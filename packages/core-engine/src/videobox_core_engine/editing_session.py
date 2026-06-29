from __future__ import annotations

from copy import deepcopy
from typing import Any


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


def build_partial_regeneration_request(
    *,
    session: dict[str, Any],
    segment_ids: list[str],
    fields: list[str],
) -> dict[str, Any]:
    return {
        "session_id": session.get("session_id"),
        "segment_ids": list(segment_ids),
        "fields": list(fields),
    }
