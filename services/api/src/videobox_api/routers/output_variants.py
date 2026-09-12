from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from videobox_api.models import (
    OutputVariantCreateRequest,
    OutputVariantMaterializeRequest,
    OutputVariantPatchRequest,
    OutputVariantRebaseRequest,
    OutputVariantRepickRequest,
    OutputVariantUnfoldRequest,
)
from videobox_core_engine.output_variants import UNFOLD_INDEPENDENCE_RULE
from videobox_api.short_form_scenes import (
    remade_short_form_variant,
    scene_pick_payload,
    short_form_layout_override,
    short_form_scene_pick,
)
from videobox_core_engine.output_variants import (
    VariantInvariantError,
    apply_variant_patch,
    build_variant_timeline_payload,
    materialize_variant,
    output_variant_from_row,
    rebase_variant,
    variant_timeline_needs_rebuild,
)
from videobox_domain_models.output_variants import OutputVariant
from videobox_storage.local_project_store import (
    EditingSessionRevisionConflict,
    LocalProjectStore,
)


def _domain_variant(row: dict[str, Any]) -> OutputVariant:
    return output_variant_from_row(row)


def _raise_variant_error(error: Exception) -> None:
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail="output_variant_missing") from error
    if isinstance(error, EditingSessionRevisionConflict):
        raise HTTPException(status_code=409, detail="output_variant_revision_conflict") from error
    if isinstance(error, (VariantInvariantError, ValueError)):
        detail = str(error)
        if "stale_variant_revision" in detail:
            detail = "stale_variant_revision"
            raise HTTPException(status_code=409, detail=detail) from error
        if "stale_master_revision" in detail:
            detail = "stale_master_revision"
            raise HTTPException(status_code=409, detail=detail) from error
        raise HTTPException(status_code=422, detail=detail) from error
    raise error


def _sync_approved_variant_review(
    store: LocalProjectStore,
    *,
    project_id: str,
    source_timeline_id: str,
    timeline_id: str,
    source_session_id: str,
    source_session_revision: int,
    source_variant_id: str,
    source_variant_revision: int,
) -> None:
    """Carry an already-approved master decision onto a derived variant timeline."""
    try:
        source_review = store.get_review_state(
            project_id=project_id,
            timeline_id=source_timeline_id,
        )
    except KeyError:
        return
    if str(source_review.get("status")) != "approved":
        return
    store.save_review_state(
        project_id=project_id,
        timeline_id=timeline_id,
        status="approved",
        source_session_id=source_session_id,
        source_session_revision=source_session_revision,
        source_variant_id=source_variant_id,
        source_variant_revision=source_variant_revision,
    )


