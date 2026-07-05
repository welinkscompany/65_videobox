from __future__ import annotations

from typing import Any, Callable


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
