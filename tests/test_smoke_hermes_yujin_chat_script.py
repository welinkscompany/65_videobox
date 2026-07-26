from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-hermes-yujin-chat.ps1"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _canary_handler(
    calls: list[tuple[str, str]],
    *,
    events_content_type: str = "text/event-stream; charset=utf-8",
    redirect_conversation: bool = False,
    events_delay_seconds: float = 0,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            calls.append(("POST", self.path))
            if self.path == "/api/projects/project-a/director/conversations":
                if redirect_conversation:
                    self.send_response(302)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                    return
                assert body == {"session_id": "session-a"}
                self._json(201, {"conversation_id": "conversation-1"})
                return
            if self.path == "/api/projects/project-a/director/conversations/conversation-1/hermes-runs":
                assert body["session_id"] == "session-a"
                assert body["text"] == "이 연결이 준비되었는지 짧게 알려 주세요."
                self._json(
                    201,
                    {
                        "run_id": "run-1",
                        "conversation_id": "conversation-1",
                        "events_url": "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events",
                    },
                )
                return
            self.send_error(404)

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            calls.append(("GET", self.path))
            if self.path == "/redirect-target":
                self._json(200, {"conversation_id": "redirected"})
                return
            if self.path != "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events":
                self.send_error(404)
                return
            if events_delay_seconds:
                time.sleep(events_delay_seconds)
            wire = (
                'id: 1\nevent: run_started\ndata: {"event_id":1,"event_type":"run_started","text":"","retryable":false}\n\n'
                'id: 2\nevent: text_delta\ndata: {"event_id":2,"event_type":"text_delta","text":"준비됨","retryable":false}\n\n'
                'id: 3\nevent: run_completed\ndata: {"event_id":3,"event_type":"run_completed","text":"준비됨","retryable":false}\n\n'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", events_content_type)
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            try:
                self.wfile.write(wire)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _json(self, status: int, payload: dict[str, str]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _run_with_server(
    handler: type[BaseHTTPRequestHandler],
    *arguments: str,
    base_path: str = "",
) -> subprocess.CompletedProcess[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        return _run(
            "-Live",
            "-BaseUri",
            f"http://127.0.0.1:{server.server_port}{base_path}",
            "-ProjectId",
            "project-a",
            "-SessionId",
            "session-a",
            *arguments,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_non_live_canary_is_network_free() -> None:
    result = _run()

    assert result.returncode == 0
    assert "network_calls=0" in result.stdout
    assert "proposal_calls=0" in result.stdout
    assert "provider_body_recorded=false" in result.stdout


def test_live_command_surface_is_windows_powershell_compatible_and_api_only() -> None:
    calls: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            calls.append(("POST", self.path))
            if self.path == "/api/projects/project-a/director/conversations":
                assert body == {"session_id": "session-a"}
                self._json(201, {"conversation_id": "conversation-1"})
                return
            if self.path == "/api/projects/project-a/director/conversations/conversation-1/hermes-runs":
                assert body["session_id"] == "session-a"
                assert body["text"] == "이 연결이 준비되었는지 짧게 알려 주세요."
                self._json(
                    201,
                    {
                        "run_id": "run-1",
                        "conversation_id": "conversation-1",
                        "events_url": "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events",
                    },
                )
                return
            self.send_error(404)

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            calls.append(("GET", self.path))
            if self.path != "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events":
                self.send_error(404)
                return
            wire = (
                'id: 1\nevent: run_started\ndata: {"event_id":1,"event_type":"run_started","text":"","retryable":false}\n\n'
                'id: 2\nevent: text_delta\ndata: {"event_id":2,"event_type":"text_delta","text":"준비됨","retryable":false}\n\n'
                'id: 3\nevent: run_completed\ndata: {"event_id":3,"event_type":"run_completed","text":"준비됨","retryable":false}\n\n'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)

        def _json(self, status: int, payload: dict[str, str]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        result = _run(
            "-Live",
            "-BaseUri",
            f"http://127.0.0.1:{server.server_port}",
            "-ProjectId",
            "project-a",
            "-SessionId",
            "session-a",
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode == 0, result.stderr
    assert "HERMES_YUJIN_CANARY_LIVE_PASS" in result.stdout
    assert "network_calls=3" in result.stdout
    assert "proposal_calls=0" in result.stdout
    assert "provider_body_recorded=false" in result.stdout
    assert calls == [
        ("POST", "/api/projects/project-a/director/conversations"),
        ("POST", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs"),
        ("GET", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events"),
    ]


def test_live_canary_denies_redirects_without_following_them() -> None:
    calls: list[tuple[str, str]] = []
    result = _run_with_server(
        _canary_handler(calls, redirect_conversation=True),
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_CANARY_FAILED:conversation_create_request" in result.stderr
    assert "redirected" not in result.stdout + result.stderr
    assert calls == [("POST", "/api/projects/project-a/director/conversations")]


def test_live_canary_rejects_a_content_type_prefix_collision() -> None:
    calls: list[tuple[str, str]] = []
    result = _run_with_server(
        _canary_handler(calls, events_content_type="text/event-streamx"),
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_CANARY_FAILED:events_content_type" in result.stderr
    assert "준비됨" not in result.stdout + result.stderr
    assert calls == [
        ("POST", "/api/projects/project-a/director/conversations"),
        ("POST", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs"),
        ("GET", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events"),
    ]


def test_live_canary_bounds_every_request_and_sse_read_with_timeout_sec() -> None:
    calls: list[tuple[str, str]] = []
    result = _run_with_server(
        _canary_handler(calls, events_delay_seconds=2),
        "-TimeoutSec",
        "1",
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_CANARY_FAILED:events_request" in result.stderr
    assert "준비됨" not in result.stdout + result.stderr
    assert calls == [
        ("POST", "/api/projects/project-a/director/conversations"),
        ("POST", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs"),
        ("GET", "/api/projects/project-a/director/conversations/conversation-1/hermes-runs/run-1/events"),
    ]


def test_live_canary_rejects_a_base_uri_path_before_network() -> None:
    calls: list[tuple[str, str]] = []
    result = _run_with_server(
        _canary_handler(calls),
        base_path="/unexpected-prefix",
    )

    assert result.returncode != 0
    assert "HERMES_YUJIN_CANARY_FAILED:base_uri_shape_invalid" in result.stderr
    assert calls == []
