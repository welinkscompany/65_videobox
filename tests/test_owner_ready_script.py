from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
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

SMOKE_MARKERS = {
    "smoke-hermes-yujin-creator-flow.ps1": (
        "HERMES_YUJIN_CREATOR_NON_LIVE_PASS "
        "sse_completed=true proposal_ready=true session_file_bound=true "
        "mutation_before_apply=0 session_revision_delta=1 caption_changes=1 "
        "playback_manifest_checked=true output_readiness_checked=true "
        "output_jobs=0 external_provider_calls=0"
    ),
    "smoke-hermes-yujin-chat.ps1": (
        "HERMES_YUJIN_CANARY_NON_LIVE network_calls=0 proposal_calls=0 "
        "provider_body_recorded=false"
    ),
    "smoke-hermes-yujin-mem0.ps1": (
        "HERMES_YUJIN_MEM0_NON_LIVE network_calls=0 provider_calls=0 "
        "credentials_printed=false"
    ),
    "verify-hermes-yujin-plan-state.ps1": (
        "Hermes Yujin plan state verified: 20 unique master task IDs; "
        "all 20 occur exactly once across four children; statuses and progress agree."
    ),
    "verify-hermes-yujin-profile.ps1": (
        "Hermes Yujin profile ownership and secret-free contents verified."
    ),
    "verify-hermes-yujin-runtime.ps1": (
        "Hermes Yujin D2 static topology verified: exact chat, gateway, and "
        "optional memory adapter boundaries."
    ),
}

PUBLIC_MARKERS = (
    "creator_non_live_pass",
    "chat_non_live_zero_calls",
    "mem0_non_live_zero_calls",
    "plan_state_verified",
    "profile_static_verified",
    "runtime_static_verified",
)

REQUIRED_CREDENTIAL_KEYS = (
    "HERMES_YUJIN_GATEWAY_USERNAME",
    "HERMES_YUJIN_GATEWAY_PASSWORD",
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH",
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN",
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64",
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64",
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID",
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN",
)


def _valid_env_text(data_root: Path) -> str:
    credential_lines = [
        f"{key}=safe-fixture-{index}"
        for index, key in enumerate(REQUIRED_CREDENTIAL_KEYS, start=1)
    ]
    return "\n".join(
        [
            f"VIDEOBOX_CONTAINER_DATA_ROOT={data_root.as_posix()}",
            "POSTGRES_PASSWORD=do-not-print-this",
            *credential_lines,
            "",
        ]
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
        'if "%~1 %~2"=="rev-parse HEAD" goto git_head\r\n'
        'if "%~1 %~2 %~3"=="rev-parse --short HEAD" (set /p FAKE_HEAD_VALUE=<"%FAKE_HEAD_PATH%"& echo !FAKE_HEAD_VALUE:~0,8!& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="rev-parse --abbrev-ref --symbolic-full-name" (echo origin/%FAKE_BRANCH%& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="rev-list --left-right --count" (echo %FAKE_DIVERGENCE%& exit /b 0)\r\n'
        'if "%~1 %~2"=="status --short" (type "%FAKE_GIT_STATUS%"& exit /b 0)\r\n'
        'if "%~1 %~2 %~3"=="ls-files --error-unmatch --" if /i "%~4"=="%FAKE_UNTRACKED_CHILD%" exit /b 1\r\n'
        'if "%~1 %~2 %~3"=="ls-files --error-unmatch --" exit /b 0\r\n'
        'if "%~1 %~2"=="diff --quiet" if "%~4"=="--" if /i "%~5"=="%FAKE_DIRTY_CHILD%" exit /b 1\r\n'
        'if "%~1 %~2"=="diff --quiet" if "%~4"=="--" exit /b 0\r\n'
        "exit /b 1\r\n"
        ":git_head\r\n"
        'set /p FAKE_HEAD_READ_COUNT=<"%FAKE_HEAD_READ_COUNT_PATH%"\r\n'
        "set /a FAKE_HEAD_READ_COUNT=!FAKE_HEAD_READ_COUNT!+1 >nul\r\n"
        '>"%FAKE_HEAD_READ_COUNT_PATH%" echo !FAKE_HEAD_READ_COUNT!\r\n'
        'type "%FAKE_HEAD_PATH%"\r\n'
        'if "!FAKE_HEAD_READ_COUNT!"=="2" if "%FAKE_HEAD_MUTATE_AFTER_FINAL%"=="1" >"%FAKE_HEAD_PATH%" echo feedface11111111111111111111111111111111\r\n'
        "exit /b 0\r\n"
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
        marker = SMOKE_MARKERS[name].replace("'", "''")
        (scripts / name).write_text(
            "param([switch]$StaticOnly)\n"
            "$line = $MyInvocation.MyCommand.Name + "
            "' static=' + $StaticOnly.IsPresent.ToString().ToLowerInvariant() + "
            "' args=' + ($args -join ',')\n"
            "Add-Content -LiteralPath $env:FAKE_SMOKE_LOG -Value $line -Encoding UTF8\n"
            "Write-Output 'password=leak-from-child token=leak-from-child'\n"
            "[Console]::Error.WriteLine('secret stderr from child')\n"
            "if ($env:FAKE_SMOKE_FAIL -ceq $MyInvocation.MyCommand.Name) { exit 1 }\n"
            f"$marker = '{marker}'\n"
            "if ($env:FAKE_SMOKE_TARGET -ceq $MyInvocation.MyCommand.Name) {\n"
            "    switch ($env:FAKE_SMOKE_MUTATION) {\n"
            "        'missing' { $marker = '' }\n"
            "        'malformed' { $marker += ' malformed-token' }\n"
            "        'duplicate' { $marker += ' network_calls=0' }\n"
            "        'unknown' { $marker += ' unknown_field=true' }\n"
            "        'nonzero_zero_call' { $marker = $marker.Replace('network_calls=0', 'network_calls=1') }\n"
            "    }\n"
            "}\n"
            "if (-not [string]::IsNullOrEmpty($marker)) { Write-Output $marker }\n"
            "if ($env:FAKE_SMOKE_SELF_MUTATE -ceq $MyInvocation.MyCommand.Name) {\n"
            "    Add-Content -LiteralPath $MyInvocation.MyCommand.Path -Value '# execution-time mutation' -Encoding UTF8\n"
            "}\n"
            "if ($env:FAKE_SMOKE_HEAD_MUTATE -ceq $MyInvocation.MyCommand.Name) {\n"
            "    [IO.File]::WriteAllText($env:FAKE_HEAD_PATH, 'feedface11111111111111111111111111111111')\n"
            "}\n"
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
    env_file.write_text(_valid_env_text(data_root), encoding="utf-8")
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
    fake_head = tmp_path / "fake-head.txt"
    fake_head.write_text("deadbeef00000000000000000000000000000000", encoding="ascii")
    fake_head_read_count = tmp_path / "fake-head-read-count.txt"
    fake_head_read_count.write_text("0", encoding="ascii")
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
        "fake_head": fake_head,
        "fake_head_read_count": fake_head_read_count,
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
    request_log: list[str] | None = None,
    delay_seconds: float = 0,
) -> Iterator[str]:
    calls = request_log if request_log is not None else []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            calls.append(self.path)
            if delay_seconds:
                time.sleep(delay_seconds)
            if redirect:
                self.send_response(302)
                self.send_header("Location", redirect_location.format(port=self.server.server_port))
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if not omit_content_length:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def _local_model_server(*, model_key: str = "qwen3-35b") -> Iterator[str]:
    # LM Studio의 실제 `/api/v1/models` 응답 모양을 그대로 흉내 낸다(2026-08-11 실측).
    # `Get-LocalModelCheck`는 `type == "llm"`이고 `loaded_instances`가 비어 있지
    # 않은 항목의 `key`만 후보로 본다.
    body = json.dumps({
        "models": [
            {"type": "llm", "key": model_key, "loaded_instances": [{"id": model_key}]},
        ]
    }).encode("utf-8")
    with _health_server(body=body) as uri:
        yield uri


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


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    command = (
        "$stream=[IO.File]::Open($env:OWNER_READY_TEST_LOCK_PATH,[IO.FileMode]::Open,"
        "[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);"
        "[Console]::Out.WriteLine('locked');[Console]::Out.Flush();"
        "[void][Console]::In.ReadLine();$stream.Dispose()"
    )
    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "OWNER_READY_TEST_LOCK_PATH": str(path)},
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "locked"
    try:
        yield
    finally:
        if process.stdin is not None:
            process.stdin.write("release\n")
            process.stdin.flush()
        process.wait(timeout=5)


