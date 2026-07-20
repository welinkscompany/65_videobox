from __future__ import annotations

from copy import deepcopy
from typing import Any
from datetime import UTC, datetime
import uuid

from videobox_domain_models.caption_style import CaptionStyle
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.editing_transactions import apply_user_transaction

MIN_SEGMENT_DURATION_SEC = 0.2
MAX_TIMELINE_UNDO_EVENTS = 10
MAX_TIMELINE_AUDIT_EVENTS = 100
FIXED_TIMELINE_TRACK_ROLES = ("narration", "broll", "bgm", "sfx", "overlay")

ALLOWED_PARTIAL_REGEN_FIELDS = {
    "caption",
    "cut_action",
    "broll",
    "visual_overlay",
    "explanation_card",
    "image_overlay",
    "table_overlay",
    "music",
    "sfx",
    "tts_replacement",
    "timeline_structure",
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
    "sfx": ("sfx_refresh", "timeline_build"),
    "tts_replacement": ("tts_refresh", "timeline_build"),
    "timeline_structure": ("timeline_build",),
}


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


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
                # Placement can later be reordered independently from a
                # deliberate source trim.  This durable offset is consumed
                # by the canonical composition materializer.
                "source_offset_sec": 0.0,
                "cut_action": segment.get("cleanup_decision", "keep"),
                "review_required": _normalize_boolish(segment.get("review_required", False)),
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
            }
        )
    return {
        "project_id": project_id,
        "timeline_id": timeline["timeline_id"],
        "segments": editable_segments,
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "session_revision": 1,
    }


def _segment_index(*, session: dict[str, Any], segment_id: str) -> int:
    for index, segment in enumerate(session.get("segments", [])):
        if isinstance(segment, dict) and str(segment.get("segment_id")) == segment_id:
            return index
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def _validate_segment_bounds(*, segments: list[dict[str, Any]]) -> None:
    normalized: list[tuple[float, float, str]] = []
    for segment in segments:
        start_sec = float(segment.get("start_sec", 0.0))
        end_sec = float(segment.get("end_sec", 0.0))
        if start_sec < 0 or end_sec - start_sec < MIN_SEGMENT_DURATION_SEC:
            raise ValueError(f"Segment duration must be at least {MIN_SEGMENT_DURATION_SEC} seconds.")
        normalized.append((start_sec, end_sec, str(segment.get("segment_id") or "")))
    ordered = sorted(normalized)
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] > current[0]:
            raise ValueError(f"Segment bounds overlap: {previous[2]} and {current[2]}.")


