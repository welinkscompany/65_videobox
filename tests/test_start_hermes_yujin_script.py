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
MINIMUM_PASSWORD = "123456789012"
MINIMUM_PASSWORD_HASH = (
    "scrypt$16384$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$"
    "ZDdxqiZYgrigmrdTCAdvmXQvbXlKPUOS9oJw2i3yb+A="
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
        MINIMUM_PASSWORD,
        MINIMUM_PASSWORD_HASH,
        "valid-dummy-user",
        "replace-before-starting",
        "${MISSING}",
    ):
        assert forbidden not in output


def _rendered_model(
    workspace_environment: dict[str, object] | None = None,
    gateway_username: str = "valid-dummy-user",
    gateway_password: str = VALID_PASSWORD,
    password_hash: str = VALID_HASH,
) -> dict[str, object]:
    return {
        "services": {
            "videobox-agent-gateway": {
                "environment": {
                    "HERMES_YUJIN_GATEWAY_PASSWORD": gateway_password,
                    "HERMES_YUJIN_GATEWAY_USERNAME": gateway_username,
                    "HERMES_YUJIN_URL": "http://videobox-hermes-yujin:9120",
                }
            },
            "videobox-hermes-yujin": {
                "environment": {
                    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": password_hash,
                    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": gateway_username,
                }
            },
            "videobox-workspace": {
                "environment": workspace_environment
                or {"POSTGRES_PASSWORD": "static-value"}
            },
        }
    }


def _write_fake_docker(tmp_path: Path) -> Path:
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
        'echo %* | findstr /c:"run" >nul\r\n'
        "if not errorlevel 1 exit /b 0\r\n"
        'powershell -NoProfile -Command "[Console]::Error.Write(('
        "'u' * 1048576))"
        '"\r\n'
        "exit /b %FAKE_DOCKER_UP_EXIT%\r\n",
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
    validate_only: bool = False,
    config_stderr: str = "quiet",
    up_exit_code: int = 0,
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
            )
        ),
        encoding="utf-8",
    )
    fake_log = tmp_path / "docker.log"
    fake_docker = _write_fake_docker(tmp_path)
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
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env={
            **os.environ,
            "FAKE_DOCKER_CONFIG": str(fake_config),
            "FAKE_DOCKER_CONFIG_STDERR": config_stderr,
            "FAKE_DOCKER_LOG": str(fake_log),
            "FAKE_DOCKER_UP_EXIT": str(up_exit_code),
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


@pytest.mark.parametrize(
    ("up_exit_code", "expected_returncode"),
    ((0, 0), (23, 1)),
)
def test_start_streams_large_stderr_without_pipe_deadlock(
    tmp_path: Path,
    up_exit_code: int,
    expected_returncode: int,
) -> None:
    result, invocations = _run_fake_start(
        tmp_path,
        up_exit_code=up_exit_code,
    )

    assert result.returncode == expected_returncode
    assert len(invocations) == (5 if expected_returncode == 0 else 4)
    assert "run --rm --no-deps" in invocations[2]
    assert "profile install /opt/videobox-yujin-profile" in invocations[2]
    assert " up " in f" {invocations[3]} "
    assert "u" * 65536 in result.stderr
    if expected_returncode == 0:
        assert "videobox-hermes-yujin" in invocations[3]
        assert "videobox-agent-gateway" in invocations[4]
        assert "targeted for startup" in result.stdout
    else:
        assert "Targeted Hermes Yujin runtime startup failed." in result.stderr
    _assert_no_values_leaked(result)


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
