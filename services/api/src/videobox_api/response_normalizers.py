from __future__ import annotations

from typing import Any

from videobox_core_engine.provider_trace import build_provider_trace
from videobox_domain_models.recommendations import RecommendationType

VALID_PREVIEW_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.SFX.value,
    RecommendationType.OVERLAY.value,
}
VALID_PREVIEW_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "sfx_review_required",
    "tts_replacement_review_required",
}


def _canonical_preview_review_flag_code(value: object) -> str:
    return str(value or "").strip().lower()


def _is_valid_preflight_visual_overlay(overlay: object) -> bool:
    if not isinstance(overlay, dict):
        return False
    overlay_type = str(overlay.get("overlay_type") or "").strip()
    if not overlay_type:
        return False
    if overlay_type not in {
        "image",
        "image_card",
        "image_overlay",
        "explanation_card",
        "table_card",
        "table_overlay",
        "hook_title",
        "visual_overlay",
    }:
        return False
    if overlay_type in {"explanation_card", "table_card", "table_overlay"}:
        return bool(str(overlay.get("text") or "").strip())
    if overlay_type in {"hook_title", "visual_overlay"}:
        return bool(str(overlay.get("text") or "").strip()) or bool(
            str(overlay.get("asset_id") or "").strip()
        )
    return bool(str(overlay.get("asset_id") or "").strip())


def _build_targeted_segments(
    session: dict[str, Any],
    segment_ids: list[str],
) -> list[dict[str, object]]:
    segment_lookup: dict[str, dict[str, object]] = {}
    for segment in session.get("segments", []):
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        if segment_id not in segment_lookup:
            segment_lookup[segment_id] = segment

    targeted_segments: list[dict[str, object]] = []
    for segment_id in segment_ids:
        normalized_segment_id = str(segment_id or "").strip()
        segment = segment_lookup.get(normalized_segment_id)
        if not isinstance(segment, dict):
            continue
        cut_action = str(segment.get("cut_action") or "keep")
        if cut_action not in {"keep", "remove", "trim"}:
            cut_action = "keep"
        review_required = segment.get("review_required", False)
        if isinstance(review_required, str):
            normalized_review_required = review_required.strip().lower()
            review_required = normalized_review_required not in {"", "0", "false", "no", "off"}
        elif not isinstance(review_required, bool):
            review_required = False
        broll_override = segment.get("broll_override")
        if not isinstance(broll_override, dict):
            broll_override = None
        else:
            broll_asset_id = broll_override.get("asset_id")
            if not isinstance(broll_asset_id, str) or not broll_asset_id.strip():
                broll_override = None
        visual_overlays = segment.get("visual_overlays")
        if not isinstance(visual_overlays, list):
            visual_overlays = []
        else:
            visual_overlays = [
                overlay
                for overlay in visual_overlays
                if _is_valid_preflight_visual_overlay(overlay)
            ]
        music_override = segment.get("music_override")
        if not isinstance(music_override, dict):
            music_override = None
        else:
            music_asset_id = music_override.get("asset_id")
            if not isinstance(music_asset_id, str) or not music_asset_id.strip():
                music_override = None
        tts_replacement = segment.get("tts_replacement")
        if not isinstance(tts_replacement, dict):
            tts_replacement = None
        else:
            recommendation_id = tts_replacement.get("recommendation_id")
            asset_id = tts_replacement.get("asset_id")
            if (
                not isinstance(recommendation_id, str)
                or not recommendation_id.strip()
                or not isinstance(asset_id, str)
                or not asset_id.strip()
            ):
                tts_replacement = None
        targeted_segments.append(
            {
                "segment_id": normalized_segment_id,
                "caption_text": str(segment.get("caption_text") or ""),
                "cut_action": cut_action,
                "review_required": bool(review_required),
                "broll_override": broll_override,
                "visual_overlays": visual_overlays,
                "music_override": music_override,
                "tts_replacement": tts_replacement,
            }
        )
    return targeted_segments


def _build_affected_output_areas(downstream_steps: list[str]) -> list[str]:
    areas: list[str] = []
    for step in downstream_steps:
        if step == "segment_refresh" and "segment copy" not in areas:
            areas.append("segment copy")
        if step == "broll_refresh" and "b-roll track" not in areas:
            areas.append("b-roll track")
        if step == "music_refresh" and "music bed" not in areas:
            areas.append("music bed")
        if step == "overlay_refresh" and "visual overlays" not in areas:
            areas.append("visual overlays")
        if step == "tts_refresh" and "narration track" not in areas:
            areas.append("narration track")
        if step == "timeline_build":
            for area in ["timeline preview", "subtitle render", "capcut export"]:
                if area not in areas:
                    areas.append(area)
    return areas


