from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.postgres_project_store import PostgresProjectStore


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("VIDEOBOX_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set VIDEOBOX_TEST_POSTGRES_URL to run PostgreSQL store integration tests")
    return value


def test_postgres_store_bootstraps_and_lists_a_project(tmp_path: Path, postgres_url: str) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)

    project = store.bootstrap_project(f"Postgres project {uuid4().hex}")

    assert next(item for item in store.list_projects() if item["project_id"] == project.project_id) == {
        "project_id": project.project_id,
        "name": project.name,
        "status": "draft",
        "root_storage_uri": f"local://projects/{project.project_id}",
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def test_api_selects_postgres_store_when_database_url_is_configured(
    monkeypatch, tmp_path: Path, postgres_url: str
) -> None:
    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", postgres_url)

    with TestClient(create_app(projects_root=tmp_path)) as client:
        assert isinstance(client.app.state.store, PostgresProjectStore)
        created = client.post("/api/projects", json={"name": f"API PostgreSQL project {uuid4().hex}"})
        listed = client.get("/api/projects")

    assert created.status_code == 201
    assert created.json()["project_id"] in {item["project_id"] for item in listed.json()["projects"]}
