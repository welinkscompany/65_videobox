from pathlib import Path
import shutil
import subprocess

import pytest

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.routers.library_assets import _remove_managed_file
from videobox_storage.media_library_store import MediaLibraryStore


FFMPEG = shutil.which("ffmpeg")


def _ffmpeg_fixture(path: Path, *inputs: str) -> None:
    assert FFMPEG is not None
    result = subprocess.run([FFMPEG, "-y", *inputs, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


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
    waveform = client.get(f"/api/library/assets/{asset_id}/waveform")
    thumbnail = client.get(f"/api/library/assets/{asset_id}/thumbnail")
    assert waveform.status_code == 200 and waveform.headers["content-type"].startswith("image/svg+xml")
    assert thumbnail.status_code == 200 and thumbnail.headers["content-type"].startswith("image/svg+xml")
    assert client.post(f"/api/library/assets/{asset_id}/trash").status_code == 200
    assert client.post(f"/api/library/assets/{asset_id}/restore").status_code == 200
    assert client.delete(f"/api/library/assets/{asset_id}/permanent").status_code == 409
    assert client.post(f"/api/library/assets/{asset_id}/trash").status_code == 200
    assert client.delete(f"/api/library/assets/{asset_id}/permanent").status_code == 204
    assert not list((tmp_path / "library" / "assets").rglob("*song.mp3"))
    assert not (tmp_path / "library" / "derivatives").exists()


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


def test_materialize_same_project_asset_is_sha_idempotent_and_keeps_one_reference(tmp_path):
    client = TestClient(app(tmp_path))
    item = client.post(
        "/api/library/ingest", data={"media_type": "sfx"},
        files=[("files", ("click.wav", b"same bytes", "audio/wav"))],
    ).json()["items"][0]
    project = client.post("/api/projects", json={"name": "same materialization"}).json()["project_id"]
    path = f"/api/library/assets/{item['library_asset_id']}/materialize"
    first = client.post(path, json={"project_id": project})
    second = client.post(path, json={"project_id": project})
    assert first.status_code == second.status_code == 201
    assert first.json()["asset"]["asset_id"] == second.json()["asset"]["asset_id"]
    assert first.json()["reference"]["reference_id"] == second.json()["reference"]["reference_id"]
    assert len(client.get(f"/api/library/assets/{item['library_asset_id']}/usage").json()["locations"]) == 1


def test_permanent_cleanup_can_remove_matching_asset_from_alternate_managed_root(tmp_path):
    relative = "assets/broll/clip.mp4"
    primary = tmp_path / "primary"
    alternate = tmp_path / "alternate"
    (primary / relative).parent.mkdir(parents=True)
    (alternate / relative).parent.mkdir(parents=True)
    (primary / relative).write_bytes(b"owner clip")
    (alternate / relative).write_bytes(b"unrelated clip")
    expected = __import__("hashlib").sha256(b"owner clip").hexdigest()

    _remove_managed_file(alternate, relative, expected_sha256=expected)
    _remove_managed_file(primary, relative, expected_sha256=expected)

    assert (alternate / relative).is_file()
    assert not (primary / relative).exists()


def test_usage_scans_direct_editing_session_and_timeline_library_references(tmp_path):
    client = TestClient(app(tmp_path))
    item = client.post(
        "/api/library/ingest", data={"media_type": "sfx"},
        files=[("files", ("click.wav", b"session ref", "audio/wav"))],
    ).json()["items"][0]
    project_id = client.post("/api/projects", json={"name": "usage scan"}).json()["project_id"]
    store = client.app.state.store
    store.list_editing_sessions = lambda *, project_id: [
        {"session_id": "session-direct", "timeline_id": "timeline-direct", "library_asset_id": item["library_asset_id"]}
    ]
    store.get_timeline_run = lambda *, project_id, timeline_id: {
        "timeline_id": timeline_id,
        "tracks": [{"clips": [{"library_asset_id": item["library_asset_id"]}]}],
    }

    usage = client.get(f"/api/library/assets/{item['library_asset_id']}/usage")
    assert usage.status_code == 200
    kinds = {(entry["location"]["kind"], entry["location"].get("id")) for entry in usage.json()["locations"]}
    assert ("editing_session", "session-direct") in kinds
    assert ("timeline", "timeline-direct") in kinds


def test_usage_scans_nested_session_json_when_hydration_fails(tmp_path):
    client = TestClient(app(tmp_path))
    item = client.post(
        "/api/library/ingest", data={"media_type": "sfx"},
        files=[("files", ("nested.wav", b"nested ref", "audio/wav"))],
    ).json()["items"][0]
    client.post("/api/projects", json={"name": "nested usage"})
    store = client.app.state.store
    store.list_editing_sessions = lambda *, project_id: [{
        "session_id": "session-json", "timeline_id": "", "session_json": __import__("json").dumps({"segments": [{"sfx_override": {"library_asset_id": item["library_asset_id"]}}]}),
    }]
    store.get_editing_session = lambda **_: (_ for _ in ()).throw(KeyError("session unavailable"))

    usage = client.get(f"/api/library/assets/{item['library_asset_id']}/usage")
    assert usage.status_code == 200
    assert any(entry["location"]["kind"] == "editing_session" for entry in usage.json()["locations"])


def test_retry_with_same_key_and_different_bytes_is_rejected(tmp_path):
    client = TestClient(app(tmp_path))
    first = client.post(
        "/api/library/ingest", data={"media_type": "sfx", "idempotency_key": "same-key"},
        files=[("files", ("a.wav", b"first", "audio/wav"))],
    )
    assert first.status_code == 201, first.text
    conflict = client.post(
        "/api/library/ingest", data={"media_type": "sfx", "idempotency_key": "same-key"},
        files=[("files", ("a.wav", b"second", "audio/wav"))],
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"] == "idempotency_key_conflict"


def test_missing_key_is_not_a_shared_batch_fallback(tmp_path):
    client = TestClient(app(tmp_path))
    first = client.post("/api/library/ingest", data={"media_type": "sfx"}, files=[("files", ("a.wav", b"first", "audio/wav"))])
    second = client.post("/api/library/ingest", data={"media_type": "sfx"}, files=[("files", ("a.wav", b"second", "audio/wav"))])
    assert first.status_code == second.status_code == 201
    assert first.json()["items"][0]["idempotency_key"] != second.json()["items"][0]["idempotency_key"]
    assert first.json()["items"][0]["library_asset_id"] != second.json()["items"][0]["library_asset_id"]


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed on this machine")
def test_derivatives_are_source_derived_and_audio_waveform_is_rendered(tmp_path):
    client = TestClient(app(tmp_path))
    red = tmp_path / "red.mp4"
    blue = tmp_path / "blue.mp4"
    _ffmpeg_fixture(red, "-f", "lavfi", "-i", "color=c=red:s=96x64:d=1", "-pix_fmt", "yuv420p")
    _ffmpeg_fixture(blue, "-f", "lavfi", "-i", "color=c=blue:s=96x64:d=1", "-pix_fmt", "yuv420p")
    red_item = client.post("/api/library/ingest", data={"media_type": "broll"}, files=[("files", ("red.mp4", red.read_bytes(), "video/mp4"))]).json()["items"][0]
    blue_item = client.post("/api/library/ingest", data={"media_type": "broll"}, files=[("files", ("blue.mp4", blue.read_bytes(), "video/mp4"))]).json()["items"][0]
    red_thumbnail = client.get(f"/api/library/assets/{red_item['library_asset_id']}/thumbnail")
    blue_thumbnail = client.get(f"/api/library/assets/{blue_item['library_asset_id']}/thumbnail")
    assert red_thumbnail.status_code == blue_thumbnail.status_code == 200
    assert red_thumbnail.headers["content-type"].startswith("image/")
    assert red_thumbnail.content != blue_thumbnail.content
    assert b"<text" not in red_thumbnail.content

    tone_a = tmp_path / "tone-a.wav"
    tone_b = tmp_path / "tone-b.wav"
    _ffmpeg_fixture(tone_a, "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ar", "8000")
    _ffmpeg_fixture(tone_b, "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-ar", "8000")
    a_item = client.post("/api/library/ingest", data={"media_type": "music"}, files=[("files", ("a.wav", tone_a.read_bytes(), "audio/wav"))]).json()["items"][0]
    b_item = client.post("/api/library/ingest", data={"media_type": "music"}, files=[("files", ("b.wav", tone_b.read_bytes(), "audio/wav"))]).json()["items"][0]
    waveform_a = client.get(f"/api/library/assets/{a_item['library_asset_id']}/waveform")
    waveform_b = client.get(f"/api/library/assets/{b_item['library_asset_id']}/waveform")
    assert waveform_a.status_code == waveform_b.status_code == 200
    assert waveform_a.headers["content-type"].startswith("image/")
    assert waveform_a.content != waveform_b.content
    assert b"<text" not in waveform_a.content
    assert client.get(f"/api/library/assets/{a_item['library_asset_id']}/preview").content == tone_a.read_bytes()


def test_derivative_tool_failure_is_visible_as_needs_attention(tmp_path, monkeypatch):
    client = TestClient(app(tmp_path))
    item = client.post("/api/library/ingest", data={"media_type": "music"}, files=[("files", ("a.wav", b"not audio", "audio/wav"))]).json()["items"][0]
    import videobox_api.routers.library_assets as module
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("ffmpeg")))
    response = client.get(f"/api/library/assets/{item['library_asset_id']}/waveform")
    assert response.status_code == 503
    assert response.json()["detail"]["state"] == "needs_attention"
    listed = client.get("/api/library/assets").json()["assets"]
    assert next(value for value in listed if value["library_asset_id"] == item["library_asset_id"])["lifecycle"] == "needs_attention"


def test_derivative_timeout_is_visible_as_needs_attention(tmp_path, monkeypatch):
    client = TestClient(app(tmp_path))
    item = client.post("/api/library/ingest", data={"media_type": "music"}, files=[("files", ("a.wav", b"timeout", "audio/wav"))]).json()["items"][0]
    import videobox_api.routers.library_assets as module
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(module.subprocess.TimeoutExpired("ffmpeg", 30)))

    response = client.get(f"/api/library/assets/{item['library_asset_id']}/waveform")

    assert response.status_code == 503
    assert response.json()["detail"]["state"] == "needs_attention"


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
