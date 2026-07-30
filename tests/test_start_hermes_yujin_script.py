from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "start-hermes-yujin.ps1"
PROFILE_ROOT = ROOT / "config" / "hermes" / "yujin"
VALID_PASSWORD = "valid-dummy-password"
VALID_SERVICE_TOKEN = "valid-service-token-that-is-at-least-32"
VALID_CAPABILITY_PRIVATE_KEY_B64 = (
    "ERERERERERERERERERERERERERERERERERERERERERE"
)
VALID_CAPABILITY_PUBLIC_KEY_B64 = (
    "0EqyMnQrtKs6E2i9RhXk5tAiSrcaAWuvhSCjMsl3hzc"
)
VALID_CAPABILITY_KEY_ID = "c3-test-key-2026-07"
VALID_HASH = (
    "scrypt$16384$8$1$iMe7ySNXHHKwvzoVKA3TJw==$"
    "kS4ekg9YeJwxO84hL0GQ/gaj4dMfUKWPJFmhwSFuaUQ="
)
MINIMUM_PASSWORD = "123456789012"
MINIMUM_PASSWORD_HASH = (
    "scrypt$16384$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$"
    "ZDdxqiZYgrigmrdTCAdvmXQvbXlKPUOS9oJw2i3yb+A="
)
PERSISTENT_PROFILE_STATE = (
    "Profile install persists in the videobox_hermes_oauth_state named volume "
    "at /opt/data; service cleanup does not delete that volume. "
    "Rerun uses --force idempotently."
)
SAFE_RERUN_RECOVERY = (
    "Recovery: powershell -NoProfile -ExecutionPolicy Bypass "
    "-File scripts/start-hermes-yujin.ps1 -EnvFile <approved-env-file>"
)


def _env_text(*extra_lines: str) -> str:
    lines = [
        "POSTGRES_PASSWORD=static-postgres-password",
        "VIDEOBOX_CONTAINER_DATA_ROOT=D:/videobox-static-data",
        "BASE_GATEWAY_USERNAME=valid-dummy-user",
        "HERMES_YUJIN_GATEWAY_USERNAME=${BASE_GATEWAY_USERNAME}",
        f"HERMES_YUJIN_GATEWAY_PASSWORD={VALID_PASSWORD}",
        f"HERMES_YUJIN_GATEWAY_PASSWORD_HASH='{VALID_HASH}'",
        f"VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN={VALID_SERVICE_TOKEN}",
        (
            "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64="
            f"{VALID_CAPABILITY_PRIVATE_KEY_B64}"
        ),
        (
            "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64="
            f"{VALID_CAPABILITY_PUBLIC_KEY_B64}"
        ),
        f"VIDEOBOX_HERMES_CAPABILITY_KEY_ID={VALID_CAPABILITY_KEY_ID}",
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
        MINIMUM_PASSWORD,
        MINIMUM_PASSWORD_HASH,
        "valid-dummy-user",
        "replace-before-starting",
        "${MISSING}",
        VALID_CAPABILITY_PRIVATE_KEY_B64,
        VALID_CAPABILITY_PUBLIC_KEY_B64,
    ):
        assert forbidden not in output


