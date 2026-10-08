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


# --- prepare-motion.ps1을 가짜 node/npm으로 실제로 돌린다 (2026-10-08, Task 5) -------------------
# 위 시험들은 글자만 본다. 아래는 Windows PowerShell 5.1에서 진짜로 띄워 본다:
# 종료 코드 읽기, 잠금 경쟁, 시간 상한과 자식 끊기.

import os
import subprocess
import sys
import time

_POWERSHELL = "powershell"
_windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 전용 스크립트")


def _prepare_fixture(tmp_path: Path, *, engine_installed: bool, node_body: str, npm_body: str = "exit /b 0") -> dict[str, Path]:
    bridge = tmp_path / "bridge root"  # 공백이 든 경로도 같이 밟는다
    (bridge / "node_modules" / "hyperframes").mkdir(parents=True)
    if engine_installed:
        (bridge / "node_modules" / "hyperframes" / "package.json").write_text('{"version":"0.8.140"}', encoding="utf-8")
    calls = tmp_path / "calls.log"
    node = tmp_path / "fake-node.cmd"
    npm = tmp_path / "fake-npm.cmd"
    node.write_text(f'@echo off\r\necho node %*>>"{calls}"\r\n{node_body}\r\n', encoding="ascii")
    npm.write_text(f'@echo off\r\necho npm %*>>"{calls}"\r\n{npm_body}\r\n', encoding="ascii")
    return {"bridge": bridge, "calls": calls, "node": node, "npm": npm, "lock": tmp_path / "prepare.lock"}


def _prepare_command(fixture: dict[str, Path], *extra: str) -> list[str]:
    return [
        _POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PREPARE),
        "-BridgeRoot", str(fixture["bridge"]), "-LockPath", str(fixture["lock"]),
        "-NodePath", str(fixture["node"]), "-NpmPath", str(fixture["npm"]), *extra,
    ]


def _run_prepare(fixture: dict[str, Path], *extra: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _prepare_command(fixture, *extra), capture_output=True, text=True, encoding="oem", errors="replace", timeout=timeout,
    )


def _call_lines(fixture: dict[str, Path]) -> list[str]:
    if not fixture["calls"].exists():
        return []
    return [line for line in fixture["calls"].read_text(encoding="oem", errors="replace").splitlines() if line.strip()]


