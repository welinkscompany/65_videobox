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


def test_remove_project_reference_deletes_only_project_copy_and_is_idempotent(tmp_path):
    client = TestClient(app(tmp_path))
    item = client.post(
        "/api/library/ingest", data={"media_type": "sfx"},
        files=[("files", ("remove.wav", b"remove me", "audio/wav"))],
    ).json()["items"][0]
    project = client.post("/api/projects", json={"name": "remove project ref"}).json()["project_id"]
    materialized = client.post(f"/api/library/assets/{item['library_asset_id']}/materialize", json={"project_id": project}).json()
    reference_id = materialized["reference"]["reference_id"]
    materialized_id = materialized["asset"]["asset_id"]
    assert client.app.state.store.get_asset(project_id=project, asset_id=materialized_id)

    path = f"/api/library/assets/{item['library_asset_id']}/references/{reference_id}"
    assert client.delete(path).status_code == 204
    with pytest.raises(KeyError):
        client.app.state.store.get_asset(project_id=project, asset_id=materialized_id)
    assert client.get(f"/api/library/assets/{item['library_asset_id']}/usage").json()["locations"] == []
    assert client.get(f"/api/library/assets/{item['library_asset_id']}/preview").status_code == 200
    assert client.delete(path).status_code == 204


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

    # **깊은 검사는 지우기 전에만 한다**(2026-09-05, owner 승인). 화면이 자산을
    # 열 때마다 부르던 자리라 실측 1.67초였고 프로젝트가 늘수록 늘어났다.
    # 여기서 지키려는 것 -- 옛 프로젝트의 숨은 참조를 찾아내는 것 -- 은 그대로다.
    usage = client.get(f"/api/library/assets/{item['library_asset_id']}/usage", params={"deep": "true"})
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

    usage = client.get(f"/api/library/assets/{item['library_asset_id']}/usage", params={"deep": "true"})
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


class _FakeEmbeddings:
    def embed(self, request):
        class _Response:
            vectors = ((0.1, 0.2),)

        return _Response()


def _semantic_app(tmp_path, monkeypatch, *, audio_rows=None, footage_rows=None):
    store = MediaLibraryStore(tmp_path / "library")
    application = create_app(projects_root=tmp_path / "projects", media_library_store=store)
    application.state.media_analysis_embedding_provider = _FakeEmbeddings()
    application.state.media_analysis_profile = {"embedding_model_name": "bge-m3"}
    if audio_rows is not None:
        monkeypatch.setattr(type(store), "find_audio_matches", lambda self, **_kw: [dict(row) for row in audio_rows])
    if footage_rows is not None:
        monkeypatch.setattr(type(store), "find_footage_matches", lambda self, **_kw: [dict(row) for row in footage_rows])
    return TestClient(application)


def test_semantic_search_rows_carry_what_the_library_screen_needs(tmp_path, monkeypatch):
    """의미검색 행에 `media_type`·`lifecycle`·`origin`이 없어서 화면 필터가 전부
    걸러냈다 -- 배지는 `뜻으로 찾음`인데 목록에는 단어 매칭만 남는 거짓말이 됐다.
    같은 자산이 단어와 뜻 양쪽으로 잡히면 한 번만 내려보낸다."""
    client = _semantic_app(tmp_path, monkeypatch, audio_rows=[
        {"library_asset_id": "pack:starter-v1:music-x", "asset_id": "music-x", "media_type": "music", "score": 0.9},
    ])
    ingested = client.post(
        "/api/library/ingest", data={"media_type": "music"},
        files=[("files", ("calm.mp3", b"bytes", "audio/mpeg"))],
    ).json()["items"][0]["library_asset_id"]

    body = client.get("/api/library/search", params={"q": "calm", "media_type": "music"}).json()

    assert body["semantic"] is True
    row = next(value for value in body["matches"] if value["library_asset_id"] == "pack:starter-v1:music-x")
    assert row["media_type"] == "music"
    assert row["lifecycle"] == "ready"
    assert row["origin"] == "builtin"
    assert row["semantic_match"] is True
    assert sum(1 for value in body["matches"] if value["library_asset_id"] == ingested) == 1


def test_semantic_flag_is_false_when_the_lookup_contributes_nothing(tmp_path, monkeypatch):
    # 조회는 돌았지만 0건이면 보이는 목록은 전부 단어 매칭이다. 그걸
    # `뜻으로 찾음`이라고 내려보내면 화면이 거짓말을 한다.
    client = _semantic_app(tmp_path, monkeypatch, audio_rows=[])

    body = client.get("/api/library/search", params={"q": "calm", "media_type": "music"}).json()

    assert body["semantic"] is False


# ---------------------------------------------------------------------------
# `source_for_user`의 실패 분기 두 개. 이 라우터가 파일 바이트를 내주기 전에
# "설정된 root 안에 있는가 + 내용 해시가 맞는가"를 확인하는데, 그 **실패** 경로에는
# 지금까지 테스트가 하나도 없었다(성공 200만 검증돼 있었다). 이 검사를 공용
# 헬퍼로 추출하기 전에 현재 상태코드 계약부터 고정한다.
# ---------------------------------------------------------------------------


def _register_user_asset(library_root: Path, *, asset_id: str, relative_path: str, content_sha256: str):
    from videobox_domain_models.library_assets import LibraryAssetOrigin, LibraryMediaType

    store = MediaLibraryStore(library_root).user_asset_store
    return store.register_asset(
        library_asset_id=asset_id,
        media_type=LibraryMediaType.MUSIC,
        origin=LibraryAssetOrigin.USER,
        content_sha256=content_sha256,
        managed_relative_path=relative_path,
        byte_count=4,
        mime_type="audio/mpeg",
        technical_metadata={},
        machine_metadata={},
        user_metadata={"filename": "pinned.mp3"},
        provenance={},
    )


def test_an_escaping_managed_path_is_refused_before_it_can_ever_be_stored(tmp_path):
    """root를 벗어나는 경로는 **저장 단계에서** 막힌다 -- 1차 방어선.

    라우터에도 경로 이탈을 422로 거절하는 분기가 있지만(`source_for_user`),
    이 검증 때문에 정상 등록 경로로는 그 분기에 도달할 수 없다. 라우터 쪽은
    심볼릭 링크나 이 검증이 생기기 전의 옛 행을 위한 2차 방어선으로 남는다.
    경로 검증을 공용 헬퍼로 옮길 때 이 1차 방어선이 먼저 깨지지 않는지 지킨다.
    """
    library_root = tmp_path / "library"

    for escaping in ("../escaped.mp3", "assets/../../escaped.mp3", "/absolute.mp3"):
        with pytest.raises(ValueError, match="safe relative path"):
            _register_user_asset(
                library_root, asset_id=f"user:{escaping}", relative_path=escaping, content_sha256="c" * 64
            )


def test_a_managed_path_inside_the_root_with_no_file_is_unavailable(tmp_path):
    """root 안이지만 파일이 없거나 해시가 다르면 404다. 위 422와 갈라진다."""
    library_root = tmp_path / "library"
    _register_user_asset(library_root, asset_id="user:absent", relative_path="assets/music/absent.mp3", content_sha256="d" * 64)
    client = TestClient(app(tmp_path))

    response = client.get("/api/library/assets/user:absent/preview")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset_unavailable"
