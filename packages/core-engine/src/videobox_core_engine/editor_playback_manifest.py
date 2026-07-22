"""Pure, seconds-based contract for the editor playback boundary.

This deliberately has no renderer, filesystem, or HTTP dependency.  The API
layer supplies the already project-scoped session and timeline documents.
"""
from __future__ import annotations

from fractions import Fraction
from math import floor
from typing import Any

from videobox_domain_models.caption_style import CaptionStyle
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.timeline_placements import placement_id


DEFAULT_FPS_NUM = 30
DEFAULT_FPS_DEN = 1
TRACK_ROLES = frozenset({"narration", "broll", "bgm", "sfx", "overlay"})


def seconds_to_frame(seconds: float, *, fps_num: int, fps_den: int) -> int:
    """Half-up conversion for non-negative seconds; frames never enter the DTO."""
    if seconds < 0 or fps_num <= 0 or fps_den <= 0:
        raise ValueError("editor_manifest_invalid_timebase")
    # UI JSON arrives as decimal floats.  Recover the intended small rational
    # before applying the specified half-up formula so 1/60 is not rounded
    # down merely because binary floating point renders it as 0.499999999999.
    canonical_seconds = Fraction(seconds).limit_denominator(1_000_000_000)
    return floor(canonical_seconds * fps_num / fps_den + Fraction(1, 2))


def frame_to_seconds(frame: int, *, fps_num: int, fps_den: int) -> float:
    if frame < 0 or fps_num <= 0 or fps_den <= 0:
        raise ValueError("editor_manifest_invalid_timebase")
    return float(Fraction(frame * fps_den, fps_num))


