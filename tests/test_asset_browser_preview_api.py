from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.asset_browser_preview import BrowserPreviewError, BrowserPreviewMediaInfo
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus
from videobox_storage.local_project_store import LocalProjectStore


class FakeProbe:
    def __init__(self, *, source_compatible: bool = False) -> None:
        self.source_compatible = source_compatible
        self.calls: list[Path] = []

    def probe(self, path: Path) -> BrowserPreviewMediaInfo:
        self.calls.append(path)
        compatible = self.source_compatible or path.name.endswith(".tmp.mp4")
        return BrowserPreviewMediaInfo(
            container_names=("mov", "mp4"),
            video_codec="h264" if compatible else "hevc",
            pixel_format="yuv420p",
            audio_codec="aac",
            width=1280 if path.name.endswith(".tmp.mp4") else 1920,
            height=720 if path.name.endswith(".tmp.mp4") else 1080,
        )


class FakeRenderer:
    def __init__(self, *, hold: threading.Event | None = None, fail: bool = False, mutate_source: bool = False) -> None:
        self.hold = hold
        self.fail = fail
        self.mutate_source = mutate_source
        self.calls: list[tuple[Path, Path]] = []

    def render(self, source: Path, destination: Path) -> None:
        self.calls.append((source, destination))
        if self.hold is not None:
            self.hold.wait(timeout=5)
        if self.fail:
            raise BrowserPreviewError("PREVIEW_RENDER_FAILED")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"0123456789")
        if self.mutate_source:
            source.write_bytes(b"changed-during-render")


def _asset(tmp_path: Path, client: TestClient, *, asset_type: AssetType = AssetType.BROLL_VIDEO) -> tuple[str, str, Path]:
    project_id = client.post("/api/projects", json={"name": "Browser preview"}).json()["project_id"]
    original = tmp_path / f"source-{asset_type.value}.mov"
    original.write_bytes(b"original-source")
    store = LocalProjectStore(tmp_path)
    asset = store.register_asset(project_id=project_id, asset_type=asset_type, source_path=original)
    stored = store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri)
    return project_id, asset.asset_id, stored


def _wait(client: TestClient, url: str) -> dict:
    for _ in range(100):
        body = client.get(url).json()
        if body["status"] not in {"pending", "running"}:
            return body
        time.sleep(0.01)
    raise AssertionError("preview job did not finish")


def test_compatible_video_returns_original_content_without_job_or_render(tmp_path: Path) -> None:
    probe = FakeProbe(source_compatible=True)
    renderer = FakeRenderer()
    client = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=probe, asset_browser_preview_renderer=renderer))
    project_id, asset_id, _stored = _asset(tmp_path, client)

    response = client.post(f"/api/projects/{project_id}/assets/{asset_id}/browser-preview")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "job_id": None,
        "content_url": f"/api/projects/{project_id}/assets/{asset_id}/content",
        "source_sha256": response.json()["source_sha256"],
        "profile": "h264-yuv420p-aac-1280-v1",
        "error_code": None,
    }
    assert renderer.calls == []
    assert LocalProjectStore(tmp_path).list_jobs(project_id=project_id) == []


def test_incompatible_video_reuses_active_job_then_serves_range_content(tmp_path: Path) -> None:
    gate = threading.Event()
    renderer = FakeRenderer(hold=gate)
    client = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=renderer))
    project_id, asset_id, _stored = _asset(tmp_path, client)
    endpoint = f"/api/projects/{project_id}/assets/{asset_id}/browser-preview"

    first = client.post(endpoint)
    second = client.post(endpoint)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["status"] in {"pending", "running"}
    assert first.json()["job_id"] == second.json()["job_id"]
    gate.set()

    ready = _wait(client, endpoint)
    assert ready["status"] == "ready"
    assert ready["content_url"] == f"{endpoint}/content"
    assert len(renderer.calls) == 1
    ranged = client.get(ready["content_url"], headers={"Range": "bytes=2-5"})
    assert ranged.status_code == 206
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.content == b"2345"
    assert client.get(ready["content_url"], headers={"Range": "bytes=99-100"}).status_code == 416


