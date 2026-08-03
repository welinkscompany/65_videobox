from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "owner-ready.ps1"
SMOKE_SCRIPTS = (
    "smoke-hermes-yujin-creator-flow.ps1",
    "smoke-hermes-yujin-chat.ps1",
    "smoke-hermes-yujin-mem0.ps1",
    "verify-hermes-yujin-plan-state.ps1",
    "verify-hermes-yujin-profile.ps1",
    "verify-hermes-yujin-runtime.ps1",
)


@pytest.fixture(autouse=True)
def _windows_only() -> None:
    if os.name != "nt":
        pytest.skip("owner-ready.ps1 is a Windows owner tool")


def _write_fake_tool(path: Path) -> None:
    path.write_text(
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        'echo %~n0 %*>>"%FAKE_COMMAND_LOG%"\r\n'
        '1>&2 echo password=leak-me token=secret-token\r\n'
        'if /i "%~n0"=="git" goto git\r\n'
        'if /i "%~n0"=="docker" goto docker\r\n'
        'if /i "%~n0"=="python" (echo Python 3.12.10& exit /b 0)\r\n'
        'if /i "%~n0"=="node" (echo v22.14.0& exit /b 0)\r\n'
        'if /i "%~n0"=="npm" (echo 10.9.2& exit /b 0)\r\n'
        'if /i "%~n0"=="ffmpeg" (echo ffmpeg version 7.1& exit /b 0)\r\n'
        'if /i "%~n0"=="ffprobe" (echo ffprobe version 7.1& exit /b 0)\r\n'
        "exit /b 127\r\n"
        ":git\r\n"
        'if "%~1 %~2"=="rev-parse --show-toplevel" (echo %FAKE_REPO_ROOT%& exit /b 0)\r\n'
        'if "%~1 %~2"=="branch --show-current" (echo %FAKE_BRANCH%& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="rev-parse --short HEAD" (echo deadbeef& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="rev-parse --abbrev-ref --symbolic-full-name" (echo origin/%FAKE_BRANCH%& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="rev-list --left-right --count" (echo %FAKE_DIVERGENCE%& exit /b 0)\r\n'
        'if "%~1 %~2"=="status --short" (type "%FAKE_GIT_STATUS%"& exit /b 0)\r\n'
        "exit /b 1\r\n"
        ":docker\r\n"
        'if /i "%~1"=="version" (echo 27.5.1& exit /b %FAKE_DOCKER_EXIT%)\r\n'
        'if /i "%~1"=="compose" if /i "%~6"=="config" if /i "%~nx5"==".env.container" if "%FAKE_FAIL_ACTUAL_CONFIG%"=="1" exit /b 1\r\n'
        'if /i "%~1"=="compose" exit /b %FAKE_DOCKER_EXIT%\r\n'
        "exit /b 1\r\n",
        encoding="utf-8",
    )