def _rendered_model(
    workspace_environment: dict[str, object] | None = None,
    gateway_username: str = "valid-dummy-user",
    gateway_password: str = VALID_PASSWORD,
    password_hash: str = VALID_HASH,
    gateway_service_token: str = VALID_SERVICE_TOKEN,
    capability_private_key_b64: str = VALID_CAPABILITY_PRIVATE_KEY_B64,
    capability_public_key_b64: str = VALID_CAPABILITY_PUBLIC_KEY_B64,
    capability_key_id: str = VALID_CAPABILITY_KEY_ID,
) -> dict[str, object]:
    return {
        "services": {
            "videobox-agent-gateway": {
                "environment": {
                    "HERMES_YUJIN_GATEWAY_PASSWORD": gateway_password,
                    "HERMES_YUJIN_GATEWAY_USERNAME": gateway_username,
                    "HERMES_YUJIN_URL": "http://videobox-hermes-yujin:9120",
                    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN": gateway_service_token,
                    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64": (
                        capability_private_key_b64
                    ),
                    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID": capability_key_id,
                }
            },
            "videobox-hermes-yujin": {
                "environment": {
                    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": password_hash,
                    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": gateway_username,
                    "HERMES_TUI_TOOLSETS": "context_engine",
                }
            },
            "videobox-workspace": {
                "environment": {
                    "POSTGRES_PASSWORD": "static-value",
                    "VIDEOBOX_AGENT_GATEWAY_URL": "http://videobox-agent-gateway:8081",
                    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN": gateway_service_token,
                    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64": (
                        capability_public_key_b64
                    ),
                    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID": capability_key_id,
                    **(workspace_environment or {}),
                }
            },
        }
    }


