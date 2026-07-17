"""Fail-closed, shared validation for files consumed by output renderers.

The proposal apply path records an immutable SHA next to the materialized
asset reference.  Every output producer calls this module before it creates
an artifact, so a replaced file cannot become a preview, FFmpeg render, or
CapCut draft by accident.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any
import re


class OutputSourceStaleError(ValueError):
    """One stable identity for every post-materialization source mismatch."""

    code = "stale_output_asset"

    def __init__(self, reason: str) -> None:
        super().__init__(f"{self.code}: {reason}")


_ASSET_URI = re.compile(r"^local://projects/[^/]+/assets/(?P<asset_id>[^/]+)$")


def verify_output_sources(*, store: Any, project_id: str, timeline: dict[str, Any]) -> None:
    """Verify all materialized timeline sources before output work begins.

    Only clips carrying an immutable expectation are constrained.  Legacy
    timelines remain readable, while every Task-11 materialized candidate is
    fail-closed for project locality, SHA and (where supplied) media revision.
    """
    root = store.project_root(project_id).resolve()
    digests_by_path: dict[Path, str] = {}
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        clips = track.get("clips", [])
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            expected = str(clip.get("expected_content_sha256") or "").strip().lower()
            expected_revision = str(clip.get("media_revision") or "").strip()
            if not expected and not expected_revision:
                continue
            uri = str(clip.get("asset_uri") or "")
            match = _ASSET_URI.match(uri)
            asset_id = str(clip.get("asset_id") or (match.group("asset_id") if match else ""))
            if not asset_id:
                raise OutputSourceStaleError("materialized source has no project asset identity")
            if match is not None and match.group("asset_id") != asset_id:
                raise OutputSourceStaleError("asset identity does not match source URI")
            try:
                asset = store.get_asset(project_id=project_id, asset_id=asset_id)
                path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"])).resolve()
                uri_path = store.resolve_storage_uri(project_id=project_id, storage_uri=uri).resolve()
            except (KeyError, OSError, ValueError) as exc:
                raise OutputSourceStaleError("materialized source is unavailable") from exc
            if uri_path != path:
                raise OutputSourceStaleError("asset identity does not match source URI")
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise OutputSourceStaleError("materialized source is not project-local") from exc
            if not path.is_file():
                raise OutputSourceStaleError("materialized source is missing")
            if expected and _sha256_streaming(path, digests_by_path) != expected:
                raise OutputSourceStaleError("content SHA-256 changed")
            if expected_revision and str(asset.get("created_at") or "") != expected_revision:
                raise OutputSourceStaleError("media revision changed")


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


__all__ = ["OutputSourceStaleError", "verify_output_freshness", "verify_output_sources"]
