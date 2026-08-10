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


def test_enabled_watcher_thread_actually_moves_a_real_file_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """Real-runtime check (not just plumbing): starts the app via its actual
    lifespan, drops a real file in the watched folder, and waits for the
    background thread to move it -- mirrors this session's manual real-Drive
    run (scripts/run_media_inbox_cycle.py) but through the app startup path."""
    _clear_media_inbox_watch_environment(monkeypatch)
    watch_dir = tmp_path / "drive-folder"
    watch_dir.mkdir()
    library_dir = tmp_path / "library"
    monkeypatch.setenv("VIDEOBOX_DATA_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_ENABLED", "1")
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(watch_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_LIBRARY_ROOT", str(library_dir))
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_INTERVAL_SECONDS", "0.05")
    (watch_dir / "clip.mp4").write_bytes(b"real footage bytes")

    app = create_app()
    with TestClient(app):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not (library_dir / "clip.mp4").exists():
            time.sleep(0.1)
        assert (library_dir / "clip.mp4").exists()
        assert (library_dir / "clip.mp4").read_bytes() == b"real footage bytes"
        assert not (watch_dir / "clip.mp4").exists()


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
    from videobox_storage.media_library_store import MediaLibraryStore

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
    library_store: MediaLibraryStore = app.state.media_library_store
    with TestClient(app):
        deadline = time.monotonic() + 20.0
        registered: list = []
        while time.monotonic() < deadline and not registered:
            registered = library_store.list_assets_needing_audio_analysis()
            if not registered:
                time.sleep(0.1)

    assert [str(item["library_asset_id"]) for item in registered] == ["owner:music:봄날의 아침.wav"]
    assert str(registered[0]["media_type"]) == "music"
    # 원본은 셋이 함께 쓰는 보관함으로 갔고, 감시 폴더에는 기다리는 것만 남는다.
    assert not dropped.exists()
    assert (drive_sync / "자산화_완료" / "봄날의 아침.wav").exists()
