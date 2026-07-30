from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "test-hermes-yujin-failure-drills.ps1"
TARGET = "videobox-hermes-yujin"
BACKEND_NODEIDS = [
    "tests/test_agent_gateway_hermes_rpc_client.py::test_expired_ticket_before_prompt_acceptance_is_refreshed_once",
    "tests/test_agent_gateway_hermes_rpc_client.py::test_connection_loss_after_prompt_acceptance_is_never_retried",
    "tests/test_hermes_run_store.py::test_run_events_are_atomic_ordered_and_restart_replayable",
    "tests/test_hermes_run_store.py::test_recovery_interrupts_orphans_once_without_provider_redispatch",
    "tests/test_hermes_run_service.py::test_closing_one_subscription_does_not_cancel_provider_run",
    "tests/test_api_hermes_conversation.py::test_startup_interrupts_orphan_without_gateway_dispatch",
    "tests/test_hermes_yujin_capability_lifecycle.py::test_sqlite_recover_interrupted_coordinated_restart_revokes_active_capabilities",
]
FRONTEND_FILES = [
    "src/features/editor/workbench/hermesSseClient.test.ts",
    "src/features/editor/workbench/editor-workbench-route.test.tsx",
]


def _write_cmd(path: Path, source: str) -> Path:
    path.write_text("@echo off\r\n" + source.replace("\n", "\r\n"), encoding="utf-8")
    return path


def _fake_logged_runner(tmp_path: Path, name: str, log_env: str) -> Path:
    return _write_cmd(
        tmp_path / f"{name}.cmd",
        f'echo %*>>"%{log_env}%"\nexit /b 0\n',
    )


def _fake_docker(tmp_path: Path) -> Path:
    return _write_cmd(
        tmp_path / "docker.cmd",
        'echo docker %*>>"%FAKE_EVENT_LOG%"\n'
        'echo %*>>"%FAKE_DOCKER_LOG%"\n'
        'set "FAKE_COMMAND="\n'
        "for %%A in (%*) do (\n"
        '  if "%%~A"=="stop" set "FAKE_COMMAND=stop"\n'
        ")\n"
        'if "%FAKE_COMMAND%"=="stop" exit /b %FAKE_STOP_EXIT%\n'
        'type "%FAKE_DOCKER_JSON%"\n'
        "echo password=raw-docker-secret 1>&2\n"
        "exit /b 0\n",
    )


def _fake_powershell(tmp_path: Path) -> Path:
    return _write_cmd(
        tmp_path / "child-powershell.cmd",
        'echo powershell %* >>"%FAKE_EVENT_LOG%"\n'
        'echo %*| findstr /i /c:"restart-hermes-yujin.ps1" >nul\n'
        "if not errorlevel 1 (\n"
        '  if not "%FAKE_RESTART_MARKER%"=="" echo %FAKE_RESTART_MARKER%\n'
        "  echo password=child-recovery-secret 1>&2\n"
        "  exit /b %FAKE_RESTART_EXIT%\n"
        ")\n"
        'echo %*| findstr /i /c:"smoke-hermes-yujin-chat.ps1" >nul\n'
        "if not errorlevel 1 exit /b %FAKE_SMOKE_EXIT%\n"
        "exit /b 91\n",
    )


