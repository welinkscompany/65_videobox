"""Task 18 remainder: a repeating watcher loop wired into the app itself.

Without this, importing footage required someone to remember to run
scripts/run_media_inbox_cycle.py by hand every time. The background thread
must never start unless explicitly enabled -- the watched path defaults to
the owner's real Drive-synced folder, and the entire test suite creates
apps via create_app() with no arguments.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _clear_media_inbox_watch_environment(monkeypatch) -> None:
    for name in (
        "VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED",
        "VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS",
        "VIDEOBOX_MEDIA_INBOX_WATCH_PATH",
        "VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT",
        "VIDEOBOX_OWNER_AUDIO_LIBRARY_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_watcher_thread_does_not_start_by_default(tmp_path: Path, monkeypatch) -> None:
    _clear_media_inbox_watch_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))

    app = create_app()

    assert app.state.media_inbox_watch_enabled is False


def test_watcher_config_resolves_from_the_environment_when_enabled(tmp_path: Path, monkeypatch) -> None:
    _clear_media_inbox_watch_environment(monkeypatch)
    watch_dir = tmp_path / "drive-folder"
    library_dir = tmp_path / "library"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(watch_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", str(library_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "0.05")

    app = create_app()

    assert app.state.media_inbox_watch_enabled is True
    assert app.state.media_inbox_watch_config.watch_path == watch_dir
    assert app.state.media_inbox_watch_config.library_root == library_dir
    assert app.state.media_inbox_watch_interval_seconds == 0.05


def test_watcher_stays_off_when_the_watch_path_is_explicitly_cleared(tmp_path: Path, monkeypatch) -> None:
    _clear_media_inbox_watch_environment(monkeypatch)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", "")

    app = create_app()

    assert app.state.media_inbox_watch_config is None


def test_enabled_watcher_thread_copy_only_registers_a_real_file_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """Real-runtime check (not just plumbing): starts the app via its actual
    lifespan, drops a real file in the watched folder, and waits for the
    background thread to copy it through the global ingest service -- mirrors
    the real Drive-mirror startup path without deleting the cloud source."""
    _clear_media_inbox_watch_environment(monkeypatch)
    watch_dir = tmp_path / "drive-folder"
    watch_dir.mkdir()
    library_dir = tmp_path / "library"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(watch_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", str(library_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "0.05")
    source = watch_dir / "clip.mp4"
    source.write_bytes(b"real footage bytes")

    app = create_app()
    with TestClient(app):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not list(library_dir.rglob("*.mp4")):
            time.sleep(0.1)
        managed = list(library_dir.rglob("*.mp4"))
        assert len(managed) == 1
        assert managed[0].read_bytes() == b"real footage bytes"
        assert source.read_bytes() == b"real footage bytes"
        assert app.state.media_inbox_watch_config.copy_only is True
        assert len(app.state.media_library_store.user_asset_store.list_assets(media_type="broll")) == 1


def test_watcher_asset_is_previewable_through_global_library_api(tmp_path: Path, monkeypatch) -> None:
    _clear_media_inbox_watch_environment(monkeypatch)
    watch_dir = tmp_path / "drive-folder"
    watch_dir.mkdir()
    library_dir = tmp_path / "library"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(watch_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", str(library_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "0.05")
    source = watch_dir / "clip.mp4"
    source.write_bytes(b"watcher bytes")

    app = create_app()
    with TestClient(app) as client:
        deadline = time.monotonic() + 10.0
        assets = []
        while time.monotonic() < deadline and not assets:
            assets = app.state.media_library_store.user_asset_store.list_assets(media_type="broll")
            if not assets:
                time.sleep(0.1)
        assert assets
        preview = client.get(f"/api/library/assets/{assets[0].library_asset_id}/preview")
        assert preview.status_code == 200
        assert preview.content == source.read_bytes()


def test_music_and_effects_get_their_own_watched_folders(tmp_path: Path, monkeypatch) -> None:
    """owner 결정 (2026-08-10): 종류를 폴더로 나눈다.

    셋은 같은 부모 아래 나란히 있고 보관함 하나를 함께 쓴다. 그래서 owner가
    새로 만들 것은 `새 음악`과 `새 효과음` 둘뿐이다.
    """
    from videobox_core_engine.media_inbox import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

    _clear_media_inbox_watch_environment(monkeypatch)
    drive_sync = tmp_path / "drive-sync"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(drive_sync / "새 영상"))

    app = create_app()

    by_folder = {
        config.watch_path.name: config
        for config in app.state.media_inbox_watch_configs
    }
    assert sorted(by_folder) == ["새 영상", "새 음악", "새 효과음"]
    assert by_folder["새 영상"].accepted_extensions == VIDEO_EXTENSIONS
    assert by_folder["새 음악"].accepted_extensions == AUDIO_EXTENSIONS
    assert by_folder["새 효과음"].accepted_extensions == AUDIO_EXTENSIONS
    # 보관함은 하나다. 셋이 같은 부모를 쓰므로 저절로 그렇게 된다.
    assert {config.archive_root for config in app.state.media_inbox_watch_configs} == {
        drive_sync / "자산화_완료"
    }
    # 음악과 효과음은 촬영본 라이브러리와 섞이지 않는다. 섞이면 촬영본 색인이
    # mp3를 영상으로 알고 분석하려 든다.
    assert by_folder["새 음악"].library_root != app.state.media_inbox_library_root
    assert by_folder["새 음악"].library_root != by_folder["새 효과음"].library_root


def test_a_dropped_track_ends_up_searchable_without_anyone_asking(tmp_path: Path, monkeypatch) -> None:
    """실제 런타임 확인. 감시가 파일을 옮기고, 정비 한 바퀴가 그것을
    라이브러리 자산으로 등록해 색인 대기 목록에 올린다.

    파일이 옮겨진 것만으로는 검색에 절대 안 나온다 -- 색인기는 폴더가 아니라
    라이브러리 DB를 읽기 때문이다. 그래서 여기서 보는 것은 "옮겨졌는가"가
    아니라 "등록되었는가"다.
    """
    import wave

    from videobox_api import main as api_main
    _clear_media_inbox_watch_environment(monkeypatch)
    drive_sync = tmp_path / "drive-sync"
    music_watch = drive_sync / "새 음악"
    music_watch.mkdir(parents=True)
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(drive_sync / "새 영상"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "0.05")
    monkeypatch.setattr(api_main, "LIBRARY_AUDIO_INDEX_INTERVAL_SECONDS", 0.05)

    dropped = music_watch / "봄날의 아침.wav"
    with wave.open(str(dropped), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x01" * 8000)

    app = api_main.create_app(media_analysis_poll_interval_seconds=0.01)
    user_asset_store = app.state.media_library_store.user_asset_store
    with TestClient(app):
        deadline = time.monotonic() + 20.0
        registered: list = []
        while time.monotonic() < deadline and not registered:
            registered = user_asset_store.list_assets(media_type="music")
            if not registered:
                time.sleep(0.1)

    assert len(registered) == 1
    assert registered[0].media_type.value == "music"
    managed = app.state.owner_audio_library_root / "music" / registered[0].managed_relative_path
    assert managed.read_bytes() == dropped.read_bytes()
    # Copy-only Drive mirror policy keeps the cloud-synced source intact.
    assert dropped.exists()
