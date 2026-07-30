from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "restart-hermes-yujin.ps1"
TARGET = "videobox-hermes-yujin"


def _fake_docker(tmp_path: Path) -> Path:
    script = tmp_path / "docker.cmd"
    script.write_text(
        "@echo off\r\n"
        'echo %*>>"%FAKE_DOCKER_LOG%"\r\n'
        'set "FAKE_COMMAND="\r\n'
        'set "FAKE_HAS_FORMAT="\r\n'
        "for %%A in (%*) do (\r\n"
        '  if "%%~A"=="restart" set "FAKE_COMMAND=restart"\r\n'
        '  if "%%~A"=="--format" set "FAKE_HAS_FORMAT=true"\r\n'
        ")\r\n"
        'if "%FAKE_COMMAND%"=="restart" (\r\n'
        '  if "%FAKE_RESTART_HANG%"=="1" for /L %%Z in (1,1,2147483647) do rem\r\n'
        '  echo restarted>"%FAKE_DOCKER_STATE%"\r\n'
        "  exit /b %FAKE_RESTART_EXIT%\r\n"
        ")\r\n"
        'if not "%FAKE_HAS_FORMAT%"=="true" (\r\n'
        '  if exist "%FAKE_DOCKER_STATE%" (\r\n'
        '    if not "%FAKE_POST_ID%"=="" echo %FAKE_POST_ID%\r\n'
        "  ) else (\r\n"
        '    if not "%FAKE_PRE_ID%"=="" echo %FAKE_PRE_ID%\r\n'
        "  )\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        'type "%FAKE_HEALTH_JSON%"\r\n'
        'powershell -NoProfile -Command "[Console]::Error.Write('
        "'password=do-not-leak hash=secret-hash'"
        ')"\r\n'
        "exit /b 0\r\n",
        encoding="utf-8",
    )
    return script


def _run(
    tmp_path: Path,
    *,
    pre_id: str = "container-1",
    post_id: str = "container-1",
    restart_exit: int = 0,
    health: str = "healthy",
    restart_hang: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "container.env"
    env_file.write_text("VIDEOBOX_TEST_ONLY=1\n", encoding="utf-8")
    log_file = tmp_path / "docker.log"
    state_file = tmp_path / "docker.state"
    health_file = tmp_path / "health.json"
    health_file.write_text(
        json.dumps(
            [
                {
                    "Service": TARGET,
                    "State": "running",
                    "Health": health,
                    "ID": post_id,
                }
            ]
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "FAKE_DOCKER_LOG": str(log_file),
        "FAKE_DOCKER_STATE": str(state_file),
        "FAKE_PRE_ID": pre_id,
        "FAKE_POST_ID": post_id,
        "FAKE_RESTART_EXIT": str(restart_exit),
        "FAKE_HEALTH_JSON": str(health_file),
        "FAKE_RESTART_HANG": "1" if restart_hang else "0",
    }
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-EnvFile",
            str(env_file),
            "-DockerExecutable",
            str(_fake_docker(tmp_path)),
            "-TimeoutSec",
            "1",
            "-PollIntervalMs",
            "10",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    calls = (
        log_file.read_text(encoding="utf-8").splitlines()
        if log_file.exists()
        else []
    )
    return result, calls


def _tokens(call: str) -> list[str]:
    return shlex.split(call, posix=False)


def test_restart_targets_only_existing_yujin_and_preserves_container(
    tmp_path: Path,
) -> None:
    result, calls = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "HERMES_YUJIN_RESTARTED"
    assert result.stderr == ""
    restart_calls = [call for call in calls if '"restart"' in call]
    assert len(restart_calls) == 1
    tokens = _tokens(restart_calls[0])
    assert tokens[-1].strip('"') == TARGET
    assert all(
        forbidden not in " ".join(calls).lower()
        for forbidden in (
            '"down"',
            '"rm"',
            '"remove"',
            '"kill"',
            '"prune"',
            '"--volumes"',
            '"--force-recreate"',
            "videobox-workspace",
            "videobox-agent-gateway",
            "videobox-hermes-dashboard",
        )
    )
    assert "do-not-leak" not in result.stdout + result.stderr
    assert "secret-hash" not in result.stdout + result.stderr
    assert "container-1" not in result.stdout + result.stderr


def test_absent_container_fails_before_restart(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, pre_id="")

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:container_missing" in result.stderr
    assert not any('"restart"' in call for call in calls)


def test_restart_failure_is_fixed_and_redacted(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, restart_exit=7)

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:restart_command" in result.stderr
    assert len([call for call in calls if '"restart"' in call]) == 1
    assert "do-not-leak" not in result.stdout + result.stderr


def test_changed_container_id_fails_closed(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, post_id="container-2")

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:container_replaced" in result.stderr


def test_health_timeout_fails_without_recreate(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, health="starting")

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:health_timeout" in result.stderr
    joined = " ".join(calls).lower()
    assert '"restart"' in joined
    assert "--force-recreate" not in joined
    assert '"up"' not in joined


def test_default_env_path_reaches_fixed_configuration_gate(
    tmp_path: Path,
) -> None:
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    copied_script = script_dir / SCRIPT.name
    copied_script.write_text(
        SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(copied_script),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:configuration_missing" in result.stderr
    assert "Cannot bind argument to parameter 'Path'" not in result.stderr


def test_restart_docker_process_is_bounded_and_redacted(tmp_path: Path) -> None:
    started = time.monotonic()
    result, calls = _run(tmp_path, restart_hang=True)
    elapsed = time.monotonic() - started

    assert result.returncode != 0
    assert "HERMES_YUJIN_RESTART_FAILED:restart_command" in result.stderr
    assert elapsed < 3
    assert len([call for call in calls if '"restart"' in call]) == 1
    assert "do-not-leak" not in result.stdout + result.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert ".WaitForExit()" not in source
    assert "WaitForExit($TimeoutSec * 1000)" in source
