from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.orchestration import (
    LocalOnlyRuntimeService,
    build_local_only_runtime_service,
)
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_core_engine.short_form_scene_pick import (
    COMPOSE_WAIT_CEILING_SECONDS,
    SCAN_WAIT_CEILING_SECONDS,
)
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)


@dataclass
class _OfflineProvider:
    """유진이 꺼져 있는 상태. 시험이 기계 상태에 따라 달라지지 않게 못박는다."""

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        raise LLMProviderError(provider_name="local_qwen", message="engine off")


def _offline_app(tmp_path: Path, *, name: str = "Output variants API", provider: object | None = None):
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider or _OfflineProvider()),
    )
    return app


def _client(tmp_path: Path) -> tuple[TestClient, str, dict]:
    app = _offline_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Output variants API"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "text": "a"},
                {"segment_id": "seg-b", "text": "b"},
            ],
            "history": [],
        },
    )
    return client, project["project_id"], session


def test_list_variants_lazily_seeds_defaults_with_source_identity(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    response = client.get(
        f"/api/projects/{project_id}/output-variants",
        params={"session_id": session["session_id"]},
    )

    assert response.status_code == 200
    variants = response.json()["variants"]
    assert [item["kind"] for item in variants] == ["horizontal", "vertical_full"]
    assert variants[0]["source_session_id"] == session["session_id"]
    assert variants[0]["source_session_revision"] == 1
    assert variants[0]["variant_revision"] == 1


def test_create_highlight_is_explicit_and_optional(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    response = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201
    assert response.json()["variant"]["kind"] == "vertical_highlight"


def test_create_highlight_auto_selects_dense_caption_segments(tmp_path: Path) -> None:
    # owner 결정(2026-08-28): "하이라이트 변형 만들기 -- 이것도 자동으로 만들도록
    # 해줘." 전에는 만들자마자 `selected_segment_ids`가 비어 있어서 전체 장면이
    # 그대로 하이라이트가 됐다 -- 자막이 빽빽한 장면 위주로 골라서 실제로 원본보다
    # 짧아지는지 확인한다.
    app = _offline_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Auto highlight"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                # 말이 빽빽한 짧은 구간 -- 높은 점수, 골라야 한다.
                {"segment_id": "seg-dense", "caption_text": "정말 중요한 대사가 여기 가득 담겨 있어요", "start_sec": 0.0, "end_sec": 2.0},
                # 자막이 아예 없는 긴 정적 구간 -- 낮은 점수, 빠져야 한다.
                {"segment_id": "seg-silent", "caption_text": "", "start_sec": 2.0, "end_sec": 30.0},
            ],
            "history": [],
        },
    )
    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201
    variant = response.json()["variant"]
    assert variant["selected_segment_ids"] == ["seg-dense"]
    assert variant["master_segment_ids"] == ["seg-dense", "seg-silent"]


def test_patch_and_rebase_return_revisioned_variant_conflicts(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    patched = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": 1,
            "patch": {"overrides": {"crop": {"mode": "cover"}}, "lock_fields": ["crop"]},
        },
    )
    assert patched.status_code == 200
    assert patched.json()["variant"]["variant_revision"] == 2

    rebased = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/rebase",
        json={"new_master_revision": 2, "changed_fields": ["crop"]},
    )
    assert rebased.status_code == 200, rebased.text
    assert rebased.json()["variant"]["source_session_revision"] == 2
    assert rebased.json()["variant"]["conflicts"][0]["field"] == "crop"

    resolved = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": rebased.json()["variant"]["variant_revision"],
            "patch": {"resolve_conflicts": {"crop": "keep_local"}},
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["variant"]["conflicts"] == []
    assert resolved.json()["variant"]["locks"][0]["field"] == "crop"


def test_materialize_writes_derived_timeline_with_full_identity(tmp_path: Path) -> None:
    client, project_id, session = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 1},
    )

    assert response.status_code == 201
    timeline = response.json()["materialization"]
    assert timeline["source_session_id"] == session["session_id"]
    assert timeline["source_session_revision"] == 1
    assert timeline["source_variant_id"] == variant["variant_id"]
    assert timeline["source_variant_revision"] == 1
    assert timeline["timeline_id"]


def test_materialize_route_gives_each_shape_its_own_canvas(tmp_path: Path) -> None:
    """**변형본을 만드는 자리가 둘이다.** 여기(편집기의 `가로·세로 비교` 준비)와
    `local_pipeline._materialize_variant_for_output`(출력 화면의 `가로·세로 출력
    만들기`)이 같은 복사 로직을 따로 갖고 있었다.

    2026-09-11에 크기 결함을 파이프라인 쪽만 고쳤는데, 이 라우터가 먼저 돌면
    틀린 크기의 타임라인이 `save_variant_materialization`에 캐시되고 파이프라인은
    **그걸 재사용한다** -- 고친 것이 조용히 건너뛰어진다. 그래서 두 자리를 한
    함수로 묶고, 이 시험이 그 자리를 지킨다.
    """
    client, project_id, _ = _client(tmp_path)
    variants = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"]
    sizes = {}
    for variant in variants:
        response = client.post(
            f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
            json={"expected_master_session_revision": 1},
        )
        assert response.status_code == 201, response.text
        timeline = client.app.state.store.get_timeline_run(
            project_id=project_id,
            timeline_id=response.json()["materialization"]["timeline_id"],
        )
        sizes[variant["kind"]] = timeline.get("output")

    assert sizes["horizontal"] == {"width": 1920, "height": 1080}
    assert sizes["vertical_full"] == {"width": 1080, "height": 1920}


def test_materialize_carries_current_approved_review_to_variant_timeline(tmp_path: Path) -> None:
    app = _offline_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Approved variant"}).json()
    store = app.state.store
    source = store.save_timeline_run(
        project_id=project["project_id"],
        output_mode="review",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        session_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "history": []},
    )
    store.save_review_state(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        status="approved",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variant = client.get(
        f"/api/projects/{project['project_id']}/output-variants",
        params={"session_id": session["session_id"]},
    ).json()["variants"][0]

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 1},
    )

    assert response.status_code == 201, response.text
    materialization = response.json()["materialization"]
    review = store.get_review_state(
        project_id=project["project_id"],
        timeline_id=materialization["timeline_id"],
    )
    assert review["status"] == "approved"
    assert review["source_session_id"] == session["session_id"]
    assert review["source_session_revision"] == 1
    assert review["source_variant_id"] == variant["variant_id"]
    assert review["source_variant_revision"] == variant["variant_revision"]


