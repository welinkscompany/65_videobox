from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_root in (
    REPOSITORY_ROOT / "services" / "api" / "src",
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "storage-abstractions" / "src",
    REPOSITORY_ROOT / "packages" / "provider-interfaces" / "src",
    REPOSITORY_ROOT / "packages" / "timeline-schema" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
    REPOSITORY_ROOT / "packages" / "capcut-export" / "src",
):
    sys.path.insert(0, str(source_root))

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.asset_browser_preview import (
    FFmpegBrowserPreviewRenderer,
    FFprobeBrowserPreviewProbe,
)
from videobox_storage.local_project_store import LocalProjectStore


SUPPORTED_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".m4v", ".mkv", ".webm"})
MAX_SAMPLE_COUNT = 100
MAX_SAMPLE_BYTES = 2 * 1024 * 1024 * 1024
REPARSE_POINT_ATTRIBUTE = 0x400
PREVIEW_TIMEOUT_SECONDS = 60.0


class OwnerSamplePackageError(RuntimeError):
    """A bounded owner-package error code that never contains a source path."""


@dataclass(frozen=True)
class SampleRecord:
    name: str
    size_bytes: int
    duration_sec: float
    container: str
    video_codec: str
    audio_codec: str | None
    pixel_format: str | None
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprint(path: Path) -> tuple[int, int, str]:
    try:
        before = path.stat()
        digest = _sha256(path)
        after = path.stat()
    except OSError as exc:
        raise OwnerSamplePackageError("sample_read_failed") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise OwnerSamplePackageError("source_changed_during_package")
    return after.st_size, after.st_mtime_ns, digest


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    except OSError as exc:
        raise OwnerSamplePackageError("sample_read_failed") from exc
    return bool(attributes & REPARSE_POINT_ATTRIBUTE)


def _is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_VIDEO_SUFFIXES


def _validated_sample_files(sample_dir: Path) -> list[Path]:
    try:
        if sample_dir.is_symlink() or _is_reparse_point(sample_dir):
            raise OwnerSamplePackageError("sample_path_escape")
        root = sample_dir.resolve(strict=True)
        if not root.is_dir():
            raise OwnerSamplePackageError("sample_directory_invalid")
        children = sorted(root.iterdir(), key=lambda path: (path.name.casefold(), path.name))
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("sample_directory_invalid") from exc

    direct_files: list[Path] = []
    for child in children:
        if child.is_symlink() or _is_reparse_point(child):
            if _is_supported_video(child) or child.is_dir():
                raise OwnerSamplePackageError("sample_path_escape")
            continue
        if child.is_dir():
            try:
                if any(_is_supported_video(descendant) for descendant in child.rglob("*") if descendant.is_file()):
                    raise OwnerSamplePackageError("sample_not_direct_child")
            except OwnerSamplePackageError:
                raise
            except OSError as exc:
                raise OwnerSamplePackageError("sample_read_failed") from exc
            continue
        if not _is_supported_video(child):
            continue
        try:
            resolved = child.resolve(strict=True)
        except OSError as exc:
            raise OwnerSamplePackageError("sample_read_failed") from exc
        if resolved.parent != root or resolved.name != child.name or not resolved.is_file():
            raise OwnerSamplePackageError("sample_path_escape")
        direct_files.append(resolved)

    if len(direct_files) > MAX_SAMPLE_COUNT:
        raise OwnerSamplePackageError("sample_count_limit_exceeded")
    for path in direct_files:
        try:
            if path.stat().st_size > MAX_SAMPLE_BYTES:
                raise OwnerSamplePackageError("sample_size_limit_exceeded")
        except OwnerSamplePackageError:
            raise
        except OSError as exc:
            raise OwnerSamplePackageError("sample_read_failed") from exc
    return direct_files


def _probe_sample(path: Path, *, ffprobe_binary: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                ffprobe_binary,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OwnerSamplePackageError("sample_probe_failed") from exc
    if completed.returncode != 0:
        raise OwnerSamplePackageError("sample_probe_failed")
    try:
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict) or not isinstance(payload.get("streams"), list):
            raise ValueError("invalid probe payload")
        return payload
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise OwnerSamplePackageError("sample_probe_failed") from exc


def _record_from_probe(path: Path, payload: dict[str, Any], fingerprint: tuple[int, int, str]) -> SampleRecord:
    streams = payload["streams"]
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise OwnerSamplePackageError("sample_video_stream_missing")
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    media_format = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration_value = media_format.get("duration") or video.get("duration")
    try:
        duration = float(duration_value)
        if not (duration > 0):
            raise ValueError("non-positive duration")
        codec = str(video["codec_name"]).strip().lower()
        container = str(media_format["format_name"]).strip().lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise OwnerSamplePackageError("sample_probe_invalid") from exc
    return SampleRecord(
        name=path.name,
        size_bytes=fingerprint[0],
        duration_sec=duration,
        container=container,
        video_codec=codec,
        audio_codec=str(audio["codec_name"]).strip().lower() if audio and audio.get("codec_name") else None,
        pixel_format=str(video["pix_fmt"]).strip().lower() if video.get("pix_fmt") else None,
        sha256=fingerprint[2],
    )


