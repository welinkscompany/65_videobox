from __future__ import annotations

import json
import subprocess
import threading
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
            self.send_header("Content-Type", "text/event-stream")
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