def _fixture_repository(tmp_path: Path) -> dict[str, Path]:
    repository = tmp_path / "repo"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    if SCRIPT.is_file():
        shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    for name in SMOKE_SCRIPTS:
        (scripts / name).write_text(
            "param([switch]$StaticOnly)\n"
            "$line = $MyInvocation.MyCommand.Name + "
            "' static=' + $StaticOnly.IsPresent.ToString().ToLowerInvariant() + "
            "' args=' + ($args -join ',')\n"
            "Add-Content -LiteralPath $env:FAKE_SMOKE_LOG -Value $line -Encoding UTF8\n"
            "Write-Output 'password=leak-from-child token=leak-from-child'\n"
            "[Console]::Error.WriteLine('secret stderr from child')\n"
            "if ($env:FAKE_SMOKE_FAIL -ceq $MyInvocation.MyCommand.Name) { exit 1 }\n"
            "exit 0\n",
            encoding="utf-8-sig",
        )
    (repository / "compose.yaml").write_text("name: 65_videobox\nservices: {}\n", encoding="utf-8")
    (repository / ".env.container.example").write_text(
        "VIDEOBOX_CONTAINER_DATA_ROOT=C:/videobox-data\nPOSTGRES_PASSWORD=example\n",
        encoding="utf-8",
    )
    data_root = tmp_path / "vb-data"
    (data_root / "runtime").mkdir(parents=True)
    (data_root / "snapshot").mkdir()
    env_file = repository / ".env.container"
    env_file.write_text(
        f"VIDEOBOX_CONTAINER_DATA_ROOT={data_root.as_posix()}\n"
        "POSTGRES_PASSWORD=do-not-print-this\n"
        "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN=do-not-print-token\n",
        encoding="utf-8",
    )
    local_app_data = tmp_path / "local-app-data"
    capcut = local_app_data / "CapCut" / "Apps" / "9.0.0.3858" / "CapCut.exe"
    capcut.parent.mkdir(parents=True)
    capcut.write_bytes(b"fixture")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)

    tools = tmp_path / "tools"
    tools.mkdir()
    paths: dict[str, Path] = {}
    for name in ("git", "docker", "python", "node", "npm", "ffmpeg", "ffprobe"):
        path = tools / f"{name}.cmd"
        _write_fake_tool(path)
        paths[name] = path
    status = tmp_path / "git-status.txt"
    status.write_text(
        "?? .tmp-final-fence-debug/\n"
        "?? .tmp-real-video-dogfood/\n"
        "?? apps/web/.tmp-real-video-dogfood/\n",
        encoding="utf-8",
    )
    return {
        **paths,
        "repository": repository,
        "script": scripts / SCRIPT.name,
        "env_file": env_file,
        "data_root": data_root,
        "local_app_data": local_app_data,
        "status": status,
        "command_log": tmp_path / "commands.log",
        "smoke_log": tmp_path / "smoke.log",
        "receipt_root": tmp_path / "receipts",
    }


@contextmanager
def _health_server(
    *,
    status: int = 200,
    redirect: bool = False,
    redirect_location: str = "/login?next=%2F",
    body: bytes = b'{"status":"ok"}',
    omit_content_length: bool = False,
) -> Iterator[str]:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            calls.append(self.path)
            if redirect:
                self.send_response(302)
                self.send_header("Location", redirect_location)
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if not omit_content_length:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _unused_loopback_uri() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/"


@contextmanager
def _malformed_http_server() -> Iterator[str]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve_once() -> None:
        connection, _address = listener.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(b"THIS IS NOT HTTP\r\n\r\n")

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        listener.close()
        thread.join(timeout=5)


