from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json
import tempfile
import warnings

from videobox_core_engine.canonical_boolish import (
    normalize_strict_boolish as _normalize_runtime_boolish,
)
from videobox_core_engine.canonical_operator_review_text import (
    canonical_operator_review_text as _canonical_runtime_operator_review_text,
)
from videobox_core_engine.canonical_recommendation import (
    canonical_recommendation_type as _canonical_runtime_recommendation_type,
    VALID_CANONICAL_RECOMMENDATION_TYPES as VALID_RESTORED_RECOMMENDATION_TYPES,
)
from videobox_core_engine.canonical_review_status import (
    canonical_review_status as _canonical_runtime_review_status,
)
from videobox_core_engine.canonical_source_uri import (
    canonical_source_uri as _canonical_runtime_source_uri,
)
from videobox_core_engine.canonical_review_flag import (
    canonical_review_flag_code as _canonical_runtime_review_flag_code,
    VALID_CANONICAL_REVIEW_FLAG_CODES as VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES,
)
from videobox_core_engine.canonical_track import (
    canonical_track_type as _canonical_runtime_track_type,
    VALID_CANONICAL_TRACK_TYPES as VALID_RUNTIME_TRACK_TYPES,
)
from videobox_capcut_export import CapCutExportAdapter
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.ffmpeg_auto_cut_executor import FfmpegAutoCutExecutor
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.editing_session import (
    build_editing_session,
    build_partial_regeneration_request,
    clear_segment_broll_override,
    clear_segment_music_override,
    clear_segment_visual_overlays,
    clear_segment_tts_replacement,
    remove_segment_explanation_card,
    remove_segment_image_overlay,
    remove_segment_table_overlay,
    select_segment_tts_replacement,
    update_segment_explanation_card,
    update_segment_image_overlay,
    update_segment_broll_override,
    update_segment_caption,
    update_segment_cut_action,
    update_segment_music_override,
    update_segment_table_overlay,
    update_segment_visual_overlay,
)
from videobox_core_engine.output_operator_copy import (
    OutputOperatorCopyBuilder,
    StaticOutputOperatorCopyBuilder,
)
from videobox_core_engine.preview_renderer import PreviewRenderer
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.recommenders import KeywordBrollRecommender, RuleBasedMusicRecommender
from videobox_core_engine.review_action_mutations import (
    apply_approved_recommendation_to_timeline,
    extract_pending_recommendation_decision,
    filtered_review_flags_after_recommendation_decision,
    timeline_recommendation_decisions,
)
from videobox_core_engine.review_guidance import HeuristicReviewGuidanceBuilder, ReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import HeuristicSegmentAnalyzer, SegmentAnalyzer
from videobox_core_engine.timeline_builder import TimelineBuilder
from videobox_core_engine.transcript_alignment import HeuristicTranscriptAligner, TranscriptAligner
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.recommenders import RecommendationProvider, RecommendationRequest
from videobox_provider_interfaces.stt import MockSTTProvider, STTProvider, STTRequest
from videobox_provider_interfaces.tts import TTSRequest
from videobox_storage.local_project_store import LocalProjectStore


def _canonical_runtime_review_flag_message(value: object) -> str:
    return _canonical_runtime_operator_review_text(value)


def _canonical_runtime_pending_recommendation_reason(value: object) -> str:
    return _canonical_runtime_operator_review_text(value)


def _normalize_runtime_cut_action(value: object) -> str:
    cut_action = str(value or "keep")
    if cut_action not in {"keep", "remove", "trim"}:
        return "keep"
    return cut_action


