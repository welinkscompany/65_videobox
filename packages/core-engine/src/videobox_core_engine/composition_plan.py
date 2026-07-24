"""Canonical, renderer-neutral representation of a timeline composition.

Both a final render and a revision-bound proxy must start here.  This module
does not resolve files or invoke ffmpeg: keeping it pure makes the range and
fingerprint fences independently testable.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Iterable

from videobox_core_engine.media_controls import normalize_media_controls


COMPOSITION_VERSION = "videobox_composition_v1"
_SUPPORTED_TRACKS = frozenset({"narration", "broll", "bgm", "sfx", "overlay"})


def _legacy_segment_source_offset(*, editing_session: dict[str, Any], segment: dict[str, Any], original_start: float) -> float:
    """Migrate old sessions without a durable source offset from their audit log."""
    if "source_offset_sec" in segment:
        return _number(segment.get("source_offset_sec"))
    segment_id = str(segment.get("segment_id") or "")
    history = editing_session.get("history")
    if isinstance(history, list):
        offset = 0.0
        saw_bounds_mutation = False
        for event in history:
            if not isinstance(event, dict) or event.get("mutation_type") != "segment_bounds_update":
                continue
            before = event.get("inverse_payload", {}).get("segments", []) if isinstance(event.get("inverse_payload"), dict) else []
            after = event.get("forward_payload", {}).get("segments", []) if isinstance(event.get("forward_payload"), dict) else []
            before_segment = next((item for item in before if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
            after_segment = next((item for item in after if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
            if before_segment is not None and after_segment is not None:
                offset += _number(after_segment.get("start_sec")) - _number(before_segment.get("start_sec"))
                saw_bounds_mutation = True
        if saw_bounds_mutation or history:
            for event in history:
                if not isinstance(event, dict) or event.get("mutation_type") != "segment_split":
                    continue
                before = event.get("inverse_payload", {}).get("segments", []) if isinstance(event.get("inverse_payload"), dict) else []
                after = event.get("forward_payload", {}).get("segments", []) if isinstance(event.get("forward_payload"), dict) else []
                current = next((item for item in after if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
                lineage = current.get("lineage") if isinstance(current, dict) and isinstance(current.get("lineage"), dict) else {}
                parent_id = str(lineage.get("parent_segment_id") or "")
                parent = next((item for item in before if isinstance(item, dict) and str(item.get("segment_id") or "") == parent_id), None)
                if current is not None and parent is not None and segment_id != parent_id:
                    offset += _number(current.get("start_sec")) - _number(parent.get("start_sec"))
            return offset
    # Hand-authored legacy fixtures predate transaction audit data.  Retain
    # their former trim interpretation while new/reordered sessions use the
    # durable marker above.
    return _number(segment.get("start_sec")) - original_start


def _session_source_slices(*, editing_session: dict[str, Any], segment: dict[str, Any], source_durations: dict[str, float]) -> list[dict[str, Any]]:
    raw = segment.get("source_slices")
    if isinstance(raw, list):
        slices = [
            {"segment_id": str(item.get("segment_id") or ""), "source_offset_sec": _number(item.get("source_offset_sec")), "duration_sec": _number(item.get("duration_sec"))}
            for item in raw if isinstance(item, dict) and str(item.get("segment_id") or "") and _number(item.get("duration_sec")) > 0
        ]
        if slices:
            return slices
    lineage = segment.get("lineage") if isinstance(segment.get("lineage"), dict) else {}
    source_ids = [str(value) for value in lineage.get("source_segment_ids", []) if str(value)] or [str(segment.get("segment_id") or "")]
    duration = max(0.0, _number(segment.get("end_sec")) - _number(segment.get("start_sec")))
    if len(source_ids) == 1:
        if "source_offset_sec" in segment or isinstance(editing_session.get("history"), list) and editing_session.get("history"):
            return [{"segment_id": source_ids[0], "source_offset_sec": _legacy_segment_source_offset(editing_session=editing_session, segment=segment, original_start=0.0), "duration_sec": duration}]
        # Pre-audit hand-authored sessions used timeline coordinates to signal
        # a trim.  Carry that marker until the raw clip supplies its base.
        return [{"segment_id": source_ids[0], "source_offset_sec": _number(segment.get("start_sec")), "duration_sec": duration, "legacy_timeline_anchor": True}]
    legacy = [{"segment_id": source_id, "source_offset_sec": 0.0, "duration_sec": source_durations.get(source_id, 0.0)} for source_id in source_ids]
    remaining, output = duration, []
    for source_slice in legacy:
        take = min(float(source_slice["duration_sec"]), remaining)
        if take > 0:
            output.append({**source_slice, "duration_sec": take})
            remaining -= take
        if remaining <= 0:
            break
    return output


def _session_override_windows(*, segment: dict[str, Any], override_field: str) -> list[tuple[float, float]]:
    """Return the placed intervals where a session override replaces base media."""
    start, end = _number(segment.get("start_sec")), _number(segment.get("end_sec"))
    direct_override = segment.get(override_field)
    raw_windows = segment.get("media_windows")
    windows = [{
        "start_offset_sec": 0.0,
        "duration_sec": end - start,
        override_field: direct_override,
    }] if isinstance(direct_override, dict) else raw_windows if isinstance(raw_windows, list) and raw_windows else [{
        "start_offset_sec": 0.0,
        "duration_sec": end - start,
        override_field: None,
    }]
    intervals: list[tuple[float, float]] = []
    for window in windows:
        if not isinstance(window, dict) or not isinstance(window.get(override_field), dict):
            continue
        window_start = max(start, start + _number(window.get("start_offset_sec")))
        window_end = min(end, window_start + _number(window.get("duration_sec")))
        if window_end > window_start:
            intervals.append((window_start, window_end))
    return intervals


def _uncovered_intervals(*, start: float, end: float, covered: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """Subtract session replacement windows from a source clip placement."""
    cursor, output = start, []
    for covered_start, covered_end in sorted(covered):
        left, right = max(start, covered_start), min(end, covered_end)
        if right <= cursor:
            continue
        if left > cursor:
            output.append((cursor, left))
        cursor = max(cursor, right)
        if cursor >= end:
            break
    if cursor < end:
        output.append((cursor, end))
    return output


def _segment_content_windows(segment: dict[str, Any]) -> list[dict[str, Any]]:
    raw = segment.get("content_windows")
    if isinstance(raw, list) and raw:
        return [item for item in raw if isinstance(item, dict)]
    return [{
        "start_offset_sec": 0.0, "duration_sec": _number(segment.get("end_sec")) - _number(segment.get("start_sec")),
        "source_segment_id": str(segment.get("segment_id") or ""),
        **{key: deepcopy(segment.get(key)) for key in ("caption_text", "caption_style", "review_required", "visual_overlays", "tts_replacement")},
    }]


def materialize_editing_session_timeline(
    *, timeline: dict[str, Any], editing_session: dict[str, Any] | None, project_id: str | None = None,
) -> dict[str, Any]:
    """Purely materialize current session edits before any output consumes them."""
    materialized = deepcopy(timeline)
    if not isinstance(editing_session, dict):
        return materialized
    project = str(project_id or timeline.get("project_id") or "").strip()
    segments = {
        str(segment.get("segment_id")): segment
        for segment in editing_session.get("segments", [])
        if isinstance(segment, dict) and str(segment.get("segment_id") or "").strip()
    }
    source_tracks = [
        track for track in timeline.get("tracks", [])
        if isinstance(track, dict)
    ]
    narration_clips = [
        clip
        for track in source_tracks
        if str(track.get("track_type") or "").strip().lower() == "narration"
        for clip in track.get("clips", [])
        if isinstance(clip, dict)
    ]
    caption_clips = sorted(
        [
            clip
            for track in source_tracks
            if str(track.get("track_type") or "").strip().lower() == "caption"
            for clip in track.get("clips", [])
            if isinstance(clip, dict)
            and str(clip.get("segment_id") or "").strip()
            and _number(clip.get("end_sec")) > _number(clip.get("start_sec"))
        ],
        key=lambda clip: (_number(clip.get("start_sec")), _number(clip.get("end_sec"))),
    )
    global_narration_clip: dict[str, Any] | None = None
    if len(narration_clips) == 1 and len(caption_clips) > 1:
        narration = narration_clips[0]
        narration_start = _number(narration.get("start_sec"))
        narration_end = _number(narration.get("end_sec"))
        if (
            str(narration.get("segment_id") or "") == str(caption_clips[0].get("segment_id") or "")
            and narration_start == _number(caption_clips[0].get("start_sec"))
            and narration_end == _number(caption_clips[-1].get("end_sec"))
            and all(
                _number(left.get("end_sec")) == _number(right.get("start_sec"))
                for left, right in zip(caption_clips, caption_clips[1:])
            )
        ):
            # Atomic drafts intentionally retain one narration source across
            # multiple visible caption segments. Its first segment_id is an
            # anchor, not permission to trim the source to that caption.
            global_narration_clip = narration
    source_durations: dict[str, float] = {}
    source_bounds: dict[str, tuple[float, float]] = {}
    for track in source_tracks:
        for clip in track.get("clips", []) if isinstance(track.get("clips"), list) else []:
            if isinstance(clip, dict) and str(clip.get("segment_id") or ""):
                source_id = str(clip["segment_id"])
                source_durations[source_id] = max(source_durations.get(source_id, 0.0), _number(clip.get("end_sec")) - _number(clip.get("start_sec")))
                start, end = _number(clip.get("start_sec")), _number(clip.get("end_sec"))
                previous = source_bounds.get(source_id)
                source_bounds[source_id] = (start, end) if previous is None else (min(previous[0], start), max(previous[1], end))
    source_targets: dict[str, list[tuple[dict[str, Any], dict[str, Any], float]]] = {}
    removed_source_ids: set[str] = set()
    for segment in segments.values():
        if str(segment.get("cut_action") or "keep") == "remove":
            removed_source_ids.update(
                str(source_slice["segment_id"])
                for source_slice in _session_source_slices(editing_session=editing_session, segment=segment, source_durations=source_durations)
            )
            continue
        placement = _number(segment.get("start_sec"))
        # original_start is only a compatibility fallback; persisted slices
        # are independent of placement and survive reorder.
        for source_slice in _session_source_slices(editing_session=editing_session, segment=segment, source_durations=source_durations):
            source_targets.setdefault(str(source_slice["segment_id"]), []).append((segment, source_slice, placement))
            placement += float(source_slice["duration_sec"])

    def caption_has_identity_projection(caption: dict[str, Any]) -> bool:
        source_id = str(caption.get("segment_id") or "")
        targets = source_targets.get(source_id, [])
        if source_id in removed_source_ids or len(targets) != 1:
            return False
        segment, source_slice, placement = targets[0]
        source_offset = float(source_slice["source_offset_sec"])
        if source_slice.get("legacy_timeline_anchor"):
            source_offset -= _number(caption.get("start_sec"))
        return (
            str(segment.get("segment_id") or "") == source_id
            and float(placement) == _number(caption.get("start_sec"))
            and source_offset == 0.0
            and float(source_slice["duration_sec"])
            == _number(caption.get("end_sec")) - _number(caption.get("start_sec"))
        )

    tracks: dict[str, list[dict[str, Any]]] = {}
    track_ids: dict[str, str] = {}
    used_track_ids: set[str] = set()
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        track_type = str(track.get("track_type") or "").strip().lower()
        if track_type not in _SUPPORTED_TRACKS:
            continue
        if track_type not in track_ids:
            base_track_id = str(track.get("track_id") or "").strip() or f"track_{track_type}"
            track_id = base_track_id
            if track_id in used_track_ids:
                track_id = f"{base_track_id}_{track_type}"
                suffix = 2
                while track_id in used_track_ids:
                    track_id = f"{base_track_id}_{track_type}_{suffix}"
                    suffix += 1
            track_ids[track_type] = track_id
            used_track_ids.add(track_id)
        clips: list[dict[str, Any]] = []
        for raw in track.get("clips", []) if isinstance(track.get("clips"), list) else []:
            if not isinstance(raw, dict):
                continue
            if track_type == "narration" and raw is global_narration_clip:
                identity_projection = all(caption_has_identity_projection(caption) for caption in caption_clips)
                if identity_projection:
                    clips.append(deepcopy(raw))
                    continue
                narration_start = _number(raw.get("start_sec"))
                base_source_in = _number(raw.get("source_in_sec", raw.get("in_sec", 0.0)))
                source_limit = _number(
                    raw.get(
                        "source_out_sec",
                        raw.get("out_sec", base_source_in + _number(raw.get("end_sec")) - narration_start),
                    )
                )
                base_clip_id = str(raw.get("clip_id") or "narration")
                for caption in caption_clips:
                    source_id = str(caption.get("segment_id") or "")
                    caption_source_in = base_source_in + _number(caption.get("start_sec")) - narration_start
                    caption_duration = _number(caption.get("end_sec")) - _number(caption.get("start_sec"))
                    for target_index, (segment, source_slice, placement) in enumerate(source_targets.get(source_id, [])):
                        source_offset = float(source_slice["source_offset_sec"])
                        if source_slice.get("legacy_timeline_anchor"):
                            source_offset -= _number(caption.get("start_sec"))
                        duration = min(
                            float(source_slice["duration_sec"]),
                            caption_duration - source_offset,
                            source_limit - caption_source_in - source_offset,
                        )
                        if duration <= 0:
                            continue
                        clip = deepcopy(raw)
                        target_segment_id = str(segment.get("segment_id") or source_id)
                        clip["clip_id"] = f"{base_clip_id}__{source_id}__{target_segment_id}__{target_index}"
                        clip["segment_id"] = target_segment_id
                        clip["start_sec"], clip["end_sec"] = placement, placement + duration
                        clip["source_in_sec"] = caption_source_in + source_offset
                        clip["source_out_sec"] = clip["source_in_sec"] + duration
                        clips.append(clip)
                continue
            source_id = str(raw.get("segment_id") or "")
            targets = source_targets.get(source_id)
            if targets is None:
                if source_id in removed_source_ids:
                    continue
                clips.append(deepcopy(raw))
                continue
            original_start, original_end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
            raw_controls = raw.get("media_controls") if isinstance(raw.get("media_controls"), dict) else {}
            base_source_in = _number(raw.get("source_in_sec", raw.get("in_sec", 0.0)))
            has_explicit_source_out = "source_out_sec" in raw or "out_sec" in raw
            base_source_out = _number(
                raw.get(
                    "source_out_sec",
                    raw.get("out_sec", base_source_in + (original_end - original_start)),
                )
            )
            bake_source_controls = track_type == "broll" and any(
                key in raw_controls for key in ("trim_start_sec", "in_sec", "out_sec")
            )
            if bake_source_controls:
                trim_start = _number(raw_controls.get("trim_start_sec"))
                original_source_in = base_source_in + trim_start + _number(raw_controls.get("in_sec"))
                natural_source_out = (
                    base_source_out + trim_start
                    if has_explicit_source_out
                    else original_source_in + (original_end - original_start)
                )
                original_source_out = min(
                    natural_source_out,
                    _number(raw_controls.get("out_sec"), natural_source_out),
                )
            else:
                original_source_in = base_source_in
                original_source_out = base_source_out
            for segment, source_slice, placement in targets:
                duration = float(source_slice["duration_sec"])
                if duration <= 0:
                    continue
                override_field = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}.get(track_type)
                offset = float(source_slice["source_offset_sec"])
                if source_slice.get("legacy_timeline_anchor"):
                    offset -= original_start
                source_in = original_source_in + offset
                covered = _session_override_windows(segment=segment, override_field=override_field) if override_field else []
                for interval_start, interval_end in _uncovered_intervals(start=placement, end=placement + duration, covered=covered):
                    clip = deepcopy(raw)
                    source_piece_start = source_in + interval_start - placement
                    clip["segment_id"] = str(segment.get("segment_id") or source_id)
                    clip["start_sec"], clip["end_sec"] = interval_start, interval_end
                    clip["source_in_sec"], clip["source_out_sec"] = source_piece_start, min(original_source_out, source_piece_start + interval_end - interval_start)
                    if bake_source_controls:
                        controls = deepcopy(raw_controls)
                        controls.pop("trim_start_sec", None)
                        controls.pop("in_sec", None)
                        controls.pop("out_sec", None)
                        clip["media_controls"] = controls
                    clips.append(clip)
        if clips:
            tracks[track_type] = clips
    removed_segment_ids = {
        segment_id for segment_id, segment in segments.items()
        if str(segment.get("cut_action") or "keep") == "remove"
    }
    export_overlays: list[dict[str, Any]] = []
    for overlay_index, raw_overlay in enumerate(timeline.get("export_overlays", [])):
        if not isinstance(raw_overlay, dict):
            continue
        source_id = str(raw_overlay.get("segment_id") or "")
        if source_id in removed_segment_ids:
            continue
        targets = source_targets.get(source_id)
        original_bounds = source_bounds.get(source_id)
        if not targets or original_bounds is None:
            export_overlays.append({**deepcopy(raw_overlay), "clip_id": str(raw_overlay.get("clip_id") or f"export-overlay-{source_id}-{overlay_index}")})
            continue
        for _segment, source_slice, placement in targets:
            window_end = placement + float(source_slice["duration_sec"])
            relative_start = _number(raw_overlay.get("start_sec")) - original_bounds[0] - float(source_slice["source_offset_sec"])
            relative_end = _number(raw_overlay.get("end_sec")) - original_bounds[0] - float(source_slice["source_offset_sec"])
            start, end = max(placement, placement + relative_start), min(window_end, placement + relative_end)
            if end > start:
                export_overlays.append({**deepcopy(raw_overlay), "clip_id": str(raw_overlay.get("clip_id") or f"export-overlay-{source_id}-{overlay_index}"), "segment_id": source_id, "start_sec": start, "end_sec": end})
    session_captions: list[dict[str, Any]] = []
    for segment_id, segment in segments.items():
        if str(segment.get("cut_action") or "keep") == "remove":
            continue
        start, end = _number(segment.get("start_sec")), _number(segment.get("end_sec"))
        if end <= start:
            continue
        raw_windows = segment.get("media_windows")
        windows = raw_windows if isinstance(raw_windows, list) and raw_windows else [{
            "start_offset_sec": 0.0, "duration_sec": end - start,
            "broll_override": segment.get("broll_override"), "music_override": segment.get("music_override"), "sfx_override": segment.get("sfx_override"),
        }]
        for track_type, field in (("broll", "broll_override"), ("bgm", "music_override"), ("sfx", "sfx_override")):
            direct_override = segment.get(field)
            field_windows = [{
                "start_offset_sec": 0.0, "duration_sec": end - start, field: direct_override,
            }] if isinstance(direct_override, dict) else windows
            for window_index, window in enumerate(field_windows):
                if not isinstance(window, dict):
                    continue
                window_start = start + _number(window.get("start_offset_sec"))
                window_end = min(end, window_start + _number(window.get("duration_sec")))
                if window_end <= window_start:
                    continue
                override = window.get(field)
                if not isinstance(override, dict) or not str(override.get("asset_id") or override.get("asset_uri") or "").strip():
                    continue
                asset_id = str(override.get("asset_id") or "").strip() or None
                asset_uri = str(override.get("asset_uri") or "").strip()
                if not asset_uri and asset_id and project:
                    asset_uri = f"local://projects/{project}/assets/{asset_id}"
                clip: dict[str, Any] = {"clip_id": f"session-{track_type}-{segment_id}-{window_index}", "segment_id": segment_id, "asset_id": asset_id, "asset_uri": asset_uri or None, "start_sec": window_start, "end_sec": window_end, "media_controls": deepcopy(override.get("media_controls") or {})}
                for key in ("expected_content_sha256", "media_revision"):
                    if override.get(key):
                        clip[key] = override[key]
                tracks.setdefault(track_type, []).append(clip)
        for window_index, window in enumerate(_segment_content_windows(segment)):
            window_start = start + _number(window.get("start_offset_sec"))
            window_end = min(end, window_start + _number(window.get("duration_sec")))
            if window_end <= window_start:
                continue
            content_segment_id = str(window.get("source_segment_id") or segment_id)
            session_captions.append({"caption_id": str(window.get("caption_id") or f"caption-{segment_id}-{window_index}"), "segment_id": content_segment_id, "caption_text": str(window.get("caption_text") or ""), "caption_style": deepcopy(window.get("caption_style") or segment.get("caption_style") or editing_session.get("caption_style") or {}), "start_sec": window_start, "end_sec": window_end, "review_required": window.get("review_required"), "tts_replacement": deepcopy(window.get("tts_replacement"))})
            for ordinal, overlay in enumerate(window.get("visual_overlays", []) if isinstance(window.get("visual_overlays"), list) else []):
                if not isinstance(overlay, dict):
                    continue
                payload = deepcopy(overlay)
                payload["overlay_type"] = _canonical_overlay_type(payload.get("overlay_type"))
                if content_segment_id != segment_id:
                    payload["source_segment_id"] = content_segment_id
                asset_id = str(payload.get("asset_id") or "").strip() or None
                asset_uri = str(payload.get("asset_uri") or "").strip()
                if not asset_uri and asset_id and project:
                    asset_uri = f"local://projects/{project}/assets/{asset_id}"
                if asset_uri:
                    clip = {"clip_id": f"session-overlay-{segment_id}-{window_index}-{ordinal}", "segment_id": segment_id, "asset_id": asset_id, "asset_uri": asset_uri, "start_sec": window_start, "end_sec": window_end, "overlay_type": str(payload.get("overlay_type") or "visual_overlay"), "overlay_payload": payload}
                    for key in ("expected_content_sha256", "media_revision"):
                        if payload.get(key):
                            clip[key] = payload[key]
                    tracks.setdefault("overlay", []).append(clip)
                else:
                    export_overlays.append({**payload, "clip_id": str(payload.get("clip_id") or f"session-overlay-{segment_id}-{window_index}-{ordinal}"), "segment_id": segment_id, "start_sec": window_start, "end_sec": window_end})
    materialized_gaps: list[dict[str, Any]] = []
    for raw_gap in timeline.get("gap_slots", []):
        if not isinstance(raw_gap, dict):
            continue
        source_id = str(raw_gap.get("segment_id") or "")
        targets = source_targets.get(source_id)
        if targets is None:
            if source_id not in removed_source_ids:
                materialized_gaps.append(deepcopy(raw_gap))
            continue
        for segment, source_slice, placement in targets:
            duration = float(source_slice["duration_sec"])
            if duration <= 0:
                continue
            gap = deepcopy(raw_gap)
            gap["segment_id"] = str(segment.get("segment_id") or source_id)
            gap["target_range"] = {
                "start_sec": placement,
                "end_sec": placement + duration,
            }
            if "start_sec" in gap:
                gap["start_sec"] = placement
            if "end_sec" in gap:
                gap["end_sec"] = placement + duration
            materialized_gaps.append(gap)

    def materialized_track_id(kind: str) -> str:
        existing = track_ids.get(kind)
        if existing is not None:
            return existing
        base = f"track_{kind}"
        candidate = base
        suffix = 2
        while candidate in used_track_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        track_ids[kind] = candidate
        used_track_ids.add(candidate)
        return candidate

    materialized["tracks"] = [
        {
            "track_id": materialized_track_id(kind),
            "track_type": kind,
            "clips": clips,
        }
        for kind, clips in tracks.items()
        if clips
    ]
    materialized["gap_slots"] = materialized_gaps
    materialized["export_overlays"] = export_overlays
    materialized["session_captions"] = session_captions
    from videobox_core_engine.timeline_placements import apply_timeline_placement_overrides
    overrides = editing_session.get("timeline_placement_overrides")
    return apply_timeline_placement_overrides(timeline=materialized, overrides=overrides if isinstance(overrides, dict) else {})


def _number(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not isfinite(parsed):
        raise ValueError("composition_plan_invalid_number")
    return parsed


def _canonical_overlay_type(value: object) -> str:
    overlay_type = str(value or "").strip()
    if overlay_type == "explanation_card":
        return overlay_type
    if overlay_type in {"image", "image_card", "image_overlay"}:
        return "image_overlay"
    if overlay_type in {"table_card", "table_overlay"}:
        return "table_overlay"
    return overlay_type or "visual_overlay"


@dataclass(frozen=True, slots=True)
class CompositionItem:
    clip_id: str
    track_type: str
    asset_uri: str | None
    asset_id: str | None
    start_sec: float
    end_sec: float
    source_in_sec: float
    source_out_sec: float
    media_controls: dict[str, Any] = field(default_factory=dict)
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    overlay_type: str | None = None
    overlay_payload: dict[str, Any] = field(default_factory=dict)

    def clipped(self, *, start_sec: float, end_sec: float) -> "CompositionItem | None":
        left, right = max(self.start_sec, start_sec), min(self.end_sec, end_sec)
        if right <= left:
            return None
        # Shift source only by the left-hand clipping amount.  The resulting
        # output is already zero based; callers must not apply another offset.
        source_start = self.source_in_sec + (left - self.start_sec)
        return CompositionItem(
            clip_id=self.clip_id, track_type=self.track_type, asset_uri=self.asset_uri, asset_id=self.asset_id,
            start_sec=left - start_sec, end_sec=right - start_sec,
            source_in_sec=source_start, source_out_sec=source_start + (right - left),
            media_controls=dict(self.media_controls), expected_content_sha256=self.expected_content_sha256,
            media_revision=self.media_revision, overlay_type=self.overlay_type,
            overlay_payload=dict(self.overlay_payload),
        )


@dataclass(frozen=True, slots=True)
class CaptionCue:
    start_sec: float
    end_sec: float
    text: str
    style: dict[str, Any] = field(default_factory=dict)
    segment_id: str | None = None

    def clipped(self, *, start_sec: float, end_sec: float) -> "CaptionCue | None":
        left, right = max(self.start_sec, start_sec), min(self.end_sec, end_sec)
        if right <= left:
            return None
        return CaptionCue(left - start_sec, right - start_sec, self.text, dict(self.style), self.segment_id)


@dataclass(frozen=True, slots=True)
class CompositionPlan:
    width: int
    height: int
    fps_num: int
    fps_den: int
    sample_aspect_ratio: str
    rotation: int
    items: tuple[CompositionItem, ...]
    captions: tuple[CaptionCue, ...] = ()
    export_overlays: tuple[dict[str, Any], ...] = ()
    version: str = COMPOSITION_VERSION

    @property
    def duration_sec(self) -> float:
        return max(
            [item.end_sec for item in self.items]
            + [cue.end_sec for cue in self.captions]
            + [_number(overlay.get("end_sec")) for overlay in self.export_overlays]
            + [0.0]
        )

    @classmethod
    def from_timeline(cls, *, timeline: dict[str, Any], captions: Iterable[dict[str, Any] | CaptionCue] = ()) -> "CompositionPlan":
        output = timeline.get("output") if isinstance(timeline.get("output"), dict) else {}
        raw_items: list[CompositionItem] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = str(track.get("track_type") or "").strip().lower()
            if track_type not in _SUPPORTED_TRACKS:
                continue
            for index, raw in enumerate(track.get("clips", []) if isinstance(track.get("clips"), list) else []):
                if not isinstance(raw, dict):
                    continue
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end <= start:
                    continue
                source_in = _number(raw.get("source_in_sec", raw.get("in_sec", 0.0)))
                has_explicit_source_out = "source_out_sec" in raw or "out_sec" in raw
                source_out = _number(raw.get("source_out_sec", raw.get("out_sec", source_in + (end - start))))
                if source_out < source_in:
                    source_out = source_in + (end - start)
                controls = dict(raw.get("media_controls") or {}) if isinstance(raw.get("media_controls"), dict) else {}
                if track_type == "broll":
                    # Older persisted timelines used ``contain`` for the
                    # current canonical ``fit`` behavior.  Normalize that
                    # legacy spelling before applying source-window controls.
                    if str(controls.get("fit") or "").strip().lower() == "contain":
                        controls["fit"] = "fit"
                    normalized = normalize_media_controls(controls, media_kind="broll", duration_sec=end - start)
                    source_in += normalized["trim_start_sec"] + float(normalized.get("in_sec", 0.0))
                    natural_source_out = (
                        source_out + normalized["trim_start_sec"]
                        if has_explicit_source_out
                        else source_in + (end - start)
                    )
                    source_out = min(natural_source_out, float(normalized.get("out_sec", natural_source_out)))
                    controls = normalized
                    if source_out <= source_in:
                        raise ValueError("composition_plan_invalid_source_bounds")
                    if source_out - source_in < end - start and not controls["loop"] and not controls["pad"]:
                        raise ValueError("composition_plan_insufficient_broll_source")
                raw_items.append(CompositionItem(
                    clip_id=str(raw.get("clip_id") or f"{track_type}-{index}"), track_type=track_type,
                    asset_uri=str(raw["asset_uri"]) if raw.get("asset_uri") is not None else None,
                    asset_id=str(raw["asset_id"]) if raw.get("asset_id") is not None else None,
                    start_sec=start, end_sec=end, source_in_sec=source_in, source_out_sec=source_out,
                    media_controls=controls,
                    expected_content_sha256=str(raw.get("expected_content_sha256") or "").strip() or None,
                    media_revision=str(raw.get("media_revision") or "").strip() or None,
                    overlay_type=str(raw.get("overlay_type")) if raw.get("overlay_type") is not None else None,
                    overlay_payload=dict(raw.get("overlay_payload") or {}) if isinstance(raw.get("overlay_payload"), dict) else {},
                ))
        cues: list[CaptionCue] = []
        for raw in captions:
            if isinstance(raw, CaptionCue):
                cues.append(raw)
            elif isinstance(raw, dict):
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end > start:
                    raw_style = raw.get("style") if isinstance(raw.get("style"), dict) else raw.get("caption_style")
                    cues.append(CaptionCue(start, end, str(raw.get("text") or raw.get("caption_text") or ""), dict(raw_style) if isinstance(raw_style, dict) else {}, str(raw["segment_id"]) if raw.get("segment_id") else None))
        overlays = tuple(
            dict(overlay)
            for overlay in timeline.get("export_overlays", [])
            if isinstance(overlay, dict) and _number(overlay.get("end_sec"), _number(overlay.get("start_sec"))) > _number(overlay.get("start_sec"))
        )
        return cls(
            width=max(1, int(_number(output.get("width") or timeline.get("video_width") or 1280))),
            height=max(1, int(_number(output.get("height") or timeline.get("video_height") or 720))),
            fps_num=max(1, int(_number(output.get("fps_num") or timeline.get("fps_num") or 30))),
            fps_den=max(1, int(_number(output.get("fps_den") or timeline.get("fps_den") or 1))),
            sample_aspect_ratio=str(output.get("sample_aspect_ratio") or timeline.get("sample_aspect_ratio") or "1:1"),
            rotation=int(output.get("rotation") or timeline.get("rotation") or 0),
            items=tuple(sorted(raw_items, key=lambda item: (item.start_sec, item.track_type, item.clip_id))),
            captions=tuple(sorted(cues, key=lambda cue: (cue.start_sec, cue.end_sec, cue.segment_id or ""))),
            export_overlays=overlays,
        )

    def for_range(self, *, start_sec: float, end_sec: float) -> "CompositionPlan":
        if not isfinite(float(start_sec)) or not isfinite(float(end_sec)) or start_sec < 0 or end_sec <= start_sec or end_sec > self.duration_sec:
            raise ValueError("composition_plan_invalid_range")
        overlays = []
        for overlay in self.export_overlays:
            left, right = max(_number(overlay.get("start_sec")), start_sec), min(_number(overlay.get("end_sec")), end_sec)
            if right > left:
                shifted = dict(overlay)
                shifted["start_sec"], shifted["end_sec"] = left - start_sec, right - start_sec
                overlays.append(shifted)
        return CompositionPlan(self.width, self.height, self.fps_num, self.fps_den, self.sample_aspect_ratio, self.rotation,
            tuple(item for source in self.items if (item := source.clipped(start_sec=start_sec, end_sec=end_sec)) is not None),
            tuple(cue for source in self.captions if (cue := source.clipped(start_sec=start_sec, end_sec=end_sec)) is not None),
            tuple(overlays), self.version)

    def canonical_dict(self) -> dict[str, Any]:
        return {"version": self.version, "canvas": {"width": self.width, "height": self.height, "fps_num": self.fps_num, "fps_den": self.fps_den, "sample_aspect_ratio": self.sample_aspect_ratio, "rotation": self.rotation}, "items": [asdict(item) for item in self.items], "captions": [asdict(cue) for cue in self.captions], "export_overlays": list(self.export_overlays)}


__all__ = ["COMPOSITION_VERSION", "CaptionCue", "CompositionItem", "CompositionPlan", "materialize_editing_session_timeline"]