def _run(
    fixture: dict[str, Path],
    *,
    mode: str = "Check",
    timeout_sec: int = 2,
    video_uri: str | None = None,
    hermes_uri: str | None = None,
    local_model_uri: str | None = None,
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
        "-LocalModelApiUri",
        local_model_uri or _unused_loopback_uri(),
    ]
    command.extend(extra or [])
    environment = {
        **os.environ,
        "FAKE_COMMAND_LOG": str(fixture["command_log"]),
        "FAKE_REPO_ROOT": str(fixture["repository"]),
        "FAKE_BRANCH": "codex/videobox-container-compatibility",
        "FAKE_DIVERGENCE": "0 0",
        "FAKE_GIT_STATUS": str(fixture["status"]),
        "FAKE_HEAD_PATH": str(fixture["fake_head"]),
        "FAKE_HEAD_READ_COUNT_PATH": str(fixture["fake_head_read_count"]),
        "FAKE_HEAD_MUTATE_AFTER_FINAL": "0",
        "FAKE_DOCKER_EXIT": "0",
        "FAKE_FAIL_ACTUAL_CONFIG": "0",
        "FAKE_SMOKE_LOG": str(fixture["smoke_log"]),
        "FAKE_SMOKE_FAIL": "",
        "FAKE_SMOKE_TARGET": "",
        "FAKE_SMOKE_MUTATION": "",
        "FAKE_UNTRACKED_CHILD": "",
        "FAKE_DIRTY_CHILD": "",
        "FAKE_SMOKE_SELF_MUTATE": "",
        "FAKE_SMOKE_HEAD_MUTATE": "",
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


def _replace_env_value(fixture: dict[str, Path], key: str, value: str) -> None:
    lines = fixture["env_file"].read_text(encoding="utf-8").splitlines()
    fixture["env_file"].write_text(
        "\n".join(value if line.startswith(f"{key}=") else line for line in lines) + "\n",
        encoding="utf-8",
    )


def _smoke_receipt_text(fixture: dict[str, Path]) -> str:
    receipts = list(fixture["receipt_root"].glob("owner-ready-smoke-*.json"))
    assert len(receipts) == 1
    return receipts[0].read_text(encoding="utf-8")


def _connection_classification_map(script: Path, names: tuple[str, ...]) -> dict[str, str]:
    command = (
        "$tokens=$null;$parseErrors=$null;"
        "$ast=[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:OWNER_READY_SCRIPT,[ref]$tokens,[ref]$parseErrors);"
        "if($parseErrors.Count -ne 0){exit 10};"
        "$reasonFunction=$ast.Find({param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -ceq 'Get-ConnectionUnavailableReason'},$true);"
        "$classificationFunction=$ast.Find({param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -ceq 'Get-ConnectionProbeFailure'},$true);"
        "if($null -eq $reasonFunction -or $null -eq $classificationFunction){exit 11};"
        "Invoke-Expression $reasonFunction.Extent.Text;"
        "Invoke-Expression $classificationFunction.Extent.Text;"
        "foreach($name in $env:SOCKET_ERROR_NAMES.Split(',')){"
        "$code=[Enum]::Parse([System.Net.Sockets.SocketError],$name);"
        "$exception=[System.Net.Sockets.SocketException]::new([int]$code);"
        "$classification=Get-ConnectionProbeFailure -Exception $exception;"
        "Write-Output ($name+'='+$classification.State+','+$classification.Reason)}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        env={
            **os.environ,
            "OWNER_READY_SCRIPT": str(script),
            "SOCKET_ERROR_NAMES": ",".join(names),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def test_default_check_is_read_only_sanitized_and_classifies_protected_residue(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    before_data = sorted(path.relative_to(fixture["data_root"]) for path in fixture["data_root"].rglob("*"))
    before_capcut = sorted(path.relative_to(fixture["local_app_data"]) for path in fixture["local_app_data"].rglob("*"))
    with _health_server() as video_uri, _health_server() as hermes_uri, _local_model_server() as model_uri:
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri, local_model_uri=model_uri)

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
    with (
        _health_server() as video_uri,
        _health_server(redirect=True) as hermes_uri,
        _local_model_server() as model_uri,
    ):
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri, local_model_uri=model_uri)

    payload = _payload(result)
    assert result.returncode == 0
    hermes = next(row for row in payload["checks"] if row["id"] == "hermes_dashboard")
    assert hermes["status"] == "pass"
    assert hermes["evidence"]["status_code"] == 302
    assert hermes["evidence"]["redirects_followed"] == 0


def test_check_passes_when_the_configured_model_is_the_one_lm_studio_has_loaded(
    tmp_path: Path,
) -> None:
    fixture = _fixture_repository(tmp_path)
    with (
        _health_server() as video_uri,
        _health_server() as hermes_uri,
        _local_model_server(model_key="qwen3-35b") as model_uri,
    ):
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri, local_model_uri=model_uri)

    payload = _payload(result)
    row = next(item for item in payload["checks"] if item["id"] == "local_model")
    assert row["status"] == "pass"
    assert row["evidence"]["configured_model"] == "qwen3-35b"
    assert row["evidence"]["loaded_llm_models"] == ["qwen3-35b"]