def _source_offset_before_bounds_mutation(*, session: dict[str, Any], segment: dict[str, Any]) -> float:
    """Recover a pre-migration trim offset before persisting the durable form."""
    if "source_offset_sec" in segment:
        return float(segment["source_offset_sec"])
    segment_id = str(segment.get("segment_id") or "")
    offset = 0.0
    for event in session.get("history", []):
        if not isinstance(event, dict) or event.get("mutation_type") != "segment_bounds_update":
            continue
        before = event.get("inverse_payload", {}).get("segments", []) if isinstance(event.get("inverse_payload"), dict) else []
        after = event.get("forward_payload", {}).get("segments", []) if isinstance(event.get("forward_payload"), dict) else []
        before_segment = next((item for item in before if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        after_segment = next((item for item in after if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        if before_segment is not None and after_segment is not None:
            offset += float(after_segment.get("start_sec", 0.0)) - float(before_segment.get("start_sec", 0.0))
    return offset


def _event_snapshot(session: dict[str, Any]) -> dict[str, Any]:
    return {"segments": deepcopy(session.get("segments", []))}


def _record_undoable_mutation(*, before: dict[str, Any], updated: dict[str, Any], mutation_type: str, segment_id: str) -> dict[str, Any]:
    def mutate(draft: dict[str, Any]) -> None:
        for key, value in updated.items():
            if key not in {"history", "undo_stack", "redo_stack", "output_freshness"}:
                draft[key] = deepcopy(value)
    return apply_user_transaction(
        session=before, label=mutation_type, affected_segment_ids=[segment_id] if segment_id else [],
        mutate=mutate, mutation_type=mutation_type,
    )


def _apply_manual_mutation(*, before: dict[str, Any], updated: dict[str, Any], mutation_type: str, segment_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = _record_undoable_mutation(before=before, updated=updated, mutation_type=mutation_type, segment_id=segment_id)
    if extra:
        result["history"][-1].update(extra)
        result["undo_stack"][-1].update(extra)
    return result


def _lineage_for_split(segment: dict[str, Any], *, parent_segment_id: str) -> dict[str, Any]:
    existing = segment.get("lineage") if isinstance(segment.get("lineage"), dict) else {}
    return {
        "root_segment_id": str(existing.get("root_segment_id") or parent_segment_id),
        "parent_segment_id": parent_segment_id,
        "source_segment_ids": list(existing.get("source_segment_ids") or [parent_segment_id]),
    }


def _asset_ids(segment: dict[str, Any], *, field: str) -> list[str]:
    output: list[str] = []
    existing = segment.get("media_lineage")
    if isinstance(existing, dict):
        output.extend(str(value) for value in existing.get(field, []) if str(value))
    legacy_field = {"broll": "broll_override", "music": "music_override", "sfx": "sfx_override", "tts": "tts_replacement"}[field]
    legacy = segment.get(legacy_field)
    if isinstance(legacy, dict) and str(legacy.get("asset_id") or ""):
        output.append(str(legacy["asset_id"]))
    return list(dict.fromkeys(output))


def _media_lineage(*segments: dict[str, Any]) -> dict[str, list[str]]:
    return {field: list(dict.fromkeys(asset_id for segment in segments for asset_id in _asset_ids(segment, field=field))) for field in ("broll", "music", "sfx", "tts")}


def split_segment(*, session: dict[str, Any], segment_id: str, split_sec: float) -> dict[str, Any]:
    updated = deepcopy(session)
    index = _segment_index(session=updated, segment_id=segment_id)
    original = updated["segments"][index]
    start_sec, end_sec = float(original["start_sec"]), float(original["end_sec"])
    split_sec = float(split_sec)
    if split_sec - start_sec < MIN_SEGMENT_DURATION_SEC or end_sec - split_sec < MIN_SEGMENT_DURATION_SEC:
        raise ValueError(f"Split must leave at least {MIN_SEGMENT_DURATION_SEC} seconds on both sides.")
    known_ids = {str(item.get("segment_id")) for item in updated["segments"] if isinstance(item, dict)}
    suffix = 2
    split_id = f"{segment_id}__split_{suffix}"
    while split_id in known_ids:
        suffix += 1
        split_id = f"{segment_id}__split_{suffix}"
    left, right = deepcopy(original), deepcopy(original)
    left["end_sec"] = split_sec
    right["segment_id"] = split_id
    right["start_sec"] = split_sec
    left["lineage"] = _lineage_for_split(original, parent_segment_id=segment_id)
    right["lineage"] = _lineage_for_split(original, parent_segment_id=segment_id)
    left["caption_needs_review"] = True
    right["caption_needs_review"] = True
    updated["segments"][index : index + 1] = [left, right]
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_split", segment_id=segment_id)


def merge_adjacent_segments(*, session: dict[str, Any], left_segment_id: str, right_segment_id: str) -> dict[str, Any]:
    updated = deepcopy(session)
    left_index = _segment_index(session=updated, segment_id=left_segment_id)
    right_index = _segment_index(session=updated, segment_id=right_segment_id)
    if right_index != left_index + 1:
        raise ValueError("Only adjacent segments can be merged.")
    left, right = updated["segments"][left_index], updated["segments"][right_index]
    if abs(float(left["end_sec"]) - float(right["start_sec"])) > 0.000001:
        raise ValueError("Only adjacent touching segments can be merged.")
    merged = deepcopy(left)
    merged["end_sec"] = float(right["end_sec"])
    merged["caption_text"] = f"{str(left.get('caption_text') or '').strip()}\n{str(right.get('caption_text') or '').strip()}".strip()
    left_lineage = left.get("lineage") if isinstance(left.get("lineage"), dict) else {}
    right_lineage = right.get("lineage") if isinstance(right.get("lineage"), dict) else {}
    merged["lineage"] = {
        "root_segment_id": str(left_lineage.get("root_segment_id") or left_segment_id),
        "source_segment_ids": list(dict.fromkeys(list(left_lineage.get("source_segment_ids") or [left_segment_id]) + list(right_lineage.get("source_segment_ids") or [right_segment_id]))),
    }
    merged["media_lineage"] = _media_lineage(left, right)
    merged["caption_needs_review"] = bool(left.get("caption_needs_review") or right.get("caption_needs_review"))
    updated["segments"][left_index : right_index + 1] = [merged]
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_merge", segment_id=left_segment_id)


def set_segment_bounds(*, session: dict[str, Any], segment_id: str, start_sec: float, end_sec: float) -> dict[str, Any]:
    updated = deepcopy(session)
    index = _segment_index(session=updated, segment_id=segment_id)
    previous_start = float(updated["segments"][index]["start_sec"])
    prior_offset = _source_offset_before_bounds_mutation(session=session, segment=updated["segments"][index])
    updated["segments"][index]["start_sec"] = float(start_sec)
    updated["segments"][index]["end_sec"] = float(end_sec)
    # Only a bounds edit changes which source moment is used.  A reorder
    # relayout deliberately leaves this value untouched.
    updated["segments"][index]["source_offset_sec"] = prior_offset + float(start_sec) - previous_start
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_bounds_update", segment_id=segment_id)


def reorder_segments(*, session: dict[str, Any], segment_ids: list[str], bounds_by_id: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    updated = deepcopy(session)
    existing = {str(segment.get("segment_id")): segment for segment in updated.get("segments", []) if isinstance(segment, dict)}
    if len(segment_ids) != len(existing) or set(segment_ids) != set(existing):
        raise ValueError("Segment order must be a complete permutation of the current segments.")
    if list(segment_ids) != [str(segment.get("segment_id")) for segment in updated["segments"]] and bounds_by_id is None:
        raise ValueError("Reorder requires a complete non-overlapping bounds_by_id relayout.")
    reordered = [deepcopy(existing[segment_id]) for segment_id in segment_ids]
    if bounds_by_id is not None:
        if set(bounds_by_id) != set(existing):
            raise ValueError("bounds_by_id must define every segment.")
        for segment in reordered:
            bounds = bounds_by_id[str(segment["segment_id"])]
            segment["start_sec"] = float(bounds["start_sec"])
            segment["end_sec"] = float(bounds["end_sec"])
    _validate_segment_bounds(segments=reordered)
    updated["segments"] = reordered
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_reorder", segment_id=",".join(segment_ids))


def undo(*, session: dict[str, Any]) -> dict[str, Any]:
    undo_stack = list(deepcopy(session.get("undo_stack", [])))
    if not undo_stack:
        raise ValueError("There is no editing operation to undo.")
    event = undo_stack.pop()
    updated = deepcopy(session)
    updated["segments"] = deepcopy(event["inverse_payload"]["segments"])
    updated["undo_stack"] = undo_stack
    updated["redo_stack"] = list(deepcopy(session.get("redo_stack", []))) + [event]
    history = list(deepcopy(session.get("history", [])))
    history.append({"mutation_type": "undo", "segment_id": str(event.get("segment_id") or "")})
    updated["history"] = history[-MAX_TIMELINE_AUDIT_EVENTS:]
    now = datetime.now(UTC).isoformat()
    revision = int(session.get("session_revision") or 1) + 1
    updated["output_freshness"] = {kind: {"source_session_revision": revision, "is_current": False, "invalidated_at": now, "invalidated_reason": "undo"} for kind in ("review", "subtitle", "preview", "final", "capcut")}
    return updated


def redo(*, session: dict[str, Any]) -> dict[str, Any]:
    redo_stack = list(deepcopy(session.get("redo_stack", [])))
    if not redo_stack:
        raise ValueError("There is no editing operation to redo.")
    event = redo_stack.pop()
    updated = deepcopy(session)
    updated["segments"] = deepcopy(event["forward_payload"]["segments"])
    updated["redo_stack"] = redo_stack
    updated["undo_stack"] = (list(deepcopy(session.get("undo_stack", []))) + [event])[-MAX_TIMELINE_UNDO_EVENTS:]
    history = list(deepcopy(session.get("history", [])))
    history.append({"mutation_type": "redo", "segment_id": str(event.get("segment_id") or "")})
    updated["history"] = history[-MAX_TIMELINE_AUDIT_EVENTS:]
    now = datetime.now(UTC).isoformat()
    revision = int(session.get("session_revision") or 1) + 1
    updated["output_freshness"] = {kind: {"source_session_revision": revision, "is_current": False, "invalidated_at": now, "invalidated_reason": "redo"} for kind in ("review", "subtitle", "preview", "final", "capcut")}
    return updated


def record_non_undoable_operation(*, session: dict[str, Any], operation_type: str) -> dict[str, Any]:
    if operation_type not in {"render", "import"}:
        raise ValueError("Only render and import may be recorded as non-undoable operations.")
    updated = deepcopy(session)
    updated.setdefault("history", []).append({"mutation_type": operation_type, "segment_id": ""})
    return updated


def build_fixed_track_timeline(*, session: dict[str, Any]) -> dict[str, Any]:
    tracks: dict[str, list[dict[str, Any]]] = {role: [] for role in FIXED_TIMELINE_TRACK_ROLES}
    for segment in session.get("segments", []):
        if not isinstance(segment, dict):
            continue
        clip = {"segment_id": segment.get("segment_id"), "start_sec": segment.get("start_sec"), "end_sec": segment.get("end_sec")}
        tracks["narration"].append({**clip, "caption_text": segment.get("caption_text")})
        for role, field in (("broll", "broll_override"), ("bgm", "music_override"), ("sfx", "sfx_override")):
            if segment.get(field) is not None:
                tracks[role].append({**clip, "asset": deepcopy(segment[field])})
        for overlay in segment.get("visual_overlays", []):
            if isinstance(overlay, dict):
                tracks["overlay"].append({**clip, "overlay": deepcopy(overlay)})
    return {"tracks": [{"role": role, "clips": tracks[role]} for role in FIXED_TIMELINE_TRACK_ROLES]}


def build_selected_range_preview(*, session: dict[str, Any], start_sec: float, end_sec: float) -> dict[str, Any]:
    start_sec, end_sec = float(start_sec), float(end_sec)
    if start_sec < 0 or end_sec <= start_sec:
        raise ValueError("Selected preview range must have a positive duration.")
    captions: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    selected_segments: list[dict[str, Any]] = []
    for segment in session.get("segments", []):
        if not isinstance(segment, dict) or float(segment.get("end_sec", 0.0)) <= start_sec or float(segment.get("start_sec", 0.0)) >= end_sec:
            continue
        selected_segments.append(deepcopy(segment))
        captions.append({"segment_id": segment["segment_id"], "caption_text": segment.get("caption_text", ""), "start_sec": max(start_sec, float(segment["start_sec"])), "end_sec": min(end_sec, float(segment["end_sec"])), "caption_style": deepcopy(segment.get("caption_style") or session.get("caption_style") or {})})
        for overlay in segment.get("visual_overlays", []):
            if isinstance(overlay, dict):
                overlays.append({"segment_id": segment["segment_id"], **deepcopy(overlay)})
    selected_session = deepcopy(session)
    selected_session["segments"] = selected_segments
    return {"start_sec": start_sec, "end_sec": end_sec, "caption_style": deepcopy(session.get("caption_style") or {}), "captions": captions, "overlays": overlays, "timeline": build_fixed_track_timeline(session=selected_session)}


def preview_caption_style_scope(*, session: dict[str, Any], scope: str, segment_ids: list[str]) -> list[str]:
    segments = [item for item in session.get("segments", []) if isinstance(item, dict)]
    requested = {str(item).strip() for item in segment_ids if str(item).strip()}
    known_ids = {str(item.get("segment_id")) for item in segments}
    if scope in {"current_caption", "from_current"} and len(requested) != 1:
        raise ValueError(f"{scope} requires exactly one caption.")
    if scope == "selected_captions" and not requested:
        raise ValueError("selected_captions requires one or more captions.")
    if scope in {"whole_project", "project_default"} and requested:
        raise ValueError(f"{scope} does not accept segment_ids.")
    if scope in {"current_caption", "selected_captions", "from_current"} and not requested.issubset(known_ids):
        raise KeyError("Requested caption is not in this editing session.")
    if scope == "whole_project":
        return [str(item["segment_id"]) for item in segments]
    if scope == "project_default":
        return []
    if scope in {"current_caption", "selected_captions"}:
        return [str(item["segment_id"]) for item in segments if str(item.get("segment_id")) in requested]
    if scope == "from_current":
        index = next((i for i, item in enumerate(segments) if str(item.get("segment_id")) in requested), None)
        return [] if index is None else [str(item["segment_id"]) for item in segments[index:]]
    raise ValueError("Unsupported caption style scope.")


def update_caption_style(*, session: dict[str, Any], style: dict[str, Any], scope: str, segment_ids: list[str]) -> dict[str, Any]:
    updated = deepcopy(session)
    target_ids = preview_caption_style_scope(session=updated, scope=scope, segment_ids=segment_ids)
    if scope != "project_default" and not target_ids:
        raise KeyError("No captions selected for caption style update.")
    resolved_style = CaptionStyle.from_dict(style).to_dict()
    if scope in {"whole_project", "project_default"}:
        updated["caption_style"] = dict(resolved_style)
    for segment in updated.get("segments", []):
        if isinstance(segment, dict) and str(segment.get("segment_id")) in target_ids:
            segment["caption_style"] = dict(resolved_style)
    return _apply_manual_mutation(before=session, updated=updated, mutation_type="caption_style_update", segment_id=",".join(target_ids))


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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="caption_update", segment_id=segment_id, extra={"caption_text": normalized_caption})
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="cut_action_update", segment_id=segment_id, extra={"cut_action": normalized_cut_action})
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_broll_override(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
    media_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["broll_override"] = {"asset_id": normalized_asset_id}
        if media_controls is not None:
            # Manual project-local placement carries the immutable identity used
            # by output verification.  Keep it alongside (not inside) the
            # normalized playback controls so downstream source verification can
            # re-hash the exact asset selected by the operator.
            expected_sha = str(media_controls.get("expected_content_sha256") or "").strip()
            media_revision = str(media_controls.get("media_revision") or "").strip()
            if expected_sha:
                segment["broll_override"]["expected_content_sha256"] = expected_sha
            if media_revision:
                segment["broll_override"]["media_revision"] = media_revision
            segment["broll_override"]["media_controls"] = normalize_media_controls(media_controls, media_kind="broll", duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)))
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="broll_override_update", segment_id=segment_id, extra={"asset_id": normalized_asset_id})
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="broll_override_clear", segment_id=segment_id)
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_sfx_override(*, session: dict[str, Any], segment_id: str, asset_id: str, asset_uri: str | None = None, media_controls: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["sfx_override"] = {"asset_id": asset_id.strip()}
        if asset_uri:
            segment["sfx_override"]["asset_uri"] = asset_uri
        if media_controls is not None:
            segment["sfx_override"]["media_controls"] = normalize_media_controls(media_controls, media_kind="audio", duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)))
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="sfx_override_update", segment_id=segment_id, extra={"asset_id": asset_id.strip()})
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def clear_segment_sfx_override(*, session: dict[str, Any], segment_id: str) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["sfx_override"] = None
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="sfx_override_clear", segment_id=segment_id)
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
    updated["undo_stack"][-1]["asset_id"] = normalized_asset_id
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="visual_overlay_clear", segment_id=segment_id)
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
    asset_uri: str | None = None,
    media_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        segment["music_override"] = {"asset_id": normalized_asset_id}
        if asset_uri:
            segment["music_override"]["asset_uri"] = asset_uri
        if media_controls is not None:
            segment["music_override"]["media_controls"] = normalize_media_controls(media_controls, media_kind="audio", duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)))
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="music_override_update", segment_id=segment_id, extra={"asset_id": normalized_asset_id})
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="music_override_clear", segment_id=segment_id)
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
    normalized_segment_ids: list[str] = []
    for segment_id in segment_ids:
        normalized_segment_id = segment_id.strip()
        if not normalized_segment_id or normalized_segment_id in normalized_segment_ids:
            continue
        normalized_segment_ids.append(normalized_segment_id)
    if not normalized_segment_ids:
        raise ValueError("segment_ids must contain at least one valid segment id.")

    session_segment_ids = {
        str(segment.get("segment_id")).strip()
        for segment in session.get("segments", [])
        if isinstance(segment, dict) and str(segment.get("segment_id") or "").strip()
    }
    unknown_segment_ids = [segment_id for segment_id in normalized_segment_ids if segment_id not in session_segment_ids]
    if unknown_segment_ids:
        raise ValueError(f"Unknown session segment ids: {', '.join(unknown_segment_ids)}")

    normalized_fields: list[str] = []
    for field in fields:
        normalized_field = field.strip()
        if not normalized_field or normalized_field in normalized_fields:
            continue
        normalized_fields.append(normalized_field)
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type=mutation_type, segment_id=segment_id, extra={"overlay_type": overlay_type})
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
        return _apply_manual_mutation(before=session, updated=updated, mutation_type=mutation_type, segment_id=segment_id, extra={"overlay_type": overlay_type})
    raise KeyError(f"Segment not found in editing session: {segment_id}")