def test_materialize_stale_master_revision_fails_closed(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": 999},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "stale_master_revision"


def test_patch_stale_variant_revision_does_not_mutate(tmp_path: Path) -> None:
    client, project_id, _ = _client(tmp_path)
    variant = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    response = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": 0,
            "patch": {"overrides": {"audio": {"gain_db": -3}}},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "stale_variant_revision"
    current = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"][0]
    assert current["variant_revision"] == 1
    assert current["overrides"]["audio"] is None


def test_materialize_reuses_revision_identity_and_preserves_master_tracks(tmp_path: Path) -> None:
    app = _offline_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "Materialization reuse"}).json()
    store = app.state.store
    source = store.save_timeline_run(
        project_id=project["project_id"],
        output_mode="horizontal",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={
            "tracks": [{"track_type": "narration", "clips": [{"clip_id": "clip-1"}]}],
            "segments": [{"segment_id": "seg-a", "text": "a"}],
        },
    )
    session = store.save_editing_session(
        project_id=project["project_id"],
        timeline_id=source["timeline_id"],
        session_payload={"segments": [{"segment_id": "seg-a", "text": "a"}], "history": []},
    )
    variants_url = f"/api/projects/{project['project_id']}/output-variants"
    variant = client.get(variants_url, params={"session_id": session["session_id"]}).json()["variants"][0]
    materialize_url = f"{variants_url}/{variant['variant_id']}/materialize"

    first = client.post(materialize_url, json={"expected_master_session_revision": 1})
    second = client.post(materialize_url, json={"expected_master_session_revision": 1})

    assert first.status_code == 201
    assert second.status_code == 201
    first_materialization = first.json()["materialization"]
    second_materialization = second.json()["materialization"]
    assert second_materialization["timeline_id"] == first_materialization["timeline_id"]
    derived = store.get_timeline_run(
        project_id=project["project_id"],
        timeline_id=first_materialization["timeline_id"],
    )
    assert derived["tracks"] == [{"track_type": "narration", "clips": [{"clip_id": "clip-1"}]}]


def test_materialize_route_rebuilds_a_cache_left_by_the_old_copy_logic(tmp_path: Path) -> None:
    """이 라우터도 `_materialize_variant_for_output`과 같은 함정에 걸린다.

    2026-09-11 실물 측정(project-e6c75c36): 캔버스 크기 결함을 고친 뒤에도
    owner의 세로 변형본은 여전히 1920x1080이었다 -- `source_variant_revision`이
    안 바뀌었으니 `get_variant_materialization`이 옛(버그가 있던) 조립 로직이
    만든 타임라인을 그대로 돌려줬기 때문이다. 이 라우터(`가로·세로 비교` 준비)와
    출력 화면 쪽(`local_pipeline._materialize_variant_for_output`) 둘 다 같은
    `existing is not None`이면 무조건 재사용하는 모양을 갖고 있었다 -- 여기서
    라우터 쪽을 따로 잰다. 옛 로직이 만들었을 법한(마스터와 같은 가로 크기)
    타임라인을 캐시 행에 직접 심어 두고 materialize를 호출한다.
    """
    client, project_id, session = _client(tmp_path)
    store = client.app.state.store
    variants = client.get(
        f"/api/projects/{project_id}/output-variants",
        params={"session_id": session["session_id"]},
    ).json()["variants"]
    vertical = next(item for item in variants if item["kind"] == "vertical_full")

    stale_timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_id=vertical["source_session_id"],
        source_session_revision=vertical["source_session_revision"],
        timeline_payload={"tracks": [], "segments": [], "output": {"width": 1920, "height": 1080}},
    )
    store.save_variant_materialization(
        project_id=project_id,
        variant_id=vertical["variant_id"],
        source_session_id=vertical["source_session_id"],
        source_session_revision=vertical["source_session_revision"],
        source_variant_revision=vertical["variant_revision"],
        timeline_id=stale_timeline["timeline_id"],
        segments=[],
    )

    response = client.post(
        f"/api/projects/{project_id}/output-variants/{vertical['variant_id']}/materialize",
        json={"expected_master_session_revision": vertical["source_session_revision"]},
    )

    assert response.status_code == 201, response.text
    materialization = response.json()["materialization"]
    assert materialization["timeline_id"] != stale_timeline["timeline_id"]
    rebuilt = store.get_timeline_run(
        project_id=project_id, timeline_id=materialization["timeline_id"]
    )
    assert rebuilt["output"] == {"width": 1080, "height": 1920}


def _short_form_project(tmp_path: Path, *, provider: object | None = None):
    """장면 셋짜리 프로젝트와, 그 위에 만들어진 숏폼(세로 하이라이트) 모양."""
    app = _offline_app(tmp_path, provider=provider)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "숏폼 장면 고르기"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-hook", "caption_text": "이것만 보세요", "start_sec": 0.0, "end_sec": 3.0},
                {"segment_id": "seg-middle", "caption_text": "중간 설명", "start_sec": 3.0, "end_sec": 20.0},
                {"segment_id": "seg-close", "caption_text": "결론입니다", "start_sec": 20.0, "end_sec": 24.0},
            ],
            "history": [],
        },
    )
    variant = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    ).json()["variant"]
    return app, client, project["project_id"], session, variant


def _save_short_form_proposal(
    app, project_id: str, session: dict, variant: dict, parameters: dict
) -> str:
    """유진이 실제로 돌려주는 모양 그대로 만들어 저장한다 (파싱 -> 되짚기 -> 저장).

    `parameters`를 그대로 받는 이유는 숏폼에 닿는 유진 action이 둘이기 때문이다 --
    장면을 직접 고르는 `select_segments`와 판 전체를 다시 판단하게 하는
    `remake_short_form`. 둘이 **같은 적용 경로**를 지나는지 재려면 같은 harness를
    써야 한다.
    """
    import json as _json

    from videobox_core_engine.yujin_creator_proposal_adapter import (
        activate_yujin_media_projection,
        parse_and_project_yujin_creator_output,
    )
    from videobox_domain_models.yujin_creator_context import YujinCreatorContext

    store = app.state.store
    asset_index_revision = int(store.get_asset_index_revision(project_id))
    session_revision = int(session["session_revision"])
    context = YujinCreatorContext.model_validate(
        {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": project_id,
            "session_id": session["session_id"],
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
            "timeline_id": "timeline-source",
            "timeline_version": "v001",
            "segment_summaries": tuple(
                {
                    "segment_id": str(item["segment_id"]),
                    "start_sec": float(item["start_sec"]),
                    "end_sec": float(item["end_sec"]),
                    "text": str(item["caption_text"]),
                }
                for item in session["segments"]
            ),
            "media_candidates": (),
            "timeline_summary": {
                "duration_sec": 24.0,
                "track_count": 1,
                "clip_count": 3,
                "gap_count": 0,
            },
            "supported_controls": ({"kind": "output_variant", "mode": "recommendation_only"},),
            "current_surface": "edit",
            "selection_kind": "variant",
            "master_session_id": session["session_id"],
            "master_session_revision": session_revision,
            "variant_id": str(variant["variant_id"]),
            "variant_kind": "vertical_highlight",
            "variant_revision": int(variant["variant_revision"]),
        }
    )
    payload = {
        "schema_version": "videobox.yujin-response.v1",
        "reply_text": "숏폼에 쓸 장면을 골랐어요.",
        "proposal": {
            "proposal_id": "proposal-short-form",
            "base_revision": f"session:{session['session_id']}:revision:{session_revision}:assets:{asset_index_revision}",
            "title": "숏폼 장면 고르기",
            "rationale": "훅과 결론만 남깁니다.",
            "variant_id": str(variant["variant_id"]),
            "base_variant_revision": int(variant["variant_revision"]),
            "operations": [
                {
                    "operation_id": "short-form-selection",
                    "kind": "output_variant",
                    "target": {
                        "variant_id": str(variant["variant_id"]),
                        "track_id": "output-variant",
                    },
                    "parameters": dict(parameters),
                    "requires_materialization": False,
                    "preview_summary": "숏폼에 넣을 장면 목록",
                }
            ],
        },
    }
    raw = (
        "숏폼에 쓸 장면을 골랐어요.\n"
        "```videobox-yujin-response\n"
        f"{_json.dumps(payload, ensure_ascii=False)}\n"
        "```"
    )
    projection = parse_and_project_yujin_creator_output(
        raw,
        context,
        revision=1,
        trusted_project_id=project_id,
        trusted_run_id="run-short-form",
    )
    assert projection.proposal is not None, projection.validation_outcome
    projection = activate_yujin_media_projection(
        store=store,
        project_id=project_id,
        context=context,
        projection=projection,
    )
    proposal = projection.proposal
    assert proposal is not None
    assert proposal.status == "ready", proposal.diff.get("proposal_mode")
    store.save_director_proposal(project_id, proposal)
    return proposal.proposal_id