def inventory_samples(sample_dir: Path, *, ffprobe_binary: str) -> list[SampleRecord]:
    paths = _validated_sample_files(Path(sample_dir))
    initial = {path.name: _source_fingerprint(path) for path in paths}
    records = [
        _record_from_probe(
            path,
            _probe_sample(path, ffprobe_binary=ffprobe_binary),
            initial[path.name],
        )
        for path in paths
    ]
    if any(_source_fingerprint(path) != initial[path.name] for path in paths):
        raise OwnerSamplePackageError("source_changed_during_package")
    return records


def select_preview_inputs(records: Sequence[SampleRecord]) -> dict[str, SampleRecord]:
    h264 = [record for record in records if record.video_codec.lower() in {"h264", "avc"}]
    hevc = [record for record in records if record.video_codec.lower() in {"hevc", "h265"}]
    if not h264 or not hevc:
        raise OwnerSamplePackageError("required_preview_codec_missing")
    key = lambda record: (record.duration_sec, record.size_bytes, record.name.casefold(), record.name)
    return {"h264": min(h264, key=key), "hevc": min(hevc, key=key)}


def _selected_source(sample_dir: Path, record: SampleRecord) -> Path:
    if Path(record.name).name != record.name:
        raise OwnerSamplePackageError("sample_not_direct_child")
    try:
        root = sample_dir.resolve(strict=True)
        source = (root / record.name).resolve(strict=True)
    except OSError as exc:
        raise OwnerSamplePackageError("sample_read_failed") from exc
    if source.parent != root or source.is_symlink() or _is_reparse_point(source) or not source.is_file():
        raise OwnerSamplePackageError("sample_path_escape")
    return source


def _poll_preview(client: TestClient, endpoint: str, state: dict[str, Any]) -> dict[str, Any]:
    deadline = time.monotonic() + PREVIEW_TIMEOUT_SECONDS
    while state.get("status") in {"pending", "running"}:
        if time.monotonic() >= deadline:
            raise OwnerSamplePackageError("preview_timeout")
        time.sleep(0.05)
        response = client.get(endpoint)
        if response.status_code != 200:
            raise OwnerSamplePackageError("preview_status_failed")
        state = response.json()
    if state.get("status") != "ready" or not state.get("content_url"):
        raise OwnerSamplePackageError("preview_not_ready")
    return state


def _probe_preview_output(path: Path, *, ffprobe_binary: str) -> tuple[str, str | None]:
    payload = _probe_sample(path, ffprobe_binary=ffprobe_binary)
    video = next((stream for stream in payload["streams"] if stream.get("codec_type") == "video"), None)
    if video is None:
        raise OwnerSamplePackageError("preview_output_invalid")
    return str(video.get("codec_name") or "").lower(), (
        str(video.get("pix_fmt")).lower() if video.get("pix_fmt") else None
    )


def _probe_api_content(
    client: TestClient,
    *,
    content_url: str,
    projects_root: Path,
    ffprobe_binary: str,
) -> tuple[str, str | None]:
    projects_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="owner-preview-probe-", dir=projects_root) as temporary:
        materialized = Path(temporary) / "preview.mp4"
        total_bytes = 0
        with client.stream("GET", content_url) as response:
            if response.status_code != 200:
                raise OwnerSamplePackageError("preview_content_failed")
            with materialized.open("wb") as target:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_SAMPLE_BYTES:
                        raise OwnerSamplePackageError("preview_content_size_exceeded")
                    target.write(chunk)
        if total_bytes <= 0:
            raise OwnerSamplePackageError("preview_content_empty")
        return _probe_preview_output(materialized, ffprobe_binary=ffprobe_binary)


def build_preview_proofs(
    *,
    sample_dir: Path,
    selected: dict[str, SampleRecord],
    projects_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
) -> dict[str, Any]:
    if (
        set(selected) != {"h264", "hevc"}
        or selected["h264"].video_codec.lower() not in {"h264", "avc"}
        or selected["hevc"].video_codec.lower() not in {"hevc", "h265"}
    ):
        raise OwnerSamplePackageError("required_preview_codec_missing")
    sources = {codec: _selected_source(Path(sample_dir), selected[codec]) for codec in ("h264", "hevc")}
    initial = {codec: _source_fingerprint(path) for codec, path in sources.items()}
    for codec, record in selected.items():
        if initial[codec][0] != record.size_bytes or initial[codec][2] != record.sha256:
            raise OwnerSamplePackageError("source_changed_during_package")

    try:
        return _build_preview_proofs_unfenced(
            selected=selected,
            sources=sources,
            initial=initial,
            projects_root=projects_root,
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
        )
    finally:
        if any(
            _source_fingerprint(sources[codec]) != initial[codec]
            for codec in ("h264", "hevc")
        ):
            raise OwnerSamplePackageError("source_changed_during_package")


