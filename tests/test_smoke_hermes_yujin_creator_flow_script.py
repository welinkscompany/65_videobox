from __future__ import annotations

import os
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-hermes-yujin-creator-flow.ps1"


def _run(
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
        timeout=60,
        check=False,
        env=environment,
    )


def test_non_live_creator_smoke_proves_explicit_apply_and_reverse_output_path() -> None:
    result = _run()

    assert result.returncode == 0, result.stderr
    assert "HERMES_YUJIN_CREATOR_NON_LIVE_PASS" in result.stdout
    assert "sse_completed=true" in result.stdout
    assert "proposal_ready=true" in result.stdout
    assert "session_file_bound=true" in result.stdout
    assert "mutation_before_apply=0" in result.stdout
    assert "session_revision_delta=1" in result.stdout
    assert "caption_changes=1" in result.stdout
    assert "playback_manifest_checked=true" in result.stdout
    assert "output_readiness_checked=true" in result.stdout
    assert "output_jobs=0" in result.stdout
    assert "external_provider_calls=0" in result.stdout


def test_live_mode_is_fail_closed_without_explicit_confirmation() -> None:
    result = _run("-Live")

    assert result.returncode != 0
    assert "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:confirmation_required" in result.stderr
    assert "HERMES_YUJIN_CREATOR_NON_LIVE_PASS" not in result.stdout


def test_live_mode_rejects_non_loopback_api_before_any_request(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"disposable-live-smoke-sample")
    disposable_root = tmp_path / "disposable"
    disposable_root.mkdir()
    environment = dict(os.environ)
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_SMOKE"] = "1"

    result = _run(
        "-Live",
        "-ConfirmLive",
        "-BaseUri",
        "https://external.invalid",
        "-ProjectId",
        "disposable-smoke-project",
        "-SessionId",
        "disposable-smoke-session",
        "-DisposableProjectRoot",
        str(disposable_root),
        "-SampleAssetPath",
        str(sample),
        environment=environment,
    )

    assert result.returncode != 0
    assert (
        "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:base_uri_loopback_required"
        in result.stderr
    )


def test_live_mode_rejects_an_unrelated_disposable_root_before_api_use(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"disposable-live-smoke-sample")
    unrelated_root = tmp_path / "unrelated-root"
    (unrelated_root / "db").mkdir(parents=True)
    (unrelated_root / "db" / "project.sqlite").write_bytes(b"not-a-project-db")
    environment = dict(os.environ)
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_SMOKE"] = "1"
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_API_TOKEN"] = (
        "local-live-smoke-api-token"
    )

    result = _run(
        "-Live",
        "-ConfirmLive",
        "-BaseUri",
        "http://127.0.0.1:9",
        "-ProjectId",
        "disposable-smoke-project",
        "-SessionId",
        "disposable-smoke-session",
        "-DisposableProjectRoot",
        str(unrelated_root),
        "-SampleAssetPath",
        str(sample),
        environment=environment,
    )

    assert result.returncode != 0
    assert (
        "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:project_root_identity_mismatch"
        in result.stderr
    )
    assert "runtime_unavailable" not in result.stderr


def test_live_mode_binds_local_session_file_before_any_api_post(
    tmp_path: Path,
) -> None:
    project_id = "disposable-smoke-project"
    session_id = "editing_session_001"
    project_root = tmp_path / project_id
    (project_root / "db").mkdir(parents=True)
    (project_root / "db" / "project.sqlite").write_bytes(b"local-project")
    (project_root / "editing_sessions").mkdir()
    local_session = {
        "session_id": session_id,
        "project_id": project_id,
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "caption_style": None,
        "segments": [
            {
                "segment_id": "segment-1",
                "caption_text": "local caption",
                "start_sec": 0.0,
                "end_sec": 2.0,
            }
        ],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "timeline_placement_overrides": {},
        "created_at": "2026-07-28T00:00:00+00:00",
        "updated_at": "2026-07-28T00:00:00+00:00",
    }
    (project_root / "editing_sessions" / f"{session_id}.json").write_text(
        json.dumps(local_session),
        encoding="utf-8",
    )
    sample = tmp_path / "sample.mp4"
    sample.write_bytes(b"disposable-live-smoke-sample")
    calls: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            calls.append(("GET", self.path))
            if self.path == "/api/projects":
                self._json(
                    200,
                    {
                        "projects": [
                            {
                                "project_id": project_id,
                                "name": "Disposable smoke project",
                                "status": "draft",
                                "root_storage_uri": (
                                    f"local://projects/{project_id}"
                                ),
                            }
                        ]
                    },
                )
                return
            if self.path == (
                f"/api/projects/{project_id}/editing-sessions/{session_id}"
            ):
                self._json(
                    200,
                    {
                        **local_session,
                        "session_revision": 2,
                        "segments": [
                            {
                                **local_session["segments"][0],
                                "caption_text": "different server caption",
                            }
                        ],
                        "undo_count": 0,
                        "redo_count": 0,
                    },
                )
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            calls.append(("POST", self.path))
            self.send_error(500)

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    environment = dict(os.environ)
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_SMOKE"] = "1"
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_API_TOKEN"] = (
        "local-live-smoke-api-token"
    )
    try:
        result = _run(
            "-Live",
            "-ConfirmLive",
            "-BaseUri",
            f"http://127.0.0.1:{server.server_port}",
            "-ProjectId",
            project_id,
            "-SessionId",
            session_id,
            "-DisposableProjectRoot",
            str(project_root),
            "-SampleAssetPath",
            str(sample),
            environment=environment,
        )
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()

    assert result.returncode != 0
    assert (
        "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:session_file_api_mismatch"
        in result.stderr
    )
    assert [method for method, _path in calls if method == "POST"] == []