def _build_review_guidance_reuse_key(review_snapshot: dict[str, Any]) -> str | None:
    if _canonical_runtime_review_status(review_snapshot.get("review_status"), default="draft") != "blocked":
        return None

    review_flags: list[dict[str, str]] = []
    existing_review_flag_keys: set[tuple[str, str, str]] = set()
    for item in review_snapshot.get("review_flags", []):
        if not isinstance(item, dict):
            continue
        code = _canonical_runtime_review_flag_code(item.get("code"))
        segment_id = str(item.get("segment_id") or "").strip()
        if code not in VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES or not segment_id:
            continue
        message = _canonical_runtime_review_flag_message(item.get("message"))
        review_flag_key = (code, segment_id, message)
        if review_flag_key in existing_review_flag_keys:
            continue
        existing_review_flag_keys.add(review_flag_key)
        review_flags.append({"code": code, "segment_id": segment_id, "message": message})
    review_flags.sort(key=lambda item: (item["code"], item["segment_id"], item["message"]))

    pending_recommendations: list[dict[str, str]] = []
    existing_pending_recommendation_keys: set[tuple[str, str, str, str, str, str]] = set()
    for item in review_snapshot.get("pending_recommendations", []):
        if not _is_runtime_blocking_pending_recommendation(item):
            continue
        recommendation_id = str(item.get("recommendation_id") or "").strip()
        target_segment_id = str(item.get("target_segment_id") or "").strip()
        recommendation_type = _canonical_runtime_recommendation_type(item.get("recommendation_type"))
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        reason = _canonical_runtime_pending_recommendation_reason(item.get("reason"))
        selected_asset_id = str(item.get("selected_asset_id") or "").strip()
        selected_asset_uri = _canonical_runtime_source_uri(payload.get("selected_asset_uri"))
        pending_recommendation_key = (
            recommendation_id,
            target_segment_id,
            recommendation_type,
            reason,
            selected_asset_id,
            selected_asset_uri,
        )
        if pending_recommendation_key in existing_pending_recommendation_keys:
            continue
        existing_pending_recommendation_keys.add(pending_recommendation_key)
        pending_recommendations.append(
            {
                "recommendation_id": recommendation_id,
                "target_segment_id": target_segment_id,
                "recommendation_type": recommendation_type,
                "reason": reason,
                "selected_asset_id": selected_asset_id,
                "selected_asset_uri": selected_asset_uri,
            }
        )
    pending_recommendations.sort(
        key=lambda item: (
            item["recommendation_id"],
            item["target_segment_id"],
            item["recommendation_type"],
            item["reason"],
            item["selected_asset_id"],
            item["selected_asset_uri"],
        )
    )

    if not review_flags and not pending_recommendations:
        return None

    return json.dumps(
        {
            "review_status": "blocked",
            "review_flags": review_flags,
            "pending_recommendations": pending_recommendations,
        },
        ensure_ascii=True,
        sort_keys=True,
    )


def _is_valid_runtime_overlay(overlay: object) -> bool:
    if not isinstance(overlay, dict):
        return False
    overlay_type = str(overlay.get("overlay_type") or "").strip()
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


def _is_runtime_blocking_review_flag(flag: object) -> bool:
    if not isinstance(flag, dict):
        return False
    code = flag.get("code")
    segment_id = flag.get("segment_id")
    return (
        isinstance(code, str)
        and bool(code.strip())
        and isinstance(segment_id, str)
        and bool(segment_id.strip())
    )


def _runtime_pending_recommendation_identity_key(item: object) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        return ("", "", "")
    recommendation_id = item.get("recommendation_id")
    target_segment_id = item.get("target_segment_id")
    return (
        recommendation_id.strip() if isinstance(recommendation_id, str) else "",
        target_segment_id.strip() if isinstance(target_segment_id, str) else "",
        _canonical_runtime_recommendation_type(item.get("recommendation_type")),
    )


def _is_runtime_blocking_pending_recommendation(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    recommendation_id, target_segment_id, recommendation_type = (
        _runtime_pending_recommendation_identity_key(item)
    )
    decision_state = str(item.get("decision_state") or "").strip().lower()
    if decision_state and decision_state != "pending":
        return False
    if _normalize_runtime_boolish(item.get("auto_apply_allowed", False)) and not _normalize_runtime_boolish(
        item.get("review_required", False)
    ):
        return False
    return (
        bool(recommendation_id)
        and bool(target_segment_id)
        and recommendation_type in VALID_RESTORED_RECOMMENDATION_TYPES
    )


def _normalized_runtime_pending_recommendations(items: object) -> list[dict[str, Any]]:
    normalized_pending_recommendations: list[dict[str, Any]] = []
    existing_pending_keys: set[tuple[str, str, str]] = set()
    if not isinstance(items, list):
        return normalized_pending_recommendations
    for item in items:
        if not _is_runtime_blocking_pending_recommendation(item):
            continue
        pending_key = _runtime_pending_recommendation_identity_key(item)
        recommendation_id, target_segment_id, recommendation_type = pending_key
        normalized_item = {
            **deepcopy(item),
            "recommendation_id": recommendation_id,
            "target_segment_id": target_segment_id,
            "recommendation_type": recommendation_type,
            "provider_trace": item.get("provider_trace")
            if isinstance(item.get("provider_trace"), dict)
            else build_provider_trace(final_provider="rule_based_fallback"),
        }
        if pending_key in existing_pending_keys:
            continue
        existing_pending_keys.add(pending_key)
        normalized_pending_recommendations.append(normalized_item)
    return normalized_pending_recommendations
