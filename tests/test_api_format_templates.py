from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_formats_start_empty_and_are_shared_across_projects(tmp_path: Path) -> None:
    # 포맷은 프로젝트가 아니라 사용자에게 붙는다. 새 프로젝트를 열어도 같은 목록이다.
    client = TestClient(create_app(projects_root=tmp_path))
    client.post("/api/projects", json={"name": "첫 프로젝트"})
    client.post("/api/projects", json={"name": "둘째 프로젝트"})

    response = client.get("/api/format-templates")

    assert response.status_code == 200
    assert response.json() == {"templates": []}


def test_saving_a_format_from_a_session_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    # 없는 편집본에서 포맷을 뽑을 수는 없다. 조용히 빈 포맷을 만들면 나중에
    # 그걸 적용했을 때 아무 일도 안 일어난다.
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates",
        json={"name": "내 포맷", "session_id": "session_missing"},
    )

    assert response.status_code == 404


def test_a_format_needs_a_name(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates",
        json={"name": "", "session_id": "session_a"},
    )

    assert response.status_code == 422


def test_applying_a_format_nobody_saved_is_reported(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "포맷"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/format-templates/format_template_missing/apply",
        json={"session_id": "session_a", "expected_revision": 1},
    )

    assert response.status_code == 404