def test_yujin_short_form_cut_applies_through_the_real_apply_route(tmp_path: Path) -> None:
    """유진이 고른 숏폼 장면이 **실제 적용 경로**를 통과해 저장된다.

    이 저장소가 반복해서 겪은 함정이라 화면이 밟는 경로 그대로 잰다 -- 스키마와
    적용기가 있어도 라우터가 `overrides`만 합치고 있으면 장면 선택은
    어디에도 닿지 않는다.
    """
    app, client, project_id, session, variant = _short_form_project(tmp_path)
    before = list(variant["selected_segment_ids"] or [])
    proposal_id = _save_short_form_proposal(
        app,
        project_id,
        session,
        variant,
        {"action": "select_segments", "segment_ids": ["seg-hook", "seg-close"]},
    )
    candidate_id = app.state.store.get_director_proposal(
        project_id=project_id, proposal_id=proposal_id
    ).candidates[0].candidate_id

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply",
        json={
            "candidate_ids": [candidate_id],
            "expected_revision": int(session["session_revision"]),
        },
    )

    assert response.status_code == 200, response.text
    applied = response.json()["variant"]
    assert applied["selected_segment_ids"] == ["seg-hook", "seg-close"]
    assert applied["variant_revision"] == int(variant["variant_revision"]) + 1

    # 되돌리기 -- 화면의 `전체 장면으로 되돌리기`와 **같은 문**(통째 목록 PATCH)이다.
    undone = client.patch(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}",
        json={
            "expected_variant_revision": applied["variant_revision"],
            "patch": {"selected_segment_ids": before},
        },
    )

    assert undone.status_code == 200, undone.text
    assert undone.json()["variant"]["selected_segment_ids"] == before


# --- 숏폼 장면 고르기: 자막 글자 수가 아니라 유진의 판단 -----------------------
#
# 가짜 모델은 `tests/test_api_caption_translation.py`와 같은 틀이다 -- 진짜
# `LocalOnlyRuntimeService`에 **가짜 provider**를 끼운다. LM Studio가 떠 있든
# 말든 결과가 같아야 하므로 시험은 절대 진짜 모델을 부르지 않는다.


def _compose_answer(prompt: str) -> StructuredLLMResponse:
    """짜기 단계의 가짜 응답. 훑기에서 고른 대목을 그대로 이어 붙인 후보 하나.

    **가짜를 한 자리에만 둔다.** 2026-09-12에 짜기 단계가 생겼을 때 시험 대역이
    셋이었고, 하나만 고치면 나머지가 `IndexError`로 죽는다.
    """
    lines = [
        int(line.strip().partition(". ")[0])
        for line in prompt.split("고를 대목:", 1)[1].splitlines()
        if line.strip()[:1].isdigit()
    ]
    output_data = {
        "thinking": "가짜 유진이 먼저 생각한다",
        "candidates": [{"lines": lines, "reason": "퍼질 이유 한 줄"}],
        "chosen": 1,
        "schema_version": "videobox.short-form-compose.v1",
    }
    return StructuredLLMResponse(
        provider_name="local_qwen",
        model_name="Qwen3-32B",
        output_data=output_data,
        raw_text=json.dumps(output_data, ensure_ascii=False),
        metadata={},
    )


@dataclass
class _ScenePickProvider:
    """훅·결론·숫자를 보고 고르는 가짜 심사자. 자막 길이는 보지 않는다."""

    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if "고를 대목:" in request.prompt:
            return _compose_answer(request.prompt)
        block = request.prompt.split("고를 장면:", 1)[1]
        picks = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped[:1].isdigit():
                continue
            number_text, _, caption = stripped.partition(". ")
            # 줄 모양은 `번호. (N초) 글`이다. 시각 표시를 떼지 않으면 `(0초)`의
            # 숫자가 "숫자·결과가 있다"로 세어진다.
            if caption.startswith("("):
                caption = caption.partition(") ")[2]
            if "결론" in caption:
                picks.append({"scene": int(number_text), "worth": 5, "why": "conclusion"})
            elif any(character.isdigit() for character in caption):
                picks.append({"scene": int(number_text), "worth": 4, "why": "number_or_result"})
        output_data = {"schema_version": "videobox.short-form-scene-pick.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


def _runtime_factory(provider: object):
    def factory(_: object) -> LocalOnlyRuntimeService:
        return LocalOnlyRuntimeService(
            local_provider=provider,  # type: ignore[arg-type]
            local_runtime_config=LocalOpenAICompatibleRuntimeConfig(
                enabled=True,
                base_url="http://127.0.0.1:1234/v1",
                model_name="Qwen3-32B",
                timeout_seconds=42,
            ),
        )

    return factory


def test_create_short_form_uses_yujin_judgement_not_caption_length(tmp_path: Path) -> None:
    """자막이 빽빽한 잡담보다 **짧아도 결론인 장면**을 고른다.

    지금 기준(`len(caption_text) / duration`)이면 잡담이 이긴다. 대표님이 원한
    것은 마케팅 판단이다 -- 훅, 결론, 숫자·결과가 나오는 대목.
    """
    provider = _ScenePickProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "숏폼 고르기"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                # 말은 빽빽하지만 알맹이가 없는 장면 -- 밀도로는 1등이다.
                {"segment_id": "seg-filler", "caption_text": "그래서 뭐 아무튼 저는 그냥 이렇게 저렇게 해봤고요 네 그렇습니다 아시겠죠", "start_sec": 0.0, "end_sec": 2.0},
                # 자막은 짧지만 결론이다.
                {"segment_id": "seg-conclusion", "caption_text": "결론은 이겁니다", "start_sec": 2.0, "end_sec": 12.0},
            ],
            "history": [],
        },
    )

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["variant"]["selected_segment_ids"] == ["seg-conclusion"]
    assert body["scene_pick"]["judged_by"] == "yujin"
    assert provider.calls, "유진을 부르지도 않고 유진이 골랐다고 하면 안 된다"