def _run(
    fixture: dict[str, Path],
    *,
    mode: str = "Check",
    timeout_sec: int = 2,
    video_uri: str | None = None,
    hermes_uri: str | None = None,
    extra: list[str] | None = None,
    environment_patch: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(fixture["script"]),
        "-Mode",
        mode,
        "-Json",
        "-TimeoutSec",
        str(timeout_sec),
        "-EnvFile",
        str(fixture["env_file"]),
        "-PythonExecutable",
        str(fixture["python"]),
        "-GitExecutable",
        str(fixture["git"]),
        "-DockerExecutable",
        str(fixture["docker"]),
        "-NodeExecutable",
        str(fixture["node"]),
        "-NpmExecutable",
        str(fixture["npm"]),
        "-FfmpegExecutable",
        str(fixture["ffmpeg"]),
        "-FfprobeExecutable",
        str(fixture["ffprobe"]),
        "-LocalAppData",
        str(fixture["local_app_data"]),
        "-ReceiptRoot",
        str(fixture["receipt_root"]),
        "-VideoBoxUri",
        video_uri or _unused_loopback_uri(),
        "-HermesDashboardUri",
        hermes_uri or _unused_loopback_uri(),
    ]
    command.extend(extra or [])
    environment = {
        **os.environ,
        "FAKE_COMMAND_LOG": str(fixture["command_log"]),
        "FAKE_REPO_ROOT": str(fixture["repository"]),
        "FAKE_BRANCH": "codex/videobox-container-compatibility",
        "FAKE_DIVERGENCE": "0 0",
        "FAKE_GIT_STATUS": str(fixture["status"]),
        "FAKE_DOCKER_EXIT": "0",
        "FAKE_FAIL_ACTUAL_CONFIG": "0",
        "FAKE_SMOKE_LOG": str(fixture["smoke_log"]),
        "FAKE_SMOKE_FAIL": "",
        **(environment_patch or {}),
    }
    return subprocess.run(
        command,
        cwd=fixture["repository"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode in {0, 1, 2}, result.stderr
    return json.loads(result.stdout)


def test_default_check_is_read_only_sanitized_and_classifies_protected_residue(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    before_data = sorted(path.relative_to(fixture["data_root"]) for path in fixture["data_root"].rglob("*"))
    before_capcut = sorted(path.relative_to(fixture["local_app_data"]) for path in fixture["local_app_data"].rglob("*"))
    with _health_server() as video_uri, _health_server() as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["schema_version"] == "videobox-owner-ready-v1"
    assert payload["mode"] == "Check"
    assert payload["overall_status"] == "pass"
    checks = payload["checks"]
    assert isinstance(checks, list) and checks
    assert all(set(row) == {"id", "status", "summary", "action", "evidence"} for row in checks)
    assert {row["status"] for row in checks} == {"pass"}
    working_tree = next(row for row in checks if row["id"] == "working_tree")
    assert working_tree["evidence"] == {"protected_residue_count": 3, "other_change_count": 0}
    serialized = json.dumps(payload).lower()
    assert "leak-me" not in serialized
    assert "secret-token" not in serialized
    assert "do-not-print" not in serialized
    assert str(fixture["repository"]).lower() not in serialized
    calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert 'docker "compose"' in calls and '"config"' in calls
    assert '"up"' not in calls
    assert "start-process" not in calls
    assert "smoke-hermes" not in calls
    assert before_data == sorted(path.relative_to(fixture["data_root"]) for path in fixture["data_root"].rglob("*"))
    assert before_capcut == sorted(path.relative_to(fixture["local_app_data"]) for path in fixture["local_app_data"].rglob("*"))
    assert not fixture["receipt_root"].exists()


def test_check_blocks_dirty_or_unknown_residue_without_exposing_paths(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["status"].write_text(" M services/api/private.py\n?? owner-secret-evidence/\n", encoding="utf-8")
    result = _run(fixture)

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["overall_status"] == "blocked"
    working_tree = next(row for row in payload["checks"] if row["id"] == "working_tree")
    assert working_tree["status"] == "blocked"
    assert working_tree["evidence"] == {"protected_residue_count": 0, "other_change_count": 2}
    serialized = json.dumps(payload)
    assert "private.py" not in serialized
    assert "owner-secret-evidence" not in serialized


@pytest.mark.parametrize(
    ("field", "uri"),
    [
        ("video_uri", "https://example.com/"),
        ("hermes_uri", "http://user:password@127.0.0.1:9119/"),
        ("video_uri", "http://127.0.0.1:5173/?secret=value"),
    ],
)
def test_check_rejects_unsafe_urls_before_any_probe(tmp_path: Path, field: str, uri: str) -> None:
    fixture = _fixture_repository(tmp_path)
    kwargs = {field: uri}
    result = _run(fixture, **kwargs)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["overall_status"] == "fail"
    assert payload["checks"] == [
        {
            "id": "network_boundary",
            "status": "fail",
            "summary": "로컬 주소 설정을 확인할 수 없습니다.",
            "action": "VideoBox와 Hermes 주소를 127.0.0.1의 기본 주소로 되돌린 뒤 다시 확인하세요.",
            "evidence": {"external_request_count": 0},
        }
    ]
    serialized = json.dumps(payload)
    assert "example.com" not in serialized
    assert "password" not in serialized


def test_check_blocks_detached_or_diverged_branch_without_path_output(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(
        fixture,
        environment_patch={"FAKE_BRANCH": "HEAD", "FAKE_DIVERGENCE": "1 2"},
    )

    payload = _payload(result)
    assert result.returncode == 2
    workspace = next(row for row in payload["checks"] if row["id"] == "workspace")
    assert workspace["status"] == "blocked"
    assert workspace["evidence"] == {"branch_attached": False, "upstream_synced": False}
    assert str(fixture["repository"]) not in json.dumps(payload)


def test_check_reports_missing_env_and_tool_as_precise_blocks(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["env_file"].unlink()
    fixture["ffmpeg"] = tmp_path / "missing-ffmpeg.exe"
    result = _run(fixture)

    payload = _payload(result)
    assert result.returncode == 2
    rows = {row["id"]: row for row in payload["checks"]}
    assert rows["ffmpeg"]["status"] == "blocked"
    assert rows["ffmpeg"]["evidence"] == {"available": False}
    assert rows["container_env"]["status"] == "blocked"
    assert rows["data_root"]["status"] == "blocked"
    assert rows["path_headroom"]["status"] == "blocked"
    assert rows["compose"]["status"] == "pass"
    assert '"config"' in fixture["command_log"].read_text(encoding="utf-8").lower()


def test_check_treats_the_unfollowed_hermes_login_redirect_as_reachable(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri, _health_server(redirect=True) as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0
    hermes = next(row for row in payload["checks"] if row["id"] == "hermes_dashboard")
    assert hermes["status"] == "pass"
    assert hermes["evidence"]["status_code"] == 302
    assert hermes["evidence"]["redirects_followed"] == 0


def test_check_rejects_an_external_hermes_redirect_without_following_it(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri, _health_server(
        redirect=True,
        redirect_location="https://example.com/login",
    ) as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    hermes = next(row for row in payload["checks"] if row["id"] == "hermes_dashboard")
    assert hermes["status"] == "fail"
    assert hermes["evidence"]["status_code"] == 302
    assert hermes["evidence"]["redirects_followed"] == 0
    assert hermes["evidence"]["external_request_count"] == 0


def test_check_still_rejects_a_redirect_from_videobox_health(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server(redirect=True) as video_uri, _health_server() as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    video = next(row for row in payload["checks"] if row["id"] == "videobox_health")
    assert video["status"] == "fail"
    assert video["evidence"]["status_code"] == 302
    assert video["evidence"]["redirects_followed"] == 0


@pytest.mark.parametrize(
    "body,omit_content_length",
    [
        (b"x" * 65537, True),
        (b"not-json", False),
        (b'{"status":"wrong"}', False),
    ],
    ids=["chunked_oversize", "malformed_json", "wrong_status"],
)
def test_check_fails_closed_on_oversize_or_invalid_video_health_body(
    tmp_path: Path,
    body: bytes,
    omit_content_length: bool,
) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server(body=body, omit_content_length=omit_content_length) as video_uri, _health_server() as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    video = next(row for row in payload["checks"] if row["id"] == "videobox_health")
    assert video["status"] == "fail"
    assert video["evidence"]["redirects_followed"] == 0


def test_check_classifies_a_malformed_http_response_as_fail_not_service_off(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _malformed_http_server() as video_uri, _health_server() as hermes_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    video = next(row for row in payload["checks"] if row["id"] == "videobox_health")
    assert video["status"] == "fail"
    assert "꺼져" not in video["summary"]


def test_check_blocks_a_data_root_without_legacy_windows_path_headroom(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    long_root = tmp_path / ("long-data-root-" + "x" * 85)
    (long_root / "runtime").mkdir(parents=True)
    (long_root / "snapshot").mkdir()
    fixture["env_file"].write_text(
        f"VIDEOBOX_CONTAINER_DATA_ROOT={long_root.as_posix()}\nPOSTGRES_PASSWORD=hidden\n",
        encoding="utf-8",
    )
    result = _run(fixture)

    payload = _payload(result)
    headroom = next(row for row in payload["checks"] if row["id"] == "path_headroom")
    assert result.returncode == 2
    assert headroom["status"] == "blocked"
    assert headroom["evidence"]["remaining_characters"] < 20
    assert "더 짧은 전용 데이터 폴더" in headroom["action"]
    assert str(long_root) not in json.dumps(payload)


def test_check_resolves_a_windows_cmd_tool_when_given_its_extensionless_path(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["npm"] = fixture["npm"].with_suffix("")
    result = _run(fixture)

    payload = _payload(result)
    npm = next(row for row in payload["checks"] if row["id"] == "npm")
    assert npm["status"] == "pass"
    assert npm["evidence"] == {"available": True, "version": "10.9.2"}


def test_start_is_blocked_without_env_and_never_runs_compose_up(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["env_file"].unlink()
    result = _run(fixture, mode="Start")

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["mode"] == "Start"
    assert payload["overall_status"] == "blocked"
    assert any(row["id"] == "container_env" and row["status"] == "blocked" for row in payload["checks"])
    calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert '"config"' in calls
    assert '"up"' not in calls


def test_start_runs_only_the_two_base_services_and_waits_for_health(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri:
        result = _run(fixture, mode="Start", video_uri=video_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["mode"] == "Start"
    assert payload["overall_status"] == "pass"
    started = next(row for row in payload["checks"] if row["id"] == "start")
    assert started["status"] == "pass"
    assert started["evidence"] == {
        "started": True,
        "services": ["videobox-postgres", "videobox-workspace"],
        "health_status_code": 200,
    }
    calls = fixture["command_log"].read_text(encoding="utf-8").lower().splitlines()
    up_calls = [line for line in calls if '"up"' in line]
    assert len(up_calls) == 1
    assert up_calls[0].endswith('"up" "-d" "videobox-postgres" "videobox-workspace"')
    assert "hermes" not in up_calls[0]
    assert "profile" not in up_calls[0]
    assert "remove-orphans" not in up_calls[0]
    serialized = json.dumps(payload).lower()
    assert "do-not-print" not in serialized
    assert str(fixture["env_file"]).lower() not in serialized


def test_start_validates_the_actual_env_without_output_before_compose_up(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(
        fixture,
        mode="Start",
        environment_patch={"FAKE_FAIL_ACTUAL_CONFIG": "1"},
    )

    payload = _payload(result)
    assert result.returncode == 1
    actual_config = next(row for row in payload["checks"] if row["id"] == "start_compose")
    assert actual_config["status"] == "fail"
    assert actual_config["evidence"] == {"parsed": False, "raw_config_recorded": False}
    calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert calls.count('"config"') == 2
    assert '"up"' not in calls
    serialized = json.dumps(payload).lower()
    assert "do-not-print" not in serialized
    assert str(fixture["env_file"]).lower() not in serialized


def test_start_whatif_reports_intent_without_running_compose_up(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(fixture, mode="Start", extra=["-WhatIf"])

    payload = _payload(result)
    assert result.returncode == 0
    start = next(row for row in payload["checks"] if row["id"] == "start")
    assert start["status"] == "pass"
    assert start["evidence"] == {
        "started": False,
        "services": ["videobox-postgres", "videobox-workspace"],
        "what_if": True,
    }
    calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert '"up"' not in calls


def test_smoke_runs_exact_static_non_live_scripts_and_writes_sanitized_receipt(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(fixture, mode="Smoke")

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["mode"] == "Smoke"
    assert payload["overall_status"] == "pass"
    assert payload["external_provider_calls"] == 0
    assert [row["id"] for row in payload["checks"]] == [
        "creator_flow_non_live",
        "chat_non_live",
        "mem0_non_live",
        "plan_state",
        "profile_static",
        "runtime_static",
    ]
    calls = fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()
    assert len(calls) == 6
    assert [line.split()[0] for line in calls] == list(SMOKE_SCRIPTS)
    assert all("live" not in line.lower() for line in calls)
    assert all("static=true" in line for line in calls[-2:])
    assert all("static=false" in line for line in calls[:4])
    assert all(line.endswith(" args=") for line in calls)
    receipts = list(fixture["receipt_root"].glob("owner-ready-smoke-*.json"))
    assert len(receipts) == 1
    assert list(fixture["receipt_root"].glob("*.tmp")) == []
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert set(receipt) == {
        "schema_version",
        "mode",
        "overall_status",
        "generated_at",
        "commit",
        "external_provider_calls",
        "checks",
    }
    assert receipt["mode"] == "Smoke"
    assert receipt["overall_status"] == "pass"
    assert receipt["commit"] == "deadbeef"
    assert receipt["external_provider_calls"] == 0
    assert all(set(row) == {"id", "status", "action"} for row in receipt["checks"])
    serialized = json.dumps(payload) + receipts[0].read_text(encoding="utf-8")
    assert "leak-from-child" not in serialized
    assert "secret stderr" not in serialized
    assert str(fixture["repository"]) not in serialized
    assert str(fixture["receipt_root"]) not in serialized


def test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    hanging_script = fixture["repository"] / "scripts" / SMOKE_SCRIPTS[0]
    child_pid_path = tmp_path / "hanging-child.pid"
    hanging_script.write_text(
        "param([switch]$StaticOnly)\n"
        "$child = Start-Process -FilePath powershell -ArgumentList "
        "'-NoProfile','-Command','Start-Sleep -Seconds 30' -NoNewWindow -PassThru\n"
        "[IO.File]::WriteAllText($env:FAKE_CHILD_PID_PATH, [string]$child.Id)\n"
        "Start-Sleep -Seconds 30\n",
        encoding="utf-8-sig",
    )

    started = time.monotonic()
    result = _run(
        fixture,
        mode="Smoke",
        timeout_sec=1,
        environment_patch={"FAKE_CHILD_PID_PATH": str(child_pid_path)},
    )
    elapsed = time.monotonic() - started

    payload = _payload(result)
    assert result.returncode == 1
    assert elapsed < 8
    assert payload["checks"][0]["id"] == "creator_flow_non_live"
    assert payload["checks"][0]["status"] == "fail"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    child_probe = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"if (Get-Process -Id {child_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}",
        ],
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert child_probe.returncode == 0


def test_smoke_continues_after_one_failure_and_records_only_bounded_results(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(
        fixture,
        mode="Smoke",
        environment_patch={"FAKE_SMOKE_FAIL": "smoke-hermes-yujin-chat.ps1"},
    )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["overall_status"] == "fail"
    assert len(payload["checks"]) == 6
    failed = [row for row in payload["checks"] if row["status"] == "fail"]
    assert [row["id"] for row in failed] == ["chat_non_live"]
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 6
    receipt = json.loads(next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["overall_status"] == "fail"
    assert len(receipt["checks"]) == 6
    assert "leak-from-child" not in json.dumps(receipt)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (
            "Open",
            {"opened": False, "target": "videobox_loopback", "what_if": True},
        ),
        (
            "OpenCapCut",
            {
                "opened": False,
                "target": "capcut",
                "arguments": 0,
                "what_if": True,
            },
        ),
    ],
)
def test_open_modes_report_exact_targets_under_whatif_without_launching(
    tmp_path: Path, mode: str, expected: dict[str, object]
) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(fixture, mode=mode, extra=["-WhatIf"])

    payload = _payload(result)
    assert result.returncode == 0
    opened = next(row for row in payload["checks"] if row["id"] == "open")
    assert opened["status"] == "pass"
    assert opened["evidence"] == expected
    assert not fixture["receipt_root"].exists()
    source = SCRIPT.read_text(encoding="utf-8-sig")
    assert "Start-Process -FilePath $VideoBoxUri.AbsoluteUri" in source
    assert "Start-Process -FilePath $script:capCutExecutable" in source
    assert "-ArgumentList" not in source
