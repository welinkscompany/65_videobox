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

from videobox_core_engine.caption_translation import caption_text_for_language
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.transitions import normalize_transition


COMPOSITION_VERSION = "videobox_composition_v1"
DEFAULT_OUTPUT_WIDTH = 1080
DEFAULT_OUTPUT_HEIGHT = 1920
_SUPPORTED_TRACKS = frozenset({"narration", "broll", "bgm", "sfx", "overlay"})
_RIPPLE_PLAYBACK_RATES = frozenset({1.0, 1.5, 2.0})


def _ripple_playback_rate(segment: dict[str, Any]) -> float:
    rate = _number(segment.get("ripple_playback_rate", 1.0))
    if rate not in _RIPPLE_PLAYBACK_RATES:
        raise ValueError("composition_plan_invalid_ripple_playback_rate")
    return rate


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


def _session_override_windows(
    *,
    segment: dict[str, Any],
    override_field: str,
    suppressed_action_ids: frozenset[str] = frozenset(),
) -> list[tuple[float, float]]:
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
        override = window.get(override_field) if isinstance(window, dict) else None
        if not isinstance(override, dict):
            continue
        if str(override.get("source_action_id") or "").strip() in suppressed_action_ids:
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
        **{key: deepcopy(segment.get(key)) for key in ("caption_text", "caption_translations", "caption_style", "review_required", "visual_overlays", "tts_replacement")},
    }]


