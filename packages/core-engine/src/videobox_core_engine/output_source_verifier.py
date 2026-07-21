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


def capture_output_source_snapshots(*, store: Any, project_id: str, timeline: dict[str, Any]) -> tuple[OutputSourceSnapshot, ...]:
    """Snapshot every concrete project asset consumed by the composition.

    A persisted expected SHA/revision is validated when present, but cannot be
    a prerequisite for fencing an actual base or legacy clip.  Capture the
    current SHA and revision for every project asset in tracks and export
    overlays so final publication cannot make an output from replaced bytes
    observable merely because an older timeline lacks Task-11 identity fields.
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
        actual_digest = _sha256_streaming(path, digests_by_path)
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


def verify_output_sources(*, store: Any, project_id: str, timeline: dict[str, Any]) -> None:
    """Verify all materialized timeline sources before output work begins."""
    verify_output_source_snapshots(capture_output_source_snapshots(
        store=store, project_id=project_id, timeline=timeline,
    ))


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


def verify_output_freshness(*, editing_session: dict[str, Any] | None, timeline: dict[str, Any], subtitle: dict[str, Any] | None = None, review: dict[str, Any] | None = None) -> None:
    """Reject stale output dependencies before an artifact is reused/exported."""
    if editing_session is not None:
        current_revision = int(editing_session.get("session_revision") or 0)
        expected_revision = timeline.get("source_session_revision")
        if expected_revision is None:
            raise OutputSourceStaleError("editing session revision is unstamped")
        if int(expected_revision) != current_revision:
            raise OutputSourceStaleError("editing session revision changed")
    for name, artifact in (("review", review), ("subtitle", subtitle)):
        if artifact is not None:
            if not bool(artifact.get("is_current", True)):
                raise OutputSourceStaleError(f"{name} freshness changed")
            if editing_session is not None:
                artifact_revision = artifact.get("source_session_revision")
                if artifact_revision is None or int(artifact_revision) != current_revision:
                    raise OutputSourceStaleError(f"{name} session revision changed")


__all__ = [
    "OutputSourceSnapshot",
    "OutputSourceStaleError",
    "capture_output_source_snapshots",
    "verify_output_freshness",
    "verify_output_source_snapshots",
    "verify_output_sources",
]
