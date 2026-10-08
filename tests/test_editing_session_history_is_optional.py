"""편집 세션을 읽을 때 `history`(되돌리기 기록)는 선택이다.

편집기 화면은 `history`를 읽지 않는데, 0907 프로젝트에서는 세션 830KB 중
817KB가 그 기록이었다. 화면은 `?include_history=false`로 빼고 읽는다.
기본(쿼리 없음)은 지금처럼 전부 -- 유진·MCP 같은 다른 소비자를 지킨다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _seeded(tmp_path: Path) -> tuple[TestClient, str, str]:
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id = client.post("/api/projects", json={"name": "history optional"}).json()["project_id"]
    store = LocalProjectStore(tmp_path / "projects")
    saved = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline-history",
        session_payload={
            "segments": [
                {"segment_id": "s1", "caption_text": "첫 장면", "start_sec": 0.0, "end_sec": 2.0, "cut_action": "keep", "review_required": False},
            ],
            "history": [{"mutation_type": "x", "segment_id": "s1", "inverse_payload": {"segments": []}}],
        },
    )
    return client, project_id, str(saved["session_id"])


def test_default_keeps_full_history_for_other_consumers(tmp_path: Path) -> None:
    client, project_id, session_id = _seeded(tmp_path)
    by_id = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}")
    latest = client.get(f"/api/projects/{project_id}/editing-sessions/latest")
    assert by_id.status_code == 200, by_id.text
    assert len(by_id.json()["history"]) == 1
    assert len(latest.json()["history"]) == 1


def test_include_history_false_returns_empty_history(tmp_path: Path) -> None:
    client, project_id, session_id = _seeded(tmp_path)
    by_id = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}?include_history=false")
    latest = client.get(f"/api/projects/{project_id}/editing-sessions/latest?include_history=false")
    assert by_id.json()["history"] == []
    assert latest.json()["history"] == []
    assert by_id.json()["segments"][0]["segment_id"] == "s1"