def _processes_with(marker: str) -> list[str]:
    result = subprocess.run(
        [_POWERSHELL, "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*" + marker + "*' -and $_.Name -ne 'powershell.exe' } "
         "| ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True, timeout=60,
    )
    return [line for line in result.stdout.split() if line.strip()]


@_windows_only
def test_prepare_reads_a_fast_childs_exit_code_instead_of_null(tmp_path: Path) -> None:
    """5.1에서는 `Handle`을 안 건드리면 빨리 끝난 자식의 ExitCode가 비어 읽힌다 -- 실패가 성공이 된다."""
    fixture = _prepare_fixture(tmp_path, engine_installed=True, node_body="exit /b 3")
    result = _run_prepare(fixture)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "종료 코드 3" in result.stdout
    assert not fixture["lock"].exists(), "실패해도 잠금은 풀려야 한다"


@_windows_only
def test_prepare_succeeds_and_installs_only_when_the_engine_is_missing(tmp_path: Path) -> None:
    ready = _prepare_fixture(tmp_path / "ready", engine_installed=True, node_body="exit /b 0")
    result = _run_prepare(ready)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [line.split()[0] for line in _call_lines(ready)] == ["node"]
    assert "browser ensure" in _call_lines(ready)[0]
    assert not ready["lock"].exists()

    fresh = _prepare_fixture(tmp_path / "fresh", engine_installed=False, node_body="exit /b 0")
    result = _run_prepare(fresh)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = _call_lines(fresh)
    assert [line.split()[0] for line in lines] == ["npm", "node"]
    assert "ci --ignore-scripts" in lines[0]


@_windows_only
def test_prepare_timeout_is_bounded_and_kills_the_whole_process_tree(tmp_path: Path) -> None:
    marker = f"-n {7000 + os.getpid() % 900}"  # 이 시험만의 ping 표식
    fixture = _prepare_fixture(tmp_path, engine_installed=True, node_body=f"ping {marker} 127.0.0.1 >nul")
    started = time.monotonic()
    result = _run_prepare(fixture, "-BrowserTimeoutSeconds", "3")
    elapsed = time.monotonic() - started
    try:
        assert result.returncode == 1, result.stdout + result.stderr
        assert "3 초 안에 끝나지 않아" in result.stdout
        assert elapsed < 40, f"상한 3초인데 {elapsed:.0f}초 걸렸다"
        time.sleep(1)
        assert _processes_with(marker) == [], "시간 상한 뒤에도 자식(ping)이 살아 있다"
        assert not fixture["lock"].exists()
    finally:
        for pid in _processes_with(marker):
            subprocess.run(["taskkill.exe", "/PID", pid, "/F"], capture_output=True)


@_windows_only
def test_prepare_double_start_runs_the_work_once(tmp_path: Path) -> None:
    """두 번째 실행이 잠금 검사와 생성 사이에 끼어들 수 없다(CreateNew) -- 일은 한 번만 돈다."""
    fixture = _prepare_fixture(tmp_path, engine_installed=True, node_body="ping -n 9 127.0.0.1 >nul")
    first = subprocess.Popen(
        _prepare_command(fixture), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="oem", errors="replace",
    )
    try:
        deadline = time.monotonic() + 30
        while not _call_lines(fixture) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert _call_lines(fixture), "첫 실행이 시작하지 않았다"
        second_started = time.monotonic()
        second = _run_prepare(fixture)
        second_elapsed = time.monotonic() - second_started
        assert second.returncode == 0, second.stdout + second.stderr
        assert "이미 준비하고 있습니다" in second.stdout
        assert second_elapsed < 8, "두 번째 실행은 기다리지 않고 바로 끝나야 한다"
        assert fixture["lock"].exists(), "두 번째 실행이 첫 실행의 잠금을 지우면 안 된다"
        first_out, _ = first.communicate(timeout=60)
        assert first.returncode == 0, first_out
        assert len(_call_lines(fixture)) == 1
        assert not fixture["lock"].exists()
    finally:
        if first.poll() is None:
            subprocess.run(["taskkill.exe", "/PID", str(first.pid), "/T", "/F"], capture_output=True)


@_windows_only
def test_prepare_races_simultaneous_starts_into_one_run(tmp_path: Path) -> None:
    fixture = _prepare_fixture(tmp_path, engine_installed=True, node_body="ping -n 9 127.0.0.1 >nul")
    processes = [
        subprocess.Popen(
            _prepare_command(fixture), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="oem", errors="replace",
        )
        for _ in range(3)
    ]
    outputs = [process.communicate(timeout=90)[0] for process in processes]
    assert [process.returncode for process in processes] == [0, 0, 0], outputs
    assert len(_call_lines(fixture)) == 1, _call_lines(fixture)
    assert sum("이미 준비하고 있습니다" in out for out in outputs) == 2


@_windows_only
def test_prepare_replaces_a_dead_lock_but_respects_a_fresh_one(tmp_path: Path) -> None:
    fresh = _prepare_fixture(tmp_path / "fresh", engine_installed=True, node_body="exit /b 0")
    fresh["lock"].write_text("", encoding="utf-8")
    result = _run_prepare(fresh)
    assert result.returncode == 0 and "이미 준비하고 있습니다" in result.stdout
    assert _call_lines(fresh) == [] and fresh["lock"].exists()

    stale = _prepare_fixture(tmp_path / "stale", engine_installed=True, node_body="exit /b 0")
    stale["lock"].write_text("", encoding="utf-8")
    old = time.time() - 31 * 60
    os.utime(stale["lock"], (old, old))
    result = _run_prepare(stale)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_call_lines(stale)) == 1 and not stale["lock"].exists()


@_windows_only
def test_prepare_writes_its_own_log_so_the_launcher_needs_no_redirect(tmp_path: Path) -> None:
    """띄우는 쪽이 리다이렉트하면 부른 쪽 파이프가 이 창에 상속돼 켜기가 준비를 기다린다 -- 로그는 스스로 남긴다."""
    fixture = _prepare_fixture(tmp_path, engine_installed=True, node_body="echo fake-browser-output")
    log = tmp_path / "prepare.log"
    result = _run_prepare(fixture, "-LogPath", str(log))
    assert result.returncode == 0, result.stdout + result.stderr
    text = log.read_text(encoding="utf-8", errors="replace")
    assert "fake-browser-output" in text
    assert "모션 도구 준비가 끝났습니다" in text
    assert not fixture["lock"].exists()