def test_when_yujin_is_off_the_screen_is_told_it_was_not_her_choice(tmp_path: Path) -> None:
    """대비책이 **보이는** 대비책인지. 대표님이 유진의 판단이라고 믿는 결과가
    사실은 글자 수 세기면 그게 제일 나쁘다.
    """
    app = _offline_app(tmp_path)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "유진 꺼짐"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-filler", "caption_text": "그래서 뭐 아무튼 그냥 이렇게 저렇게 해봤고요 네", "start_sec": 0.0, "end_sec": 2.0},
                {"segment_id": "seg-conclusion", "caption_text": "결론은 이겁니다", "start_sec": 2.0, "end_sec": 12.0},
            ],
            "history": [],
        },
    )

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201, response.text
    scene_pick = response.json()["scene_pick"]
    assert scene_pick["judged_by"] == "caption_density"
    assert scene_pick["scenes_read_by_yujin"] == 0
    assert "유진이 고른" not in scene_pick["notice"]
    assert "유진이 전체 장면을 읽고" not in scene_pick["notice"]
    assert "자막" in scene_pick["notice"]


def test_a_long_form_does_not_take_its_short_only_from_the_opening(tmp_path: Path) -> None:
    """243을 곱해 본다. 지금 컨테이너의 최대 장면 수는 5개라 작은 입력으로는
    이 기능의 가장 어려운 부분이 시험에 닿지 않는다.
    """
    provider = _ScenePickProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "롱폼"}).json()
    segments = []
    for index in range(243):
        if index == 242:
            caption = "결론은 이겁니다"
        elif index == 180:
            caption = "매출이 3배 늘었어요"
        else:
            caption = "그래서 말인데요 " * (6 if index < 32 else 1)
        segments.append({
            "segment_id": f"timeline_001:{index:03d}",
            "caption_text": caption,
            "start_sec": float(index * 5),
            "end_sec": float(index * 5 + 5),
        })
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={"segments": segments, "history": []},
    )

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    picked = body["variant"]["selected_segment_ids"]
    assert "timeline_001:242" in picked, "결론이 빠지면 마케팅용이 아니다"
    assert body["scene_pick"]["judged_by"] == "yujin"
    # 2026-09-12부터는 **빠지는 구간이 없다.** 상한을 넘으면 대목을 버리는 대신
    # 합쳐서 줄이므로 유진이 영상 전 구간을 읽는다. 그러니 문구도 그렇게 말한다 --
    # 덜 봤다고 말하는 것도, 더 봤다고 말하는 것도 거짓이다.
    assert body["scene_pick"]["scenes_total"] == 243
    assert body["scene_pick"]["scenes_read_by_yujin"] == 243
    assert "전 구간" in body["scene_pick"]["notice"]
    assert "확인하지 못했어요" not in body["scene_pick"]["notice"]


# --- 숏폼 다시 만들기 --------------------------------------------------------
#
# 2026-09-11 실물 측정: 한 편집본에 숏폼이 한 번 생기면 다시 만들 길이 없었다.
# `(project_id, source_session_id, kind)` 유일 제약 때문에 두 번째 만들기는
# `IntegrityError`로 죽어 대표님에게 맨 `Internal Server Error`가 갔고, 지우는
# 문은 없으며(`delete_output_variant`는 저장소 전체에 0건), 화면 단추는 한 번
#쓰면 조용히 죽어 있었다.
#
# 그래서 "다시 만들기"는 **같은 모양의 장면 목록을 다시 판단해 갈아 끼우는
# 일**이다 -- 지우고 새로 만드는 것이 아니다. 되돌리기는 이미 있는 통째 목록
# PATCH(`전체 장면으로 되돌리기`)가 그대로 지킨다.


@dataclass
class _ChangingScenePickProvider:
    """부를 때마다 다른 장면을 고르는 가짜 심사자.

    **다시 만들기가 실제로 다시 판단하는지**를 재려면 두 번의 답이 달라야 한다.
    같은 답이면 "다시 골랐다"와 "아무것도 안 했다"를 구분할 수 없다.
    """

    sweeps: int = 0
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if "고를 대목:" in request.prompt:
            return _compose_answer(request.prompt)
        self.sweeps += 1
        wanted = "결론입니다" if self.sweeps == 1 else "중간 설명"
        block = request.prompt.split("고를 장면:", 1)[1]
        picks = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped[:1].isdigit():
                continue
            number_text, _, caption = stripped.partition(". ")
            if caption.startswith("("):
                caption = caption.partition(") ")[2]
            if wanted in caption:
                picks.append({"scene": int(number_text), "worth": 5, "why": "conclusion"})
        output_data = {"schema_version": "videobox.short-form-scene-pick.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


def _repick(client: TestClient, project_id: str, variant: dict) -> dict:
    """숏폼을 다시 고르라고 **걸어 두고** 결과를 받아 온다.

    이 길은 2026-09-12부터 걸어 두고 물어보는 길이다(202 + 폴링) -- 실측으로 약
    400초가 걸려 nginx 330초 벽 안에서는 한 요청으로 끝낼 수 없다. 시험이 이
    도우미 한 자리를 쓰는 이유는 화면도 한 자리(`makeShortForm`)만 쓰기 때문이다.
    """
    started = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/repick",
        json={"expected_variant_revision": int(variant["variant_revision"])},
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    polled = client.get(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/repick/{job_id}"
    )
    assert polled.status_code == 200, polled.text
    body = polled.json()
    assert body["status"] == "succeeded", body
    return body["result"]

def test_a_short_can_be_remade_and_yujin_judges_the_scenes_again(tmp_path: Path) -> None:
    """대표님이 숏폼을 **다시** 만들 수 있다. 유진이 판을 다시 읽고 목록을 갈아 끼운다."""
    provider = _ChangingScenePickProvider()
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)
    assert variant["selected_segment_ids"] == ["seg-close"]

    body = _repick(client, project_id, variant)

    assert body["variant"]["selected_segment_ids"] == ["seg-middle"]
    assert body["variant"]["variant_revision"] == int(variant["variant_revision"]) + 1
    assert body["scene_pick"]["judged_by"] == "yujin"
    assert provider.sweeps == 2, "다시 만들기가 유진을 다시 부르지 않으면 다시 판단한 것이 아니다"
    # 저장된 값까지 본다. 응답만 보면 화면이 받은 것과 저장된 것이 갈릴 수 있다.
    stored = app.state.store.get_output_variant(
        project_id=project_id, variant_id=variant["variant_id"]
    )
    assert stored["selected_segment_ids"] == ["seg-middle"]


def test_remaking_a_short_that_lands_on_the_same_scenes_still_succeeds(tmp_path: Path) -> None:
    """다시 판단했는데 결과가 같을 수 있다. 그때 대표님에게 오류를 보이지 않는다.

    `apply_variant_patch`는 바뀐 것이 없으면 **버전을 안 올린 그대로** 돌려주고,
    그 값을 저장소에 그대로 넘기면 `variant_revision_must_advance_by_one`으로
    422가 난다 -- 판단은 정상이었는데 화면에는 실패로 보인다. 그래서 결과가 같아도
    버전은 올라간다(`remade_short_form_variant`). 두 쓰는 문(화면 PATCH·유진 제안
    트랜잭션)이 둘 다 버전 1 증가를 요구하므로, 부르는 쪽마다 따로 판단하게 두면
    두 경로가 갈린다.
    """
    app, client, project_id, session, variant = _short_form_project(tmp_path)
    before = list(variant["selected_segment_ids"] or [])

    body = _repick(client, project_id, variant)

    assert body["variant"]["selected_segment_ids"] == before
    assert body["variant"]["variant_revision"] == int(variant["variant_revision"]) + 1
    assert body["scene_pick"]["judged_by"] == "caption_density"


