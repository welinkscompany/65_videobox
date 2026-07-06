from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ASSET_URI_PATTERN = re.compile(r"^local://projects/[^/]+/assets/(?P<asset_id>[^/]+)$")
_SEGMENT_URI_PATTERN = re.compile(r"^local://projects/[^/]+/segments/(?P<segment_id>[^/]+)$")


class TimelineClipSourceError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class ResolvedClipSource:
    path: Path
    trim_start_sec: float
    trim_duration_sec: float | None  # None means "use the source's natural length"


def resolve_generic_asset_uri(*, store: Any, project_id: str, asset_uri: str) -> Path:
    asset_match = _ASSET_URI_PATTERN.match(asset_uri)
    if asset_match:
        asset = store.get_asset(project_id=project_id, asset_id=asset_match.group("asset_id"))
        return store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
    return store.resolve_storage_uri(project_id=project_id, storage_uri=asset_uri)


def resolve_narration_clip_source(
    *, store: Any, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
) -> ResolvedClipSource:
    asset_uri = str(clip.get("asset_uri") or "")
    segment_match = _SEGMENT_URI_PATTERN.match(asset_uri)
    if segment_match:
        narration_source_uri = timeline.get("narration_source_uri")
        if not narration_source_uri:
            raise TimelineClipSourceError(
                f"Timeline has no narration_source_uri to resolve narration clip '{asset_uri}'."
            )
        path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(narration_source_uri))
        return ResolvedClipSource(
            path=path,
            trim_start_sec=float(clip["start_sec"]),
            trim_duration_sec=float(clip["end_sec"]) - float(clip["start_sec"]),
        )
    # A TTS-replacement (or any other override) asset is its own standalone
    # clip, not a slice of the original recording — play it in full rather
    # than guessing a trim window that might cut off synthesized speech.
    path = resolve_generic_asset_uri(store=store, project_id=project_id, asset_uri=asset_uri)
    return ResolvedClipSource(path=path, trim_start_sec=0.0, trim_duration_sec=None)


def resolve_broll_clip_source(*, store: Any, project_id: str, clip: dict[str, Any]) -> ResolvedClipSource:
    path = resolve_generic_asset_uri(store=store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
    duration = float(clip["end_sec"]) - float(clip["start_sec"])
    return ResolvedClipSource(path=path, trim_start_sec=0.0, trim_duration_sec=duration)


__all__ = [
    "ResolvedClipSource",
    "TimelineClipSourceError",
    "resolve_broll_clip_source",
    "resolve_generic_asset_uri",
    "resolve_narration_clip_source",
]