def _write_fake_docker(
    tmp_path: Path,
    *,
    gateway_stop_exit_code: int,
    profile_install_exit_code: int,
    quiesce_stop_exit_code: int,
) -> Path:
    fake_docker = tmp_path / "docker.cmd"
    fake_docker.write_text(
        "@echo off\r\n"
        'echo %*>>"%FAKE_DOCKER_LOG%"\r\n'
        'echo %* | findstr /c:"config" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        '  if /I "%FAKE_DOCKER_CONFIG_STDERR%"=="large" (\r\n'
        '    powershell -NoProfile -Command "[Console]::Error.Write(('
        "'c' * 1048576))"
        '"\r\n'
        "  )\r\n"
        '  type "%FAKE_DOCKER_CONFIG%"\r\n'
        "  exit /b 0\r\n"
        ")\r\n"
        'echo %* | findstr /c:"--status" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        '  if /I "%FAKE_DOCKER_PREEXISTING%"=="true" '
        "echo videobox-hermes-yujin\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        'echo %* | findstr /c:"stop" >nul\r\n'
        "if errorlevel 1 goto not_stop\r\n"
        'echo %* | findstr /c:"videobox-workspace" >nul\r\n'
        f"if not errorlevel 1 exit /b {quiesce_stop_exit_code}\r\n"
        'echo %* | findstr /c:"videobox-agent-gateway" >nul\r\n'
        f"if not errorlevel 1 exit /b {gateway_stop_exit_code}\r\n"
        "exit /b %FAKE_DOCKER_STOP_EXIT%\r\n"
        ":not_stop\r\n"
        'echo %* | findstr /c:"--no-deps" >nul\r\n'
        f"if not errorlevel 1 exit /b {profile_install_exit_code}\r\n"
        'echo %* | findstr /c:"run" >nul\r\n'
        "if not errorlevel 1 exit /b 0\r\n"
        'echo %* | findstr /c:"--force-recreate" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        '  echo %* | findstr /c:"videobox-workspace" >nul\r\n'
        "  if not errorlevel 1 (\r\n"
        '    powershell -NoProfile -Command "[Console]::Error.Write(('
        "'u' * 1048576))"
        '"\r\n'
        "    exit /b %FAKE_DOCKER_WORKSPACE_UP_EXIT%\r\n"
        "  )\r\n"
        ")\r\n"
        'echo %* | findstr /c:"videobox-agent-gateway" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        '  powershell -NoProfile -Command "[Console]::Error.Write(('
        "'u' * 1048576))"
        '"\r\n'
        "  exit /b %FAKE_DOCKER_GATEWAY_UP_EXIT%\r\n"
        ")\r\n"
        'powershell -NoProfile -Command "[Console]::Error.Write(('
        "'u' * 1048576))"
        '"\r\n'
        "exit /b %FAKE_DOCKER_HERMES_UP_EXIT%\r\n",
        encoding="utf-8",
    )
    return fake_docker


def _run_fake_start(
    tmp_path: Path,
    *,
    workspace_environment: dict[str, object] | None = None,
    gateway_username: str = "valid-dummy-user",
    gateway_password: str = VALID_PASSWORD,
    password_hash: str = VALID_HASH,
    gateway_service_token: str = VALID_SERVICE_TOKEN,
    capability_private_key_b64: str = VALID_CAPABILITY_PRIVATE_KEY_B64,
    capability_public_key_b64: str = VALID_CAPABILITY_PUBLIC_KEY_B64,
    capability_key_id: str = VALID_CAPABILITY_KEY_ID,
    validate_only: bool = False,
    config_stderr: str = "quiet",
    hermes_up_exit_code: int = 0,
    gateway_up_exit_code: int = 0,
    workspace_up_exit_code: int = 0,
    profile_install_exit_code: int = 0,
    stop_exit_code: int = 0,
    gateway_stop_exit_code: int = 0,
    quiesce_stop_exit_code: int = 0,
    preexisting_hermes: bool = False,
    profile_root: Path | None = None,
    timeout_seconds: float = 8,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "container.env"
    env_file.write_text(_env_text(), encoding="utf-8")
    fake_config = tmp_path / "config.json"
    fake_config.write_text(
        json.dumps(
            _rendered_model(
                workspace_environment,
                gateway_username,
                gateway_password,
                password_hash,
                gateway_service_token,
                capability_private_key_b64,
                capability_public_key_b64,
                capability_key_id,
            )
        ),
        encoding="utf-8",
    )
    fake_log = tmp_path / "docker.log"
    fake_docker = _write_fake_docker(
        tmp_path,
        gateway_stop_exit_code=gateway_stop_exit_code,
        profile_install_exit_code=profile_install_exit_code,
        quiesce_stop_exit_code=quiesce_stop_exit_code,
    )
    command = [
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
    ]
    if validate_only:
        command.append("-ValidateOnly")
    if profile_root is not None:
        command.extend(["-ProfileRoot", str(profile_root)])
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_DOCKER_CONFIG": str(fake_config),
            "FAKE_DOCKER_CONFIG_STDERR": config_stderr,
            "FAKE_DOCKER_LOG": str(fake_log),
            "FAKE_DOCKER_HERMES_UP_EXIT": str(hermes_up_exit_code),
            "FAKE_DOCKER_GATEWAY_UP_EXIT": str(gateway_up_exit_code),
            "FAKE_DOCKER_WORKSPACE_UP_EXIT": str(workspace_up_exit_code),
            "FAKE_DOCKER_PROFILE_INSTALL_EXIT": str(
                profile_install_exit_code
            ),
            "FAKE_DOCKER_STOP_EXIT": str(stop_exit_code),
            "FAKE_DOCKER_QUIESCE_STOP_EXIT": str(
                quiesce_stop_exit_code
            ),
            "FAKE_DOCKER_PREEXISTING": str(preexisting_hermes).lower(),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        process.communicate(timeout=5)
        pytest.fail(
            f"Hermes Yujin startup exceeded the {timeout_seconds:g}s bound"
        )
    result = subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout,
        stderr,
    )
    invocations = (
        fake_log.read_text(encoding="utf-8").splitlines()
        if fake_log.exists()
        else []
    )
    return result, invocations


def test_captured_validation_drains_large_stderr_without_deadlock(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        validate_only=True,
        config_stderr="large",
    )

    assert result.returncode == 0
    assert len(invocations) == 2
    assert "config" in invocations[0]
    assert "run" in invocations[1]
    _assert_no_values_leaked(result)


def test_validate_only_runs_profile_static_verification_without_install_or_up(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "yujin"
    shutil.copytree(PROFILE_ROOT, copied)
    valid_runtime = tmp_path / "valid-runtime"
    invalid_runtime = tmp_path / "invalid-runtime"
    valid_runtime.mkdir()
    invalid_runtime.mkdir()

    valid, valid_invocations = _run_fake_start(
        valid_runtime,
        validate_only=True,
        profile_root=copied,
    )
    assert valid.returncode == 0, valid.stderr
    assert len(valid_invocations) == 2

    (copied / "config.yaml").write_text(
        "nested:\n  client_secret: generated-runtime-value\n",
        encoding="utf-8",
    )
    invalid, invalid_invocations = _run_fake_start(
        invalid_runtime,
        validate_only=True,
        profile_root=copied,
    )
    assert invalid.returncode != 0
    assert len(invalid_invocations) == 2
    assert all("profile install" not in call for call in invalid_invocations)
    assert all(" up " not in f" {call} " for call in invalid_invocations)
    assert "generated-runtime-value" not in f"{invalid.stdout}\n{invalid.stderr}"


@pytest.mark.parametrize(
    ("hermes_up_exit_code", "expected_returncode"),
    ((0, 0), (23, 1)),
)
def test_start_streams_large_stderr_without_pipe_deadlock(
    tmp_path: Path,
    hermes_up_exit_code: int,
    expected_returncode: int,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        hermes_up_exit_code=hermes_up_exit_code,
    )

    assert result.returncode == expected_returncode
    assert len(invocations) == (8 if expected_returncode == 0 else 5)
    assert '"ps"' in invocations[2]
    assert "run --rm --no-deps" in invocations[3]
    assert "profile install /opt/videobox-yujin-profile" in invocations[3]
    assert " up " in f" {invocations[4]} "
    assert "--wait" in invocations[4]
    assert "u" * 65536 in result.stderr
    if expected_returncode == 0:
        assert "videobox-hermes-yujin" in invocations[4]
        assert '"stop"' in invocations[5]
        assert '"videobox-agent-gateway"' in invocations[5]
        assert '"videobox-workspace"' in invocations[5]
        assert "videobox-workspace" in invocations[6]
        assert "--force-recreate" in invocations[6]
        assert "--wait" in invocations[6]
        assert "videobox-agent-gateway" in invocations[7]
        assert "--wait" in invocations[7]
        assert "targeted for startup" in result.stdout
    else:
        assert "Targeted Hermes Yujin runtime startup failed." in result.stderr
    _assert_no_values_leaked(result)


def test_hermes_start_failure_reports_persistent_profile_and_safe_rerun(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        hermes_up_exit_code=23,
    )
    compact_stderr = re.sub(r"\s+", "", result.stderr)

    assert result.returncode != 0
    assert re.sub(r"\s+", "", PERSISTENT_PROFILE_STATE) in compact_stderr
    assert re.sub(r"\s+", "", SAFE_RERUN_RECOVERY) in compact_stderr
    assert "Targeted Hermes Yujin runtime startup failed." in result.stderr
    assert str(tmp_path) not in result.stderr
    _assert_no_values_leaked(result)
    assert any("profile install" in call for call in invocations)
    hermes_up_call = next(
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-hermes-yujin" in call
    )
    assert "--wait" in hermes_up_call
    assert all('"down"' not in call for call in invocations)
    assert all('"volume"' not in call for call in invocations)
    assert all('"-v"' not in call for call in invocations)
    assert all('"stop"' not in call for call in invocations)


def test_profile_install_failure_preserves_existing_admission_without_quiesce(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        profile_install_exit_code=37,
    )

    assert result.returncode != 0
    assert "profile installation failed" in result.stderr
    assert all('"stop"' not in call for call in invocations)
    assert all("videobox-workspace" not in call or '"config"' in call for call in invocations)
    assert all(
        not (" up " in f" {call} " and "videobox-agent-gateway" in call)
        for call in invocations
    )
    _assert_no_values_leaked(result)


def test_key_replacement_quiesces_both_services_before_recreate_and_admission(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=True,
    )

    assert result.returncode == 0
    quiesce_calls = [
        call
        for call in invocations
        if '"stop"' in call
        and '"videobox-agent-gateway"' in call
        and '"videobox-workspace"' in call
    ]
    workspace_calls = [
        call
        for call in invocations
        if " up " in f" {call} "
        and "videobox-workspace" in call
        and "--force-recreate" in call
        and "--wait" in call
    ]
    gateway_calls = [
        call
        for call in invocations
        if " up " in f" {call} "
        and "videobox-agent-gateway" in call
        and "--force-recreate" in call
    ]
    profile_call = next(
        call for call in invocations if "profile install" in call
    )
    assert len(quiesce_calls) == 1
    assert len(workspace_calls) == 1
    assert len(gateway_calls) == 1
    assert invocations.index(profile_call) < invocations.index(
        quiesce_calls[0]
    )
    assert invocations.index(quiesce_calls[0]) < invocations.index(
        workspace_calls[0]
    )
    assert invocations.index(workspace_calls[0]) < invocations.index(
        gateway_calls[0]
    )
    _assert_no_values_leaked(result)


def test_new_hermes_and_profile_are_ready_before_coordinated_quiesce(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(tmp_path)

    assert result.returncode == 0
    profile_call = next(
        call for call in invocations if "profile install" in call
    )
    hermes_up_call = next(
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-hermes-yujin" in call
    )
    quiesce_call = next(
        call
        for call in invocations
        if '"stop"' in call
        and '"videobox-agent-gateway"' in call
        and '"videobox-workspace"' in call
    )
    workspace_call = next(
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-workspace" in call
    )
    gateway_call = next(
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-agent-gateway" in call
    )
    assert invocations.index(profile_call) < invocations.index(hermes_up_call)
    assert "--wait" in hermes_up_call
    assert invocations.index(hermes_up_call) < invocations.index(quiesce_call)
    assert invocations.index(quiesce_call) < invocations.index(workspace_call)
    assert invocations.index(workspace_call) < invocations.index(gateway_call)
    assert "--wait" in gateway_call
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    ("preexisting_hermes", "stop_exit_code", "expected_phrase"),
    (
        (False, 0, "newly started Hermes service was stopped"),
        (False, 41, "automatic stop failed"),
        (True, 0, "Pre-existing Hermes service was left running"),
    ),
)
def test_quiesce_failure_recovers_only_new_hermes_and_preserves_admission(
    tmp_path: Path,
    preexisting_hermes: bool,
    stop_exit_code: int,
    expected_phrase: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=preexisting_hermes,
        quiesce_stop_exit_code=43,
        stop_exit_code=stop_exit_code,
    )

    assert result.returncode != 0
    assert "admission quiesce failed" in result.stderr
    assert expected_phrase in result.stderr
    hermes_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call and '"videobox-hermes-yujin"' in call
    ]
    workspace_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-workspace" in call
    ]
    gateway_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-agent-gateway" in call
    ]
    assert workspace_calls == []
    assert gateway_calls == []
    if preexisting_hermes:
        assert hermes_stop_calls == []
    else:
        assert len(hermes_stop_calls) == 1
    _assert_no_values_leaked(result)


