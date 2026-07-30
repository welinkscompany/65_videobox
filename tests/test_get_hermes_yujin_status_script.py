from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "get-hermes-yujin-status.ps1"
SERVICES = (
    "videobox-workspace",
    "videobox-agent-gateway",
    "videobox-hermes-yujin",
)


def _fake_docker(tmp_path: Path) -> Path:
    script = tmp_path / "docker.cmd"
    script.write_text(
        "@echo off\r\n"
        'echo %*>>"%FAKE_DOCKER_LOG%"\r\n'
        'type "%FAKE_DOCKER_PS%"\r\n'
        'powershell -NoProfile -Command "[Console]::Error.Write('
        "'password=leak-me ticket=secret-ticket'"
        ')"\r\n'
        "exit /b %FAKE_DOCKER_EXIT%\r\n",
        encoding="utf-8",
    )
    return script


def _run(
    tmp_path: Path,
    rows: list[dict[str, object]],
    *,
    ndjson: bool = False,
    exit_code: int = 0,
    missing_env: bool = False,
    status_api_uri: str | None = None,
    timeout_sec: int = 3,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    env_file = tmp_path / "container.env"
    if not missing_env:
        env_file.write_text("VIDEOBOX_TEST_ONLY=1\n", encoding="utf-8")
    docker_log = tmp_path / "docker.log"
    ps_file = tmp_path / "ps.json"
    if ndjson:
        ps_file.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
    else:
        ps_file.write_text(json.dumps(rows), encoding="utf-8")
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
        str(_fake_docker(tmp_path)),
        "-TimeoutSec",
        str(timeout_sec),
    ]
    if status_api_uri is not None:
        command.extend(["-StatusApiUri", status_api_uri])
    environment = {
        **os.environ,
        "FAKE_DOCKER_LOG": str(docker_log),
        "FAKE_DOCKER_PS": str(ps_file),
        "FAKE_DOCKER_EXIT": str(exit_code),
    }
    result = subprocess.run(
        command,
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
        docker_log.read_text(encoding="utf-8").splitlines()
        if docker_log.exists()
        else []
    )
    return result, calls


def _rows(
    *,
    state: str = "running",
    health: str = "healthy",
    include_yujin: bool = True,
) -> list[dict[str, object]]:
    return [
        {
            "Service": service,
            "State": state,
            "Health": health,
            "ExitCode": 0,
            "ID": f"secret-{service}",
            "Mounts": "oauth-secret-volume",
        }
        for service in SERVICES
        if include_yujin or service != "videobox-hermes-yujin"
    ]


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout)


def _application_status(**patch: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state": "chat_verified",
        "http_ready": True,
        "provider_ready": True,
        "chat_verified": True,
        "checked_at": "2026-07-30T12:00:00Z",
        "last_chat_verified_at": "2026-07-30T11:59:59Z",
        "restart_available": False,
        "status_basis": "application_path",
    }
    payload.update(patch)
    return payload