def test_a_second_short_tells_the_owner_what_to_do_instead_of_a_bare_500(tmp_path: Path) -> None:
    """같은 편집본에 숏폼을 두 번 만들려 하면 **할 수 있는 일**을 알려 준다.

    전에는 유일 제약 위반이 아무도 안 잡아서 맨 `Internal Server Error`가 갔다.
    """
    app, client, project_id, session, variant = _short_form_project(tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "short_form_already_exists"


def test_yujin_can_remake_the_short_when_the_owner_tells_her_to(tmp_path: Path) -> None:
    """대표님이 유진에게 "숏폼 다시 만들어줘"라고 말해도 된다.

    채팅으로 `select_segments`를 쓰면 유진은 창작 맥락에 담긴 장면(최대 32개)만
    보고 고른다 -- 243장면짜리 롱폼에서는 단추 경로(영상 전 구간에서 고르게
    추린 48개)보다 못한 판단이고, 프로필도 그럴 때는 단추를 쓰라고 안내한다.
    "단추를 쓰세요"는 **말로 시킬 수 있다**는 요구를 못 지킨다. 그래서
    `remake_short_form`은 단추와 **같은 판단 쓸기**를 서버에서 돌린다.
    """
    provider = _ChangingScenePickProvider()
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)
    assert variant["selected_segment_ids"] == ["seg-close"]
    proposal_id = _save_short_form_proposal(
        app, project_id, session, variant, {"action": "remake_short_form"}
    )
    candidate_id = app.state.store.get_director_proposal(
        project_id=project_id, proposal_id=proposal_id
    ).candidates[0].candidate_id

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply",
        json={
            "candidate_ids": [candidate_id],
            "expected_revision": int(session["session_revision"]),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["variant"]["selected_segment_ids"] == ["seg-middle"]
    assert body["scene_pick"]["judged_by"] == "yujin"
    assert provider.sweeps == 2


# --- 2026-09-12: 퍼질까로 고르고, 그 이유를 화면까지 보낸다 -------------------
#
# owner 지시: "단순히 자르는것보다 자극적으로 숏폼이 확산할수 있을정도로 llm 이
# 구분 하도록 생각하면서 만들어야지." 그리고 장면이 아니라 **발화**에서 고른다.


@dataclass
class _SpreadProvider:
    """퍼질까로 고르고 후보 숏폼을 짜는 가짜 유진. 두 단계를 다 받는다."""

    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if "고를 대목:" in request.prompt:
            lines = [
                int(line.strip().partition(". ")[0])
                for line in request.prompt.split("고를 대목:", 1)[1].splitlines()
                if line.strip()[:1].isdigit()
            ]
            output_data = {
                "thinking": "통념을 뒤집는 첫마디가 손을 멈춘다",
                "candidates": [{"lines": lines, "reason": "대놓고 솔직한 한마디라 남에게 보내고 싶어져요"}],
                "chosen": 1,
                "schema_version": "videobox.short-form-compose.v1",
            }
        else:
            picks = []
            for line in request.prompt.split("고를 장면:", 1)[1].splitlines():
                stripped = line.strip()
                if not stripped[:1].isdigit():
                    continue
                number_text, _, rest = stripped.partition(". ")
                if "뭐하러 알려" in rest:
                    picks.append({"scene": int(number_text), "worth": 5})
            output_data = {"schema_version": "videobox.short-form-spread-scan.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


def test_the_short_form_is_judged_from_the_transcript_and_its_reason_reaches_the_screen(
    tmp_path: Path,
) -> None:
    """**장면 자막이 비어 있어도** 숏폼이 나온다 -- 판단 재료가 전사에 있다.

    그리고 유진이 "왜 퍼질지" 댄 문장이 화면이 받는 응답에 실려 온다. 값만
    만들고 아무도 안 읽으면 배선이 아니다.
    """
    provider = _SpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "퍼질까로 고르기"}).json()
    store = app.state.store
    store.save_transcript(
        project_id=project["project_id"],
        source_asset_id="asset-video",
        transcript_text="전사",
        segments=[
            {"start_sec": 0.0, "end_sec": 10.0, "text": "오늘은 세 가지를 알려드릴게요"},
            {"start_sec": 10.0, "end_sec": 20.0, "text": "그걸 알면 제가 팔지 뭐하러 알려 줄까요"},
            {"start_sec": 20.0, "end_sec": 30.0, "text": "정리하면 이렇습니다"},
        ],
    )
    session = store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {
                    "segment_id": f"seg-{index}",
                    "caption_text": "",
                    "start_sec": float(index) * 10.0,
                    "end_sec": float(index + 1) * 10.0,
                    "source_offset_sec": float(index) * 10.0,
                    "broll_override": {"asset_id": "asset-video"},
                }
                for index in range(3)
            ],
            "history": [],
        },
    )

    response = client.post(
        f"/api/projects/{project['project_id']}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["variant"]["selected_segment_ids"] == ["seg-1"]
    assert body["scene_pick"]["judged_by"] == "yujin"
    assert (
        body["scene_pick"]["spread_reason"]
        == "대놓고 솔직한 한마디라 남에게 보내고 싶어져요"
    )
    assert "뭐하러 알려" in "\n".join(call.prompt for call in provider.calls)


def test_the_longer_wait_reaches_the_socket_not_just_the_engine(tmp_path: Path) -> None:
    """**기다리기가 실제로 기다림이 되는지.**

    상한은 `LocalQwenHTTPTransport`가 만들 때 한 번 박히고 소켓까지 내려간다.
    그래서 엔진이 "150초 기다릴게"라고 말해도 그 값이 소켓에 닿지 않으면 호출은
    여전히 30초에 끊긴다 -- 재지 않으면 못 볼 자리다(2026-09-12 실측: 30초
    상한에서 대표님 영상의 묶음 여섯 중 넷이 끊겼다).
    """
    del tmp_path
    seen: list[int] = []

    class _Recording:
        def __call__(self, request: object, timeout: int | None = None):
            seen.append(int(timeout or 0))
            raise LLMProviderError(
                provider_name="local_qwen", message="여기까지만 본다", error_code="stop"
            )

    service = build_local_only_runtime_service(
        store=None,  # type: ignore[arg-type]
        local_runtime_config=LocalOpenAICompatibleRuntimeConfig(
            enabled=True,
            base_url="http://127.0.0.1:1234/v1",
            model_name="Qwen3-32B",
            timeout_seconds=30,
        ),
        local_http_client=_Recording(),
    )

    try:
        service.generate_structured(
            project_id="proj-1",
            task_type=LLMTaskType.SHORT_FORM_SCENE_PICK,
            prompt="아무 말",
            response_schema={"type": "object", "properties": {"a": {"type": "string"}}},
            wait_seconds=SCAN_WAIT_CEILING_SECONDS,
        )
    except Exception:  # noqa: BLE001
        pass

    assert seen == [SCAN_WAIT_CEILING_SECONDS], seen


def test_the_screen_waits_for_yujin_in_the_background_instead_of_hitting_the_proxy_wall(
    tmp_path: Path,
) -> None:
    """숏폼 다시 만들기는 **걸어 두고 물어보는** 일이다.

    실측(2026-09-12, 대표님 영상 94장면): 훑기 129.8초 + 짜기 266.8초 = 약 400초.
    nginx는 330초에 끊는다(`docker/workspace-nginx.conf`) -- 같은 요청 안에서는
    끝까지 기다릴 수가 없고, 끊기면 대표님은 우리 한국말 대신 프록시의 504 HTML을
    본다. 더빙·자막 번역이 같은 이유로 이미 이 모양이다.
    """
    provider = _ChangingScenePickProvider()
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)

    started = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/repick",
        json={"expected_variant_revision": int(variant["variant_revision"])},
    )

    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    assert started.json()["status"] == "processing"

    polled = client.get(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/repick/{job_id}"
    )
    assert polled.status_code == 200, polled.text
    body = polled.json()
    assert body["status"] == "succeeded", body
    assert body["result"]["variant"]["selected_segment_ids"] == ["seg-middle"]
    assert body["result"]["scene_pick"]["judged_by"] == "yujin"
    # 뒤에서 도니까 짜기에 **꽉 찬 상한**을 줄 수 있다. 같은 요청 안에서 돌면
    # 예산이 이 값을 깎는다.
    compose_calls = [call for call in provider.calls if "고를 대목:" in call.prompt]
    assert compose_calls, "짜기를 안 불렀으면 퍼질 이유가 안 나온다"
    assert compose_calls[-1].provider_context["timeout_seconds"] == COMPOSE_WAIT_CEILING_SECONDS
    # 저장된 값까지 본다. 응답만 보면 화면이 받은 것과 저장된 것이 갈릴 수 있다.
    stored = app.state.store.get_output_variant(
        project_id=project_id, variant_id=variant["variant_id"]
    )
    assert stored["selected_segment_ids"] == ["seg-middle"]