def test_check_blocks_when_the_configured_model_name_does_not_match_what_is_loaded(
    tmp_path: Path,
) -> None:
    # 이게 오늘 실제로 이 저장소에서 벌어지고 있던 어긋남이다(2026-08-11) --
    # `.env.container`가 비어 있으면 기본값(`qwen3-35b`)을 쓰는데, LM Studio는
    # `qwen/qwen3.6-35b-a3b`를 로드해 두고도 조용히 요청을 받아 준다. 이 확인이
    # 없으면 owner는 다른 모델로 바꾼 뒤에도 그 사실을 알 길이 없다.
    fixture = _fixture_repository(tmp_path)
    with (
        _health_server() as video_uri,
        _health_server() as hermes_uri,
        _local_model_server(model_key="gemma-3-27b") as model_uri,
    ):
        result = _run(fixture, video_uri=video_uri, hermes_uri=hermes_uri, local_model_uri=model_uri)

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["overall_status"] == "blocked"
    row = next(item for item in payload["checks"] if item["id"] == "local_model")
    assert row["status"] == "blocked"
    assert row["evidence"]["configured_model"] == "qwen3-35b"
    assert row["evidence"]["loaded_llm_models"] == ["gemma-3-27b"]
    assert "qwen3-35b" in row["summary"]
    assert "gemma-3-27b" in row["action"]


