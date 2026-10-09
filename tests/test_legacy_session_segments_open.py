"""옛 모양 장면(키 넷뿐)이 든 편집본도 열려야 한다 (Task 15).

시험용 프로젝트 둘(`project-de4b6405`, `243-ab10834c`)이 열면 500이었다.
`cut_action`·`review_required`가 없는 옛 장면에서 응답 검증이 실패했다.
저장 계층은 이미 `str(segment.get("cut_action") or "keep")`로 읽는다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def test_latest_session_opens_with_defaults_for_a_four_key_legacy_segment(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "옛 모양 시험"}).json()["project_id"]
    LocalProjectStore(tmp_path).save_editing_session(
        project_id=project_id,
        timeline_id="timeline-longform",
        session_payload={
            "history": [],
            "segments": [
                {"segment_id": "seg-000", "caption_text": "a", "start_sec": 0.0, "end_sec": 5.0},
            ],
        },
    )

    response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")

    assert response.status_code == 200, response.text
    segment = response.json()["segments"][0]
    assert segment["cut_action"] == "keep"
    assert segment["review_required"] is False