def _append_event(path: Path, event: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(event + "\n")


def _handler(
    state: dict[str, Any],
    *,
    revision: int = 7,
    event_mode: str = "success",
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback
            state["calls"].append(("GET", self.path))
            if self.path == "/api/projects/project-a/editing-sessions/session-a":
                self._json(
                    200,
                    {
                        "project_id": "project-a",
                        "session_id": "session-a",
                        "session_revision": revision,
                        "private": "server-response-secret",
                    },
                )
                return
            if self.path.endswith("/hermes-runs/run-1/events"):
                state["event_get_count"] += 1
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()
                replay = state["event_get_count"] > 1
                prefix = "sse-replay" if replay else "sse"
                self._event("run_started", "", prefix)
                if event_mode == "missing_barrier":
                    self.close_connection = True
                    return
                if replay:
                    self._event("text_delta", "첫 공개 델타", prefix)
                    self._event("blocked", "", prefix)
                    self.close_connection = True
                    return
                if event_mode == "fast_complete":
                    self._event("run_completed", "", prefix)
                    self.close_connection = True
                    return
                self._event("text_delta", "첫 공개 델타", prefix)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    docker_log = state["docker_log"]
                    if docker_log.exists() and " stop " in (
                        " " + docker_log.read_text(encoding="utf-8") + " "
                    ):
                        break
                    time.sleep(0.02)
                else:
                    state["barrier_error"] = "stop_not_observed"
                if event_mode == "terminal_complete":
                    self._event("run_completed", "", prefix)
                else:
                    self._event("blocked", "", prefix)
                self.close_connection = True
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib callback
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            state["calls"].append(("POST", self.path))
            if self.path == "/api/projects/project-a/director/conversations":
                assert payload == {"session_id": "session-a"}
                self._json(201, {"conversation_id": "conversation-1"})
                return
            if self.path.endswith("/hermes-runs"):
                assert payload["session_id"] == "session-a"
                assert payload["expected_session_revision"] == 7
                assert payload["text"]
                self._json(
                    201,
                    {
                        "run_id": "run-1",
                        "conversation_id": "conversation-1",
                        "events_url": (
                            "/api/projects/project-a/director/conversations/"
                            "conversation-1/hermes-runs/run-1/events"
                        ),
                    },
                )
                return
            if self.path.endswith("/messages"):
                assert payload["text"]
                assert payload["session_id"] == "session-a"
                assert payload["client_message_id"]
                state["manual_messages"] += 1
                _append_event(state["event_log"], "api manual-message")
                self._json(200, {"message_id": "manual-1"})
                return
            self.send_error(404)

        def _event(self, event_type: str, text: str, prefix: str) -> None:
            _append_event(state["event_log"], f"{prefix} {event_type}")
            payload = json.dumps(
                {"event_type": event_type, "text": text},
                ensure_ascii=False,
            )
            wire = f"event: {event_type}\ndata: {payload}\n\n".encode()
            try:
                self.wfile.write(wire)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _start_server(
    tmp_path: Path,
    *,
    revision: int = 7,
    event_mode: str = "success",
) -> tuple[ThreadingHTTPServer, threading.Thread, dict[str, Any]]:
    state: dict[str, Any] = {
        "calls": [],
        "manual_messages": 0,
        "event_get_count": 0,
        "docker_log": tmp_path / "docker.log",
        "event_log": tmp_path / "events.log",
    }
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler(state, revision=revision, event_mode=event_mode),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker, state


def _run(
    tmp_path: Path,
    *arguments: str,
    server_port: int | None = None,
    docker_health: str = "healthy",
    docker_id: str = "container-1",
    stop_exit: int = 0,
    restart_exit: int = 0,
    restart_marker: str = "",
    smoke_exit: int = 0,
    env_source: str = "VIDEOBOX_TEST_ONLY=1\n",
) -> tuple[subprocess.CompletedProcess[str], dict[str, Path]]:
    env_file = tmp_path / "approved.env"
    env_file.write_text(env_source, encoding="utf-8")
    docker_json = tmp_path / "docker.json"
    docker_json.write_text(
        json.dumps(
            [
                {
                    "Service": TARGET,
                    "State": "running",
                    "Health": docker_health,
                    "ID": docker_id,
                }
            ]
        ),
        encoding="utf-8",
    )
    paths = {
        "event_log": tmp_path / "events.log",
        "docker_log": tmp_path / "docker.log",
        "python_log": tmp_path / "python.log",
        "npm_log": tmp_path / "npm.log",
    }
    environment = {
        **os.environ,
        "FAKE_EVENT_LOG": str(paths["event_log"]),
        "FAKE_DOCKER_LOG": str(paths["docker_log"]),
        "FAKE_DOCKER_JSON": str(docker_json),
        "FAKE_STOP_EXIT": str(stop_exit),
        "FAKE_RESTART_EXIT": str(restart_exit),
        "FAKE_RESTART_MARKER": restart_marker,
        "FAKE_SMOKE_EXIT": str(smoke_exit),
        "FAKE_PYTHON_LOG": str(paths["python_log"]),
        "FAKE_NPM_LOG": str(paths["npm_log"]),
    }
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
        "-PythonExecutable",
        str(_fake_logged_runner(tmp_path, "python", "FAKE_PYTHON_LOG")),
        "-NpmExecutable",
        str(_fake_logged_runner(tmp_path, "npm", "FAKE_NPM_LOG")),
        "-PowerShellExecutable",
        str(_fake_powershell(tmp_path)),
        "-TimeoutSec",
        "3",
        *arguments,
    ]
    if server_port is not None:
        command.extend(
            [
                "-BaseUri",
                f"http://127.0.0.1:{server_port}",
                "-ProjectId",
                "project-a",
                "-SessionId",
                "session-a",
                "-ExpectedSessionRevision",
                "7",
            ]
        )
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return result, paths


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _live_arguments() -> tuple[str, ...]:
    return (
        "-Live",
        "-ConfirmServiceStop",
        "-ConfirmConversationWrite",
        "-ConfirmDisposableProject",
    )


def test_static_only_runs_exact_bounded_regression_owners(tmp_path: Path) -> None:
    result, paths = _run(tmp_path, "-StaticOnly")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "HERMES_YUJIN_FAILURE_DRILLS_STATIC_PASS "
        "backend_nodes=7 frontend_files=2 docker_calls=0 "
        "network_calls=0 provider_calls=0"
    )
    assert _lines(paths["python_log"]) == ["-m pytest -q " + " ".join(BACKEND_NODEIDS)]
    assert _lines(paths["npm_log"]) == [
        "--prefix apps/web test -- --run " + " ".join(FRONTEND_FILES)
    ]
    assert _lines(paths["docker_log"]) == []
    source = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in (
        '"down"',
        '"rm"',
        '"remove"',
        '"kill"',
        '"prune"',
        '"--volumes"',
        '"--force-recreate"',
        '"up"',
        '"recreate"',
    ):
        assert forbidden not in source
    assert source.count("$handler.useproxy = $false") == 2
    assert "invoke-webrequest" not in source


