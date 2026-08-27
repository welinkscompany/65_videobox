"""Fail-closed, shared validation for files consumed by output renderers.

The proposal apply path records an immutable SHA next to the materialized
asset reference.  Every output producer calls this module before it creates
an artifact, so a replaced file cannot become a preview, FFmpeg render, or
CapCut draft by accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import re


class OutputSourceStaleError(ValueError):
    """One stable identity for every post-materialization source mismatch."""

    code = "stale_output_asset"

    def __init__(self, reason: str) -> None:
        super().__init__(f"{self.code}: {reason}")


_ASSET_URI = re.compile(r"^local://projects/(?P<project_id>[^/]+)/assets/(?P<asset_id>[^/]+)$")
_SEGMENT_URI = re.compile(r"^local://projects/[^/]+/segments/[^/]+$")


@dataclass(frozen=True)
class OutputSourceSnapshot:
    """A verified project-local source that can be rechecked without SQLite."""

    path: Path
    expected_content_sha256: str | None
    asset_id: str | None
    expected_media_revision: str | None


def capture_output_source_snapshots(
    *, store: Any, project_id: str, timeline: dict[str, Any],
    hash_cache: dict[tuple[Path, int], str] | None = None,
) -> tuple[OutputSourceSnapshot, ...]:
    """Snapshot every concrete project asset consumed by the composition.

    A persisted expected SHA/revision is validated when present, but cannot be
    a prerequisite for fencing an actual base or legacy clip.  Capture the
    current SHA and revision for every project asset in tracks and export
    overlays so final publication cannot make an output from replaced bytes
    observable merely because an older timeline lacks Task-11 identity fields.

    ``hash_cache`` is an optional, caller-owned ``(path, mtime_ns) -> sha256``
    cache (same shape as ``FfmpegFinalRenderer._stream_probe_cache``). A
    changed file always changes mtime, so a cache hit is exactly as trustworthy
    as a fresh read. Omit it (default) and this hashes fresh every call, same
    as before. This hashing is unrelated to (and on top of) the exact-preview
    pipeline's own hash pass over the same files (``local_pipeline.py``'s
    ``_exact_preview_asset_hash_cache``) -- the two do not share a cache.

    2026-08-28: a single ``render_exact_preview_to_mp4`` call was measured
    hashing the same handful of project-local sources here in ~3.2s with no
    cache, ~2.5s of which was one real (546MB) source's first full read.
    Passing ``FfmpegFinalRenderer._output_source_hash_cache`` in only helps
    *within* one such call right now -- ``render_exact_preview_to_mp4``
    builds its proxy renderer with ``dataclasses.replace(self, ...)``, and
    `replace()` re-runs every ``init=False`` field's ``default_factory``,
    so this cache (and the pre-existing ``_stream_probe_cache``) starts
    empty again on every render. Making it survive across renders needs a
    separate fix to that construction, not this function.
    """
    root = store.project_root(project_id).resolve()
    digests_by_path: dict[Path, str] = {}
    snapshots: dict[Path, OutputSourceSnapshot] = {}
    inputs: list[tuple[str, dict[str, Any]]] = []
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        clips = track.get("clips", [])
        if not isinstance(clips, list):
            continue
        track_type = str(track.get("track_type") or "")
        inputs.extend((track_type, clip) for clip in clips if isinstance(clip, dict))
    inputs.extend(("export_overlay", overlay) for overlay in timeline.get("export_overlays", []) if isinstance(overlay, dict))
    for track_type, clip in inputs:
        expected = str(clip.get("expected_content_sha256") or "").strip().lower()
        expected_revision = str(clip.get("media_revision") or "").strip()
        uri = str(clip.get("asset_uri") or "")
        asset_id = str(clip.get("asset_id") or "")
        if _SEGMENT_URI.match(uri):
            if track_type != "narration":
                raise OutputSourceStaleError("segment source is only valid for narration")
            # A virtual narration segment is rendered from this timeline's
            # actual narration source, not from a standalone segment file.
            uri = str(timeline.get("narration_source_uri") or "")
            asset_id = ""
            if not uri or _SEGMENT_URI.match(uri):
                raise OutputSourceStaleError("segment narration source has no registered asset identity")
        if not uri and asset_id:
            uri = f"local://projects/{project_id}/assets/{asset_id}"
        match = _ASSET_URI.match(uri)
        if not asset_id and match is not None:
            asset_id = match.group("asset_id")
        if not asset_id and not match:
            # A direct local URI is renderable too, so it must bind back to a
            # registered asset before it can participate in output.  Do not
            # let legacy identity omission turn that source into a fail-open.
            if uri.startswith(f"local://projects/{project_id}/") and not _SEGMENT_URI.match(uri):
                try:
                    asset = next(
                        candidate for candidate in store.list_assets(project_id=project_id)
                        if str(candidate.get("storage_uri") or "") == uri
                    )
                except (OSError, ValueError) as exc:
                    raise OutputSourceStaleError("materialized source is missing or unavailable") from exc
                except StopIteration as exc:
                    raise OutputSourceStaleError("materialized source has no registered asset identity") from exc
                asset_id = str(asset["asset_id"])
            else:
                # Text-only overlays and segment-backed narration have no
                # standalone project asset to fingerprint on this path.
                if expected or expected_revision:
                    raise OutputSourceStaleError("materialized source has no project asset identity")
                continue
        if match is not None and (
            match.group("project_id") != project_id or match.group("asset_id") != asset_id
        ):
            raise OutputSourceStaleError("asset identity does not match source URI")
        try:
            asset = store.get_asset(project_id=project_id, asset_id=asset_id)
            path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"])).resolve()
            uri_path = (
                None if match is not None
                else store.resolve_storage_uri(project_id=project_id, storage_uri=uri).resolve()
            )
        except (KeyError, OSError, ValueError) as exc:
            raise OutputSourceStaleError("materialized source is missing or unavailable") from exc
        if uri_path is not None and uri_path != path:
            raise OutputSourceStaleError("asset identity does not match source URI")
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise OutputSourceStaleError("materialized source is not project-local") from exc
        if not path.is_file():
            raise OutputSourceStaleError("materialized source is missing")
        actual_digest = _cached_or_streamed_sha256(path, digests_by_path, hash_cache)
        if expected and actual_digest != expected:
            raise OutputSourceStaleError("content SHA-256 changed")
        actual_revision = str(asset.get("created_at") or "")
        if expected_revision and actual_revision != expected_revision:
            raise OutputSourceStaleError("media revision changed")
        snapshots[path] = OutputSourceSnapshot(
            path=path,
            expected_content_sha256=expected or actual_digest,
            asset_id=asset_id,
            expected_media_revision=expected_revision or actual_revision,
        )
    return tuple(snapshots.values())


def verify_output_source_snapshots(
    snapshots: tuple[OutputSourceSnapshot, ...],
    *,
    media_revision_lookup: Callable[[str], str | None] | None = None,
) -> None:
    """Recheck captured source expectations without opening another store connection."""
    digests_by_path: dict[Path, str] = {}
    for snapshot in snapshots:
        if not snapshot.path.is_file():
            raise OutputSourceStaleError("materialized source is missing")
        if (
            snapshot.expected_content_sha256 is not None
            and _sha256_streaming(snapshot.path, digests_by_path) != snapshot.expected_content_sha256
        ):
            raise OutputSourceStaleError("content SHA-256 changed")
        if snapshot.expected_media_revision is not None and media_revision_lookup is not None:
            if media_revision_lookup(str(snapshot.asset_id or "")) != snapshot.expected_media_revision:
                raise OutputSourceStaleError("media revision changed")


def verify_output_sources(
    *, store: Any, project_id: str, timeline: dict[str, Any],
    hash_cache: dict[tuple[Path, int], str] | None = None,
) -> None:
    """Verify all materialized timeline sources before output work begins.

    2026-08-28: this used to call ``verify_output_source_snapshots`` right
    after ``capture_output_source_snapshots`` with zero elapsed time in
    between -- capture already raises ``OutputSourceStaleError`` on any
    expected-vs-actual sha mismatch while it hashes, so re-hashing the same
    bytes microseconds later could only ever agree with itself. Measured on
    my-project: that immediate re-verify cost ~2.3s of a ~5.5s call for no
    protection. The real "capture, do work, then recheck" fence this file
    also provides is unaffected -- it lives at its own call sites
    (``local_pipeline.py``), which capture before work and call
    ``verify_output_source_snapshots`` again afterward, when real time (and
    therefore real risk of the file changing) has actually elapsed.
    """
    capture_output_source_snapshots(
        store=store, project_id=project_id, timeline=timeline, hash_cache=hash_cache,
    )


def _sha256_streaming(path: Path, digests_by_path: dict[Path, str]) -> str:
    """Hash each output source once per verifier pass without whole-file reads."""
    cached = digests_by_path.get(path)
    if cached is not None:
        return cached
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    digests_by_path[path] = value
    return value


def _cached_or_streamed_sha256(
    path: Path, digests_by_path: dict[Path, str], hash_cache: dict[tuple[Path, int], str] | None,
) -> str:
    """As ``_sha256_streaming``, but backed by an optional caller-owned
    ``(path, mtime_ns)`` cache that can outlive a single call (see
    ``capture_output_source_snapshots``)."""
    if hash_cache is None:
        return _sha256_streaming(path, digests_by_path)
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return _sha256_streaming(path, digests_by_path)
    key = (path, mtime_ns)
    cached = hash_cache.get(key)
    if cached is not None:
        return cached
    digest = _sha256_streaming(path, digests_by_path)
    hash_cache[key] = digest
    return digest


def verify_output_freshness(*, editing_session: dict[str, Any] | None, timeline: dict[str, Any], subtitle: dict[str, Any] | None = None, review: dict[str, Any] | None = None, variant: dict[str, Any] | None = None) -> None:
    """Reject stale output dependencies before an artifact is reused/exported."""
    if editing_session is not None:
        current_session_id = str(editing_session.get("session_id") or "")
        if not current_session_id:
            raise OutputSourceStaleError("editing session identity is unstamped")
        current_revision = int(editing_session.get("session_revision") or 0)
        expected_session_id = str(timeline.get("source_session_id") or "")
        if not expected_session_id:
            raise OutputSourceStaleError("editing session identity is unstamped")
        if expected_session_id != current_session_id:
            raise OutputSourceStaleError("editing session changed")
        expected_revision = timeline.get("source_session_revision")
        if expected_revision is None:
            raise OutputSourceStaleError("editing session revision is unstamped")
        if int(expected_revision) != current_revision:
            raise OutputSourceStaleError("editing session revision changed")
    timeline_has_variant_identity = bool(
        timeline.get("source_variant_id")
        or timeline.get("source_variant_revision") is not None
    )
    if timeline_has_variant_identity and variant is None:
        raise OutputSourceStaleError("variant identity is unstamped")
    for name, artifact in (("review", review), ("subtitle", subtitle)):
        if artifact is not None:
            if not bool(artifact.get("is_current", True)):
                raise OutputSourceStaleError(f"{name} freshness changed")
            if editing_session is not None:
                artifact_session_id = str(artifact.get("source_session_id") or "")
                if not artifact_session_id:
                    raise OutputSourceStaleError(
                        f"{name} session identity is unstamped"
                    )
                if artifact_session_id != current_session_id:
                    raise OutputSourceStaleError(f"{name} session changed")
                artifact_revision = artifact.get("source_session_revision")
                if artifact_revision is None or int(artifact_revision) != current_revision:
                    raise OutputSourceStaleError(f"{name} session revision changed")
    if variant is not None:
        expected_variant_id = str(timeline.get("source_variant_id") or "")
        expected_variant_revision = timeline.get("source_variant_revision")
        current_variant_id = str(variant.get("variant_id") or "")
        current_variant_revision = variant.get("variant_revision")
        if not expected_variant_id or expected_variant_revision is None:
            raise OutputSourceStaleError("variant identity is unstamped")
        if expected_variant_id != current_variant_id:
            raise OutputSourceStaleError("variant changed")
        if int(expected_variant_revision) != int(current_variant_revision or 0):
            raise OutputSourceStaleError("variant revision changed")
        if (
            str(variant.get("source_session_id") or "")
            != str(timeline.get("source_session_id") or "")
            or int(variant.get("source_session_revision") or 0)
            != int(timeline.get("source_session_revision") or 0)
        ):
            raise OutputSourceStaleError("variant source lineage changed")
        if editing_session is not None and (
            str(variant.get("source_session_id") or "")
            != str(editing_session.get("session_id") or "")
            or int(variant.get("source_session_revision") or 0)
            != int(editing_session.get("session_revision") or 0)
        ):
            raise OutputSourceStaleError("variant source session changed")


__all__ = [
    "OutputSourceSnapshot",
    "OutputSourceStaleError",
    "capture_output_source_snapshots",
    "verify_output_freshness",
    "verify_output_source_snapshots",
    "verify_output_sources",
]
