"""Task 18's remaining API surface: browse the media-inbox library and copy
one file into a project (packages/core-engine/media_inbox.py's
import_media_inbox_asset_to_project, wired to HTTP)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _make_app_and_project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", str(tmp_path / "library"))
    monkeypatch.delenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", raising=False)
    app = create_app()
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "media inbox import"}).json()["project_id"]
    return client, project_id


def test_lists_empty_when_the_library_root_does_not_exist_yet(tmp_path: Path, monkeypatch) -> None:
    client, _project_id = _make_app_and_project(tmp_path, monkeypatch)

    response = client.get("/api/media-inbox/assets")

    assert response.status_code == 200
    assert response.json() == {"assets": []}


def test_lists_files_sitting_in_the_library_root(tmp_path: Path, monkeypatch) -> None:
    client, _project_id = _make_app_and_project(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "clip.mp4").write_bytes(b"12345")

    response = client.get("/api/media-inbox/assets")

    assert response.status_code == 200
    assert response.json() == {"assets": [{"filename": "clip.mp4", "size_bytes": 5}]}


def test_imports_a_library_file_into_a_project_as_a_broll_asset(tmp_path: Path, monkeypatch) -> None:
    """Task 22: collected footage is B-roll.  Registering it as `raw_video`
    put it somewhere the b-roll listing never looked, so an import looked like
    it had done nothing."""
    client, project_id = _make_app_and_project(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "clip.mp4").write_bytes(b"library footage")

    response = client.post(f"/api/projects/{project_id}/media-inbox/import", json={"filename": "clip.mp4"})

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == project_id
    assert body["asset_type"] == "broll_video"
    # The library copy stays in place for reuse across projects.
    assert (library_root / "clip.mp4").exists()

    # The point of the correction: the imported clip is now reachable from the
    # listing the asset screen actually reads.
    listed = client.get(f"/api/projects/{project_id}/assets/broll-video")
    assert listed.status_code == 200
    assets = listed.json()["assets"]
    assert [asset["asset_id"] for asset in assets] == [body["asset_id"]]
    assert assets[0]["metadata"]["title"] == "clip"


def test_returns_404_for_a_missing_library_file(tmp_path: Path, monkeypatch) -> None:
    client, project_id = _make_app_and_project(tmp_path, monkeypatch)

    response = client.post(f"/api/projects/{project_id}/media-inbox/import", json={"filename": "missing.mp4"})

    assert response.status_code == 404
    assert response.json()["detail"] == "media_inbox_asset_missing"


def test_retries_are_idempotent_for_the_same_library_bytes(tmp_path: Path, monkeypatch) -> None:
    client, project_id = _make_app_and_project(tmp_path, monkeypatch)
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "clip.mp4").write_bytes(b"library footage")

    first = client.post(f"/api/projects/{project_id}/media-inbox/import", json={"filename": "clip.mp4"})
    second = client.post(f"/api/projects/{project_id}/media-inbox/import", json={"filename": "clip.mp4"})

    assert first.status_code == second.status_code == 201
    assert first.json()["asset_id"] == second.json()["asset_id"]
    listed = client.get(f"/api/projects/{project_id}/assets/broll-video").json()["assets"]
    assert len(listed) == 1


def test_rejects_a_path_traversal_filename(tmp_path: Path, monkeypatch) -> None:
    client, project_id = _make_app_and_project(tmp_path, monkeypatch)

    response = client.post(f"/api/projects/{project_id}/media-inbox/import", json={"filename": "../secret.txt"})

    assert response.status_code == 422
    assert response.json()["detail"] == "media_inbox_filename_invalid"
