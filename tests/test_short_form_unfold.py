"""숏폼을 **펼쳐서 따로 편집한다**.

대표님 문장(2026-09-12)의 후반부: "내가 그걸 받아봤는데, 만약에 뭔가 보정이 좀 더
필요하면 내가 수동으로 좀 더 수정을 하면 되잖아."

지금은 그게 막힌다. 숏폼(`OutputVariant`)이 담을 수 있는 것은 장면 목록과 화면
**전체** 설정 다섯(`crop`·`focal`·`caption`·`safe_area`·`audio`)뿐이고, 장면별
편집은 전부 마스터 세션에서 온다(`variant_render_session`이 마스터를 숏폼 장면
목록에 투영한다). 그래서 숏폼의 한 장면 자막을 고치면 **원본 8분 영상의 그 장면도
같이 고쳐진다.**

이 시험이 재는 것은 그 한 가지다 -- 펼친 편집본에서 장면을 고쳐도 원본 편집본은
글자 하나 안 바뀐다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.orchestration import LocalOnlyRuntimeService
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    StructuredLLMRequest,
    StructuredLLMResponse,
)

# 유진 경로 시험은 **이미 있는 harness를 가져온다.** 창작 맥락을 만들고 유진
# 응답을 파싱해 제안으로 저장하는 일은 `test_api_output_variants`가 이미 한다
# (`select_segments`·`remake_short_form`가 그걸 쓴다). 여기에 한 벌 더 베끼면
# 같은 로직이 두 자리에 있게 되고, 이 저장소가 반복해 걸린 함정이 그것이다.
from test_api_output_variants import _save_short_form_proposal, _short_form_project


@dataclass
class _OfflineProvider:
    """유진이 꺼져 있는 상태. 펼치기는 판단이 아니라 그릇을 옮기는 일이라 모델이
    필요 없다 -- 시험이 기계 상태에 흔들리지 않게 못박는다."""

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        raise LLMProviderError(provider_name="local_qwen", message="engine off")


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


def _board_with_short_form(tmp_path: Path) -> tuple[TestClient, object, str, dict, dict]:
    """장면 셋인 편집본 + 그중 둘을 고른 숏폼."""
    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=_runtime_factory(_OfflineProvider()),
    )
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "숏폼 펼치기"}).json()
    project_id = project["project_id"]
    timeline = app.state.store.save_timeline_run(
        project_id=project_id,
        output_mode="landscape",
        timeline_payload={
            "version": "v001",
            "timebase": "seconds",
            "fps_num": 30,
            "fps_den": 1,
            "output": {"width": 1920, "height": 1080},
            "tracks": [],
        },
    )
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id=str(timeline["timeline_id"]),
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "caption_text": "첫 장면", "start_sec": 0.0, "end_sec": 5.0, "cut_action": "keep", "review_required": False},
                {"segment_id": "seg-b", "caption_text": "둘째 장면", "start_sec": 5.0, "end_sec": 10.0, "cut_action": "keep", "review_required": False},
                {"segment_id": "seg-c", "caption_text": "셋째 장면", "start_sec": 10.0, "end_sec": 15.0, "cut_action": "keep", "review_required": False},
            ],
            "history": [],
        },
    )
    # **원본 판에 이력이 있어야 시험에 이가 있다.** 갓 만든 판은 `history`가
    # 비어 있어서, 펼친 판이 원본 이력을 물려받아도 아무 시험이 안 빨개진다.
    # 대표님이 숏폼을 뽑기 전에 이미 한 번 고쳤다고 보는 것이 실제에도 가깝다.
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/segments/seg-b/caption",
        json={"expected_revision": int(session["session_revision"]), "caption_text": "둘째 장면"},
    )
    session = app.state.store.get_editing_session(
        project_id=project_id, session_id=str(session["session_id"])
    )
    assert session["history"], "원본 판에 이력이 안 생겼다 -- 이 시험의 전제가 깨졌다"
    variant = app.state.store.create_output_variant(
        project_id=project_id,
        source_session_id=str(session["session_id"]),
        kind="vertical_highlight",
        selected_segment_ids=["seg-a", "seg-c"],
    )
    return client, app, project_id, session, variant


def test_editing_an_unfolded_short_form_leaves_the_original_board_untouched(tmp_path: Path) -> None:
    """**이 시험이 이 조각의 요점이다.**

    펼친 편집본에서 자막을 고치고, 원본 편집본의 자막과 판 버전이 그대로인지 본다.
    지금은 숏폼에 장면별 편집을 담을 자리가 없어서 이 길 자체가 없다.
    """
    client, _app, project_id, session, variant = _board_with_short_form(tmp_path)

    unfolded = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/unfold",
        json={"expected_variant_revision": int(variant["variant_revision"])},
    )
    assert unfolded.status_code == 201, unfolded.text
    board = unfolded.json()["editing_session"]
    assert board["session_id"] != session["session_id"]
    # 펼친 판에는 고른 장면만 있고, 0초부터 이어 붙어 있다.
    assert [item["segment_id"] for item in board["segments"]] == ["seg-a", "seg-c"]
    assert [(item["start_sec"], item["end_sec"]) for item in board["segments"]] == [(0.0, 5.0), (5.0, 10.0)]

    edited = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{board['session_id']}/segments/seg-c/caption",
        json={"expected_revision": int(board["session_revision"]), "caption_text": "숏폼용으로 더 자극적인 한마디"},
    )
    assert edited.status_code == 200, edited.text
    assert [item["caption_text"] for item in edited.json()["segments"]] == ["첫 장면", "숏폼용으로 더 자극적인 한마디"]

    master = client.get(f"/api/projects/{project_id}/editing-sessions/{session['session_id']}").json()
    assert [item["caption_text"] for item in master["segments"]] == ["첫 장면", "둘째 장면", "셋째 장면"]
    assert int(master["session_revision"]) == int(session["session_revision"])


def test_without_unfolding_the_same_edit_changes_the_original_board(tmp_path: Path) -> None:
    """**변형 탐침.** 펼치지 않고 같은 편집을 하면 원본이 같이 바뀐다.

    이것이 없애려는 결함 자체다 -- 숏폼의 장면별 편집은 마스터 세션에만 쓸 수
    있으므로, 펼치기가 없으면 위 시험의 편집이 원본 8분 영상을 고친다. 이 시험이
    초록인 동안 위 시험이 지키는 것이 무엇인지 분명해진다.
    """
    client, _app, project_id, session, variant = _board_with_short_form(tmp_path)

    assert variant["source_session_id"] == session["session_id"]
    edited = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/segments/seg-c/caption",
        json={"expected_revision": int(session["session_revision"]), "caption_text": "숏폼용으로 더 자극적인 한마디"},
    )
    assert edited.status_code == 200, edited.text
    # 숏폼의 장면을 고쳤을 뿐인데 원본 판의 자막이 바뀌었다.
    assert [item["caption_text"] for item in edited.json()["segments"]] == [
        "첫 장면",
        "둘째 장면",
        "숏폼용으로 더 자극적인 한마디",
    ]


def test_undo_on_the_unfolded_board_is_its_own_and_leaves_the_master_history_alone(
    tmp_path: Path,
) -> None:
    """되돌리기가 펼친 판에서 **혼자** 돈다.

    유진에게 말한 편집은 확인 없이 바로 적용되고, 되돌리기가 유일한 안전장치다
    (owner 결정 2026-09-01). 펼친 판의 되돌리기가 안 돌거나 원본 이력과 섞이면
    그 안전장치가 없는 것과 같다.
    """
    client, app, project_id, session, variant = _board_with_short_form(tmp_path)
    board = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/unfold",
        json={"expected_variant_revision": int(variant["variant_revision"])},
    ).json()["editing_session"]
    # 갓 펼친 판은 되돌릴 것이 없다 -- 원본의 이력을 물려받지 않는다.
    assert board["history"] == []
    assert board["undo_stack"] == []

    edited = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{board['session_id']}/segments/seg-a/caption",
        json={"expected_revision": int(board["session_revision"]), "caption_text": "훅 한마디"},
    ).json()
    assert [item["caption_text"] for item in edited["segments"]] == ["훅 한마디", "셋째 장면"]
    stored = app.state.store.get_editing_session(
        project_id=project_id, session_id=board["session_id"]
    )
    assert len(stored["undo_stack"]) == 1

    undone = client.post(
        f"/api/projects/{project_id}/editing-sessions/{board['session_id']}/undo",
        json={"expected_revision": int(edited["session_revision"])},
    )
    assert undone.status_code == 200, undone.text
    assert [item["caption_text"] for item in undone.json()["segments"]] == ["첫 장면", "셋째 장면"]

    master = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    # 원본 판의 이력은 펼치기 전 그대로다 -- 펼친 판에서 한 일이 여기 안 쌓인다.
    assert master["history"] == session["history"]
    assert master["undo_stack"] == session["undo_stack"]
    assert int(master["session_revision"]) == int(session["session_revision"])


def test_unfold_tells_the_owner_that_the_original_no_longer_follows(tmp_path: Path) -> None:
    """규칙 한 문장이 **화면까지 간다.** 값만 만들고 아무도 안 읽으면 배선이 아니다."""
    client, _app, project_id, _session, variant = _board_with_short_form(tmp_path)
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/unfold",
        json={"expected_variant_revision": int(variant["variant_revision"])},
    )

    assert response.status_code == 201, response.text
    assert response.json()["notice"] == "펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요."
    # 숏폼에도 펼쳤다는 기록이 남는다(버전이 한 칸 오른다).
    assert int(response.json()["variant"]["variant_revision"]) == int(variant["variant_revision"]) + 1


def test_only_the_short_form_can_be_unfolded(tmp_path: Path) -> None:
    """가로·세로 전체본은 펼칠 것이 없다 -- 장면 목록이 원본과 같다."""
    client, _app, project_id, session, _variant = _board_with_short_form(tmp_path)
    full = [
        item
        for item in client.get(
            f"/api/projects/{project_id}/output-variants",
            params={"session_id": session["session_id"]},
        ).json()["variants"]
        if item["kind"] == "vertical_full"
    ][0]

    response = client.post(
        f"/api/projects/{project_id}/output-variants/{full['variant_id']}/unfold",
        json={},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "only_vertical_highlight_can_be_unfolded"


def test_the_unfolded_board_renders_itself_even_after_the_original_is_edited(
    tmp_path: Path,
) -> None:
    """펼친 판의 완성본은 **그 판**으로 만들어진다 -- 원본을 고친 뒤에도.

    두 곳이 걸려 있다. 하나는 타임라인에서 파생 표시(`source_variant_id`)를 떼는
    것 -- 안 떼면 렌더가 이 판을 숏폼으로 보고 마스터 세션에 다시 투영해서, 펼친
    판의 편집이 완성본에 안 닿는다. 다른 하나는 "가장 나중 편집본"으로 찾는 옛
    길 -- 한 프로젝트에 판이 둘이 되면 원본을 한 번 고치는 순간 그 길이 엉뚱한
    판을(또는 아무것도) 집는다.
    """
    client, app, project_id, session, variant = _board_with_short_form(tmp_path)
    board = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/unfold",
        json={},
    ).json()["editing_session"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{board['session_id']}/segments/seg-a/caption",
        json={"expected_revision": int(board["session_revision"]), "caption_text": "펼친 판에서만 고친 자막"},
    )
    # 대표님이 원본 판으로 돌아가 한 번 고친다 -- "가장 나중"이 원본으로 바뀐다.
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/segments/seg-b/caption",
        json={"expected_revision": int(session["session_revision"]), "caption_text": "원본에서만 고친 자막"},
    )

    board_timeline = app.state.store.get_timeline_run(
        project_id=project_id, timeline_id=str(board["timeline_id"])
    )
    assert "source_variant_id" not in board_timeline
    render_session = app.state.orchestrator.pipeline._editing_session_for_output_timeline(
        project_id=project_id, timeline=board_timeline
    )
    assert render_session is not None, "펼친 판의 완성본을 만들 세션을 못 찾았다"
    assert render_session["session_id"] == board["session_id"]
    assert [item["caption_text"] for item in render_session["segments"]] == [
        "펼친 판에서만 고친 자막",
        "셋째 장면",
    ]


def test_unfolding_a_stale_short_form_is_refused(tmp_path: Path) -> None:
    """낡은 판을 펼치면 대표님이 화면에서 본 것과 다른 장면이 나온다."""
    client, _app, project_id, _session, variant = _board_with_short_form(tmp_path)
    response = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/unfold",
        json={"expected_variant_revision": int(variant["variant_revision"]) + 5},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "stale_variant_revision"


def test_yujin_can_unfold_the_short_into_its_own_board_when_told_to(tmp_path: Path) -> None:
    """대표님이 유진에게 **"이 숏폼 따로 편집하게 펼쳐줘"**라고 말해도 된다.

    화면으로 되는 일은 전부 유진에게 말해서도 되어야 한다(owner 상시 지시). 겹은
    셋이고 이 시험이 재는 것은 그 셋이 이어져 있는지다 -- 의도 스키마
    (`VariantShortFormUnfoldParameters`), 적용기(`batch_apply`의 `_is_short_form_unfold`),
    그리고 안내문(`SKILL.md`, 별도 시험이 지킨다).

    **그리고 규칙 문장이 같이 와야 한다.** 되돌릴 수 없는 일(원본과의 줄이
    끊긴다)을 말없이 하면 안 된다.
    """
    app, client, project_id, session, variant = _short_form_project(tmp_path)
    proposal_id = _save_short_form_proposal(
        app, project_id, session, variant, {"action": "unfold_to_editing_board"}
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
    board = body["editing_session"]
    assert board["session_id"] != session["session_id"]
    assert [item["segment_id"] for item in board["segments"]] == list(
        variant["selected_segment_ids"]
    )
    assert body["notice"] == "펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요."
    # 숏폼에는 펼쳤다는 기록만 남는다 -- 장면 목록은 그대로다.
    assert body["variant"]["variant_revision"] == int(variant["variant_revision"]) + 1
    assert body["variant"]["selected_segment_ids"] == list(variant["selected_segment_ids"])
    # 원본 편집본은 글자 하나 안 바뀐다.
    master = app.state.store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    assert int(master["session_revision"]) == int(session["session_revision"])
    assert [item["caption_text"] for item in master["segments"]] == [
        "이것만 보세요",
        "중간 설명",
        "결론입니다",
    ]