def test_workspace_recreate_failure_keeps_gateway_quiesced_without_key_output(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=True,
        workspace_up_exit_code=31,
    )

    assert result.returncode != 0
    workspace_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-workspace" in call
    ]
    gateway_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-agent-gateway" in call
    ]
    assert len(workspace_calls) == 1
    assert gateway_calls == []
    assert all('"down"' not in call for call in invocations)
    assert all('"volume"' not in call for call in invocations)
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    ("preexisting_hermes", "stop_exit_code", "expected_phrase"),
    (
        (False, 0, "newly started Hermes service was stopped"),
        (False, 41, "automatic stop failed"),
        (True, 0, "Pre-existing Hermes service was left running"),
    ),
)
def test_workspace_failure_preserves_or_recovers_hermes_by_prior_state(
    tmp_path: Path,
    preexisting_hermes: bool,
    stop_exit_code: int,
    expected_phrase: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=preexisting_hermes,
        workspace_up_exit_code=31,
        stop_exit_code=stop_exit_code,
    )

    assert result.returncode != 0
    assert "workspace restart failed" in result.stderr
    assert expected_phrase in result.stderr
    hermes_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call and '"videobox-hermes-yujin"' in call
    ]
    if preexisting_hermes:
        assert hermes_stop_calls == []
    else:
        assert len(hermes_stop_calls) == 1
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    ("preexisting_hermes", "stop_exit_code", "expected_phrase"),
    (
        (False, 0, "newly started Hermes service was stopped"),
        (False, 41, "automatic stop failed"),
        (True, 0, "Pre-existing Hermes service was left running"),
    ),
)
def test_gateway_failure_preserves_or_recovers_hermes_by_prior_state(
    tmp_path: Path,
    preexisting_hermes: bool,
    stop_exit_code: int,
    expected_phrase: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=preexisting_hermes,
        gateway_up_exit_code=29,
        stop_exit_code=stop_exit_code,
    )

    assert result.returncode != 0
    assert "gateway startup failed" in result.stderr
    compact_stderr = re.sub(r"\s+", "", result.stderr)
    assert re.sub(r"\s+", "", expected_phrase) in compact_stderr
    assert re.sub(r"\s+", "", PERSISTENT_PROFILE_STATE) in compact_stderr
    assert re.sub(r"\s+", "", SAFE_RERUN_RECOVERY) in compact_stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert SAFE_RERUN_RECOVERY in source
    assert "generated-runtime-value" not in result.stderr
    assert str(tmp_path) not in result.stderr
    _assert_no_values_leaked(result)
    for invocation in invocations:
        assert '"down"' not in invocation
        assert '"rm"' not in invocation
        assert '"-v"' not in invocation
    quiesce_calls = [
        call
        for call in invocations
        if '"stop"' in call
        and '"videobox-agent-gateway"' in call
        and '"videobox-workspace"' in call
    ]
    hermes_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call and '"videobox-hermes-yujin"' in call
    ]
    hermes_up_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-hermes-yujin" in call
    ]
    gateway_up_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-agent-gateway" in call
    ]
    gateway_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call
        and '"videobox-agent-gateway"' in call
        and '"videobox-workspace"' not in call
    ]
    assert len(quiesce_calls) == 1
    assert len(gateway_up_calls) == 1
    assert "--wait" in gateway_up_calls[0]
    assert len(gateway_stop_calls) == 1
    assert gateway_stop_calls[0].endswith(
        '"stop" "videobox-agent-gateway"'
    )
    assert invocations.index(gateway_stop_calls[0]) == (
        invocations.index(gateway_up_calls[0]) + 1
    )
    if preexisting_hermes:
        assert hermes_stop_calls == []
        assert hermes_up_calls == []
    else:
        assert len(hermes_stop_calls) == 1
        assert len(hermes_up_calls) == 1
        assert invocations.index(gateway_stop_calls[0]) < invocations.index(
            hermes_stop_calls[0]
        )


