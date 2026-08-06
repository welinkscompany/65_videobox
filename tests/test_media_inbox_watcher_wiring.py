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
