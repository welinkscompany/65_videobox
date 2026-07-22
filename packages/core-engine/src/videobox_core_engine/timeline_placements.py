"""Pure contracts for independently placed non-narration timeline items."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from math import isfinite
from typing import Any


PLACEMENT_KINDS = frozenset({"broll", "bgm", "sfx", "overlay", "caption"})


def placement_id(*, kind: str, base_id: str) -> str:
    if kind not in PLACEMENT_KINDS or not base_id.strip():
        raise ValueError("timeline_placement_identity_invalid")
    return f"{kind}:{base_id}"


def collect_timeline_placements(*, timeline: dict[str, object]) -> dict[str, dict[str, object]]:
    """Collect base placements without reading or mutating session overrides."""
    result: dict[str, dict[str, object]] = {}
    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        raise ValueError("timeline_placement_tracks_invalid")
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError("timeline_placement_tracks_invalid")
        kind = str(track.get("track_type") or "")
        if kind not in PLACEMENT_KINDS - {"caption"}:
            continue
        clips = track.get("clips")
        if not isinstance(clips, list):
            raise ValueError("timeline_placement_clips_invalid")
        for clip in clips:
            if not isinstance(clip, dict):
                raise ValueError("timeline_placement_clips_invalid")
            _add_placement(result=result, kind=kind, base_id=str(clip.get("clip_id") or ""), start=clip.get("start_sec"), end=clip.get("end_sec"))
    captions = timeline.get("session_captions")
    if captions is None:
        captions = timeline.get("caption_segments", [])
    if not isinstance(captions, list):
        raise ValueError("timeline_placement_captions_invalid")
    for caption in captions:
        if not isinstance(caption, dict):
            raise ValueError("timeline_placement_captions_invalid")
        _add_placement(result=result, kind="caption", base_id=str(caption.get("caption_id") or ""), start=caption.get("start_sec"), end=caption.get("end_sec"))
    return {key: result[key] for key in sorted(result)}


def apply_placement_changes(
    *,
    placements: dict[str, dict[str, object]],
    changes: list[dict[str, object]],
    output_duration_sec: float,
    fps_num: int,
    fps_den: int,
) -> dict[str, dict[str, object]]:
    """Validate and half-up quantize one final batch without silent clamping."""
    if not changes:
        raise ValueError("timeline_placement_changes_required")
    output_frames = _seconds_to_frame(output_duration_sec, fps_num=fps_num, fps_den=fps_den)
    if output_frames < 1:
        raise ValueError("timeline_placement_output_invalid")
    normalized: dict[str, dict[str, object]] = {}
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("timeline_placement_change_invalid")
        identifier = str(change.get("placement_id") or "")
        if identifier in normalized:
            raise ValueError("timeline_placement_duplicate")
        existing = placements.get(identifier)
        if existing is None:
            raise ValueError("timeline_placement_unknown")
        kind = str(change.get("kind") or "")
        if kind != existing.get("kind"):
            raise ValueError("timeline_placement_kind_mismatch")
        start = _finite_seconds(change.get("start_sec"))
        end = _finite_seconds(change.get("end_sec"))
        if start < 0 or end > output_duration_sec:
            raise ValueError("timeline_placement_out_of_range")
        start_frame = _seconds_to_frame(start, fps_num=fps_num, fps_den=fps_den)
        end_frame = _seconds_to_frame(end, fps_num=fps_num, fps_den=fps_den)
        if start_frame < 0 or end_frame > output_frames:
            raise ValueError("timeline_placement_out_of_range")
        if end_frame - start_frame < 1:
            raise ValueError("timeline_placement_frame_span_invalid")
        normalized[identifier] = {
            "placement_id": identifier,
            "kind": kind,
            "start_sec": _frame_to_seconds(start_frame, fps_num=fps_num, fps_den=fps_den),
            "end_sec": _frame_to_seconds(end_frame, fps_num=fps_num, fps_den=fps_den),
        }
    return {key: normalized[key] for key in sorted(normalized)}


def apply_timeline_placement_overrides(*, timeline: dict[str, object], overrides: dict[str, dict[str, object]]) -> dict[str, object]:
    """Apply already validated override times while preserving every other field."""
    materialized = deepcopy(timeline)
    if not overrides:
        return materialized
    placements = collect_timeline_placements(timeline=materialized)
    expected = set(placements)
    for identifier, override in overrides.items():
        if identifier not in expected or not isinstance(override, dict):
            raise ValueError("timeline_placement_unknown")
        if str(override.get("placement_id") or "") != identifier or override.get("kind") != placements[identifier]["kind"]:
            raise ValueError("timeline_placement_kind_mismatch")
    for track in materialized["tracks"]:  # collect_timeline_placements validates the shape above
        if not isinstance(track, dict):
            continue
        kind = str(track.get("track_type") or "")
        if kind not in PLACEMENT_KINDS - {"caption"}:
            continue
        for clip in track.get("clips", []) if isinstance(track.get("clips"), list) else []:
            if not isinstance(clip, dict):
                continue
            override = overrides.get(placement_id(kind=kind, base_id=str(clip.get("clip_id") or "")))
            if override:
                clip["start_sec"], clip["end_sec"] = override["start_sec"], override["end_sec"]
    captions = materialized.get("session_captions")
    if captions is None:
        captions = materialized.get("caption_segments", [])
    for caption in captions if isinstance(captions, list) else []:
        if not isinstance(caption, dict):
            continue
        override = overrides.get(placement_id(kind="caption", base_id=str(caption.get("caption_id") or "")))
        if override:
            caption["start_sec"], caption["end_sec"] = override["start_sec"], override["end_sec"]
    return materialized


def _add_placement(*, result: dict[str, dict[str, object]], kind: str, base_id: str, start: object, end: object) -> None:
    identifier = placement_id(kind=kind, base_id=base_id)
    if identifier in result:
        raise ValueError("timeline_placement_duplicate")
    start_sec, end_sec = _finite_seconds(start), _finite_seconds(end)
    if start_sec < 0 or end_sec <= start_sec:
        raise ValueError("timeline_placement_bounds_invalid")
    result[identifier] = {"placement_id": identifier, "kind": kind, "start_sec": start_sec, "end_sec": end_sec}


def _finite_seconds(value: object) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("timeline_placement_not_finite") from exc
    if not isfinite(result):
        raise ValueError("timeline_placement_not_finite")
    return result


def _seconds_to_frame(seconds: float, *, fps_num: int, fps_den: int) -> int:
    if not isfinite(seconds):
        raise ValueError("timeline_placement_not_finite")
    if fps_num <= 0 or fps_den <= 0:
        raise ValueError("timeline_placement_fps_invalid")
    value = Fraction(str(seconds)) * fps_num / fps_den
    return (value.numerator * 2 + value.denominator) // (value.denominator * 2)


def _frame_to_seconds(frame: int, *, fps_num: int, fps_den: int) -> float:
    return float(Fraction(frame * fps_den, fps_num))
