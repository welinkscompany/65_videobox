"""모션 다리를 켜고 준비하는 PowerShell 스크립트 둘 (2026-10-08)."""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "scripts" / "start-motion.ps1"
PREPARE = ROOT / "scripts" / "prepare-motion.ps1"


@pytest.mark.parametrize("script", [START, PREPARE])
def test_motion_scripts_are_saved_so_windows_powershell_reads_korean(script: Path) -> None:
    assert script.read_bytes().startswith(codecs.BOM_UTF8)


def test_the_start_script_runs_the_motion_bridge_with_the_repository_python() -> None:
    text = START.read_text(encoding="utf-8-sig")
    assert "[int]$Port = 8202" in text
    assert "host_motion_service.py" in text
    assert ".venv\\Scripts\\python.exe" in text


def test_the_prepare_script_is_bounded_and_quiet() -> None:
    """처음 준비(약 120MB 설치 + 약 270MB 브라우저)는 몇 분 걸린다. 끝없이 매달리면 안 된다."""
    text = PREPARE.read_text(encoding="utf-8-sig")
    assert ".WaitForExit(" in text
    assert "taskkill.exe" in text
    assert "'ci', '--ignore-scripts'" in text
    assert "'browser', 'ensure'" in text
    for name in ("HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_NO_UPDATE_CHECK"):
        assert name in text
    assert "0.8.140" in text
