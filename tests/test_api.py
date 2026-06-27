from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_health_endpoint_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_project_creation_endpoint_returns_local_storage_metadata(tmp_path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post("/api/projects", json={"name": "Narration Draft"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Narration Draft"
    assert payload["root_storage_uri"].startswith("local://projects/")
