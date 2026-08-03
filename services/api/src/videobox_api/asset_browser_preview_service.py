from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from videobox_core_engine.asset_browser_preview import BrowserPreviewError, BrowserPreviewMediaInfo
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore, sha256_file


BROWSER_PREVIEW_PROFILE = "h264-yuv420p-aac-1280-v1"
_VIDEO_ASSET_TYPES = {AssetType.RAW_VIDEO.value, AssetType.BROLL_VIDEO.value}


class BrowserPreviewProbe(Protocol):
    def probe(self, source: Path) -> BrowserPreviewMediaInfo: ...


class BrowserPreviewRenderer(Protocol):
    def render(self, source: Path, destination: Path) -> None: ...


class AssetBrowserPreviewUnsupported(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    input_ref: str
    source_sha256: str
    source: Path
    output: Path
    output_uri: str


class AssetBrowserPreviewService:
    def __init__(self, *, store: LocalProjectStore, probe: BrowserPreviewProbe, renderer: BrowserPreviewRenderer) -> None:
        self.store = store
        self.probe = probe
        self.renderer = renderer
        self._hash_cache: dict[Path, tuple[int, int, str]] = {}
        self._hash_lock = threading.Lock()

    def prepare(self, *, project_id: str, asset_id: str) -> tuple[dict, bool, str | None]:
        identity = self._asset_identity(project_id=project_id, asset_id=asset_id)
        job = self.store.get_latest_asset_preview_job(
            project_id=project_id, input_ref=identity.input_ref
        )
        if job is not None and job["status"] in {
            JobStatus.PENDING.value,
            JobStatus.RUNNING.value,
        }:
            return self._job_payload(project_id, asset_id, identity.source_sha256, job), False, identity.input_ref
        if (
            job is not None
            and job["status"] == JobStatus.SUCCEEDED.value
            and self._output_ready(identity)
        ):
            return self._ready_proxy(
                project_id, asset_id, identity.source_sha256, str(job["job_id"])
            ), False, identity.input_ref
        if job is None:
            if self.probe.probe(identity.source).browser_compatible:
                return self._ready_original(
                    project_id, asset_id, identity.source_sha256
                ), False, None
            if self._output_ready(identity):
                return self._ready_proxy(
                    project_id, asset_id, identity.source_sha256, None
                ), False, identity.input_ref
        job, created = self.store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref=identity.input_ref)
        return self._job_payload(project_id, asset_id, identity.source_sha256, job), created, identity.input_ref

    def status(self, *, project_id: str, asset_id: str) -> dict:
        identity = self._asset_identity(project_id=project_id, asset_id=asset_id)
        job = self.store.get_latest_asset_preview_job(project_id=project_id, input_ref=identity.input_ref)
        if job is not None:
            if job["status"] == JobStatus.SUCCEEDED.value:
                if self._output_ready(identity):
                    return self._ready_proxy(
                        project_id, asset_id, identity.source_sha256, str(job["job_id"])
                    )
                return self._failed(
                    identity.source_sha256, str(job["job_id"]), "PREVIEW_CACHE_MISSING"
                )
            return self._job_payload(project_id, asset_id, identity.source_sha256, job)
        if job is None:
            job = self._latest_asset_job(project_id=project_id, asset_id=asset_id)
            if job is not None and job["status"] == JobStatus.SUCCEEDED.value:
                return self._failed(identity.source_sha256, str(job["job_id"]), "PREVIEW_SOURCE_CHANGED")
            if job is not None:
                return self._job_payload(project_id, asset_id, identity.source_sha256, job)
        if self._output_ready(identity):
            return self._ready_proxy(project_id, asset_id, identity.source_sha256, None)
        if self.probe.probe(identity.source).browser_compatible:
            return self._ready_original(project_id, asset_id, identity.source_sha256)
        return self._failed(identity.source_sha256, None, "PREVIEW_NOT_PREPARED")

    def run(self, *, project_id: str, asset_id: str, input_ref: str, job_id: str) -> None:
        temporary: Path | None = None
        try:
            identity = self._asset_identity(project_id=project_id, asset_id=asset_id)
            if identity.input_ref != input_ref:
                raise BrowserPreviewError("PREVIEW_SOURCE_CHANGED")
            temporary = identity.output.with_name(f"{identity.output.stem}.tmp.mp4")
            self.renderer.render(identity.source, temporary)
            rendered = self.probe.probe(temporary)
            if not rendered.browser_compatible or max(rendered.width, rendered.height) > 1280:
                raise BrowserPreviewError("PREVIEW_OUTPUT_INCOMPATIBLE")
            current = self._asset_identity(project_id=project_id, asset_id=asset_id, force_hash=True)
            if current.input_ref != input_ref:
                raise BrowserPreviewError("PREVIEW_SOURCE_CHANGED")
            identity.output.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, identity.output)
            self.store.update_job(project_id=project_id, job_id=job_id, status=JobStatus.SUCCEEDED, output_ref=identity.output_uri)
        except BrowserPreviewError as exc:
            self.store.update_job(project_id=project_id, job_id=job_id, status=JobStatus.FAILED, error_message=exc.code)
        except Exception:
            self.store.update_job(project_id=project_id, job_id=job_id, status=JobStatus.FAILED, error_message="PREVIEW_RENDER_FAILED")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def content_path(self, *, project_id: str, asset_id: str) -> Path:
        identity = self._asset_identity(project_id=project_id, asset_id=asset_id)
        if not identity.output.is_file() or identity.output.stat().st_size <= 0:
            raise FileNotFoundError("browser_preview_not_ready")
        return identity.output

    def recover_orphans(self) -> int:
        return sum(
            self.store.recover_orphaned_asset_preview_jobs(project_id=str(project["project_id"]))
            for project in self.store.list_projects()
        )

    def _asset_identity(self, *, project_id: str, asset_id: str, force_hash: bool = False) -> _SourceIdentity:
        asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
        if str(asset["asset_type"]) not in _VIDEO_ASSET_TYPES:
            raise AssetBrowserPreviewUnsupported("asset_browser_preview_unsupported")
        source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        if not source.is_file():
            raise FileNotFoundError("asset_file_missing")
        stat = source.stat()
        digest = self._source_hash(source, stat.st_size, stat.st_mtime_ns, force=force_hash)
        input_ref = ":".join([project_id, asset_id, str(asset["created_at"]), str(stat.st_size), str(stat.st_mtime_ns), digest, BROWSER_PREVIEW_PROFILE])
        fingerprint = hashlib.sha256(input_ref.encode("utf-8")).hexdigest()
        asset_dir = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:12]
        relative = Path("cache") / "browser" / asset_dir / f"{fingerprint[:24]}.mp4"
        output = self.store.project_root(project_id) / relative
        output_uri = f"local://projects/{project_id}/{relative.as_posix()}"
        return _SourceIdentity(input_ref, digest, source, output, output_uri)

    def _source_hash(self, path: Path, size: int, mtime_ns: int, *, force: bool) -> str:
        resolved = path.resolve()
        with self._hash_lock:
            cached = self._hash_cache.get(resolved)
            if not force and cached is not None and cached[:2] == (size, mtime_ns):
                return cached[2]
        digest = sha256_file(resolved)
        with self._hash_lock:
            self._hash_cache[resolved] = (size, mtime_ns, digest)
        return digest

    def _latest_asset_job(self, *, project_id: str, asset_id: str) -> dict | None:
        prefix = f"{project_id}:{asset_id}:"
        jobs = [job for job in self.store.list_jobs(project_id=project_id) if job["job_type"] == JobType.ASSET_PREVIEW_PROXY.value and str(job.get("input_ref") or "").startswith(prefix)]
        return jobs[-1] if jobs else None

    @staticmethod
    def _output_ready(identity: _SourceIdentity) -> bool:
        return identity.output.is_file() and identity.output.stat().st_size > 0

    @staticmethod
    def _ready_original(project_id: str, asset_id: str, source_sha256: str) -> dict:
        return {"status": "ready", "job_id": None, "content_url": f"/api/projects/{project_id}/assets/{asset_id}/content", "source_sha256": source_sha256, "profile": BROWSER_PREVIEW_PROFILE, "error_code": None}

    @staticmethod
    def _ready_proxy(project_id: str, asset_id: str, source_sha256: str, job_id: str | None) -> dict:
        return {"status": "ready", "job_id": job_id, "content_url": f"/api/projects/{project_id}/assets/{asset_id}/browser-preview/content", "source_sha256": source_sha256, "profile": BROWSER_PREVIEW_PROFILE, "error_code": None}

    @staticmethod
    def _failed(source_sha256: str, job_id: str | None, error_code: str) -> dict:
        return {"status": "failed", "job_id": job_id, "content_url": None, "source_sha256": source_sha256, "profile": BROWSER_PREVIEW_PROFILE, "error_code": error_code}

    def _job_payload(self, project_id: str, asset_id: str, source_sha256: str, job: dict) -> dict:
        if job["status"] == JobStatus.SUCCEEDED.value:
            return self._ready_proxy(project_id, asset_id, source_sha256, str(job["job_id"]))
        if job["status"] == JobStatus.FAILED.value:
            return self._failed(source_sha256, str(job["job_id"]), str(job.get("error_message") or "PREVIEW_RENDER_FAILED"))
        status = "pending" if job["status"] == JobStatus.PENDING.value else "running"
        return {"status": status, "job_id": str(job["job_id"]), "content_url": None, "source_sha256": source_sha256, "profile": BROWSER_PREVIEW_PROFILE, "error_code": None}
