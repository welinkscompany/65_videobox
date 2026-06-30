from __future__ import annotations

from copy import deepcopy
from typing import Any

ALLOWED_PARTIAL_REGEN_FIELDS = {
    "caption",
    "cut_action",
    "broll",
    "visual_overlay",
    "explanation_card",
    "image_overlay",
    "table_overlay",
    "music",
    "tts_replacement",
}

PARTIAL_REGEN_STEPS_BY_FIELD = {
    "caption": ("segment_refresh", "timeline_build"),
    "cut_action": ("segment_refresh", "timeline_build"),
    "broll": ("broll_refresh", "timeline_build"),
    "visual_overlay": ("overlay_refresh", "timeline_build"),
    "explanation_card": ("overlay_refresh", "timeline_build"),
    "image_overlay": ("overlay_refresh", "timeline_build"),
    "table_overlay": ("overlay_refresh", "timeline_build"),
    "music": ("music_refresh", "timeline_build"),
    "tts_replacement": ("tts_refresh", "timeline_build"),
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
                "tts_replacement": None,
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


def clear_segment_broll_override(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["broll_override"] = None
        updated.setdefault("history", []).append(
            {
                "mutation_type": "broll_override_clear",
                "segment_id": segment_id,
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
    normalized_overlay_type = overlay_type.strip()
    normalized_asset_id = asset_id.strip()
    updated = _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type=normalized_overlay_type,
        overlay_payload={
            "overlay_type": normalized_overlay_type,
            "asset_id": normalized_asset_id,
        },
        mutation_type="visual_overlay_update",
    )
    updated["history"][-1]["asset_id"] = normalized_asset_id
    return updated


def clear_segment_visual_overlays(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["visual_overlays"] = []
        updated.setdefault("history", []).append(
            {
                "mutation_type": "visual_overlay_clear",
                "segment_id": segment_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_explanation_card(
    *,
    session: dict[str, Any],
    segment_id: str,
    title: str,
    body: str,
    text: str,
) -> dict[str, Any]:
    return _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="explanation_card",
        overlay_payload={
            "overlay_type": "explanation_card",
            "title": title.strip(),
            "body": body.strip(),
            "text": text.strip(),
        },
        mutation_type="explanation_card_update",
    )


def remove_segment_explanation_card(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    return _remove_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="explanation_card",
        mutation_type="explanation_card_remove",
    )


def update_segment_image_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
    text: str,
) -> dict[str, Any]:
    return _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="image_card",
        overlay_payload={
            "overlay_type": "image_card",
            "asset_id": asset_id.strip(),
            "text": text.strip(),
        },
        mutation_type="image_overlay_update",
    )


def remove_segment_image_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    return _remove_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="image_card",
        mutation_type="image_overlay_remove",
    )


def update_segment_table_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    columns: list[str],
    rows: list[list[str]],
    text: str,
) -> dict[str, Any]:
    return _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="table_card",
        overlay_payload={
            "overlay_type": "table_card",
            "columns": [str(item) for item in columns],
            "rows": [[str(cell) for cell in row] for row in rows],
            "text": text.strip(),
        },
        mutation_type="table_overlay_update",
    )


def remove_segment_table_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    return _remove_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="table_card",
        mutation_type="table_overlay_remove",
    )


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


def clear_segment_music_override(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["music_override"] = None
        updated.setdefault("history", []).append(
            {
                "mutation_type": "music_override_clear",
                "segment_id": segment_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def select_segment_tts_replacement(
    *,
    session: dict[str, Any],
    segment_id: str,
    recommendation_id: str,
    asset_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_recommendation_id = recommendation_id.strip()
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["tts_replacement"] = {
            "recommendation_id": normalized_recommendation_id,
            "asset_id": normalized_asset_id,
        }
        updated.setdefault("history", []).append(
            {
                "mutation_type": "tts_replacement_select",
                "segment_id": segment_id,
                "recommendation_id": normalized_recommendation_id,
                "asset_id": normalized_asset_id,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def clear_segment_tts_replacement(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["tts_replacement"] = None
        updated.setdefault("history", []).append(
            {
                "mutation_type": "tts_replacement_clear",
                "segment_id": segment_id,
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


def _upsert_segment_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    overlay_type: str,
    overlay_payload: dict[str, Any],
    mutation_type: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        overlays = [
            overlay
            for overlay in segment.get("visual_overlays", [])
            if isinstance(overlay, dict) and str(overlay.get("overlay_type") or "") != overlay_type
        ]
        overlays.append(overlay_payload)
        segment["visual_overlays"] = overlays
        updated.setdefault("history", []).append(
            {
                "mutation_type": mutation_type,
                "segment_id": segment_id,
                "overlay_type": overlay_type,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def _remove_segment_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    overlay_type: str,
    mutation_type: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["visual_overlays"] = [
            overlay
            for overlay in segment.get("visual_overlays", [])
            if not (isinstance(overlay, dict) and str(overlay.get("overlay_type") or "") == overlay_type)
        ]
        updated.setdefault("history", []).append(
            {
                "mutation_type": mutation_type,
                "segment_id": segment_id,
                "overlay_type": overlay_type,
            }
        )
        return updated
    raise KeyError(f"Segment not found in editing session: {segment_id}")
