from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite
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
    target_duration_sec: float | None = None


def resolve_generic_asset_uri(*, store: Any, project_id: str, asset_uri: str) -> Path:
    asset_match = _ASSET_URI_PATTERN.match(asset_uri)
    if asset_match:
        asset = store.get_asset(project_id=project_id, asset_id=asset_match.group("asset_id"))
        return store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
    return store.resolve_storage_uri(project_id=project_id, storage_uri=asset_uri)


def _explicit_narration_source_bounds(clip: dict[str, Any]) -> tuple[float, float] | None:
    has_source_in = "source_in_sec" in clip
    has_source_out = "source_out_sec" in clip
    if not has_source_in and not has_source_out:
        return None
    if not has_source_in or not has_source_out:
        raise TimelineClipSourceError(
            "Explicit narration source bounds require both source_in_sec and source_out_sec."
        )
    try:
        source_in = float(clip["source_in_sec"])
        source_out = float(clip["source_out_sec"])
    except (TypeError, ValueError) as exc:
        raise TimelineClipSourceError("Explicit narration source bounds must be finite numbers.") from exc
    if not isfinite(source_in) or not isfinite(source_out):
        raise TimelineClipSourceError("Explicit narration source bounds must be finite numbers.")
    if source_in < 0 or source_out <= source_in:
        raise TimelineClipSourceError(
            "Explicit narration source bounds must be nonnegative and source_out_sec must follow source_in_sec."
        )
    return source_in, source_out


def resolve_narration_clip_source(
    *, store: Any, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
) -> ResolvedClipSource:
    asset_uri = str(clip.get("asset_uri") or "")
    source_bounds = _explicit_narration_source_bounds(clip)
    target_duration = float(clip["end_sec"]) - float(clip["start_sec"])
    segment_match = _SEGMENT_URI_PATTERN.match(asset_uri)
    if segment_match:
        narration_source_uri = timeline.get("narration_source_uri")
        if not narration_source_uri:
            raise TimelineClipSourceError(
                f"Timeline has no narration_source_uri to resolve narration clip '{asset_uri}'."
            )
        path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(narration_source_uri))
        if source_bounds is not None:
            source_in, source_out = source_bounds
            return ResolvedClipSource(
                path=path,
                trim_start_sec=source_in,
                trim_duration_sec=source_out - source_in,
                target_duration_sec=target_duration,
            )
        return ResolvedClipSource(
            path=path,
            trim_start_sec=float(clip["start_sec"]),
            trim_duration_sec=target_duration,
            target_duration_sec=target_duration,
        )
    # A TTS-replacement (or any other override) asset is its own standalone
    # clip, not a slice of the original recording — play it in full rather
    # than guessing a trim window that might cut off synthesized speech.
    path = resolve_generic_asset_uri(store=store, project_id=project_id, asset_uri=asset_uri)
    if source_bounds is not None:
        source_in, source_out = source_bounds
        return ResolvedClipSource(
            path=path,
            trim_start_sec=source_in,
            trim_duration_sec=source_out - source_in,
            target_duration_sec=target_duration,
        )
    return ResolvedClipSource(
        path=path,
        trim_start_sec=0.0,
        trim_duration_sec=None,
        target_duration_sec=target_duration,
    )


def resolve_broll_clip_source(*, store: Any, project_id: str, clip: dict[str, Any]) -> ResolvedClipSource:
    path = resolve_generic_asset_uri(store=store, project_id=project_id, asset_uri=str(clip.get("asset_uri") or ""))
    duration = float(clip["end_sec"]) - float(clip["start_sec"])
    return ResolvedClipSource(
        path=path,
        trim_start_sec=0.0,
        trim_duration_sec=duration,
        target_duration_sec=duration,
    )


__all__ = [
    "ResolvedClipSource",
    "TimelineClipSourceError",
    "resolve_broll_clip_source",
    "resolve_generic_asset_uri",
    "resolve_narration_clip_source",
]
