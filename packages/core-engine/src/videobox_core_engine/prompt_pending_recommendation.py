from __future__ import annotations

from typing import Any, Callable
from videobox_domain_models.recommendations import RecommendationType


VALID_PROMPT_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.OVERLAY.value,
}

VALID_PROMPT_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "tts_replacement_review_required",
}


def canonical_prompt_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def canonical_prompt_decision_state(value: object) -> str:
    return str(value or "").strip().lower()


def canonical_prompt_review_flag_message(value: object) -> str:
    message = str(value or "").strip()
    return message or "Operator review required before approval or output."


def has_canonical_review_flag_identity(
    item: dict[str, Any],
    *,
    canonical_review_flag_code: Callable[[object], str],
    valid_review_flag_codes: set[str],
) -> bool:
    code = canonical_review_flag_code(item.get("code"))
    segment_id = str(item.get("segment_id") or "").strip()
    return bool(code in valid_review_flag_codes and segment_id)


def has_canonical_pending_recommendation_identity(
    item: dict[str, Any],
    *,
    canonical_recommendation_type: Callable[[object], str],
    valid_recommendation_types: set[str],
) -> bool:
    recommendation_id = str(item.get("recommendation_id") or "").strip()
    target_segment_id = str(item.get("target_segment_id") or "").strip()
    recommendation_type = canonical_recommendation_type(item.get("recommendation_type"))
    return bool(
        recommendation_id
        and target_segment_id
        and recommendation_type in valid_recommendation_types
    )


def normalize_prompt_review_flag_row(
    item: dict[str, Any],
    *,
    canonical_review_flag_code: Callable[[object], str],
    canonical_review_flag_message: Callable[[object], str],
) -> dict[str, Any]:
    prompt_row = dict(item)
    prompt_row["code"] = canonical_review_flag_code(prompt_row.get("code"))
    prompt_row["segment_id"] = str(prompt_row.get("segment_id") or "").strip()
    prompt_row["message"] = canonical_review_flag_message(prompt_row.get("message"))
    return prompt_row


def normalize_prompt_pending_recommendation_row(
    item: dict[str, Any],
    *,
    canonical_recommendation_type: Callable[[object], str],
    canonical_reason: Callable[[object], str],
    canonical_decision_state: Callable[[object], str],
) -> dict[str, Any]:
    prompt_row = dict(item)
    if "recommendation_id" in prompt_row:
        prompt_row["recommendation_id"] = str(prompt_row.get("recommendation_id") or "").strip()
    prompt_row["recommendation_type"] = canonical_recommendation_type(
        prompt_row.get("recommendation_type")
    )
    if "target_segment_id" in prompt_row:
        prompt_row["target_segment_id"] = str(prompt_row.get("target_segment_id") or "").strip()
    prompt_row["reason"] = canonical_reason(prompt_row.get("reason"))
    if "decision_state" in prompt_row:
        prompt_row["decision_state"] = canonical_decision_state(prompt_row.get("decision_state"))
    if "selected_asset_id" in prompt_row:
        prompt_row["selected_asset_id"] = str(prompt_row.get("selected_asset_id") or "").strip()
    if "created_at" in prompt_row:
        prompt_row["created_at"] = str(prompt_row.get("created_at") or "").strip()
    payload = prompt_row.get("payload")
    if isinstance(payload, dict) and "selected_asset_uri" in payload:
        normalized_payload = dict(payload)
        normalized_payload["selected_asset_uri"] = str(
            normalized_payload.get("selected_asset_uri") or ""
        ).strip()
        prompt_row["payload"] = normalized_payload
    return prompt_row