def build_output_variants_router(
    store: LocalProjectStore,
    *,
    yujin_runtime_service: Any | None = None,
    orchestrator: Any | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/output-variants")
    def list_variants(
        project_id: str,
        session_id: str | None = Query(default=None, min_length=1),
    ) -> dict[str, object]:
        try:
            return {"variants": store.ensure_output_variants(project_id=project_id, session_id=session_id)}
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post(
        "/api/projects/{project_id}/output-variants",
        status_code=status.HTTP_201_CREATED,
    )
    def create_variant(project_id: str, request: OutputVariantCreateRequest) -> dict[str, object]:
        try:
            # **숏폼에 넣을 장면은 유진이 고른다**(2026-09-11). 저장소에는 런타임이
            # 없어서 고르는 일을 저장소 밖에서 한다. 누가 골랐는지(`judged_by`)를
            # 응답에 같이 실어 보내는 이유는 화면 문구 때문이다 -- 자막 밀도로 고른
            # 결과를 "유진이 골랐어요"라고 말하면 안 된다.
            pick = short_form_scene_pick(
                store=store,
                project_id=project_id,
                session_id=request.source_session_id,
                runtime=yujin_runtime_service,
            )
            return {
                "variant": store.create_output_variant(
                    project_id=project_id,
                    source_session_id=request.source_session_id,
                    kind=request.kind,
                    variant_id=request.variant_id,
                    selected_segment_ids=pick.segment_ids,
                    # **첫 화면 제목 띠도 같은 판단에서 나온다**(`shorts_layout.py`).
                    # 유진이 짜기 한 호출에서 장면과 제목을 같이 주므로 여기서
                    # 같이 저장한다 -- 나중에 따로 저장하면 제목 없는 판이 한 번
                    # 렌더될 수 있다. 못 받았으면 `None`이고 제목 띠 없이 나간다.
                    layout=short_form_layout_override(pick),
                ),
                "scene_pick": scene_pick_payload(pick),
            }
        except sqlite3.IntegrityError as error:
            # 한 편집본에 숏폼은 하나뿐이다(`output_variants`의
            # `UNIQUE(project_id, source_session_id, kind)`). 그 위반을 전에는
            # 아무도 안 잡아서 대표님에게 맨 `Internal Server Error`가 갔다
            # (2026-09-11 컨테이너에서 재현). PostgreSQL에서도 같은 예외로 온다 --
            # `postgres_project_store.py:80`이 `psycopg`의 유일 위반을
            # `sqlite3.IntegrityError`로 옮긴다. **지우는 문을 내는 대신** 이미
            # 있는 숏폼을 다시 만들라고 알려 준다(`short_form_scenes.py` 머리말).
            raise HTTPException(status_code=409, detail="short_form_already_exists") from error
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post(
        "/api/projects/{project_id}/output-variants/{variant_id}/repick",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def repick_short_form_route(
        project_id: str,
        variant_id: str,
        request: OutputVariantRepickRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, object]:
        """숏폼을 **다시 만든다** -- 걸어 두고 바로 돌아온다.

        진행 상황은 `GET .../repick/{job_id}`.

        **비동기여야 한다(2026-09-12 실측).** 대표님 영상(94장면)에서 훑기 129.8초
        + 짜기 266.8초 = 약 400초가 걸린다. nginx는 330초에 끊으므로
        (`docker/workspace-nginx.conf`) 같은 요청 안에서 기다리면 대표님은 우리
        한국말 대신 프록시의 504 HTML을 본다. owner 결정(2026-09-12)은 "다른 모델
        쓸 때는 잠시 기다리자"인데, **기다리려면 요청 밖으로 나와야 한다.**
        더빙·자막 번역이 같은 이유로 이미 이 모양이다.

        새 모양을 만들지 않는다 -- 유일 제약 때문에 그럴 수 없고, 지우는 문은
        "되돌릴 길이 없다"는 문제를 다시 연다(`short_form_scenes.py` 머리말).
        """
        if orchestrator is None:  # pragma: no cover - 배선이 빠지면 바로 드러나야 한다
            raise HTTPException(status_code=503, detail="short_form_repick_unavailable")
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")
        expected = (
            request.expected_variant_revision
            if request.expected_variant_revision is not None
            else int(current["variant_revision"])
        )
        # **걸기 전에 막는다.** 400초를 기다린 뒤에 "낡은 값이었어요"라고 알리지
        # 않는다(자막 번역의 `start_caption_translation`과 같은 태도).
        if expected != int(current["variant_revision"]):
            raise HTTPException(status_code=409, detail="stale_variant_revision")
        if str(current.get("kind")) != "vertical_highlight":
            raise HTTPException(status_code=422, detail="only_vertical_highlight_can_be_remade")
        started = orchestrator.start_short_form_pick(project_id=project_id)
        background_tasks.add_task(
            orchestrator.run_short_form_pick_job,
            project_id=project_id,
            variant_id=variant_id,
            job_id=started["job_id"],
            runtime=yujin_runtime_service,
            expected_variant_revision=expected,
        )
        return dict(started)

    @router.get("/api/projects/{project_id}/output-variants/{variant_id}/repick/{job_id}")
    def get_repick_short_form_job(
        project_id: str, variant_id: str, job_id: str
    ) -> dict[str, object]:
        """다시 고르는 일이 어디까지 왔는지. 끝나면 `result`에 모양과 판단이 온다."""
        del variant_id
        if orchestrator is None:  # pragma: no cover
            raise HTTPException(status_code=503, detail="short_form_repick_unavailable")
        try:
            return orchestrator.get_short_form_pick_job(project_id=project_id, job_id=job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="short_form_repick_job_missing") from error

    @router.post(
        "/api/projects/{project_id}/output-variants/{variant_id}/unfold",
        status_code=status.HTTP_201_CREATED,
    )
    def unfold_short_form_route(
        project_id: str,
        variant_id: str,
        request: OutputVariantUnfoldRequest,
    ) -> dict[str, object]:
        """숏폼을 **따로 편집할 수 있는 판**으로 펼친다.

        왜 이 문이 필요한가: 숏폼이 담을 수 있는 것은 장면 목록과 화면 전체 설정
        다섯뿐이고, 장면별 편집은 전부 마스터 세션에서 온다. 그래서 숏폼의 한
        장면을 고치면 **원본 영상의 그 장면도 같이 바뀐다** -- 대표님이
        "받아봤는데 보정이 좀 더 필요하면 수동으로 수정"한다고 한 일이 막혀 있다.

        펼치면 그 뒤로는 이미 있는 편집 문 전부가 그대로 돈다(자막·확대·전환·
        효과음·오버레이·되돌리기), 그리고 유진의 편집 의도 16개도 새 배선 없이
        붙는다. 대가는 원본과의 줄이 끊기는 것이고, 그 규칙은 응답의 `notice`로
        화면까지 그대로 나간다.
        """
        if orchestrator is None:  # pragma: no cover - 배선이 빠지면 바로 드러나야 한다
            raise HTTPException(status_code=503, detail="short_form_unfold_unavailable")
        try:
            unfolded = orchestrator.unfold_short_form_editing_session(
                project_id=project_id,
                variant_id=variant_id,
                expected_variant_revision=request.expected_variant_revision,
            )
            result = {
                "editing_session": unfolded["editing_session"],
                # 펼쳤다는 기록(버전 +1)을 여기서 쓴다. 유진 경로는 제안 소진과
                # 같은 트랜잭션에서 쓰므로 그쪽이 자기 문을 쓴다.
                "variant": store.update_output_variant(
                    project_id=project_id,
                    variant_id=variant_id,
                    expected_variant_revision=int(unfolded["expected_variant_revision"]),
                    variant=unfolded["unfolded_variant"],
                ),
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")
        # **규칙 문장을 여기서 같이 보낸다.** 값만 만들고 아무도 안 읽으면 배선이
        # 아니다 -- 화면이 이 문장을 그대로 띄운다.
        return {**result, "notice": UNFOLD_INDEPENDENCE_RULE}

    @router.patch("/api/projects/{project_id}/output-variants/{variant_id}")
    def patch_variant(
        project_id: str, variant_id: str, request: OutputVariantPatchRequest
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            updated = apply_variant_patch(
                _domain_variant(current),
                request.patch,
                expected_variant_revision=request.expected_variant_revision,
            )
            return {
                "variant": store.update_output_variant(
                    project_id=project_id,
                    variant_id=variant_id,
                    expected_variant_revision=request.expected_variant_revision,
                    variant=updated,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post("/api/projects/{project_id}/output-variants/{variant_id}/rebase")
    def rebase_variant_route(
        project_id: str, variant_id: str, request: OutputVariantRebaseRequest
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            rebased = rebase_variant(
                _domain_variant(current),
                new_master_revision=request.new_master_revision,
                changed_fields=tuple(request.changed_fields),
            )
            return {
                "variant": store.update_output_variant(
                    project_id=project_id,
                    variant_id=variant_id,
                    expected_variant_revision=int(current["variant_revision"]),
                    variant=rebased,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    @router.post(
        "/api/projects/{project_id}/output-variants/{variant_id}/materialize",
        status_code=status.HTTP_201_CREATED,
    )
    def materialize_variant_route(
        project_id: str,
        variant_id: str,
        request: OutputVariantMaterializeRequest,
    ) -> dict[str, object]:
        try:
            current = store.get_output_variant(project_id=project_id, variant_id=variant_id)
            variant = _domain_variant(current)
            session = store.get_editing_session(
                project_id=project_id, session_id=variant.source_session_id
            )
            current_master_revision = int(session.get("session_revision") or 0)
            if request.expected_master_session_revision is not None and (
                current_master_revision != request.expected_master_session_revision
            ):
                raise VariantInvariantError("stale_master_revision")
            if current_master_revision != variant.source_session_revision:
                raise VariantInvariantError("stale_master_revision")
            derived = materialize_variant(
                variant,
                session.get("segments", []),
                master_session_revision=current_master_revision,
            )
            try:
                master_timeline = store.get_timeline_run(
                    project_id=project_id,
                    timeline_id=str(session.get("timeline_id") or ""),
                )
            except KeyError:
                master_timeline = {}
            # 조립은 `build_variant_timeline_payload` 한 곳에서만 한다. 예전에는
            # 출력 화면 쪽(`local_pipeline._materialize_variant_for_output`)과 여기가
            # 같은 복사 로직을 따로 들고 있었고, 2026-09-11에 크기 결함을 한쪽만
            # 고쳤더니 **여기가 먼저 돌면 틀린 타임라인이 캐시되어** 그 고침이
            # 건너뛰어졌다(`save_variant_materialization`을 나중 호출자가 재사용한다).
            timeline_payload = build_variant_timeline_payload(
                master_timeline=master_timeline, variant_kind=variant.kind, derived=derived,
                overrides=variant.overrides,
            )
            # 이 라우터만 챙기던 것들. 공용 조립은 마스터에 있는 값을 그대로
            # 물려주므로, 마스터에 없을 때 빈 목록으로 세워 두는 몫만 남는다.
            timeline_payload.update({
                "review_flags": list(master_timeline.get("review_flags", []) or []),
                "pending_recommendations": list(master_timeline.get("pending_recommendations", []) or []),
                "applied_recommendations": list(master_timeline.get("applied_recommendations", []) or []),
            })
            # 캐시(`variant_materializations`)가 있어도 무조건 재사용하지 않는다.
            # 2026-09-11 실물 측정: `source_variant_revision`이 안 바뀌었다는
            # 이유로 캐시를 그대로 돌려주면, **옛(버그가 있던) 조립 로직이 만든
            # 타임라인**을 owner가 버튼을 다시 눌러도 계속 받게 된다. 캐시가
            # 있으면 지금 payload와 대조하고(`variant_timeline_needs_rebuild`),
            # 같을 때만 재사용한다.
            try:
                existing = store.get_variant_materialization(
                    project_id=project_id,
                    variant_id=variant_id,
                    source_variant_revision=derived.source_variant_revision,
                )
                cached_timeline = store.get_timeline_run(
                    project_id=project_id,
                    timeline_id=str(existing["timeline_id"]),
                )
            except KeyError:
                existing = None
                cached_timeline = None
            if existing is not None and not variant_timeline_needs_rebuild(
                cached_timeline=cached_timeline, fresh_payload=timeline_payload
            ):
                _sync_approved_variant_review(
                    store,
                    project_id=project_id,
                    source_timeline_id=str(session.get("timeline_id") or ""),
                    timeline_id=str(existing["timeline_id"]),
                    source_session_id=derived.source_session_id,
                    source_session_revision=derived.source_session_revision,
                    source_variant_id=derived.source_variant_id,
                    source_variant_revision=derived.source_variant_revision,
                )
                return {"materialization": {
                    **existing,
                    "source_variant_id": derived.source_variant_id,
                    "source_variant_revision": derived.source_variant_revision,
                }}
            timeline = store.save_timeline_run(
                project_id=project_id,
                output_mode=variant.kind,
                source_session_id=derived.source_session_id,
                source_session_revision=derived.source_session_revision,
                timeline_payload=timeline_payload,
            )
            # (project_id, variant_id, source_variant_revision)에 ON CONFLICT
            # DO UPDATE라, 같은 revision에 낡은 행이 이미 있어도 충돌하지 않고
            # timeline_id·segments만 새 값으로 갈아 끼운다.
            materialization = store.save_variant_materialization(
                project_id=project_id,
                variant_id=variant_id,
                source_session_id=derived.source_session_id,
                source_session_revision=derived.source_session_revision,
                source_variant_revision=derived.source_variant_revision,
                timeline_id=timeline["timeline_id"],
                segments=derived.segments,
            )
            _sync_approved_variant_review(
                store,
                project_id=project_id,
                source_timeline_id=str(session.get("timeline_id") or ""),
                timeline_id=str(timeline["timeline_id"]),
                source_session_id=derived.source_session_id,
                source_session_revision=derived.source_session_revision,
                source_variant_id=derived.source_variant_id,
                source_variant_revision=derived.source_variant_revision,
            )
            return {"materialization": {**materialization, **{
                "timeline_id": timeline["timeline_id"],
                "source_session_id": derived.source_session_id,
                "source_session_revision": derived.source_session_revision,
                "source_variant_id": derived.source_variant_id,
                "source_variant_revision": derived.source_variant_revision,
            }}}
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

    return router