def test_a_stale_revision_is_refused_before_yujin_is_ever_called(tmp_path: Path) -> None:
    """걸어 두기 **전에** 막는다. 400초를 기다린 뒤에 알리지 않는다."""
    provider = _ChangingScenePickProvider()
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)
    del app, session
    calls_before = len(provider.calls)

    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/repick",
        json={"expected_variant_revision": int(variant["variant_revision"]) + 5},
    )

    assert response.status_code == 409, response.text
    assert len(provider.calls) == calls_before, "막을 요청에 유진을 불렀다"


# --- 쓸 자리만 나눈다 (대표님 지시 2026-09-12) --------------------------------
#
# "그럼 이걸 모두다 안쪼개도 되니까, 마케팅적으로 가장 자극되고 사용할수 있는것만
# 분석해서 최적화로 쪼개면 되잖아. 굳이 안쓰는걸 다 쪼갤필요는 없잖아"
#
# 실측(2026-09-12): 93번 나누기에 마지막 한 번이 298초, 세션 JSON 13.2MB.
# 그런데 그 94장면 중 숏폼이 쓴 것은 6개였다. 판단은 전사에서 하므로 장면이
# 필요 없고, 자를 자리에만 경계가 필요하다.


@dataclass
class _OwnerSizedSpreadProvider:
    """전 구간을 읽고 **한 대목만** 퍼진다고 하는 가짜 유진."""

    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if "고를 대목:" in request.prompt:
            lines = [
                int(line.strip().partition(". ")[0])
                for line in request.prompt.split("고를 대목:", 1)[1].splitlines()
                if line.strip()[:1].isdigit()
            ]
            output_data = {
                "thinking": "통념을 뒤집는 첫마디가 손을 멈춘다",
                "candidates": [{"lines": lines, "reason": "매출 3배라는 결과로 끝까지 붙잡아요"}],
                "chosen": 1,
                "schema_version": "videobox.short-form-compose.v1",
            }
        else:
            picks = []
            for line in request.prompt.split("고를 장면:", 1)[1].splitlines():
                stripped = line.strip()
                if not stripped[:1].isdigit():
                    continue
                number_text, _, rest = stripped.partition(". ")
                if "퍼질 한마디" in rest:
                    picks.append({"scene": int(number_text), "worth": 5})
            output_data = {"schema_version": "videobox.short-form-spread-scan.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


_OWNER_VIDEO_SEC = 494.837
_OWNER_UTTERANCE_COUNT = 213


def _owner_sized_transcript() -> list[dict[str, object]]:
    """대표님 실제 영상과 같은 규모: 발화 213개, 494.837초."""
    step = _OWNER_VIDEO_SEC / float(_OWNER_UTTERANCE_COUNT)
    return [
        {
            "start_sec": index * step,
            "end_sec": (index + 1) * step,
            "text": (
                "퍼질 한마디 매출이 3배 올랐어요"
                if index in (100, 101)
                # 두 번째 판단이 **다른 자리**를 고를 수 있게 표시를 하나 더 둔다.
                else "다른 한마디 고객이 답을 알려 줬어요"
                if index in (20, 21)
                else f"그냥 설명 {index}입니다"
            ),
        }
        for index in range(_OWNER_UTTERANCE_COUNT)
    ]


def _owner_sized_board(app, project_id: str, *, timeline_id: str = "timeline-source") -> dict:
    """제품의 실제 문이 만드는 모양 -- **장면 하나**가 영상 전체다.

    `+ 새로 만들기`(장면 1개) -> 자료실 영상 깔기 -> 장면 길이를 영상 길이로.
    받아쓰기는 장면을 나누지 않는다(`captions_from_transcript`는 글만 옮긴다).
    """
    store = app.state.store
    store.save_transcript(
        project_id=project_id,
        source_asset_id="asset-video",
        transcript_text="전사",
        segments=_owner_sized_transcript(),
    )
    return store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline_id,
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "",
                    "start_sec": 0.0,
                    "end_sec": _OWNER_VIDEO_SEC,
                    "source_offset_sec": 0.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset-video"},
                }
            ],
            "history": [],
            "undo_stack": [],
            "redo_stack": [],
        },
    )