def _build_preview_proofs_unfenced(
    *,
    selected: dict[str, SampleRecord],
    sources: dict[str, Path],
    initial: dict[str, tuple[int, int, str]],
    projects_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
) -> dict[str, Any]:

    projects_root = Path(projects_root)
    app = create_app(
        projects_root=projects_root,
        asset_browser_preview_probe=FFprobeBrowserPreviewProbe(ffprobe_binary=ffprobe_binary),
        asset_browser_preview_renderer=FFmpegBrowserPreviewRenderer(ffmpeg_binary=ffmpeg_binary),
    )
    api_import_log = [{"method": "POST", "path": "/api/projects"}]
    previews: dict[str, dict[str, Any]] = {}
    with TestClient(app) as client:
        project_response = client.post("/api/projects", json={"name": "Task 23C owner sample preview"})
        if project_response.status_code != 201:
            raise OwnerSamplePackageError("project_create_failed")
        project_id = str(project_response.json().get("project_id") or "")
        if not project_id:
            raise OwnerSamplePackageError("project_create_failed")
        store = LocalProjectStore(projects_root)

        for codec in ("h264", "hevc"):
            record = selected[codec]
            source = sources[codec]
            import_path = f"/api/projects/{project_id}/assets/broll-video"
            api_import_log.append(
                {"method": "POST", "path": "/api/projects/{project_id}/assets/broll-video"}
            )
            imported_response = client.post(
                import_path,
                json={"source_path": str(source), "title": source.stem, "tags": ["owner-sample-qa"]},
            )
            if imported_response.status_code != 201:
                raise OwnerSamplePackageError("sample_import_failed")
            imported = imported_response.json()
            asset_id = str(imported.get("asset_id") or "")
            storage_uri = str(imported.get("storage_uri") or "")
            if not asset_id or not storage_uri.startswith(f"local://projects/{project_id}/"):
                raise OwnerSamplePackageError("sample_import_invalid")
            try:
                stored = store.resolve_storage_uri(project_id=project_id, storage_uri=storage_uri)
                stored_resolved = stored.resolve(strict=True)
                runtime_resolved = projects_root.resolve(strict=True)
                if not stored_resolved.is_relative_to(runtime_resolved):
                    raise OwnerSamplePackageError("project_copy_path_escape")
                copy_sha = _sha256(stored_resolved)
            except OwnerSamplePackageError:
                raise
            except (OSError, ValueError) as exc:
                raise OwnerSamplePackageError("project_copy_invalid") from exc
            if copy_sha != record.sha256:
                if _source_fingerprint(source) != initial[codec]:
                    raise OwnerSamplePackageError("source_changed_during_package")
                raise OwnerSamplePackageError("project_copy_hash_mismatch")

            endpoint = f"/api/projects/{project_id}/assets/{asset_id}/browser-preview"
            started = client.post(endpoint)
            if started.status_code not in {200, 202}:
                raise OwnerSamplePackageError("preview_start_failed")
            state = _poll_preview(client, endpoint, started.json())
            expected_content_url = (
                f"/api/projects/{project_id}/assets/{asset_id}/content"
                if codec == "h264"
                else f"{endpoint}/content"
            )
            if state.get("content_url") != expected_content_url:
                raise OwnerSamplePackageError("preview_content_url_invalid")
            ranged = client.get(expected_content_url, headers={"Range": "bytes=0-31"})
            if ranged.status_code != 206:
                raise OwnerSamplePackageError("preview_range_failed")
            if codec == "h264":
                output_codec, output_pixel_format = _probe_preview_output(
                    stored_resolved, ffprobe_binary=ffprobe_binary
                )
            else:
                output_codec, output_pixel_format = _probe_api_content(
                    client,
                    content_url=expected_content_url,
                    projects_root=projects_root,
                    ffprobe_binary=ffprobe_binary,
                )
            if output_codec != "h264" or output_pixel_format != "yuv420p":
                raise OwnerSamplePackageError("preview_output_invalid")
            previews[codec] = {
                "source_name": record.name,
                "source_sha256": record.sha256,
                "project_copy_ref": storage_uri,
                "project_copy_sha256": copy_sha,
                "preview_kind": "original" if codec == "h264" else "proxy",
                "content_url": expected_content_url,
                "range_status": ranged.status_code,
                "output_video_codec": output_codec,
                "output_pixel_format": output_pixel_format,
            }

    return {
        "project_ref": f"projects/{project_id}",
        "api_import_log": api_import_log,
        "previews": previews,
        "external_provider_calls": 0,
    }
