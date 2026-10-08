"""e2e 실행기가 소유자의 실제 데이터·비밀에 닿지 않는지 (2026-10-08 계획 H Task 1 보정)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.e2e_real_editor_api import _assert_not_real_root, _clean_old_runs, _trust_web_port_origin, build_child_env


def test_child_env_drops_every_videobox_name_and_secret_but_keeps_the_basics() -> None:
    parent = {
        "PATH": "p", "SystemRoot": "C:\Windows", "TEMP": "t",
        "VIDEOBOX_MEDIA_INBOX_WATCH_PATH": "D:\inbox",
        "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN": "t",
        "VIDEOBOX_BRIDGE_TOKEN": "t",
        "VIDEOBOX_DATABASE_URL": "postgres://real",
        "VIDEOBOX_HERMES_HOME": "x",
        "SOME_API_KEY": "k",
    }
    child = build_child_env(parent, data_root=Path("X:/tmp/e2e"))
    assert child["PATH"] == "p" and child["SystemRoot"] == "C:\Windows"
    assert child["VIDEOBOX_DATA_ROOT"] == str(Path("X:/tmp/e2e"))
    assert set(child) == {"PATH", "SystemRoot", "TEMP", "VIDEOBOX_DATA_ROOT"}


def test_guard_refuses_real_root_child_ancestor_and_drive_root(tmp_path: Path) -> None:
    real = tmp_path / "real" / "projects"
    real.mkdir(parents=True)
    allowed = [tmp_path / "ok"]
    for bad in (real, real / "sub", real.parent, Path(real.anchor)):
        with pytest.raises(SystemExit):
            _assert_not_real_root(bad, [real], [Path(real.anchor)])
    with pytest.raises(SystemExit):  # 허용 위치 밖
        _assert_not_real_root(tmp_path / "elsewhere", [real], allowed)
    _assert_not_real_root(tmp_path / "ok" / "run1", [real], allowed)


def test_cleanup_only_touches_old_folders_inside_real_flow_data(tmp_path: Path) -> None:
    root = tmp_path / "real-flow-data"
    old, fresh = root / "old", root / "fresh"
    old.mkdir(parents=True)
    fresh.mkdir()
    os.utime(old, (1, 1))
    other = tmp_path / "not-it" / "old"
    other.mkdir(parents=True)
    os.utime(other, (1, 1))
    _clean_old_runs(root)
    _clean_old_runs(tmp_path / "not-it")
    assert not old.exists() and fresh.exists() and other.exists()


def test_web_port_origin_only_adds_that_loopback_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from videobox_api import csrf_guard

    original = csrf_guard.TRUSTED_ORIGINS
    monkeypatch.setattr(csrf_guard, "TRUSTED_ORIGINS", original)
    for bad in ["", "abc", "0", "65536", "-1", "80; x", "１２３", " "]:
        assert _trust_web_port_origin(bad) is None
        assert csrf_guard.TRUSTED_ORIGINS == original
    assert _trust_web_port_origin("56872") == "http://127.0.0.1:56872"
    assert csrf_guard.TRUSTED_ORIGINS == original | {"http://127.0.0.1:56872"}
