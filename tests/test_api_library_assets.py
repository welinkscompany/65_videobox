from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore


def app(tmp_path):
    return create_app(projects_root=tmp_path / "projects", media_library_store=MediaLibraryStore(tmp_path / "library"))


def test_library_ingest_list_preview_and_lifecycle(tmp_path):
    client = TestClient(app(tmp_path))
    source = b"fake audio bytes"
    response = client.post(
        "/api/library/ingest",
        data={"media_type": "music", "idempotency_key": "batch-1"},
        files=[("files", ("song.mp3", source, "audio/mpeg"))],
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["items"][0]["state"] == "ready"
    asset_id = payload["items"][0]["library_asset_id"]
    listed = client.get("/api/library/assets").json()["assets"]
    item = next(value for value in listed if value["library_asset_id"] == asset_id)
    assert "managed_relative_path" in item and not Path(item["managed_relative_path"]).is_absolute()
    assert client.get(f"/api/library/assets/{asset_id}/preview").status_code == 200
    assert client.get(f"/api/library/assets/{asset_id}/waveform").status_code == 200
    assert client.get(f"/api/library/assets/{asset_id}/thumbnail").status_code == 200
    assert client.post(f"/api/library/assets/{asset_id}/trash").status_code == 200
    assert client.post(f"/api/library/assets/{asset_id}/restore").status_code == 200
    assert client.delete(f"/api/library/assets/{asset_id}/permanent").status_code == 409
    assert client.post(f"/api/library/assets/{asset_id}/trash").status_code == 200
    assert client.delete(f"/api/library/assets/{asset_id}/permanent").status_code == 204
    assert not list((tmp_path / "library" / "assets").rglob("*song.mp3"))


def test_retry_reuses_ingest_item_and_usage_blocks_delete(tmp_path):
    client = TestClient(app(tmp_path))
    source = b"same"
    first = client.post(
        "/api/library/ingest", data={"media_type": "sfx", "idempotency_key": "retry"},
        files=[("files", ("a.wav", source, "audio/wav"))],
    ).json()["items"][0]
    second = client.post(
        "/api/library/ingest", data={"media_type": "sfx", "idempotency_key": "retry"},
        files=[("files", ("a.wav", source, "audio/wav"))],
    ).json()["items"][0]
    assert first["library_asset_id"] == second["library_asset_id"]
    assert first["ingest_item_id"] == second["ingest_item_id"]
    project = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
    materialized = client.post(
        f"/api/library/assets/{first['library_asset_id']}/materialize", json={"project_id": project}
    )
    assert materialized.status_code == 201, materialized.text
    blocked = client.delete(f"/api/library/assets/{first['library_asset_id']}/permanent")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["locations"]


def test_builtin_rejects_trash(tmp_path):
    client = TestClient(app(tmp_path))
    assert client.post("/api/library/assets/pack:missing/trash").status_code == 404


def test_search_user_asset(tmp_path):
    client = TestClient(app(tmp_path))
    response = client.post(
        "/api/library/ingest", data={"media_type": "music"},
        files=[("files", ("calm.mp3", b"bytes", "audio/mpeg"))],
    )
    asset_id = response.json()["items"][0]["library_asset_id"]
    matches = client.get("/api/library/search", params={"q": "calm", "media_type": "music"}).json()["matches"]
    assert matches[0]["library_asset_id"] == asset_id