def test_live_gate_failure_is_pure_and_fixed(tmp_path: Path) -> None:
    result, paths = _run(tmp_path, "-Live")

    assert result.returncode != 0
    assert "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:confirmation_required" in result.stderr
    assert _lines(paths["docker_log"]) == []
    assert _lines(paths["event_log"]) == []
    assert "raw-docker-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "env_source",
    [
        "GOOD=1\nGOOD=2\n",
        "1INVALID=value\n",
        "GOOD=\"unterminated\n",
        "GOOD=replace-before-starting\n",
        "GOOD value\n",
    ],
)
def test_stage_a_rejects_invalid_env_syntax_before_any_io(
    tmp_path: Path,
    env_source: str,
) -> None:
    result, paths = _run(
        tmp_path,
        *_live_arguments(),
        "-ProjectId",
        "project-a",
        "-SessionId",
        "session-a",
        "-ExpectedSessionRevision",
        "7",
        env_source=env_source,
    )

    assert result.returncode != 0
    assert (
        "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:environment_not_approved"
        in result.stderr
    )
    assert _lines(paths["docker_log"]) == []
    assert _lines(paths["event_log"]) == []


def test_read_only_preflight_mismatch_has_no_mutation_or_write(tmp_path: Path) -> None:
    server, worker, state = _start_server(tmp_path, revision=8)
    try:
        result, paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert "HERMES_YUJIN_FAILURE_DRILL_PREFLIGHT_FAILED:session_mismatch" in result.stderr
    assert (
        "docker_reads=1 api_reads=1 docker_mutations=0 conversation_writes=0"
        in " ".join(result.stderr.split())
    )
    assert state["calls"] == [
        ("GET", "/api/projects/project-a/editing-sessions/session-a")
    ]
    assert not any(" stop " in f" {call} " for call in _lines(paths["docker_log"]))
    assert state["manual_messages"] == 0
    assert "server-response-secret" not in result.stdout + result.stderr
    assert "raw-docker-secret" not in result.stdout + result.stderr


def test_fast_complete_without_public_delta_is_unrun(tmp_path: Path) -> None:
    server, worker, state = _start_server(tmp_path, event_mode="fast_complete")
    try:
        result, paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert "HERMES_YUJIN_FAILURE_DRILL_UNRUN:fast_complete" in result.stderr
    assert not any(" stop " in f" {call} " for call in _lines(paths["docker_log"]))
    assert state["manual_messages"] == 0
    assert not any("powershell " in line for line in _lines(paths["event_log"]))


def test_missing_provider_active_barrier_is_unrun(tmp_path: Path) -> None:
    server, worker, state = _start_server(tmp_path, event_mode="missing_barrier")
    try:
        result, paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert (
        "HERMES_YUJIN_FAILURE_DRILL_UNRUN:provider_active_barrier_missing"
        in result.stderr
    )
    assert not any(" stop " in f" {call} " for call in _lines(paths["docker_log"]))
    assert state["manual_messages"] == 0
    assert not any("powershell " in line for line in _lines(paths["event_log"]))