def materialize_editing_session_timeline(
    *, timeline: dict[str, Any], editing_session: dict[str, Any] | None, project_id: str | None = None,
) -> dict[str, Any]:
    """Purely materialize current session edits before any output consumes them."""
    materialized = deepcopy(timeline)
    if not isinstance(editing_session, dict):
        return materialized
    project = str(project_id or timeline.get("project_id") or "").strip()
    recommendation_decisions = (
        timeline.get("recommendation_decisions")
        if isinstance(timeline.get("recommendation_decisions"), dict)
        else {}
    )
    rejected_sfx_action_ids_by_segment: dict[str, set[str]] = {}
    for recommendation in timeline.get("rejected_recommendations", []):
        if not isinstance(recommendation, dict):
            continue
        recommendation_id = str(recommendation.get("recommendation_id") or "").strip()
        if (
            str(recommendation.get("recommendation_type") or "").strip().lower() != "sfx"
            or str(recommendation.get("decision_state") or "").strip().lower() != "rejected"
            or recommendation_decisions.get(recommendation_id) != "rejected"
        ):
            continue
        payload = recommendation.get("payload")
        action_id = (
            str(payload.get("source_override_action_id") or "").strip()
            if isinstance(payload, dict)
            else ""
        )
        segment_id = str(recommendation.get("target_segment_id") or "").strip()
        if action_id and segment_id:
            rejected_sfx_action_ids_by_segment.setdefault(segment_id, set()).add(action_id)
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
            placement += float(source_slice["duration_sec"]) / _ripple_playback_rate(segment)

    session_output_end = max(
        (
            _number(segment.get("end_sec"))
            for segment in segments.values()
            if str(segment.get("cut_action") or "keep") != "remove"
        ),
        default=0.0,
    )

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
                clip = deepcopy(raw)
                # BGM has no scene id, so no source target can carry the
                # ripple.  It must stay at normal pitch but cannot outlive
                # the shortened final timeline.
                if track_type == "bgm" and session_output_end > _number(clip.get("start_sec")):
                    clip["end_sec"] = min(_number(clip.get("end_sec")), session_output_end)
                if _number(clip.get("end_sec")) > _number(clip.get("start_sec")):
                    clips.append(clip)
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
                source_duration = float(source_slice["duration_sec"])
                rate = _ripple_playback_rate(segment)
                duration = source_duration / rate
                if duration <= 0:
                    continue
                override_field = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}.get(track_type)
                offset = float(source_slice["source_offset_sec"])
                if source_slice.get("legacy_timeline_anchor"):
                    offset -= original_start
                source_in = original_source_in + offset
                suppressed_action_ids = (
                    frozenset(rejected_sfx_action_ids_by_segment.get(str(segment.get("segment_id") or ""), set()))
                    if track_type == "sfx"
                    else frozenset()
                )
                covered = (
                    _session_override_windows(
                        segment=segment,
                        override_field=override_field,
                        suppressed_action_ids=suppressed_action_ids,
                    )
                    if override_field
                    else []
                )
                for interval_start, interval_end in _uncovered_intervals(start=placement, end=placement + duration, covered=covered):
                    clip = deepcopy(raw)
                    source_piece_start = source_in + (interval_start - placement) * rate
                    clip["segment_id"] = str(segment.get("segment_id") or source_id)
                    clip["start_sec"], clip["end_sec"] = interval_start, interval_end
                    clip["source_in_sec"], clip["source_out_sec"] = source_piece_start, min(original_source_out, source_piece_start + (interval_end - interval_start) * rate)
                    clip["playback_rate"] = rate
                    if track_type == "broll":
                        clip["effective_playback_rate"] = rate * _number(raw_controls.get("speed"), 1.0)
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
    # 자막 언어는 **여기서 한 번만** 읽는다. 렌더 경로가 둘이라 인자로
    # 흘리면 한쪽만 고쳐진다(`caption_translation` 모듈 주석 참고).
    caption_language = str(editing_session.get("caption_language") or "").strip() or None
    session_captions: list[dict[str, Any]] = []
    for segment_id, segment in segments.items():
        if str(segment.get("cut_action") or "keep") == "remove":
            continue
        start, end = _number(segment.get("start_sec")), _number(segment.get("end_sec"))
        segment_playback_rate = _ripple_playback_rate(segment)
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
                if (
                    track_type == "sfx"
                    and str(override.get("source_action_id") or "").strip()
                    in rejected_sfx_action_ids_by_segment.get(segment_id, set())
                ):
                    continue
                asset_id = str(override.get("asset_id") or "").strip() or None
                asset_uri = str(override.get("asset_uri") or "").strip()
                if not asset_uri and asset_id and project:
                    asset_uri = f"local://projects/{project}/assets/{asset_id}"
                playback_rate = 1.0 if track_type == "bgm" else segment_playback_rate
                clip: dict[str, Any] = {
                    "clip_id": f"session-{track_type}-{segment_id}-{window_index}",
                    "segment_id": segment_id,
                    "asset_id": asset_id,
                    "asset_uri": asset_uri or None,
                    "start_sec": window_start,
                    "end_sec": window_end,
                    "playback_rate": playback_rate,
                    "media_controls": deepcopy(override.get("media_controls") or {}),
                }
                # B-roll's `in_sec`/`out_sec` is resolved by
                # CompositionPlan.  Supplying a synthetic source range here
                # turns that established trim into a second trim and can make
                # a valid range empty.  Audio has no such source-window
                # controls, so it can carry the exact accelerated source span.
                if track_type != "broll":
                    clip["source_in_sec"] = 0.0
                    clip["source_out_sec"] = (window_end - window_start) * playback_rate
                if track_type == "broll":
                    clip["effective_playback_rate"] = playback_rate * _number(
                        clip["media_controls"].get("speed"),
                        1.0,
                    )
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
            session_captions.append({"caption_id": str(window.get("caption_id") or f"caption-{segment_id}-{window_index}"), "segment_id": content_segment_id, "caption_text": caption_text_for_language(window, caption_language), "caption_style": deepcopy(window.get("caption_style") or segment.get("caption_style") or editing_session.get("caption_style") or {}), "start_sec": window_start, "end_sec": window_end, "playback_rate": segment_playback_rate, "review_required": window.get("review_required"), "tts_replacement": deepcopy(window.get("tts_replacement")), "caption_source_text": str(window.get("caption_text") or ""), "caption_language": caption_language})
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
                    clip = {"clip_id": f"session-overlay-{segment_id}-{window_index}-{ordinal}", "segment_id": segment_id, "asset_id": asset_id, "asset_uri": asset_uri, "start_sec": window_start, "end_sec": window_end, "playback_rate": segment_playback_rate, "overlay_type": str(payload.get("overlay_type") or "visual_overlay"), "overlay_payload": payload}
                    for key in ("expected_content_sha256", "media_revision"):
                        if payload.get(key):
                            clip[key] = payload[key]
                    tracks.setdefault("overlay", []).append(clip)
                else:
                    candidate = {
                        **payload,
                        "clip_id": str(
                            payload.get("clip_id")
                            or f"session-overlay-{segment_id}-{window_index}-{ordinal}"
                        ),
                        "segment_id": segment_id,
                        "start_sec": window_start,
                        "end_sec": window_end,
                    }
                    identity_keys = (
                        "overlay_type",
                        "asset_id",
                        "asset_uri",
                        "text",
                        "title",
                        "body",
                        "segment_id",
                        "start_sec",
                        "end_sec",
                    )
                    candidate_identity = tuple(candidate.get(key) for key in identity_keys)
                    if not any(
                        tuple(existing.get(key) for key in identity_keys)
                        == candidate_identity
                        for existing in export_overlays
                    ):
                        export_overlays.append(candidate)
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
            covered = _session_override_windows(segment=segment, override_field="broll_override")
            for gap_start, gap_end in _uncovered_intervals(
                start=placement,
                end=placement + duration,
                covered=covered,
            ):
                gap = deepcopy(raw_gap)
                gap["segment_id"] = str(segment.get("segment_id") or source_id)
                gap["target_range"] = {
                    "start_sec": gap_start,
                    "end_sec": gap_end,
                }
                if "start_sec" in gap:
                    gap["start_sec"] = gap_start
                if "end_sec" in gap:
                    gap["end_sec"] = gap_end
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

    # 장면의 전환을 그 장면을 **여는** 화면 클립에 싣는다.
    #
    # 장면 하나가 화면 클립 여러 개로 쪼개질 수 있다(override 창, 빈 구간).
    # 전환은 장면이 시작하는 경계 하나에만 붙으므로 **가장 앞선 클립**만 받는다.
    # 뒤쪽 클립까지 받으면 장면 한복판에서 전환이 또 돈다.
    for segment_id, segment in segments.items():
        transition = normalize_transition(segment.get("transition_in"))
        if transition is None or str(segment.get("cut_action") or "keep") == "remove":
            continue
        opening = min(
            (
                clip for clip in tracks.get("broll", [])
                if str(clip.get("segment_id") or "") == segment_id
            ),
            key=lambda clip: _number(clip.get("start_sec")),
            default=None,
        )
        if opening is not None:
            opening["transition"] = dict(transition)

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
    from videobox_core_engine.track_states import apply_track_states_to_timeline, normalize_track_states
    overrides = editing_session.get("timeline_placement_overrides")
    placed = apply_timeline_placement_overrides(timeline=materialized, overrides=overrides if isinstance(overrides, dict) else {})
    # 눈·음소거를 트랙 dict에 실어 준다. 여기서 얹어야 렌더러가 세션을 다시
    # 열지 않고 타임라인만 보고 판단할 수 있다.
    return apply_track_states_to_timeline(
        timeline=placed,
        states=normalize_track_states(editing_session.get("track_states")),
    )


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
    # Scene ripple rate.  B-roll's media_controls.speed remains an independent
    # source-control rate; renderers combine the two only for that track.
    playback_rate: float = 1.0
    media_controls: dict[str, Any] = field(default_factory=dict)
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    overlay_type: str | None = None
    overlay_payload: dict[str, Any] = field(default_factory=dict)
    # 앞 장면에서 이 클립으로 넘어오는 방법. **클립 경계에 붙는 값**이라
    # 들어오는 쪽에 싣는다 -- 경계는 이 클립의 시작 시각 하나로 정해진다.
    transition: dict[str, Any] | None = None

    def clipped(self, *, start_sec: float, end_sec: float) -> "CompositionItem | None":
        left, right = max(self.start_sec, start_sec), min(self.end_sec, end_sec)
        if right <= left:
            return None
        # Shift source only by the left-hand clipping amount.  The resulting
        # output is already zero based; callers must not apply another offset.
        source_start = self.source_in_sec + (left - self.start_sec) * self.playback_rate
        return CompositionItem(
            clip_id=self.clip_id, track_type=self.track_type, asset_uri=self.asset_uri, asset_id=self.asset_id,
            start_sec=left - start_sec, end_sec=right - start_sec,
            source_in_sec=source_start, source_out_sec=source_start + (right - left) * self.playback_rate,
            playback_rate=self.playback_rate,
            media_controls=dict(self.media_controls), expected_content_sha256=self.expected_content_sha256,
            media_revision=self.media_revision, overlay_type=self.overlay_type,
            overlay_payload=dict(self.overlay_payload),
            # 앞을 잘라 내면 **넘어올 앞 장면이 없다.** 전환은 경계에 붙은
            # 값이므로 경계가 사라지면 같이 사라진다. 그대로 두면 구간
            # 미리보기의 첫 프레임이 난데없이 전환으로 시작한다.
            transition=dict(self.transition) if self.transition and left == self.start_sec else None,
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
    # 소리를 끈 레인(`track_states.py`). 렌더러가 이 레인의 소리를 안 섞는다 --
    # 트랙마다 음량 제어가 달라서 값 하나를 덮어쓰는 방식으로는 못 끈다.
    muted_tracks: frozenset[str] = frozenset()
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
        # 눈·음소거는 **맨 위 한 칸**에서 읽는다(`track_states.py`). 트랙마다
        # 표시하는 방식은 materializer가 안 만드는 트랙(자막, 빈 오버레이)을
        # 영영 못 잡았다 -- 그 주석은 `apply_track_states_to_timeline`에 있다.
        from videobox_core_engine.track_states import hidden_lanes, muted_lanes
        hidden = hidden_lanes(timeline)
        muted = muted_lanes(timeline)
        raw_items: list[CompositionItem] = []
        gap_slot_ids = {
            str(gap.get("gap_slot_id") or "").strip()
            for gap in timeline.get("gap_slots", [])
            if isinstance(gap, dict) and str(gap.get("gap_slot_id") or "").strip()
        }
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = str(track.get("track_type") or "").strip().lower()
            if track_type not in _SUPPORTED_TRACKS:
                continue
            # 눈(`track_states.py`). **숨김은 통째로 뺀다.** 음소거는 여기서
            # 손대지 않는다 -- 클립을 빼면 그림까지 사라지고, 음량 제어가
            # 트랙마다 달라 값 하나로는 못 끈다. 렌더러가 맡는다.
            if track_type in hidden:
                continue
            for index, raw in enumerate(track.get("clips", []) if isinstance(track.get("clips"), list) else []):
                if not isinstance(raw, dict):
                    continue
                gap_slot_id = str(raw.get("gap_slot_id") or "").strip()
                asset_id = str(raw.get("asset_id") or "").strip()
                if track_type == "broll" and gap_slot_id in gap_slot_ids and asset_id.startswith("asset_gap_placeholder_"):
                    # Draft gap placeholders are in-app guidance surfaces, not
                    # video inputs.  Gap metadata remains authoritative while
                    # exact previews render the available composition only.
                    continue
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end <= start:
                    continue
                source_in = _number(raw.get("source_in_sec", raw.get("in_sec", 0.0)))
                has_explicit_source_out = "source_out_sec" in raw or "out_sec" in raw
                source_out = _number(raw.get("source_out_sec", raw.get("out_sec", source_in + (end - start))))
                if source_out < source_in:
                    source_out = source_in + (end - start)
                playback_rate = _number(raw.get("playback_rate", 1.0))
                if playback_rate <= 0:
                    raise ValueError("composition_plan_invalid_playback_rate")
                controls = dict(raw.get("media_controls") or {}) if isinstance(raw.get("media_controls"), dict) else {}
                if track_type == "broll":
                    # Older persisted timelines used ``contain`` for the
                    # current canonical ``fit`` behavior.  Normalize that
                    # legacy spelling before applying source-window controls.
                    if str(controls.get("fit") or "").strip().lower() == "contain":
                        controls["fit"] = "fit"
                    normalized = normalize_media_controls(controls, media_kind="broll", duration_sec=end - start)
                    # 배속은 **원본을 얼마나 먹는가**를 바꾼다. 2배속으로 4초를
                    # 채우려면 원본 8초가 필요하다. 이걸 빼먹으면 절반만 빨리
                    # 지나가고 뒤가 빈다.
                    speed = float(normalized["speed"])
                    source_in += normalized["trim_start_sec"] + float(normalized.get("in_sec", 0.0))
                    natural_source_out = (
                        source_out + normalized["trim_start_sec"]
                        if has_explicit_source_out
                        else source_in + (end - start) * speed * playback_rate
                    )
                    source_out = min(natural_source_out, float(normalized.get("out_sec", natural_source_out)))
                    controls = normalized
                    if source_out <= source_in:
                        raise ValueError("composition_plan_invalid_source_bounds")
                    # 모자란지도 배속을 반영해 잰다. 원본 4초는 0.5배속에서
                    # 타임라인 8초를 채운다 -- 배속을 무시하면 멀쩡한 것을 막는다.
                    if (source_out - source_in) / speed < end - start and not controls["loop"] and not controls["pad"]:
                        raise ValueError("composition_plan_insufficient_broll_source")
                raw_items.append(CompositionItem(
                    clip_id=str(raw.get("clip_id") or f"{track_type}-{index}"), track_type=track_type,
                    asset_uri=str(raw["asset_uri"]) if raw.get("asset_uri") is not None else None,
                    asset_id=str(raw["asset_id"]) if raw.get("asset_id") is not None else None,
                    start_sec=start, end_sec=end, source_in_sec=source_in, source_out_sec=source_out,
                    playback_rate=playback_rate,
                    media_controls=controls,
                    expected_content_sha256=str(raw.get("expected_content_sha256") or "").strip() or None,
                    media_revision=str(raw.get("media_revision") or "").strip() or None,
                    overlay_type=str(raw.get("overlay_type")) if raw.get("overlay_type") is not None else None,
                    overlay_payload=dict(raw.get("overlay_payload") or {}) if isinstance(raw.get("overlay_payload"), dict) else {},
                    # 전환은 **화면 클립에만** 붙는다. 소리 트랙의 경계에는
                    # 넘길 그림이 없다 -- 조용히 무시하지 않고 아예 안 읽는다.
                    transition=normalize_transition(raw.get("transition")) if track_type == "broll" else None,
                ))
        # **트랙 순회가 못 잡는 레인이 둘 있다**(`track_states.py`). 자막은 따로
        # 들어오고(`captions=`), 글자 오버레이(설명 카드·표·도형)는 트랙이 아니라
        # `export_overlays`에 있다. 둘 다 화면에는 자기 레인으로 그려지므로,
        # 눈을 끄면 사라진 것처럼 보이는데 완성본에는 그대로 박힌다.
        #
        # 자막만 고치고 오버레이를 놓쳐서 같은 실패를 두 번 냈다(2026-08-23).
        # 그래서 한 자리에서 한꺼번에 읽는다 -- 레인이 늘면 여기만 본다.
        cues: list[CaptionCue] = []
        for raw in () if "caption" in hidden else captions:
            if isinstance(raw, CaptionCue):
                cues.append(raw)
            elif isinstance(raw, dict):
                start, end = _number(raw.get("start_sec")), _number(raw.get("end_sec"))
                if end > start:
                    raw_style = raw.get("style") if isinstance(raw.get("style"), dict) else raw.get("caption_style")
                    cues.append(CaptionCue(start, end, str(raw.get("text") or raw.get("caption_text") or ""), dict(raw_style) if isinstance(raw_style, dict) else {}, str(raw["segment_id"]) if raw.get("segment_id") else None))
        # 오버레이 레인을 껐으면 글자 오버레이도 함께 빠진다 -- 위 `hidden_lanes`
        # 주석 참고. `tracks` 쪽 오버레이 클립은 이미 트랙 순회에서 빠졌고,
        # 여기 있는 것이 그 나머지 절반이다.
        overlays = () if "overlay" in hidden else tuple(
            dict(overlay)
            for overlay in timeline.get("export_overlays", [])
            if isinstance(overlay, dict) and _number(overlay.get("end_sec"), _number(overlay.get("start_sec"))) > _number(overlay.get("start_sec"))
        )
        return cls(
            width=max(1, int(_number(output.get("width") or timeline.get("video_width") or DEFAULT_OUTPUT_WIDTH))),
            height=max(1, int(_number(output.get("height") or timeline.get("video_height") or DEFAULT_OUTPUT_HEIGHT))),
            fps_num=max(1, int(_number(output.get("fps_num") or timeline.get("fps_num") or 30))),
            fps_den=max(1, int(_number(output.get("fps_den") or timeline.get("fps_den") or 1))),
            sample_aspect_ratio=str(output.get("sample_aspect_ratio") or timeline.get("sample_aspect_ratio") or "1:1"),
            rotation=int(output.get("rotation") or timeline.get("rotation") or 0),
            items=tuple(sorted(raw_items, key=lambda item: (item.start_sec, item.track_type, item.clip_id))),
            captions=tuple(sorted(cues, key=lambda cue: (cue.start_sec, cue.end_sec, cue.segment_id or ""))),
            export_overlays=overlays,
            muted_tracks=muted,
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


__all__ = [
    "COMPOSITION_VERSION",
    "DEFAULT_OUTPUT_HEIGHT",
    "DEFAULT_OUTPUT_WIDTH",
    "CaptionCue",
    "CompositionItem",
    "CompositionPlan",
    "materialize_editing_session_timeline",
]