@pytest.mark.parametrize(
    ("preexisting_hermes", "stop_exit_code", "expected_phrase"),
    (
        (False, 0, "newly started Hermes service was stopped"),
        (False, 41, "automatic Hermes stop failed"),
        (True, 0, "Pre-existing Hermes service was left running"),
    ),
)
def test_gateway_quiescence_failure_reports_unconfirmed_admission_and_recovers_hermes(
    tmp_path: Path,
    preexisting_hermes: bool,
    stop_exit_code: int,
    expected_phrase: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        preexisting_hermes=preexisting_hermes,
        gateway_up_exit_code=29,
        gateway_stop_exit_code=47,
        stop_exit_code=stop_exit_code,
    )

    assert result.returncode != 0
    compact_stderr = re.sub(r"\s+", "", result.stderr)
    assert re.sub(r"\s+", "", "gateway startup failed") in compact_stderr
    assert re.sub(r"\s+", "", "gateway stop failed") in compact_stderr
    assert (
        re.sub(r"\s+", "", "admission quiescence could not be confirmed")
        in compact_stderr
    )
    assert re.sub(r"\s+", "", expected_phrase) in compact_stderr
    assert re.sub(r"\s+", "", SAFE_RERUN_RECOVERY) in compact_stderr
    _assert_no_values_leaked(result)

    gateway_up_calls = [
        call
        for call in invocations
        if " up " in f" {call} " and "videobox-agent-gateway" in call
    ]
    gateway_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call
        and '"videobox-agent-gateway"' in call
        and '"videobox-workspace"' not in call
    ]
    hermes_stop_calls = [
        call
        for call in invocations
        if '"stop"' in call and '"videobox-hermes-yujin"' in call
    ]
    assert len(gateway_up_calls) == 1
    assert len(gateway_stop_calls) == 1
    assert gateway_stop_calls[0].endswith(
        '"stop" "videobox-agent-gateway"'
    )
    assert invocations.index(gateway_stop_calls[0]) == (
        invocations.index(gateway_up_calls[0]) + 1
    )
    if preexisting_hermes:
        assert hermes_stop_calls == []
    else:
        assert len(hermes_stop_calls) == 1
        assert invocations.index(gateway_stop_calls[0]) < invocations.index(
            hermes_stop_calls[0]
        )
    for invocation in invocations:
        assert '"down"' not in invocation
        assert '"rm"' not in invocation
        assert '"-v"' not in invocation


