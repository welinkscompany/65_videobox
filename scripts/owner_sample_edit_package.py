from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Sequence


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

from videobox_api.asset_browser_preview_service import BROWSER_PREVIEW_PROFILE
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
PREVIEW_RENDER_TIMEOUT_SECONDS = 45
MANIFEST_FILENAME = "owner-sample-edit-package.json"
MANIFEST_TEMP_FILENAME = ".owner-sample-edit-package.json.tmp"
PACKAGE_SCHEMA_VERSION = "videobox.owner-sample-edit-package.v1"
DEFAULT_NARRATION_PATH = REPOSITORY_ROOT / "artifacts" / "task5-korean-600.wav"
MAX_MANIFEST_ARTIFACTS = 16
MAX_REVERSE_TRACE_NODES = 64
MAX_REVERSE_UPSTREAM = 8
MAX_MANIFEST_PATH_LENGTH = 240
REVIEW_ARTIFACT_KEYS = (
    "exact_preview",
    "final_mp4",
    "srt",
    "timeline_snapshot",
    "editing_session_snapshot",
    "capcut_draft",
    "ffprobe_summary",
    "review_checklist",
)
EDIT_RESULT_ARTIFACT_KEYS = tuple(
    key for key in REVIEW_ARTIFACT_KEYS if key != "review_checklist"
)
CONTROL_CHECKS = {
    "broll": "broll_controls_in_timeline",
    "bgm": "audio_controls_in_timeline",
    "sfx": "approved_sfx_in_final_and_capcut",
    "caption": "revised_caption_in_srt",
    "tts": "approved_tts_in_final_and_capcut",
    "explanation_overlay": "image_overlay_in_final_and_capcut",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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
            raise OwnerSamplePackageError("sample_not_direct_child")
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
    h264 = [record for record in records if _is_original_browser_ready(record)]
    hevc = [record for record in records if record.video_codec.lower() in {"hevc", "h265"}]
    if not h264 or not hevc:
        raise OwnerSamplePackageError("required_preview_codec_missing")
    key = lambda record: (record.duration_sec, record.size_bytes, record.name.casefold(), record.name)
    return {"h264": min(h264, key=key), "hevc": min(hevc, key=key)}


def _is_original_browser_ready(record: SampleRecord) -> bool:
    container_tokens = {
        token.strip().lower() for token in record.container.split(",") if token.strip()
    }
    return (
        record.video_codec.lower() in {"h264", "avc"}
        and bool(container_tokens.intersection({"mov", "mp4"}))
        and record.pixel_format is not None
        and record.pixel_format.lower() == "yuv420p"
        and (record.audio_codec is None or record.audio_codec.lower() == "aac")
    )


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


def _assert_final_source_fence(
    sources: dict[str, Path], initial: dict[str, tuple[int, int, str]]
) -> None:
    for codec in ("h264", "hevc"):
        source = sources[codec]
        try:
            if source.is_symlink() or _is_reparse_point(source) or not source.is_file():
                raise OwnerSamplePackageError("source_changed_during_package")
            current = _source_fingerprint(source)
        except (OSError, OwnerSamplePackageError):
            raise OwnerSamplePackageError("source_changed_during_package") from None
        if current != initial[codec]:
            raise OwnerSamplePackageError("source_changed_during_package")


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
) -> tuple[str, str | None, str]:
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
        video_codec, pixel_format = _probe_preview_output(
            materialized, ffprobe_binary=ffprobe_binary
        )
        return video_codec, pixel_format, _sha256(materialized)


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
        or not _is_original_browser_ready(selected["h264"])
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
        _assert_final_source_fence(sources, initial)


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
        asset_browser_preview_renderer=FFmpegBrowserPreviewRenderer(
            ffmpeg_binary=ffmpeg_binary,
            timeout_seconds=PREVIEW_RENDER_TIMEOUT_SECONDS,
        ),
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
            if state.get("source_sha256") != copy_sha:
                raise OwnerSamplePackageError("preview_source_identity_mismatch")
            if state.get("profile") != BROWSER_PREVIEW_PROFILE:
                raise OwnerSamplePackageError("preview_profile_mismatch")
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
            output_codec, output_pixel_format, content_sha = _probe_api_content(
                client,
                content_url=expected_content_url,
                projects_root=projects_root,
                ffprobe_binary=ffprobe_binary,
            )
            if codec == "h264" and content_sha != copy_sha:
                raise OwnerSamplePackageError("preview_content_hash_mismatch")
            if output_codec != "h264" or output_pixel_format != "yuv420p":
                raise OwnerSamplePackageError("preview_output_invalid")
            previews[codec] = {
                "source_name": record.name,
                "source_sha256": record.sha256,
                "preview_source_sha256": str(state["source_sha256"]),
                "profile": str(state["profile"]),
                "project_copy_ref": storage_uri,
                "project_copy_sha256": copy_sha,
                "content_sha256": content_sha,
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


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return False


def _prepare_package_root(*, sample_dir: Path, output_root: Path) -> Path:
    sample_candidate = Path(sample_dir)
    try:
        if not sample_candidate.exists() or not sample_candidate.is_dir():
            raise OwnerSamplePackageError("sample_directory_invalid")
        if sample_candidate.is_symlink() or _is_reparse_point(sample_candidate):
            raise OwnerSamplePackageError("sample_path_escape")
        sample_root = sample_candidate.resolve(strict=True)
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("sample_directory_invalid") from exc

    candidate = Path(output_root)
    try:
        planned_root = candidate.resolve(strict=False)
    except OSError as exc:
        raise OwnerSamplePackageError("package_root_invalid") from exc
    if (
        planned_root == sample_root
        or planned_root.is_relative_to(sample_root)
        or sample_root.is_relative_to(planned_root)
    ):
        raise OwnerSamplePackageError("package_root_overlaps_samples")
    try:
        if candidate.exists():
            if candidate.is_symlink() or _is_reparse_point(candidate) or not candidate.is_dir():
                raise OwnerSamplePackageError("package_root_invalid")
            package_root = candidate.resolve(strict=True)
        else:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.mkdir()
            package_root = candidate.resolve(strict=True)
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("package_root_invalid") from exc

    if (
        package_root == sample_root
        or package_root.is_relative_to(sample_root)
        or sample_root.is_relative_to(package_root)
    ):
        raise OwnerSamplePackageError("package_root_overlaps_samples")
    try:
        if next(package_root.iterdir(), None) is not None:
            raise OwnerSamplePackageError("package_root_not_empty")
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("package_root_invalid") from exc
    return package_root


def _copy_stream_bounded(source: Path, target: Path) -> None:
    total = 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, target.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MAX_SAMPLE_BYTES:
                    raise OwnerSamplePackageError("narration_size_limit_exceeded")
                writer.write(chunk)
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("narration_copy_failed") from exc
    if total <= 0:
        raise OwnerSamplePackageError("narration_empty")


def _run_narration_generator(
    target: Path, *, ffmpeg_binary: str, ffprobe_binary: str
) -> None:
    generator = REPOSITORY_ROOT / "scripts" / "New-ProductionReadinessKoreanSample.ps1"
    if not generator.is_file():
        raise OwnerSamplePackageError("narration_generator_missing")
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(generator),
                "-OutputPath",
                str(target),
                "-FfmpegBinary",
                ffmpeg_binary,
                "-FfprobeBinary",
                ffprobe_binary,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3_600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OwnerSamplePackageError("narration_generation_failed") from exc
    if completed.returncode != 0 or not target.is_file():
        raise OwnerSamplePackageError("narration_generation_failed")


def _prepare_narration(
    *,
    narration: Path,
    package_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
) -> tuple[dict[str, Any], tuple[Path, tuple[int, int, str]] | None]:
    target = package_root / "inputs" / "qa-narration.wav"
    source = Path(narration)
    if source.exists():
        try:
            if source.is_symlink() or _is_reparse_point(source) or not source.is_file():
                raise OwnerSamplePackageError("narration_invalid")
            source = source.resolve(strict=True)
        except OwnerSamplePackageError:
            raise
        except OSError as exc:
            raise OwnerSamplePackageError("narration_invalid") from exc
        if source.is_relative_to(package_root):
            raise OwnerSamplePackageError("narration_must_be_external_input")
        initial = _source_fingerprint(source)
        _copy_stream_bounded(source, target)
        if _source_fingerprint(source) != initial:
            raise OwnerSamplePackageError("narration_source_changed")
        copy_sha = _sha256(target)
        if copy_sha != initial[2]:
            raise OwnerSamplePackageError("narration_copy_hash_mismatch")
        return (
            {
                "source_name": source.name,
                "source_sha256": initial[2],
                "copy_path": target.relative_to(package_root).as_posix(),
                "copy_sha256": copy_sha,
                "generated_locally": False,
            },
            (source, initial),
        )

    if not _same_path(source, DEFAULT_NARRATION_PATH):
        raise OwnerSamplePackageError("narration_missing")
    target.parent.mkdir(parents=True, exist_ok=True)
    _run_narration_generator(
        target,
        ffmpeg_binary=ffmpeg_binary,
        ffprobe_binary=ffprobe_binary,
    )
    if target.is_symlink() or _is_reparse_point(target) or not target.is_file():
        raise OwnerSamplePackageError("narration_generation_failed")
    generated_sha = _sha256(target)
    return (
        {
            "source_name": "New-ProductionReadinessKoreanSample.ps1",
            "source_sha256": generated_sha,
            "copy_path": target.relative_to(package_root).as_posix(),
            "copy_sha256": generated_sha,
            "generated_locally": True,
        },
        None,
    )


def _assert_narration_source_fence(
    source_fence: tuple[Path, tuple[int, int, str]] | None,
) -> None:
    if source_fence is None:
        return
    source, initial = source_fence
    try:
        if source.is_symlink() or _is_reparse_point(source) or not source.is_file():
            raise OwnerSamplePackageError("narration_source_changed")
        if _source_fingerprint(source) != initial:
            raise OwnerSamplePackageError("narration_source_changed")
    except OwnerSamplePackageError as exc:
        if str(exc) == "narration_source_changed":
            raise
        raise OwnerSamplePackageError("narration_source_changed") from None
    except OSError:
        raise OwnerSamplePackageError("narration_source_changed") from None


def write_review_checklist(package_root: Path) -> Path:
    root = Path(package_root)
    try:
        if root.is_symlink() or _is_reparse_point(root) or not root.is_dir():
            raise OwnerSamplePackageError("package_root_invalid")
        path = root / "review-checklist.ko.md"
        path.write_text(
            """# 사람 검토 체크리스트

> 자동 통과 아님: 아래 항목은 사람이 직접 보고 듣고 확인해야 합니다.

- [ ] 영상: 화면 흐름, 잘림, 검은 화면이 없는지 확인
- [ ] 자막: 내용, 맞춤법, 표시 시점을 확인
- [ ] 목소리: 발음, 속도, 음량이 자연스러운지 확인
- [ ] 음악: 분위기와 음량이 영상에 맞는지 확인
- [ ] 효과음: 위치와 크기가 과하지 않은지 확인
- [ ] 장면 전환: 전환 시점과 연결이 자연스러운지 확인
- [ ] 권리: 영상, 음악, 효과음, 이미지 사용 권리를 확인
- [ ] 최종 export: 최종 파일을 처음부터 끝까지 재생해 확인
""",
            encoding="utf-8",
            newline="\n",
        )
        return path
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("review_checklist_write_failed") from exc


def _load_default_edit_flow_runner() -> Callable[..., dict[str, Any]]:
    script = REPOSITORY_ROOT / "scripts" / "verify-production-readiness-smoke.py"
    spec = importlib.util.spec_from_file_location("videobox_owner_package_smoke", script)
    if spec is None or spec.loader is None:
        raise OwnerSamplePackageError("edit_flow_runner_unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        runner = getattr(module, "run_smoke")
    except (AttributeError, ImportError, OSError) as exc:
        raise OwnerSamplePackageError("edit_flow_runner_unavailable") from exc
    if not callable(runner):
        raise OwnerSamplePackageError("edit_flow_runner_unavailable")
    return runner


def _validate_edit_result(result: dict[str, Any]) -> dict[str, bool]:
    if not isinstance(result, dict) or result.get("fixture_name") != "audio_ducking":
        raise OwnerSamplePackageError("edit_flow_fixture_mismatch")
    if result.get("desktop_capcut_opened") is not False:
        raise OwnerSamplePackageError("desktop_edit_boundary_violated")
    checks = result.get("checks")
    if not isinstance(checks, dict):
        raise OwnerSamplePackageError("edit_flow_controls_missing")
    controls = {
        control: checks.get(check_name) is True
        for control, check_name in CONTROL_CHECKS.items()
    }
    if not all(controls.values()):
        raise OwnerSamplePackageError("edit_flow_controls_missing")
    return controls


def _path_has_link_or_reparse(root: Path, relative: PurePosixPath) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
            if not current.exists():
                return False
            if _is_reparse_point(current):
                return True
        except OwnerSamplePackageError:
            return True
    return False


def _safe_manifest_artifact_path(package_root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or len(value) > MAX_MANIFEST_PATH_LENGTH:
        raise OwnerSamplePackageError("manifest_artifact_path_invalid")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if (
        "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or windows.drive
        or windows.root
        or posix.is_absolute()
        or any(part in {"", ".", ".."} for part in posix.parts)
        or posix.as_posix() != value
    ):
        raise OwnerSamplePackageError("manifest_artifact_path_invalid")
    if _path_has_link_or_reparse(package_root, posix):
        raise OwnerSamplePackageError("manifest_artifact_path_invalid")
    path = package_root.joinpath(*posix.parts)
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(package_root) or not resolved.is_file():
            raise OwnerSamplePackageError("manifest_artifact_missing")
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("manifest_artifact_missing") from exc
    return resolved


def _artifact_evidence_from_edit(
    *, package_root: Path, edit_result: dict[str, Any], checklist_path: Path
) -> dict[str, dict[str, str]]:
    paths: dict[str, Path] = {"review_checklist": checklist_path}
    for key in EDIT_RESULT_ARTIFACT_KEYS:
        row = edit_result.get(key)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise OwnerSamplePackageError("edit_artifact_missing")
        path = Path(row["path"])
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise OwnerSamplePackageError("edit_artifact_missing") from exc
        if (
            not resolved.is_relative_to(package_root)
            or resolved.is_symlink()
            or _is_reparse_point(resolved)
            or not resolved.is_file()
        ):
            raise OwnerSamplePackageError("edit_artifact_path_invalid")
        actual_sha = _sha256(resolved)
        if row.get("sha256") != actual_sha:
            raise OwnerSamplePackageError("edit_artifact_sha_mismatch")
        paths[key] = resolved
    return {
        key: {
            "path": path.relative_to(package_root).as_posix(),
            "sha256": _sha256(path),
        }
        for key, path in paths.items()
    }


def _build_reverse_trace(
    *,
    artifacts: dict[str, dict[str, str]],
    narration: dict[str, Any],
    previews: dict[str, Any],
    controls: dict[str, bool],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {
        f"artifact:{name}": {
            "kind": "artifact",
            "artifact": name,
            "sha256": artifacts[name]["sha256"],
            "upstream": ["editing_session:current"],
        }
        for name in sorted(artifacts)
    }
    nodes.update(
        {
            "editing_session:current": {
                "kind": "editing_session",
                "editing_session_sha256": artifacts["editing_session_snapshot"]["sha256"],
                "timeline_sha256": artifacts["timeline_snapshot"]["sha256"],
                "upstream": ["typed_controls:applied"],
            },
            "typed_controls:applied": {
                "kind": "typed_controls",
                "controls": controls,
                "qa_fixture_only": True,
                "upstream": ["copied_asset:narration", "preview:h264", "preview:hevc"],
            },
            "copied_asset:narration": {
                "kind": "copied_asset",
                "ref": narration["copy_path"],
                "sha256": narration["copy_sha256"],
                "upstream": ["source_sha:narration"],
            },
            "source_sha:narration": {
                "kind": "source_sha",
                "source_name": narration["source_name"],
                "sha256": narration["source_sha256"],
                "upstream": [],
            },
        }
    )
    for codec in ("h264", "hevc"):
        proof = previews[codec]
        nodes[f"preview:{codec}"] = {
            "kind": "preview_proof",
            "source_name": proof["source_name"],
            "source_sha256": proof["source_sha256"],
            "preview_source_sha256": proof["preview_source_sha256"],
            "profile": proof["profile"],
            "content_sha256": proof["content_sha256"],
            "preview_kind": proof["preview_kind"],
            "upstream": [f"copied_asset:{codec}"],
        }
        nodes[f"copied_asset:{codec}"] = {
            "kind": "copied_asset",
            "ref": proof["project_copy_ref"],
            "sha256": proof["project_copy_sha256"],
            "upstream": [f"source_sha:{codec}"],
        }
        nodes[f"source_sha:{codec}"] = {
            "kind": "source_sha",
            "source_name": proof["source_name"],
            "sha256": proof["source_sha256"],
            "upstream": [],
        }
    return {"nodes": nodes}


def _validate_source_inventory(manifest: dict[str, Any]) -> None:
    rows = manifest.get("source_inventory")
    allowed = {
        "name",
        "size_bytes",
        "duration_sec",
        "container",
        "video_codec",
        "audio_codec",
        "pixel_format",
        "sha256",
    }
    if not isinstance(rows, list) or len(rows) > MAX_SAMPLE_COUNT:
        raise OwnerSamplePackageError("manifest_source_inventory_invalid")
    for row in rows:
        if not isinstance(row, dict) or set(row) != allowed:
            raise OwnerSamplePackageError("manifest_source_inventory_invalid")
        name = row.get("name")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or "/" in name
            or "\\" in name
            or not SHA256_PATTERN.fullmatch(str(row.get("sha256") or ""))
        ):
            raise OwnerSamplePackageError("manifest_source_inventory_invalid")

    selected = manifest.get("selected_sources")
    if not isinstance(selected, dict) or set(selected) != {"h264", "hevc"}:
        raise OwnerSamplePackageError("manifest_source_inventory_invalid")
    by_name = {row["name"]: row["sha256"] for row in rows}
    for row in selected.values():
        if (
            not isinstance(row, dict)
            or set(row) != {"name", "sha256"}
            or not isinstance(row.get("name"), str)
            or Path(row["name"]).name != row["name"]
            or row.get("sha256") != by_name.get(row["name"])
        ):
            raise OwnerSamplePackageError("manifest_source_inventory_invalid")


def _validate_narration_evidence(package_root: Path, manifest: dict[str, Any]) -> None:
    narration = manifest.get("narration")
    if (
        not isinstance(narration, dict)
        or set(narration)
        != {
            "source_name",
            "source_sha256",
            "copy_path",
            "copy_sha256",
            "generated_locally",
        }
        or not isinstance(narration.get("source_name"), str)
        or Path(narration["source_name"]).name != narration["source_name"]
        or "/" in narration["source_name"]
        or "\\" in narration["source_name"]
        or not isinstance(narration.get("generated_locally"), bool)
        or not isinstance(narration.get("source_sha256"), str)
        or not SHA256_PATTERN.fullmatch(narration["source_sha256"])
        or narration.get("copy_sha256") != narration["source_sha256"]
    ):
        raise OwnerSamplePackageError("manifest_narration_invalid")
    try:
        copied = _safe_manifest_artifact_path(package_root, narration.get("copy_path"))
    except OwnerSamplePackageError as exc:
        raise OwnerSamplePackageError("manifest_narration_invalid") from exc
    if _sha256(copied) != narration["copy_sha256"]:
        raise OwnerSamplePackageError("manifest_narration_invalid")


def _validate_reverse_graph(manifest: dict[str, Any]) -> None:
    trace = manifest.get("reverse_trace")
    nodes = trace.get("nodes") if isinstance(trace, dict) else None
    if not isinstance(nodes, dict) or not nodes or len(nodes) > MAX_REVERSE_TRACE_NODES:
        raise OwnerSamplePackageError("manifest_reverse_trace_invalid")
    preview_proofs = manifest.get("preview_proofs")
    previews = preview_proofs.get("previews") if isinstance(preview_proofs, dict) else None
    if not isinstance(previews, dict):
        raise OwnerSamplePackageError("manifest_reverse_trace_invalid")
    expected_nodes = _build_reverse_trace(
        artifacts=manifest["artifacts"],
        narration=manifest["narration"],
        previews=previews,
        controls=manifest["controls"],
    )["nodes"]
    if set(nodes) != set(expected_nodes):
        raise OwnerSamplePackageError("manifest_reverse_trace_invalid")
    for node_id, node in nodes.items():
        if (
            not isinstance(node_id, str)
            or len(node_id) > 128
            or not isinstance(node, dict)
            or node != expected_nodes[node_id]
        ):
            raise OwnerSamplePackageError("manifest_reverse_trace_invalid")
        upstream = node.get("upstream")
        if (
            not isinstance(upstream, list)
            or len(upstream) > MAX_REVERSE_UPSTREAM
            or upstream != sorted(set(upstream))
            or any(not isinstance(parent, str) or parent not in nodes for parent in upstream)
        ):
            raise OwnerSamplePackageError("manifest_reverse_trace_invalid")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise OwnerSamplePackageError("manifest_reverse_trace_invalid")
        if node_id in visited:
            return
        visiting.add(node_id)
        for parent in nodes[node_id]["upstream"]:
            visit(parent)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(nodes):
        visit(node_id)
    artifact_node_ids = {f"artifact:{name}" for name in manifest["artifacts"]}
    required_shared_nodes = set(nodes) - artifact_node_ids
    for artifact_node_id in artifact_node_ids:
        reachable: set[str] = set()

        def collect(node_id: str) -> None:
            if node_id in reachable:
                return
            reachable.add(node_id)
            for parent in nodes[node_id]["upstream"]:
                collect(parent)

        collect(artifact_node_id)
        if not required_shared_nodes.issubset(reachable):
            raise OwnerSamplePackageError("manifest_reverse_trace_invalid")


def validate_reverse_manifest(package_root: Path, manifest: dict[str, Any]) -> None:
    """Validate internal provenance consistency, not cryptographic authenticity.

    A coordinated rewrite of every unsigned field is outside this package's trust
    model and would require a separately authorized signed receipt.
    """

    try:
        root = Path(package_root)
        if root.is_symlink() or _is_reparse_point(root):
            raise OwnerSamplePackageError("manifest_package_root_invalid")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise OwnerSamplePackageError("manifest_package_root_invalid")
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("manifest_package_root_invalid") from exc
    expected_top_level = {
        "schema_version",
        "isolated_package",
        "qa_fixture",
        "source_inventory",
        "selected_sources",
        "narration",
        "preview_proofs",
        "controls",
        "artifacts",
        "authorities",
        "reverse_trace",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != expected_top_level
        or manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION
        or manifest.get("isolated_package") is not True
        or manifest.get("qa_fixture") != "audio_ducking"
    ):
        raise OwnerSamplePackageError("manifest_schema_invalid")
    _validate_source_inventory(manifest)
    _validate_narration_evidence(root, manifest)
    _validate_manifest_preview_proofs(root, manifest)
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(artifacts, dict)
        or set(artifacts) != set(REVIEW_ARTIFACT_KEYS)
        or len(artifacts) > MAX_MANIFEST_ARTIFACTS
    ):
        raise OwnerSamplePackageError("manifest_artifacts_invalid")
    for row in artifacts.values():
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OwnerSamplePackageError("manifest_artifacts_invalid")
        artifact = _safe_manifest_artifact_path(root, row["path"])
        claimed_sha = row.get("sha256")
        if not isinstance(claimed_sha, str) or not SHA256_PATTERN.fullmatch(claimed_sha):
            raise OwnerSamplePackageError("manifest_artifact_sha_mismatch")
        if _sha256(artifact) != claimed_sha:
            raise OwnerSamplePackageError("manifest_artifact_sha_mismatch")
    expected_controls = {key: True for key in CONTROL_CHECKS}
    expected_authorities = {
        "owner_approval": False,
        "rights_approval": False,
        "desktop_edit": False,
        "desktop_export": False,
        "automatic_apply": False,
        "memory_write": False,
        "external_provider_calls": 0,
    }
    if manifest.get("controls") != expected_controls or manifest.get("authorities") != expected_authorities:
        raise OwnerSamplePackageError("manifest_authority_invalid")
    _validate_reverse_graph(manifest)


def _publish_manifest_atomic(package_root: Path, manifest: dict[str, Any]) -> Path:
    temporary = package_root / MANIFEST_TEMP_FILENAME
    final = package_root / MANIFEST_FILENAME
    try:
        if temporary.exists() or final.exists():
            raise OwnerSamplePackageError("manifest_already_exists")
        with temporary.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(manifest, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(final)
        return final
    except OwnerSamplePackageError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise OwnerSamplePackageError("manifest_publish_failed") from exc


def _validate_preview_proofs(
    *, selected: dict[str, SampleRecord], proofs: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(proofs, dict) or proofs.get("external_provider_calls") != 0:
        raise OwnerSamplePackageError("preview_provider_boundary_violated")
    previews = proofs.get("previews")
    if not isinstance(previews, dict) or set(previews) != {"h264", "hevc"}:
        raise OwnerSamplePackageError("preview_proof_invalid")
    for codec in ("h264", "hevc"):
        proof = previews.get(codec)
        record = selected[codec]
        if (
            not isinstance(proof, dict)
            or proof.get("source_name") != record.name
            or proof.get("source_sha256") != record.sha256
            or proof.get("project_copy_sha256") != record.sha256
            or proof.get("range_status") != 206
            or proof.get("output_video_codec") != "h264"
            or proof.get("output_pixel_format") != "yuv420p"
        ):
            raise OwnerSamplePackageError("preview_proof_invalid")
    return previews


def _resolve_manifest_project_copy(
    *, package_root: Path, project_id: str, storage_uri: str
) -> Path:
    prefix = f"local://projects/{project_id}/"
    if not storage_uri.startswith(prefix):
        raise OwnerSamplePackageError("manifest_project_copy_invalid")
    relative_text = storage_uri.removeprefix(prefix)
    relative = PurePosixPath(relative_text)
    windows = PureWindowsPath(relative_text)
    if (
        not relative_text
        or "\\" in relative_text
        or windows.drive
        or windows.root
        or relative.is_absolute()
        or relative.as_posix() != relative_text
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise OwnerSamplePackageError("manifest_project_copy_invalid")
    projects_root = package_root / "projects"
    try:
        if (
            not projects_root.is_dir()
            or projects_root.is_symlink()
            or _is_reparse_point(projects_root)
        ):
            raise OwnerSamplePackageError("manifest_project_copy_invalid")
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("manifest_project_copy_invalid") from exc
    project_relative = PurePosixPath("projects", project_id, *relative.parts)
    if _path_has_link_or_reparse(projects_root, project_relative):
        raise OwnerSamplePackageError("manifest_project_copy_invalid")
    try:
        projects_root = projects_root.resolve(strict=True)
        resolved = projects_root.joinpath(*project_relative.parts).resolve(strict=True)
        if not resolved.is_relative_to(projects_root) or not resolved.is_file():
            raise OwnerSamplePackageError("manifest_project_copy_invalid")
    except OwnerSamplePackageError:
        raise
    except OSError as exc:
        raise OwnerSamplePackageError("manifest_project_copy_invalid") from exc
    return resolved


def _validate_manifest_preview_proofs(package_root: Path, manifest: dict[str, Any]) -> None:
    proofs = manifest.get("preview_proofs")
    project_ref = proofs.get("project_ref") if isinstance(proofs, dict) else None
    project_parts = PurePosixPath(project_ref).parts if isinstance(project_ref, str) else ()
    if (
        not isinstance(proofs, dict)
        or set(proofs) != {
            "project_ref",
            "api_import_log",
            "previews",
            "external_provider_calls",
        }
        or proofs.get("external_provider_calls") != 0
        or len(project_parts) != 2
        or project_parts[0] != "projects"
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project_parts[1])
        or not isinstance(proofs.get("api_import_log"), list)
        or len(proofs["api_import_log"]) > 8
    ):
        raise OwnerSamplePackageError("manifest_preview_proof_invalid")
    project_id = project_parts[1]
    allowed_import_paths = {
        "/api/projects",
        "/api/projects/{project_id}/assets/broll-video",
    }
    if any(
        not isinstance(row, dict)
        or set(row) != {"method", "path"}
        or row.get("method") != "POST"
        or row.get("path") not in allowed_import_paths
        for row in proofs["api_import_log"]
    ):
        raise OwnerSamplePackageError("manifest_preview_proof_invalid")
    previews = proofs.get("previews")
    selected = manifest.get("selected_sources")
    inventory_rows = manifest.get("source_inventory")
    inventory = {
        row["name"]: row["sha256"]
        for row in inventory_rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    allowed = {
        "source_name",
        "source_sha256",
        "preview_source_sha256",
        "profile",
        "project_copy_ref",
        "project_copy_sha256",
        "content_sha256",
        "preview_kind",
        "content_url",
        "range_status",
        "output_video_codec",
        "output_pixel_format",
    }
    if not isinstance(previews, dict) or set(previews) != {"h264", "hevc"}:
        raise OwnerSamplePackageError("manifest_preview_proof_invalid")
    for codec, proof in previews.items():
        if not isinstance(proof, dict) or set(proof) != allowed:
            raise OwnerSamplePackageError("manifest_preview_proof_invalid")
        name = proof.get("source_name")
        hashes = (
            proof.get("source_sha256"),
            proof.get("preview_source_sha256"),
            proof.get("project_copy_sha256"),
            proof.get("content_sha256"),
        )
        content_url = proof.get("content_url")
        selected_row = selected.get(codec) if isinstance(selected, dict) else None
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or "/" in name
            or "\\" in name
            or any(not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value) for value in hashes)
            or not isinstance(proof.get("project_copy_ref"), str)
            or not proof["project_copy_ref"].startswith("local://projects/")
            or not isinstance(content_url, str)
            or not content_url.startswith("/api/projects/")
            or "://" in content_url
            or proof.get("range_status") != 206
            or proof.get("output_video_codec") != "h264"
            or proof.get("output_pixel_format") != "yuv420p"
            or proof.get("preview_kind") != ("original" if codec == "h264" else "proxy")
            or not isinstance(selected_row, dict)
            or name != selected_row.get("name")
            or proof.get("source_sha256") != selected_row.get("sha256")
            or inventory.get(name) != proof.get("source_sha256")
            or proof.get("preview_source_sha256") != proof.get("source_sha256")
            or proof.get("project_copy_sha256") != proof.get("source_sha256")
            or proof.get("profile") != BROWSER_PREVIEW_PROFILE
            or (
                codec == "h264"
                and proof.get("content_sha256") != proof.get("source_sha256")
            )
        ):
            raise OwnerSamplePackageError("manifest_preview_proof_invalid")
        project_copy = _resolve_manifest_project_copy(
            package_root=package_root,
            project_id=project_id,
            storage_uri=proof["project_copy_ref"],
        )
        if _sha256(project_copy) != proof["project_copy_sha256"]:
            raise OwnerSamplePackageError("manifest_project_copy_invalid")


def build_owner_sample_package(
    *,
    sample_dir: Path,
    output_root: Path,
    narration: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
    edit_flow_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inventory -> public API preview proof -> deterministic edit flow -> atomic manifest."""

    package_root = _prepare_package_root(
        sample_dir=Path(sample_dir), output_root=Path(output_root)
    )
    narration_row, narration_source_fence = _prepare_narration(
        narration=Path(narration),
        package_root=package_root,
        ffmpeg_binary=ffmpeg_binary,
        ffprobe_binary=ffprobe_binary,
    )
    selected_sources: dict[str, Path] = {}
    selected_fingerprints: dict[str, tuple[int, int, str]] = {}
    final_fences_verified = False
    try:
        records = inventory_samples(Path(sample_dir), ffprobe_binary=ffprobe_binary)
        selected = select_preview_inputs(records)
        selected_sources = {
            codec: _selected_source(Path(sample_dir), selected[codec])
            for codec in ("h264", "hevc")
        }
        selected_fingerprints = {
            codec: _source_fingerprint(path) for codec, path in selected_sources.items()
        }
        for codec in ("h264", "hevc"):
            fingerprint = selected_fingerprints[codec]
            if (
                fingerprint[0] != selected[codec].size_bytes
                or fingerprint[2] != selected[codec].sha256
            ):
                raise OwnerSamplePackageError("source_changed_during_package")

        preview_proofs = build_preview_proofs(
            sample_dir=Path(sample_dir),
            selected=selected,
            projects_root=package_root / "projects",
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
        )
        previews = _validate_preview_proofs(selected=selected, proofs=preview_proofs)
        runner = edit_flow_runner or _load_default_edit_flow_runner()
        edit_result = runner(
            narration=package_root / narration_row["copy_path"],
            work_root=package_root / "edit",
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
            fixture_name="audio_ducking",
        )
        controls = _validate_edit_result(edit_result)
        checklist = write_review_checklist(package_root)
        artifacts = _artifact_evidence_from_edit(
            package_root=package_root,
            edit_result=edit_result,
            checklist_path=checklist,
        )
        manifest: dict[str, Any] = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "isolated_package": True,
            "qa_fixture": "audio_ducking",
            "source_inventory": [asdict(record) for record in records],
            "selected_sources": {
                codec: {"name": selected[codec].name, "sha256": selected[codec].sha256}
                for codec in ("h264", "hevc")
            },
            "narration": narration_row,
            "preview_proofs": preview_proofs,
            "controls": controls,
            "artifacts": artifacts,
            "authorities": {
                "owner_approval": False,
                "rights_approval": False,
                "desktop_edit": False,
                "desktop_export": False,
                "automatic_apply": False,
                "memory_write": False,
                "external_provider_calls": 0,
            },
        }
        manifest["reverse_trace"] = _build_reverse_trace(
            artifacts=artifacts,
            narration=narration_row,
            previews=previews,
            controls=controls,
        )
        _assert_final_source_fence(selected_sources, selected_fingerprints)
        _assert_narration_source_fence(narration_source_fence)
        final_fences_verified = True
        validate_reverse_manifest(package_root, manifest)
        _publish_manifest_atomic(package_root, manifest)
        return manifest
    finally:
        if selected_sources and not final_fences_verified:
            _assert_final_source_fence(selected_sources, selected_fingerprints)
        if not final_fences_verified:
            _assert_narration_source_fence(narration_source_fence)
