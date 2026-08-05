from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> LocalProjectStore:
    return LocalProjectStore(tmp_path)


def test_archived_project_disappears_from_the_default_list_but_data_stays(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("kept-project")

    store.archive_project(project_id=project.project_id)

    assert project.project_id not in {item["project_id"] for item in store.list_projects()}
    # The database file (and everything under it) is untouched.
    assert (store.project_root(project.project_id) / "db" / "project.sqlite").is_file()
    archived = store.get_project(project_id=project.project_id)
    assert archived["status"] == "archived"


def test_archived_project_is_visible_when_explicitly_included(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("kept-project")
    store.archive_project(project_id=project.project_id)

    listed = {item["project_id"]: item for item in store.list_projects(include_archived=True)}

    assert project.project_id in listed
    assert listed[project.project_id]["status"] == "archived"


def test_restoring_an_archived_project_brings_it_back_to_the_default_list(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("kept-project")
    store.archive_project(project_id=project.project_id)

    store.restore_project(project_id=project.project_id)

    assert project.project_id in {item["project_id"] for item in store.list_projects()}
    assert store.get_project(project_id=project.project_id)["status"] == "draft"


def test_archiving_a_nonexistent_project_fails_safely(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.archive_project(project_id="does-not-exist")


def test_restoring_a_nonexistent_project_fails_safely(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.restore_project(project_id="does-not-exist")


def test_archiving_an_already_archived_project_is_a_safe_no_op(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("kept-project")
    store.archive_project(project_id=project.project_id)

    store.archive_project(project_id=project.project_id)

    assert store.get_project(project_id=project.project_id)["status"] == "archived"


def test_api_archive_and_restore_round_trip(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Put Away Draft"}).json()["project_id"]

    archived = client.post(f"/api/projects/{project_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert project_id not in {item["project_id"] for item in client.get("/api/projects").json()["projects"]}
    assert project_id in {
        item["project_id"] for item in client.get("/api/projects", params={"include_archived": True}).json()["projects"]
    }

    restored = client.post(f"/api/projects/{project_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"
    assert project_id in {item["project_id"] for item in client.get("/api/projects").json()["projects"]}


def test_api_archiving_a_nonexistent_project_is_a_404(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    response = client.post("/api/projects/does-not-exist/archive")
    assert response.status_code == 404


def test_delete_project_permanently_removes_the_project_directory(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("gone-forever")
    project_dir = store.project_root(project.project_id)
    assert project_dir.is_dir()

    store.delete_project_permanently(project_id=project.project_id)

    assert not project_dir.exists()
    assert project.project_id not in {item["project_id"] for item in store.list_projects(include_archived=True)}
    with pytest.raises(KeyError):
        store.get_project(project_id=project.project_id)


def test_delete_project_permanently_on_a_nonexistent_project_fails_safely(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.delete_project_permanently(project_id="does-not-exist")


def test_delete_project_permanently_works_on_an_archived_project_too(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("archived-then-gone")
    store.archive_project(project_id=project.project_id)

    store.delete_project_permanently(project_id=project.project_id)

    assert not store.project_root(project.project_id).exists()


def test_api_permanent_delete_requires_explicit_confirmation(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Needs Confirm"}).json()["project_id"]

    unconfirmed = client.request("DELETE", f"/api/projects/{project_id}")
    assert unconfirmed.status_code == 400
    assert project_id in {item["project_id"] for item in client.get("/api/projects").json()["projects"]}

    confirmed = client.request("DELETE", f"/api/projects/{project_id}", params={"confirm": "true"})
    assert confirmed.status_code == 204
    assert project_id not in {
        item["project_id"] for item in client.get("/api/projects", params={"include_archived": True}).json()["projects"]
    }


def test_api_permanent_delete_of_a_nonexistent_project_is_a_404(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    response = client.request("DELETE", "/api/projects/does-not-exist", params={"confirm": "true"})
    assert response.status_code == 404
