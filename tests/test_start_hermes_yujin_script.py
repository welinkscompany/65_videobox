from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "start-hermes-yujin.ps1"
VALID_PASSWORD = "valid-dummy-password"
VALID_HASH = (
    "scrypt$16384$8$1$iMe7ySNXHHKwvzoVKA3TJw==$"
    "kS4ekg9YeJwxO84hL0GQ/gaj4dMfUKWPJFmhwSFuaUQ="
)


def _env_text(*extra_lines: str) -> str:
    lines = [
        "POSTGRES_PASSWORD=static-postgres-password",
        "VIDEOBOX_CONTAINER_DATA_ROOT=D:/videobox-static-data",
        "BASE_GATEWAY_USERNAME=valid-dummy-user",
        "HERMES_YUJIN_GATEWAY_USERNAME=${BASE_GATEWAY_USERNAME}",
        f"HERMES_YUJIN_GATEWAY_PASSWORD={VALID_PASSWORD}",
        f"HERMES_YUJIN_GATEWAY_PASSWORD_HASH='{VALID_HASH}'",
    ]
    lines.extend(extra_lines)
    return "\n".join(lines) + "\n"


def _validate(tmp_path: Path, text: str) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "container.env"
    env_file.write_text(text, encoding="utf-8")
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-EnvFile",
            str(env_file),
            "-ValidateOnly",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _assert_no_values_leaked(result: subprocess.CompletedProcess[str]) -> None:
    output = f"{result.stdout}\n{result.stderr}"
    for forbidden in (
        VALID_PASSWORD,
        VALID_HASH,
        "valid-dummy-user",
        "replace-before-starting",
        "${MISSING}",
    ):
        assert forbidden not in output


def test_unresolved_value_never_reaches_targeted_up_with_a_fake_executable(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "container.env"
    env_file.write_text(
        _env_text("HERMES_YUJIN_GATEWAY_PASSWORD=${MISSING}"),
        encoding="utf-8",
    )
    fake_docker = tmp_path / "docker.cmd"
    fake_log = tmp_path / "docker.log"
    fake_config = tmp_path / "config.json"
    fake_config.write_text(
        json.dumps(
            {
                "services": {
                    "videobox-agent-gateway": {
                        "environment": {
                            "HERMES_YUJIN_GATEWAY_PASSWORD": "${MISSING}",
                            "HERMES_YUJIN_GATEWAY_USERNAME": "valid-dummy-user",
                            "HERMES_YUJIN_URL": "http://videobox-hermes-yujin:9120",
                        }
                    },
                    "videobox-hermes-yujin": {
                        "environment": {
                            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": VALID_HASH,
                            "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": "valid-dummy-user",
                        }
                    },
                    "videobox-workspace": {
                        "environment": {"POSTGRES_PASSWORD": "static-value"}
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    fake_docker.write_text(
        "@echo off\r\n"
        'echo %*>>"%FAKE_DOCKER_LOG%"\r\n'
        'echo %* | findstr /c:"config" >nul\r\n'
        "if %errorlevel%==0 (\r\n"
        '  type "%FAKE_DOCKER_CONFIG%"\r\n'
        ")\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )
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
            str(fake_docker),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_DOCKER_CONFIG": str(fake_config),
            "FAKE_DOCKER_LOG": str(fake_log),
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode != 0
    invocations = fake_log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 1
    assert "config" in invocations[0]
    assert " up " not in f" {invocations[0]} "
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    "extra_lines",
    (
        ('HERMES_YUJIN_GATEWAY_USERNAME=""',),
        ("HERMES_YUJIN_GATEWAY_PASSWORD= # resolves empty",),
        ("HERMES_YUJIN_GATEWAY_PASSWORD=${MISSING}",),
        (
            "HERMES_YUJIN_GATEWAY_PASSWORD=first-value",
            "HERMES_YUJIN_GATEWAY_PASSWORD=",
        ),
        ("HERMES_YUJIN_GATEWAY_USERNAME=   ",),
        ("HERMES_YUJIN_GATEWAY_PASSWORD=",),
        ("HERMES_YUJIN_GATEWAY_PASSWORD=replace-before-starting",),
        ("HERMES_YUJIN_GATEWAY_PASSWORD_HASH=placeholder",),
    ),
)
def test_validate_only_rejects_fail_open_env_shapes_without_leaking_values(
    tmp_path: Path,
    extra_lines: tuple[str, ...],
) -> None:
    result = _validate(tmp_path, _env_text(*extra_lines))

    assert result.returncode != 0
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    "extra_lines",
    (
        (),
        (
            "HERMES_YUJIN_GATEWAY_PASSWORD=replace-before-starting",
            f"HERMES_YUJIN_GATEWAY_PASSWORD={VALID_PASSWORD}",
        ),
    ),
)
def test_validate_only_accepts_resolved_values_and_duplicate_last_wins(
    tmp_path: Path,
    extra_lines: tuple[str, ...],
) -> None:
    result = _validate(tmp_path, _env_text(*extra_lines))

    assert result.returncode == 0, "validation failed without safe diagnostics"
    _assert_no_values_leaked(result)


def test_start_script_uses_compose_and_pinned_hermes_as_validation_authorities() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "[IO.File]::ReadAllLines" not in source
    assert '"config"' in source
    assert '"--format", "json"' in source
    assert "compose.hermes-yujin.yaml" in source
    assert '"--profile", "hermes-yujin"' in source
    assert "plugins.dashboard_auth.basic import _verify_password" in source
    assert '"--network", "none"' in source
    assert "ProcessStartInfo" in source
    assert "-ValidateOnly" not in source
    assert "skip-security" not in source.lower()
