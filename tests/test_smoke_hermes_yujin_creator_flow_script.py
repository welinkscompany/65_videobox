from __future__ import annotations

import hashlib
import hmac
import os
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from videobox_api.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-hermes-yujin-creator-flow.ps1"
ROOT_ATTESTATION_SECRET = "live-smoke-root-attestation-secret-32-bytes"


def _root_attestation_request(secret: str, project_id: str, nonce: str) -> str:
    message = (
        "videobox-live-smoke-root-attestation-request-v1"
        f"\0{project_id}\0{nonce}"
    )
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()


def _root_attestation_response(
    secret: str,
    project_id: str,
    nonce: str,
    project_root: Path,
) -> str:
    canonical_root = os.path.normcase(str(project_root.resolve(strict=True)))
    message = (
        "videobox-live-smoke-root-attestation-response-v1"
        f"\0{project_id}\0{nonce}\0{canonical_root}"
    )
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()


def test_live_root_attestation_endpoint_is_secret_gated_and_path_opaque(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    disabled = TestClient(create_app(projects_root=projects_root))
    project_id = disabled.post(
        "/api/projects",
        json={"name": "attestation disabled"},
    ).json()["project_id"]
    nonce = "a" * 64
    path = (
        f"/internal/live-smoke/projects/{project_id}/root-attestation"
        f"?nonce={nonce}"
    )
    assert disabled.get(path).status_code == 404

    enabled_app = create_app(
        projects_root=projects_root,
        live_smoke_root_attestation_secret=ROOT_ATTESTATION_SECRET,
    )
    enabled = TestClient(enabled_app)
    project_root = enabled_app.state.store.project_root(project_id)
    request_mac = _root_attestation_request(
        ROOT_ATTESTATION_SECRET,
        project_id,
        nonce,
    )
    rejected = enabled.get(
        path,
        headers={"X-VideoBox-Live-Smoke-Attestation": "0" * 64},
    )
    accepted = enabled.get(
        path,
        headers={"X-VideoBox-Live-Smoke-Attestation": request_mac},
    )

    assert rejected.status_code == 404
    assert accepted.status_code == 200
    assert accepted.json() == {
        "version": "v1",
        "project_id": project_id,
        "nonce": nonce,
        "root_attestation": _root_attestation_response(
            ROOT_ATTESTATION_SECRET,
            project_id,
            nonce,
            project_root,
        ),
    }
    assert str(project_root) not in accepted.text


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
            parsed = urlsplit(self.path)
            if parsed.path == (
                f"/internal/live-smoke/projects/{project_id}/"
                "root-attestation"
            ):
                nonce = parse_qs(parsed.query).get("nonce", [""])[0]
                request_mac = self.headers.get(
                    "X-VideoBox-Live-Smoke-Attestation"
                )
                if request_mac != _root_attestation_request(
                    ROOT_ATTESTATION_SECRET,
                    project_id,
                    nonce,
                ):
                    self.send_error(404)
                    return
                self._json(200, {
                    "version": "v1",
                    "project_id": project_id,
                    "nonce": nonce,
                    "root_attestation": _root_attestation_response(
                        ROOT_ATTESTATION_SECRET,
                        project_id,
                        nonce,
                        project_root,
                    ),
                })
                return
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
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_ROOT_ATTESTATION_SECRET"] = (
        ROOT_ATTESTATION_SECRET
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


def test_live_mode_rejects_an_exact_clone_on_a_different_absolute_root_before_any_post(
    tmp_path: Path,
) -> None:
    project_id = "disposable-smoke-project"
    session_id = "editing_session_001"
    client_root = tmp_path / "client" / project_id
    server_root = tmp_path / "server" / project_id
    for root in (client_root, server_root):
        (root / "db").mkdir(parents=True)
        (root / "db" / "project.sqlite").write_bytes(b"exact-clone-db")
        (root / "editing_sessions").mkdir()
    local_session = {
        "session_id": session_id,
        "project_id": project_id,
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "caption_style": None,
        "segments": [{
            "segment_id": "segment-1",
            "caption_text": "same caption",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "sfx_override": None,
            "tts_replacement": None,
            "caption_style": None,
        }],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "timeline_placement_overrides": {},
        "created_at": "2026-07-30T00:00:00+00:00",
        "updated_at": "2026-07-30T00:00:00+00:00",
    }
    for root in (client_root, server_root):
        (root / "editing_sessions" / f"{session_id}.json").write_text(
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
            parsed = urlsplit(self.path)
            if parsed.path == (
                f"/internal/live-smoke/projects/{project_id}/"
                "root-attestation"
            ):
                nonce = parse_qs(parsed.query).get("nonce", [""])[0]
                request_mac = self.headers.get(
                    "X-VideoBox-Live-Smoke-Attestation"
                )
                if request_mac != _root_attestation_request(
                    ROOT_ATTESTATION_SECRET,
                    project_id,
                    nonce,
                ):
                    self.send_error(404)
                    return
                self._json(200, {
                    "version": "v1",
                    "project_id": project_id,
                    "nonce": nonce,
                    "root_attestation": _root_attestation_response(
                        ROOT_ATTESTATION_SECRET,
                        project_id,
                        nonce,
                        server_root,
                    ),
                })
                return
            if self.path == "/api/projects":
                self._json(200, {"projects": [{
                    "project_id": project_id,
                    "name": "Disposable smoke project",
                    "status": "draft",
                    "root_storage_uri": f"local://projects/{project_id}",
                }]})
                return
            if self.path == (
                f"/api/projects/{project_id}/editing-sessions/{session_id}"
            ):
                remote_session = dict(local_session)
                remote_session.pop("undo_stack")
                remote_session.pop("redo_stack")
                remote_session.pop("timeline_placement_overrides")
                remote_session.update({"undo_count": 0, "redo_count": 0})
                self._json(200, remote_session)
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
    environment["VIDEOBOX_HERMES_YUJIN_LIVE_ROOT_ATTESTATION_SECRET"] = (
        ROOT_ATTESTATION_SECRET
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
            str(client_root),
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
        "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:root_attestation_mismatch"
        in result.stderr
    )
    assert [method for method, _path in calls if method == "POST"] == []
