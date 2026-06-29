from __future__ import annotations

from copy import deepcopy
from typing import Any

ALLOWED_PARTIAL_REGEN_FIELDS = {
    "caption",
    "cut_action",
    "broll",
    "visual_overlay",
    "music",
}

PARTIAL_REGEN_STEPS_BY_FIELD = {
    "caption": ("segment_refresh", "timeline_build"),
    "cut_action": ("segment_refresh", "timeline_build"),
    "broll": ("broll_refresh", "timeline_build"),
    "visual_overlay": ("overlay_refresh", "timeline_build"),
    "music": ("music_refresh", "timeline_build"),
}


def build_editing_session(
    *,
    project_id: str,
    timeline: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    editable_segments: list[dict[str, Any]] = []
    for segment in segments:
        editable_segments.append(
            {
                "segment_id": segment["segment_id"],
                "caption_text": segment["text"],
                "start_sec": segment["start_sec"],
                "end_sec": segment["end_sec"],
                "cut_action": segment.get("cleanup_decision", "keep"),
                "review_required": bool(segment.get("review_required", False)),
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
            }
        )
    return {
        "project_id": project_id,
        "timeline_id": timeline["timeline_id"],
        "segments": editable_segments,
        "history": [],
    }


def update_segment_caption(
    *,
    session: dict[str, Any],
    segment_id: str,
    caption_text: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_caption = caption_text.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["caption_text"] = normalized_caption
        updated.setdefault("history", []).append(
            {
                "mutation_type": "caption_update",
                "segment_id": segment_id,
                "caption_text": normalized_caption,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_cut_action(
    *,
    session: dict[str, Any],
    segment_id: str,
    cut_action: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_cut_action = cut_action.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["cut_action"] = normalized_cut_action
        updated.setdefault("history", []).append(
            {
                "mutation_type": "cut_action_update",
                "segment_id": segment_id,
                "cut_action": normalized_cut_action,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_broll_override(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["broll_override"] = {"asset_id": normalized_asset_id}
        updated.setdefault("history", []).append(
            {
                "mutation_type": "broll_override_update",
                "segment_id": segment_id,
                "asset_id": normalized_asset_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_visual_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    overlay_type: str,
    asset_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_overlay_type = overlay_type.strip()
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["visual_overlays"] = [
            {
                "overlay_type": normalized_overlay_type,
                "asset_id": normalized_asset_id,
            }
        ]
        updated.setdefault("history", []).append(
            {
                "mutation_type": "visual_overlay_update",
                "segment_id": segment_id,
                "overlay_type": normalized_overlay_type,
                "asset_id": normalized_asset_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_music_override(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["music_override"] = {"asset_id": normalized_asset_id}
        updated.setdefault("history", []).append(
            {
                "mutation_type": "music_override_update",
                "segment_id": segment_id,
                "asset_id": normalized_asset_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def build_partial_regeneration_request(
    *,
    session: dict[str, Any],
    segment_ids: list[str],
    fields: list[str],
) -> dict[str, Any]:
    normalized_segment_ids = [segment_id.strip() for segment_id in segment_ids if segment_id.strip()]
    if not normalized_segment_ids:
        raise ValueError("segment_ids must contain at least one valid segment id.")

    session_segment_ids = {
        str(segment.get("segment_id")).strip()
        for segment in session.get("segments", [])
        if str(segment.get("segment_id") or "").strip()
    }
    unknown_segment_ids = [segment_id for segment_id in normalized_segment_ids if segment_id not in session_segment_ids]
    if unknown_segment_ids:
        raise ValueError(f"Unknown session segment ids: {', '.join(unknown_segment_ids)}")

    normalized_fields = [field.strip() for field in fields if field.strip()]
    if not normalized_fields:
        raise ValueError("fields must contain at least one valid field.")

    unsupported_fields = [field for field in normalized_fields if field not in ALLOWED_PARTIAL_REGEN_FIELDS]
    if unsupported_fields:
        raise ValueError(f"Unsupported partial regeneration fields: {', '.join(unsupported_fields)}")

    downstream_steps: list[str] = []
    for field in normalized_fields:
        for step in PARTIAL_REGEN_STEPS_BY_FIELD[field]:
            if step == "timeline_build":
                continue
            if step not in downstream_steps:
                downstream_steps.append(step)
    downstream_steps.append("timeline_build")

    return {
        "session_id": session.get("session_id"),
        "segment_ids": normalized_segment_ids,
        "fields": normalized_fields,
        "downstream_steps": downstream_steps,
    }
