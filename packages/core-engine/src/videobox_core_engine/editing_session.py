from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from datetime import UTC, datetime
from math import isfinite
import uuid

from videobox_domain_models.caption_style import CaptionStyle
from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.transitions import normalize_transition
from videobox_core_engine.editing_transactions import SESSION_TRACK_STATES_KEY, SESSION_TRACKS_KEY, apply_user_transaction
# 도형 프리셋 목록은 여기서 다시 정의하지 않고 그대로 가져다 쓴다. 예전 이름을
# 그대로 두어 이 모듈에서 가져다 쓰던 곳은 손대지 않아도 된다.
from videobox_core_engine.overlay_shapes import (  # noqa: F401
    SHAPE_OVERLAY_HORIZONTALS,
    SHAPE_OVERLAY_MOTION_SET,
    SHAPE_OVERLAY_SHAPES,
    SHAPE_OVERLAY_SIZES,
    SHAPE_OVERLAY_VERTICALS,
)

MIN_SEGMENT_DURATION_SEC = 0.2
# **리플 배속 허용 범위(owner 지시 2026-09-04, "속도는 캡컷이랑 동일하게 맞춰").**
# 예전에는 `frozenset({1.0, 1.5, 2.0})` 셋뿐이라 1.25배를 쓸 방법이 없었다.
# 캡컷 `속도`는 숫자칸이라 임의 배속을 받는다.
#
# 이 범위는 **렌더가 실제로 낼 수 있는 것**에서 왔다 -- `_atempo_chain`이
# "허용 범위(0.25~4)"를 명시하고 그 범위를 `atempo` 단계로 쪼개 처리한다
# (`ffmpeg_final_renderer.py:92`). 너무 짧아지는 장면은 아래
# `MIN_SEGMENT_DURATION_SEC`이 따로 막는다. 즉 엔진은 처음부터 이 범위를
# 감당하게 만들어져 있었고 검증만 셋으로 좁혀 놨던 것이다.
#
# **유진 스키마는 안 넓힌다.** `set_scene_speed`는 `enum: [1, 1.5, 2]`로 좁게
# 둔다 -- 사람이 고르는 것과 AI가 제안하는 것의 범위가 같을 이유가 없다.
MIN_RIPPLE_PLAYBACK_RATE = 0.25
MAX_RIPPLE_PLAYBACK_RATE = 4.0
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
                "source_slices": [{"segment_id": segment["segment_id"], "source_offset_sec": 0.0, "duration_sec": float(segment["end_sec"]) - float(segment["start_sec"])}],
                "cut_action": segment.get("cleanup_decision", "keep"),
                "review_required": _normalize_boolish(segment.get("review_required", False)),
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
                "content_windows": [{
                    "caption_id": f"caption-{segment['segment_id']}",
                    "start_offset_sec": 0.0,
                    "duration_sec": float(segment["end_sec"]) - float(segment["start_sec"]),
                    "source_segment_id": segment["segment_id"],
                    "caption_text": segment["text"],
                    "review_required": _normalize_boolish(segment.get("review_required", False)),
                    "visual_overlays": [],
                }],
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
        if not isfinite(start_sec) or not isfinite(end_sec) or start_sec < 0 or end_sec - start_sec < MIN_SEGMENT_DURATION_SEC:
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
    _EXCLUDED_KEYS = {"history", "undo_stack", "redo_stack", "output_freshness"}

    def mutate(draft: dict[str, Any]) -> None:
        for key, value in updated.items():
            if key not in _EXCLUDED_KEYS:
                draft[key] = deepcopy(value)
        # `updated`는 `before`(=session)의 deepcopy에서 시작하므로, `before`에는
        # 있었는데 `updated`에는 없는 열쇠는 호출자가 일부러 지운 것이다
        # (`set_track_states`가 "전부 기본"일 때 `track_states`를 pop하는 경우
        # 등). 위 루프는 있는 값만 옮기고 없는 값은 그냥 안 건드리므로, `draft`가
        # `before`를 deepcopy한 채로 남아 그 지움이 전파되지 않았다 -- 마지막
        # 트랙의 눈을 다시 켜도 숨김이 안 풀리던 결함이 이것이었다.
        for key in before.keys() - updated.keys() - _EXCLUDED_KEYS:
            draft.pop(key, None)
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


def _source_slices(segment: dict[str, Any], *, fallback_offset: float | None = None) -> list[dict[str, float | str]]:
    raw = segment.get("source_slices")
    if isinstance(raw, list):
        normalized = [
            {"segment_id": str(item.get("segment_id") or ""), "source_offset_sec": float(item.get("source_offset_sec", 0.0)), "duration_sec": float(item.get("duration_sec", 0.0))}
            for item in raw if isinstance(item, dict) and str(item.get("segment_id") or "") and float(item.get("duration_sec", 0.0)) > 0
        ]
        if normalized:
            return normalized
    return [{"segment_id": str(segment.get("segment_id") or ""), "source_offset_sec": float(segment.get("source_offset_sec", fallback_offset or 0.0)), "duration_sec": float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0))}]


def _has_explicit_source_slices(segment: dict[str, Any]) -> bool:
    """`_source_slices`가 저장된 원본 좌표를 돌려주는지, 폴백을 타는지 가른다.

    폴백은 현재 표시 길이를 원본인 척 돌려준다. 배속처럼 표시 길이를 바꾸는
    연산은 그 차이를 알아야 한다."""
    raw = segment.get("source_slices")
    if not isinstance(raw, list):
        return False
    return any(
        isinstance(item, dict)
        and str(item.get("segment_id") or "")
        and float(item.get("duration_sec", 0.0)) > 0
        for item in raw
    )


