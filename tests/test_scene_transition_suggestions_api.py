"""유진의 장면 전환 추천 -- 화면이 실제로 부를 수 있는 자리.

`implementation-plan.ko.md` §4.1.2가 "아직 아닌 것"으로 남겨 뒀던 마지막
항목이다(owner 지시 2026-08-31, "너가 할 수 있는거 먼저 진행해줘"). 순수
계산은 `test_scene_transitions.py`가 이미 촘촘히 본다 -- 여기는 그 계산이
실제 세션 데이터를 읽어 실제 API 경로로 나오는지만 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "transition suggestions"}).json()["project_id"]
    return client, project_id


def _seed_session(tmp_path: Path, project_id: str, segments: list[dict]) -> str:
    store = LocalProjectStore(tmp_path / "projects")
    saved = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline-suggestions",
        session_payload={"segments": segments, "history": []},
    )
    return str(saved["session_id"])


def test_the_screen_can_fetch_a_real_recommendation(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    session_id = _seed_session(tmp_path, project_id, [
        {"segment_id": "seg-1", "caption_text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep",
         "broll_override": {"asset_id": "asset-a", "asset_uri": "local://a"}},
        {"segment_id": "seg-2", "caption_text": "둘째 장면", "start_sec": 4.0, "end_sec": 8.0, "cut_action": "keep",
         "broll_override": {"asset_id": "asset-b", "asset_uri": "local://b"}},
    ])

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/transition-suggestions")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "suggestions": [
            {"segment_id": "seg-2", "type": "fade", "duration_sec": 0.5, "reason": "different_broll_asset"},
        ],
    }


def test_an_already_chosen_scene_is_not_recommended_again(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    session_id = _seed_session(tmp_path, project_id, [
        {"segment_id": "seg-1", "caption_text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep",
         "broll_override": {"asset_id": "asset-a", "asset_uri": "local://a"}},
        {"segment_id": "seg-2", "caption_text": "둘째 장면", "start_sec": 4.0, "end_sec": 8.0, "cut_action": "keep",
         "broll_override": {"asset_id": "asset-b", "asset_uri": "local://b"},
         "transition_in": {"type": "dissolve", "duration_sec": 0.4, "chosen_by": "owner"}},
    ])

    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/transition-suggestions")

    assert response.status_code == 200, response.text
    assert response.json() == {"suggestions": []}


def test_a_recommendation_applies_through_the_same_endpoint_the_owner_uses(tmp_path: Path) -> None:
    """유진이 골랐다는 표시(`chosen_by: yujin`)가 실제로 저장되는지까지 본다 --
    추천을 보여 주기만 하고 적용 경로가 없으면 완료가 아니다(CLAUDE.md §4)."""
    client, project_id = _client(tmp_path)
    session_id = _seed_session(tmp_path, project_id, [
        {"segment_id": "seg-1", "caption_text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep", "review_required": False,
         "broll_override": {"asset_id": "asset-a", "asset_uri": "local://a"}},
        {"segment_id": "seg-2", "caption_text": "둘째 장면", "start_sec": 4.0, "end_sec": 8.0, "cut_action": "keep", "review_required": False,
         "broll_override": {"asset_id": "asset-b", "asset_uri": "local://b"}},
    ])
    suggestion = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/transition-suggestions"
    ).json()["suggestions"][0]
    session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{suggestion['segment_id']}/transition",
        json={
            "transition": {"type": suggestion["type"], "duration_sec": suggestion["duration_sec"], "chosen_by": "yujin"},
            "expected_revision": session["session_revision"],
        },
    )

    assert response.status_code == 200, response.text
    saved_segment = next(s for s in response.json()["segments"] if s["segment_id"] == "seg-2")
    assert saved_segment["transition_in"] == {"type": "fade", "duration_sec": 0.5, "chosen_by": "yujin"}
    # 적용한 뒤에는 같은 경계를 다시 추천하지 않는다.
    again = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/transition-suggestions")
    assert again.json() == {"suggestions": []}