@pytest.mark.parametrize(
    "aliased_secret",
    ("valid-dummy-user", VALID_PASSWORD, VALID_HASH),
)
def test_workspace_alias_of_any_resolved_credential_fails_closed(
    tmp_path: Path,
    aliased_secret: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        workspace_environment={"SAFE_ALIAS": aliased_secret},
        validate_only=True,
    )

    assert result.returncode != 0
    assert len(invocations) == 1
    assert "config" in invocations[0]
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    "composite_secret",
    (
        f"https://user:{VALID_PASSWORD}@host/path",
        f"prefix-{VALID_PASSWORD}-suffix",
        f"https://host/{VALID_HASH}/status",
        f"prefix-{VALID_HASH}-suffix",
    ),
)
def test_workspace_composite_password_or_hash_fails_closed(
    tmp_path: Path,
    composite_secret: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        workspace_environment={"SAFE_ALIAS": composite_secret},
        validate_only=True,
    )

    assert result.returncode != 0
    assert len(invocations) == 1
    _assert_no_values_leaked(result)


@pytest.mark.parametrize("password_length", range(12))
def test_validate_only_rejects_passwords_shorter_than_twelve_before_hash_check(
    tmp_path: Path,
    password_length: int,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        gateway_password="x" * password_length,
        validate_only=True,
    )

    assert result.returncode != 0
    assert len(invocations) == 1
    _assert_no_values_leaked(result)


