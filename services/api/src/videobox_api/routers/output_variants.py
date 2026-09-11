from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from videobox_api.models import (
    OutputVariantCreateRequest,
    OutputVariantMaterializeRequest,
    OutputVariantPatchRequest,
    OutputVariantRebaseRequest,
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


def build_output_variants_router(store: LocalProjectStore) -> APIRouter:
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
            return {
                "variant": store.create_output_variant(
                    project_id=project_id,
                    source_session_id=request.source_session_id,
                    kind=request.kind,
                    variant_id=request.variant_id,
                )
            }
        except Exception as error:
            _raise_variant_error(error)
            raise AssertionError("unreachable")

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