def _run_with_status_server(
    tmp_path: Path,
    *,
    payload: object | None = None,
    raw_body: bytes | None = None,
    status: int = 200,
    content_type: str = "application/json; charset=utf-8",
    delay_seconds: float = 0,
    redirect: bool = False,
    timeout_sec: int = 3,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            calls.append(self.path)
            if self.path == "/redirect-target":
                body = json.dumps(_application_status()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if redirect:
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.end_headers()
                return
            if delay_seconds:
                time.sleep(delay_seconds)
            body = raw_body
            if body is None:
                body = json.dumps(
                    payload if payload is not None else _application_status()
                ).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result, _docker_calls = _run(
            tmp_path,
            _rows(),
            status_api_uri=(
                f"http://127.0.0.1:{server.server_port}"
                "/api/hermes-yujin/status"
            ),
            timeout_sec=timeout_sec,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
    return result, calls


def test_missing_configuration_is_network_and_docker_free(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, [], missing_env=True)
    payload = _payload(result)

    assert payload["state"] == "not_configured"
    assert payload["status_basis"] == "docker_compose"
    assert calls == []
    assert [row["name"] for row in payload["services"]] == list(SERVICES)
    assert all(not row["present"] for row in payload["services"])


def test_default_env_path_is_resolved_after_script_startup(
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

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "not_configured"
    assert "Cannot bind argument to parameter 'Path'" not in result.stderr


def test_array_json_healthy_services_are_http_ready_and_sanitized(
    tmp_path: Path,
) -> None:
    result, calls = _run(tmp_path, _rows())
    payload = _payload(result)

    assert payload == {
        **payload,
        "schema_version": "v1",
        "state": "http_ready",
        "status_basis": "docker_compose",
        "http_ready": True,
        "provider_ready": False,
        "chat_verified": False,
        "last_chat_verified_at": None,
        "application_status_checked": False,
    }
    assert len(calls) == 1
    assert '"ps"' in calls[0]
    assert '"--all"' in calls[0]
    assert '"--format" "json"' in calls[0]
    output = result.stdout + result.stderr
    assert "secret-" not in output
    assert "oauth-secret-volume" not in output
    assert "leak-me" not in output
    assert "secret-ticket" not in output


def test_ndjson_absent_yujin_is_stopped(tmp_path: Path) -> None:
    result, _ = _run(
        tmp_path,
        _rows(include_yujin=False),
        ndjson=True,
    )
    payload = _payload(result)

    assert payload["state"] == "stopped"
    yujin = next(
        row
        for row in payload["services"]
        if row["name"] == "videobox-hermes-yujin"
    )
    assert yujin == {
        "name": "videobox-hermes-yujin",
        "present": False,
        "running": False,
        "health": "unknown",
        "exit_code": None,
    }


def test_running_unhealthy_service_is_starting(tmp_path: Path) -> None:
    rows = _rows()
    rows[-1]["Health"] = "starting"
    result, _ = _run(tmp_path, rows)

    assert _payload(result)["state"] == "starting"


def test_docker_failure_is_redacted_degraded_status(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, [], exit_code=9)
    payload = _payload(result)

    assert payload["state"] == "degraded"
    assert payload["http_ready"] is False
    assert len(calls) == 1
    assert "leak-me" not in result.stdout + result.stderr


def test_non_loopback_status_uri_is_rejected_before_docker(
    tmp_path: Path,
) -> None:
    result, calls = _run(
        tmp_path,
        _rows(),
        status_api_uri="https://example.com/api/hermes-yujin/status",
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_STATUS_FAILED:status_api_uri_invalid" in result.stderr
    assert calls == []


@pytest.mark.parametrize(
    "application_status",
    [
        _application_status(),
        _application_status(
            state="degraded",
            http_ready=False,
            provider_ready=False,
            chat_verified=False,
        ),
        _application_status(
            state="degraded",
            http_ready=True,
            provider_ready=False,
            chat_verified=False,
        ),
    ],
)
def test_application_status_happy_chat_and_degraded_states(
    tmp_path: Path,
    application_status: dict[str, object],
) -> None:
    result, calls = _run_with_status_server(
        tmp_path,
        payload=application_status,
    )
    payload = _payload(result)

    assert payload["state"] == application_status["state"]
    assert payload["http_ready"] is application_status["http_ready"]
    assert payload["provider_ready"] is application_status["provider_ready"]
    assert payload["chat_verified"] is application_status["chat_verified"]
    assert payload["last_chat_verified_at"] == (
        application_status["last_chat_verified_at"]
    )
    assert payload["application_status_checked"] is True
    assert calls == ["/api/hermes-yujin/status"]


@pytest.mark.parametrize(
    "application_status",
    [
        _application_status(checked_at="2026-02-30T12:00:00Z"),
        _application_status(
            checked_at="2026-07-30T12:00:00Z",
            last_chat_verified_at="2026-07-30T12:00:01Z",
        ),
        _application_status(
            state="provider_ready",
            http_ready=True,
            provider_ready=False,
            chat_verified=False,
        ),
        _application_status(
            state="degraded",
            provider_ready=True,
            chat_verified=False,
        ),
        {**_application_status(), "private_detail": "SECRET"},
    ],
)
def test_malformed_application_status_is_sanitized_degraded(
    tmp_path: Path,
    application_status: dict[str, object],
) -> None:
    result, _calls = _run_with_status_server(
        tmp_path,
        payload=application_status,
    )
    payload = _payload(result)

    assert payload["state"] == "degraded"
    assert payload["http_ready"] is True
    assert payload["provider_ready"] is False
    assert payload["chat_verified"] is False
    assert "SECRET" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("options", "expected_calls"),
    [
        ({"redirect": True}, ["/api/hermes-yujin/status"]),
        ({"content_type": "application/jsonx"}, ["/api/hermes-yujin/status"]),
        ({"raw_body": b"x" * 16385}, ["/api/hermes-yujin/status"]),
        (
            {"delay_seconds": 2, "timeout_sec": 1},
            ["/api/hermes-yujin/status"],
        ),
    ],
)
def test_application_status_transport_failures_are_bounded_and_sanitized(
    tmp_path: Path,
    options: dict[str, object],
    expected_calls: list[str],
) -> None:
    result, calls = _run_with_status_server(tmp_path, **options)
    payload = _payload(result)

    assert payload["state"] == "degraded"
    assert payload["application_status_checked"] is True
    assert calls == expected_calls


def test_status_api_uses_streaming_bounded_no_proxy_http_client() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert ".WaitForExit()" not in source
    assert ".WaitForExit($TimeoutSec * 1000)" in source
    assert "ReadAsStringAsync" not in source
    assert "ResponseHeadersRead" in source
    assert "ReadAsStreamAsync" in source
    assert "$handler.UseProxy = $false" in source
    assert "$handler.AllowAutoRedirect = $false" in source
    assert "16384" in source