def test_check_blocks_when_lm_studio_is_not_reachable(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri, _health_server() as hermes_uri:
        result = _run(
            fixture,
            video_uri=video_uri,
            hermes_uri=hermes_uri,
            local_model_uri=_unused_loopback_uri(),
        )

    payload = _payload(result)
    assert result.returncode == 2
    row = next(item for item in payload["checks"] if item["id"] == "local_model")
    assert row["status"] == "blocked"
    assert row["evidence"]["reachable"] is False
    assert "LM Studio" in row["summary"]


def test_check_keeps_stalled_loopback_as_blocked_with_bounded_timeout_reason(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri, _health_server(delay_seconds=2) as hermes_uri:
        result = _run(
            fixture,
            video_uri=video_uri,
            hermes_uri=hermes_uri,
            timeout_sec=1,
        )

    payload = _payload(result)
    hermes = next(row for row in payload["checks"] if row["id"] == "hermes_dashboard")
    assert result.returncode == 2
    assert payload["overall_status"] == "blocked"
    assert hermes["status"] == "blocked"
    assert hermes["evidence"]["probe_reason"] == "timeout"
    assert str(fixture["repository"]) not in json.dumps(payload)


def test_connection_reason_classifier_preserves_broad_unavailable_socket_errors(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    broad_names = (
        "ConnectionReset",
        "HostDown",
        "HostNotFound",
        "NetworkDown",
        "NetworkUnreachable",
        "TimedOut",
    )

    classifications = _connection_classification_map(
        fixture["script"],
        ("ConnectionRefused", *broad_names),
    )

    assert classifications["ConnectionRefused"] == "blocked,connection_refused"
    assert {classifications[name] for name in broad_names} == {
        "blocked,connection_unavailable"
    }


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


def test_start_waits_through_the_gateway_502s_that_precede_a_ready_app(tmp_path: Path) -> None:
    """실측(2026-08-17): 재시작 직후 1~3초는 nginx가 502를 돌려주고 4초부터 200이다.

    프로브가 첫 502를 '실패'로 보고 대기 루프를 즉시 빠져나오는 바람에, 재빌드할 때마다
    `[FAIL]`이 떴고 확인해 보면 매번 healthy였다. **거짓 실패가 위험한 이유는 불편해서가
    아니라, 진짜 실패와 똑같이 생겨서 사람이 FAIL을 무시하도록 길들이기 때문이다.**
    """
    attempts: list[str] = []

    class WarmingUpHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            attempts.append(self.path)
            if len(attempts) <= 3:
                self.send_response(502)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), WarmingUpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fixture = _fixture_repository(tmp_path)
        result = _run(fixture, mode="Start", video_uri=f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()

    payload = _payload(result)
    started = next(row for row in payload["checks"] if row["id"] == "start")
    assert started["status"] == "pass", started
    assert started["evidence"]["health_status_code"] == 200
    # 포기하지 않고 다시 물어봤다는 증거.
    assert len(attempts) > 3


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
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["mode"] == "Smoke"
    assert payload["overall_status"] == "pass"
    assert payload["readiness_status"] == "local_ready"
    assert payload["static_non_live_checks_passed"] is True
    assert payload["dashboard_status"] == "ready"
    assert payload["credential_status"] == "present_unverified"
    assert payload["live_canary_status"] == "not_run"
    assert payload["external_provider_calls"] == 0
    assert payload["external_network_calls"] == 0
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
    serialized_calls = "\n".join(calls).lower()
    for forbidden in (
        "-live",
        "approve",
        "projectid",
        "sessionid",
        "conversationid",
        "credential",
        "password",
        "token",
    ):
        assert forbidden not in serialized_calls
    tool_calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert "docker " not in tool_calls
    assert "start-hermes-yujin" not in tool_calls
    assert "get-hermes-yujin-status" not in tool_calls
    assert "verify-hermes-yujin-zero-tools" not in tool_calls
    receipts = list(fixture["receipt_root"].glob("owner-ready-smoke-*.json"))
    assert len(receipts) == 1
    assert list(fixture["receipt_root"].glob("*.tmp")) == []
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert set(receipt) == {
        "schema_version",
        "mode",
        "readiness_status",
        "static_non_live_checks_passed",
        "dashboard_status",
        "credential_status",
        "live_canary_status",
        "generated_at",
        "commit",
        "external_provider_calls",
        "external_network_calls",
        "checks",
    }
    assert receipt["schema_version"] == "videobox-hermes-readiness-v1"
    assert receipt["mode"] == "Smoke"
    assert receipt["readiness_status"] == "local_ready"
    assert receipt["static_non_live_checks_passed"] is True
    assert receipt["dashboard_status"] == "ready"
    assert receipt["credential_status"] == "present_unverified"
    assert receipt["live_canary_status"] == "not_run"
    assert receipt["commit"] == "deadbeef00000000000000000000000000000000"
    assert receipt["external_provider_calls"] == 0
    assert receipt["external_network_calls"] == 0
    assert all(
        set(row) == {"id", "mode", "status", "marker", "script_sha256", "action"}
        for row in receipt["checks"]
    )
    assert [row["marker"] for row in receipt["checks"]] == list(PUBLIC_MARKERS)
    assert [row["mode"] for row in receipt["checks"]] == [
        "non_live",
        "non_live",
        "non_live",
        "non_live",
        "static_only",
        "static_only",
    ]
    assert [row["script_sha256"] for row in receipt["checks"]] == [
        hashlib.sha256((fixture["repository"] / "scripts" / name).read_bytes()).hexdigest()
        for name in SMOKE_SCRIPTS
    ]
    serialized = json.dumps(payload) + receipts[0].read_text(encoding="utf-8")
    assert "leak-from-child" not in serialized
    assert "secret stderr" not in serialized
    assert str(fixture["repository"]) not in serialized
    assert str(fixture["receipt_root"]) not in serialized
    assert str(fixture["env_file"]) not in serialized


def test_receipt_temp_writer_creates_exclusive_unique_files(tmp_path: Path) -> None:
    final_path = tmp_path / "owner-ready-smoke-fixed.json"
    command = (
        "$tokens=$null;$parseErrors=$null;"
        "$ast=[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:OWNER_READY_SCRIPT,[ref]$tokens,[ref]$parseErrors);"
        "if($parseErrors.Count -ne 0){exit 10};"
        "$writer=$ast.Find({param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -ceq 'Write-ExclusiveReceiptTempFile'},$true);"
        "if($null -eq $writer){exit 11};"
        "Invoke-Expression $writer.Extent.Text;"
        "$first=Write-ExclusiveReceiptTempFile -FinalPath $env:OWNER_READY_FINAL_PATH -Content 'first';"
        "$second=Write-ExclusiveReceiptTempFile -FinalPath $env:OWNER_READY_FINAL_PATH -Content 'second';"
        "[pscustomobject]@{first=$first;second=$second;"
        "first_text=[IO.File]::ReadAllText($first);second_text=[IO.File]::ReadAllText($second)}"
        "|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "OWNER_READY_SCRIPT": str(SCRIPT),
            "OWNER_READY_FINAL_PATH": str(final_path),
        },
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["first"] != payload["second"]
    assert payload["first_text"] == "first"
    assert payload["second_text"] == "second"
    assert Path(payload["first"]).name.endswith(".tmp")
    assert Path(payload["second"]).name.endswith(".tmp")


def test_receipt_temp_writer_removes_partial_file_after_write_failure(tmp_path: Path) -> None:
    final_path = tmp_path / "owner-ready-smoke-fixed.json"
    command = (
        "$tokens=$null;$parseErrors=$null;"
        "$ast=[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:OWNER_READY_SCRIPT,[ref]$tokens,[ref]$parseErrors);"
        "if($parseErrors.Count -ne 0){exit 10};"
        "$writer=$ast.Find({param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -ceq 'Write-ExclusiveReceiptTempFile'},$true);"
        "if($null -eq $writer){exit 11};"
        "$instrumented=$writer.Extent.Text.Replace("
        "'$stream.Flush($true)',"
        "\"throw [IO.IOException]::new('fixture write failure')\");"
        "if($instrumented -ceq $writer.Extent.Text){exit 12};"
        "Invoke-Expression $instrumented;"
        "try { Write-ExclusiveReceiptTempFile "
        "-FinalPath $env:OWNER_READY_FINAL_PATH -Content 'partial' | Out-Null } catch {};"
        "@([IO.Directory]::GetFiles([IO.Path]::GetDirectoryName($env:OWNER_READY_FINAL_PATH),'*.tmp')).Count"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "OWNER_READY_SCRIPT": str(SCRIPT),
            "OWNER_READY_FINAL_PATH": str(final_path),
        },
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


def test_smoke_dashboard_accepts_only_an_unfollowed_same_loopback_login_redirect(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    requests: list[str] = []
    with _health_server(redirect=True, request_log=requests) as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["dashboard_status"] == "ready"
    assert payload["readiness_status"] == "local_ready"
    assert requests == ["/"]
    source = fixture["script"].read_text(encoding="utf-8-sig")
    assert "$handler.AllowAutoRedirect = $false" in source
    assert "$handler.UseProxy = $false" in source


@pytest.mark.parametrize(
    "redirect_location",
    [
        "http://localhost:{port}/login",
        "https://example.com/login",
    ],
    ids=["cross_host", "external_host"],
)
def test_smoke_dashboard_rejects_cross_host_redirect_without_following(
    tmp_path: Path,
    redirect_location: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    requests: list[str] = []
    with _health_server(
        redirect=True,
        redirect_location=redirect_location,
        request_log=requests,
    ) as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["dashboard_status"] == "invalid"
    assert payload["readiness_status"] == "not_ready"
    assert payload["external_network_calls"] == 0
    assert requests == ["/"]


def test_smoke_dashboard_rejects_cross_port_redirect_without_contacting_target(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    target_requests: list[str] = []
    with _health_server(request_log=target_requests) as target_uri:
        with _health_server(
            redirect=True,
            redirect_location=f"{target_uri}login",
        ) as hermes_uri:
            result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["dashboard_status"] == "invalid"
    assert payload["readiness_status"] == "not_ready"
    assert target_requests == []


@pytest.mark.parametrize(
    "status,body,omit_content_length",
    [
        (503, b"unavailable", False),
        (200, b"x" * 65537, False),
        (200, b"x" * 65537, True),
    ],
    ids=["other_status", "declared_oversize", "streamed_oversize"],
)
def test_smoke_dashboard_fails_closed_on_other_status_or_oversize_body(
    tmp_path: Path,
    status: int,
    body: bytes,
    omit_content_length: bool,
) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server(
        status=status,
        body=body,
        omit_content_length=omit_content_length,
    ) as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["dashboard_status"] == "invalid"
    assert payload["readiness_status"] == "not_ready"


def test_smoke_dashboard_connection_refused_is_not_running(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(fixture, mode="Smoke", timeout_sec=10)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["dashboard_status"] == "not_running"
    assert payload["credential_status"] == "present_unverified"
    assert payload["readiness_status"] == "not_ready"


def test_smoke_stalled_dashboard_precedes_missing_credentials_as_invalid(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["env_file"].unlink()
    with _health_server(delay_seconds=2) as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            timeout_sec=1,
        )

    payload = _payload(result)
    receipt = json.loads(_smoke_receipt_text(fixture))
    assert result.returncode == 1
    assert payload["dashboard_status"] == "invalid"
    assert payload["credential_status"] == "missing"
    assert payload["readiness_status"] == "not_ready"
    assert payload["external_network_calls"] == 0
    assert receipt["dashboard_status"] == "invalid"
    assert receipt["readiness_status"] == "not_ready"


def test_smoke_rejects_external_dashboard_url_before_any_child_or_request(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    result = _run(fixture, mode="Smoke", hermes_uri="https://example.com/")

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["checks"] == [
        {
            "id": "network_boundary",
            "status": "fail",
            "summary": "로컬 주소 설정을 확인할 수 없습니다.",
            "action": "VideoBox와 Hermes 주소를 127.0.0.1의 기본 주소로 되돌린 뒤 다시 확인하세요.",
            "evidence": {"external_request_count": 0},
        }
    ]
    assert not fixture["smoke_log"].exists()
    assert not fixture["receipt_root"].exists()
    assert not fixture["command_log"].exists()


@pytest.mark.parametrize("missing_key", REQUIRED_CREDENTIAL_KEYS)
def test_smoke_credential_classifier_rejects_each_missing_required_key(
    tmp_path: Path,
    missing_key: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    lines = fixture["env_file"].read_text(encoding="utf-8").splitlines()
    fixture["env_file"].write_text(
        "\n".join(line for line in lines if not line.startswith(f"{missing_key}=")) + "\n",
        encoding="utf-8",
    )
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["dashboard_status"] == "ready"
    assert payload["credential_status"] == "invalid"
    assert payload["readiness_status"] == "credential_blocked"


@pytest.mark.parametrize(
    "replacement",
    [
        "HERMES_YUJIN_GATEWAY_PASSWORD=safe-first\nHERMES_YUJIN_GATEWAY_PASSWORD=safe-second",
        "HERMES_YUJIN_GATEWAY_PASSWORD=",
        "HERMES_YUJIN_GATEWAY_PASSWORD=\"   \"",
        "HERMES_YUJIN_GATEWAY_PASSWORD=\"",
        'HERMES_YUJIN_GATEWAY_PASSWORD=abc"def',
        'HERMES_YUJIN_GATEWAY_PASSWORD="abc"def"',
        "HERMES_YUJIN_GATEWAY_PASSWORD=abc'def",
        "HERMES_YUJIN_GATEWAY_PASSWORD='abc'def'",
        "HERMES_YUJIN_GATEWAY_PASSWORD=\"abc'def\"",
        "HERMES_YUJIN_GATEWAY_PASSWORD='abc\"def'",
        "HERMES_YUJIN_GATEWAY_PASSWORD= # resolves empty",
        "HERMES_YUJIN_GATEWAY_PASSWORD=$NAME",
        'HERMES_YUJIN_GATEWAY_PASSWORD="$NAME"',
        "HERMES_YUJIN_GATEWAY_PASSWORD=${NAME}",
        'HERMES_YUJIN_GATEWAY_PASSWORD="${NAME}"',
        "HERMES_YUJIN_GATEWAY_PASSWORD=${UNFINISHED",
        'HERMES_YUJIN_GATEWAY_PASSWORD="${UNFINISHED"',
        "HERMES_YUJIN_GATEWAY_PASSWORD=abc\x00def",
        "HERMES_YUJIN_GATEWAY_PASSWORD=abc\tdef",
        "HERMES_YUJIN_GATEWAY_PASSWORD=abc\u0085def",
        "HERMES_YUJIN_GATEWAY_PASSWORD=${UNRESOLVED_SECRET}",
        "HERMES_YUJIN_GATEWAY_PASSWORD=REPLACE-BEFORE-STARTING",
        "HERMES_YUJIN_GATEWAY_PASSWORD=replace_before_starting",
        "HERMES_YUJIN_GATEWAY_PASSWORD=prefix_replace_me_suffix",
        "HERMES_YUJIN_GATEWAY_PASSWORD=Placeholder",
        "HERMES_YUJIN_GATEWAY_PASSWORD=change-me",
        "HERMES_YUJIN_GATEWAY_PASSWORD=change_me",
        "HERMES_YUJIN_GATEWAY_PASSWORD=ChangeMe",
        "HERMES_YUJIN_GATEWAY_PASSWORD=sentinel",
    ],
    ids=[
        "duplicate",
        "blank",
        "quoted_blank",
        "unmatched_quote",
        "embedded_double_unquoted",
        "embedded_double_wrapped",
        "embedded_single_unquoted",
        "embedded_single_wrapped",
        "mixed_single_inside_double",
        "mixed_double_inside_single",
        "inline_comment_empty",
        "unquoted_dollar_name",
        "double_quoted_dollar_name",
        "unquoted_closed_brace_interpolation",
        "double_quoted_closed_brace_interpolation",
        "unquoted_unfinished_brace_interpolation",
        "double_quoted_unfinished_brace_interpolation",
        "nul_control",
        "tab_control",
        "c1_control",
        "unresolved",
        "replace_before_starting",
        "replace_before_starting_underscore",
        "replace_me",
        "placeholder",
        "change_me_hyphen",
        "change_me_underscore",
        "changeme",
        "sentinel",
    ],
)
def test_smoke_credential_classifier_fails_closed_without_value_disclosure(
    tmp_path: Path,
    replacement: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    _replace_env_value(fixture, "HERMES_YUJIN_GATEWAY_PASSWORD", replacement)
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    receipt_text = _smoke_receipt_text(fixture)
    serialized = result.stdout + result.stderr + receipt_text
    assert result.returncode == 2
    assert payload["credential_status"] == "invalid"
    assert payload["readiness_status"] == "credential_blocked"
    assert str(fixture["env_file"]) not in serialized
    for fragment in replacement.splitlines():
        assert fragment not in serialized


@pytest.mark.parametrize(
    "replacement",
    [
        'HERMES_YUJIN_GATEWAY_PASSWORD="ordinary-quoted"',
        "HERMES_YUJIN_GATEWAY_PASSWORD='ordinary-quoted'",
        'HERMES_YUJIN_GATEWAY_PASSWORD="hash#inside" # outside comment',
        "HERMES_YUJIN_GATEWAY_PASSWORD=plain#literal",
        "HERMES_YUJIN_GATEWAY_PASSWORD=ordinary-literal # placeholder",
        "HERMES_YUJIN_GATEWAY_PASSWORD='$NAME'",
        "HERMES_YUJIN_GATEWAY_PASSWORD='${NAME}'",
        "HERMES_YUJIN_GATEWAY_PASSWORD='${UNFINISHED'",
        "HERMES_YUJIN_GATEWAY_PASSWORD='bcrypt-$2b$12$abcdefghijklmnopqrstuv'",
        "HERMES_YUJIN_GATEWAY_PASSWORD=$$NAME",
        'HERMES_YUJIN_GATEWAY_PASSWORD="$$NAME"',
    ],
    ids=[
        "double_quoted",
        "single_quoted",
        "quoted_hash_with_comment",
        "unquoted_hash_literal",
        "unquoted_comment_stripped",
        "single_quoted_dollar_name",
        "single_quoted_closed_brace_literal",
        "single_quoted_unfinished_brace_literal",
        "single_quoted_bcrypt_literal",
        "unquoted_escaped_dollar",
        "double_quoted_escaped_dollar",
    ],
)
def test_smoke_credential_classifier_accepts_safe_literal_and_comment_forms(
    tmp_path: Path,
    replacement: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    _replace_env_value(fixture, "HERMES_YUJIN_GATEWAY_PASSWORD", replacement)
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    serialized = result.stdout + result.stderr + _smoke_receipt_text(fixture)
    assert result.returncode == 0, result.stderr
    assert payload["credential_status"] == "present_unverified"
    assert payload["readiness_status"] == "local_ready"
    assert replacement not in serialized


@pytest.mark.parametrize(
    "bom,encoding",
    [
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
    ],
    ids=["utf16_le", "utf16_be", "utf32_le", "utf32_be"],
)
def test_smoke_credential_classifier_rejects_non_utf8_bom_encodings(
    tmp_path: Path,
    bom: bytes,
    encoding: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    env_text = _valid_env_text(fixture["data_root"])
    fixture["env_file"].write_bytes(bom + env_text.encode(encoding))
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    serialized = result.stdout + result.stderr + _smoke_receipt_text(fixture)
    assert result.returncode == 2
    assert payload["credential_status"] == "invalid"
    assert payload["readiness_status"] == "credential_blocked"
    assert str(fixture["env_file"]) not in serialized


def test_smoke_credential_classifier_accepts_strict_utf8_bom(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    env_text = _valid_env_text(fixture["data_root"])
    fixture["env_file"].write_bytes(codecs.BOM_UTF8 + env_text.encode("utf-8"))
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["credential_status"] == "present_unverified"
    assert payload["readiness_status"] == "local_ready"


def test_smoke_credential_classifier_ignores_optional_mem0_key(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with fixture["env_file"].open("a", encoding="utf-8") as env_file:
        env_file.write("MEM0_API_KEY=placeholder\n")
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["credential_status"] == "present_unverified"
    assert payload["readiness_status"] == "local_ready"
    assert "MEM0_API_KEY" not in result.stdout


def test_smoke_credential_classifier_rejects_oversize_env_without_leaking_it(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    canary = "ENV_OVERSIZE_SECRET_CANARY"
    fixture["env_file"].write_text(canary + ("x" * 70000), encoding="utf-8")
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    receipt_text = _smoke_receipt_text(fixture)
    serialized = result.stdout + result.stderr + receipt_text
    assert result.returncode == 2
    assert payload["credential_status"] == "invalid"
    assert payload["readiness_status"] == "credential_blocked"
    assert canary not in serialized
    assert str(fixture["env_file"]) not in serialized


def test_smoke_credential_classifier_maps_read_failure_to_invalid_without_details(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _exclusive_file_lock(fixture["env_file"]), _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    receipt_text = _smoke_receipt_text(fixture)
    serialized = result.stdout + result.stderr + receipt_text
    assert result.returncode == 2
    assert payload["credential_status"] == "invalid"
    assert payload["readiness_status"] == "credential_blocked"
    assert str(fixture["env_file"]) not in serialized
    assert "sharing violation" not in serialized.lower()
    assert "being used by another process" not in serialized.lower()


def test_smoke_credential_values_and_metadata_never_leave_process(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    secrets = [f"private-canary-{index}" for index in range(len(REQUIRED_CREDENTIAL_KEYS))]
    lines = fixture["env_file"].read_text(encoding="utf-8").splitlines()
    values = dict(zip(REQUIRED_CREDENTIAL_KEYS, secrets, strict=True))
    fixture["env_file"].write_text(
        "\n".join(
            f"{key}='{values[key]}'" if key in values else line
            for line in lines
            for key in [line.split("=", 1)[0]]
        )
        + "\n",
        encoding="utf-8",
    )
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    receipt_text = _smoke_receipt_text(fixture)
    serialized = result.stdout + result.stderr + receipt_text
    assert result.returncode == 0, result.stderr
    assert payload["credential_status"] == "present_unverified"
    assert payload["readiness_status"] == "local_ready"
    assert str(fixture["env_file"]) not in serialized
    for key, secret in zip(REQUIRED_CREDENTIAL_KEYS, secrets, strict=True):
        assert key not in serialized
        assert secret not in serialized
    tool_calls = fixture["command_log"].read_text(encoding="utf-8").lower()
    assert "start-hermes-yujin" not in tool_calls
    assert "get-hermes-yujin-status" not in tool_calls
    assert "verify-hermes-yujin-zero-tools" not in tool_calls
    assert "docker " not in tool_calls


@pytest.mark.parametrize(
    "mutation",
    ["missing", "malformed", "duplicate", "unknown", "nonzero_zero_call"],
)
def test_smoke_fails_closed_on_invalid_exact_marker_and_continues_all_gates(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            environment_patch={
                "FAKE_SMOKE_TARGET": "smoke-hermes-yujin-chat.ps1",
                "FAKE_SMOKE_MUTATION": mutation,
            },
        )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert payload["static_non_live_checks_passed"] is False
    assert [row["id"] for row in payload["checks"] if row["status"] == "fail"] == [
        "chat_non_live"
    ]
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 6
    receipt = json.loads(next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8"))
    failed = [row for row in receipt["checks"] if row["status"] == "fail"]
    assert len(failed) == 1
    assert failed[0]["marker"] == "invalid"


def test_smoke_readiness_priority_is_fail_closed_and_never_live_ready(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)

    fixture["env_file"].unlink()
    with _health_server() as hermes_uri:
        missing_env = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)
    missing_payload = _payload(missing_env)
    assert missing_env.returncode == 2
    assert missing_payload["readiness_status"] == "credential_blocked"
    assert missing_payload["credential_status"] == "missing"
    assert missing_payload["dashboard_status"] == "ready"

    failed_gate = _run(
        fixture,
        mode="Smoke",
        environment_patch={"FAKE_SMOKE_FAIL": "smoke-hermes-yujin-chat.ps1"},
    )
    failed_payload = _payload(failed_gate)
    assert failed_gate.returncode == 1
    assert failed_payload["readiness_status"] == "not_ready"

    fixture["env_file"].write_text(_valid_env_text(fixture["data_root"]), encoding="utf-8")
    dashboard_off = _run(fixture, mode="Smoke", timeout_sec=10)
    dashboard_payload = _payload(dashboard_off)
    assert dashboard_off.returncode == 1
    assert dashboard_payload["readiness_status"] == "not_ready"
    assert dashboard_payload["dashboard_status"] == "not_running"
    assert dashboard_payload["credential_status"] == "present_unverified"

    source = fixture["script"].read_text(encoding="utf-8-sig")
    all_output = json.dumps(missing_payload) + json.dumps(failed_payload) + json.dumps(dashboard_payload)
    assert 'readiness_status = "live_ready"' not in source
    assert '"readiness_status": "live_ready"' not in all_output


@pytest.mark.parametrize("credential_case", ["missing", "invalid"])
def test_smoke_not_running_dashboard_with_blocked_credentials_is_credential_blocked(
    tmp_path: Path,
    credential_case: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    if credential_case == "missing":
        fixture["env_file"].unlink()
    else:
        _replace_env_value(
            fixture,
            "HERMES_YUJIN_GATEWAY_PASSWORD",
            "HERMES_YUJIN_GATEWAY_PASSWORD=placeholder",
        )

    result = _run(fixture, mode="Smoke", timeout_sec=10)

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["dashboard_status"] == "not_running"
    assert payload["credential_status"] == credential_case
    assert payload["readiness_status"] == "credential_blocked"


def test_smoke_malformed_dashboard_precedes_missing_credentials(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["env_file"].unlink()
    with _malformed_http_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["static_non_live_checks_passed"] is True
    assert payload["dashboard_status"] == "invalid"
    assert payload["credential_status"] == "missing"
    assert payload["readiness_status"] == "not_ready"


def test_smoke_missing_child_has_no_sha_and_remaining_gates_continue(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    (fixture["repository"] / "scripts" / SMOKE_SCRIPTS[0]).unlink()
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert [row["id"] for row in payload["checks"] if row["status"] == "fail"] == [
        "creator_flow_non_live"
    ]
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 5
    receipt = json.loads(next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["checks"][0]["script_sha256"] == "unavailable"
    assert all(row["status"] == "pass" for row in receipt["checks"][1:])


@pytest.mark.parametrize("git_guard", ["FAKE_DIRTY_CHILD", "FAKE_UNTRACKED_CHILD"])
def test_smoke_rejects_a_child_not_unchanged_from_head_and_continues_all_gates(
    tmp_path: Path,
    git_guard: str,
) -> None:
    fixture = _fixture_repository(tmp_path)
    child_name = "smoke-hermes-yujin-chat.ps1"
    child_path = fixture["repository"] / "scripts" / child_name
    child_path.write_text(
        child_path.read_text(encoding="utf-8-sig") + "# local working-tree edit\n",
        encoding="utf-8-sig",
    )
    relative_child = f"scripts/{child_name}"
    with _health_server() as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            environment_patch={git_guard: relative_child},
        )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert [row["id"] for row in payload["checks"] if row["status"] == "fail"] == [
        "chat_non_live"
    ]
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 6
    receipt_text = next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["checks"][1]["status"] == "fail"
    assert receipt["checks"][1]["marker"] == "invalid"
    assert receipt["checks"][1]["script_sha256"] == hashlib.sha256(child_path.read_bytes()).hexdigest()
    serialized = json.dumps(payload) + receipt_text
    assert str(fixture["repository"]) not in serialized
    assert str(child_path) not in serialized
    tool_calls = fixture["command_log"].read_text(encoding="utf-8").replace('"', "")
    assert f"git ls-files --error-unmatch -- {relative_child}" in tool_calls
    start_commit = "deadbeef00000000000000000000000000000000"
    assert f"git diff --quiet {start_commit} -- {relative_child}" in tool_calls


def test_smoke_rejects_a_child_that_mutates_itself_during_execution(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    child_name = "smoke-hermes-yujin-chat.ps1"
    child_path = fixture["repository"] / "scripts" / child_name
    start_sha = hashlib.sha256(child_path.read_bytes()).hexdigest()
    with _health_server() as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            environment_patch={"FAKE_SMOKE_SELF_MUTATE": child_name},
        )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert [row["id"] for row in payload["checks"] if row["status"] == "fail"] == [
        "chat_non_live"
    ]
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 6
    assert hashlib.sha256(child_path.read_bytes()).hexdigest() != start_sha
    receipt_text = next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["commit"] == "deadbeef00000000000000000000000000000000"
    assert receipt["checks"][1]["status"] == "fail"
    assert receipt["checks"][1]["script_sha256"] == start_sha
    serialized = json.dumps(payload) + receipt_text
    assert str(child_path) not in serialized


def test_smoke_rejects_head_change_during_execution_and_keeps_start_commit(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    target = SMOKE_SCRIPTS[0]
    with _health_server() as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            environment_patch={"FAKE_SMOKE_HEAD_MUTATE": target},
        )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert len(fixture["smoke_log"].read_text(encoding="utf-8-sig").splitlines()) == 6
    receipt_text = next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["commit"] == "deadbeef00000000000000000000000000000000"
    assert all(row["status"] == "fail" for row in receipt["checks"])
    serialized = json.dumps(payload) + receipt_text
    assert str(fixture["fake_head"]) not in serialized


def test_smoke_rechecks_provenance_after_temp_receipt_before_publish(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    with _health_server() as hermes_uri:
        result = _run(
            fixture,
            mode="Smoke",
            hermes_uri=hermes_uri,
            environment_patch={"FAKE_HEAD_MUTATE_AFTER_FINAL": "1"},
        )

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["readiness_status"] == "not_ready"
    assert int(fixture["fake_head_read_count"].read_text(encoding="ascii")) >= 3
    receipt_text = next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["commit"] == "deadbeef00000000000000000000000000000000"
    assert receipt["readiness_status"] == "not_ready"
    assert all(row["status"] == "fail" for row in receipt["checks"])
    serialized = json.dumps(payload) + receipt_text
    assert str(fixture["fake_head"]) not in serialized
    assert str(fixture["fake_head_read_count"]) not in serialized


def test_smoke_receipt_write_failure_is_not_reported_as_ready(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    fixture["receipt_root"].write_text("not-a-directory", encoding="utf-8")
    with _health_server() as hermes_uri:
        result = _run(fixture, mode="Smoke", hermes_uri=hermes_uri)

    payload = _payload(result)
    assert result.returncode == 1
    assert payload["overall_status"] == "fail"
    assert payload["readiness_status"] == "not_ready"
    receipt_check = next(row for row in payload["checks"] if row["id"] == "receipt")
    assert receipt_check["status"] == "fail"
    assert payload["receipt"] == {"written": False, "file_name": None}


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
    receipt = json.loads(next(fixture["receipt_root"].glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "videobox-hermes-readiness-v1"
    assert receipt["readiness_status"] == "not_ready"
    assert receipt["checks"][0]["marker"] == "invalid"
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
    assert receipt["readiness_status"] == "not_ready"
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


def test_yujin_memory_start_installs_profile_before_compose_up() -> None:
    """-WithYujinMemory 로 켜면 유진 프로필을 먼저 설치해야 한다.

    프로필이 없으면 컨테이너가 "Profile 'videobox-yujin' does not exist" 로
    즉시 종료하고, 게이트웨이까지 연쇄로 못 뜬다. 2026-08-08 실제로 재현했다.
    """
    source = SCRIPT.read_text(encoding="utf-8-sig")

    installer = source.find("install-hermes-yujin-profile.ps1")
    assert installer != -1, "owner-ready 가 유진 프로필 설치를 호출하지 않는다"

    compose_up = source.find('@("up", "-d")')
    assert compose_up != -1
    assert installer < compose_up, "프로필 설치는 compose up 보다 먼저여야 한다"

    guard = source.rfind("if ($WithYujinMemory)", 0, installer)
    assert guard != -1, "프로필 설치는 -WithYujinMemory 일 때만 실행해야 한다"


def test_the_rebuild_budget_fits_a_cold_image_build() -> None:
    """재빌드를 180초로 묶어 두면 **멀쩡한 빌드가 거짓 FAIL로 뜬다.**

    2026-08-20에 실제로 겪었다. 화면 코드를 고친 뒤 재빌드하니 09:33:34에 시작해
    09:36:35에 끝났다 -- **181초**, 제한시간 180초 바로 위다. 손으로 같은
    `docker compose build`를 돌리면 성공한다. 즉 빌드는 멀쩡했고 시계만 짧았다.

    화면 묶음을 처음부터 다시 만드는 빌드는 원래 분 단위다. 캐시가 살아 있을
    때만 빠르다. 그 두 경우를 같은 잣대로 재면 안 된다.

    거짓 FAIL이 더 나쁜 이유는 다음 사람이 **진짜 실패와 구분할 수 없기**
    때문이다 -- 이 저장소는 "FAIL이 뜨면 진짜 실패"를 전제로 검증을 쌓아 왔다.
    """
    script = SCRIPT.read_text(encoding="utf-8")
    rebuild_budget = re.search(
        r"rebuildResult = Invoke-CapturedProcess[^\n]*CommandTimeoutSec \(\[Math\]::Max\(\$TimeoutSec, (\d+)\)\)",
        script,
    )

    assert rebuild_budget is not None, "재빌드 제한시간을 찾지 못했다"
    assert int(rebuild_budget.group(1)) >= 900, (
        "재빌드 제한시간이 차가운 빌드보다 짧다. 실측 181초짜리 빌드가 180초 벽에 잘려 "
        "거짓 FAIL이 났다."
    )


def test_a_failed_rebuild_keeps_the_log_it_tells_the_owner_to_read() -> None:
    """실패 안내는 "Docker 빌드 로그를 확인하세요"인데 **로그를 아무 데도 안 남겼다.**

    2026-08-20에 재빌드가 실패했을 때 원인을 알아내려고 같은 명령을 손으로 다시
    돌려야 했다. 안내가 가리키는 것을 스스로 남기지 않으면 그 안내는 빈말이다.
    """
    script = SCRIPT.read_text(encoding="utf-8")
    start = script.index("$rebuildResult = Invoke-CapturedProcess")
    rebuild_block = script[start : script.index("-Evidence @{ rebuilt", start) + 400]

    assert "rebuild_log" in rebuild_block, (
        "재빌드가 실패해도 로그가 근거로 남지 않는다. 실패 원인을 다음 사람이 볼 수 있어야 한다."
    )