def test_a_short_cuts_only_the_places_it_uses_not_the_whole_video(tmp_path: Path) -> None:
    """대표님 규모(494.837초·발화 213개)에서 **쓸 자리만** 나눈다.

    전에는 이 판에서 고를 장면이 하나뿐이라 "숏폼"이 원본과 같은 494초였고,
    60초 숏폼을 얻으려면 먼저 93번을 나눠야 했다(마지막 한 번에 298초).
    """
    provider = _OwnerSizedSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "쓸 자리만 나누기"}).json()["project_id"]
    session = _owner_sized_board(app, project_id)
    assert len(session["segments"]) == 1

    response = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scene_pick"]["judged_by"] == "yujin"
    # **판이 바뀐 것을 화면에 말해 준다.** 안 말하면 대표님 화면은 장면 하나를
    # 그대로 보여 주고, 다음 편집이 조용히 충돌한다.
    assert body["scene_pick"]["board_scenes_cut"] > 0
    assert "나눴어요" in body["scene_pick"]["notice"]

    board = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    # **93번이 아니다.** 고른 대목마다 양 끝 둘이니 장면은 그만큼만 늘어난다.
    assert 1 < len(board["segments"]) <= 20, f"너무 많이 나눴다: {len(board['segments'])}"
    # 판 버전은 **한 번만** 오른다 -- 나누기가 한 덩이라서.
    assert int(board["session_revision"]) == int(session["session_revision"]) + 1
    assert len(board["undo_stack"]) == 1, "되돌리기 한 번으로 취소돼야 한다"

    duration_by_id = {
        str(segment["segment_id"]): float(segment["end_sec"]) - float(segment["start_sec"])
        for segment in board["segments"]
    }
    picked = body["variant"]["selected_segment_ids"]
    assert picked and set(picked) <= set(duration_by_id)
    total = sum(duration_by_id[segment_id] for segment_id in picked)
    assert 8.0 <= total <= 60.0, f"숏폼 길이가 20~60초 범위 밖이다: {total:.2f}초"

    undone = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/undo",
        json={"expected_revision": int(board["session_revision"])},
    )
    assert undone.status_code == 200, undone.text
    restored = undone.json()["session"] if "session" in undone.json() else undone.json()
    assert len(restored["segments"]) == 1, "한 번 눌러 판이 그대로 돌아와야 한다"


def test_remaking_a_short_twice_does_not_cut_the_same_place_again(tmp_path: Path) -> None:
    """`다시 만들기`를 두 번 눌러도 같은 자리를 두 번 나누지 않는다.

    **왜 판 버전이 그래도 한 칸 오르는가**(2026-09-12 정정): 두 번째 누름은 직전
    변환이 낸 자리를 **되돌린 뒤 새로 나눈다**. 판단이 같은 대목을 골라 결과 장면이
    같아도, 되돌리고 다시 나누는 일은 한 덩이 편집이라 판 버전이 한 칸 오른다.
    전에는 "나눌 자리가 없다"며 아무것도 안 해서 버전이 그대로였는데, 그 길은 두 번째
    판단이 **이미 잘린 판**을 보게 만드는 원인이었다.
    """
    provider = _OwnerSizedSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "두 번 눌러도"}).json()["project_id"]
    session = _owner_sized_board(app, project_id)

    created = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )
    assert created.status_code == 201, created.text
    after_first = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert len(after_first["segments"]) > 1, "첫 번째에 자리를 냈어야 두 번째를 잴 수 있다"

    again = _repick(client, project_id, created.json()["variant"])

    after_second = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert len(after_second["segments"]) == len(after_first["segments"]), "조각이 늘면 안 된다"
    # 같은 판단이면 **같은 자리**가 나와야 한다 -- 되돌리고 새로 나눠도 결과는 같다.
    assert _picked_bounds(after_second, again["variant"]) == _picked_bounds(
        after_first, created.json()["variant"]
    )
    assert again["variant"]["selected_segment_ids"] == created.json()["variant"]["selected_segment_ids"]
    # 되돌리기·다시 나누기가 **한 덩이**다. 판 버전은 누름마다 정확히 한 칸만 오른다.
    assert int(after_second["session_revision"]) == int(after_first["session_revision"]) + 1
    assert len(after_second["undo_stack"]) == 1, "되돌리기 한 번으로 원래대로 돌아가야 한다"


@dataclass
class _ShiftingSpreadProvider:
    """판단마다 **다른 자리**가 퍼진다고 하는 가짜 유진.

    다시 만들기가 새 자리를 나누는지 재려면 두 번의 답이 달라야 한다. 같은
    답이면 "새 자리를 나눴다"와 "아무것도 안 했다"를 구분할 수 없다.
    """

    sweeps: int = 0

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        if "고를 대목:" in request.prompt:
            self.sweeps += 1
            lines = [
                int(line.strip().partition(". ")[0])
                for line in request.prompt.split("고를 대목:", 1)[1].splitlines()
                if line.strip()[:1].isdigit()
            ]
            output_data = {
                "thinking": "무엇이 손을 멈추게 하는지 먼저 본다",
                "candidates": [{"lines": lines, "reason": "인용하고 싶은 한마디예요"}],
                "chosen": 1,
                "schema_version": "videobox.short-form-compose.v1",
            }
        else:
            wanted = "퍼질 한마디" if self.sweeps == 0 else "다른 한마디"
            picks = []
            for line in request.prompt.split("고를 장면:", 1)[1].splitlines():
                stripped = line.strip()
                if not stripped[:1].isdigit():
                    continue
                number_text, _, rest = stripped.partition(". ")
                if wanted in rest:
                    picks.append({"scene": int(number_text), "worth": 5})
            output_data = {"schema_version": "videobox.short-form-spread-scan.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


def test_yujin_telling_us_to_remake_also_cuts_only_what_it_uses(tmp_path: Path) -> None:
    """말로 시켜도 같은 일이 일어난다 -- 새 자리를 나누고 그 판 버전으로 옮긴다.

    유진 경로는 제안 수명까지 한 트랜잭션으로 닫는 **다른 문**을 쓴다
    (`apply_director_variant_proposal_transaction`). 단추만 고치면 이 문이 나누기
    전 판 버전을 요구해서 조용히 거절한다 -- 같은 로직이 두 자리에 있는 함정이다.
    """
    provider = _ShiftingSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "말로 시켜 나누기"}).json()["project_id"]
    session = _owner_sized_board(app, project_id)
    variant = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    ).json()["variant"]
    board = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert len(board["segments"]) > 1

    proposal_id = _save_short_form_proposal(
        app, project_id, board, variant, {"action": "remake_short_form"}
    )
    candidate_id = app.state.store.get_director_proposal(
        project_id=project_id, proposal_id=proposal_id
    ).candidates[0].candidate_id

    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply",
        json={
            "candidate_ids": [candidate_id],
            "expected_revision": int(board["session_revision"]),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scene_pick"]["judged_by"] == "yujin"
    after = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    # 새 자리를 나눴다 -- 두 번째 판단이 다른 대목을 골랐으니까. **장면 수로는 잴 수
    # 없다**(2026-09-12 정정): 직전 자리를 되돌린 뒤 새로 나누므로 조각이 쌓이지 않고,
    # 대목 수가 같으면 장면 수도 같다. 그래서 고른 **자리**가 옮겨졌는지를 잰다.
    assert _picked_bounds(after, body["variant"]) != _picked_bounds(board, variant)
    assert len(after["segments"]) == len(board["segments"]), "조각이 쌓이면 안 된다"
    # 모양이 **지금** 판 버전을 가리켜야 출력이 `stale_master_revision`으로 안 막힌다.
    assert int(body["variant"]["source_session_revision"]) == int(after["session_revision"])
    materialized = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": int(after["session_revision"])},
    )
    assert materialized.status_code == 201, materialized.text


def _picked_bounds(board: dict, variant: dict) -> list[tuple[float, float]]:
    """숏폼이 실제로 쓰는 **판 위 시각**. 장면 이름이 아니라 자리를 잰다."""
    picked = set(variant["selected_segment_ids"])
    return [
        (round(float(segment["start_sec"]), 3), round(float(segment["end_sec"]), 3))
        for segment in board["segments"]
        if str(segment["segment_id"]) in picked
    ]