def _source_slice_basis(*, session: dict[str, Any], segment: dict[str, Any], fallback_offset: float | None = None) -> list[dict[str, float | str]]:
    """Return the immutable source window from which bounds edits may trim.

    Older sessions only stored the current window.  Their transaction inverse
    payloads retain the pre-trim window, so recover that when possible rather
    than permanently losing source material after a shrink/expand cycle.
    """
    raw = segment.get("source_slice_basis")
    if isinstance(raw, list):
        basis = _source_slices({**segment, "source_slices": raw}, fallback_offset=fallback_offset)
        if basis:
            return basis
    segment_id = str(segment.get("segment_id") or "")
    for event in reversed(session.get("history", [])):
        if not isinstance(event, dict) or event.get("mutation_type") != "segment_bounds_update":
            continue
        inverse = event.get("inverse_payload") if isinstance(event.get("inverse_payload"), dict) else {}
        candidate = next((item for item in inverse.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        if candidate is not None:
            return _source_slices(candidate, fallback_offset=fallback_offset)
    return _source_slices(segment, fallback_offset=fallback_offset)


def _legacy_source_basis_and_window_start(
    *, session: dict[str, Any], segment: dict[str, Any], fallback_offset: float | None = None,
) -> tuple[list[dict[str, float | str]], float] | None:
    """Recover a bounded source basis from a pre-basis edit history.

    This migration is deliberately narrow: it only accepts a complete chain of
    legacy bounds transactions whose oldest snapshot can be proven to contain
    the current source slice.  Anything else remains fail-closed.
    """
    if "source_slice_basis" in segment or "source_slice_window_start_sec" in segment:
        return None
    segment_id = str(segment.get("segment_id") or "")
    transitions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in session.get("history", []):
        if not isinstance(event, dict) or event.get("mutation_type") != "segment_bounds_update":
            continue
        inverse = event.get("inverse_payload") if isinstance(event.get("inverse_payload"), dict) else {}
        forward = event.get("forward_payload") if isinstance(event.get("forward_payload"), dict) else {}
        before = next((item for item in inverse.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        after = next((item for item in forward.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        if before is not None and after is not None:
            transitions.append((before, after))
    if not transitions:
        return None

    current_slices = _source_slices(segment, fallback_offset=fallback_offset)
    if len(current_slices) != 1 or str(current_slices[0]["segment_id"]) != segment_id:
        return None
    previous_after = None
    for before, after in transitions:
        if previous_after is not None and (
            float(previous_after.get("start_sec", 0.0)) != float(before.get("start_sec", 0.0))
            or float(previous_after.get("end_sec", 0.0)) != float(before.get("end_sec", 0.0))
        ):
            return None
        previous_after = after
    latest = transitions[-1][1]
    if (
        float(latest.get("start_sec", 0.0)) != float(segment.get("start_sec", 0.0))
        or float(latest.get("end_sec", 0.0)) != float(segment.get("end_sec", 0.0))
    ):
        return None

    oldest = transitions[0][0]
    leading_trim = sum(
        float(after.get("start_sec", 0.0)) - float(before.get("start_sec", 0.0))
        for before, after in transitions
    )
    if leading_trim < 0:
        return None
    oldest_duration = float(oldest.get("end_sec", 0.0)) - float(oldest.get("start_sec", 0.0))
    if oldest_duration <= 0:
        return None
    if isinstance(oldest.get("source_slices"), list):
        basis = _source_slices(oldest, fallback_offset=fallback_offset)
    else:
        basis = [{
            "segment_id": segment_id,
            "source_offset_sec": float(current_slices[0]["source_offset_sec"]) - leading_trim,
            "duration_sec": oldest_duration,
        }]
    if float(basis[0]["source_offset_sec"]) < 0:
        return None
    expected_current = _slice_source_window(
        slices=basis, leading_trim_sec=leading_trim,
        duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)),
    )
    if expected_current != current_slices:
        return None
    return basis, leading_trim


def _has_unrecoverable_legacy_bounds_transition(*, session: dict[str, Any], segment_id: str) -> bool:
    """Identify pre-basis transactions that cannot safely grow source output.

    A new transaction records durable basis data in its forward snapshot.  A
    pair where both snapshots predate that data is legacy; if the complete
    recovery helper rejects it, it must not silently authorize a synthetic
    right-edge source extension.
    """
    for event in session.get("history", []):
        if not isinstance(event, dict) or event.get("mutation_type") != "segment_bounds_update":
            continue
        inverse = event.get("inverse_payload") if isinstance(event.get("inverse_payload"), dict) else {}
        forward = event.get("forward_payload") if isinstance(event.get("forward_payload"), dict) else {}
        before = next((item for item in inverse.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        after = next((item for item in forward.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id") or "") == segment_id), None)
        if before is None or after is None:
            continue
        if all(
            key not in snapshot
            for snapshot in (before, after)
            for key in ("source_slice_basis", "source_slice_window_start_sec")
        ):
            return True
    return False


def _slice_source_window(*, slices: list[dict[str, float | str]], leading_trim_sec: float, duration_sec: float) -> list[dict[str, float | str]]:
    remaining_trim, remaining_duration = max(0.0, leading_trim_sec), max(0.0, duration_sec)
    output: list[dict[str, float | str]] = []
    for source_slice in slices:
        available = float(source_slice["duration_sec"])
        if remaining_trim >= available:
            remaining_trim -= available
            continue
        offset = float(source_slice["source_offset_sec"]) + remaining_trim
        available -= remaining_trim
        remaining_trim = 0.0
        take = min(available, remaining_duration)
        if take > 0:
            output.append({"segment_id": str(source_slice["segment_id"]), "source_offset_sec": offset, "duration_sec": take})
            remaining_duration -= take
        if remaining_duration <= 0:
            break
    return output


def _extend_unproven_source_basis(*, slices: list[dict[str, float | str]], required_duration_sec: float) -> list[dict[str, float | str]]:
    """Keep the legacy right-edge extension contract without inventing left source."""
    extended = deepcopy(slices)
    available_duration = sum(float(item["duration_sec"]) for item in extended)
    if required_duration_sec <= available_duration:
        return extended
    if not extended:
        raise ValueError("segment_source_expansion_outside_slice")
    extended[-1]["duration_sec"] = float(extended[-1]["duration_sec"]) + required_duration_sec - available_duration
    return extended


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


def _media_windows(segment: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep per-window media authority when adjacent segments become one."""
    raw = segment.get("media_windows")
    if isinstance(raw, list) and raw:
        return [deepcopy(item) for item in raw if isinstance(item, dict)]
    return [{
        "caption_id": f"caption-{str(segment.get('segment_id') or '')}",
        "start_offset_sec": 0.0,
        "duration_sec": float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)),
        **{field: deepcopy(segment.get(field)) for field in ("broll_override", "music_override", "sfx_override")},
    }]


def _segment_media_source_rate(segment: dict[str, Any]) -> float:
    """장면 시간 1초가 b-roll 원본을 몇 초 먹는가(리플 배속).

    `composition_plan`이 세션 선택 클립의 원본 소비량을 재는 식과 같다
    (`(end-start) * speed * playback_rate`). 여기서는 장면 쪽 배속만 보고,
    클립 자체의 `speed`는 `_advanced_broll_source_start`가 본다.
    """
    try:
        rate = float(segment.get("ripple_playback_rate", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return rate if rate > 0 else 1.0


def _advanced_broll_source_start(override: Any, *, by_sec: float) -> Any:
    """장면 앞을 잘라 낸 만큼 b-roll 시작점도 앞으로 감은 사본을 돌려준다.

    **렌더가 b-roll의 시작점으로 읽는 값은 `media_controls.trim_start_sec`
    하나뿐이다.** `source_slices`·`source_offset_sec`는 장면이 자기 원본(내레이션)
    안에서 어디인지를 말할 뿐, 장면에 깔아 놓은 b-roll 자산의 어디를 쓸지는
    말하지 않는다(`composition_plan`의 세션 선택 클립 분기는 `source_in_sec`을
    아예 안 싣는다).

    그래서 장면을 쪼개거나 앞 경계를 뒤로 끌면 여기서 같이 감아 줘야 한다.
    2026-09-12 대표님 실제 영상 실측: 이걸 안 해서 장면 94개가 전부
    `trim_start_sec: 0.0`이었고, 숏폼은 원본 맨 앞 8초를 열 번 반복한 영상이
    나왔다. `loop: true`가 기본이라 길이만 맞고 그림은 계속 처음이었다.

    `media_controls`가 아예 없는 선택에도 칸을 만들어 넣는다 -- 없으면 기본값
    0으로 읽혀 같은 결함이 그대로 남는다.

    앞 경계를 **왼쪽으로** 끌면 `by_sec`이 음수다. 그때는 되감는다. 0보다
    작아질 수는 없으므로 거기서 멈춘다 -- 원본보다 앞은 없다.
    """
    if not isinstance(override, dict) or by_sec == 0:
        return override
    raw_controls = override.get("media_controls")
    controls = dict(raw_controls) if isinstance(raw_controls, dict) else {}
    try:
        speed = float(controls.get("speed", 1.0))
    except (TypeError, ValueError):
        speed = 1.0
    if speed <= 0:
        speed = 1.0
    try:
        current = float(controls.get("trim_start_sec", 0.0))
    except (TypeError, ValueError):
        current = 0.0
    moved = current + by_sec * speed
    if moved < 0:
        moved = 0.0
    if moved == current and isinstance(raw_controls, dict) and "trim_start_sec" in raw_controls:
        return override
    controls["trim_start_sec"] = moved
    return {**override, "media_controls": controls}


def _slice_media_windows(*, segment: dict[str, Any], start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    """Clip a segment's durable media choices and rebase them to a split child."""
    original_start = float(segment.get("start_sec", 0.0))
    return _slice_media_window_basis(
        windows=_media_windows(segment), leading_trim_sec=0.0,
        duration_sec=end_sec - start_sec, basis_start_sec=start_sec - original_start,
        media_source_rate=_segment_media_source_rate(segment),
    )


def _media_window_basis(segment: dict[str, Any]) -> list[dict[str, Any]]:
    raw = segment.get("media_window_basis")
    if isinstance(raw, list):
        return [deepcopy(item) for item in raw if isinstance(item, dict)]
    return _media_windows(segment)


def _slice_media_window_basis(
    *, windows: list[dict[str, Any]], leading_trim_sec: float, duration_sec: float, basis_start_sec: float = 0.0,
    media_source_rate: float = 1.0,
) -> list[dict[str, Any]]:
    """Slice immutable per-track media choices and rebase them to a new segment window."""
    selected_start = basis_start_sec + leading_trim_sec
    selected_end = selected_start + duration_sec
    output: list[dict[str, Any]] = []
    for window in windows:
        window_start = float(window.get("start_offset_sec", 0.0))
        window_end = window_start + float(window.get("duration_sec", 0.0))
        clipped_start, clipped_end = max(selected_start, window_start), min(selected_end, window_end)
        if clipped_end <= clipped_start:
            continue
        sliced = {
            **deepcopy(window),
            "start_offset_sec": clipped_start - selected_start,
            "duration_sec": clipped_end - clipped_start,
        }
        # 창 앞을 잘라 낸 만큼 그 창에 걸린 b-roll도 같이 감는다. 소리
        # (`music_override`/`sfx_override`)에는 시작점 칸 자체가 없다.
        if isinstance(sliced.get("broll_override"), dict):
            sliced["broll_override"] = _advanced_broll_source_start(
                sliced["broll_override"], by_sec=(clipped_start - window_start) * media_source_rate
            )
        output.append(sliced)
    return output


def _clear_windowed_media_override(*, segment: dict[str, Any], field: str) -> None:
    """A new direct choice or clear supersedes stale per-window choices only for that track."""
    for raw in (segment.get("media_windows"), segment.get("media_window_basis")):
        if isinstance(raw, list):
            for window in raw:
                if isinstance(window, dict):
                    window.pop(field, None)


def _effective_media_windows(segment: dict[str, Any]) -> list[dict[str, Any]]:
    """창에 **지금 실제로 렌더되는 것**을 담아서 돌려준다.

    `_media_windows()`만 쓰면 안 되는 이유: 직접 선택(`segment["broll_override"]`
    등)을 고르는 순간 그 필드는 창에서 지워진다(`_clear_windowed_media_override`).
    그러니 창 목록만 보면 그 선택이 없는 것처럼 보인다. 렌더는 직접 선택을
    창보다 먼저 보므로(`composition_plan.py`의 `direct_override` 분기)
    실제로는 세그먼트 전체에 그 선택이 깔려 있다.

    **합칠 때 이 차이가 데이터를 지웠다**(2026-09-10 발견): 합치기는 직접
    선택을 지우고 창에 권한을 넘기는데, 접어 넣을 것이 창에 없어서 양쪽
    선택이 통째로 사라졌다. 그래서 넘기기 전에 여기서 접어 넣는다 --
    직접 선택은 세그먼트 전체에 걸리므로 모든 창에 같은 값을 쓴다.
    """
    windows = _media_windows(segment)
    for field in ("broll_override", "music_override", "sfx_override"):
        direct = segment.get(field)
        if not isinstance(direct, dict):
            continue
        for window in windows:
            window[field] = deepcopy(direct)
    return windows


def _content_windows(segment: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve per-source editorial meaning when a visible segment is merged."""
    raw = segment.get("content_windows")
    if isinstance(raw, list) and raw:
        return [deepcopy(item) for item in raw if isinstance(item, dict)]
    return [{
        "start_offset_sec": 0.0,
        "duration_sec": float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)),
        "source_segment_id": str(segment.get("segment_id") or ""),
        **{key: deepcopy(segment.get(key)) for key in ("caption_text", "caption_translations", "caption_style", "review_required", "visual_overlays", "tts_replacement")},
    }]


def _slice_content_windows(*, segment: dict[str, Any], start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    origin = float(segment.get("start_sec", 0.0))
    result: list[dict[str, Any]] = []
    for window in _content_windows(segment):
        window_start = origin + float(window.get("start_offset_sec", 0.0))
        window_end = window_start + float(window.get("duration_sec", 0.0))
        clipped_start, clipped_end = max(start_sec, window_start), min(end_sec, window_end)
        if clipped_end > clipped_start:
            result.append({**window, "start_offset_sec": clipped_start - start_sec, "duration_sec": clipped_end - clipped_start})
    return result


def _split_one_segment_in_place(*, segments: list[dict[str, Any]], segment_id: str, split_sec: float) -> None:
    """장면 하나를 두 조각으로 나눈다. **되돌리기 기록은 남기지 않는다.**

    기록을 여기서 남기지 않는 이유: 한 번에 여러 자리를 나눠야 하는 부름이
    있다(`split_segments_at` -- 숏폼이 쓸 자리만 나누기). 나누기마다 기록을
    남기면 대표님이 되돌리기를 열두 번 눌러야 숏폼 하나가 취소된다.
    """
    index = next(
        (
            position
            for position, item in enumerate(segments)
            if isinstance(item, dict) and str(item.get("segment_id")) == segment_id
        ),
        None,
    )
    if index is None:
        raise KeyError(f"Segment not found in editing session: {segment_id}")
    original = segments[index]
    start_sec, end_sec = float(original["start_sec"]), float(original["end_sec"])
    split_sec = float(split_sec)
    if not isfinite(split_sec):
        raise ValueError("segment_bounds_must_be_finite")
    if split_sec - start_sec < MIN_SEGMENT_DURATION_SEC or end_sec - split_sec < MIN_SEGMENT_DURATION_SEC:
        raise ValueError(f"Split must leave at least {MIN_SEGMENT_DURATION_SEC} seconds on both sides.")
    known_ids = {str(item.get("segment_id")) for item in segments if isinstance(item, dict)}
    suffix = 2
    split_id = f"{segment_id}__split_{suffix}"
    while split_id in known_ids:
        suffix += 1
        split_id = f"{segment_id}__split_{suffix}"
    left, right = deepcopy(original), deepcopy(original)
    left["end_sec"] = split_sec
    right["segment_id"] = split_id
    right["start_sec"] = split_sec
    source_slices = _source_slices(original)
    left["source_slices"] = _slice_source_window(slices=source_slices, leading_trim_sec=0.0, duration_sec=split_sec - start_sec)
    right["source_slices"] = _slice_source_window(slices=source_slices, leading_trim_sec=split_sec - start_sec, duration_sec=end_sec - split_sec)
    left["source_slice_basis"] = deepcopy(left["source_slices"])
    right["source_slice_basis"] = deepcopy(right["source_slices"])
    left["source_slice_basis_is_proven"] = True
    right["source_slice_basis_is_proven"] = True
    left["source_slice_window_start_sec"] = 0.0
    right["source_slice_window_start_sec"] = 0.0
    # 오른쪽 조각은 원본의 중간부터 시작한다. 직접 선택(`broll_override`)은
    # 창보다 먼저 읽히므로(`composition_plan`) 여기서 같이 감지 않으면 쪼갠
    # 장면 전부가 b-roll의 맨 앞을 다시 보여 준다.
    right["broll_override"] = _advanced_broll_source_start(
        right.get("broll_override"),
        by_sec=(split_sec - start_sec) * _segment_media_source_rate(original),
    )
    left["media_windows"] = _slice_media_windows(segment=original, start_sec=start_sec, end_sec=split_sec)
    right["media_windows"] = _slice_media_windows(segment=original, start_sec=split_sec, end_sec=end_sec)
    left["content_windows"] = _slice_content_windows(segment=original, start_sec=start_sec, end_sec=split_sec)
    right["content_windows"] = _slice_content_windows(segment=original, start_sec=split_sec, end_sec=end_sec)
    left["media_window_basis"] = deepcopy(left["media_windows"])
    right["media_window_basis"] = deepcopy(right["media_windows"])
    left["media_window_basis_offset_sec"] = 0.0
    right["media_window_basis_offset_sec"] = 0.0
    right["source_offset_sec"] = float(right["source_slices"][0]["source_offset_sec"]) if right["source_slices"] else float(original.get("source_offset_sec", 0.0))
    left["lineage"] = _lineage_for_split(original, parent_segment_id=segment_id)
    right["lineage"] = _lineage_for_split(original, parent_segment_id=segment_id)
    left["caption_needs_review"] = True
    right["caption_needs_review"] = True
    segments[index : index + 1] = [left, right]


def split_segment(*, session: dict[str, Any], segment_id: str, split_sec: float) -> dict[str, Any]:
    updated = deepcopy(session)
    _split_one_segment_in_place(segments=updated["segments"], segment_id=segment_id, split_sec=split_sec)
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_split", segment_id=segment_id)


#: 이미 경계가 있는 자리로 볼 오차. **1밀리초다.**
#:
#: 왜 이 값인가: 30fps에서 한 프레임이 33밀리초이므로 1밀리초는 절대로 보이는
#: 프레임을 옮기지 못한다. 반대쪽 끝에서, 494초쯤의 float64 반올림 오차는 약
#: 1e-13초라 일곱 자리 여유가 있다 -- 전사 시각을 원본 좌표에서 판 좌표로
#: 옮길 때 생기는 noise를 "새 경계"로 오해하지 않을 만큼 넉넉하다.
BOUNDARY_TOLERANCE_SEC = 0.001


def plan_board_splits(
    *,
    segments: list[dict[str, Any]],
    board_secs: list[float] | tuple[float, ...],
    tolerance_sec: float = BOUNDARY_TOLERANCE_SEC,
) -> tuple[tuple[str, float], ...]:
    """판 위 시각 목록을 **실제로 나눌 자리**로 바꾼다. 아무것도 안 바꾼다.

    셋을 걸러 낸다.

    1. **이미 경계인 자리는 안 나눈다**(오차 `tolerance_sec` 안). 안 걸러 내면
       `다시 만들기`를 두 번 누를 때 같은 자리를 두 번 나눠 조각이 생긴다.
    2. **최소 길이(`MIN_SEGMENT_DURATION_SEC`)를 못 남기는 자리는 안 나눈다.**
       엔진이 거절하는 자리이고, 거절을 받아 오면 나누기 전체가 실패한다.
       그때는 **가까운 기존 경계로 붙는다**(오차는 최대 0.2초).
    3. 어느 장면에도 안 걸리는 자리(판 밖)는 버린다.

    결과는 **적용 순서**다 -- 큰 시각부터다. 나누기는 왼쪽 조각에 원래 id를
    남기므로(오른쪽이 `__split_N`), 뒤에서부터 나누면 앞의 자리는 여전히 원래
    id를 가리킨다. 앞에서부터 나누면 두 번째 자리가 사라진 id를 가리킨다.
    """
    bounds = [
        (
            str(segment.get("segment_id") or ""),
            float(segment.get("start_sec", 0.0)),
            float(segment.get("end_sec", 0.0)),
        )
        for segment in segments
        if isinstance(segment, dict) and str(segment.get("segment_id") or "").strip()
    ]
    planned: list[tuple[str, float]] = []
    # 큰 시각부터. 같은 장면 안의 여러 자리를 나눌 때 앞자리가 원래 id에 남는다.
    for board_sec in sorted({float(value) for value in board_secs}, reverse=True):
        if not isfinite(board_sec):
            continue
        target = next(
            (
                item
                for item in bounds
                if item[1] < board_sec < item[2]
            ),
            None,
        )
        if target is None:
            # 이미 경계이거나 판 밖이다. 둘 다 나눌 것이 없다.
            continue
        segment_id, start_sec, end_sec = target
        if board_sec - start_sec <= tolerance_sec or end_sec - board_sec <= tolerance_sec:
            continue
        if board_sec - start_sec < MIN_SEGMENT_DURATION_SEC or end_sec - board_sec < MIN_SEGMENT_DURATION_SEC:
            # 조각을 만들지 않는다. 가까운 기존 경계로 붙는 셈이다.
            continue
        planned.append((segment_id, board_sec))
        # 나눈 뒤 원래 id는 왼쪽 조각이다. 다음(더 작은) 자리를 위해 끝을 당긴다.
        bounds[bounds.index(target)] = (segment_id, start_sec, board_sec)
    return tuple(planned)


def split_segments_at(
    *,
    session: dict[str, Any],
    splits: list[tuple[str, float]] | tuple[tuple[str, float], ...],
    label: str,
) -> dict[str, Any]:
    """여러 자리를 **한 덩이로** 나눈다. 되돌리기 한 칸, 판 버전 한 번.

    `split_segment`를 여러 번 부르는 것과 결과 장면은 같지만, 되돌리기가 다르다 --
    이 함수는 `apply_user_transaction`으로 한 덩이를 만든다. 유진 편집은 확인
    클릭 없이 적용되고 **되돌리기가 유일한 안전장치**이므로(owner 결정
    2026-09-01), 숏폼 하나를 취소하려고 Ctrl+Z를 열두 번 누르게 해서는 안 된다.
    """
    if not splits:
        raise ValueError("split_places_required")

    def mutate(draft: dict[str, Any]) -> None:
        for segment_id, split_sec in splits:
            _split_one_segment_in_place(
                segments=draft["segments"], segment_id=segment_id, split_sec=float(split_sec)
            )
        _validate_segment_bounds(segments=draft["segments"])

    return apply_user_transaction(
        session=session,
        label=label,
        affected_segment_ids=list(dict.fromkeys(segment_id for segment_id, _ in splits)),
        mutate=mutate,
        mutation_type="segments_split_batch",
    )


def merge_adjacent_segments(*, session: dict[str, Any], left_segment_id: str, right_segment_id: str) -> dict[str, Any]:
    updated = deepcopy(session)
    left_index = _segment_index(session=updated, segment_id=left_segment_id)
    right_index = _segment_index(session=updated, segment_id=right_segment_id)
    if right_index != left_index + 1:
        raise ValueError("Only adjacent segments can be merged.")
    left, right = updated["segments"][left_index], updated["segments"][right_index]
    if abs(float(left["end_sec"]) - float(right["start_sec"])) > 0.000001:
        raise ValueError("Only adjacent touching segments can be merged.")
    left_action = str(left.get("cut_action") or "keep")
    right_action = str(right.get("cut_action") or "keep")
    if left_action == "remove" or right_action == "remove" or left_action != right_action:
        raise ValueError("Only same non-remove cut actions can be merged.")
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
    left_duration = float(left["end_sec"]) - float(left["start_sec"])
    merged["media_windows"] = _effective_media_windows(left) + [
        {**window, "start_offset_sec": left_duration + float(window.get("start_offset_sec", 0.0))}
        for window in _effective_media_windows(right)
    ]
    merged["media_window_basis"] = deepcopy(merged["media_windows"])
    merged["media_window_basis_offset_sec"] = 0.0
    merged["content_windows"] = _content_windows(left) + [
        {**window, "start_offset_sec": left_duration + float(window.get("start_offset_sec", 0.0))}
        for window in _content_windows(right)
    ]
    # A merged segment no longer has one uniform override.  The materializer
    # consumes its durable windows so neither adjacent selection is stretched
    # across the other source slice.
    for field in ("broll_override", "music_override", "sfx_override"):
        merged[field] = None
    merged["visual_overlays"] = []
    merged["tts_replacement"] = None
    merged["review_required"] = _normalize_boolish(left.get("review_required")) or _normalize_boolish(right.get("review_required"))
    merged["source_slices"] = _source_slices(left) + _source_slices(right)
    merged["source_slice_basis"] = deepcopy(merged["source_slices"])
    merged["source_slice_basis_is_proven"] = True
    merged["source_slice_window_start_sec"] = 0.0
    merged["source_offset_sec"] = float(merged["source_slices"][0]["source_offset_sec"]) if merged["source_slices"] else 0.0
    merged["caption_needs_review"] = bool(left.get("caption_needs_review") or right.get("caption_needs_review"))
    updated["segments"][left_index : right_index + 1] = [merged]
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_merge", segment_id=left_segment_id)


def set_segment_bounds(*, session: dict[str, Any], segment_id: str, start_sec: float, end_sec: float) -> dict[str, Any]:
    updated = deepcopy(session)
    index = _segment_index(session=updated, segment_id=segment_id)
    previous_start = float(updated["segments"][index]["start_sec"])
    start_sec, end_sec = float(start_sec), float(end_sec)
    if not isfinite(start_sec) or not isfinite(end_sec):
        raise ValueError("segment_bounds_must_be_finite")
    prior_offset = _source_offset_before_bounds_mutation(session=session, segment=updated["segments"][index])
    segment = deepcopy(updated["segments"][index])
    # Preserve the established public error precedence: a malformed timeline
    # must report its structural violation before inspecting source authority.
    updated["segments"][index]["start_sec"] = start_sec
    updated["segments"][index]["end_sec"] = end_sec
    _validate_segment_bounds(segments=updated["segments"])
    legacy_source = _legacy_source_basis_and_window_start(session=session, segment=segment, fallback_offset=prior_offset)
    if legacy_source is None and _has_unrecoverable_legacy_bounds_transition(session=session, segment_id=str(segment.get("segment_id") or "")):
        raise ValueError("segment_source_expansion_outside_slice")
    source_basis = legacy_source[0] if legacy_source is not None else _source_slice_basis(session=session, segment=segment, fallback_offset=prior_offset)
    previous_window_start = legacy_source[1] if legacy_source is not None else float(segment.get("source_slice_window_start_sec", 0.0))
    next_window_start = previous_window_start + start_sec - previous_start
    if next_window_start < 0:
        raise ValueError("segment_source_expansion_outside_slice")
    source_basis_is_proven = legacy_source is not None or bool(segment.get("source_slice_basis_is_proven", False))
    if not source_basis_is_proven:
        source_basis = _extend_unproven_source_basis(
            slices=source_basis,
            required_duration_sec=next_window_start + end_sec - start_sec,
        )
    # Only a bounds edit changes which source moment is used.  A reorder
    # relayout deliberately leaves this value untouched.
    updated["segments"][index]["source_offset_sec"] = prior_offset + start_sec - previous_start
    slices = _slice_source_window(slices=source_basis, leading_trim_sec=next_window_start, duration_sec=end_sec - start_sec)
    if sum(float(item["duration_sec"]) for item in slices) < end_sec - start_sec - 0.000001:
        raise ValueError("segment_source_expansion_outside_slice")
    updated["segments"][index]["source_slices"] = slices
    updated["segments"][index]["source_slice_basis"] = deepcopy(source_basis)
    updated["segments"][index]["source_slice_basis_is_proven"] = source_basis_is_proven
    updated["segments"][index]["source_slice_window_start_sec"] = next_window_start
    if legacy_source is not None and "media_window_basis" not in segment and "media_windows" not in segment:
        media_basis = [{
            "start_offset_sec": 0.0,
            "duration_sec": sum(float(item["duration_sec"]) for item in source_basis),
            **{field: deepcopy(segment.get(field)) for field in ("broll_override", "music_override", "sfx_override")},
        }]
        previous_media_offset = legacy_source[1]
    else:
        media_basis = _media_window_basis(segment)
        previous_media_offset = float(segment.get("media_window_basis_offset_sec", 0.0))
    next_media_offset = previous_media_offset + start_sec - previous_start
    if next_media_offset < 0:
        raise ValueError("segment_media_expansion_outside_window")
    media_source_rate = _segment_media_source_rate(segment)
    # 앞 경계를 뒤로 끌면 b-roll 시작점도 그만큼 뒤로 간다 -- 쪼개기와 같은
    # 규칙이다. 창은 불변 기준(`media_window_basis`)에서 절대값으로 다시
    # 잘리고, 직접 선택은 지금 값에서 이번 이동분만큼만 더한다.
    updated["segments"][index]["broll_override"] = _advanced_broll_source_start(
        segment.get("broll_override"), by_sec=(start_sec - previous_start) * media_source_rate
    )
    updated["segments"][index]["media_windows"] = _slice_media_window_basis(
        windows=media_basis, leading_trim_sec=next_media_offset, duration_sec=end_sec - start_sec,
        media_source_rate=media_source_rate,
    )
    updated["segments"][index]["media_window_basis"] = deepcopy(media_basis)
    updated["segments"][index]["media_window_basis_offset_sec"] = next_media_offset
    updated["segments"][index]["content_windows"] = _slice_content_windows(segment=segment, start_sec=start_sec, end_sec=end_sec)
    return _record_undoable_mutation(before=session, updated=updated, mutation_type="segment_bounds_update", segment_id=segment_id)


def set_segment_ripple_playback_rate(*, session: dict[str, Any], segment_id: str, rate: float) -> dict[str, Any]:
    """Retime one visible scene without trimming its narrative source.

    `set_segment_bounds` deliberately changes the source window.  A shortform
    speed command has the opposite contract: it keeps that whole window,
    shortens the displayed time, and moves only later scenes by the resulting
    delta.  The materializer turns the durable rate into renderer instructions.
    """
    requested_rate = float(rate)
    if not isfinite(requested_rate) or not (MIN_RIPPLE_PLAYBACK_RATE <= requested_rate <= MAX_RIPPLE_PLAYBACK_RATE):
        raise ValueError("segment_ripple_playback_rate_invalid")

    updated = deepcopy(session)
    index = _segment_index(session=updated, segment_id=segment_id)
    segment = updated["segments"][index]
    previous_rate = float(segment.get("ripple_playback_rate", 1.0))
    source_duration = sum(
        float(source_slice["duration_sec"])
        for source_slice in _source_slices(segment)
    )
    if not _has_explicit_source_slices(segment):
        # 폴백은 원본이 아니라 **지금 보이는 길이**를 돌려준다. 거기엔 앞서 건
        # 배속이 이미 반영돼 있어서 그대로 나누면 배속이 곱해진다 -- 5초 장면을
        # 1.5배로 두고 이어서 2배로 두면 2.5초가 아니라 1.67초가 됐다
        # (2026-09-05 실기 검증). 캡컷의 `속도`는 절대값이므로, 앞 배속을
        # 되돌려 원본 길이를 복원한 다음 나눈다.
        source_duration *= previous_rate
    display_duration = source_duration / requested_rate
    if display_duration < MIN_SEGMENT_DURATION_SEC:
        raise ValueError("segment_ripple_playback_rate_below_minimum_duration")

    previous_start = float(segment["start_sec"])
    previous_duration = float(segment["end_sec"]) - previous_start
    delta = previous_duration - display_duration
    # Window offsets are displayed-time coordinates.  Keep them aligned with
    # the same source moments after a speed change; otherwise captions and
    # scene-attached media still last four seconds over a two-second scene.
    window_scale = previous_rate / requested_rate
    for field in ("media_windows", "media_window_basis", "content_windows"):
        windows = segment.get(field)
        if not isinstance(windows, list):
            continue
        for window in windows:
            if not isinstance(window, dict):
                continue
            for key in ("start_offset_sec", "duration_sec"):
                if key in window:
                    window[key] = float(window[key]) * window_scale
    if "media_window_basis_offset_sec" in segment:
        segment["media_window_basis_offset_sec"] = float(segment["media_window_basis_offset_sec"]) * window_scale
    segment["end_sec"] = previous_start + display_duration
    if requested_rate == 1.0:
        segment.pop("ripple_playback_rate", None)
    else:
        segment["ripple_playback_rate"] = requested_rate
    # A ripple edit must not reflow any earlier scene.  Subsequent scenes keep
    # their own duration (and their own rate) but move by the exact shrink/grow
    # delta, preserving deliberate later gaps if the source had them.
    for later_segment in updated["segments"][index + 1 :]:
        later_segment["start_sec"] = float(later_segment["start_sec"]) - delta
        later_segment["end_sec"] = float(later_segment["end_sec"]) - delta
    _validate_segment_bounds(segments=updated["segments"])
    return _record_undoable_mutation(
        before=session,
        updated=updated,
        mutation_type="segment_ripple_speed_update",
        segment_id=segment_id,
    )


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


def set_timeline_placement_overrides(*, session: dict[str, Any], overrides: dict[str, dict[str, object]]) -> dict[str, Any]:
    updated = deepcopy(session)
    updated["timeline_placement_overrides"] = deepcopy(overrides)
    return _record_undoable_mutation(
        before=session,
        updated=updated,
        mutation_type="timeline_placement_update",
        segment_id=",".join(sorted(overrides)),
    )


def set_track_states(*, session: dict[str, Any], states: dict[str, dict[str, bool]]) -> dict[str, Any]:
    """트랙 눈·음소거를 세션에 남긴다(`track_states.py`).

    되돌리기 대상이다 -- 결과물이 달라지는 편집이므로, 실수로 트랙을 통째로
    숨겨 놓고 왜 안 보이는지 찾아 헤매는 일이 없어야 한다.
    """
    updated = deepcopy(session)
    if states:
        updated["track_states"] = deepcopy(states)
    else:
        # 전부 기본으로 돌아왔으면 칸 자체를 지운다 -- 한 번도 안 건드린
        # 세션과 같은 모양이 되도록(`normalize_track_states`와 같은 규칙).
        updated.pop("track_states", None)
    return _record_undoable_mutation(
        before=session,
        updated=updated,
        mutation_type="track_state_update",
        segment_id=",".join(sorted(states)),
    )


def _restore_session_tracks(updated: dict[str, Any], payload: dict[str, Any]) -> None:
    """되돌리기·다시하기가 트랙 목록도 같이 되돌린다(자유 멀티트랙 Phase 5).

    **없던 상태로 돌아갈 때는 열쇠를 지운다.** 빈 목록을 남기면 "트랙을 저장한
    적 없는 세션"과 모양이 달라져서, 옛 고정 다섯 역할로 읽어 주는 길이
    막힌다.
    """
    if SESSION_TRACKS_KEY not in payload:
        return
    if payload[SESSION_TRACKS_KEY] is None:
        updated.pop(SESSION_TRACKS_KEY, None)
    else:
        updated[SESSION_TRACKS_KEY] = deepcopy(payload[SESSION_TRACKS_KEY])


def _restore_session_track_states(updated: dict[str, Any], payload: dict[str, Any]) -> None:
    """되돌리기·다시하기가 트랙 눈·음소거도 같이 되돌린다.

    `set_track_states`의 docstring이 "되돌리기 대상"이라고 명시하는데, 스냅샷에
    이 열쇠가 빠져 있어 실제로는 안 되돌아가던 결함을 고친다. `_restore_session_tracks`와
    똑같은 모양 -- **없던 상태로 돌아갈 때는 열쇠를 지운다.** 빈 값을 남기면
    "한 번도 안 건드린 세션"과 모양이 달라져서 `normalize_track_states`와
    저장 호환성이 깨진다.

    `payload`에 열쇠 자체가 없으면(손으로 만든 옛 스냅샷 dict 등) 아무 것도
    하지 않는다 -- 무조건 읽으면 그런 dict에서 `KeyError`가 난다.
    """
    if SESSION_TRACK_STATES_KEY not in payload:
        return
    if payload[SESSION_TRACK_STATES_KEY] is None:
        updated.pop(SESSION_TRACK_STATES_KEY, None)
    else:
        updated[SESSION_TRACK_STATES_KEY] = deepcopy(payload[SESSION_TRACK_STATES_KEY])


def undo(*, session: dict[str, Any]) -> dict[str, Any]:
    undo_stack = list(deepcopy(session.get("undo_stack", [])))
    if not undo_stack:
        raise ValueError("There is no editing operation to undo.")
    event = undo_stack.pop()
    updated = deepcopy(session)
    updated["segments"] = deepcopy(event["inverse_payload"]["segments"])
    inverse = event.get("inverse_payload") if isinstance(event.get("inverse_payload"), dict) else {}
    if "timeline_placement_overrides" in inverse:
        if inverse["timeline_placement_overrides"] is None:
            updated.pop("timeline_placement_overrides", None)
        else:
            updated["timeline_placement_overrides"] = deepcopy(inverse["timeline_placement_overrides"])
    if "caption_style" in inverse:
        if inverse["caption_style"] is None:
            updated.pop("caption_style", None)
        else:
            updated["caption_style"] = deepcopy(inverse["caption_style"])
    _restore_session_tracks(updated, inverse)
    _restore_session_track_states(updated, inverse)
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
    forward = event.get("forward_payload") if isinstance(event.get("forward_payload"), dict) else {}
    if "timeline_placement_overrides" in forward:
        if forward["timeline_placement_overrides"] is None:
            updated.pop("timeline_placement_overrides", None)
        else:
            updated["timeline_placement_overrides"] = deepcopy(forward["timeline_placement_overrides"])
    if "caption_style" in forward:
        if forward["caption_style"] is None:
            updated.pop("caption_style", None)
        else:
            updated["caption_style"] = deepcopy(forward["caption_style"])
    _restore_session_tracks(updated, forward)
    _restore_session_track_states(updated, forward)
    updated["redo_stack"] = redo_stack
    updated["undo_stack"] = (list(deepcopy(session.get("undo_stack", []))) + [event])[-MAX_TIMELINE_UNDO_EVENTS:]
    history = list(deepcopy(session.get("history", [])))
    history.append({"mutation_type": "redo", "segment_id": str(event.get("segment_id") or "")})
    updated["history"] = history[-MAX_TIMELINE_AUDIT_EVENTS:]
    now = datetime.now(UTC).isoformat()
    revision = int(session.get("session_revision") or 1) + 1
    updated["output_freshness"] = {kind: {"source_session_revision": revision, "is_current": False, "invalidated_at": now, "invalidated_reason": "redo"} for kind in ("review", "subtitle", "preview", "final", "capcut")}
    return updated


def _merge_broll_media_controls(*, session: dict[str, Any], segment_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """그 장면 B-roll의 조정값 몇 개만 바꾼다. 나머지는 그대로 둔다.

    `update_segment_broll_override`는 덮어쓰기라 지금 값을 통째로 다시 실어야
    한다 -- 원본 신원(해시·판)을 안 실으면 출력 검증이 그 장면을 "바뀐 원본"으로
    읽는다. 색감·손떨림·변형이 전부 같은 함정을 지나므로 한 자리에 모은다.
    """
    existing = next(
        (
            segment.get("broll_override")
            for segment in session.get("segments", [])
            if isinstance(segment, dict) and str(segment.get("segment_id")) == segment_id
        ),
        None,
    )
    if not isinstance(existing, dict) or not str(existing.get("asset_id") or "").strip():
        raise ValueError("scene_look_needs_broll")
    controls = dict(existing.get("media_controls") or {})
    controls.update(changes)
    for field in ("expected_content_sha256", "media_revision"):
        if existing.get(field):
            controls[field] = existing[field]
    return update_segment_broll_override(
        session=session, segment_id=segment_id, asset_id=str(existing["asset_id"]), media_controls=controls
    )


def _merge_audio_media_controls(*, session: dict[str, Any], segment_id: str, field: str, changes: dict[str, Any]) -> dict[str, Any]:
    """그 장면 음악·효과음의 소리 정리 값만 바꾼다. 위와 같은 이유로 통째로 다시 싣는다."""
    existing = next(
        (
            segment.get(field)
            for segment in session.get("segments", [])
            if isinstance(segment, dict) and str(segment.get("segment_id")) == segment_id
        ),
        None,
    )
    if not isinstance(existing, dict) or not str(existing.get("asset_id") or "").strip():
        raise ValueError("sound_cleanup_needs_media")
    controls = dict(existing.get("media_controls") or {})
    controls.update(changes)
    for key in ("expected_content_sha256", "media_revision"):
        if existing.get(key):
            controls[key] = existing[key]
    updater = update_segment_music_override if field == "music_override" else update_segment_sfx_override
    return updater(
        session=session, segment_id=segment_id, asset_id=str(existing["asset_id"]), media_controls=controls
    )


def _apply_yujin_editing_operations(*, session: dict[str, Any], operations: tuple[object, ...]) -> dict[str, Any]:
    """Return a session copy with validated AI editing operations applied."""
    from videobox_domain_models.yujin_editing_proposals import (
        ApplyMediaOperation,
        RemoveImageOverlayOperation,
        RemoveMediaOperation,
        ReorderSegmentsOperation,
        SetCaptionFontOperation,
        SetImageOverlayOperation,
        SetSceneTransitionOperation,
        SetCaptionTextOperation,
        SetCutActionOperation,
        SetPhotoMotionOperation,
        SetPictureCleanupOperation,
        SetSceneLookOperation,
        SetSceneTransformOperation,
        SetSoundCleanupOperation,
        SetSegmentBoundsOperation,
        SetSceneSpeedOperation,
    )

    working = deepcopy(session)
    for operation in operations:
        if isinstance(operation, SetSceneSpeedOperation):
            working = set_segment_ripple_playback_rate(
                session=working, segment_id=operation.segment_id, rate=float(operation.rate)
            )
        elif isinstance(operation, SetSegmentBoundsOperation):
            working = set_segment_bounds(
                session=working,
                segment_id=operation.segment_id,
                start_sec=operation.start_sec,
                end_sec=operation.end_sec,
            )
        elif isinstance(operation, SetCutActionOperation):
            working = update_segment_cut_action(
                session=working,
                segment_id=operation.segment_id,
                cut_action={"exclude": "remove", "restore": "keep"}[operation.action],
            )
        elif isinstance(operation, SetCaptionTextOperation):
            # **창작자가 보고 있던 언어를 고친다.** 유진에게도 그 언어로 보여
            # 줬으므로 고치는 자리도 같아야 한다 -- 영어를 보며 "짧게 줄여 줘"라고
            # 했는데 한국어가 고쳐지면 창작자 눈에는 아무 일도 안 일어난다.
            working = update_segment_caption(
                session=working, segment_id=operation.segment_id, caption_text=operation.text,
                language=str(working.get("caption_language") or "") or None,
            )
        elif isinstance(operation, SetCaptionFontOperation):
            # **편집본 전체**에 건다. 글꼴만 바꾸고 크기·색은 그대로 둬야 하므로
            # 지금 스타일 위에 얹는다 -- 통째로 갈아 끼우면 창작자가 맞춰 둔
            # 나머지가 조용히 기본값으로 돌아간다.
            current = working.get("caption_style")
            style = dict(current) if isinstance(current, dict) else {}
            # 말한 칸만 얹는다. "글꼴 더 큰 걸로"라고만 했는데 글꼴 이름까지
            # 채우면 창작자가 맞춰 둔 글꼴이 조용히 바뀐다 -- 크기를 더하면서
            # 생긴 자리다(2026-09-06).
            if operation.family is not None:
                style["font_family"] = operation.family
            if operation.size_px is not None:
                style["font_size_px"] = operation.size_px
            working = update_caption_style(
                session=working, style=style, scope="whole_project", segment_ids=[],
            )
        elif isinstance(operation, SetSceneTransitionOperation):
            # 화면이 쓰는 것과 **같은 함수**다. 전환 값은 들어오는 쪽 장면에
            # 실린다(그 함수의 머리말 참고) -- 두 벌로 적으면 한쪽만 고쳐진다.
            working = update_segment_transition(
                session=working, segment_id=operation.segment_id,
                transition=(
                    None if operation.transition_type is None
                    else {"type": operation.transition_type, "chosen_by": "yujin",
                          **({"duration_sec": operation.duration_sec} if operation.duration_sec else {})}
                ),
            )
        elif isinstance(operation, SetSceneLookOperation):
            # 손떨림·노이즈·변형과 **같은 자리**에 얹는다(전부 그 장면 B-roll의
            # 조정값이다). 병합과 원본 신원 보존은 한 함수가 맡는다 -- 두 벌이면
            # 한쪽만 고쳐진다.
            working = _merge_broll_media_controls(
                session=working, segment_id=operation.segment_id,
                changes={"filter": {"type": operation.look, "chosen_by": "yujin"}},
            )
        elif isinstance(operation, SetPhotoMotionOperation):
            # 색감과 **같은 자리**다(그 장면 B-roll의 조정값). 색감처럼 `chosen_by`를
            # 달지 않는 이유는 렌더러가 읽는 모양이 문자열 하나이기 때문이다 --
            # 여기서 dict로 실으면 `normalize_media_controls`가 거절한다.
            working = _merge_broll_media_controls(
                session=working, segment_id=operation.segment_id,
                changes={"photo_motion": operation.motion},
            )
        elif isinstance(operation, (SetPictureCleanupOperation, SetSceneTransformOperation)):
            # 색감과 같은 자리에 얹는다 -- 전부 그 장면 B-roll의 조정값이다.
            changes = {
                field: value
                for field, value in operation.model_dump(exclude={"intent", "segment_id"}).items()
                if value is not None
            }
            working = _merge_broll_media_controls(session=working, segment_id=operation.segment_id, changes=changes)
        elif isinstance(operation, SetSoundCleanupOperation):
            field = "music_override" if operation.media_type == "bgm" else "sfx_override"
            changes = {
                key: value
                for key, value in operation.model_dump(exclude={"intent", "segment_id", "media_type"}).items()
                if value is not None
            }
            working = _merge_audio_media_controls(
                session=working, segment_id=operation.segment_id, field=field, changes=changes
            )
        elif isinstance(operation, SetImageOverlayOperation):
            # `update_segment_image_overlay`는 Task 1 뒤로 세 상태(유지·지움·
            # 바꿈)를 받는다: 인자를 아예 안 주면 유지(`_KEEP` 기본값), `None`을
            # 주면 지움, 값을 주면 바꿈이다. 그런데 유진의 명령 스키마
            # (`SetImageOverlayOperation`)에는 그 셋을 가를 길이 없다 -- 넷 다
            # `str | None`이라 "말 안 함"도 `None`으로 온다(`preset_overrides()`가
            # 쓰는 `model_fields_set`을 유진의 JSON 응답에는 못 쓴다). 그래서
            # `operation.vertical` 같은 값을 그대로 아래로 흘리면(예전 코드),
            # 유진이 크기만 말하고 자리는 말 안 한 순간 그 `None`이 이제
            # "지워라"로 읽혀서 앞서 정한 자리가 조용히 사라진다 -- 대표님이
            # 실제로 겪은 결함, Task 1 뒤로는 오히려 더 나빠졌다.
            #
            # 그래서 여기서 유진의 `None`을 전부 "말 안 함"으로 읽고, 값이 있는
            # 칸만 골라 kwargs로 만들어 `**`로 펼친다 -- 이러면 안 말한 칸은
            # 키워드 인자 자체가 안 넘어가서 `_KEEP` 기본값이 적용된다. 화면
            # 쪽(`editing_session_and_regeneration.py`의 `preset_overrides` 처리)과
            # 같은 모양이다.
            #
            # 유진에게 "이 칸만 콕 집어 안 고름으로 지워라"라고 말할 길은
            # 일부러 안 만들었다(YAGNI 판단, 보고서 참고) -- 창작자가 실제로
            # 하는 말("가운데로 되돌려줘")은 값을 대는 말이지 "지워라"가
            # 아니고, 통째로 되돌리고 싶으면 이미 있는 remove_image_overlay로
            # 뺐다가 다시 얹으면 된다.
            preset_overrides = {
                field_name: value
                for field_name, value in (
                    ("vertical", operation.vertical),
                    ("horizontal", operation.horizontal),
                    ("size", operation.size),
                    ("motion", operation.motion),
                )
                if value is not None
            }
            # `preserve_source_audio`는 **먼저 옛 값을 읽어서 채운다**
            # (Task 4, 2026-09-11, 다른 계획) -- 넷과 다른 이유다. `update_segment_image_overlay`는
            # 오버레이 전체를 다시 쓰므로, 유진이 소리를 말하지 않고 자리만
            # 옮기면 `None`을 그대로 내려보내는 순간 이미 켜 둔 소리가
            # 빈 열쇠로 사라진다. `preserve_source_audio`는 `False`가 진짜
            # 값이라 지울 상태가 없어서(이번 세 상태 계약 밖) 이 방식을
            # 그대로 둔다 -- 건드리지 않는다.
            resolved_preserve_source_audio = (
                operation.preserve_source_audio
                if operation.preserve_source_audio is not None
                else _current_image_overlay_preserve_source_audio(
                    session=working, segment_id=operation.segment_id
                )
            )
            working = update_segment_image_overlay(
                session=working,
                segment_id=operation.segment_id,
                asset_id=operation.asset_id,
                # 사진 오버레이의 `text`는 화면에서도 비워 두고 부르는 자리가
                # 있다(`ImageOverlayRequest.text`의 기본값이 빈 글이다).
                text="",
                preserve_source_audio=resolved_preserve_source_audio,
                **preset_overrides,
            )
        elif isinstance(operation, RemoveImageOverlayOperation):
            working = remove_segment_image_overlay(session=working, segment_id=operation.segment_id)
        elif isinstance(operation, ApplyMediaOperation):
            if operation.media_type == "broll":
                working = update_segment_broll_override(
                    session=working, segment_id=operation.segment_id, asset_id=operation.asset_id
                )
            elif operation.media_type == "bgm":
                working = update_segment_music_override(
                    session=working, segment_id=operation.segment_id, asset_id=operation.asset_id
                )
            else:
                working = update_segment_sfx_override(
                    session=working, segment_id=operation.segment_id, asset_id=operation.asset_id
                )
        elif isinstance(operation, RemoveMediaOperation):
            if operation.media_type == "broll":
                working = clear_segment_broll_override(session=working, segment_id=operation.segment_id)
            elif operation.media_type == "bgm":
                working = clear_segment_music_override(session=working, segment_id=operation.segment_id)
            else:
                working = clear_segment_sfx_override(session=working, segment_id=operation.segment_id)
        elif isinstance(operation, ReorderSegmentsOperation):
            by_id = {
                str(segment["segment_id"]): segment
                for segment in working.get("segments", [])
                if isinstance(segment, dict)
            }
            cursor = min(float(segment.get("start_sec", 0.0)) for segment in by_id.values())
            bounds_by_id: dict[str, dict[str, float]] = {}
            for segment_id in operation.segment_ids:
                segment = by_id[segment_id]
                duration = float(segment["end_sec"]) - float(segment["start_sec"])
                bounds_by_id[segment_id] = {"start_sec": cursor, "end_sec": cursor + duration}
                cursor += duration
            working = reorder_segments(
                session=working, segment_ids=list(operation.segment_ids), bounds_by_id=bounds_by_id
            )
        else:
            raise ValueError("editing_proposal_operation_not_supported")
    return working


def project_yujin_editing_proposal(*, session: dict[str, Any], proposal: object) -> dict[str, Any]:
    """Project a validated AI proposal without changing session metadata or undo state."""
    operations = tuple(getattr(proposal, "operations", ()))
    if not operations:
        raise ValueError("editing_proposal_operations_required")
    projected = _apply_yujin_editing_operations(session=session, operations=operations)
    for field in ("session_revision", "output_freshness", "history", "undo_stack", "redo_stack"):
        if field in session:
            projected[field] = deepcopy(session[field])
        else:
            projected.pop(field, None)
    return projected


def apply_yujin_editing_proposal(*, session: dict[str, Any], proposal: object) -> dict[str, Any]:
    """Apply validated AI operations as exactly one existing user transaction."""
    operations = tuple(getattr(proposal, "operations", ()))
    if not operations:
        raise ValueError("editing_proposal_operations_required")
    affected = [str(item.segment_id) for item in operations if hasattr(item, "segment_id")]
    from videobox_domain_models.yujin_editing_proposals import ReorderSegmentsOperation

    for operation in operations:
        if isinstance(operation, ReorderSegmentsOperation):
            affected.extend(operation.segment_ids)
    affected = list(dict.fromkeys(affected))

    def mutate(draft: dict[str, Any]) -> None:
        projected = _apply_yujin_editing_operations(session=draft, operations=operations)
        draft["segments"] = projected["segments"]

    return apply_user_transaction(
        session=session, label="유진 편집안 적용", affected_segment_ids=affected, mutate=mutate,
        mutation_type="yujin_editing_proposal",
    )


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


def _write_caption(target: dict[str, Any], text: str, language: str | None) -> None:
    """원본 자리에 쓸지, 그 언어 번역 자리에 쓸지 한 곳에서 정한다."""
    if language is None:
        target["caption_text"] = text
        return
    translations = target.get("caption_translations")
    target["caption_translations"] = {
        **(translations if isinstance(translations, Mapping) else {}),
        language: text,
    }


def captions_from_transcript(
    *,
    session: dict[str, Any],
    transcript_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """받아쓴 말을 장면 캡션으로 옮긴다 — 캡컷 `자동 캡션` 자리.

    부품은 처음부터 다 있었다. 받아쓰기는 시간 구간별 텍스트를 주고, 장면도
    시간 구간을 갖는다. **그 둘을 잇는 코드만 없었다** -- 받아쓰기 결과는
    제작 파이프라인의 다음 단계로만 흘렀다.

    규칙 하나: **말이 가장 많이 걸친 장면에 그 말을 준다.** 걸친 말을 양쪽에
    다 넣으면 같은 문장이 두 번 보이고, 어느 쪽도 지우지 않으면 창작자는
    지운 말이 왜 남아 있는지 모른다.

    **말이 없는 장면은 건드리지 않는다.** 창작자가 손으로 써 둔 캡션을 빈
    문자열로 덮으면, 받아쓰기 한 번에 공들여 쓴 말이 사라진다.
    """
    lines = [
        {
            "start_sec": float(item.get("start_sec", 0.0)),
            "end_sec": float(item.get("end_sec", 0.0)),
            "text": str(item.get("text") or "").strip(),
        }
        for item in transcript_segments
        if str(item.get("text") or "").strip()
    ]
    if not lines:
        raise ValueError("transcript_has_no_speech")

    updated = deepcopy(session)
    segments = [segment for segment in updated.get("segments", []) if isinstance(segment, dict)]
    # 말한 순서대로 이어 붙인다 -- 받아쓰기가 순서대로 오지 않을 수 있다.
    lines.sort(key=lambda line: (line["start_sec"], line["end_sec"]))

    collected: dict[str, list[str]] = {}
    for line in lines:
        best_id, best_overlap = None, 0.0
        for segment in segments:
            start = float(segment.get("start_sec", 0.0))
            end = float(segment.get("end_sec", 0.0))
            overlap = min(line["end_sec"], end) - max(line["start_sec"], start)
            if overlap > best_overlap:
                best_id, best_overlap = str(segment.get("segment_id") or ""), overlap
        if best_id:
            collected.setdefault(best_id, []).append(line["text"])

    if not collected:
        raise ValueError("transcript_has_no_speech")

    for segment in segments:
        spoken = collected.get(str(segment.get("segment_id") or ""))
        if spoken:
            segment["caption_text"] = " ".join(spoken)

    return _apply_manual_mutation(
        before=session,
        updated=updated,
        mutation_type="captions_from_transcript",
        segment_id=",".join(sorted(collected)),
    )


def update_segment_caption(
    *,
    session: dict[str, Any],
    segment_id: str,
    caption_text: str,
    language: str | None = None,
) -> dict[str, Any]:
    """자막을 고친다. `language`를 주면 **그 언어 번역을 고치고 원본은 안 건드린다.**

    언어를 받는 이유: 창작자가 영어 자막을 보면서 고치면 화면에 보이는 것과
    저장되는 곳이 같아야 한다. 안 그러면 **한국어 원본이 영어로 덮여 사라지고**,
    정작 완성본에 나가는 영어는 그대로다 -- 2026-09-03에 실제로 그랬다.

    유진이 고치는 길은 언어를 안 준다. 유진은 한국어 원문을 보고 말하므로
    원본을 고치는 것이 맞다.
    """
    if language is not None and language not in SUPPORTED_CAPTION_LANGUAGES:
        raise ValueError(f"Unsupported caption language: {language}")
    updated = deepcopy(session)
    normalized_caption = caption_text.strip()
    matched = False
    for segment in updated.get("segments", []):
        if not isinstance(segment, dict):
            continue
        containing_segment_id = str(segment.get("segment_id") or "")
        if containing_segment_id == segment_id:
            _write_caption(segment, normalized_caption, language)
            matched = True
        content_windows = segment.get("content_windows")
        if not isinstance(content_windows, list):
            continue
        for window in content_windows:
            if not isinstance(window, dict):
                continue
            source_segment_id = str(window.get("source_segment_id") or containing_segment_id)
            if source_segment_id != segment_id:
                continue
            _write_caption(window, normalized_caption, language)
            matched = True
    if matched:
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="caption_update", segment_id=segment_id, extra={"caption_text": normalized_caption, **({"language": language} if language else {})})
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


def update_segment_transition(
    *,
    session: dict[str, Any],
    segment_id: str,
    transition: dict[str, Any] | None,
) -> dict[str, Any]:
    """이 장면으로 **넘어올 때** 쓸 전환을 정한다.

    값을 들어오는 쪽 장면에 싣는 이유는 경계가 그 장면의 시작 시각 하나로
    정해지기 때문이다. 앞 장면에 실으면 장면을 지우거나 순서를 바꿀 때
    전환이 어느 경계 것이었는지 알 수 없게 된다.

    첫 장면에도 저장은 된다. 앞에 붙은 장면이 없으면 렌더러가 조용히 넘긴다
    (`build_plan_filter_graph`) -- 저장을 거절하면 순서를 바꿔 두 번째로
    내려온 순간 owner가 다시 골라야 한다.
    """
    normalized = normalize_transition(transition)
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        if normalized is None:
            segment.pop("transition_in", None)
        else:
            segment["transition_in"] = normalized
        return _apply_manual_mutation(
            before=session, updated=updated, mutation_type="transition_update",
            segment_id=segment_id,
            extra={"transition": normalized["type"] if normalized else "none"},
        )
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def _broll_controls_with_default_source_audio(
    *, session: dict[str, Any], media_controls: dict[str, Any] | None
) -> dict[str, Any] | None:
    """빈 편집판에 깐 영상은 **자기 소리를 그대로 들려준다.**

    b-roll의 `preserve_source_audio` 기본값은 꺼짐이다. 그 기본값은 "대본 →
    내레이션"으로 만든 편집본을 전제한다 -- 목소리는 내레이션 트랙에 있고,
    b-roll은 그 위에 까는 장식이라 자기 소리가 같이 나면 말이 겹친다.

    **빈 편집판(`timing_source == "blank"`)에는 그 내레이션이 없다.** 대표님이
    `+ 새로 만들기`로 열고 찍어 온 영상을 장면에 까는 길이 그것이고, 그 영상의
    소리가 곧 말소리다. 2026-09-12 실측: 8분 영상으로 만든 숏폼이
    `mean_volume -91.0 dB`, 완전한 무음으로 나왔다. 사람이 말하는 영상인데
    목소리가 없었다.

    **고른 값은 덮지 않는다.** 칸이 이미 있으면(`normalize_media_controls`를
    한 번이라도 지난 값은 항상 있다) 그대로 둔다 -- 나중에 소리를 끄면 그
    선택이 다시 켜지지 않는다.
    """
    if str(session.get("timing_source") or "").strip() != "blank":
        return media_controls
    if isinstance(media_controls, dict) and "preserve_source_audio" in media_controls:
        return media_controls
    return {**(media_controls or {}), "preserve_source_audio": True}


def update_segment_broll_override(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
    media_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    media_controls = _broll_controls_with_default_source_audio(session=session, media_controls=media_controls)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        _clear_windowed_media_override(segment=segment, field="broll_override")
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
        _clear_windowed_media_override(segment=segment, field="broll_override")
        segment["broll_override"] = None
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="broll_override_clear", segment_id=segment_id)
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def update_segment_sfx_override(*, session: dict[str, Any], segment_id: str, asset_id: str, asset_uri: str | None = None, media_controls: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = deepcopy(session)
    normalized_asset_id = asset_id.strip()
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        existing = segment.get("sfx_override")
        same_asset = isinstance(existing, dict) and str(existing.get("asset_id") or "").strip() == normalized_asset_id
        next_override = deepcopy(existing) if same_asset else {}
        _clear_windowed_media_override(segment=segment, field="sfx_override")
        next_override["asset_id"] = normalized_asset_id
        # A review decision must bind to this exact user action, not merely to
        # a segment or asset that the user may intentionally select again.
        next_override["source_action_id"] = f"action:sfx_override:{uuid.uuid4().hex}"
        if asset_uri:
            next_override["asset_uri"] = asset_uri
        if media_controls is not None:
            previous_controls = existing.get("media_controls") if same_asset and isinstance(existing.get("media_controls"), dict) else {}
            next_override["media_controls"] = normalize_media_controls(
                {**previous_controls, **media_controls},
                media_kind="audio",
                duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)),
            )
        segment["sfx_override"] = next_override
        return _apply_manual_mutation(before=session, updated=updated, mutation_type="sfx_override_update", segment_id=segment_id, extra={"asset_id": normalized_asset_id})
    raise KeyError(f"Segment not found in editing session: {segment_id}")


def clear_segment_sfx_override(*, session: dict[str, Any], segment_id: str) -> dict[str, Any]:
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if str(segment.get("segment_id")) != segment_id:
            continue
        _clear_windowed_media_override(segment=segment, field="sfx_override")
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
    has_direct_match = any(
        isinstance(segment, dict) and str(segment.get("segment_id") or "") == segment_id
        for segment in updated.get("segments", [])
    )
    matched = False
    for segment in updated.get("segments", []):
        if not isinstance(segment, dict):
            continue
        containing_segment_id = str(segment.get("segment_id") or "")
        direct_match = containing_segment_id == segment_id
        if direct_match:
            segment["visual_overlays"] = []
            matched = True
        content_windows = segment.get("content_windows")
        if not isinstance(content_windows, list):
            continue
        for window in content_windows:
            if not isinstance(window, dict):
                continue
            source_segment_id = str(window.get("source_segment_id") or containing_segment_id)
            if (has_direct_match and not direct_match) or (not has_direct_match and source_segment_id != segment_id):
                continue
            window["visual_overlays"] = []
            matched = True
    if not matched:
        raise KeyError(f"Segment not found in editing session: {segment_id}")
    return _apply_manual_mutation(before=session, updated=updated, mutation_type="visual_overlay_clear", segment_id=segment_id)


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


# 사진 오버레이도 도형과 **같은 프리셋 어휘**를 쓴다(owner 요청 2026-09-06,
# "사진을 우리 영상 위에도 얹어서 움직이게").
#
# 목록을 새로 만들지 않고 `overlay_shapes`의 것을 그대로 본뜬다 -- 사본을 두면
# 화면·API·렌더가 서로 다른 목록을 보게 되고, 도형에서 이미 그 값을 치렀다.
# 승인 범위도 도형과 같다(2026-08-20 승인 5항): 오버레이 하나가 등장·퇴장·이동
# 하는 정도까지이고 자유 좌표·초 단위·키프레임은 밖이다.
_IMAGE_OVERLAY_PRESET_VALUES: dict[str, frozenset[str]] = {
    "vertical": SHAPE_OVERLAY_VERTICALS,
    "horizontal": SHAPE_OVERLAY_HORIZONTALS,
    "size": SHAPE_OVERLAY_SIZES,
    "motion": SHAPE_OVERLAY_MOTION_SET,
}


class _KeepSentinel:
    """`update_segment_image_overlay`의 프리셋 인자 기본값 전용 파수꾼.

    화면에는 `안 고름`(값을 `None`으로 지워서 보냄)이라는 실제 상태가 있어서
    "인자를 아예 안 줌"과 "`None`을 줌"을 같은 것으로 접으면 안 된다. 그런데
    `None`은 이미 파이썬 기본값으로 흔히 쓰이므로, "안 줌"을 나타내려면
    `None`이 아닌 별도 기본값이 필요하다. 이 클래스의 유일한 인스턴스(`_KEEP`)가
    그 자리를 채운다 -- 부르는 쪽이 실수로 만들어 낼 수 없도록 모듈 밖에 노출하지
    않는다.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - 디버그 출력용
        return "_KEEP"


_KEEP = _KeepSentinel()


def update_segment_image_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    asset_id: str,
    text: str,
    vertical: str | None | _KeepSentinel = _KEEP,
    horizontal: str | None | _KeepSentinel = _KEEP,
    size: str | None | _KeepSentinel = _KEEP,
    motion: str | None | _KeepSentinel = _KEEP,
    preserve_source_audio: bool | None = None,
) -> dict[str, Any]:
    """사진 오버레이를 얹는다. 프리셋 넷은 각각 **세 상태**를 받는다.

    | 부르는 쪽이 하는 것 | 뜻 |
    |---|---|
    | 인자를 아예 안 줌(기본값 `_KEEP`) | 지금 저장된 값을 그대로 둔다 |
    | `None`을 줌 | 지워서 "안 고름"으로 되돌린다 |
    | 값을 줌 | 그 값으로 바꾼다 |

    왜 두 상태(안 줌 vs `None`)로 갈랐는가: 화면에는 `안 고름`(`InspectorControls.tsx`의
    `IMAGE_PRESET_UNSET`)이라는 실제 상태가 있고, 창작자가 그걸 고르면 화면은
    그 칸을 빼서 보낸다 -- 이게 지금 "칸 없음"의 뜻이다. 그런데 유진은 프리셋을
    "말 안 한" 채로 다른 것만 바꿔 달라고 하는 경우가 많고, 그때 "칸 없음"이
    지금처럼 지움 취급되면 앞서 정한 자리가 조용히 사라진다(owner가 실제로
    겪은 결함). 같은 신호("칸 없음")가 두 화자에게 반대 뜻이라 하나로 못
    접는다 -- 그래서 "아예 안 줌"(`_KEEP`, 기본값)과 "`None`을 줌"을 갈랐다.

    "지금 값을 그대로 둔다"는 이 함수가 저장된 값을 읽어서 새 payload에
    다시 심는다는 뜻이다. `_upsert_segment_overlay`가 옛 오버레이를 통째로
    버리고 새 payload만 남기기 때문에(`_upsert_overlay_list`), 여기서 옮겨
    심지 않으면 "그대로 둔다"고 해 놓고 실제로는 지워진다. 저장된 값이 아예
    없으면(프리셋을 한 번도 고른 적 없는 오버레이) 옮길 것도 없다 -- 없는
    열쇠를 기본값으로 채우면 이 기능이 생기기 전 오버레이의 자국이 바뀐다.

    `None`을 준 경우는 반대로 **거절 없이** 칸을 뺀다 -- 화면의 `안 고름`이
    이 길로 온다. 값을 준 경우는 그대로 **거절**한다: 오타를 조용히 기본값으로
    좁히면 owner는 고른 것이 왜 안 되는지 알 수 없다.

    `preserve_source_audio`는 이 세 상태를 쓰지 않는다 -- `False`가 진짜 값이라
    지울 상태가 없다(건드리지 않음, 2026-09-11). **얹은 영상**(이 오버레이
    자리는 사진도, 영상도 될 수 있다)의 원본 소리를 완성본에 실을지이며, 이름은
    b-roll의 같은 칸을 그대로 빌린다(`media_controls.py`). 안 주면(`None`,
    파이썬 기본값 그대로) 열쇠 자체가 없고(무음이던 예전과 자국이 같다), 렌더러가
    없는 열쇠를 `False`로 읽는다.
    """
    presets: dict[str, str | None | _KeepSentinel] = {
        "vertical": vertical,
        "horizontal": horizontal,
        "size": size,
        "motion": motion,
    }
    normalized_presets: dict[str, str] = {}
    for field_name, raw_value in presets.items():
        if raw_value is _KEEP:
            # 인자를 아예 안 줬다 -- 지금 저장된 값을 그대로 옮긴다. 순회는
            # `preserve_source_audio`가 쓰는 것과 같은 규칙
            # (`_iter_matching_overlay_containers`)을 재사용한다.
            current_value = _current_image_overlay_preset_value(
                session=session, segment_id=segment_id, field_name=field_name,
            )
            if current_value is not None:
                normalized_presets[field_name] = current_value
            continue
        if raw_value is None:
            # 명시적으로 `None` -- 화면의 `안 고름`이 이 길로 온다. 칸을 뺀다.
            continue
        normalized = str(raw_value).strip().lower()
        allowed = _IMAGE_OVERLAY_PRESET_VALUES[field_name]
        if normalized not in allowed:
            raise ValueError(
                f"image overlay {field_name} must be one of {sorted(allowed)}: {normalized!r}"
            )
        normalized_presets[field_name] = normalized
    audio_fields: dict[str, bool] = {}
    if preserve_source_audio is not None:
        audio_fields["preserve_source_audio"] = bool(preserve_source_audio)
    return _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="image_overlay",
        overlay_payload={
            "overlay_type": "image_overlay",
            "asset_id": asset_id.strip(),
            "text": text.strip(),
            **normalized_presets,
            **audio_fields,
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
        overlay_type="image_overlay",
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
        overlay_type="table_overlay",
        overlay_payload={
            "overlay_type": "table_overlay",
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
        overlay_type="table_overlay",
        mutation_type="table_overlay_remove",
    )


# 정지 도형·아이콘("여기를 보세요")의 프리셋. 자유 좌표는 계획서 §4가 범위 밖으로
# 못박았고 지금도 그렇다. 목록은 `overlay_shapes`가 유일한 출처다 -- 여기에 사본을
# 두었더니 화면·API·렌더가 서로 다른 목록을 보게 됐다.
#
# 2026-08-20: **등장·퇴장·이동만** 승인 범위 안으로 들어왔다(승인 기록 5항).
# 프리셋 몇 가지이고, 타임라인에 점을 찍는 편집기가 아니다.


def update_segment_shape_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    shape: str,
    vertical: str,
    horizontal: str,
    size: str,
    motion: str = "none",
) -> dict[str, Any]:
    normalized = {
        "shape": shape.strip().lower(),
        "vertical": vertical.strip().lower(),
        "horizontal": horizontal.strip().lower(),
        "size": size.strip().lower(),
        # 안 보내면 `그대로`다. 이 기능이 생기기 전 화면이 보내던 요청도 그대로 통한다.
        "motion": (motion or "none").strip().lower(),
    }
    allowed = {
        "shape": SHAPE_OVERLAY_SHAPES,
        "vertical": SHAPE_OVERLAY_VERTICALS,
        "horizontal": SHAPE_OVERLAY_HORIZONTALS,
        "size": SHAPE_OVERLAY_SIZES,
        # 오타를 조용히 `그대로`로 좁히지 않는다 -- 고른 것이 왜 안 되는지
        # owner가 알 수 없게 된다. 읽는 쪽(`canonical_shape_overlay_motion`)만
        # 관대하다.
        "motion": SHAPE_OVERLAY_MOTION_SET,
    }
    for field_name, values in allowed.items():
        if normalized[field_name] not in values:
            raise ValueError(
                f"shape overlay {field_name} must be one of {sorted(values)}: {normalized[field_name]!r}"
            )
    return _upsert_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="shape_overlay",
        overlay_payload={"overlay_type": "shape_overlay", **normalized},
        mutation_type="shape_overlay_update",
    )


def remove_segment_shape_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
) -> dict[str, Any]:
    return _remove_segment_overlay(
        session=session,
        segment_id=segment_id,
        overlay_type="shape_overlay",
        mutation_type="shape_overlay_remove",
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
        existing = segment.get("music_override")
        same_asset = isinstance(existing, dict) and str(existing.get("asset_id") or "").strip() == normalized_asset_id
        next_override = deepcopy(existing) if same_asset else {}
        _clear_windowed_media_override(segment=segment, field="music_override")
        next_override["asset_id"] = normalized_asset_id
        if asset_uri:
            next_override["asset_uri"] = asset_uri
        if media_controls is not None:
            previous_controls = existing.get("media_controls") if same_asset and isinstance(existing.get("media_controls"), dict) else {}
            next_override["media_controls"] = normalize_media_controls(
                {**previous_controls, **media_controls},
                media_kind="audio",
                duration_sec=float(segment.get("end_sec", 0.0)) - float(segment.get("start_sec", 0.0)),
            )
        segment["music_override"] = next_override
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
        _clear_windowed_media_override(segment=segment, field="music_override")
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


def _iter_matching_overlay_containers(
    session: dict[str, Any], segment_id: str,
) -> list[dict[str, Any]]:
    """`segment_id`에 해당하는 오버레이 컨테이너(직속 세그먼트, 또는 그 밑
    `content_windows` 안의 창)를 전부 모아서 낸다.

    이 찾기 규칙 하나(직속 세그먼트가 있으면 직속 세그먼트 자신 + 그 세그먼트의
    모든 창, 없으면 `source_segment_id`가 일치하는 창만)를 오버레이를 쓰는 자리
    (`_upsert_segment_overlay`, `_remove_segment_overlay`)와 읽는 자리(사진
    오버레이 정체성 기록, `preserve_source_audio` 조회)가 함께 쓴다. 예전에는
    이 순회를 세 곳에서 각자 다시 짜고 있었다 -- 세그먼트/`content_windows`
    중첩 구조가 바뀌면 한 곳이라도 빠뜨리는 순간 소리 없이 데이터가 샌다.

    컨테이너 자체(딕셔너리)를 낸다. `visual_overlays` 값이 아직 list가 아니거나
    없을 수도 있다 -- 쓰는 자리는 새 list로 갈아 끼우고, 읽는 자리는 각자
    `isinstance(..., list)`로 걸러야 한다(둘의 필요가 다르기 때문에 여기서
    미리 걸러주지 않는다).
    """
    segments = session.get("segments", [])
    has_direct_match = any(
        isinstance(segment, dict) and str(segment.get("segment_id") or "") == segment_id
        for segment in segments
    )
    containers: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        containing_segment_id = str(segment.get("segment_id") or "")
        direct_match = containing_segment_id == segment_id
        if direct_match:
            containers.append(segment)
        content_windows = segment.get("content_windows")
        if not isinstance(content_windows, list):
            continue
        for window in content_windows:
            if not isinstance(window, dict):
                continue
            source_segment_id = str(window.get("source_segment_id") or containing_segment_id)
            visible_match = direct_match if has_direct_match else source_segment_id == segment_id
            if visible_match:
                containers.append(window)
    return containers


def _current_image_overlay_preserve_source_audio(
    *, session: dict[str, Any], segment_id: str,
) -> bool | None:
    """지금 저장된 사진 오버레이의 `preserve_source_audio`를 읽는다.

    `update_segment_image_overlay`는 오버레이 **전체를 다시 쓴다**
    (`_upsert_overlay_list`가 옛 것을 지우고 새 payload를 붙인다). 유진이
    소리를 말하지 않고 자리·크기만 고치면(Task 4, 2026-09-11) 새 payload에는
    `preserve_source_audio` 열쇠가 아예 없으니, 쓰기 전에 옛 값을 먼저 읽어야
    이미 켜 둔 소리가 조용히 꺼지지 않는다. `editing_session_and_regeneration.py`의
    같은 이름 메서드와 같은 이유·같은 찾기 규칙(`_iter_matching_overlay_containers`)을
    쓴다 -- 그 파일이 이 모듈을 임포트하므로(반대 방향은 순환 임포트) 여기 둔다.
    """
    equivalent = _equivalent_overlay_types("image_overlay")
    for container in _iter_matching_overlay_containers(session, segment_id):
        overlays = container.get("visual_overlays")
        if not isinstance(overlays, list):
            continue
        for overlay in overlays:
            if isinstance(overlay, dict) and str(overlay.get("overlay_type") or "") in equivalent:
                value = overlay.get("preserve_source_audio")
                if isinstance(value, bool):
                    return value
    return None


def _current_image_overlay_preset_value(
    *, session: dict[str, Any], segment_id: str, field_name: str,
) -> str | None:
    """지금 저장된 사진 오버레이의 프리셋 한 칸(`vertical`/`horizontal`/`size`/
    `motion`)을 읽는다.

    `update_segment_image_overlay`가 "인자를 아예 안 줌"(세 상태 중 "지금 값
    유지")을 처리하려면 새로 쓰기 전에 옛 값을 먼저 읽어야 한다 -- 그 함수는
    오버레이 전체를 다시 쓰므로, 옮겨 심지 않으면 "유지"라 해 놓고 실제로는
    지워진다. `_current_image_overlay_preserve_source_audio`와 같은 이유·같은
    찾기 규칙(`_iter_matching_overlay_containers`)을 쓴다 -- 그 순회를 또
    새로 짜면 이 파일에서만 세 번째, 프로젝트 전체로는 네 번째 사본이 된다.
    """
    equivalent = _equivalent_overlay_types("image_overlay")
    for container in _iter_matching_overlay_containers(session, segment_id):
        overlays = container.get("visual_overlays")
        if not isinstance(overlays, list):
            continue
        for overlay in overlays:
            if isinstance(overlay, dict) and str(overlay.get("overlay_type") or "") in equivalent:
                value = overlay.get(field_name)
                if isinstance(value, str):
                    return value
    return None


def _upsert_segment_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    overlay_type: str,
    overlay_payload: dict[str, Any],
    mutation_type: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    matched = False
    for container in _iter_matching_overlay_containers(updated, segment_id):
        container["visual_overlays"] = _upsert_overlay_list(
            container.get("visual_overlays"), overlay_type=overlay_type, overlay_payload=overlay_payload,
        )
        matched = True
    if not matched:
        raise KeyError(f"Segment not found in editing session: {segment_id}")
    return _apply_manual_mutation(before=session, updated=updated, mutation_type=mutation_type, segment_id=segment_id, extra={"overlay_type": overlay_type})


def _remove_segment_overlay(
    *,
    session: dict[str, Any],
    segment_id: str,
    overlay_type: str,
    mutation_type: str,
) -> dict[str, Any]:
    updated = deepcopy(session)
    matched = False
    for container in _iter_matching_overlay_containers(updated, segment_id):
        container["visual_overlays"] = _remove_overlay_from_list(
            container.get("visual_overlays"), overlay_type=overlay_type,
        )
        matched = True
    if not matched:
        raise KeyError(f"Segment not found in editing session: {segment_id}")
    return _apply_manual_mutation(before=session, updated=updated, mutation_type=mutation_type, segment_id=segment_id, extra={"overlay_type": overlay_type})


_OVERLAY_TYPE_ALIASES = {
    "explanation_card": frozenset({"explanation_card"}),
    "image_overlay": frozenset({"image", "image_card", "image_overlay"}),
    "table_overlay": frozenset({"table_card", "table_overlay"}),
}


def _equivalent_overlay_types(overlay_type: str) -> frozenset[str]:
    return _OVERLAY_TYPE_ALIASES.get(overlay_type, frozenset({overlay_type}))


def _upsert_overlay_list(
    raw_overlays: object,
    *,
    overlay_type: str,
    overlay_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    equivalent = _equivalent_overlay_types(overlay_type)
    overlays = [
        deepcopy(overlay)
        for overlay in raw_overlays if isinstance(overlay, dict)
        and str(overlay.get("overlay_type") or "") not in equivalent
    ] if isinstance(raw_overlays, list) else []
    overlays.append(deepcopy(overlay_payload))
    return overlays


def _remove_overlay_from_list(raw_overlays: object, *, overlay_type: str) -> list[dict[str, Any]]:
    equivalent = _equivalent_overlay_types(overlay_type)
    return [
        deepcopy(overlay)
        for overlay in raw_overlays if isinstance(overlay, dict)
        and str(overlay.get("overlay_type") or "") not in equivalent
    ] if isinstance(raw_overlays, list) else []