def test_validate_only_accepts_a_twelve_character_password_boundary(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        gateway_password=MINIMUM_PASSWORD,
        password_hash=MINIMUM_PASSWORD_HASH,
        validate_only=True,
    )

    assert result.returncode == 0
    assert len(invocations) == 2
    _assert_no_values_leaked(result)


def test_workspace_allows_a_benign_username_substring(
    tmp_path: Path,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        gateway_username="videobox",
        workspace_environment={
            "videobox": "benign-key-value",
            "DATABASE_URL": "postgresql://videobox:database-password@postgres/db",
        },
        validate_only=True,
    )

    assert result.returncode == 0
    assert len(invocations) == 2
    assert "videobox" not in f"{result.stdout}\n{result.stderr}"
    _assert_no_values_leaked(result)


@pytest.mark.parametrize(
    "environment_json",
    ("null", '"text"', "7", "[]", '["value"]', '{"SAFE":{"nested":"value"}}'),
)
def test_shared_environment_contract_rejects_non_scalar_maps(
    tmp_path: Path,
    environment_json: str,
) -> None:
    input_path = tmp_path / "environment.json"
    input_path.write_text(environment_json, encoding="utf-8")
    helper = ROOT / "scripts" / "hermes-yujin-environment-contract.ps1"
    command = (
        f". '{helper}'; "
        f"$value = Get-Content -Raw -LiteralPath '{input_path}' | ConvertFrom-Json; "
        "Assert-NoHermesYujinCredentialValueAliases "
        "-Environment $value -ExactCredentialValues @('username') "
        "-SecretSubstringValues @('password','hash') "
        "-FailureMessage 'forbidden'"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "secret" not in f"{result.stdout}\n{result.stderr}"


def test_shared_environment_contract_accepts_an_idictionary_map(
    tmp_path: Path,
) -> None:
    helper = ROOT / "scripts" / "hermes-yujin-environment-contract.ps1"
    runner = tmp_path / "runner.ps1"
    runner.write_text(
        f". '{helper}'\n"
        "$environment = @{SAFE='benign-secret-suffix'}; "
        "Assert-NoHermesYujinCredentialValueAliases "
        "-Environment $environment "
        "-ExactCredentialValues ([string[]]@('username')) "
        "-SecretSubstringValues ([string[]]@('password','hash')) "
        "-FailureMessage 'forbidden'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0


@pytest.mark.parametrize("array_value", ([], ["benign"], ["a", "b"]))
def test_validate_only_rejects_workspace_property_arrays_before_password_check(
    tmp_path: Path,
    array_value: list[str],
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        workspace_environment={"SAFE_ARRAY": array_value},
        validate_only=True,
    )

    assert result.returncode != 0
    assert len(invocations) == 1
    assert "config" in invocations[0]
    _assert_no_values_leaked(result)


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


@pytest.mark.parametrize("token", ["a" * 32, "abcd" * 8])
def test_validate_only_rejects_low_entropy_service_token_without_leaking_it(
    tmp_path: Path,
    token: str,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        gateway_service_token=token,
        validate_only=True,
    )

    assert result.returncode != 0
    assert len(invocations) == 1
    assert token not in f"{result.stdout}\n{result.stderr}"


@pytest.mark.parametrize(
    "extra_lines",
    (
        ("VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64=",),
        (
            "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64="
            "replace-before-starting",
        ),
        ("VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64=not-base64",),
        (
            "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64="
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        ),
        ("VIDEOBOX_HERMES_CAPABILITY_KEY_ID=",),
        ("VIDEOBOX_HERMES_CAPABILITY_KEY_ID=placeholder",),
        ("VIDEOBOX_HERMES_CAPABILITY_KEY_ID=changeme",),
        ("VIDEOBOX_HERMES_CAPABILITY_KEY_ID=replace_me",),
        ("VIDEOBOX_HERMES_CAPABILITY_KEY_ID=bad key id",),
    ),
)
def test_validate_only_rejects_invalid_or_mismatched_capability_pair_without_leak(
    tmp_path: Path,
    extra_lines: tuple[str, ...],
) -> None:
    result = _validate(tmp_path, _env_text(*extra_lines))

    assert result.returncode != 0
    _assert_no_values_leaked(result)


def test_start_script_validates_pinned_ed25519_pair_without_key_generation_or_output() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "cryptography==45.0.6" in source
    assert "Ed25519PrivateKey.from_private_bytes" in source
    assert "public_bytes" in source
    assert "generate" not in source.lower()
    assert "Write-Output $capability" not in source
    assert "Set-Content" not in source


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