def test_live_success_stops_only_after_barrier_and_recovers_in_finally(
    tmp_path: Path,
) -> None:
    server, worker, state = _start_server(tmp_path)
    try:
        result, paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "HERMES_YUJIN_FAILURE_DRILL_LIVE_PASS "
        "simulation=stop_during_stream service=videobox-hermes-yujin "
        "terminal=blocked manual_director=true auto_apply_calls=0"
    )
    events = _lines(paths["event_log"])
    assert events.index("sse text_delta") < next(
        index for index, event in enumerate(events) if event.startswith("docker ") and " stop " in f" {event} "
    )
    assert events.index("sse blocked") < events.index("api manual-message")
    assert events.index("sse blocked") < events.index("sse-replay blocked")
    assert events.index("sse-replay blocked") < events.index("api manual-message")
    restart_index = next(
        index for index, event in enumerate(events) if "restart-hermes-yujin.ps1" in event
    )
    post_restart_health_index = next(
        index
        for index, event in enumerate(events[restart_index + 1 :], restart_index + 1)
        if event.startswith("docker ") and " --format json " in f" {event} "
    )
    smoke_index = next(
        index for index, event in enumerate(events) if "smoke-hermes-yujin-chat.ps1" in event
    )
    assert (
        events.index("api manual-message")
        < restart_index
        < post_restart_health_index
        < smoke_index
    )
    docker_calls = _lines(paths["docker_log"])
    stop_calls = [call for call in docker_calls if " stop " in f" {call} "]
    assert len(stop_calls) == 1
    assert stop_calls[0].split()[-1].strip('"') == TARGET
    assert state["manual_messages"] == 1
    assert state["calls"] == [
        ("GET", "/api/projects/project-a/editing-sessions/session-a"),
        ("POST", "/api/projects/project-a/director/conversations"),
        (
            "POST",
            "/api/projects/project-a/director/conversations/"
            "conversation-1/hermes-runs",
        ),
        (
            "GET",
            "/api/projects/project-a/director/conversations/"
            "conversation-1/hermes-runs/run-1/events",
        ),
        (
            "GET",
            "/api/projects/project-a/director/conversations/"
            "conversation-1/hermes-runs/run-1/events",
        ),
        (
            "POST",
            "/api/projects/project-a/director/conversations/"
            "conversation-1/messages",
        ),
    ]
    joined = "\n".join(f"{method} {path}" for method, path in state["calls"]).lower()
    assert "apply" not in joined


def test_stop_failure_still_runs_recovery_and_does_not_claim_success(
    tmp_path: Path,
) -> None:
    server, worker, state = _start_server(tmp_path)
    try:
        result, paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
            stop_exit=7,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert "HERMES_YUJIN_FAILURE_DRILL_FAILED:service_stop" in result.stderr
    assert "LIVE_PASS" not in result.stdout + result.stderr
    recovery_events = [
        event
        for event in _lines(paths["event_log"])
        if "restart-hermes-yujin.ps1" in event
        or "smoke-hermes-yujin-chat.ps1" in event
    ]
    assert len(recovery_events) == 2
    assert state["manual_messages"] == 0


@pytest.mark.parametrize(
    ("restart_marker", "restart_exit", "smoke_exit", "expected"),
    [
        (
            "HERMES_YUJIN_RESTART_FAILED:restart_command",
            9,
            0,
            "restart_command",
        ),
        (
            "HERMES_YUJIN_RESTART_FAILED:health_timeout",
            9,
            0,
            "health_timeout",
        ),
        (
            "HERMES_YUJIN_RESTART_FAILED:container_replaced",
            9,
            0,
            "container_identity",
        ),
        ("", 0, 9, "canary"),
    ],
)
def test_recovery_fatal_precedes_original_and_keeps_machine_reason(
    tmp_path: Path,
    restart_marker: str,
    restart_exit: int,
    smoke_exit: int,
    expected: str,
) -> None:
    server, worker, _state = _start_server(tmp_path, event_mode="terminal_complete")
    try:
        result, _paths = _run(
            tmp_path,
            *_live_arguments(),
            server_port=server.server_port,
            restart_exit=restart_exit,
            restart_marker=restart_marker,
            smoke_exit=smoke_exit,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert (
        f"HERMES_YUJIN_FAILURE_DRILL_RECOVERY_FATAL:{expected}"
        in result.stderr
    )
    assert "HERMES_YUJIN_FAILURE_DRILL_FAILED:terminal_after_stop" not in result.stderr
    assert "raw-docker-secret" not in result.stdout + result.stderr
    assert "server-response-secret" not in result.stdout + result.stderr
    assert "child-recovery-secret" not in result.stdout + result.stderr