def test_non_video_asset_is_rejected_without_probe(tmp_path: Path) -> None:
    probe = FakeProbe()
    client = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=probe, asset_browser_preview_renderer=FakeRenderer()))
    project_id, asset_id, _stored = _asset(tmp_path, client, asset_type=AssetType.IMAGE)

    response = client.post(f"/api/projects/{project_id}/assets/{asset_id}/browser-preview")

    assert response.status_code == 409
    assert response.json()["detail"] == "asset_browser_preview_unsupported"
    assert probe.calls == []


def test_render_failure_and_source_revision_change_are_bounded(tmp_path: Path) -> None:
    for renderer, expected in [
        (FakeRenderer(fail=True), "PREVIEW_RENDER_FAILED"),
        (FakeRenderer(mutate_source=True), "PREVIEW_SOURCE_CHANGED"),
    ]:
        case_root = tmp_path / expected
        client = TestClient(create_app(projects_root=case_root, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=renderer))
        project_id, asset_id, _stored = _asset(case_root, client)
        endpoint = f"/api/projects/{project_id}/assets/{asset_id}/browser-preview"
        assert client.post(endpoint).status_code == 202
        failed = _wait(client, endpoint)
        assert failed["status"] == "failed"
        assert failed["error_code"] == expected
        assert "source-" not in str(failed).lower()
        retry = client.post(endpoint)
        assert retry.status_code == 202
        assert retry.json()["job_id"] != failed["job_id"]


def test_completed_proxy_is_not_reused_after_the_registered_source_changes(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=FakeRenderer()))
    project_id, asset_id, stored = _asset(tmp_path, client)
    endpoint = f"/api/projects/{project_id}/assets/{asset_id}/browser-preview"
    assert client.post(endpoint).status_code == 202
    assert _wait(client, endpoint)["status"] == "ready"

    stored.write_bytes(b"new-source-revision")
    stale = _wait(client, endpoint)

    assert stale["status"] == "failed"
    assert stale["error_code"] == "PREVIEW_SOURCE_CHANGED"
    assert client.get(f"{endpoint}/content").status_code == 404


def test_completed_proxy_never_reports_ready_after_its_cache_file_is_missing(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=FakeRenderer()))
    project_id, asset_id, _stored = _asset(tmp_path, client)
    endpoint = f"/api/projects/{project_id}/assets/{asset_id}/browser-preview"
    assert client.post(endpoint).status_code == 202
    assert _wait(client, endpoint)["status"] == "ready"
    output = client.app.state.asset_browser_preview_service.content_path(project_id=project_id, asset_id=asset_id)

    output.unlink()
    missing = client.get(endpoint)

    assert missing.status_code == 200
    assert missing.json()["status"] == "failed"
    assert missing.json()["error_code"] == "PREVIEW_CACHE_MISSING"
    assert missing.json()["content_url"] is None
    assert client.get(f"{endpoint}/content").status_code == 404


def test_startup_recovers_orphaned_preview_jobs_without_rendering(tmp_path: Path) -> None:
    bootstrap = TestClient(create_app(projects_root=tmp_path, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=FakeRenderer()))
    project_id, asset_id, stored = _asset(tmp_path, bootstrap)
    store = LocalProjectStore(tmp_path)
    source_hash = __import__("hashlib").sha256(stored.read_bytes()).hexdigest()
    stat = stored.stat()
    input_ref = f"{asset_id}:{store.get_asset(project_id=project_id, asset_id=asset_id)['created_at']}:{stat.st_size}:{stat.st_mtime_ns}:{source_hash}:h264-yuv420p-aac-1280-v1"
    job, _ = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref=input_ref)
    renderer = FakeRenderer()
    app = create_app(projects_root=tmp_path, asset_browser_preview_probe=FakeProbe(), asset_browser_preview_renderer=renderer)

    with TestClient(app):
        recovered = store.get_job(project_id=project_id, job_id=job["job_id"])
        assert recovered["status"] == JobStatus.FAILED.value
        assert recovered["error_message"] == "PREVIEW_WORKER_RESTARTED"
    assert renderer.calls == []