def _build_preflight_review_prediction(
    *,
    source_timeline: dict[str, Any],
    targeted_segments: list[dict[str, object]],
    fields: list[str],
) -> tuple[str, list[str]]:
    prediction_reasons: list[str] = []
    source_review_flags = source_timeline.get("review_flags")
    if not isinstance(source_review_flags, list):
        source_review_flags = []
    else:
        source_review_flags = [
            flag
            for flag in source_review_flags
            if (
                isinstance(flag, dict)
                and isinstance(flag.get("code"), str)
                and _canonical_preview_review_flag_code(flag.get("code"))
                in VALID_PREVIEW_REVIEW_FLAG_CODES
                and isinstance(flag.get("segment_id"), str)
                and flag.get("segment_id").strip()
            )
        ]
    recommendation_blocker_sources: list[object] = []
    source_pending_recommendations = source_timeline.get("pending_recommendations")
    if isinstance(source_pending_recommendations, list):
        recommendation_blocker_sources.extend(source_pending_recommendations)
    source_applied_recommendations = source_timeline.get("applied_recommendations")
    if isinstance(source_applied_recommendations, list):
        recommendation_blocker_sources.extend(source_applied_recommendations)
    source_pending_recommendations = [
            item
            for item in recommendation_blocker_sources
            if (
                isinstance(item, dict)
                and (
                    not str(item.get("decision_state") or "").strip()
                    or str(item.get("decision_state") or "").strip().lower() == "pending"
                )
                and (
                    not _normalize_boolish_response(item.get("auto_apply_allowed", False))
                    or _normalize_boolish_response(item.get("review_required", False))
                )
                and isinstance(item.get("recommendation_id"), str)
                and item.get("recommendation_id").strip()
                and isinstance(item.get("target_segment_id"), str)
                and item.get("target_segment_id").strip()
                and isinstance(item.get("recommendation_type"), str)
                and item.get("recommendation_type").strip().lower() in VALID_PREVIEW_RECOMMENDATION_TYPES
            )
        ]
    if source_review_flags or source_pending_recommendations:
        prediction_reasons.append(
            "source timeline already has unresolved review blockers that rerun will preserve"
        )
    if any(_normalize_boolish_response(segment.get("review_required", False)) for segment in targeted_segments):
        prediction_reasons.append(
            "selected segments already require operator review, so rerun output stays blocked"
        )
    known_fields = {
        "caption",
        "cut_action",
        "broll",
        "music",
        "visual_overlay",
        "explanation_card",
        "image_overlay",
        "table_overlay",
        "tts_replacement",
    }
    if prediction_reasons:
        return "blocked", prediction_reasons
    if any(field not in known_fields for field in fields):
        return "unknown", ["rerun review status could not be predicted for the requested field set"]
    return "draft", []


def _normalize_provider_trace_response(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        routing_mode = str(value.get("routing_mode") or "").strip()
        final_provider = str(value.get("final_provider") or "").strip()
        fallback_reasons = value.get("fallback_reasons")
        return {
            "routing_mode": routing_mode or "local_only",
            "final_provider": final_provider or "rule_based_fallback",
            "fallback_reasons": [
                str(reason)
                for reason in fallback_reasons
                if isinstance(reason, str) and reason.strip()
            ]
            if isinstance(fallback_reasons, list)
            else [],
        }
    return build_provider_trace(final_provider="rule_based_fallback")


def _normalize_review_flags_for_response(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().lower()
        segment_id = str(item.get("segment_id") or "").strip()
        if not code or not segment_id:
            continue
        message = str(item.get("message") or "").strip()
        normalized.append(
            {
                "code": code,
                "segment_id": segment_id,
                "message": message or "Operator review required before approval or output.",
            }
        )
    return normalized


def _normalize_boolish_response(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


def _normalize_recommendations_for_response(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        recommendation_id = str(item.get("recommendation_id") or "").strip()
        target_segment_id = str(item.get("target_segment_id") or "").strip()
        recommendation_type = str(item.get("recommendation_type") or "").strip().lower()
        if (
            not recommendation_id
            or not target_segment_id
            or recommendation_type not in VALID_PREVIEW_RECOMMENDATION_TYPES
        ):
            continue
        score_value = item.get("score", 0.0)
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            score = 0.0
        payload = item.get("payload")
        normalized_payload = dict(payload) if isinstance(payload, dict) else {}
        selected_asset_uri = str(normalized_payload.get("selected_asset_uri") or "").strip()
        if selected_asset_uri:
            normalized_payload["selected_asset_uri"] = selected_asset_uri
        elif "selected_asset_uri" in normalized_payload:
            normalized_payload["selected_asset_uri"] = ""
        normalized.append(
            {
                "recommendation_id": recommendation_id,
                "target_segment_id": target_segment_id,
                "recommendation_type": recommendation_type,
                "selected_asset_id": str(item.get("selected_asset_id") or "").strip() or None,
                "score": score,
                "reason": str(item.get("reason") or "").strip()
                or "Operator review required before approval or output.",
                "auto_apply_allowed": _normalize_boolish_response(
                    item.get("auto_apply_allowed", False)
                ),
                "review_required": _normalize_boolish_response(
                    item.get("review_required", False)
                ),
                "decision_state": str(item.get("decision_state") or "").strip().lower() or None,
                "payload": normalized_payload,
                "created_at": str(item.get("created_at") or "").strip() or "unknown",
                "provider_trace": _normalize_provider_trace_response(item.get("provider_trace")),
            }
        )
    return normalized


def _normalize_timeline_payload_for_response(timeline: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(timeline)
    normalized["review_flags"] = _normalize_review_flags_for_response(timeline.get("review_flags"))
    normalized["applied_recommendations"] = _normalize_recommendations_for_response(
        timeline.get("applied_recommendations")
    )
    normalized["pending_recommendations"] = _normalize_recommendations_for_response(
        timeline.get("pending_recommendations")
    )
    return normalized


def _normalize_operator_guidance_response(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        value = {}
    action_items = value.get("action_items")
    provider_trace = value.get("provider_trace")
    return {
        "summary": str(value.get("summary") or "").strip()
        or "Operator review guidance is unavailable.",
        "action_items": [
            str(item).strip()
            for item in action_items
            if str(item).strip()
        ]
        if isinstance(action_items, list)
        else [],
        "provider_trace": provider_trace
        if isinstance(provider_trace, dict)
        else build_provider_trace(final_provider="heuristic_fallback"),
    }