def build_editor_playback_manifest(
    *,
    project_id: str,
    session: dict[str, Any],
    timeline: dict[str, Any],
    asset_content_url_prefix: str,
    exact_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Join one explicit session and its matching timeline into a view contract."""
    if str(session.get("project_id")) != project_id or str(timeline.get("project_id")) != project_id:
        raise KeyError("editor_manifest_project_mismatch")
    if str(session.get("timeline_id")) != str(timeline.get("timeline_id")):
        raise ValueError("editor_manifest_timeline_mismatch")
    # Validate persisted source roles before materialization.  The materializer
    # intentionally only emits renderer-supported tracks, so validating after
    # it would otherwise turn an invalid stored role into a silent omission.
    for item in timeline.get("tracks", []):
        if isinstance(item, dict):
            _track_contract(item)
    fps_num = _positive_int(timeline.get("fps_num"), DEFAULT_FPS_NUM)
    fps_den = _positive_int(timeline.get("fps_den"), DEFAULT_FPS_DEN)
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=session, project_id=project_id)
    output = materialized.get("output") if isinstance(materialized.get("output"), dict) else {}
    segments = materialized.get("session_captions") if isinstance(materialized.get("session_captions"), list) else []
    raw_style = session.get("caption_style") if isinstance(session.get("caption_style"), dict) else {}
    style = CaptionStyle.from_dict(raw_style).to_dict()
    source_session_id = timeline.get("source_session_id")
    source_revision = timeline.get("source_session_revision")
    session_revision = int(session.get("session_revision") or 1)
    source_status = "current" if source_session_id == session.get("session_id") and source_revision == session_revision else "stale"
    tracks = [contract for item in materialized.get("tracks", []) if isinstance(item, dict) if (contract := _track_contract(item)) is not None]
    asset_ids = sorted({str(clip["asset_id"]) for track in tracks for clip in track["clips"] if clip.get("asset_id")})
    preview = dict(exact_preview or {"status": "unavailable", "url": None, "source_session_revision": None})
    return {
        "project_id": project_id,
        "session_id": str(session["session_id"]),
        "timeline_id": str(timeline["timeline_id"]),
        "session_revision": session_revision,
        "timeline_version": str(timeline.get("version") or "v001"),
        "timebase": "seconds",
        "fps": {"num": fps_num, "den": fps_den},
        "output": {
            "width": _positive_int(output.get("width"), 1080),
            "height": _positive_int(output.get("height"), 1920),
            "sample_aspect_ratio": str(output.get("sample_aspect_ratio") or "1:1"),
            "rotation": int(output.get("rotation") or 0),
            "duration_sec": _duration_seconds(output, tracks, segments),
        },
        "tracks": tracks,
        "captions": [
            {
                "segment_id": str(segment["segment_id"]),
                "caption_id": str(segment.get("caption_id") or placement_id(kind="caption", base_id=str(segment["segment_id"]))),
                "placement_id": placement_id(kind="caption", base_id=str(segment.get("caption_id") or segment["segment_id"])),
                "text": str(segment.get("caption_text") or segment.get("text") or ""),
                "start_sec": float(segment.get("start_sec") or 0),
                "end_sec": float(segment.get("end_sec") or 0),
                "style": style,
            }
            for segment in segments
            if isinstance(segment, dict) and segment.get("segment_id")
        ],
        "gap_slots": [_gap_contract(gap) for gap in materialized.get("gap_slots", []) if isinstance(gap, dict)],
        "source_status": {"status": source_status, "source_session_id": source_session_id, "source_session_revision": source_revision},
        "audition": {"asset_urls": {asset_id: f"{asset_content_url_prefix}/{asset_id}/content" for asset_id in asset_ids}},
        "exact_preview": preview,
    }


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _track_contract(track: dict[str, Any]) -> dict[str, Any] | None:
    track_type = str(track.get("track_type") or "")
    # Legacy timelines carry captions as a track.  Captions have their own
    # typed manifest field, so never publish that duplicate generic track.
    if track_type == "caption":
        return None
    if track_type not in TRACK_ROLES:
        raise ValueError("editor_manifest_unsupported_track_role")
    clips = []
    for raw in track.get("clips", []):
        if not isinstance(raw, dict) or not raw.get("clip_id") or not raw.get("segment_id"):
            continue
        clip_type = str(raw.get("clip_type") or track_type)
        if clip_type not in TRACK_ROLES or clip_type != track_type:
            raise ValueError("editor_manifest_unsupported_clip_role")
        controls = raw.get("media_controls") or {}
        if not isinstance(controls, dict):
            raise ValueError("editor_manifest_invalid_media_controls")
        if clip_type == "overlay":
            if raw.get("overlay_type") not in {"explanation_card", "image_overlay", "table_overlay"}:
                raise ValueError("editor_manifest_unsupported_overlay_subtype")
            if not isinstance(raw.get("overlay_payload"), dict):
                raise ValueError("editor_manifest_invalid_overlay_payload")
        clips.append({
            "clip_id": str(raw["clip_id"]), "segment_id": str(raw["segment_id"]),
            "placement_id": placement_id(kind=clip_type, base_id=str(raw["clip_id"])) if clip_type != "narration" else None,
            "clip_type": clip_type,
            "asset_id": raw.get("asset_id"), "asset_uri": raw.get("asset_uri"),
            "start_sec": float(raw.get("start_sec") or 0), "end_sec": float(raw.get("end_sec") or 0),
            "media_controls": dict(controls),
            "expected_content_sha256": raw.get("expected_content_sha256"), "media_revision": raw.get("media_revision"),
            "overlay_type": raw.get("overlay_type") if clip_type == "overlay" else None,
            "overlay_payload": dict(raw.get("overlay_payload") or {}) if clip_type == "overlay" and isinstance(raw.get("overlay_payload"), dict) else {},
        })
    return {"track_id": str(track.get("track_id") or "track"), "track_type": track_type, "clips": clips}


def _gap_contract(gap: dict[str, Any]) -> dict[str, Any]:
    gap_id = str(gap.get("gap_id") or gap.get("gap_slot_id") or "")
    target_range = gap.get("target_range") if isinstance(gap.get("target_range"), dict) else {}
    if not gap_id:
        raise ValueError("editor_manifest_invalid_gap_slot")
    return {
        "gap_id": gap_id,
        "segment_id": str(gap.get("segment_id") or gap_id),
        "start_sec": float(gap.get("start_sec", target_range.get("start_sec", 0))),
        "end_sec": float(gap.get("end_sec", target_range.get("end_sec", 0))),
        "reason": str(gap.get("reason") or "asset_gap"),
    }


def _duration_seconds(output: dict[str, Any], tracks: list[dict[str, Any]], segments: list[Any]) -> float:
    if output.get("duration_sec") is not None:
        return float(output["duration_sec"])
    endpoints = [float(clip["end_sec"]) for track in tracks for clip in track["clips"]]
    endpoints.extend(float(item.get("end_sec") or 0) for item in segments if isinstance(item, dict))
    return max(endpoints, default=0.0)
