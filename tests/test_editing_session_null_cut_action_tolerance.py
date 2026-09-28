"""AK-System Hermes가 `ask_yujin`으로 실제 프로젝트를 읽다가 500을 만났다
(2026-09-28, AK MCP 연결 실사용 첫 결함).

원인: `segments[].cut_action`이 저장 데이터에서 `null`인 세그먼트가 있었다.
`packages/core-engine/.../composition_plan.py`는 `cut_action`이 없거나
null이면 `"keep"`으로 다루는 관용을 이미 갖고 있다(`str(segment.get("cut_action")
or "keep")` 패턴, 여러 자리) -- 그런데 API 응답 모델
(`EditingSessionSegmentResponse.cut_action: str`)은 그 관용을 안 지켜서,
내부적으로는 멀쩡히 처리되는 데이터가 API 경계에서만 `pydantic.ValidationError`로
터져 500이 됐다(`GET /api/projects/{id}/editing-sessions/latest`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def test_latest_editing_session_tolerates_a_null_cut_action_segment(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "결함주입 시험"}).json()["project_id"]

    store = LocalProjectStore(tmp_path)
    store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline-1",
        session_payload={
            "history": [],
            "segments": [
                {
                    "segment_id": "segment-1",
                    "caption_text": "실제 데이터에서 나온 것과 같은 모양",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": None,  # 실제로 관측된 값 -- 저장 계층은 이미 이걸 "keep"으로 다룬다
                    "review_required": False,
                }
            ],
        },
    )

    response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")

    assert response.status_code == 200, response.text
    assert response.json()["segments"][0]["cut_action"] == "keep"


def test_latest_editing_session_still_reports_the_stored_cut_action_when_present(
    tmp_path: Path,
) -> None:
    """회귀 방지 -- null을 keep으로 바꾸는 관용이 실제로 저장된 값을 덮어쓰지 않는지."""
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "정상값 대조"}).json()["project_id"]

    store = LocalProjectStore(tmp_path)
    store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline-1",
        session_payload={
            "history": [],
            "segments": [
                {
                    "segment_id": "segment-1",
                    "caption_text": "지워진 장면",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "remove",
                    "review_required": False,
                }
            ],
        },
    )

    response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")

    assert response.status_code == 200, response.text
    assert response.json()["segments"][0]["cut_action"] == "remove"
