from __future__ import annotations

from copy import deepcopy
from typing import Any

from videobox_core_engine.canonical_recommendation import (
    canonical_recommendation_type as _canonical_recommendation_type,
    VALID_CANONICAL_RECOMMENDATION_TYPES as VALID_PENDING_RECOMMENDATION_TYPES,
)
from videobox_core_engine.canonical_review_flag import canonical_review_flag_code as _canonical_review_flag_code
from videobox_core_engine.canonical_source_uri import canonical_source_uri as _canonical_source_uri
from videobox_core_engine.canonical_track import canonical_track_type as _canonical_track_type
from videobox_core_engine.provider_trace import build_provider_trace

def _is_valid_pending_recommendation_entry(item: dict[str, Any]) -> bool:
    recommendation_id = str(item.get("recommendation_id") or "").strip()
    target_segment_id = str(item.get("target_segment_id") or "").strip()
    recommendation_type = _canonical_recommendation_type(item.get("recommendation_type"))
    return bool(
        recommendation_id
        and target_segment_id
        and recommendation_type in VALID_PENDING_RECOMMENDATION_TYPES
    )


def extract_pending_recommendation_decision(
    *,
    timeline: dict[str, Any],
    recommendation_id: str,
    decision: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    pending_recommendations = deepcopy(timeline.get("pending_recommendations", []))
    original_recommendation: dict[str, Any] | None = None
    decided_recommendation: dict[str, Any] | None = None
    remaining_pending: list[dict[str, Any]] = []
    for item in pending_recommendations:
        if not isinstance(item, dict):
            continue
        if not _is_valid_pending_recommendation_entry(item):
            continue
        if str(item.get("recommendation_id") or "").strip() != recommendation_id:
            remaining_pending.append(item)
            continue
        original_recommendation = deepcopy(item)
        decided_recommendation = deepcopy(item)
        decided_recommendation["recommendation_id"] = recommendation_id
        if decision == "approved":
            decided_recommendation["auto_apply_allowed"] = True
            decided_recommendation["review_required"] = False
            decided_recommendation["decision_state"] = "approved"
            decided_recommendation["provider_trace"] = decided_recommendation.get(
                "provider_trace"
            ) or build_provider_trace(
                final_provider=(
                    "heuristic_fallback"
                    if _canonical_recommendation_type(decided_recommendation.get("recommendation_type"))
                    == "broll"
                    else "rule_based_fallback"
                )
            )
    if original_recommendation is None or decided_recommendation is None:
        raise KeyError(f"Pending recommendation not found: {recommendation_id}")
    return original_recommendation, decided_recommendation, remaining_pending


def timeline_recommendation_decisions(
    *,
    timeline: dict[str, Any],
    recommendation_id: str,
    decision: str,
) -> dict[str, str]:
    existing = timeline.get("recommendation_decisions")
    normalized = (
        {
            str(key).strip(): str(value).strip()
            for key, value in existing.items()
            if str(key).strip() and str(value).strip()
        }
        if isinstance(existing, dict)
        else {}
    )
    normalized[recommendation_id] = decision
    return normalized


def should_keep_review_flag(
    *,
    flag: dict[str, Any],
    recommendation_flag_code: str,
    target_segment_id: str,
    remaining_pending: list[dict[str, Any]],
) -> bool:
    flag_code = _canonical_review_flag_code(flag.get("code"))
    flag_segment_id = str(flag.get("segment_id") or "").strip()
    if not (
        flag_code == recommendation_flag_code
        and flag_segment_id == target_segment_id
    ):
        return True
    return any(
        _canonical_recommendation_type(item.get("recommendation_type"))
        == recommendation_flag_code.removesuffix("_review_required")
        and str(item.get("target_segment_id") or "").strip() == target_segment_id
        for item in remaining_pending
    )


def filtered_review_flags_after_recommendation_decision(
    *,
    timeline: dict[str, Any],
    decided_recommendation: dict[str, Any],
    remaining_pending: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendation_flag_code = (
        f"{_canonical_recommendation_type(decided_recommendation.get('recommendation_type'))}_review_required"
    )
    target_segment_id = str(decided_recommendation.get("target_segment_id") or "").strip()
    return [
        flag
        for flag in deepcopy(timeline.get("review_flags", []))
        if isinstance(flag, dict)
        if should_keep_review_flag(
            flag=flag,
            recommendation_flag_code=recommendation_flag_code,
            target_segment_id=target_segment_id,
            remaining_pending=remaining_pending,
        )
    ]


def apply_approved_recommendation_to_timeline(
    *,
    timeline: dict[str, Any],
    decided_recommendation: dict[str, Any],
) -> None:
    if _canonical_recommendation_type(decided_recommendation.get("recommendation_type")) != "tts_replacement":
        return
    payload = decided_recommendation.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Approved TTS replacement requires payload.selected_asset_uri.")
    selected_asset_uri = _canonical_source_uri(payload.get("selected_asset_uri"))
    target_segment_id = str(decided_recommendation.get("target_segment_id") or "").strip()
    if not selected_asset_uri:
        raise ValueError("Approved TTS replacement requires payload.selected_asset_uri.")
    if not target_segment_id:
        raise ValueError("Approved TTS replacement requires target_segment_id.")
    matched_clip = False
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        if _canonical_track_type(track.get("track_type")) != "narration":
            continue
        clips = track.get("clips")
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            if str(clip.get("segment_id") or "").strip() == target_segment_id:
                matched_clip = True
                clip["asset_uri"] = selected_asset_uri
    if not matched_clip:
        raise ValueError("Approved TTS replacement requires a matching target narration clip.")