def test_pressing_convert_again_judges_the_original_board_and_never_stacks_cuts(
    tmp_path: Path,
) -> None:
    """두 번째 누름은 **첫 번째가 자른 판**이 아니라 원래 판을 보고 판단한다.

    2026-09-12 실물: 장면 하나짜리 판에서 `숏폼으로 변환`을 세 번 누르니
    **1 -> 19 장면**이 되고 이름이 `...__split_6__split_5`처럼 겹쳐 붙었다. 유진이
    읽은 장면 수도 1 -> 13으로 늘어, 두 번째 판단이 원본이 아니라 이미 잘린 판을
    본다는 증거가 됐다.
    """
    provider = _ShiftingSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "두 번 눌러도 같은 출발점"}).json()["project_id"]
    session = _owner_sized_board(app, project_id)
    assert len(session["segments"]) == 1

    created = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["scene_pick"]["scenes_total"] == 1
    after_first = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert len(after_first["segments"]) > 1, "첫 번째에 자리를 냈어야 두 번째를 잴 수 있다"

    again = _repick(client, project_id, first["variant"])

    # **유진이 본 판이 첫 번째와 같아야 한다.** 지금은 첫 번째가 자른 장면 수가
    # 그대로 넘어가 판단 재료가 달라진다.
    assert again["scene_pick"]["scenes_total"] == first["scene_pick"]["scenes_total"]
    after_second = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    # 두 번째 판단은 **다른 대목**을 골랐다(`_ShiftingSpreadProvider`). 그래도 조각이
    # 쌓이지 않는다 -- 직전 변환이 낸 자리를 먼저 되돌리고 새로 나누니까.
    #
    # 장면 **id**로는 잴 수 없다. 되돌린 뒤 같은 원본 장면을 다시 나누면 이름 번호가
    # 처음부터 다시 붙어 다른 자리에도 같은 id가 나온다 -- 그래서 **시각**을 잰다.
    assert _picked_bounds(after_second, again["variant"]) != _picked_bounds(
        after_first, first["variant"]
    ), "두 번째가 다른 대목을 골라야 '되돌리고 새로 나눴다'를 잴 수 있다"
    assert len(after_second["segments"]) == len(after_first["segments"])
    stacked = [
        str(segment["segment_id"])
        for segment in after_second["segments"]
        if str(segment["segment_id"]).count("__split_") > 1
    ]
    assert not stacked, f"이름이 겹쳐 붙었다: {stacked}"
    # 안내문 `되돌리기 한 번으로 원래대로 돌아가요`가 참이어야 한다.
    assert len(after_second["undo_stack"]) == 1
    undone = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/undo",
        json={"expected_revision": int(after_second["session_revision"])},
    )
    assert undone.status_code == 200, undone.text
    restored = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert len(restored["segments"]) == 1, "한 번 눌러 원래 판으로 돌아와야 한다"


def _owner_sized_board_with_approved_review(app, project_id: str) -> tuple[dict, dict]:
    """검토 승인까지 마친 판. `숏폼으로 변환` 단추가 켜지는 조건 그대로다.

    화면 단추는 `canRenderSubtitle`(`OutputsPage.tsx`)로 잠기는데, 그 조건이
    타임라인과 승인 둘 다 **지금 판 버전**을 가리킬 것을 요구한다. 그래서 시험도
    타임라인 행을 실제로 만들고 승인을 그 판 버전에 묶는다.
    """
    store = app.state.store
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={"segments": [{"segment_id": "seg_001", "text": ""}], "tracks": []},
    )
    session = _owner_sized_board(app, project_id, timeline_id=timeline["timeline_id"])
    store.save_review_state(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_id=session["session_id"],
        source_session_revision=int(session["session_revision"]),
    )
    return session, timeline


def test_cutting_only_scene_boundaries_does_not_unlock_the_owners_approval(
    tmp_path: Path,
) -> None:
    """장면 경계를 나누는 것은 완성본을 **한 바이트도** 바꾸지 않으므로 승인을 풀지 않는다.

    2026-09-12 실물: 변환이 판을 바꾸니 승인이 풀려 `숏폼으로 변환`이 비활성이 됐고,
    두 번째로 누르려면 대표님이 `검토본 다시 만들기` -> `검토 승인`을 다시 밟아야
    했다. "한 번 누르면 되는 단추"가 두 번째부터 세 번 누르는 단추가 된 것이다.

    **승인을 대신 눌러 주는 것이 아니다** -- 이미 있는 승인의 상태와 승인 시각을
    그대로 두고, 가리키는 판 버전만 옮긴다. 승인이 없었으면 여전히 없다.
    """
    provider = _OwnerSizedSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "승인이 풀리지 않는다"}).json()["project_id"]
    session, timeline = _owner_sized_board_with_approved_review(app, project_id)
    store = app.state.store
    approved_at = store.get_review_state(
        project_id=project_id, timeline_id=timeline["timeline_id"]
    )["approved_at"]

    created = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["scene_pick"]["board_scenes_cut"] > 0, "나눠야 잴 수 있는 시험이다"
    board = store.get_editing_session(project_id=project_id, session_id=session["session_id"])
    review = store.get_review_state(project_id=project_id, timeline_id=timeline["timeline_id"])
    assert review["status"] == "approved"
    assert bool(review["is_current"]) is True, "경계 나누기는 승인을 풀지 않는다"
    assert int(review["source_session_revision"]) == int(board["session_revision"])
    assert review["source_session_id"] == session["session_id"]
    # 승인 시각은 **대표님이 실제로 누른 때**로 남는다. 다시 찍으면 없던 승인을
    # 방금 받은 것처럼 보인다.
    assert review["approved_at"] == approved_at
    # 화면 단추는 타임라인 쪽 판 버전도 본다. 한쪽만 옮기면 단추는 여전히 잠긴다.
    assert int(
        store.get_timeline_run(project_id=project_id, timeline_id=timeline["timeline_id"])[
            "source_session_revision"
        ]
    ) == int(board["session_revision"])


def test_a_board_with_no_approval_does_not_gain_one_from_the_short_form_cut(
    tmp_path: Path,
) -> None:
    """승인이 없던 판은 나누기를 지나도 승인이 **생기지 않는다.**

    사람 게이트를 없애지 않는다는 경계다(`CLAUDE.md` §2.1). 승인을 옮기는 코드가
    `save_review_state`를 쓰면 `is_current`를 1로 되살리고 `approved_at`을 다시
    찍어 없던 승인이 생긴 것처럼 보인다 -- 그 길을 안 쓴다는 것을 여기서 지킨다.
    """
    provider = _OwnerSizedSpreadProvider()
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(provider),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "승인 없는 판"}).json()["project_id"]
    store = app.state.store
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_id="pending-session",
        source_session_revision=1,
        timeline_payload={"segments": [{"segment_id": "seg_001", "text": ""}], "tracks": []},
    )
    session = _owner_sized_board(app, project_id, timeline_id=timeline["timeline_id"])

    created = client.post(
        f"/api/projects/{project_id}/output-variants",
        json={"source_session_id": session["session_id"], "kind": "vertical_highlight"},
    )

    assert created.status_code == 201, created.text
    review = store.get_review_state(project_id=project_id, timeline_id=timeline["timeline_id"])
    assert review["status"] != "approved"
    assert review["approved_at"] is None
