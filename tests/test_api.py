from __future__ import annotations

from dataclasses import dataclass, field
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import (
    _build_preflight_review_prediction,
    _normalize_review_flags_for_response,
    _normalize_recommendations_for_response,
    create_app,
)
from videobox_api.orchestration import LocalFirstRuntimeService
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_operator_copy import LocalFirstOutputOperatorCopyBuilder
from videobox_core_engine.preview_renderer import PreviewRenderer
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.review_action_mutations import apply_approved_recommendation_to_timeline
from videobox_core_engine.review_guidance import HeuristicReviewGuidanceBuilder, LocalFirstReviewGuidanceBuilder
from videobox_core_engine.settings import AutoCutConfig, LocalOpenAICompatibleRuntimeConfig
from videobox_core_engine.timeline_builder import TimelineBuilder
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from videobox_provider_interfaces.stt import STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore


@dataclass
class FakeStructuredProvider:
    responses: list[StructuredLLMResponse] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        raise AssertionError("No fake structured response configured.")


class FailingSegmentAnalyzer:
    def analyze(
        self,
        *,
        project_id: str,
        transcript_segments: list[dict[str, object]],
        script_text: str | None,
    ) -> list[dict[str, object]]:
        del project_id, transcript_segments, script_text
        raise LocalFirstStructuredGenerationError(
            message="segment provider failed",
            error_code="SEGMENT_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="local_qwen",
                fallback_reasons=["local_provider_error"],
            ),
        )


class FailingBrollRecommender:
    def recommend(self, request):  # noqa: ANN001
        del request
        raise LocalFirstStructuredGenerationError(
            message="broll Gemini fallback failed",
            error_code="BROLL_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        )


class FailingMusicRecommenderWithoutTrace:
    def recommend(self, request):  # noqa: ANN001
        del request
        raise RuntimeError("music provider exploded without trace")


class FailingOutputOperatorCopyBuilder:
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, object],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> dict[str, object]:
        del project_id, timeline, subtitle_file_uri
        raise LocalFirstStructuredGenerationError(
            message=f"{output_target} provider failed",
            error_code="OUTPUT_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        )


def test_preflight_review_prediction_ignores_string_false_targeted_segment_review_required() -> None:
    predicted_status, reasons = _build_preflight_review_prediction(
        source_timeline={
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
        targeted_segments=[
            {
                "segment_id": "seg_001",
                "caption_text": "Office overview.",
                "review_required": "false",
            }
        ],
        fields=["caption"],
    )

    assert predicted_status == "draft"
    assert reasons == []


def test_build_targeted_segments_matches_trimmed_request_segment_ids() -> None:
    from videobox_api.main import _build_targeted_segments

    targeted_segments = _build_targeted_segments(
        {
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Office overview.",
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ]
        },
        [" seg_001 "],
    )

    assert targeted_segments == [
        {
            "segment_id": "seg_001",
            "caption_text": "Office overview.",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]


def test_partial_regeneration_helper_matches_trimmed_source_segment_ids() -> None:
    class _FakeStore:
        def list_segments(self, *, project_id: str) -> list[dict[str, object]]:
            assert project_id == "project_001"
            return [
                {
                    "segment_id": " seg_001 ",
                    "text": "Source segment with padded id.",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "confidence": 0.99,
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ]

    runner = LocalPipelineRunner(store=_FakeStore())  # type: ignore[arg-type]

    segments = runner._segments_for_timeline(
        project_id="project_001",
        timeline={
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ]
        },
    )

    assert segments == [
        {
            "segment_id": " seg_001 ",
            "text": "Source segment with padded id.",
            "start_sec": 0.0,
            "end_sec": 1.0,
            "confidence": 0.99,
            "review_required": False,
            "cleanup_decision": "keep",
        }
    ]


def test_recommendation_response_normalization_canonicalizes_mixed_case_decision_state() -> None:
    recommendations = _normalize_recommendations_for_response(
        [
            {
                "recommendation_id": "rec_001",
                "target_segment_id": "seg_001",
                "recommendation_type": "tts_replacement",
                "selected_asset_id": "asset_tts_001",
                "score": 0.91,
                "reason": "Approved TTS replacement.",
                "auto_apply_allowed": True,
                "review_required": False,
                "decision_state": " Approved ",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
                "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
            }
        ]
    )

    assert recommendations[0]["decision_state"] == "approved"


def test_recommendation_response_normalization_canonicalizes_mixed_case_recommendation_type() -> None:
    recommendations = _normalize_recommendations_for_response(
        [
            {
                "recommendation_id": "rec_001",
                "target_segment_id": "seg_001",
                "recommendation_type": " TTS_REPLACEMENT ",
                "selected_asset_id": "asset_tts_001",
                "score": 0.91,
                "reason": "Approved TTS replacement.",
                "auto_apply_allowed": True,
                "review_required": False,
                "decision_state": "approved",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
                "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
            }
        ]
    )

    assert recommendations[0]["recommendation_type"] == "tts_replacement"


def test_review_flag_response_normalization_canonicalizes_mixed_case_code() -> None:
    review_flags = _normalize_review_flags_for_response(
        [
            {
                "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                "segment_id": " seg_001 ",
            }
        ]
    )

    assert review_flags == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_001",
            "message": "Operator review required before approval or output.",
        }
    ]


def test_timeline_builder_treats_string_false_recommendation_review_required_as_false() -> None:
    builder = TimelineBuilder()

    timeline = builder.build(
        project_id="project_001",
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
        recommendations=[
            {
                "recommendation_id": "rec_broll_001",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.BROLL.value,
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Office skyline b-roll.",
                "auto_apply_allowed": True,
                "review_required": "false",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
    )

    assert [item["recommendation_id"] for item in timeline.applied_recommendations] == ["rec_broll_001"]
    assert timeline.pending_recommendations == []
    assert timeline.review_flags == []


def test_timeline_builder_review_snapshot_treats_string_false_recommendation_fields_as_applied() -> None:
    builder = TimelineBuilder()

    snapshot = builder.build_review_snapshot(
        project_id="project_001",
        timeline_id="timeline_001",
        segments=[],
        recommendations=[
            {
                "recommendation_id": "rec_broll_001",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.BROLL.value,
                "selected_asset_id": "asset_broll_001",
                "score": 0.91,
                "reason": "Keep existing B-roll choice.",
                "auto_apply_allowed": "true",
                "review_required": "false",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert [item["recommendation_id"] for item in snapshot["applied_recommendations"]] == ["rec_broll_001"]
    assert snapshot["pending_recommendations"] == []


def test_timeline_builder_canonicalizes_mixed_case_applied_recommendation_type_surface() -> None:
    builder = TimelineBuilder()

    timeline = builder.build(
        project_id="project_001",
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
        recommendations=[
            {
                "recommendation_id": "rec_tts_001",
                "target_segment_id": "seg_001",
                "recommendation_type": " TTS_REPLACEMENT ",
                "selected_asset_id": "asset_tts_001",
                "score": 0.91,
                "reason": "Approved TTS replacement.",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {
                    "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                },
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
    )

    assert timeline.applied_recommendations[0]["recommendation_type"] == "tts_replacement"


def test_timeline_builder_filters_unknown_applied_recommendation_from_surface() -> None:
    builder = TimelineBuilder()

    timeline = builder.build(
        project_id="project_001",
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
        recommendations=[
            {
                "recommendation_id": "rec_unknown_applied_surface",
                "target_segment_id": "seg_001",
                "recommendation_type": "legacy_overlay_pick",
                "selected_asset_id": "asset_overlay_001",
                "score": 0.5,
                "reason": "Unknown stale recommendation should not remain on applied surface.",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
    )

    assert timeline.applied_recommendations == []


def test_timeline_builder_review_snapshot_filters_unknown_applied_recommendation_from_surface() -> None:
    builder = TimelineBuilder()

    snapshot = builder.build_review_snapshot(
        project_id="project_001",
        timeline_id="timeline_001",
        segments=[],
        recommendations=[
            {
                "recommendation_id": "rec_unknown_applied_surface",
                "target_segment_id": "seg_001",
                "recommendation_type": "legacy_overlay_pick",
                "selected_asset_id": "asset_overlay_001",
                "score": 0.5,
                "reason": "Unknown stale recommendation should not remain on applied surface.",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert snapshot["applied_recommendations"] == []


def test_preview_renderer_treats_string_false_tts_recommendation_review_required_as_false() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved TTS replacement.",
                    "auto_apply_allowed": "true",
                    "review_required": "false",
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]


def test_preview_renderer_matches_trimmed_tts_recommendation_type_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": " tts_replacement ",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved trimmed TTS replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]
    assert "local://projects/project_001/assets/narration_original.wav" not in payload["player_html"]


def test_preview_renderer_matches_trimmed_tts_target_segment_id_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": " seg_001 ",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved TTS replacement with trimmed target segment id.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]
    assert "local://projects/project_001/assets/narration_original.wav" not in payload["player_html"]


def test_preview_renderer_matches_trimmed_narration_clip_segment_id_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": " seg_001 ",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved TTS replacement with trimmed narration clip segment id.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]
    assert "local://projects/project_001/assets/narration_original.wav" not in payload["player_html"]


def test_preview_renderer_trims_narration_clip_segment_id_surface_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": " seg_001 ",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved TTS replacement with trimmed narration clip segment id surface.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "seg_001: local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]
    assert " seg_001 " not in payload["player_html"]


def test_preview_renderer_matches_mixed_case_tts_recommendation_type_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/assets/tts_selected.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved mixed-case TTS replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_001/assets/tts_selected.wav"
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    assert "local://projects/project_001/assets/tts_selected.wav" in payload["player_html"]
    assert "local://projects/project_001/assets/narration_original.wav" not in payload["player_html"]


def test_preview_renderer_canonicalizes_mixed_case_review_status_surface() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": " APPROVED ",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/assets/narration_original.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [],
        },
    )

    assert "Review status: approved" in payload["player_html"]
    assert "Review status:  APPROVED " not in payload["player_html"]


def test_preview_renderer_matches_mixed_case_narration_track_type_for_narration_source() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": " NARRATION ",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_001/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "applied_recommendations": [],
        },
    )

    assert "seg_001: local://projects/project_001/assets/narration_original.wav" in payload["player_html"]


def test_preview_renderer_canonicalizes_mixed_case_track_type_surface() -> None:
    renderer = PreviewRenderer()

    payload = renderer.build_preview_payload(
        project_id="project_001",
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "narration_source_uri": "local://projects/project_001/assets/narration_original.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": " NARRATION ",
                    "clips": [],
                }
            ],
            "applied_recommendations": [],
        },
    )

    assert "<strong>narration</strong>: 0 clips" in payload["player_html"]
    assert "<strong> NARRATION </strong>" not in payload["player_html"]


def test_apply_approved_tts_recommendation_matches_mixed_case_narration_track_type() -> None:
    timeline = {
        "tracks": [
            {
                "track_id": "narration_primary",
                "track_type": " NARRATION ",
                "clips": [
                    {
                        "clip_id": "clip_narration_001",
                        "segment_id": "seg_001",
                        "asset_uri": "local://projects/project_001/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "clip_type": "narration",
                    }
                ],
            }
        ]
    }

    apply_approved_recommendation_to_timeline(
        timeline=timeline,
        decided_recommendation={
            "recommendation_type": "tts_replacement",
            "target_segment_id": "seg_001",
            "payload": {
                "selected_asset_uri": "local://projects/project_001/assets/generated/asset_tts_001.wav"
            },
        },
    )

    assert timeline["tracks"][0]["clips"][0]["asset_uri"] == (
        "local://projects/project_001/assets/generated/asset_tts_001.wav"
    )


def test_output_operator_copy_builder_canonicalizes_mixed_case_review_status_in_prompt() -> None:
    builder = LocalFirstOutputOperatorCopyBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        timeline={
            "timeline_id": "timeline_001",
            "review_status": " APPROVED ",
            "tracks": [],
            "review_flags": [],
            "pending_recommendations": [],
        },
        output_target="preview_render",
        subtitle_file_uri=None,
    )

    assert "Review status: approved" in prompt
    assert "Review status:  APPROVED " not in prompt


def test_output_operator_copy_builder_canonicalizes_mixed_case_track_type_in_prompt() -> None:
    builder = LocalFirstOutputOperatorCopyBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        timeline={
            "timeline_id": "timeline_001",
            "review_status": "approved",
            "tracks": [
                {
                    "track_id": "track_001",
                    "track_type": " NARRATION ",
                    "clips": [{"clip_id": "clip_001"}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
        },
        output_target="preview_render",
        subtitle_file_uri=None,
    )

    assert "'track_type': 'narration'" in prompt
    assert "'track_type': ' NARRATION '" not in prompt


def test_review_guidance_builder_ignores_string_false_segment_review_required() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    assert builder._segments_needing_attention(
        [
            {
                "segment_id": "seg_001",
                "review_required": "false",
            },
            {
                "segment_id": "seg_002",
                "review_required": True,
            },
        ]
    ) == ["seg_002"]


def test_review_guidance_builder_trims_segment_ids_needing_attention_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [],
            "pending_recommendations": [],
            "segments": [
                {"segment_id": " seg_001 ", "review_required": True},
                {"segment_id": "seg_002", "review_required": False},
            ],
        }
    )

    assert "Segments needing attention: ['seg_001']" in prompt
    assert "Segments needing attention: [' seg_001 ']" not in prompt


def test_review_guidance_builder_canonicalizes_mixed_case_pending_recommendation_type_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_001",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "reason": "Select narration asset",
                }
            ],
            "segments": [],
        }
    )

    assert "'recommendation_type': 'tts_replacement'" in prompt
    assert "'recommendation_type': ' TTS_REPLACEMENT '" not in prompt


def test_review_guidance_builder_trims_pending_recommendation_target_segment_id_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_001",
                    "recommendation_type": "tts_replacement",
                    "target_segment_id": " seg_001 ",
                    "reason": "Select narration asset",
                }
            ],
            "segments": [],
        }
    )

    assert "'target_segment_id': 'seg_001'" in prompt
    assert "'target_segment_id': ' seg_001 '" not in prompt


def test_review_guidance_builder_canonicalizes_mixed_case_review_flag_code_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [
                {
                    "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                    "segment_id": "seg_001",
                }
            ],
            "pending_recommendations": [],
            "segments": [],
        }
    )

    assert "'code': 'tts_replacement_review_required'" in prompt
    assert "'code': ' TTS_REPLACEMENT_REVIEW_REQUIRED '" not in prompt


def test_review_guidance_builder_trims_review_flag_segment_id_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": " seg_001 ",
                }
            ],
            "pending_recommendations": [],
            "segments": [],
        }
    )

    assert "'segment_id': 'seg_001'" in prompt
    assert "'segment_id': ' seg_001 '" not in prompt


def test_review_guidance_builder_trims_review_flag_message_in_prompt() -> None:
    builder = LocalFirstReviewGuidanceBuilder(runtime_service=object())

    prompt = builder._build_prompt(
        review_snapshot={
            "review_status": "blocked",
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": " Operator review still required. ",
                }
            ],
            "pending_recommendations": [],
            "segments": [],
        }
    )

    assert "'message': 'Operator review still required.'" in prompt
    assert "'message': ' Operator review still required. '" not in prompt


def test_heuristic_review_guidance_builder_canonicalizes_mixed_case_approved_review_status() -> None:
    builder = HeuristicReviewGuidanceBuilder()

    guidance = builder.build(
        project_id="project_001",
        review_snapshot={
            "review_status": " APPROVED ",
            "review_flags": [],
            "pending_recommendations": [],
            "segments": [],
        },
    )

    assert guidance["summary"] == "Timeline review is approved and outputs can be generated."
    assert guidance["action_items"] == [
        "Generate subtitles, preview, or export from the approved timeline."
    ]


def test_local_pipeline_review_snapshot_reuses_persisted_guidance_for_mixed_case_approved_status(
    monkeypatch,
) -> None:
    persisted_guidance = {
        "summary": "Persisted approved guidance.",
        "action_items": ["Generate outputs from the approved timeline."],
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }

    class _FakeStore:
        def get_job(self, *, project_id: str, job_id: str) -> dict[str, object]:
            assert project_id == "project_001"
            assert job_id == "timeline_job_001"
            return {"job_id": job_id, "job_type": JobType.TIMELINE_BUILD.value, "output_ref": "timeline_001"}

        def list_segments(self, *, project_id: str) -> list[dict[str, object]]:
            assert project_id == "project_001"
            return []

        def build_review_snapshot(
            self,
            *,
            project_id: str,
            timeline_id: str,
            segments: list[dict[str, object]],
            timeline_applied_recommendations: list[dict[str, object]],
            timeline_pending_recommendations: list[dict[str, object]],
            timeline_review_flags: list[dict[str, object]],
        ) -> dict[str, object]:
            assert project_id == "project_001"
            assert timeline_id == "timeline_001"
            assert segments == []
            assert timeline_applied_recommendations == []
            assert timeline_pending_recommendations == []
            assert timeline_review_flags == []
            return {
                "project_id": project_id,
                "timeline_id": timeline_id,
                "review_status": "approved",
                "segments": [],
                "applied_recommendations": [],
                "pending_recommendations": [],
                "review_flags": [],
            }

        def get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, object]:
            assert project_id == "project_001"
            assert timeline_id == "timeline_001"
            return {"status": "approved"}

        def get_persisted_operator_guidance(
            self,
            *,
            project_id: str,
            timeline_id: str,
        ) -> dict[str, object]:
            assert project_id == "project_001"
            assert timeline_id == "timeline_001"
            return persisted_guidance

        def save_operator_guidance(
            self,
            *,
            project_id: str,
            timeline_id: str,
            operator_guidance: dict[str, object],
        ) -> None:
            raise AssertionError("Persisted guidance should have been reused without saving.")

    class _FailingGuidanceBuilder:
        def build(self, *, project_id: str, review_snapshot: dict[str, object]) -> dict[str, object]:
            del project_id, review_snapshot
            raise AssertionError("Persisted guidance should have been reused without rebuilding.")

    runner = LocalPipelineRunner(
        store=_FakeStore(),  # type: ignore[arg-type]
        review_guidance_builder=_FailingGuidanceBuilder(),  # type: ignore[arg-type]
    )

    monkeypatch.setattr(
        runner,
        "get_timeline_result",
        lambda *, project_id, job_id: {
            "job_id": job_id,
            "status": JobStatus.SUCCEEDED.value,
            "timeline": {
                "timeline_id": "timeline_001",
                "review_status": " APPROVED ",
                "applied_recommendations": [],
                "pending_recommendations": [],
                "review_flags": [],
            },
        },
    )

    snapshot = runner.get_review_snapshot(project_id="project_001", job_id="timeline_job_001")

    assert snapshot["review_status"] == " APPROVED "
    assert snapshot["operator_guidance"] == persisted_guidance


def test_store_save_recommendation_run_treats_string_false_review_required_as_false(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="String False Recommendation Store Project")

    run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Office skyline b-roll.",
                "auto_apply_allowed": True,
                "review_required": "false",
                "payload": {},
            }
        ],
    )

    persisted = run["recommendations"][0]
    recommendation_rows = store.list_recommendation_rows(project_id=project.project_id)

    assert persisted["review_required"] is False
    assert persisted["decision_state"] == "approved"
    assert recommendation_rows[0]["review_required"] is False
    assert recommendation_rows[0]["decision_state"] == "approved"


def test_store_save_recommendation_run_treats_string_false_auto_apply_allowed_as_false(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="String False Auto Apply Store Project")

    run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Office skyline b-roll.",
                "auto_apply_allowed": "false",
                "review_required": False,
                "payload": {},
            }
        ],
    )

    persisted = run["recommendations"][0]
    recommendation_rows = store.list_recommendation_rows(project_id=project.project_id)

    assert persisted["auto_apply_allowed"] is False
    assert persisted["decision_state"] == "pending"
    assert recommendation_rows[0]["auto_apply_allowed"] is False
    assert recommendation_rows[0]["decision_state"] == "pending"


def test_store_list_recommendation_rows_treats_legacy_string_false_columns_as_false(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy String False Recommendation Row Project")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                decision_state,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rec_legacy_false_row",
                project.project_id,
                "seg_001",
                RecommendationType.BROLL.value,
                "asset_broll_001",
                0.88,
                "Office skyline b-roll.",
                "false",
                "false",
                "approved",
                json.dumps({}, ensure_ascii=True),
                "2026-07-04T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    recommendation_rows = store.list_recommendation_rows(project_id=project.project_id)

    assert recommendation_rows[0]["auto_apply_allowed"] is False
    assert recommendation_rows[0]["review_required"] is False


def test_store_list_recommendation_rows_uses_trimmed_broll_type_for_default_provider_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Trimmed Broll Recommendation Row Trace Project")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                decision_state,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rec_trimmed_broll_trace_row",
                project.project_id,
                "seg_001",
                " broll ",
                "asset_broll_001",
                0.88,
                "Trimmed broll row should still use heuristic fallback trace.",
                1,
                0,
                "approved",
                json.dumps({}, ensure_ascii=True),
                "2026-07-04T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    recommendation_rows = store.list_recommendation_rows(project_id=project.project_id)

    assert recommendation_rows[0]["provider_trace"]["final_provider"] == "heuristic_fallback"


def test_store_build_review_snapshot_treats_legacy_string_false_recommendation_as_approved(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy String False Review Snapshot Project")

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=None,
        segments=[],
        recommendations=[
            {
                "recommendation_id": "rec_legacy_false_snapshot",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.BROLL.value,
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Legacy string false recommendation for review snapshot.",
                "auto_apply_allowed": "true",
                "review_required": "false",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert [item["recommendation_id"] for item in snapshot["applied_recommendations"]] == [
        "rec_legacy_false_snapshot"
    ]
    assert snapshot["pending_recommendations"] == []


def test_store_build_review_snapshot_splits_applied_and_pending_recommendations_without_inline_type(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Split Without Inline Type Project")
    store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.92,
                "reason": "Matched office overview keywords",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["office", "overview"]},
            },
            {
                "target_segment_id": "seg_002",
                "selected_asset_id": "asset_002",
                "score": 0.71,
                "reason": "Needs manual pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {"tags": ["team", "meeting"]},
            },
        ],
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id="timeline_001",
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview",
                "review_required": False,
                "cleanup_decision": "keep",
            },
            {
                "segment_id": "seg_002",
                "text": "Team meeting restart",
                "review_required": True,
                "cleanup_decision": "review",
            },
        ],
        recommendations=[
            {
                "recommendation_id": "rec_001",
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.92,
                "reason": "Matched office overview keywords",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["office", "overview"]},
            },
            {
                "recommendation_id": "rec_002",
                "target_segment_id": "seg_002",
                "selected_asset_id": "asset_002",
                "score": 0.71,
                "reason": "Needs manual pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {"tags": ["team", "meeting"]},
            },
        ],
        timeline_review_flags=[
            {"code": "segment_review_required", "segment_id": "seg_002", "message": "Needs review"},
            {"code": "broll_review_required", "segment_id": "seg_002", "message": "Needs manual pick"},
        ],
    )

    assert len(snapshot["applied_recommendations"]) == 1
    assert len(snapshot["pending_recommendations"]) == 1
    assert len(snapshot["review_flags"]) == 2
    assert snapshot["timeline_id"] == "timeline_001"


def test_store_build_review_snapshot_reclassifies_legacy_applied_like_timeline_pending_override(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Pending Override Legacy Applied Like Project")

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=None,
        segments=[],
        timeline_applied_recommendations=[],
        timeline_pending_recommendations=[
            {
                "recommendation_id": "rec_tts_legacy_applied_like",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.TTS_REPLACEMENT.value,
                "selected_asset_id": "asset_tts_001",
                "score": 1.0,
                "reason": "Legacy applied-like recommendation should not remain pending.",
                "auto_apply_allowed": "true",
                "review_required": "false",
                "decision_state": None,
                "payload": {
                    "selected_asset_uri": (
                        "local://projects/project_001/assets/generated/asset_tts_001.wav"
                    )
                },
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert [item["recommendation_id"] for item in snapshot["applied_recommendations"]] == [
        "rec_tts_legacy_applied_like"
    ]
    assert snapshot["pending_recommendations"] == []


def test_store_build_review_snapshot_reclassifies_legacy_pending_like_timeline_applied_override(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Applied Override Legacy Pending Like Project")

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=None,
        segments=[],
        timeline_applied_recommendations=[
            {
                "recommendation_id": "rec_tts_legacy_pending_like",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.TTS_REPLACEMENT.value,
                "selected_asset_id": "asset_tts_001",
                "score": 1.0,
                "reason": "Legacy pending-like recommendation should not remain applied.",
                "auto_apply_allowed": "false",
                "review_required": "true",
                "decision_state": None,
                "payload": {
                    "selected_asset_uri": (
                        "local://projects/project_001/assets/generated/asset_tts_001.wav"
                    )
                },
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_pending_recommendations=[],
        timeline_review_flags=[],
    )

    assert snapshot["applied_recommendations"] == []
    assert [item["recommendation_id"] for item in snapshot["pending_recommendations"]] == [
        "rec_tts_legacy_pending_like"
    ]


def test_store_build_review_snapshot_marks_status_blocked_when_pending_override_exists_despite_persisted_approved(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Persisted Approved Pending Override Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        segments=[],
        timeline_applied_recommendations=[],
        timeline_pending_recommendations=[
            {
                "recommendation_id": "rec_tts_pending_override",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.TTS_REPLACEMENT.value,
                "selected_asset_id": "asset_tts_001",
                "score": 1.0,
                "reason": "Pending override should force blocked review status.",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert snapshot["review_status"] == "blocked"


def test_store_build_review_snapshot_ignores_unknown_review_flag_for_status_when_persisted_approved(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Unknown Flag Approved Status Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        segments=[],
        timeline_applied_recommendations=[],
        timeline_pending_recommendations=[],
        timeline_review_flags=[
            {
                "code": "legacy_review_flag",
                "segment_id": "seg_001",
                "message": "Legacy metadata should not reopen review status.",
            }
        ],
    )

    assert snapshot["review_status"] == "approved"


def test_store_build_review_snapshot_ignores_unknown_pending_recommendation_for_status_when_persisted_approved(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Review Snapshot Unknown Pending Recommendation Approved Status Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        segments=[],
        timeline_applied_recommendations=[],
        timeline_pending_recommendations=[
            {
                "recommendation_id": "rec_stale_unknown_type",
                "target_segment_id": "seg_001",
                "recommendation_type": "legacy_overlay_pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert snapshot["review_status"] == "approved"


def test_store_build_review_snapshot_filters_unknown_pending_recommendation_from_surface(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Review Snapshot Unknown Pending Recommendation Surface Project"
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=None,
        segments=[],
        timeline_applied_recommendations=[],
        timeline_pending_recommendations=[
            {
                "recommendation_id": "rec_stale_unknown_type",
                "target_segment_id": "seg_001",
                "recommendation_type": "legacy_overlay_pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_review_flags=[],
    )

    assert snapshot["pending_recommendations"] == []


def test_store_build_review_snapshot_filters_unknown_applied_recommendation_from_surface(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Review Snapshot Unknown Applied Recommendation Surface Project"
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id=None,
        segments=[],
        timeline_applied_recommendations=[
            {
                "recommendation_id": "rec_unknown_applied_surface",
                "target_segment_id": "seg_001",
                "recommendation_type": "legacy_overlay_pick",
                "selected_asset_id": "asset_overlay_001",
                "score": 0.5,
                "reason": "Unknown stale recommendation should not remain on applied surface.",
                "auto_apply_allowed": True,
                "review_required": False,
                "decision_state": "approved",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        timeline_pending_recommendations=[],
        timeline_review_flags=[],
    )

    assert snapshot["applied_recommendations"] == []

def test_store_save_timeline_run_marks_misbucketed_applied_pending_like_recommendation_as_blocked(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Save Pending Like Applied Bucket Project")

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_legacy_pending_like",
                    "target_segment_id": "seg_001",
                    "recommendation_type": RecommendationType.TTS_REPLACEMENT.value,
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Pending-like recommendation leaked into applied bucket.",
                    "auto_apply_allowed": "false",
                    "review_required": "true",
                    "decision_state": None,
                    "payload": {},
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
        },
    )

    review_state = store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
    )

    assert review_state["status"] == "blocked"


def test_store_save_timeline_run_ignores_stale_nonlist_review_flags_when_setting_initial_status(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Save Stale Review Flags Initial Status Project")

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": "stale_review_flag_container",
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )

    review_state = store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
    )

    assert review_state["status"] == "draft"


def test_store_save_timeline_run_marks_mixed_case_review_flag_as_blocked_initial_status(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Save Mixed Case Review Flag Initial Status Project")

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [
                {
                    "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                    "segment_id": "seg_001",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )

    review_state = store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
    )

    assert review_state["status"] == "blocked"


def test_store_save_timeline_run_ignores_unknown_pending_recommendation_when_setting_initial_status(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Timeline Save Unknown Pending Recommendation Initial Status Project"
    )

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_unknown_type",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "legacy_overlay_pick",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-04T00:00:00+00:00",
                }
            ],
        },
    )

    review_state = store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
    )

    assert review_state["status"] == "draft"


def test_editing_session_api_normalizes_legacy_string_false_segment_review_required_from_store(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy String False Segment Editing Session Project")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO segments (
                segment_id,
                project_id,
                start_sec,
                end_sec,
                text,
                source_asset_id,
                confidence,
                cleanup_decision,
                review_required,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "seg_001",
                project.project_id,
                0.0,
                2.0,
                "Legacy string false segment row.",
                "asset_narration_001",
                0.99,
                "keep",
                "false",
                json.dumps({}, ensure_ascii=True),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "transcript_text": "Legacy string false segment row.",
                    "script_text": "Legacy string false segment row.",
                    "summary": "Legacy string false segment row.",
                    "keywords": ["legacy"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "legacy",
                    "narration_text": "Legacy string false segment row.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert response.status_code == 201
    assert response.json()["segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Legacy string false segment row.",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]


def test_editing_session_api_preserves_string_false_segment_review_required_after_segment_analysis_write(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="String False Segment Analysis Write Project")

    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Segment analysis stored string false.",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "confidence": 0.99,
                "review_required": "false",
                "cleanup_decision": "keep",
            }
        ],
    )

    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "transcript_text": "Segment analysis stored string false.",
                    "script_text": "Segment analysis stored string false.",
                    "summary": "Segment analysis stored string false.",
                    "keywords": ["segment"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "segment",
                    "narration_text": "Segment analysis stored string false.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert response.status_code == 201
    assert response.json()["segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Segment analysis stored string false.",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]


def test_timeline_api_normalizes_legacy_string_false_pending_recommendation_fields(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy String False Timeline Recommendation Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "transcript_text": "Legacy string false pending recommendation.",
                    "script_text": "Legacy string false pending recommendation.",
                    "summary": "Legacy string false pending recommendation.",
                    "keywords": ["legacy"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "legacy",
                    "narration_text": "Legacy string false pending recommendation.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_legacy_false_pending",
                    "target_segment_id": "seg_001",
                    "recommendation_type": RecommendationType.BROLL.value,
                    "selected_asset_id": "asset_broll_001",
                    "score": 0.88,
                    "reason": "Legacy string false pending recommendation.",
                    "auto_apply_allowed": "false",
                    "review_required": "false",
                    "decision_state": "pending",
                    "payload": {},
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
                }
            ],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")

    assert response.status_code == 200
    assert response.json()["timeline"]["pending_recommendations"] == [
        {
            "recommendation_id": "rec_legacy_false_pending",
            "target_segment_id": "seg_001",
            "recommendation_type": RecommendationType.BROLL.value,
            "selected_asset_id": "asset_broll_001",
            "score": 0.88,
            "reason": "Legacy string false pending recommendation.",
            "auto_apply_allowed": False,
            "review_required": False,
            "decision_state": "pending",
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
            "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
        }
    ]


def test_partial_regeneration_result_normalizes_legacy_string_false_pending_recommendation_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy String False Partial Regeneration Result Project")
    source_timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "transcript_text": "Legacy string false partial regeneration recommendation.",
                    "script_text": "Legacy string false partial regeneration recommendation.",
                    "summary": "Legacy string false partial regeneration recommendation.",
                    "keywords": ["legacy"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "legacy",
                    "narration_text": "Legacy string false partial regeneration recommendation.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    source_timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=source_timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=source_timeline["timeline_id"],
    )
    persisted_source_timeline = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=source_timeline["timeline_id"],
    )

    partial_timeline = {
        "timeline_id": "timeline_candidate_001",
        "project_id": project.project_id,
        "output_mode": "review",
        "version": "v001",
        "narration_source_uri": f"local://projects/{project.project_id}/assets/narration.wav",
        "tracks": persisted_source_timeline["tracks"],
        "segments": persisted_source_timeline["segments"],
        "review_flags": [],
        "applied_recommendations": [],
        "pending_recommendations": [
            {
                "recommendation_id": "rec_legacy_false_partial_pending",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.BROLL.value,
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Legacy string false partial regeneration recommendation.",
                "auto_apply_allowed": "false",
                "review_required": "false",
                "decision_state": "pending",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
                "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
            }
        ],
        "recommendation_decisions": {},
        "export_overlays": [],
        "review_status": "blocked",
    }
    partial_payload = store.save_partial_regeneration_run(
        project_id=project.project_id,
        payload={
            "source_timeline_id": source_timeline["timeline_id"],
            "timeline_id": partial_timeline["timeline_id"],
            "session_id": "session_001",
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
            "downstream_steps": ["caption_refresh", "timeline_build"],
            "regenerated_segments": [],
            "request": {"segment_ids": ["seg_001"], "fields": ["caption"]},
            "timeline": partial_timeline,
            "rerun_jobs": [],
        },
    )
    partial_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PARTIAL_REGENERATION,
        input_ref="session_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=partial_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=partial_payload["partial_regeneration_id"],
    )

    def fake_get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, object]:
        del self, project_id, timeline_id
        return {"status": "draft"}

    monkeypatch.setattr(LocalProjectStore, "get_review_state", fake_get_review_state)

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get(f"/api/projects/{project.project_id}/partial-regenerations/{partial_job['job_id']}")

    assert response.status_code == 200
    assert response.json()["timeline"]["pending_recommendations"] == [
        {
            "recommendation_id": "rec_legacy_false_partial_pending",
            "target_segment_id": "seg_001",
            "recommendation_type": RecommendationType.BROLL.value,
            "selected_asset_id": "asset_broll_001",
            "score": 0.88,
            "reason": "Legacy string false partial regeneration recommendation.",
            "auto_apply_allowed": False,
            "review_required": False,
            "decision_state": "pending",
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
            "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
        }
    ]


def test_partial_regeneration_result_fills_default_provider_trace_for_applied_recommendation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Applied Recommendation Default Trace Project")
    source_timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "transcript_text": "Applied recommendation default trace.",
                    "script_text": "Applied recommendation default trace.",
                    "summary": "Applied recommendation default trace.",
                    "keywords": ["applied"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "applied",
                    "narration_text": "Applied recommendation default trace.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    source_timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=source_timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=source_timeline["timeline_id"],
    )
    persisted_source_timeline = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=source_timeline["timeline_id"],
    )

    partial_timeline = {
        "timeline_id": "timeline_candidate_001",
        "project_id": project.project_id,
        "output_mode": "review",
        "version": "v001",
        "narration_source_uri": f"local://projects/{project.project_id}/assets/narration.wav",
        "tracks": persisted_source_timeline["tracks"],
        "segments": persisted_source_timeline["segments"],
        "review_flags": [],
        "applied_recommendations": [
            {
                "recommendation_id": "rec_applied_missing_trace",
                "target_segment_id": "seg_001",
                "recommendation_type": RecommendationType.BROLL.value,
                "selected_asset_id": "asset_broll_001",
                "score": 0.88,
                "reason": "Applied recommendation without provider trace.",
                "auto_apply_allowed": True,
                "review_required": False,
                "decision_state": "approved",
                "payload": {},
                "created_at": "2026-07-04T00:00:00+00:00",
            }
        ],
        "pending_recommendations": [],
        "recommendation_decisions": {},
        "export_overlays": [],
        "review_status": "approved",
    }
    partial_payload = store.save_partial_regeneration_run(
        project_id=project.project_id,
        payload={
            "source_timeline_id": source_timeline["timeline_id"],
            "timeline_id": partial_timeline["timeline_id"],
            "session_id": "session_001",
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
            "downstream_steps": ["caption_refresh", "timeline_build"],
            "regenerated_segments": [],
            "request": {"segment_ids": ["seg_001"], "fields": ["caption"]},
            "timeline": partial_timeline,
            "rerun_jobs": [],
        },
    )
    partial_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PARTIAL_REGENERATION,
        input_ref="session_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=partial_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=partial_payload["partial_regeneration_id"],
    )

    def fake_get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, object]:
        del self, project_id, timeline_id
        return {"status": "approved"}

    monkeypatch.setattr(LocalProjectStore, "get_review_state", fake_get_review_state)

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get(f"/api/projects/{project.project_id}/partial-regenerations/{partial_job['job_id']}")

    assert response.status_code == 200
    assert response.json()["timeline"]["applied_recommendations"] == [
        {
            "recommendation_id": "rec_applied_missing_trace",
            "target_segment_id": "seg_001",
            "recommendation_type": RecommendationType.BROLL.value,
            "selected_asset_id": "asset_broll_001",
            "score": 0.88,
            "reason": "Applied recommendation without provider trace.",
            "auto_apply_allowed": True,
            "review_required": False,
            "decision_state": "approved",
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
            "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
        }
    ]


def _single_segment_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Office overview.",
                confidence=0.99,
            )
        ],
        provider_name="mock_stt",
    )


def _risky_multi_segment_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview. Team meeting restart.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Office overview.",
                confidence=0.99,
            ),
            STTSegment(
                start_sec=1.0,
                end_sec=2.0,
                text="Team meeting restart.",
                confidence=0.72,
            ),
        ],
        provider_name="mock_stt",
    )


def _split_script_line_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview intro. Team update starts.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=0.8,
                text="Office over",
                confidence=0.98,
            ),
            STTSegment(
                start_sec=0.8,
                end_sec=1.6,
                text="view intro",
                confidence=0.97,
            ),
            STTSegment(
                start_sec=1.6,
                end_sec=3.0,
                text="Team update starts.",
                confidence=0.96,
            ),
        ],
        provider_name="mock_stt",
    )


def _coarse_multi_sentence_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview intro. Team update starts.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=3.0,
                text="Office overview intro. Team update starts.",
                confidence=0.98,
            ),
        ],
        provider_name="mock_stt",
    )


def _direction_mismatch_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Turn left now.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Turn left now.",
                confidence=0.99,
            ),
        ],
        provider_name="mock_stt",
    )


def _high_similarity_word_substitution_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Send the file today.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Send the file today.",
                confidence=0.99,
            ),
        ],
        provider_name="mock_stt",
    )


def _create_segment_analysis_project(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    source_audio = tmp_path / "segment-runtime.wav"
    source_script = tmp_path / "segment-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")

    project_id = client.post("/api/projects", json={"name": "AI Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    return project_id, script_asset_id, transcription_job_id


def _local_first_service_factory(
    *,
    local_provider: FakeStructuredProvider,
    gemini_provider: FakeStructuredProvider,
    local_enabled: bool = True,
):
    def factory(store: LocalProjectStore) -> LocalFirstRuntimeService:
        return LocalFirstRuntimeService(
            store=store,
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_config=LLMProviderConfig(provider_name="local_qwen", enabled=local_enabled),
            gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
            local_runtime_config=LocalOpenAICompatibleRuntimeConfig(
                enabled=local_enabled,
                base_url="http://127.0.0.1:11434/v1",
                model_name="Qwen3-32B",
                timeout_seconds=42,
            ),
        )

    return factory


def _create_broll_recommendation_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "broll-runtime.wav"
    source_script = tmp_path / "broll-runtime.txt"
    broll_asset = tmp_path / "skyline.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")
    broll_asset.write_bytes(b"video bytes")

    project_id = client.post("/api/projects", json={"name": "AI Broll Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]
    return project_id, segment_job_id


def _create_music_recommendation_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "music-runtime.wav"
    source_script = tmp_path / "music-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")

    project_id = client.post("/api/projects", json={"name": "AI Music Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]
    return project_id, segment_job_id


def _create_timeline_review_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "review-runtime.wav"
    source_script = tmp_path / "review-runtime.txt"
    broll_asset = tmp_path / "review-runtime.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")
    broll_asset.write_bytes(b"video bytes")

    project_id = client.post("/api/projects", json={"name": "AI Review Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]
    return project_id, timeline_job_id


def test_health_endpoint_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_app_exposes_local_runtime_builder_on_app_state(tmp_path: Path) -> None:
    config = LocalOpenAICompatibleRuntimeConfig(
        enabled=True,
        base_url="http://127.0.0.1:11434/v1/",
        model_name="Qwen3-32B",
        timeout_seconds=42,
    )

    app = create_app(projects_root=tmp_path, local_runtime_config=config)

    assert app.state.local_runtime_config.base_url == "http://127.0.0.1:11434/v1"
    assert app.state.local_runtime_config.model_name == "Qwen3-32B"
    assert callable(app.state.build_local_first_runtime_service)


def test_project_creation_endpoint_returns_local_storage_metadata(tmp_path) -> None:
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)

    response = client.post("/api/projects", json={"name": "Narration Draft"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Narration Draft"
    assert payload["root_storage_uri"].startswith("local://projects/")


def test_ingest_and_analysis_flow_persists_files_and_records(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Line one.\n\nLine two with restart.\n", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_response = client.post("/api/projects", json={"name": "Narration Draft"})
    project_id = project_response.json()["project_id"]

    narration_response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    )
    script_response = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    )

    assert narration_response.status_code == 201
    assert script_response.status_code == 201
    narration_asset_id = narration_response.json()["asset_id"]
    script_asset_id = script_response.json()["asset_id"]

    transcription_response = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    )
    assert transcription_response.status_code == 202
    transcription_job_id = transcription_response.json()["job_id"]

    transcription_result_response = client.get(
        f"/api/projects/{project_id}/jobs/transcription/{transcription_job_id}"
    )
    assert transcription_result_response.status_code == 200
    transcription_payload = transcription_result_response.json()
    assert transcription_payload["status"] == "succeeded"
    assert transcription_payload["transcript_uri"].startswith(
        f"local://projects/{project_id}/analysis/transcripts/"
    )

    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]

    segment_result_response = client.get(
        f"/api/projects/{project_id}/jobs/segment-analysis/{segment_job_id}"
    )
    assert segment_result_response.status_code == 200
    segment_payload = segment_result_response.json()
    assert segment_payload["status"] == "succeeded"
    assert len(segment_payload["segments"]) >= 2
    assert any(segment["review_required"] for segment in segment_payload["segments"])

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "inputs" / "narration" / source_audio.name).read_bytes() == b"fake wav data"
    assert (
        project_root / "inputs" / "scripts" / source_script.name
    ).read_text(encoding="utf-8") == "Line one.\n\nLine two with restart.\n"

    transcript_files = list((project_root / "analysis" / "transcripts").glob("*.json"))
    assert transcript_files
    transcript_payload = json.loads(transcript_files[0].read_text(encoding="utf-8"))
    assert transcript_payload["source_asset_id"] == narration_asset_id

    segment_files = list((project_root / "analysis" / "segments").glob("*.json"))
    assert segment_files
    persisted_segments = json.loads(segment_files[0].read_text(encoding="utf-8"))
    assert persisted_segments["script_asset_id"] == script_asset_id


def test_segment_analysis_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 1
    assert gemini_provider.calls == []


def test_segment_analysis_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    key_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Fallback Gemini",
            "api_key": "AIza-segment-fallback",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert key_response.status_code == 201

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 1
    assert len(gemini_provider.calls) == 1


def test_segment_analysis_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    key_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Disabled Local Gemini",
            "api_key": "AIza-segment-disabled",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert key_response.status_code == 201

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is False
    assert segment["cleanup_decision"] == "keep"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 1


def test_segment_analysis_endpoint_preserves_heuristic_fallback_when_local_disabled_without_gemini_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is False
    assert segment["cleanup_decision"] == "keep"


def test_segment_analysis_endpoint_marks_job_failed_on_unexpected_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(errors=[RuntimeError("segment analyzer exploded")])
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "segment analyzer exploded"
    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    assert jobs_response.status_code == 200
    segment_jobs = [
        job for job in jobs_response.json()["jobs"]
        if job["job_type"] == "segment_analysis"
    ]
    assert len(segment_jobs) == 1
    assert segment_jobs[0]["status"] == "failed"
    assert segment_jobs[0]["error_message"] == "segment analyzer exploded"
    assert len(local_provider.calls) == 1
    assert gemini_provider.calls == []


def test_segment_analysis_endpoint_uses_transcript_alignment_before_heuristic_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime.wav"
    source_script = tmp_path / "aligned-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro.\n\nTeam update starts.\n", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Aligned Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)
    assert all(segment["cleanup_decision"] == "keep" for segment in segments)


def test_segment_analysis_endpoint_flags_review_when_script_meaning_differs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _direction_mismatch_transcribe,
    )
    source_audio = tmp_path / "mismatch-runtime.wav"
    source_script = tmp_path / "mismatch-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Turn right now.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Mismatch Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["text"] == "Turn left now."
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"


def test_segment_analysis_endpoint_flags_review_for_high_similarity_word_substitution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _high_similarity_word_substitution_transcribe,
    )
    source_audio = tmp_path / "near-match-runtime.wav"
    source_script = tmp_path / "near-match-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Send the final today.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Near Match Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["text"] == "Send the file today."
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"


def test_segment_analysis_endpoint_aligns_single_line_multi_sentence_script_without_false_review_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-single-line.wav"
    source_script = tmp_path / "aligned-runtime-single-line.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro. Team update starts.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Aligned Single Line Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)
    assert all(segment["cleanup_decision"] == "keep" for segment in segments)


def test_segment_analysis_endpoint_preserves_transcript_when_script_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-no-script.wav"
    source_audio.write_bytes(b"fake wav data")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Missing Script Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": None,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office over",
        "view intro",
        "Team update starts.",
    ]


def test_segment_analysis_endpoint_keeps_spoken_words_when_script_is_only_partial_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-partial-script.wav"
    source_script = tmp_path / "aligned-runtime-partial-script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Partial Script Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office over view intro",
        "Team update starts.",
    ]


def test_segment_analysis_endpoint_splits_coarse_transcript_segment_for_multi_sentence_script(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _coarse_multi_sentence_transcribe,
    )
    source_audio = tmp_path / "coarse-runtime.wav"
    source_script = tmp_path / "coarse-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro. Team update starts.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Coarse Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)


def test_segment_analysis_endpoint_splits_coarse_transcript_segment_when_script_is_partial(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _coarse_multi_sentence_transcribe,
    )
    source_audio = tmp_path / "coarse-runtime-partial.wav"
    source_script = tmp_path / "coarse-runtime-partial.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Coarse Partial Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)


def test_segment_analysis_keeps_heuristic_review_flags_when_ai_downplays_risky_segment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _risky_multi_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert segments[0]["review_required"] is False
    assert segments[0]["cleanup_decision"] == "keep"
    assert segments[1]["review_required"] is True
    assert segments[1]["cleanup_decision"] == "review"


def test_segment_analysis_local_first_path_preserves_downstream_timeline_review_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Review the flagged narration segment before export.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Review the flagged narration segment before export.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    broll_asset = tmp_path / "segment-downstream.mp4"
    broll_asset.write_bytes(b"video bytes")
    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    assert asset_response.status_code == 201

    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    assert any(flag["code"] == "segment_review_required" for flag in review_snapshot.json()["review_flags"])
    assert len(local_provider.calls) >= 2


def test_recommendation_flow_persists_broll_and_music_results(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    broll_team = tmp_path / "team-meeting.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")
    broll_team.write_bytes(b"video bytes 2")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Recommendation Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    city_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )
    team_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_team),
            "title": "Team meeting",
            "tags": ["team", "meeting", "collaboration"],
        },
    )
    assert city_asset.status_code == 201
    assert team_asset.status_code == 201

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]

    broll_job = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    music_job = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    assert broll_job.status_code == 202
    assert music_job.status_code == 202

    broll_result = client.get(
        f"/api/projects/{project_id}/jobs/broll-recommendation/{broll_job.json()['job_id']}"
    )
    music_result = client.get(
        f"/api/projects/{project_id}/jobs/music-recommendation/{music_job.json()['job_id']}"
    )
    assert broll_result.status_code == 200
    assert music_result.status_code == 200

    broll_payload = broll_result.json()
    music_payload = music_result.json()
    assert broll_payload["status"] == "succeeded"
    assert music_payload["status"] == "succeeded"
    assert len(broll_payload["recommendations"]) >= 2
    assert len(music_payload["recommendations"]) >= 2
    assert all("score" in item for item in broll_payload["recommendations"])
    assert all("reason" in item for item in broll_payload["recommendations"])
    assert all(item["auto_apply_allowed"] is True for item in broll_payload["recommendations"])
    assert all(item["review_required"] is False for item in broll_payload["recommendations"])

    project_root = tmp_path / "projects" / project_id
    recommendation_files = list((project_root / "analysis" / "recommendations").glob("*.json"))
    assert len(recommendation_files) >= 2
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in recommendation_files
    ]
    recommendation_types = {payload["recommendation_type"] for payload in payloads}
    assert {"broll", "bgm"}.issubset(recommendation_types)


def test_music_recommendation_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "cinematic pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: cinematic pulse."
    assert recommendation["score"] == 0.91
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 2
    assert local_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION
    assert gemini_provider.calls == []


def test_music_recommendation_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "warm ambient", "score": 0.83},
                raw_text='{"music_mood":"warm ambient","score":0.83}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-music-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_music_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "warm ambient"
    assert recommendation["score"] == 0.83
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 2
    assert len(gemini_provider.calls) == 2
    assert gemini_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_music_recommendation_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Disabled Local Gemini",
        "api_key": "AIza-music-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_music_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "steady documentary"
    assert recommendation["score"] == 0.78
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 2
    assert gemini_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION


def test_music_recommendation_endpoint_preserves_rule_based_fallback_when_local_disabled_without_gemini_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "clean documentary pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: clean documentary pulse."
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "rule_based_fallback",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }


def test_music_recommendation_endpoint_preserves_rule_based_path_after_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "clean documentary pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: clean documentary pulse."


def test_music_recommendation_local_first_path_preserves_downstream_timeline_behavior(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    broll_asset = tmp_path / "music-downstream.mp4"
    broll_asset.write_bytes(b"video bytes")
    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    assert asset_response.status_code == 201

    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    music_result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{music_job_id}")

    assert timeline_result.status_code == 200
    assert music_result.status_code == 200
    assert any(track["track_type"] == "bgm" for track in timeline_result.json()["timeline"]["tracks"])
    assert music_result.json()["recommendations"][0]["payload"]["music_mood"] == "cinematic pulse"
    assert len(local_provider.calls) == 3


def test_broll_recommendation_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_broll_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    payload = result.json()
    assert payload["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert payload["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 2
    assert gemini_provider.calls == []


def test_broll_recommendation_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-test-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_broll_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 2
    assert len(gemini_provider.calls) == 2


def test_broll_recommendation_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-test-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_broll_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 2


def test_broll_recommendation_endpoint_preserves_heuristic_path_after_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_broll_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }


def test_timeline_and_review_snapshot_flow(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Timeline Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    timeline_response = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    )
    assert timeline_response.status_code == 202
    timeline_job_id = timeline_response.json()["job_id"]

    timeline_result = client.get(
        f"/api/projects/{project_id}/timelines/{timeline_job_id}"
    )
    review_snapshot = client.get(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}"
    )
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200

    timeline_payload = timeline_result.json()
    review_payload = review_snapshot.json()
    assert timeline_payload["status"] == "succeeded"
    assert timeline_payload["job_id"].startswith("timeline_build_job_")
    assert timeline_payload["timeline"]["project_id"] == project_id
    assert len(timeline_payload["timeline"]["tracks"]) >= 1
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_payload["timeline"]["tracks"]}
    )
    assert len(review_payload["segments"]) >= 2
    assert len(review_payload["applied_recommendations"]) >= 2
    assert len(review_payload["pending_recommendations"]) == 0
    assert any(flag["code"] == "segment_review_required" for flag in review_payload["review_flags"])
    assert review_payload["timeline_id"] == timeline_payload["timeline"]["timeline_id"]

    project_root = tmp_path / "projects" / project_id
    timeline_files = list((project_root / "timelines").glob("timeline_*.json"))
    assert timeline_files
    timeline_json = json.loads(timeline_files[0].read_text(encoding="utf-8"))
    assert timeline_json["project_id"] == project_id
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_json["tracks"]}
    )


def test_review_snapshot_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Review the flagged narration segment before export.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Review the flagged narration segment before export.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Review the flagged narration segment before export."
    assert payload["operator_guidance"]["action_items"] == ["Check seg_001 narration alignment"]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 4
    assert local_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls == []


def test_review_snapshot_persists_operator_guidance_for_repeated_reads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Persisted local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Persisted local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    second_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert first_review_snapshot.status_code == 200
    assert second_review_snapshot.status_code == 200
    first_payload = first_review_snapshot.json()
    second_payload = second_review_snapshot.json()
    assert first_payload["operator_guidance"]["summary"] == "Persisted local review summary."
    assert second_payload["operator_guidance"] == first_payload["operator_guidance"]
    assert len(local_provider.calls) == 4


def test_review_snapshot_fills_default_provider_trace_for_persisted_operator_guidance(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Persisted Guidance Default Trace Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Persisted review guidance without provider trace.",
                    "script_text": "Persisted review guidance without provider trace.",
                    "summary": "Persisted review guidance without provider trace.",
                    "keywords": ["guidance"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "guidance",
                    "narration_text": "Persisted review guidance without provider trace.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="draft",
    )
    store.save_operator_guidance(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        operator_guidance={
            "summary": "Persisted legacy guidance without trace.",
            "action_items": ["Review the current draft before output."],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    review_snapshot = client.get(f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"] == {
        "summary": "Persisted legacy guidance without trace.",
        "action_items": ["Review the current draft before output."],
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }


def test_review_snapshot_invalidates_persisted_guidance_when_review_status_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Draft review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Draft review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    second_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert first_review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert second_review_snapshot.status_code == 200
    assert first_review_snapshot.json()["operator_guidance"]["summary"] == "Draft review summary."
    assert second_review_snapshot.json()["review_status"] == "approved"
    assert second_review_snapshot.json()["operator_guidance"]["summary"] == (
        "Timeline review is approved and outputs can be generated."
    )
    assert second_review_snapshot.json()["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_review_snapshot_ignores_persisted_approved_guidance_when_synthetic_segment_blocker_makes_status_blocked(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Synthetic Segment Blocker Guidance Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Operator cleanup still required.",
                    "script_text": "Operator cleanup still required.",
                    "summary": "Segment still requires review.",
                    "keywords": ["operator", "review"],
                    "visual_plan": "Review before output.",
                    "broll_query": "operator review",
                    "narration_text": "Operator cleanup still required.",
                    "review_required": True,
                    "cleanup_decision": "review",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    store.save_operator_guidance(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        operator_guidance={
            "summary": "Timeline review is approved and outputs can be generated.",
            "action_items": ["Generate subtitles, preview, or export from the approved timeline."],
            "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    review_snapshot = client.get(f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["review_status"] == "blocked"
    assert payload["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_001",
            "message": "Segment requires operator review before export.",
        }
    ]
    assert payload["operator_guidance"]["summary"] != (
        "Timeline review is approved and outputs can be generated."
    )
    assert payload["operator_guidance"]["action_items"] != [
        "Generate subtitles, preview, or export from the approved timeline."
    ]


def test_review_snapshot_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini fallback review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Gemini fallback review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-review-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Gemini fallback review summary."
    assert payload["operator_guidance"]["action_items"] == ["Resolve flagged review items"]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 4
    assert len(gemini_provider.calls) == 4
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_review_snapshot_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Disabled local review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Disabled Local Gemini",
        "api_key": "AIza-review-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Disabled local review summary."
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 4
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY


def test_review_snapshot_preserves_blocking_behavior_when_ai_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["review_status"] == "draft"
    assert payload["operator_guidance"]["summary"].lower().startswith("timeline is ready for approval")
    assert preview_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()


def test_review_snapshot_falls_back_to_heuristic_guidance_on_unexpected_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"].lower().startswith("review is blocked")
    assert payload["operator_guidance"]["action_items"] == ["Segment requires operator review before export."]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_preview_and_export_use_operator_copy_runtime_in_production_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Preview operator copy from local runtime.",
                    "action_items": ["Check caption timing in the playable preview."],
                },
                raw_text='{"summary":"Preview operator copy from local runtime.","action_items":["Check caption timing in the playable preview."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Export operator copy from local runtime.",
                    "action_items": ["Open the CapCut payload and confirm subtitle attachment."],
                },
                raw_text='{"summary":"Export operator copy from local runtime.","action_items":["Open the CapCut payload and confirm subtitle attachment."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202
    assert len(local_provider.calls) == 5
    assert local_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert local_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY
    assert "preview" in local_provider.calls[3].prompt.lower()
    assert "capcut" in local_provider.calls[4].prompt.lower()


def test_preview_and_export_return_ai_backed_operator_copy_on_local_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Preview operator copy from local runtime.",
                    "action_items": ["Check caption timing in the playable preview."],
                },
                raw_text='{"summary":"Preview operator copy from local runtime.","action_items":["Check caption timing in the playable preview."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Export operator copy from local runtime.",
                    "action_items": ["Open the CapCut payload and confirm subtitle attachment."],
                },
                raw_text='{"summary":"Export operator copy from local runtime.","action_items":["Open the CapCut payload and confirm subtitle attachment."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"] == [
        "Preview operator copy from local runtime.",
        "Check caption timing in the playable preview.",
    ]
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert export_result.json()["export"]["notes"] == [
        "Export operator copy from local runtime.",
        "Open the CapCut payload and confirm subtitle attachment.",
        "CapCut remains an export target, not the internal source of truth.",
    ]
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }


def test_preview_and_export_fall_back_to_gemini_operator_copy_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Review the playable preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Review the playable preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the CapCut export package before delivery."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the CapCut export package before delivery."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Output Fallback Gemini",
        "api_key": "AIza-output-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"] == [
        "Gemini preview operator copy.",
        "Review the playable preview before handoff.",
    ]
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert export_result.json()["export"]["notes"] == [
        "Gemini export operator copy.",
        "Validate the CapCut export package before delivery.",
        "CapCut remains an export target, not the internal source of truth.",
    ]
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 5
    assert len(gemini_provider.calls) == 5
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_preview_and_export_skip_local_operator_copy_when_local_runtime_is_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local preview operator copy.",
                    "action_items": ["Review the preview in Gemini fallback mode."],
                },
                raw_text='{"summary":"Disabled local preview operator copy.","action_items":["Review the preview in Gemini fallback mode."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local export operator copy.",
                    "action_items": ["Review the export in Gemini fallback mode."],
                },
                raw_text='{"summary":"Disabled local export operator copy.","action_items":["Review the export in Gemini fallback mode."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(),
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Output Disabled Gemini",
        "api_key": "AIza-output-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"][0] == "Disabled local preview operator copy."
    assert export_result.json()["export"]["notes"][0] == "Disabled local export operator copy."
    assert export_result.json()["export"]["notes"][-1] == "CapCut remains an export target, not the internal source of truth."
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert len(gemini_provider.calls) == 5
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY


def test_preview_and_export_gating_blocks_before_operator_copy_runtime_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert len(local_provider.calls) == 3


def test_project_listing_and_job_feed_support_dashboard(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Dashboard Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    projects_response = client.get("/api/projects")
    project_response = client.get(f"/api/projects/{project_id}")
    jobs_response = client.get(f"/api/projects/{project_id}/jobs")

    assert projects_response.status_code == 200
    assert project_response.status_code == 200
    assert jobs_response.status_code == 200

    projects_payload = projects_response.json()
    project_payload = project_response.json()
    jobs_payload = jobs_response.json()

    assert any(project["project_id"] == project_id for project in projects_payload["projects"])
    assert project_payload["project_id"] == project_id
    assert project_payload["name"] == "Dashboard Draft"
    assert any(job["job_id"] == timeline_job_id for job in jobs_payload["jobs"])
    assert any(job["job_type"] == "timeline_build" for job in jobs_payload["jobs"])


def test_preview_and_capcut_export_flow_persist_outputs_and_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Output Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]
    approve_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    assert approve_response.status_code == 202

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_job_id = preview_response.json()["job_id"]
    export_job_id = export_response.json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200

    preview_payload = preview_result.json()
    export_payload = export_result.json()
    assert preview_payload["status"] == "succeeded"
    assert preview_payload["preview"]["timeline_id"] == "timeline_001"
    assert preview_payload["preview"]["artifact_kind"] == "playable_html_preview"
    assert preview_payload["preview"]["player_uri"].endswith(".html")
    assert export_payload["status"] == "succeeded"
    assert export_payload["export"]["timeline_id"] == "timeline_001"
    assert export_payload["export"]["export_type"] == "capcut"
    assert export_payload["export"]["adapter"] == "capcut_v1_port"
    assert export_payload["export"]["notes"][0].lower().startswith("capcut export manifest")
    assert export_payload["export"]["capcut_tracks"][0]["segments"][0]["source_uri"].endswith("/inputs/narration/source-narration.wav")

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "previews" / "preview_001.json").exists()
    assert (
        project_root / "exports" / "capcut" / "export_001" / "capcut_payload.json"
    ).exists()


def test_preview_and_capcut_export_require_review_clearance(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Review Gate Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert "review" in preview_response.json()["detail"].lower()
    assert "review" in export_response.json()["detail"].lower()

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))


def test_preview_and_export_surface_pending_tts_replacement_blocker_before_approval(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Pending TTS Blocker Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "tts_replacement" in preview_response.json()["detail"]
    assert "rec_tts_seg_001" in preview_response.json()["detail"]
    assert "tts_replacement" in export_response.json()["detail"]
    assert "rec_tts_seg_001" in export_response.json()["detail"]
    assert "tts_replacement" in subtitle_response.json()["detail"]
    assert "rec_tts_seg_001" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project.project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project.project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_output_jobs_ignore_stale_truthy_blocker_shapes_on_approved_timeline(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_response = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_response.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["review_flags"] = "stale_review_flag_container"
    persisted_timeline["pending_recommendations"] = ["stale_entry"]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    store = LocalProjectStore(tmp_path)
    store.save_review_state(
        project_id=project_id,
        timeline_id=str(timeline_payload["timeline_id"]),
        status="approved",
    )

    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_result = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_response.json()['job_id']}")
    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_response.json()['job_id']}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_response.json()['job_id']}")

    assert subtitle_result.status_code == 200
    assert preview_result.status_code == 200
    assert export_result.status_code == 200


def test_reopening_approved_review_ignores_stale_truthy_blocker_shapes_and_returns_draft(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_response = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_response.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["review_flags"] = "stale_review_flag_container"
    persisted_timeline["pending_recommendations"] = ["stale_entry"]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    store = LocalProjectStore(tmp_path)
    store.save_review_state(
        project_id=project_id,
        timeline_id=str(timeline_payload["timeline_id"]),
        status="approved",
    )

    reopen_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/reopen")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert reopen_response.status_code == 202
    assert reopen_response.json()["review_status"] == "draft"
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()
    assert "approval" in export_response.json()["detail"].lower()
    assert "approval" in subtitle_response.json()["detail"].lower()


def test_timeline_and_review_snapshot_read_paths_normalize_stale_truthy_blocker_shapes_after_reopen(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_response = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_response.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["review_flags"] = "stale_review_flag_container"
    persisted_timeline["pending_recommendations"] = ["stale_entry"]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    store = LocalProjectStore(tmp_path)
    store.save_review_state(
        project_id=project_id,
        timeline_id=str(timeline_payload["timeline_id"]),
        status="approved",
    )

    reopen_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/reopen")

    assert reopen_response.status_code == 202
    assert reopen_response.json()["review_status"] == "draft"

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    refreshed_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert refreshed_timeline.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "draft"
    assert refreshed_timeline.json()["timeline"]["review_flags"] == []
    assert refreshed_timeline.json()["timeline"]["pending_recommendations"] == []

    assert refreshed_snapshot.status_code == 200
    assert refreshed_snapshot.json()["review_status"] == "draft"
    assert refreshed_snapshot.json()["review_flags"] == []
    assert refreshed_snapshot.json()["pending_recommendations"] == []


def test_approved_review_state_still_blocks_outputs_when_timeline_has_residual_review_blockers(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Residual Blocker Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "review blockers" in preview_response.json()["detail"].lower()
    assert "review blockers" in export_response.json()["detail"].lower()
    assert "review blockers" in subtitle_response.json()["detail"].lower()
    assert "tts_replacement" in preview_response.json()["detail"]
    assert "rec_tts_seg_001" in preview_response.json()["detail"]
    assert "tts_replacement" in export_response.json()["detail"]
    assert "rec_tts_seg_001" in export_response.json()["detail"]
    assert "tts_replacement" in subtitle_response.json()["detail"]
    assert "rec_tts_seg_001" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project.project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project.project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_approved_review_state_still_blocks_outputs_when_only_review_flags_remain(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Review Flag Only Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "review blockers" in preview_response.json()["detail"].lower()
    assert "review blockers" in export_response.json()["detail"].lower()
    assert "review blockers" in subtitle_response.json()["detail"].lower()
    assert "tts_replacement_review_required@seg_001" in preview_response.json()["detail"]
    assert "tts_replacement_review_required@seg_001" in export_response.json()["detail"]
    assert "tts_replacement_review_required@seg_001" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project.project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project.project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_output_gating_blocks_mixed_case_review_flag_code_on_approved_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Mixed Case Review Flag Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert "tts_replacement_review_required@seg_001" in preview_response.json()["detail"]


def test_output_jobs_ignore_unknown_dict_shaped_review_flag_on_approved_timeline(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Unknown Review Flag Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "legacy_review_flag",
                    "segment_id": "seg_001",
                    "message": "Legacy metadata that should not block output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_result = client.get(
        f"/api/projects/{project.project_id}/subtitles/{subtitle_response.json()['job_id']}"
    )
    preview_result = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    )
    export_result = client.get(
        f"/api/projects/{project.project_id}/exports/{export_response.json()['job_id']}"
    )
    timeline_result = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")
    review_snapshot = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}"
    )

    assert subtitle_result.status_code == 200
    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200
    assert timeline_result.json()["timeline"]["review_status"] == "approved"
    assert review_snapshot.json()["review_status"] == "approved"
    assert timeline_result.json()["timeline"]["review_flags"] == [
        {
            "code": "legacy_review_flag",
            "segment_id": "seg_001",
            "message": "Legacy metadata that should not block output.",
        }
    ]
    assert review_snapshot.json()["review_flags"] == [
        {
            "code": "legacy_review_flag",
            "segment_id": "seg_001",
            "message": "Legacy metadata that should not block output.",
        }
    ]


def test_output_jobs_ignore_stale_non_bool_segment_review_required_on_approved_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Stale Review Required Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Legacy stale review required shape.",
                    "script_text": "Legacy stale review required shape.",
                    "summary": "Legacy stale review required shape.",
                    "keywords": ["legacy"],
                    "visual_plan": "Keep current visuals.",
                    "broll_query": "legacy",
                    "narration_text": "Legacy stale review required shape.",
                    "review_required": {"legacy": "stale_review_required_container"},
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_result = client.get(
        f"/api/projects/{project.project_id}/subtitles/{subtitle_response.json()['job_id']}"
    )
    preview_result = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    )
    export_result = client.get(
        f"/api/projects/{project.project_id}/exports/{export_response.json()['job_id']}"
    )
    timeline_result = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")
    review_snapshot = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}"
    )

    assert subtitle_result.status_code == 200
    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200
    assert timeline_result.json()["timeline"]["review_status"] == "approved"
    assert review_snapshot.json()["review_status"] == "approved"
    assert timeline_result.json()["timeline"]["review_flags"] == []
    assert review_snapshot.json()["review_flags"] == []


def test_output_jobs_ignore_approved_decision_state_entries_left_in_pending_recommendations(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Stale Pending Decision Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Already approved recommendation leaked into pending recommendations.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_001.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_result = client.get(
        f"/api/projects/{project.project_id}/subtitles/{subtitle_response.json()['job_id']}"
    )
    preview_result = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    )
    export_result = client.get(
        f"/api/projects/{project.project_id}/exports/{export_response.json()['job_id']}"
    )
    timeline_result = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")
    review_snapshot = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}"
    )

    assert subtitle_result.status_code == 200
    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200
    assert timeline_result.json()["timeline"]["review_status"] == "approved"
    assert review_snapshot.json()["review_status"] == "approved"
    assert timeline_result.json()["timeline"]["pending_recommendations"] == []
    assert review_snapshot.json()["pending_recommendations"] == []


def test_output_jobs_ignore_legacy_applied_like_entries_left_in_pending_recommendations(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Applied Like Pending Recommendation Output Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Legacy applied-like recommendation leaked into pending recommendations.",
                    "auto_apply_allowed": "true",
                    "review_required": "false",
                    "decision_state": None,
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_001.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202


def test_review_snapshot_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Applied Bucket Pending Like Review Snapshot Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Pending-like recommendation leaked into applied recommendations.",
                    "auto_apply_allowed": "false",
                    "review_required": "true",
                    "decision_state": None,
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_001.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get(f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "blocked"
    assert payload["applied_recommendations"] == []
    assert [item["recommendation_id"] for item in payload["pending_recommendations"]] == [
        "rec_tts_seg_001"
    ]


def test_timeline_api_reclassifies_pending_like_entry_misbucketed_into_applied_recommendations(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Applied Bucket Pending Like Timeline API Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Pending-like recommendation leaked into applied recommendations.",
                    "auto_apply_allowed": "false",
                    "review_required": "true",
                    "decision_state": None,
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_001.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")

    assert response.status_code == 200
    payload = response.json()["timeline"]
    assert payload["review_status"] == "blocked"
    assert payload["applied_recommendations"] == []
    assert [item["recommendation_id"] for item in payload["pending_recommendations"]] == [
        "rec_tts_seg_001"
    ]


def test_timeline_api_filters_unknown_type_entry_misbucketed_into_applied_recommendations(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline API Unknown Applied Recommendation Surface Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_unknown_applied_surface",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "legacy_overlay_pick",
                    "selected_asset_id": "asset_overlay_001",
                    "score": 0.5,
                    "reason": "Unknown stale recommendation should not remain on applied surface.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {},
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")

    assert response.status_code == 200
    payload = response.json()["timeline"]
    assert payload["review_status"] == "approved"
    assert payload["applied_recommendations"] == []


def test_approved_review_state_still_blocks_outputs_when_only_pending_recommendations_remain(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Pending Only Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "review blockers" in preview_response.json()["detail"].lower()
    assert "review blockers" in export_response.json()["detail"].lower()
    assert "review blockers" in subtitle_response.json()["detail"].lower()
    assert "tts_replacement:rec_tts_seg_001@seg_001" in preview_response.json()["detail"]
    assert "tts_replacement:rec_tts_seg_001@seg_001" in export_response.json()["detail"]
    assert "tts_replacement:rec_tts_seg_001@seg_001" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project.project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project.project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_preview_export_and_subtitles_require_explicit_approval_even_without_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Approval Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    assert review_snapshot.status_code == 200
    assert review_snapshot.json()["pending_recommendations"] == []
    assert review_snapshot.json()["review_flags"] == []

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()
    assert "approval" in export_response.json()["detail"].lower()
    assert "approval" in subtitle_response.json()["detail"].lower()

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_preview_render_accepts_mixed_case_review_approval_state_without_blockers(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Mixed Case Review Approval Output Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "narration_source_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO review_approvals (
                timeline_id,
                project_id,
                status,
                approved_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                timeline["timeline_id"],
                project.project_id,
                " APPROVED ",
                "2026-07-04T00:00:00+00:00",
                "2026-07-04T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 202
    preview_result = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    )
    assert preview_result.status_code == 200
    assert preview_result.json()["status"] == "succeeded"


def test_approved_review_state_still_blocks_outputs_when_segment_review_required_remains_without_snapshot_blockers(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved State Segment Review Required Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Operator cleanup still required.",
                    "script_text": "Operator cleanup still required.",
                    "summary": "Segment still requires review.",
                    "keywords": ["operator", "review"],
                    "visual_plan": "Review before output.",
                    "broll_query": "operator review",
                    "narration_text": "Operator cleanup still required.",
                    "review_required": True,
                    "cleanup_decision": "review",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "review blockers" in preview_response.json()["detail"].lower()
    assert "review blockers" in export_response.json()["detail"].lower()
    assert "review blockers" in subtitle_response.json()["detail"].lower()
    assert "segment_review_required@seg_001" in preview_response.json()["detail"]
    assert "segment_review_required@seg_001" in export_response.json()["detail"]
    assert "segment_review_required@seg_001" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project.project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    refreshed_timeline = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")
    refreshed_snapshot = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}"
    )
    assert refreshed_timeline.status_code == 200
    assert refreshed_snapshot.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "blocked"
    assert refreshed_snapshot.json()["review_status"] == "blocked"
    assert refreshed_timeline.json()["timeline"]["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_001",
            "message": "Segment requires operator review before export.",
        }
    ]
    assert refreshed_snapshot.json()["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_001",
            "message": "Segment requires operator review before export.",
        }
    ]
    assert refreshed_timeline.json()["timeline"]["pending_recommendations"] == []
    assert refreshed_snapshot.json()["pending_recommendations"] == []

    project_root = tmp_path / "projects" / project.project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_review_snapshot_api_can_approve_pending_recommendation(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["pending_recommendations"] == []
    assert payload["review_flags"] == []
    assert payload["applied_recommendations"][0]["recommendation_id"] == "rec_broll_review_002"

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["pending_recommendations"] == []
    assert refreshed_timeline_payload["review_flags"] == []
    assert refreshed_timeline_payload["applied_recommendations"][0]["recommendation_id"] == (
        "rec_broll_review_002"
    )


def test_approving_last_pending_recommendation_keeps_review_blocked_when_segment_review_required_remains(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline["segments"] = [
        {
            "segment_id": "seg_001",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "transcript_text": "Intro segment.",
            "script_text": "Intro segment.",
            "summary": "Intro segment.",
            "keywords": ["intro"],
            "visual_plan": "Keep current visuals.",
            "broll_query": "intro",
            "narration_text": "Intro segment.",
            "review_required": False,
            "cleanup_decision": "keep",
        },
        {
            "segment_id": "seg_002",
            "start_sec": 2.0,
            "end_sec": 4.0,
            "transcript_text": "Needs operator review.",
            "script_text": "Needs operator review.",
            "summary": "Needs operator review.",
            "keywords": ["review"],
            "visual_plan": "Review before output.",
            "broll_query": "review",
            "narration_text": "Needs operator review.",
            "review_required": True,
            "cleanup_decision": "review",
        },
    ]
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "blocked"
    assert payload["pending_recommendations"] == []
    assert payload["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_002",
            "message": "Segment requires operator review before export.",
        }
    ]

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    refreshed_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    assert refreshed_snapshot.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "blocked"
    assert refreshed_timeline.json()["timeline"]["pending_recommendations"] == []
    assert refreshed_timeline.json()["timeline"]["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_002",
            "message": "Segment requires operator review before export.",
        }
    ]
    assert refreshed_snapshot.json()["review_status"] == "blocked"
    assert refreshed_snapshot.json()["pending_recommendations"] == []
    assert refreshed_snapshot.json()["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_002",
            "message": "Segment requires operator review before export.",
        }
    ]


def test_approving_last_pending_recommendation_keeps_outputs_blocked_by_remaining_segment_review_required(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["segments"] = [
        {
            "segment_id": "seg_001",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "transcript_text": "Intro segment.",
            "script_text": "Intro segment.",
            "summary": "Intro segment.",
            "keywords": ["intro"],
            "visual_plan": "Keep current visuals.",
            "broll_query": "intro",
            "narration_text": "Intro segment.",
            "review_required": False,
            "cleanup_decision": "keep",
        },
        {
            "segment_id": "seg_002",
            "start_sec": 2.0,
            "end_sec": 4.0,
            "transcript_text": "Needs operator review.",
            "script_text": "Needs operator review.",
            "summary": "Needs operator review.",
            "keywords": ["review"],
            "visual_plan": "Review before output.",
            "broll_query": "review",
            "narration_text": "Needs operator review.",
            "review_required": True,
            "cleanup_decision": "review",
        },
    ]
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "blocked"
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "segment_review_required@seg_002" in preview_response.json()["detail"]
    assert "segment_review_required@seg_002" in export_response.json()["detail"]
    assert "segment_review_required@seg_002" in subtitle_response.json()["detail"]


def test_output_blocker_synthesis_deduplicates_repeated_segment_review_required_entries(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Segment Review Required Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Duplicate review segment first copy.",
                    "script_text": "Duplicate review segment first copy.",
                    "summary": "First copy.",
                    "keywords": ["duplicate"],
                    "visual_plan": "Review before output.",
                    "broll_query": "duplicate",
                    "narration_text": "Duplicate review segment first copy.",
                    "review_required": True,
                    "cleanup_decision": "review",
                },
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Duplicate review segment second copy.",
                    "script_text": "Duplicate review segment second copy.",
                    "summary": "Second copy.",
                    "keywords": ["duplicate"],
                    "visual_plan": "Review before output.",
                    "broll_query": "duplicate",
                    "narration_text": "Duplicate review segment second copy.",
                    "review_required": True,
                    "cleanup_decision": "review",
                },
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert preview_response.json()["detail"].count("segment_review_required@seg_001") == 1


def test_output_blockers_deduplicate_repeated_persisted_review_flag_entries(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Persisted Review Flag Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Duplicate persisted review flag segment.",
                    "script_text": "Duplicate persisted review flag segment.",
                    "summary": "Duplicate review flag.",
                    "keywords": ["duplicate"],
                    "visual_plan": "Review before output.",
                    "broll_query": "duplicate",
                    "narration_text": "Duplicate persisted review flag segment.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Operator must confirm the TTS replacement before output.",
                },
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Operator must confirm the TTS replacement before output.",
                },
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert preview_response.json()["detail"].count("tts_replacement_review_required@seg_001") == 1


def test_output_blockers_deduplicate_repeated_persisted_pending_recommendation_entries(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Persisted Pending Recommendation Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Duplicate persisted pending recommendation segment.",
                    "script_text": "Duplicate persisted pending recommendation segment.",
                    "summary": "Duplicate pending recommendation.",
                    "keywords": ["duplicate"],
                    "visual_plan": "Review before output.",
                    "broll_query": "duplicate",
                    "narration_text": "Duplicate persisted pending recommendation segment.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Operator must confirm the TTS replacement before output.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-02T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Operator must confirm the TTS replacement before output.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-02T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert preview_response.json()["detail"].count("tts_replacement:rec_tts_seg_001@seg_001") == 1


def test_output_blocker_detail_canonicalizes_mixed_case_pending_recommendation_type(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Mixed Case Pending Recommendation Detail Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Mixed case pending recommendation segment.",
                    "script_text": "Mixed case pending recommendation segment.",
                    "summary": "Mixed case pending recommendation.",
                    "keywords": ["mixed-case"],
                    "visual_plan": "Review before output.",
                    "broll_query": "mixed-case",
                    "narration_text": "Mixed case pending recommendation segment.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Operator must confirm the TTS replacement before output.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-02T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert "tts_replacement:rec_tts_seg_001@seg_001" in preview_response.json()["detail"]


def test_output_blocker_detail_trims_pending_recommendation_identity_fields(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Trimmed Pending Recommendation Detail Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [
                {
                    "segment_id": "seg_001",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "transcript_text": "Trimmed pending recommendation segment.",
                    "script_text": "Trimmed pending recommendation segment.",
                    "summary": "Trimmed pending recommendation.",
                    "keywords": ["trimmed"],
                    "visual_plan": "Review before output.",
                    "broll_query": "trimmed",
                    "narration_text": "Trimmed pending recommendation segment.",
                    "review_required": False,
                    "cleanup_decision": "keep",
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": " rec_tts_seg_001 ",
                    "target_segment_id": " seg_001 ",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Operator must confirm the TTS replacement before output.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert "tts_replacement:rec_tts_seg_001@seg_001" in preview_response.json()["detail"]
    assert "tts_replacement: rec_tts_seg_001 @ seg_001 " not in preview_response.json()["detail"]


def test_approving_last_pending_recommendation_still_requires_explicit_review_approval_for_output(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "draft"
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()
    assert "approval" in export_response.json()["detail"].lower()
    assert "approval" in subtitle_response.json()["detail"].lower()

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["pending_recommendations"] == []
    assert refreshed_timeline_payload["review_flags"] == []
    assert [item["recommendation_id"] for item in refreshed_timeline_payload["applied_recommendations"]] == [
        "rec_broll_review_002"
    ]

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_approving_last_pending_recommendation_removes_trimmed_review_flag_for_same_segment(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_trimmed_flag",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_flag",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": " seg_002 ",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_flag/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["review_flags"] == []

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []


def test_approving_last_pending_recommendation_removes_trimmed_review_flag_code_for_same_segment(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_trimmed_flag_code",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_flag_code",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": " broll_review_required ",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_flag_code/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["review_flags"] == []

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []


def test_approving_last_pending_recommendation_removes_mixed_case_review_flag_code_for_same_segment(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_mixed_case_flag_code",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_mixed_case_flag_code",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": " BROLL_REVIEW_REQUIRED ",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_mixed_case_flag_code/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["review_flags"] == []

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []


def test_approving_last_pending_recommendation_matches_trimmed_recommendation_id(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": " rec_broll_review_trimmed_id ",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_id",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rec_broll_review_trimmed_id",
                project_id,
                "seg_002",
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_id/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["review_flags"] == []
    assert [item["recommendation_id"] for item in payload["applied_recommendations"]] == [
        "rec_broll_review_trimmed_id"
    ]

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []
    assert [item["recommendation_id"] for item in refreshed_timeline_payload["applied_recommendations"]] == [
        "rec_broll_review_trimmed_id"
    ]


def test_approving_last_pending_recommendation_rewrites_trimmed_recommendation_decision_key(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": " rec_broll_review_trimmed_decision_key ",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_decision_key",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    persisted_timeline["recommendation_decisions"] = {
        " rec_broll_review_trimmed_decision_key ": "pending"
    }
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rec_broll_review_trimmed_decision_key",
                project_id,
                "seg_002",
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_decision_key/approve"
    )

    assert approve_response.status_code == 200
    persisted_timeline_after_approve = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline_after_approve["recommendation_decisions"] == {
        "rec_broll_review_trimmed_decision_key": "approved"
    }


def test_approving_last_pending_recommendation_persists_canonical_trimmed_recommendation_id(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": " rec_broll_review_trimmed_persisted_id ",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_persisted_id",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rec_broll_review_trimmed_persisted_id",
                project_id,
                "seg_002",
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_persisted_id/approve"
    )

    assert approve_response.status_code == 200
    persisted_timeline_after_approve = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert [item["recommendation_id"] for item in persisted_timeline_after_approve["applied_recommendations"]] == [
        "rec_broll_review_trimmed_persisted_id"
    ]


def test_approving_last_pending_recommendation_removes_blocker_with_trimmed_target_segment_id(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_trimmed_target_segment",
        "target_segment_id": " seg_002 ",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_trimmed_target_segment",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                "seg_002",
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_target_segment/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["review_flags"] == []

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []


def test_approving_last_pending_recommendation_ignores_stale_non_dict_review_flags_before_output_approval(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        "stale_truthy_review_flag",
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        },
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "draft"
    assert approve_response.json()["review_flags"] == []
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()
    assert "approval" in export_response.json()["detail"].lower()
    assert "approval" in subtitle_response.json()["detail"].lower()

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["review_flags"] == []
    assert refreshed_timeline_payload["pending_recommendations"] == []
    assert [item["recommendation_id"] for item in refreshed_timeline_payload["applied_recommendations"]] == [
        "rec_broll_review_002"
    ]


def test_review_snapshot_api_approve_preserves_non_target_review_items_and_blocked_status(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    non_target_candidate = {
        "recommendation_id": "rec_tts_review_003",
        "target_segment_id": "seg_003",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_003",
        "score": 0.91,
        "reason": "Operator still needs to review the regenerated narration.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"voice_sample_id": "voice_003"},
        "created_at": "2026-06-30T00:00:01+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate, non_target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        },
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        },
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.executemany(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    target_candidate["recommendation_id"],
                    project_id,
                    target_candidate["target_segment_id"],
                    target_candidate["recommendation_type"],
                    target_candidate["selected_asset_id"],
                    target_candidate["score"],
                    target_candidate["reason"],
                    0,
                    1,
                    json.dumps(target_candidate["payload"], ensure_ascii=True),
                    target_candidate["created_at"],
                ),
                (
                    non_target_candidate["recommendation_id"],
                    project_id,
                    non_target_candidate["target_segment_id"],
                    non_target_candidate["recommendation_type"],
                    non_target_candidate["selected_asset_id"],
                    non_target_candidate["score"],
                    non_target_candidate["reason"],
                    0,
                    1,
                    json.dumps(non_target_candidate["payload"], ensure_ascii=True),
                    non_target_candidate["created_at"],
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "blocked"
    assert [item["recommendation_id"] for item in payload["pending_recommendations"]] == [
        "rec_tts_review_003"
    ]
    assert payload["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    assert [item["recommendation_id"] for item in payload["applied_recommendations"]] == [
        "rec_broll_review_002"
    ]

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "blocked"
    assert [
        item["recommendation_id"] for item in refreshed_timeline_payload["pending_recommendations"]
    ] == ["rec_tts_review_003"]
    assert refreshed_timeline_payload["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    assert [
        item["recommendation_id"] for item in refreshed_timeline_payload["applied_recommendations"]
    ] == ["rec_broll_review_002"]

    connection = sqlite3.connect(database_path)
    try:
        target_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_002",),
        ).fetchone()
        non_target_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_tts_review_003",),
        ).fetchone()
    finally:
        connection.close()

    persisted_timeline_after_approve = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert target_row == (1, 0, "approved")
    assert non_target_row == (0, 1, None)
    assert persisted_timeline_after_approve["recommendation_decisions"] == {
        "rec_broll_review_002": "approved"
    }


def test_approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    remaining_candidate = {
        "recommendation_id": "rec_tts_review_003",
        "target_segment_id": "seg_003",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_003",
        "score": 0.91,
        "reason": "Operator still needs to review the regenerated narration.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"voice_sample_id": "voice_003"},
        "created_at": "2026-06-30T00:00:01+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate, remaining_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        },
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_003",
            "message": "Operator must confirm the TTS replacement before approval.",
        },
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.executemany(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    target_candidate["recommendation_id"],
                    project_id,
                    target_candidate["target_segment_id"],
                    target_candidate["recommendation_type"],
                    target_candidate["selected_asset_id"],
                    target_candidate["score"],
                    target_candidate["reason"],
                    0,
                    1,
                    json.dumps(target_candidate["payload"], ensure_ascii=True),
                    target_candidate["created_at"],
                ),
                (
                    remaining_candidate["recommendation_id"],
                    project_id,
                    remaining_candidate["target_segment_id"],
                    remaining_candidate["recommendation_type"],
                    remaining_candidate["selected_asset_id"],
                    remaining_candidate["score"],
                    remaining_candidate["reason"],
                    0,
                    1,
                    json.dumps(remaining_candidate["payload"], ensure_ascii=True),
                    remaining_candidate["created_at"],
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "blocked"
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "tts_replacement" in preview_response.json()["detail"]
    assert "rec_tts_review_003" in preview_response.json()["detail"]
    assert "tts_replacement" in export_response.json()["detail"]
    assert "rec_tts_review_003" in export_response.json()["detail"]
    assert "tts_replacement" in subtitle_response.json()["detail"]
    assert "rec_tts_review_003" in subtitle_response.json()["detail"]

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    subtitle_job = next(job for job in jobs_payload if job["job_type"] == "subtitle_render")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"
    assert subtitle_job["status"] == "failed"

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))
    assert not list((project_root / "subtitles").glob("subtitle_*.srt"))


def test_last_blocker_approval_followed_by_explicit_review_approval_unlocks_outputs(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_recommendation_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )
    blocked_preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    approve_review_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_recommendation_response.status_code == 200
    assert approve_recommendation_response.json()["review_status"] == "draft"
    assert blocked_preview_response.status_code == 400
    assert "approval" in blocked_preview_response.json()["detail"].lower()
    assert approve_review_response.status_code == 202
    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    subtitle_result = client.get(
        f"/api/projects/{project_id}/subtitles/{subtitle_response.json()['job_id']}"
    )
    preview_result = client.get(
        f"/api/projects/{project_id}/previews/{preview_response.json()['job_id']}"
    )
    export_result = client.get(
        f"/api/projects/{project_id}/exports/{export_response.json()['job_id']}"
    )

    assert refreshed_timeline.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "approved"
    assert review_snapshot.status_code == 200
    assert review_snapshot.json()["review_status"] == "approved"
    assert subtitle_result.status_code == 200
    assert subtitle_result.json()["subtitle"]["format"] == "srt"
    assert subtitle_result.json()["subtitle"]["file_uri"].endswith(".srt")
    assert preview_result.status_code == 200
    assert preview_result.json()["preview"]["artifact_kind"] == "playable_html_preview"
    assert preview_result.json()["preview"]["player_uri"].endswith(".html")
    assert export_result.status_code == 200
    assert export_result.json()["export"]["adapter"] == "capcut_v1_port"
    assert export_result.json()["export"]["subtitle_file_uri"].endswith(".srt")


def test_reopening_approved_review_reblocks_outputs_until_reapproved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Reopen Approval Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )
    reopen_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/reopen")
    reblocked_preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    reblocked_export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    reblocked_subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202
    assert subtitle_response.status_code == 202
    assert reopen_response.status_code == 202
    assert reopen_response.json()["review_status"] == "draft"
    assert reblocked_preview_response.status_code == 400
    assert reblocked_export_response.status_code == 400
    assert reblocked_subtitle_response.status_code == 400
    assert "approval" in reblocked_preview_response.json()["detail"].lower()
    assert "approval" in reblocked_export_response.json()["detail"].lower()
    assert "approval" in reblocked_subtitle_response.json()["detail"].lower()

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    refreshed_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert refreshed_timeline.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "draft"
    assert refreshed_snapshot.status_code == 200
    assert refreshed_snapshot.json()["review_status"] == "draft"

    failed_preview_jobs = [job for job in jobs_payload if job["job_type"] == "preview_render" and job["status"] == "failed"]
    failed_export_jobs = [job for job in jobs_payload if job["job_type"] == "capcut_export" and job["status"] == "failed"]
    failed_subtitle_jobs = [job for job in jobs_payload if job["job_type"] == "subtitle_render" and job["status"] == "failed"]
    assert failed_preview_jobs
    assert failed_export_jobs
    assert failed_subtitle_jobs


def test_reopening_approved_review_with_residual_blockers_returns_blocked_status(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Reopen Residual Blocker Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-01T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    reopen_response = client.post(
        f"/api/projects/{project.project_id}/review-approvals/{timeline_job['job_id']}/reopen"
    )
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    subtitle_response = client.post(
        f"/api/projects/{project.project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert reopen_response.status_code == 202
    assert reopen_response.json()["review_status"] == "blocked"
    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "review blockers" in preview_response.json()["detail"].lower()
    assert "review blockers" in export_response.json()["detail"].lower()
    assert "review blockers" in subtitle_response.json()["detail"].lower()

    refreshed_timeline = client.get(f"/api/projects/{project.project_id}/timelines/{timeline_job['job_id']}")
    refreshed_snapshot = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{timeline_job['job_id']}"
    )

    assert refreshed_timeline.status_code == 200
    assert refreshed_timeline.json()["timeline"]["review_status"] == "blocked"
    assert refreshed_snapshot.status_code == 200
    assert refreshed_snapshot.json()["review_status"] == "blocked"


def test_review_snapshot_api_approve_tts_replacement_updates_target_narration_clip_and_keeps_other_blockers(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_002",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_002.wav"
            )
        },
        "created_at": "2026-07-01T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    non_target_candidate = {
        "recommendation_id": "rec_broll_review_001",
        "target_segment_id": "seg_001",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_001",
        "score": 0.81,
        "reason": "Operator still needs to review the B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["office"]},
        "created_at": "2026-07-01T00:00:01+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate, non_target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        },
        {
            "code": "broll_review_required",
            "segment_id": "seg_001",
            "message": "Operator must confirm the B-roll pick before approval.",
        },
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.executemany(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    target_candidate["recommendation_id"],
                    project_id,
                    target_candidate["target_segment_id"],
                    target_candidate["recommendation_type"],
                    target_candidate["selected_asset_id"],
                    target_candidate["score"],
                    target_candidate["reason"],
                    0,
                    1,
                    json.dumps(target_candidate["payload"], ensure_ascii=True),
                    target_candidate["created_at"],
                ),
                (
                    non_target_candidate["recommendation_id"],
                    project_id,
                    non_target_candidate["target_segment_id"],
                    non_target_candidate["recommendation_type"],
                    non_target_candidate["selected_asset_id"],
                    non_target_candidate["score"],
                    non_target_candidate["reason"],
                    0,
                    1,
                    json.dumps(non_target_candidate["payload"], ensure_ascii=True),
                    non_target_candidate["created_at"],
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_002/approve"
    )

    assert approve_response.status_code == 200
    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "blocked"
    assert [
        item["recommendation_id"] for item in refreshed_timeline_payload["pending_recommendations"]
    ] == ["rec_broll_review_001"]
    assert refreshed_timeline_payload["review_flags"] == [
        {
            "code": "broll_review_required",
            "segment_id": "seg_001",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    narration_track = next(
        track for track in refreshed_timeline_payload["tracks"] if track["track_type"] == "narration"
    )
    clip_by_segment = {
        clip["segment_id"]: clip["asset_uri"]
        for clip in narration_track["clips"]
    }
    assert clip_by_segment["seg_001"] == f"local://projects/{project_id}/segments/seg_001"
    assert clip_by_segment["seg_002"] == target_candidate["payload"]["selected_asset_uri"]


def test_review_snapshot_api_approve_tts_replacement_updates_all_duplicate_target_narration_clips(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_002",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_002.wav"
            )
        },
        "created_at": "2026-07-01T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    narration_track = next(
        track for track in persisted_timeline["tracks"] if track["track_type"] == "narration"
    )
    narration_track["clips"].append(
        {
            "clip_id": "clip_narration_duplicate_seg_002",
            "segment_id": "seg_002",
            "asset_uri": f"local://projects/{project_id}/segments/seg_002_duplicate_stale",
            "start_sec": 8.0,
            "end_sec": 10.0,
            "clip_type": "narration",
        }
    )
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_002/approve"
    )

    assert approve_response.status_code == 200
    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    narration_track = next(
        track for track in refreshed_timeline_payload["tracks"] if track["track_type"] == "narration"
    )
    seg_002_asset_uris = [
        clip["asset_uri"]
        for clip in narration_track["clips"]
        if clip["segment_id"] == "seg_002"
    ]

    assert seg_002_asset_uris == [
        target_candidate["payload"]["selected_asset_uri"],
        target_candidate["payload"]["selected_asset_uri"],
    ]


def test_approving_last_pending_tts_replacement_persists_remaining_segment_review_required_blocker(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_002",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_002.wav"
            )
        },
        "created_at": "2026-07-01T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["segments"] = [
        {
            "segment_id": "seg_001",
            "start_sec": 0.0,
            "end_sec": 6.0,
            "transcript_text": "Approved intro segment.",
            "script_text": "Approved intro segment.",
            "summary": "Approved intro segment.",
            "keywords": ["intro"],
            "visual_plan": "Keep current visuals.",
            "broll_query": "intro",
            "narration_text": "Approved intro segment.",
            "review_required": False,
            "cleanup_decision": "keep",
        },
        {
            "segment_id": "seg_002",
            "start_sec": 6.0,
            "end_sec": 12.0,
            "transcript_text": "Segment still needs manual review.",
            "script_text": "Segment still needs manual review.",
            "summary": "Segment still needs manual review.",
            "keywords": ["review"],
            "visual_plan": "Review before export.",
            "broll_query": "review",
            "narration_text": "Segment still needs manual review.",
            "review_required": True,
            "cleanup_decision": "review",
        },
    ]
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_002/approve"
    )

    assert approve_response.status_code == 200
    persisted_timeline_after_approve = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline_after_approve["pending_recommendations"] == []
    assert persisted_timeline_after_approve["review_flags"] == [
        {
            "code": "segment_review_required",
            "segment_id": "seg_002",
            "message": "Segment requires operator review before export.",
        }
    ]
    assert [
        item["recommendation_id"]
        for item in persisted_timeline_after_approve["applied_recommendations"]
    ] == ["rec_tts_review_002"]
    assert persisted_timeline_after_approve["applied_recommendations"][0]["decision_state"] == "approved"
    narration_track = next(
        track
        for track in persisted_timeline_after_approve["tracks"]
        if track["track_type"] == "narration"
    )
    seg_002_clip = next(clip for clip in narration_track["clips"] if clip["segment_id"] == "seg_002")
    assert seg_002_clip["asset_uri"] == target_candidate["payload"]["selected_asset_uri"]


def test_review_snapshot_api_rejects_tts_approval_without_selected_asset_uri(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_missing_uri",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_missing_uri",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {},
        "created_at": "2026-07-02T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    narration_track = next(
        track for track in persisted_timeline["tracks"] if track["track_type"] == "narration"
    )
    original_seg_002_asset_uri = next(
        clip["asset_uri"] for clip in narration_track["clips"] if clip["segment_id"] == "seg_002"
    )
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_missing_uri/approve"
    )

    assert approve_response.status_code == 400
    assert "selected_asset_uri" in approve_response.json()["detail"]

    persisted_timeline_after_attempt = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline_after_attempt["applied_recommendations"] == []
    assert [
        item["recommendation_id"]
        for item in persisted_timeline_after_attempt["pending_recommendations"]
    ] == ["rec_tts_review_missing_uri"]
    narration_track_after_attempt = next(
        track
        for track in persisted_timeline_after_attempt["tracks"]
        if track["track_type"] == "narration"
    )
    seg_002_clip_after_attempt = next(
        clip for clip in narration_track_after_attempt["clips"] if clip["segment_id"] == "seg_002"
    )
    assert seg_002_clip_after_attempt["asset_uri"] == original_seg_002_asset_uri

    connection = sqlite3.connect(database_path)
    try:
        target_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_tts_review_missing_uri",),
        ).fetchone()
    finally:
        connection.close()

    assert target_row == (0, 1, None)


def test_review_snapshot_api_approve_tts_replacement_matches_trimmed_target_narration_clip_segment_id(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_trimmed_clip_segment",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_trimmed_clip_segment",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_trimmed_clip_segment.wav"
            )
        },
        "created_at": "2026-07-04T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    narration_track = next(
        track for track in persisted_timeline["tracks"] if track["track_type"] == "narration"
    )
    for clip in narration_track["clips"]:
        if clip["segment_id"] == "seg_002":
            clip["segment_id"] = " seg_002 "
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_trimmed_clip_segment/approve"
    )

    assert approve_response.status_code == 200
    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_narration_track = next(
        track for track in refreshed_timeline.json()["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    seg_002_clip = next(
        clip for clip in refreshed_narration_track["clips"] if clip["segment_id"].strip() == "seg_002"
    )
    assert seg_002_clip["asset_uri"] == target_candidate["payload"]["selected_asset_uri"]


def test_review_snapshot_api_approve_tts_replacement_matches_trimmed_recommendation_type(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_trimmed_type",
        "target_segment_id": "seg_002",
        "recommendation_type": " tts_replacement ",
        "selected_asset_id": "asset_tts_review_trimmed_type",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_trimmed_type.wav"
            )
        },
        "created_at": "2026-07-04T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_trimmed_type/approve"
    )

    assert approve_response.status_code == 200
    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_narration_track = next(
        track for track in refreshed_timeline.json()["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    seg_002_clip = next(
        clip for clip in refreshed_narration_track["clips"] if clip["segment_id"] == "seg_002"
    )
    assert seg_002_clip["asset_uri"] == target_candidate["payload"]["selected_asset_uri"]


def test_review_snapshot_api_approve_broll_uses_trimmed_recommendation_type_for_provider_trace_fallback(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_broll_review_trimmed_type_trace",
        "target_segment_id": "seg_001",
        "recommendation_type": " broll ",
        "selected_asset_id": "asset_broll_review_trimmed_type_trace",
        "score": 0.81,
        "reason": "Operator approved the trimmed-type B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["office"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_001",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_trimmed_type_trace/approve"
    )

    assert approve_response.status_code == 200
    approval_payload = approve_response.json()
    assert approval_payload["applied_recommendations"][0]["provider_trace"]["final_provider"] == (
        "heuristic_fallback"
    )

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")

    assert refreshed_timeline.status_code == 200
    assert (
        refreshed_timeline.json()["timeline"]["applied_recommendations"][0]["provider_trace"]["final_provider"]
        == "heuristic_fallback"
    )


def test_review_snapshot_api_approve_broll_uses_mixed_case_recommendation_type_for_provider_trace_fallback(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_broll_review_mixed_case_type_trace",
        "target_segment_id": "seg_001",
        "recommendation_type": " BROLL ",
        "selected_asset_id": "asset_broll_review_mixed_case_type_trace",
        "score": 0.81,
        "reason": "Operator approved the mixed-case B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["office"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_001",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_mixed_case_type_trace/approve"
    )

    assert approve_response.status_code == 200
    approval_payload = approve_response.json()
    assert approval_payload["applied_recommendations"][0]["provider_trace"]["final_provider"] == (
        "heuristic_fallback"
    )

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")

    assert refreshed_timeline.status_code == 200
    assert (
        refreshed_timeline.json()["timeline"]["applied_recommendations"][0]["provider_trace"]["final_provider"]
        == "heuristic_fallback"
    )


def test_review_snapshot_api_rejects_tts_approval_without_matching_target_narration_clip(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_missing_clip",
        "target_segment_id": "seg_999",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_missing_clip",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_missing_clip.wav"
            )
        },
        "created_at": "2026-07-03T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    original_narration_track = json.loads(
        json.dumps(
            next(track for track in persisted_timeline["tracks"] if track["track_type"] == "narration")
        )
    )
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_999",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_missing_clip/approve"
    )

    assert approve_response.status_code == 400
    assert "target narration clip" in approve_response.json()["detail"].lower()

    persisted_timeline_after_attempt = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline_after_attempt["applied_recommendations"] == []
    assert [
        item["recommendation_id"]
        for item in persisted_timeline_after_attempt["pending_recommendations"]
    ] == ["rec_tts_review_missing_clip"]
    narration_track_after_attempt = next(
        track
        for track in persisted_timeline_after_attempt["tracks"]
        if track["track_type"] == "narration"
    )
    assert narration_track_after_attempt == original_narration_track

    connection = sqlite3.connect(database_path)
    try:
        target_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_tts_review_missing_clip",),
        ).fetchone()
    finally:
        connection.close()

    assert target_row == (0, 1, None)


def test_review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_decision_state",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_decision_state",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_decision_state.wav"
            )
        },
        "created_at": "2026-07-03T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_decision_state/approve"
    )

    assert approve_response.status_code == 200
    approval_payload = approve_response.json()
    assert approval_payload["applied_recommendations"][0]["decision_state"] == "approved"

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    refreshed_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert refreshed_timeline.status_code == 200
    assert refreshed_snapshot.status_code == 200
    assert refreshed_timeline.json()["timeline"]["applied_recommendations"][0]["decision_state"] == "approved"
    assert refreshed_snapshot.json()["applied_recommendations"][0]["decision_state"] == "approved"


def test_review_snapshot_api_can_reject_pending_recommendation_without_leaving_it_pending(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    rejected_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator rejected the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [rejected_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rejected_candidate["recommendation_id"],
                project_id,
                rejected_candidate["target_segment_id"],
                rejected_candidate["recommendation_type"],
                rejected_candidate["selected_asset_id"],
                rejected_candidate["score"],
                rejected_candidate["reason"],
                0,
                1,
                json.dumps(rejected_candidate["payload"], ensure_ascii=True),
                rejected_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    reject_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/reject"
    )

    assert reject_response.status_code == 200
    payload = reject_response.json()
    assert payload["review_status"] == "draft"
    assert payload["pending_recommendations"] == []
    assert payload["applied_recommendations"] == []
    assert payload["review_flags"] == []

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "draft"
    assert refreshed_timeline_payload["pending_recommendations"] == []
    assert refreshed_timeline_payload["applied_recommendations"] == []
    assert refreshed_timeline_payload["review_flags"] == []

    connection = sqlite3.connect(database_path)
    try:
        rejected_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_002",),
        ).fetchone()
    finally:
        connection.close()

    persisted_timeline_after_reject = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert rejected_row == (0, 0, "rejected")
    assert persisted_timeline_after_reject["recommendation_decisions"] == {
        "rec_broll_review_002": "rejected"
    }

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            UPDATE recommendations
            SET auto_apply_allowed = 1, review_required = 0, decision_state = 'approved'
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_002",),
        )
        connection.commit()
    finally:
        connection.close()

    repeated_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert repeated_snapshot.status_code == 200
    assert repeated_snapshot.json()["review_status"] == "draft"
    assert repeated_snapshot.json()["pending_recommendations"] == []
    assert repeated_snapshot.json()["applied_recommendations"] == []
    assert repeated_snapshot.json()["review_flags"] == []


def test_review_snapshot_api_approve_rolls_back_timeline_and_recommendation_when_review_state_save_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_rollback_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_rollback_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")
    original_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    def fail_save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
    ) -> dict[str, object]:
        del self, project_id, timeline_id, status
        raise OSError("review state persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_review_state", fail_save_review_state)

    with pytest.warns(UserWarning, match="stage=review_state"):
        approve_response = client.post(
            f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
            "rec_broll_review_rollback_002/approve"
        )

    assert approve_response.status_code == 500

    connection = sqlite3.connect(database_path)
    try:
        recommendation_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_rollback_002",),
        ).fetchone()
    finally:
        connection.close()

    restored_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert restored_timeline["pending_recommendations"] == original_timeline["pending_recommendations"]
    assert restored_timeline["applied_recommendations"] == original_timeline["applied_recommendations"]
    assert restored_timeline["review_flags"] == original_timeline["review_flags"]
    assert restored_timeline["recommendation_decisions"] == original_timeline.get("recommendation_decisions")
    assert recommendation_row == (0, 1, None)


def test_review_snapshot_api_approve_rollback_normalizes_legacy_string_false_recommendation_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    legacy_candidate = {
        "recommendation_id": "rec_broll_review_rollback_legacy_false_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_rollback_legacy_false_002",
        "score": 0.88,
        "reason": "Legacy string false candidate for rollback normalization.",
        "auto_apply_allowed": "false",
        "review_required": "false",
        "decision_state": "pending",
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-07-04T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [legacy_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                decision_state,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                legacy_candidate["recommendation_id"],
                project_id,
                legacy_candidate["target_segment_id"],
                legacy_candidate["recommendation_type"],
                legacy_candidate["selected_asset_id"],
                legacy_candidate["score"],
                legacy_candidate["reason"],
                "false",
                "false",
                "pending",
                json.dumps(legacy_candidate["payload"], ensure_ascii=True),
                legacy_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    def fail_save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
    ) -> dict[str, object]:
        del self, project_id, timeline_id, status
        raise OSError("review state persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_review_state", fail_save_review_state)

    with pytest.warns(UserWarning, match="stage=review_state"):
        approve_response = client.post(
            f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
            "rec_broll_review_rollback_legacy_false_002/approve"
        )

    assert approve_response.status_code == 500

    connection = sqlite3.connect(database_path)
    try:
        recommendation_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_rollback_legacy_false_002",),
        ).fetchone()
    finally:
        connection.close()

    assert recommendation_row == (0, 0, "pending")


def test_review_snapshot_api_reject_rolls_back_timeline_and_recommendation_when_review_state_save_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    rejected_candidate = {
        "recommendation_id": "rec_broll_review_rollback_reject_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_rollback_reject_002",
        "score": 0.88,
        "reason": "Operator rejected the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [rejected_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")
    original_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rejected_candidate["recommendation_id"],
                project_id,
                rejected_candidate["target_segment_id"],
                rejected_candidate["recommendation_type"],
                rejected_candidate["selected_asset_id"],
                rejected_candidate["score"],
                rejected_candidate["reason"],
                0,
                1,
                json.dumps(rejected_candidate["payload"], ensure_ascii=True),
                rejected_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    def fail_save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
    ) -> dict[str, object]:
        del self, project_id, timeline_id, status
        raise OSError("review state persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_review_state", fail_save_review_state)

    with pytest.warns(UserWarning, match="stage=review_state"):
        reject_response = client.post(
            f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
            "rec_broll_review_rollback_reject_002/reject"
        )

    assert reject_response.status_code == 500

    connection = sqlite3.connect(database_path)
    try:
        recommendation_row = connection.execute(
            """
            SELECT auto_apply_allowed, review_required, decision_state
            FROM recommendations
            WHERE recommendation_id = ?
            """,
            ("rec_broll_review_rollback_reject_002",),
        ).fetchone()
    finally:
        connection.close()

    restored_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert restored_timeline["pending_recommendations"] == original_timeline["pending_recommendations"]
    assert restored_timeline["applied_recommendations"] == original_timeline["applied_recommendations"]
    assert restored_timeline["review_flags"] == original_timeline["review_flags"]
    assert restored_timeline["recommendation_decisions"] == original_timeline.get("recommendation_decisions")
    assert recommendation_row == (0, 1, None)




def test_review_snapshot_api_warns_when_timeline_rollback_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    approved_candidate = {
        "recommendation_id": "rec_broll_review_warn_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_warn_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    original_update_timeline_run = LocalProjectStore.update_timeline_run
    update_timeline_run_calls = {"count": 0}

    def flaky_update_timeline_run(self, *args, **kwargs):
        update_timeline_run_calls["count"] += 1
        if update_timeline_run_calls["count"] == 2:
            raise OSError("timeline rollback offline")
        return original_update_timeline_run(self, *args, **kwargs)

    def fail_save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
    ) -> dict[str, object]:
        del self, project_id, timeline_id, status
        raise OSError("review state persistence offline")

    monkeypatch.setattr(LocalProjectStore, "update_timeline_run", flaky_update_timeline_run)
    monkeypatch.setattr(LocalProjectStore, "save_review_state", fail_save_review_state)

    with pytest.warns(UserWarning) as recorded_warnings:
        approve_response = client.post(
            f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
            "rec_broll_review_warn_002/approve"
        )

    assert approve_response.status_code == 500
    warning_messages = [str(item.message) for item in recorded_warnings]
    assert any("stage=timeline" in message for message in warning_messages)
    assert any("stage=review_state" in message for message in warning_messages)


def test_review_snapshot_stays_timeline_local_when_another_timeline_mutates_shared_recommendation_state(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_a_job_id = _create_timeline_review_project(client, tmp_path)
    store = LocalProjectStore(tmp_path)

    timeline_a_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_a_job_id}")
    timeline_a_payload = timeline_a_result.json()["timeline"]
    timeline_a_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_a_payload["timeline_id"]}.json'
    )
    persisted_timeline_a = json.loads(timeline_a_path.read_text(encoding="utf-8"))
    shared_candidate = {
        "recommendation_id": "rec_broll_shared_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_shared_002",
        "score": 0.88,
        "reason": "Operator must decide on the shared B-roll pick per timeline.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline_a["applied_recommendations"] = []
    persisted_timeline_a["pending_recommendations"] = [shared_candidate]
    persisted_timeline_a["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_a_path.write_text(json.dumps(persisted_timeline_a, indent=2), encoding="utf-8")

    persisted_timeline_b = {
        key: value
        for key, value in persisted_timeline_a.items()
        if key not in {"timeline_id", "file_uri", "created_at"}
    }
    created_timeline_b = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        timeline_payload=persisted_timeline_b,
    )
    timeline_b_job = store.create_job(
        project_id=project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref=str(persisted_timeline_a.get("lineage", {}).get("segment_analysis_job_id") or ""),
    )
    store.update_job(
        project_id=project_id,
        job_id=timeline_b_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=created_timeline_b["timeline_id"],
    )

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                shared_candidate["recommendation_id"],
                project_id,
                shared_candidate["target_segment_id"],
                shared_candidate["recommendation_type"],
                shared_candidate["selected_asset_id"],
                shared_candidate["score"],
                shared_candidate["reason"],
                0,
                1,
                json.dumps(shared_candidate["payload"], ensure_ascii=True),
                shared_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_a_job_id}/recommendations/"
        "rec_broll_shared_002/approve"
    )
    timeline_b_snapshot = client.get(
        f"/api/projects/{project_id}/review-snapshots/{timeline_b_job['job_id']}"
    )

    assert approve_response.status_code == 200
    assert timeline_b_snapshot.status_code == 200
    assert timeline_b_snapshot.json()["review_status"] == "blocked"
    assert [item["recommendation_id"] for item in timeline_b_snapshot.json()["pending_recommendations"]] == [
        "rec_broll_shared_002"
    ]
    assert timeline_b_snapshot.json()["review_flags"] == [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]


def test_rejecting_one_duplicate_pending_recommendation_keeps_shared_review_flag_when_blocker_remains(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    rejected_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator rejected the first B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    remaining_candidate = {
        "recommendation_id": "rec_broll_review_003",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_003",
        "score": 0.84,
        "reason": "Operator still needs to review the alternate B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting", "alt"]},
        "created_at": "2026-06-30T00:00:01+00:00",
        "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [rejected_candidate, remaining_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.executemany(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    rejected_candidate["recommendation_id"],
                    project_id,
                    rejected_candidate["target_segment_id"],
                    rejected_candidate["recommendation_type"],
                    rejected_candidate["selected_asset_id"],
                    rejected_candidate["score"],
                    rejected_candidate["reason"],
                    0,
                    1,
                    json.dumps(rejected_candidate["payload"], ensure_ascii=True),
                    rejected_candidate["created_at"],
                ),
                (
                    remaining_candidate["recommendation_id"],
                    project_id,
                    remaining_candidate["target_segment_id"],
                    remaining_candidate["recommendation_type"],
                    remaining_candidate["selected_asset_id"],
                    remaining_candidate["score"],
                    remaining_candidate["reason"],
                    0,
                    1,
                    json.dumps(remaining_candidate["payload"], ensure_ascii=True),
                    remaining_candidate["created_at"],
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    reject_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/reject"
    )

    assert reject_response.status_code == 200
    payload = reject_response.json()
    assert payload["review_status"] == "blocked"
    assert [item["recommendation_id"] for item in payload["pending_recommendations"]] == [
        "rec_broll_review_003"
    ]
    assert payload["review_flags"] == [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["review_status"] == "blocked"
    assert [
        item["recommendation_id"] for item in refreshed_timeline_payload["pending_recommendations"]
    ] == ["rec_broll_review_003"]
    assert refreshed_timeline_payload["review_flags"] == [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]


def test_approved_tts_replacement_flows_through_preview_and_export_outputs(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved TTS Output Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "narration_source_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": (
                                f"local://projects/{project.project_id}/assets/generated/"
                                "asset_tts_approved_001.wav"
                            ),
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_approved_001",
                    "score": 1.0,
                    "reason": "Approved narration replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": f"local://projects/{project.project_id}/assets/generated/asset_tts_approved_001.wav"
                    },
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_payload = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    ).json()
    export_payload = client.get(
        f"/api/projects/{project.project_id}/exports/{export_response.json()['job_id']}"
    ).json()

    preview_html_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=preview_payload["preview"]["player_uri"],
    )
    assert "asset_tts_approved_001" in preview_html_path.read_text(encoding="utf-8")
    voiceover_track = next(
        track for track in export_payload["export"]["capcut_tracks"] if track["track_name"] == "voiceover"
    )
    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        f"local://projects/{project.project_id}/assets/generated/asset_tts_approved_001.wav",
        f"local://projects/{project.project_id}/inputs/narration/source.wav",
    ]


def test_review_approval_persists_tts_narration_asset_uri_before_preview_and_export_read_timeline(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_002",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_002.wav"
            )
        },
        "created_at": "2026-07-01T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_002/approve"
    )

    assert approve_response.status_code == 200

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    narration_track = next(
        track for track in refreshed_timeline.json()["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    seg_002_clip = next(
        clip for clip in narration_track["clips"] if clip["segment_id"] == "seg_002"
    )
    assert seg_002_clip["asset_uri"] == target_candidate["payload"]["selected_asset_uri"]

    approve_review_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    assert approve_review_response.status_code == 202

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_payload = client.get(
        f"/api/projects/{project_id}/previews/{preview_response.json()['job_id']}"
    ).json()
    export_payload = client.get(
        f"/api/projects/{project_id}/exports/{export_response.json()['job_id']}"
    ).json()

    store = LocalProjectStore(tmp_path)
    preview_html_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=preview_payload["preview"]["player_uri"],
    )
    assert target_candidate["payload"]["selected_asset_uri"] in preview_html_path.read_text(encoding="utf-8")
    voiceover_track = next(
        track for track in export_payload["export"]["capcut_tracks"] if track["track_name"] == "voiceover"
    )
    assert target_candidate["payload"]["selected_asset_uri"] in [
        segment["source_uri"] for segment in voiceover_track["segments"]
    ]


def test_review_approval_duplicate_tts_narration_clips_flow_through_preview_and_export_outputs(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    target_candidate = {
        "recommendation_id": "rec_tts_review_duplicate_output",
        "target_segment_id": "seg_002",
        "recommendation_type": "tts_replacement",
        "selected_asset_id": "asset_tts_review_duplicate_output",
        "score": 0.94,
        "reason": "Operator approved the regenerated narration take.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {
            "selected_asset_uri": (
                f"local://projects/{project_id}/assets/generated/asset_tts_review_duplicate_output.wav"
            )
        },
        "created_at": "2026-07-03T00:00:00+00:00",
        "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
    }
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    narration_track = next(
        track for track in persisted_timeline["tracks"] if track["track_type"] == "narration"
    )
    narration_track["clips"].append(
        {
            "clip_id": "clip_narration_duplicate_seg_002_output",
            "segment_id": "seg_002",
            "asset_uri": f"local://projects/{project_id}/segments/seg_002_duplicate_stale",
            "start_sec": 8.0,
            "end_sec": 10.0,
            "clip_type": "narration",
        }
    )
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [target_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the TTS replacement before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_candidate["recommendation_id"],
                project_id,
                target_candidate["target_segment_id"],
                target_candidate["recommendation_type"],
                target_candidate["selected_asset_id"],
                target_candidate["score"],
                target_candidate["reason"],
                0,
                1,
                json.dumps(target_candidate["payload"], ensure_ascii=True),
                target_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_tts_review_duplicate_output/approve"
    )
    assert approve_response.status_code == 200

    approve_review_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    assert approve_review_response.status_code == 202

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_payload = client.get(
        f"/api/projects/{project_id}/previews/{preview_response.json()['job_id']}"
    ).json()
    export_payload = client.get(
        f"/api/projects/{project_id}/exports/{export_response.json()['job_id']}"
    ).json()

    store = LocalProjectStore(tmp_path)
    preview_html_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=preview_payload["preview"]["player_uri"],
    )
    assert (
        preview_html_path.read_text(encoding="utf-8").count(target_candidate["payload"]["selected_asset_uri"])
        == 2
    )
    voiceover_track = next(
        track for track in export_payload["export"]["capcut_tracks"] if track["track_name"] == "voiceover"
    )
    selected_sources = [
        segment["source_uri"]
        for segment in voiceover_track["segments"]
        if segment["source_uri"] == target_candidate["payload"]["selected_asset_uri"]
    ]
    assert selected_sources == [
        target_candidate["payload"]["selected_asset_uri"],
        target_candidate["payload"]["selected_asset_uri"],
    ]


def test_editing_session_api_can_create_and_patch_caption_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )

    assert create_response.status_code == 201
    session_id = create_response.json()["session_id"]

    patch_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Manual caption fix"},
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["session_id"] == session_id
    assert payload["segments"][0]["caption_text"] == "Manual caption fix"
    assert payload["history"][-1]["mutation_type"] == "caption_update"


def test_editing_session_api_rejects_blank_caption_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    patch_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "   "},
    )

    assert patch_response.status_code == 422


def test_editing_session_api_can_fetch_cut_and_broll_updates(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    cut_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/cut-action",
        json={"cut_action": "remove"},
    )
    broll_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    get_response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}",
    )

    assert cut_response.status_code == 200
    assert broll_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["cut_action"] == "remove"
    assert payload["segments"][0]["broll_override"] == {"asset_id": "asset_manual_001"}
    assert payload["history"][-2]["mutation_type"] == "cut_action_update"
    assert payload["history"][-1]["mutation_type"] == "broll_override_update"


def test_editing_session_api_can_clear_broll_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["broll_override"] is None
    assert payload["history"][-1]["mutation_type"] == "broll_override_clear"


def test_editing_session_api_can_fetch_latest_session_by_updated_at(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_session = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    ).json()
    second_session = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    ).json()

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{first_session['session_id']}/segments/seg_001/caption",
        json={"caption_text": "Older session touched first"},
    )
    latest_update_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{second_session['session_id']}/segments/seg_001/caption",
        json={"caption_text": "Latest session should win"},
    )

    response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")

    assert latest_update_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == second_session["session_id"]
    assert payload["segments"][0]["caption_text"] == "Latest session should win"
    assert payload["updated_at"] == latest_update_response.json()["updated_at"]


def test_editing_session_api_can_start_partial_regeneration_job(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll", "visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"].startswith("partial_regeneration_job_")
    assert payload["status"] == "succeeded"
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["fields"] == ["broll", "visual_overlay"]
    assert payload["downstream_steps"] == [
        "broll_refresh",
        "overlay_refresh",
        "timeline_build",
    ]


def test_editing_session_api_surfaces_draft_prediction_when_starting_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Start Prediction Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert payload["affected_output_areas"] == [
        "segment copy",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]


def test_editing_session_api_surfaces_blocked_prediction_when_starting_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/caption",
        json={"caption_text": "Team meeting overview with corrected label"},
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/broll",
        json={"asset_id": "asset_manual_002"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_002"],
            "fields": ["caption", "broll", "visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]
    assert payload["affected_output_areas"] == [
        "segment copy",
        "b-roll track",
        "visual overlays",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]


def test_editing_session_api_can_preview_partial_regeneration_scope_without_creating_job(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/caption",
        json={"caption_text": "Team meeting overview with corrected label"},
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/broll",
        json={"asset_id": "asset_manual_002"},
    )

    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002"],
            "fields": ["caption", "broll", "visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" not in payload
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_002"]
    assert payload["fields"] == ["caption", "broll", "visual_overlay"]
    assert payload["downstream_steps"] == [
        "segment_refresh",
        "broll_refresh",
        "overlay_refresh",
        "timeline_build",
    ]
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Team meeting overview with corrected label",
            "cut_action": "keep",
            "review_required": True,
            "broll_override": {"asset_id": "asset_manual_002"},
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["affected_output_areas"] == [
        "segment copy",
        "b-roll track",
        "visual overlays",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_blocked_for_manual_tts_rerun_scope_on_review_required_segment(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/tts-replacement",
        json={
            "recommendation_id": "rec_tts_review_002",
            "asset_id": "asset_tts_review_002",
        },
    )
    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002"],
            "fields": ["tts_replacement"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]
    assert payload["affected_output_areas"] == [
        "narration track",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Line two with restart from review runtime.",
            "cut_action": "keep",
            "review_required": True,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": {
                "recommendation_id": "rec_tts_review_002",
                "asset_id": "asset_tts_review_002",
            },
        }
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_as_draft_for_clean_rerun_scope(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Clean Preflight Draft Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Clean caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []


def test_editing_session_api_marks_preflight_as_draft_for_clean_manual_tts_rerun_scope(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Clean Manual TTS Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Clean caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": {
                        "recommendation_id": "rec_tts_seg_001",
                        "asset_id": "asset_tts_001",
                    },
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["tts_replacement"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert payload["affected_output_areas"] == [
        "narration track",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Clean caption",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": {
                "recommendation_id": "rec_tts_seg_001",
                "asset_id": "asset_tts_001",
            },
        }
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_invalid_cut_action_to_keep_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Invalid Cut Action Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale cut action",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "stale_invalid_value",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale cut action",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_missing_visual_overlays_to_empty_list_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Missing Visual Overlays Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with missing overlay list",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": None,
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with missing overlay list",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_non_dict_visual_overlay_entries_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Visual Overlay Entry Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale overlay entry",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        "stale_overlay_entry",
                        {
                            "overlay_id": "overlay_image_001",
                            "overlay_type": "image",
                            "asset_id": "asset_image_001",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale overlay entry",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_id": "overlay_image_001",
                    "overlay_type": "image",
                    "asset_id": "asset_image_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_empty_visual_overlay_dict_entries_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Empty Visual Overlay Entry Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with empty visual overlay entry",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {},
                        {
                            "overlay_id": "overlay_image_001",
                            "overlay_type": "image",
                            "asset_id": "asset_image_001",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with empty visual overlay entry",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_id": "overlay_image_001",
                    "overlay_type": "image",
                    "asset_id": "asset_image_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_minimal_dict_visual_overlay_entries_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Minimal Dict Visual Overlay Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale minimal visual overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "legacy": "stale_visual_overlay_dict",
                        },
                        {
                            "overlay_id": "overlay_image_001",
                            "overlay_type": "image",
                            "asset_id": "asset_image_001",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale minimal visual overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_id": "overlay_image_001",
                    "overlay_type": "image",
                    "asset_id": "asset_image_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_overlay_type_only_visual_overlay_entries_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Overlay Type Only Visual Overlay Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with overlay-type-only visual overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_card",
                        },
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "Exterior reference image",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with overlay-type-only visual overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "image_card",
                    "asset_id": "asset_image_001",
                    "text": "Exterior reference image",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_unknown_overlay_type_entries_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Unknown Overlay Type Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with unknown overlay type",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "legacy_card",
                            "asset_id": "asset_legacy_001",
                        },
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "Exterior reference image",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with unknown overlay type",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "image_card",
                    "asset_id": "asset_image_001",
                    "text": "Exterior reference image",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_legacy_hook_title_overlay_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Hook Title Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with legacy hook title overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "hook_title",
                            "asset_id": "asset_hook_title_001",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with legacy hook title overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "hook_title",
                    "asset_id": "asset_hook_title_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_canonical_visual_overlay_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Canonical Visual Overlay Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with canonical visual overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "visual_overlay",
                            "asset_id": "asset_visual_overlay_001",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with canonical visual overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "visual_overlay",
                    "asset_id": "asset_visual_overlay_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_canonical_image_overlay_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Canonical Image Overlay Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with canonical image overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_overlay",
                            "asset_id": "asset_image_overlay_001",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["image_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with canonical image overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "image_overlay",
                    "asset_id": "asset_image_overlay_001",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_canonical_table_overlay_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Canonical Table Overlay Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with canonical table overlay",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "table_overlay",
                            "text": "Revenue | Cost | Margin",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["table_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with canonical table overlay",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [
                {
                    "overlay_type": "table_overlay",
                    "text": "Revenue | Cost | Margin",
                }
            ],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_string_false_review_required_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="String False Review Required Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with string false review_required",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": "false",
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with string false review_required",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_stale_non_bool_review_required_to_false_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Non Bool Review Required Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale non-bool review_required",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": {"stale": "review_required_container"},
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale non-bool review_required",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_stale_broll_override_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Broll Override Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale broll override",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": "stale_broll_override",
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale broll override",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_empty_broll_override_dict_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Empty Broll Override Dict Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with empty broll override dict",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {
                        "asset_id": "   ",
                    },
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with empty broll override dict",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_nested_broll_override_asset_id_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Nested Broll Override Asset Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with nested broll asset id",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {
                        "asset_id": {"stale": "nested_broll_asset_id"},
                    },
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with nested broll asset id",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_stale_music_override_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Music Override Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale music override",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": "stale_music_override",
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale music override",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_empty_music_override_dict_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Empty Music Override Dict Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with empty music override dict",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": {
                        "asset_id": "   ",
                    },
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with empty music override dict",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_nested_music_override_asset_id_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Nested Music Override Asset Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with nested music asset id",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": {
                        "asset_id": {"stale": "nested_music_asset_id"},
                    },
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with nested music asset id",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_stale_tts_replacement_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale TTS Replacement Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with stale tts replacement",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": "stale_tts_replacement",
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with stale tts replacement",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_nested_tts_recommendation_id_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Nested TTS Recommendation Id Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with nested tts recommendation id",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": {
                        "recommendation_id": {"stale": "nested_tts_recommendation_id"},
                        "asset_id": "asset_tts_001",
                    },
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with nested tts recommendation id",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_normalizes_empty_tts_replacement_dict_to_none_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Empty TTS Replacement Dict Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with empty tts replacement dict",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": {
                        "recommendation_id": "   ",
                        "asset_id": "",
                    },
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with empty tts replacement dict",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_request_segment_order_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Ordered Multi Segment Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "First caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_broll_001"},
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Second caption",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "trim",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": {"asset_id": "music_manual_002"},
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002", "seg_001"],
            "fields": ["music", "broll"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_ids"] == ["seg_002", "seg_001"]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Second caption",
            "cut_action": "trim",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": {"asset_id": "music_manual_002"},
            "tts_replacement": None,
        },
        {
            "segment_id": "seg_001",
            "caption_text": "First caption",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": {"asset_id": "asset_broll_001"},
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        },
    ]
    assert payload["affected_output_areas"] == [
        "music bed",
        "b-roll track",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_first_seen_duplicate_session_segment_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Session Segment Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Canonical first caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_broll_001"},
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stale duplicate caption that should not override",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "remove",
                    "review_required": True,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": {"asset_id": "music_stale_001"},
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Canonical first caption",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": {"asset_id": "asset_broll_001"},
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_deduplicates_repeated_segment_ids_in_preflight_scope(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Segment Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "First caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Second caption",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "trim",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_broll_002"},
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002", "seg_001", "seg_002"],
            "fields": ["broll"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_ids"] == ["seg_002", "seg_001"]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Second caption",
            "cut_action": "trim",
            "review_required": False,
            "broll_override": {"asset_id": "asset_broll_002"},
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        },
        {
            "segment_id": "seg_001",
            "caption_text": "First caption",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        },
    ]
    assert payload["affected_output_areas"] == [
        "b-roll track",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_matches_trimmed_session_segment_ids_in_preflight_targeted_segments(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Trimmed Session Segment Id Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": " seg_001 ",
                    "caption_text": "Caption with padded session segment id",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": [" seg_001 "],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption with padded session segment id",
            "cut_action": "keep",
            "review_required": False,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_deduplicates_repeated_fields_in_preflight_scope(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Duplicate Field Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption with duplicate field request",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_broll_001"},
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption", "broll", "caption", "broll"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["fields"] == ["caption", "broll"]
    assert payload["downstream_steps"] == [
        "segment_refresh",
        "broll_refresh",
        "timeline_build",
    ]
    assert payload["affected_output_areas"] == [
        "segment copy",
        "b-roll track",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_rejects_preflight_for_unsupported_field_scope_without_creating_jobs(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Unknown Preflight Prediction Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Clean caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["unsupported_field"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 400
    assert "Unsupported partial regeneration fields: unsupported_field" in response.json()["detail"]
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_blocked_when_source_timeline_still_has_review_blockers_only(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Source Blockers Only Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_009",
                    "message": "Operator review still required.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_009",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_009",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
    ]


def test_editing_session_api_normalizes_stale_source_review_flags_shape_to_draft_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Source Review Flags Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": "stale_review_flag_container",
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_non_dict_source_review_flag_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Stale Source Review Flag Entry Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": ["stale_review_flag_entry"],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_minimal_dict_source_review_flag_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Stale Minimal Dict Source Review Flag Entries Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "legacy": "stale_review_flag_dict",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_code_only_source_review_flag_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Code Only Source Review Flag Entries Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "segment_review_required",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_unknown_code_source_review_flag_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Unknown Code Source Review Flag Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "legacy_manual_attention",
                    "segment_id": "seg_009",
                    "message": "Stale legacy blocker should not survive prediction.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_blocked_when_source_review_flag_has_valid_code_and_segment_without_message(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Source Review Flag Without Message Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_009",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
    ]


def test_editing_session_api_marks_preflight_blocked_when_source_review_flag_has_mixed_case_valid_code(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Mixed Case Source Review Flag Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                    "segment_id": "seg_009",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
    ]


def test_editing_session_api_filters_nested_segment_id_source_review_flag_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Nested Segment Id Source Review Flag Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": {"stale": "nested_segment_id"},
                    "message": "Nested stale segment id should not survive prediction.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_ignores_nested_segment_id_source_review_flag_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Nested Segment Id Source Review Flag Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": {"stale": "nested_segment_id"},
                    "message": "Nested stale segment id should not survive runtime.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "draft"
    assert result_payload["timeline"]["review_flags"] == []
    assert result_payload["timeline"]["pending_recommendations"] == []


def test_editing_session_api_marks_preflight_blocked_when_source_timeline_has_pending_recommendations_only(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Source Pending Recommendations Only Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_009",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_009",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
    ]


def test_editing_session_api_marks_preflight_blocked_when_source_timeline_has_misbucketed_applied_pending_like_recommendation(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Source Applied Bucket Pending Like Recommendation Preflight Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_009",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_009",
                    "score": 0.93,
                    "reason": "Pending-like recommendation leaked into applied bucket.",
                    "auto_apply_allowed": "false",
                    "review_required": "true",
                    "decision_state": None,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
    ]


def test_editing_session_api_normalizes_stale_source_pending_recommendations_shape_to_draft_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Stale Source Pending Recommendations Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": "stale_pending_recommendation_container",
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_non_dict_source_pending_recommendation_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Stale Source Pending Recommendation Entry Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": ["stale_pending_recommendation_entry"],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_stale_minimal_dict_source_pending_recommendation_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Stale Minimal Dict Source Pending Recommendation Entries Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_only",
                },
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []


def test_editing_session_api_filters_recommendation_id_only_source_pending_recommendation_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Recommendation Id Only Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_only",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_filters_unknown_type_source_pending_recommendation_entries_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Unknown Type Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_unknown_type",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "legacy_overlay_pick",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_preserves_mixed_case_source_pending_recommendation_type_in_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Mixed Case Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_mixed_case_tts_type",
                    "target_segment_id": "seg_009",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "selected_asset_id": "asset_tts_review_009",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve"
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_filters_approved_decision_state_source_pending_recommendation_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Approved Decision State Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_stale_approved",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 0.87,
                    "reason": "Already approved recommendation leaked into pending recommendations.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_001.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []


def test_editing_session_api_filters_legacy_applied_like_source_pending_recommendation_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Legacy Applied Like Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_legacy_applied_like",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_legacy_applied_like",
                    "score": 0.87,
                    "reason": "Legacy applied-like recommendation should not block preflight prediction.",
                    "auto_apply_allowed": "true",
                    "review_required": "false",
                    "decision_state": None,
                    "payload": {
                        "selected_asset_uri": (
                            f"local://projects/{project.project_id}/assets/generated/asset_tts_legacy_applied_like.wav"
                        )
                    },
                    "created_at": "2026-07-04T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []


def test_editing_session_api_filters_nested_target_segment_id_source_pending_recommendation_from_preflight_prediction(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Nested Target Segment Id Source Pending Recommendation Preflight Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_nested_target",
                    "target_segment_id": {"stale": "nested_target_segment_id"},
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_nested_target",
                    "score": 0.93,
                    "reason": "Nested stale target segment id should not survive prediction.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    before_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []
    assert before_jobs == after_jobs


def test_editing_session_api_ignores_nested_target_segment_id_source_pending_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Nested Target Segment Id Source Pending Recommendation Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_nested_target",
                    "target_segment_id": {"stale": "nested_target_segment_id"},
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_nested_target",
                    "score": 0.93,
                    "reason": "Nested stale target segment id should not survive runtime.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "draft"
    assert result_payload["timeline"]["pending_recommendations"] == []
    assert result_payload["timeline"]["review_flags"] == []


def test_editing_session_api_ignores_stale_minimal_dict_source_pending_recommendation_entries_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Stale Minimal Dict Source Pending Recommendation Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "legacy": "stale_pending_recommendation_dict",
                },
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "draft"
    assert result_payload["timeline"]["pending_recommendations"] == []
    assert result_payload["timeline"]["review_flags"] == []


def test_editing_session_api_deduplicates_repeated_source_pending_recommendations_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Duplicate Source Pending Recommendation Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_001",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_001",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
                {
                    "recommendation_id": "rec_tts_review_001",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_001",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "blocked"
    assert len(result_payload["timeline"]["pending_recommendations"]) == 1
    assert result_payload["timeline"]["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Awaiting operator approval.",
        }
    ]


def test_editing_session_api_deduplicates_mixed_case_source_pending_recommendations_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Mixed Case Duplicate Source Pending Recommendation Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_mixed_case_001",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_001",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
                {
                    "recommendation_id": "rec_tts_review_mixed_case_001",
                    "target_segment_id": "seg_009",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "selected_asset_id": "asset_tts_review_001",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                },
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "blocked"
    assert len(result_payload["timeline"]["pending_recommendations"]) == 1
    assert result_payload["timeline"]["pending_recommendations"][0]["recommendation_type"] == "tts_replacement"
    assert result_payload["timeline"]["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Awaiting operator approval.",
        }
    ]


def test_partial_regeneration_result_marks_review_status_blocked_when_preserved_pending_recommendation_remains(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Preserved Pending Status Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_002",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_002",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert len(result_payload["timeline"]["pending_recommendations"]) == 1
    assert result_payload["timeline"]["review_status"] == "blocked"


def test_partial_regeneration_result_preserves_source_pending_recommendation_with_default_provider_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Pending Recommendation Default Trace Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_review_missing_trace",
                    "target_segment_id": "seg_009",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_review_missing_trace",
                    "score": 0.93,
                    "reason": "Awaiting operator approval.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "blocked"
    assert result_payload["timeline"]["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Awaiting operator approval.",
        }
    ]
    assert result_payload["timeline"]["pending_recommendations"] == [
        {
            "recommendation_id": "rec_tts_review_missing_trace",
            "target_segment_id": "seg_009",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": "asset_tts_review_missing_trace",
            "score": 0.93,
            "reason": "Awaiting operator approval.",
            "auto_apply_allowed": False,
            "review_required": True,
            "decision_state": None,
            "payload": {},
            "created_at": "2026-06-29T00:00:00+00:00",
            "provider_trace": build_provider_trace(final_provider="rule_based_fallback"),
        }
    ]


def test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_remains(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Preserved Review Flag Status Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_009",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "blocked"
    assert result_payload["timeline"]["pending_recommendations"] == []
    assert result_payload["timeline"]["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Operator review required before approval or output.",
        }
    ]


def test_partial_regeneration_result_marks_review_status_blocked_when_preserved_source_review_flag_has_mixed_case_valid_code(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Partial Regeneration Mixed Case Preserved Review Flag Status Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": " TTS_REPLACEMENT_REVIEW_REQUIRED ",
                    "segment_id": "seg_009",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "blocked"
    assert result_payload["timeline"]["pending_recommendations"] == []
    assert result_payload["timeline"]["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Operator review required before approval or output.",
        }
    ]


def test_review_snapshot_deduplicates_preserved_source_review_flags_for_partial_regeneration_candidate(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Partial Regeneration Duplicate Source Review Flag Snapshot Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_009",
                },
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_009",
                    "message": "Duplicate source blocker should be deduped in candidate review snapshot.",
                },
            ],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    snapshot_response = client.get(
        f"/api/projects/{project.project_id}/review-snapshots/{payload['job_id']}",
    )
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["review_status"] == "blocked"
    assert snapshot_payload["pending_recommendations"] == []
    assert snapshot_payload["review_flags"] == [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_009",
            "message": "Operator review required before approval or output.",
        }
    ]


def test_editing_session_api_normalizes_string_false_review_required_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="String False Review Required Runtime Fallback Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption without review blocker",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": "false",
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["timeline"]["review_status"] == "draft"
    assert result_payload["timeline"]["pending_recommendations"] == []
    assert result_payload["timeline"]["review_flags"] == []


def test_editing_session_api_normalizes_invalid_cut_action_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Invalid Cut Action Runtime Fallback Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption with stale cut action",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "stale_invalid_value",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["regenerated_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Updated caption with stale cut action",
            "cut_action": "keep",
        }
    ]
    assert result_payload["timeline"]["review_status"] == "draft"


def test_editing_session_api_normalizes_invalid_target_cut_action_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Invalid Target Cut Action Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Stable caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "stale_invalid_value",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["cut_action"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["regenerated_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Stable caption",
            "cut_action": "keep",
        }
    ]


def test_editing_session_api_matches_trimmed_session_segment_ids_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Trimmed Session Segment Id Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": " seg_001 ",
                    "caption_text": "Caption updated through trimmed runtime lookup",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["regenerated_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption updated through trimmed runtime lookup",
            "cut_action": "keep",
        }
    ]


def test_editing_session_api_matches_trimmed_source_segment_ids_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Trimmed Source Segment Id Runtime Project"
    )
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": " seg_001 ",
                "text": "Original caption from stale source segment id",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption updated through trimmed source runtime lookup",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["regenerated_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption updated through trimmed source runtime lookup",
            "cut_action": "keep",
        }
    ]


def test_editing_session_api_normalizes_invalid_source_cut_action_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Invalid Source Cut Action Runtime Project"
    )
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Original caption from stale source cut action",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "stale_invalid_value",
            }
        ],
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption updated with stale source cut action",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["regenerated_segments"] == [
        {
            "segment_id": "seg_001",
            "caption_text": "Caption updated with stale source cut action",
            "cut_action": "keep",
        }
    ]


def test_editing_session_api_replaces_trimmed_stale_applied_tts_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    replacement_audio = tmp_path / "partial-regeneration-trimmed-tts.wav"
    replacement_audio.write_bytes(b"tts replacement wav")
    replacement_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(replacement_audio)},
    ).json()["asset_id"]

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    stale_selected_asset_uri = (
        f"local://projects/{project_id}/assets/generated/stale_trimmed_tts.wav"
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_stale_tts",
            "target_segment_id": "seg_001",
            "recommendation_type": " tts_replacement ",
            "selected_asset_id": "asset_stale_tts",
            "score": 1.0,
            "reason": "Stale trimmed TTS recommendation should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {
                "selected_asset_uri": stale_selected_asset_uri,
            },
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_manual_tts_seg_001", "asset_id": replacement_asset_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["tts_replacement"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    narration_track = next(
        track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    assert narration_track["clips"][0]["asset_uri"] != stale_selected_asset_uri
    assert narration_track["clips"][0]["asset_uri"].endswith("/inputs/narration/partial-regeneration-trimmed-tts.wav")
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "rec_manual_tts_seg_001"
    ]


def test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_tts_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    replacement_audio = tmp_path / "partial-regeneration-trimmed-target-segment-tts.wav"
    replacement_audio.write_bytes(b"tts replacement wav")
    replacement_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(replacement_audio)},
    ).json()["asset_id"]

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    stale_selected_asset_uri = (
        f"local://projects/{project_id}/assets/generated/stale_trimmed_target_segment_tts.wav"
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_target_segment_stale_tts",
            "target_segment_id": " seg_001 ",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": "asset_stale_tts",
            "score": 1.0,
            "reason": "Stale TTS recommendation with trimmed target segment should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {
                "selected_asset_uri": stale_selected_asset_uri,
            },
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_manual_tts_seg_001", "asset_id": replacement_asset_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["tts_replacement"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    narration_track = next(
        track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    assert narration_track["clips"][0]["asset_uri"] != stale_selected_asset_uri
    assert narration_track["clips"][0]["asset_uri"].endswith(
        "/inputs/narration/partial-regeneration-trimmed-target-segment-tts.wav"
    )
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "rec_manual_tts_seg_001"
    ]


def test_editing_session_api_replaces_mixed_case_stale_applied_tts_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    replacement_audio = tmp_path / "partial-regeneration-mixed-case-tts.wav"
    replacement_audio.write_bytes(b"tts replacement wav")
    replacement_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(replacement_audio)},
    ).json()["asset_id"]

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    stale_selected_asset_uri = (
        f"local://projects/{project_id}/assets/generated/stale_mixed_case_tts.wav"
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_mixed_case_stale_tts",
            "target_segment_id": "seg_001",
            "recommendation_type": " TTS_REPLACEMENT ",
            "selected_asset_id": "asset_stale_tts",
            "score": 1.0,
            "reason": "Stale mixed-case TTS recommendation should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {
                "selected_asset_uri": stale_selected_asset_uri,
            },
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_manual_tts_seg_001", "asset_id": replacement_asset_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["tts_replacement"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    narration_track = next(
        track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    assert narration_track["clips"][0]["asset_uri"] != stale_selected_asset_uri
    assert narration_track["clips"][0]["asset_uri"].endswith("/inputs/narration/partial-regeneration-mixed-case-tts.wav")
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "rec_manual_tts_seg_001"
    ]


def test_editing_session_api_replaces_trimmed_stale_applied_broll_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_stale_broll",
            "target_segment_id": "seg_001",
            "recommendation_type": " broll ",
            "selected_asset_id": "asset_stale_broll",
            "score": 1.0,
            "reason": "Stale trimmed B-roll recommendation should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    broll_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "broll")
    assert [clip["asset_uri"] for clip in broll_track["clips"]] == [
        f"local://projects/{project_id}/assets/asset_manual_001"
    ]
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        f"manual_broll_seg_001"
    ]


def test_editing_session_api_replaces_mixed_case_stale_applied_broll_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_mixed_case_stale_broll",
            "target_segment_id": "seg_001",
            "recommendation_type": " BROLL ",
            "selected_asset_id": "asset_stale_broll",
            "score": 1.0,
            "reason": "Stale mixed-case B-roll recommendation should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    broll_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "broll")
    assert [clip["asset_uri"] for clip in broll_track["clips"]] == [
        f"local://projects/{project_id}/assets/asset_manual_001"
    ]
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        f"manual_broll_seg_001"
    ]


def test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_broll_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_target_segment_stale_broll",
            "target_segment_id": " seg_001 ",
            "recommendation_type": "broll",
            "selected_asset_id": "asset_stale_broll",
            "score": 1.0,
            "reason": "Stale B-roll recommendation with trimmed target segment should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    broll_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "broll")
    assert [clip["asset_uri"] for clip in broll_track["clips"]] == [
        f"local://projects/{project_id}/assets/asset_manual_001"
    ]
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "manual_broll_seg_001"
    ]


def test_editing_session_api_replaces_trimmed_stale_applied_bgm_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_stale_bgm",
            "target_segment_id": "seg_001",
            "recommendation_type": " bgm ",
            "selected_asset_id": "music_stale_001",
            "score": 1.0,
            "reason": "Stale trimmed BGM recommendation should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["music"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    bgm_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "bgm")
    assert [clip["asset_uri"] for clip in bgm_track["clips"]] == [
        f"local://projects/{project_id}/music/music_manual_001"
    ]
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "manual_bgm_seg_001"
    ]


def test_editing_session_api_replaces_trimmed_target_segment_id_stale_applied_bgm_recommendation_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["applied_recommendations"] = [
        {
            "recommendation_id": "rec_trimmed_target_segment_stale_bgm",
            "target_segment_id": " seg_001 ",
            "recommendation_type": "bgm",
            "selected_asset_id": "music_stale_001",
            "score": 1.0,
            "reason": "Stale BGM recommendation with trimmed target segment should be replaced by refresh.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {},
            "created_at": "2026-07-04T00:00:00+00:00",
        }
    ]
    persisted_timeline["pending_recommendations"] = []
    persisted_timeline["review_flags"] = []
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["music"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    bgm_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "bgm")
    assert [clip["asset_uri"] for clip in bgm_track["clips"]] == [
        f"local://projects/{project_id}/music/music_manual_001"
    ]
    assert [item["recommendation_id"] for item in result_payload["timeline"]["applied_recommendations"]] == [
        "manual_bgm_seg_001"
    ]


def test_editing_session_api_matches_trimmed_source_segment_id_for_music_refresh_partial_regeneration(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "UPDATE segments SET segment_id = ? WHERE project_id = ? AND segment_id = ?",
            (" seg_001 ", project_id, "seg_001"),
        )
        connection.commit()
    finally:
        connection.close()

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["music"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{payload['job_id']}",
    )

    assert result_response.status_code == 200
    result_payload = result_response.json()
    bgm_track = next(track for track in result_payload["timeline"]["tracks"] if track["track_type"] == "bgm")
    clip_segment_ids = [clip["segment_id"] for clip in bgm_track["clips"]]
    assert "seg_001" in clip_segment_ids
    assert any(
        item["target_segment_id"] == "seg_001"
        for item in result_payload["timeline"]["applied_recommendations"]
    )


def test_editing_session_api_filters_unknown_overlay_type_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Unknown Overlay Type Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Overlay refresh caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "legacy_card",
                            "text": "stale overlay should be ignored",
                        },
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "valid image card",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    timeline_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "timelines"
        / f'{result_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
            "text": "valid image card",
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]


def test_editing_session_api_filters_assetless_image_overlay_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Assetless Image Overlay Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Overlay refresh caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_card",
                            "asset_id": "   ",
                            "text": "stale image overlay should be ignored",
                        },
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "valid image card",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    timeline_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "timelines"
        / f'{result_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
            "text": "valid image card",
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]


def test_editing_session_api_preserves_canonical_table_overlay_when_running_partial_regeneration(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Canonical Table Overlay Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Overlay refresh caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "table_overlay",
                            "text": "Revenue | Cost | Margin",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["table_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    timeline_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "timelines"
        / f'{result_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "table_overlay",
            "text": "Revenue | Cost | Margin",
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]


def test_editing_session_api_replaces_trimmed_segment_id_existing_overlay_when_running_full_overlay_refresh(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Trimmed Existing Overlay Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [
                {
                    "segment_id": " seg_001 ",
                    "overlay_type": "hook_title",
                    "text": "stale hook title should be replaced",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                }
            ],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Overlay refresh caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "fresh image card",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    timeline_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "timelines"
        / f'{result_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
            "text": "fresh image card",
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]


def test_editing_session_api_does_not_preserve_unknown_existing_overlay_type_on_targeted_overlay_rerun(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(
        name="Unknown Existing Overlay Preservation Runtime Project"
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "segments": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [
                {
                    "segment_id": "seg_001",
                    "overlay_type": "legacy_card",
                    "text": "stale preserved overlay should be dropped",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                },
                {
                    "segment_id": "seg_001",
                    "overlay_type": "image_card",
                    "asset_id": "asset_image_old",
                    "text": "old image card",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                },
            ],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Overlay refresh caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_001",
                            "text": "valid image card",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["image_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "succeeded"
    result_response = client.get(
        f"/api/projects/{project.project_id}/partial-regenerations/{payload['job_id']}",
    )
    assert result_response.status_code == 200
    result_payload = result_response.json()
    timeline_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "timelines"
        / f'{result_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    assert persisted_timeline["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
            "text": "valid image card",
            "start_sec": 0.0,
            "end_sec": 2.0,
        }
    ]


def test_editing_session_api_marks_preflight_blocked_when_target_segment_still_requires_review_only(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Target Review Only Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Needs operator review",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": True,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "selected segments already require operator review, so rerun output stays blocked",
    ]


def test_editing_session_api_marks_preflight_blocked_when_source_timeline_and_target_segment_both_keep_review_blockers(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator review still required.",
        }
    ]
    persisted_timeline["pending_recommendations"] = [
        {
            "recommendation_id": "rec_tts_review_002",
            "target_segment_id": "seg_002",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": "asset_tts_review_002",
            "score": 0.93,
            "reason": "Awaiting operator approval.",
            "auto_apply_allowed": False,
            "review_required": True,
            "payload": {},
            "created_at": "2026-06-29T00:00:00+00:00",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]


def test_editing_session_api_can_fetch_partial_regeneration_result(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    start_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )
    job_id = start_response.json()["job_id"]

    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{job_id}",
    )

    assert result_response.status_code == 200
    payload = result_response.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "succeeded"
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["fields"] == ["broll"]
    assert payload["downstream_steps"] == ["broll_refresh", "timeline_build"]
    assert payload["session_updated_at"]
    assert payload["timeline"]["timeline_id"].startswith("timeline_")
    latest_session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    assert payload["session_updated_at"] == latest_session["updated_at"]


def test_review_snapshot_api_uses_partial_regeneration_job_id_for_candidate_timeline(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Office overview tightened for smoke"},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    response = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["timeline_id"] == "timeline_002"
    assert payload["review_status"] == "blocked"
    assert payload["segments"][0]["segment_id"] == "seg_001"


def test_editing_session_api_rejects_invalid_partial_regeneration_request(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["does_not_exist"],
            "fields": ["not_a_real_field"],
        },
    )

    assert response.status_code == 400


def test_editing_session_api_rejects_partial_regeneration_when_scope_normalizes_empty(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["   "],
            "fields": ["broll"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 400
    assert before_jobs == after_jobs


def test_editing_session_api_can_fetch_visual_overlay_and_music_updates(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    visual_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/visual-overlay",
        json={"overlay_type": "image_card", "asset_id": "asset_image_001"},
    )
    music_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )
    get_response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}",
    )

    assert visual_response.status_code == 200
    assert music_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {"overlay_type": "image_card", "asset_id": "asset_image_001"}
    ]
    assert payload["segments"][0]["music_override"] == {"asset_id": "music_manual_001"}
    assert payload["history"][-2]["mutation_type"] == "visual_overlay_update"
    assert payload["history"][-1]["mutation_type"] == "music_override_update"


def test_editing_session_api_can_clear_music_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["music_override"] is None
    assert payload["history"][-1]["mutation_type"] == "music_override_clear"


def test_editing_session_api_can_patch_explanation_and_tts_mutations(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    explanation_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    tts_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": "asset_tts_001"},
    )
    get_response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}")

    assert explanation_response.status_code == 200
    assert tts_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        }
    ]
    assert payload["segments"][0]["tts_replacement"] == {
        "recommendation_id": "rec_tts_seg_001",
        "asset_id": "asset_tts_001",
    }
    assert payload["history"][-2]["mutation_type"] == "explanation_card_update"
    assert payload["history"][-1]["mutation_type"] == "tts_replacement_select"


def test_editing_session_api_can_clear_explanation_card(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["visual_overlays"] == []
    assert payload["history"][-1]["mutation_type"] == "explanation_card_remove"


def test_editing_session_api_can_clear_tts_replacement(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": "asset_tts_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["tts_replacement"] is None
    assert payload["history"][-1]["mutation_type"] == "tts_replacement_clear"


def test_editing_session_api_can_clear_image_and_table_overlays(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/image-overlay",
        json={"asset_id": "asset_image_001", "text": "Exterior reference image"},
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/table-overlay",
        json={
            "columns": ["Metric", "Value"],
            "rows": [["CTR", "4.2%"]],
            "text": "Metric | Value\nCTR | 4.2%",
        },
    )

    clear_image = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/image-overlay",
    )
    clear_table = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/table-overlay",
    )

    assert clear_image.status_code == 200
    assert clear_table.status_code == 200
    payload = clear_table.json()
    assert payload["segments"][0]["visual_overlays"] == []
    assert payload["history"][-2]["mutation_type"] == "image_overlay_remove"
    assert payload["history"][-1]["mutation_type"] == "table_overlay_remove"


def test_editing_session_api_visual_overlay_patch_preserves_existing_explanation_overlay(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/visual-overlay",
        json={"overlay_type": "image_card", "asset_id": "asset_image_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
        {
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
        },
    ]


def test_editing_session_api_can_start_partial_regeneration_for_explanation_and_tts(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    tts_audio = tmp_path / "editing-session-tts.wav"
    tts_audio.write_bytes(b"tts wav data")
    tts_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(tts_audio)},
    ).json()["asset_id"]

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": tts_asset_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["explanation_card", "tts_replacement"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["fields"] == ["explanation_card", "tts_replacement"]
    assert payload["downstream_steps"] == [
        "overlay_refresh",
        "tts_refresh",
        "timeline_build",
    ]

def test_approved_timeline_can_generate_subtitles_preview_and_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Approved Output Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    approve_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 202
    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_job_id = subtitle_response.json()["job_id"]
    preview_job_id = preview_response.json()["job_id"]
    export_job_id = export_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    subtitle_result = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job_id}")
    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert review_snapshot.status_code == 200
    assert review_snapshot.json()["review_status"] == "approved"
    assert subtitle_result.status_code == 200
    assert subtitle_result.json()["subtitle"]["format"] == "srt"
    assert subtitle_result.json()["subtitle"]["file_uri"].endswith(".srt")
    assert preview_result.status_code == 200
    assert preview_result.json()["preview"]["player_uri"].endswith(".html")
    assert preview_result.json()["preview"]["artifact_kind"] == "playable_html_preview"
    assert export_result.status_code == 200
    assert export_result.json()["export"]["subtitle_file_uri"].endswith(".srt")
    assert export_result.json()["export"]["adapter"] == "capcut_v1_port"
    assert [track["track_name"] for track in export_result.json()["export"]["capcut_tracks"]] == [
        "voiceover",
        "broll",
        "subtitle",
        "bgm",
    ]


def test_auto_cut_module_introduction_does_not_break_approved_output_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Regression Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    assert client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    ).status_code == 202
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert export_result.status_code == 200
    assert export_result.json()["status"] == "succeeded"
    assert export_result.json()["export"]["export_type"] == "capcut"


def test_auto_cut_api_registers_raw_video_and_returns_planning_payload(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(
        projects_root=tmp_path,
        auto_cut_config=AutoCutConfig(
            scene_threshold=0.275,
            blackdetect_min_duration=0.8,
            blackdetect_picture_threshold=0.91,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut API Draft"}).json()["project_id"]

    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    assert raw_asset_response.status_code == 201
    assert raw_asset_response.json()["asset_type"] == "raw_video"

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 200
    assert plan_response.json() == {
        "asset_id": raw_asset_response.json()["asset_id"],
        "storage_uri": raw_asset_response.json()["storage_uri"],
        "should_auto_cut": True,
        "scene_detection_filter": "select='gt(scene,0.275)',showinfo",
        "blackdetect_filter": "blackdetect=d=0.8:pic_th=0.91",
        "planned_segments": [
            {"start_sec": 0.0, "end_sec": 30.0},
            {"start_sec": 30.0, "end_sec": 75.0},
            {"start_sec": 75.0, "end_sec": 120.0},
        ],
        "kept_segments": [
            {
                "start_sec": 0.0,
                "end_sec": 30.0,
                "duration_sec": 30.0,
                "avg_brightness": 90.0,
                "scene_change_count": 3,
                "reasons": [],
            },
            {
                "start_sec": 30.0,
                "end_sec": 75.0,
                "duration_sec": 45.0,
                "avg_brightness": 80.0,
                "scene_change_count": 2,
                "reasons": [],
            },
            {
                "start_sec": 75.0,
                "end_sec": 120.0,
                "duration_sec": 45.0,
                "avg_brightness": 85.0,
                "scene_change_count": 4,
                "reasons": [],
            },
        ],
    }


def test_auto_cut_api_rejects_non_raw_video_assets(tmp_path: Path) -> None:
    narration_audio = tmp_path / "narration.wav"
    narration_audio.write_bytes(b"audio bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Invalid Asset Draft"}).json()["project_id"]
    narration_asset_response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(narration_audio)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": narration_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 400
    assert plan_response.json()["detail"] == "auto_cut planning requires a raw_video asset."


def test_auto_cut_api_rejects_segment_sample_boundary_mismatches(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Boundary Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 5.0, "end_sec": 35.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 35.0, "end_sec": 80.0, "avg_brightness": 80.0, "scene_change_count": 2},
            ],
        },
    )

    assert plan_response.status_code == 400
    assert plan_response.json()["detail"] == "auto_cut segment_samples must match planned segment boundaries."


def test_auto_cut_api_skips_planning_for_short_inputs(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Short Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 60.0,
            "scene_timestamps": [30.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 60.0, "avg_brightness": 90.0, "scene_change_count": 3},
            ],
        },
    )

    assert plan_response.status_code == 200
    assert plan_response.json()["should_auto_cut"] is False
    assert plan_response.json()["planned_segments"] == []
    assert plan_response.json()["kept_segments"] == []


def test_auto_cut_api_rejects_malformed_black_regions(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Black Region Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [{"start": 40.0, "end": 5.0}],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 422


def test_auto_cut_api_rejects_invalid_segment_sample_metrics(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Invalid Metrics Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": -1.0, "scene_change_count": -1},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 422


def test_gemini_key_management_api_masks_secrets_and_supports_state_changes(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Gemini API Project"}).json()["project_id"]

    create_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Primary Gemini",
            "api_key": "AIza-sample-secret-1234",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["label"] == "Primary Gemini"
    assert created["status"] == "active"
    assert created["masked_api_key"].startswith("AIza")
    assert "secret" not in json.dumps(created).lower()

    list_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert list_response.status_code == 200
    listed = list_response.json()["keys"]
    assert len(listed) == 1
    assert listed[0]["key_id"] == created["key_id"]
    assert "api_key" not in listed[0]
    assert "api_key_secret" not in listed[0]

    update_response = client.patch(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}",
        json={
            "label": "Primary Gemini Updated",
            "cheap_model": "gemini-2.5-flash",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Primary Gemini Updated"
    assert update_response.json()["cheap_model"] == "gemini-2.5-flash"

    disable_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}/disable"
    )
    enable_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}/enable"
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"
    assert enable_response.status_code == 200
    assert enable_response.json()["status"] == "active"


def test_gemini_key_api_enforces_max_ten_keys(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Gemini Limit Project"}).json()["project_id"]

    for index in range(10):
        response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json={
                "label": f"Gemini {index}",
                "api_key": f"AIza-sample-secret-{index}",
                "primary_model": "gemini-2.5-flash",
                "cheap_model": "gemini-2.5-flash-lite",
                "high_quality_model": "gemini-2.5-pro",
            },
        )
        assert response.status_code == 201

    overflow = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Gemini overflow",
            "api_key": "AIza-over-limit",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert overflow.status_code == 400
    assert "10" in overflow.json()["detail"]


def test_provider_trace_audit_endpoint_summarizes_project_fallback_usage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
            for _ in range(6)
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Gemini review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Trace Audit Gemini",
        "api_key": "AIza-trace-audit",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert payload["summary"]["total_entries"] == 6
    assert payload["summary"]["provider_counts"]["gemini"] == 6
    assert payload["summary"]["fallback_entry_count"] == 6
    assert payload["summary"]["fallback_reason_counts"]["local_provider_error"] == 6
    assert payload["summary"]["artifact_type_counts"] == {
        "segment_analysis": 1,
        "broll_recommendation": 1,
        "music_recommendation": 1,
        "review_guidance": 1,
        "preview_render": 1,
        "capcut_export": 1,
    }


def test_provider_trace_audit_endpoint_exposes_artifact_level_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202

    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert [entry["artifact_type"] for entry in entries] == [
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
        "review_guidance",
        "preview_render",
        "capcut_export",
    ]
    review_entry = next(entry for entry in entries if entry["artifact_type"] == "review_guidance")
    preview_entry = next(entry for entry in entries if entry["artifact_type"] == "preview_render")
    export_entry = next(entry for entry in entries if entry["artifact_type"] == "capcut_export")
    assert review_entry["timeline_id"].startswith("timeline_")
    assert review_entry["job_id"] == timeline_job_id
    assert review_entry["status"] == "available"
    assert review_entry["provider_trace"]["final_provider"] == "local_qwen"
    assert preview_entry["job_id"] == preview_job_id
    assert preview_entry["artifact_id"].startswith("preview_")
    assert preview_entry["status"] == "succeeded"
    assert preview_entry["source_job_id"] == timeline_job_id
    assert preview_entry["provider_trace"]["final_provider"] == "local_qwen"
    assert export_entry["job_id"] == export_job_id
    assert export_entry["artifact_id"].startswith("export_")
    assert export_entry["status"] == "succeeded"
    assert export_entry["source_job_id"] == timeline_job_id
    assert export_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_supports_timeline_job_and_artifact_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202

    unfiltered = client.get(f"/api/projects/{project_id}/provider-traces")
    timeline_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"]},
    )
    blank_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": "   ", "final_provider": ""},
    )
    job_type_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"job_type": "preview_render"},
    )
    artifact_type_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"artifact_type": "review_guidance"},
    )

    assert unfiltered.status_code == 200
    assert timeline_filtered.status_code == 200
    assert blank_filtered.status_code == 200
    assert job_type_filtered.status_code == 200
    assert artifact_type_filtered.status_code == 200
    assert len(unfiltered.json()["entries"]) == 6
    assert unfiltered.json()["direct_entries"] == unfiltered.json()["entries"]
    assert unfiltered.json()["upstream_entries"] == []
    assert len(blank_filtered.json()["entries"]) == len(unfiltered.json()["entries"])
    assert blank_filtered.json()["direct_entries"] == blank_filtered.json()["entries"]
    assert blank_filtered.json()["upstream_entries"] == []
    assert {entry["artifact_type"] for entry in timeline_filtered.json()["entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert [entry["job_id"] for entry in job_type_filtered.json()["entries"]] == [preview_job_id]
    assert [entry["artifact_type"] for entry in artifact_type_filtered.json()["entries"]] == ["review_guidance"]
    assert export_job_id not in [entry["job_id"] for entry in job_type_filtered.json()["entries"]]


def test_provider_trace_audit_endpoint_supports_provider_and_fallback_reason_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
            for _ in range(6)
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Gemini review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Trace Audit Gemini",
        "api_key": "AIza-trace-audit",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    provider_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"final_provider": "gemini"},
    )
    provider_excluded = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"final_provider": "local_qwen"},
    )
    fallback_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"fallback_reason": "local_provider_error"},
    )
    fallback_excluded = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"fallback_reason": "unexpected_runtime_failure"},
    )

    assert provider_filtered.status_code == 200
    assert provider_excluded.status_code == 200
    assert fallback_filtered.status_code == 200
    assert fallback_excluded.status_code == 200
    assert len(provider_filtered.json()["entries"]) == 6
    assert provider_excluded.json()["entries"] == []
    assert len(fallback_filtered.json()["entries"]) == 6
    assert fallback_excluded.json()["entries"] == []
    assert {entry["provider_trace"]["final_provider"] for entry in provider_filtered.json()["entries"]} == {"gemini"}
    assert all(
        "local_provider_error" in entry["provider_trace"]["fallback_reasons"]
        for entry in fallback_filtered.json()["entries"]
    )


def test_provider_trace_audit_timeline_filter_includes_failed_preview_render_for_the_same_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Filtered Failed Preview Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="preview_render provider failed"):
        runner.start_preview_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )

    assert filtered_response.status_code == 200
    filtered_entries = filtered_response.json()["entries"]
    failed_entry = next(
        entry
        for entry in filtered_entries
        if entry["status"] == "failed" and entry["job_type"] == "preview_render"
    )
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["timeline_id"] == timeline["timeline_id"]


def test_provider_trace_audit_timeline_filter_includes_failed_capcut_export_for_the_same_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Filtered Failed Export Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="capcut_export provider failed"):
        runner.start_capcut_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )

    assert filtered_response.status_code == 200
    filtered_entries = filtered_response.json()["entries"]
    failed_entry = next(
        entry
        for entry in filtered_entries
        if entry["status"] == "failed" and entry["job_type"] == "capcut_export"
    )
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["timeline_id"] == timeline["timeline_id"]


def test_provider_trace_audit_timeline_filter_include_upstream_adds_segment_broll_and_music_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    direct_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert {entry["artifact_type"] for entry in direct_filtered.json()["entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in direct_filtered.json()["direct_entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert direct_filtered.json()["upstream_entries"] == []
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["entries"]} == {
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["direct_entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["upstream_entries"]} == {
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
    }
    assert len(upstream_filtered.json()["entries"]) == (
        len(upstream_filtered.json()["direct_entries"]) + len(upstream_filtered.json()["upstream_entries"])
    )
    assert next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "preview_render"
    )["status"] == "succeeded"
    assert next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "capcut_export"
    )["status"] == "succeeded"


def test_provider_trace_audit_timeline_filter_include_upstream_supports_partial_regeneration_candidate(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Provider trace candidate upstream check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")

    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "include_upstream": "true"},
    )

    assert filtered_response.status_code == 200
    assert {entry["artifact_type"] for entry in filtered_response.json()["direct_entries"]} == {
        "review_guidance",
    }
    assert {entry["artifact_type"] for entry in filtered_response.json()["upstream_entries"]} == {
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
    }
    review_entry = next(
        entry
        for entry in filtered_response.json()["direct_entries"]
        if entry["artifact_type"] == "review_guidance"
    )
    assert review_entry["timeline_id"] == candidate_timeline_id


def test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_id(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate review guidance job lineage check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")

    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "review_guidance"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance"]
    review_entry = filtered_response.json()["entries"][0]
    assert review_entry["timeline_id"] == candidate_timeline_id
    assert review_entry["job_id"] == partial_job_id
    assert review_entry["source_job_id"] == partial_job_id


def test_provider_trace_audit_candidate_review_guidance_entry_uses_partial_regeneration_job_type(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate review guidance job type check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")

    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "review_guidance"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance"]
    review_entry = filtered_response.json()["entries"][0]
    assert review_entry["job_id"] == partial_job_id
    assert review_entry["job_type"] == "partial_regeneration"


def test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_job_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate attempt audit summary.",
                    "action_items": ["Check candidate review guidance lineage."],
                },
                raw_text='{"summary":"Candidate attempt audit summary.","action_items":["Check candidate review guidance lineage."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate attempt job truth check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")

    assert review_snapshot.status_code == 500
    assert partial_result.status_code == 200

    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "review_guidance_attempt"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance_attempt"]
    attempt_entry = filtered_response.json()["entries"][0]
    assert attempt_entry["timeline_id"] == candidate_timeline_id
    assert attempt_entry["job_id"] == partial_job_id
    assert attempt_entry["source_job_id"] == partial_job_id
    assert attempt_entry["job_type"] == "partial_regeneration"


def test_provider_trace_audit_candidate_review_guidance_attempt_entry_uses_partial_regeneration_finished_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate attempt finished_at summary.",
                    "action_items": ["Check candidate attempt finished_at lineage."],
                },
                raw_text='{"summary":"Candidate attempt finished_at summary.","action_items":["Check candidate attempt finished_at lineage."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate attempt finished_at check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert review_snapshot.status_code == 500
    assert partial_result.status_code == 200

    partial_job = next(job for job in jobs_payload if job["job_id"] == partial_job_id)
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "review_guidance_attempt"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance_attempt"]
    attempt_entry = filtered_response.json()["entries"][0]
    assert attempt_entry["job_id"] == partial_job_id
    assert attempt_entry["finished_at"] == partial_job["finished_at"]


def test_provider_trace_audit_candidate_preview_render_entry_uses_preview_created_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Preview operator copy.",
                    "action_items": ["Check the preview artifact."],
                },
                raw_text='{"summary":"Preview operator copy.","action_items":["Check the preview artifact."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate preview created_at check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{partial_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": partial_job_id},
    )

    assert approve_response.status_code == 202
    assert preview_response.status_code == 202

    preview_job_id = preview_response.json()["job_id"]
    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    assert preview_result.status_code == 200
    preview_id = preview_result.json()["preview"]["preview_id"]
    store = LocalProjectStore(tmp_path)
    preview_row = store._fetchone(
        project_id,
        """
        SELECT created_at
        FROM preview_renders
        WHERE preview_id = ?
        """,
        (preview_id,),
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "preview_render"},
    )

    assert preview_row is not None
    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["preview_render"]
    preview_entry = filtered_response.json()["entries"][0]
    assert preview_entry["job_id"] == preview_response.json()["job_id"]
    assert preview_entry["source_job_id"] == partial_job_id
    assert preview_entry["created_at"] == preview_row["created_at"]


def test_provider_trace_audit_candidate_subtitle_render_entry_uses_subtitle_created_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate subtitle created_at check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{partial_job_id}/approve")
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": partial_job_id},
    )

    assert approve_response.status_code == 202
    assert subtitle_response.status_code == 202

    subtitle_job_id = subtitle_response.json()["job_id"]
    subtitle_result = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job_id}")
    assert subtitle_result.status_code == 200
    subtitle_id = subtitle_result.json()["subtitle"]["subtitle_id"]
    store = LocalProjectStore(tmp_path)
    subtitle_row = store._fetchone(
        project_id,
        """
        SELECT created_at
        FROM subtitle_renders
        WHERE subtitle_id = ?
        """,
        (subtitle_id,),
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "subtitle_render"},
    )

    assert subtitle_row is not None
    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["subtitle_render"]
    subtitle_entry = filtered_response.json()["entries"][0]
    assert subtitle_entry["job_id"] == subtitle_job_id
    assert subtitle_entry["source_job_id"] == partial_job_id
    assert subtitle_entry["created_at"] == subtitle_row["created_at"]


def test_provider_trace_audit_candidate_capcut_export_entry_uses_export_created_at(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Export operator copy.",
                    "action_items": ["Validate the export artifact."],
                },
                raw_text='{"summary":"Export operator copy.","action_items":["Validate the export artifact."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate export created_at check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{partial_job_id}/approve")
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": partial_job_id},
    )

    assert approve_response.status_code == 202
    assert export_response.status_code == 202

    export_job_id = export_response.json()["job_id"]
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")
    assert export_result.status_code == 200
    export_id = export_result.json()["export"]["export_id"]
    store = LocalProjectStore(tmp_path)
    export_row = store._fetchone(
        project_id,
        """
        SELECT created_at
        FROM exports
        WHERE export_id = ?
        """,
        (export_id,),
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id, "artifact_type": "capcut_export"},
    )

    assert export_row is not None
    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["capcut_export"]
    export_entry = filtered_response.json()["entries"][0]
    assert export_entry["job_id"] == export_response.json()["job_id"]
    assert export_entry["source_job_id"] == partial_job_id
    assert export_entry["created_at"] == export_row["created_at"]


def test_provider_trace_audit_candidate_timeline_filter_includes_failed_preview_render_without_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate failed preview filter check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": partial_job_id},
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id},
    )

    assert preview_response.status_code == 400
    assert filtered_response.status_code == 200
    failed_entry = next(
        entry
        for entry in filtered_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "preview_render"
    )
    assert failed_entry["source_job_id"] == partial_job_id
    assert failed_entry["timeline_id"] == candidate_timeline_id


def test_provider_trace_audit_candidate_timeline_filter_includes_failed_capcut_export_without_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate failed export filter check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": partial_job_id},
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id},
    )

    assert export_response.status_code == 400
    assert filtered_response.status_code == 200
    failed_entry = next(
        entry
        for entry in filtered_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "capcut_export"
    )
    assert failed_entry["source_job_id"] == partial_job_id
    assert failed_entry["timeline_id"] == candidate_timeline_id


def test_provider_trace_audit_candidate_timeline_filter_includes_failed_subtitle_render_without_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Initial review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Initial review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Candidate review summary.",
                    "action_items": ["Approve the candidate now."],
                },
                raw_text='{"summary":"Candidate review summary.","action_items":["Approve the candidate now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Candidate failed subtitle filter check."},
    )
    partial_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )
    partial_job_id = partial_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}")
    partial_result = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}")
    assert review_snapshot.status_code == 200
    assert partial_result.status_code == 200

    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": partial_job_id},
    )
    candidate_timeline_id = partial_result.json()["timeline"]["timeline_id"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": candidate_timeline_id},
    )

    assert subtitle_response.status_code == 400
    assert filtered_response.status_code == 200
    failed_entry = next(
        entry
        for entry in filtered_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "subtitle_render"
    )
    assert failed_entry["source_job_id"] == partial_job_id
    assert failed_entry["timeline_id"] == candidate_timeline_id


def test_provider_trace_audit_timeline_filter_include_upstream_includes_failed_upstream_job(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Upstream Provenance Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    failed_broll_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.RUNNING,
    )
    failed_broll_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_broll_job["job_id"],
        status=JobStatus.FAILED,
        error_message="broll provider failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project.project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_broll_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_broll_job["job_id"],
            "source_job_id": segment_job["job_id"],
            "status": "failed",
            "finished_at": failed_broll_job["finished_at"],
            "error_message": "broll provider failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error"],
            ),
        },
    )
    music_run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BGM,
        source_job_id=segment_job["job_id"],
        recommendations=[
            {
                "recommendation_id": "bgm_rec_001",
                "target_segment_id": "seg_001",
                "selected_asset_id": None,
                "score": 0.8,
                "reason": "steady mood",
                "auto_apply_allowed": False,
                "review_required": False,
                "payload": {"provider_trace": build_provider_trace(final_provider="local_qwen")},
            }
        ],
    )
    music_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.MUSIC_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=music_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=music_run["recommendation_run_id"],
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    direct_filtered = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert direct_filtered.json()["entries"] == []
    failed_upstream = next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "broll_recommendation"
    )
    assert failed_upstream["source_job_id"] == segment_job["job_id"]
    assert failed_upstream["provider_trace"]["final_provider"] == "gemini"


def test_timeline_build_persists_exact_recommendation_job_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    music_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "music_recommendation")

    timeline_path = tmp_path / "projects" / project_id / "timelines" / f'{timeline_payload["timeline_id"]}.json'
    persisted_payload = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert persisted_payload["lineage"] == {
        "segment_analysis_job_id": segment_job_id,
        "recommendation_job_ids": [broll_job_id, music_job_id],
    }


def test_provider_trace_audit_include_upstream_uses_exact_persisted_recommendation_lineage_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    original_broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    sibling_broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    assert sibling_broll_job_id != original_broll_job_id

    direct_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert {entry["job_id"] for entry in direct_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == set()
    assert {entry["job_id"] for entry in upstream_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["upstream_entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["direct_entries"] if entry["artifact_type"] == "broll_recommendation"} == set()


def test_provider_trace_audit_include_upstream_falls_back_to_shared_segment_for_legacy_timelines_without_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    original_broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    sibling_broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    timeline_path = tmp_path / "projects" / project_id / "timelines" / f'{timeline_payload["timeline_id"]}.json'
    persisted_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_payload.pop("lineage", None)
    timeline_path.write_text(json.dumps(persisted_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert upstream_filtered.status_code == 200
    assert {entry["job_id"] for entry in upstream_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
        sibling_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["upstream_entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
        sibling_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["direct_entries"] if entry["artifact_type"] == "broll_recommendation"} == set()


def test_provider_trace_audit_include_upstream_excludes_failed_recommendation_not_in_exact_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]
    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")

    store = LocalProjectStore(tmp_path)
    failed_broll_job = store.create_job(
        project_id=project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job_id,
        status=JobStatus.RUNNING,
    )
    failed_broll_job = store.update_job(
        project_id=project_id,
        job_id=failed_broll_job["job_id"],
        status=JobStatus.FAILED,
        error_message="sibling broll failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_broll_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_broll_job["job_id"],
            "source_job_id": segment_job_id,
            "status": "failed",
            "finished_at": failed_broll_job["finished_at"],
            "error_message": "sibling broll failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error"],
            ),
        },
    )

    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert upstream_filtered.status_code == 200
    assert failed_broll_job["job_id"] not in {
        entry["job_id"]
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "broll_recommendation"
    }


def test_provider_trace_audit_timeline_filter_keeps_review_guidance_attempt_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Audit local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Audit local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "artifact_type": "review_guidance_attempt"},
    )

    assert review_snapshot.status_code == 500
    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance_attempt"]
    assert filtered_response.json()["entries"][0]["timeline_id"] == timeline_payload["timeline_id"]


def test_provider_trace_audit_timeline_filter_keeps_legacy_review_guidance_entry(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Filtered Guidance Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "operator_guidance_history": [
                {
                    "artifact_id": "timeline_001:review_guidance:001",
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="local_qwen"),
                }
            ],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"], "artifact_type": "review_guidance"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance"]
    assert filtered_response.json()["entries"][0]["timeline_id"] == timeline["timeline_id"]
    assert filtered_response.json()["entries"][0]["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_backfills_legacy_records_without_complete_trace_data(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Trace Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id=segment_job["job_id"],
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.8,
                "reason": "Matched keywords: office",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"matched_tags": ["office"]},
            }
        ],
    )
    recommendation_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=recommendation_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="broll_001",
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_path = tmp_path / "projects" / project.project_id / "timelines" / "timeline_001.json"
    timeline_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline_payload["operator_guidance"] = {
        "summary": "Legacy review guidance.",
        "action_items": ["Approve the timeline now."],
        "provider_trace": {
            "routing_mode": "local_first",
            "final_provider": "heuristic_fallback",
            "fallback_reasons": [],
        },
    }
    timeline_payload["operator_guidance_history"] = [
        {
            "artifact_id": "timeline_001:review_guidance:001",
            "created_at": timeline_payload["created_at"],
            "provider_trace": {
                "routing_mode": "local_first",
                "final_provider": "heuristic_fallback",
                "fallback_reasons": [],
            },
        }
    ]
    timeline_path.write_text(json.dumps(timeline_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    preview = store.save_preview_run(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        preview_payload={
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [],
            "notes": ["Legacy preview."],
        },
    )
    preview_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PREVIEW_RENDER,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=preview_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=preview["preview_id"],
    )
    export = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        export_payload={
            "timeline_id": timeline["timeline_id"],
            "adapter": "capcut_v1",
            "tracks": [],
            "notes": ["Legacy export."],
        },
    )
    export_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.CAPCUT_EXPORT,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=export_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=export["export_id"],
    )
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE segments SET metadata_json = '[]'")
        connection.execute("UPDATE recommendations SET payload_json = 'null'")
        connection.commit()
    finally:
        connection.close()
    preview_path = tmp_path / "projects" / project.project_id / "previews" / "preview_001.json"
    preview_payload = json.loads(preview_path.read_text(encoding="utf-8"))
    preview_payload.pop("provider_trace", None)
    preview_path.write_text(json.dumps(preview_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    export_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "exports"
        / "capcut"
        / "export_001"
        / "capcut_payload.json"
    )
    export_payload = json.loads(export_path.read_text(encoding="utf-8"))
    export_payload.pop("provider_trace", None)
    export_path.write_text(json.dumps(export_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = {entry["artifact_type"]: entry for entry in audit_response.json()["entries"]}
    assert entries["segment_analysis"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["broll_recommendation"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["review_guidance"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["preview_render"]["provider_trace"]["final_provider"] == "static_fallback"
    assert entries["capcut_export"]["provider_trace"]["final_provider"] == "static_fallback"


def test_provider_trace_audit_endpoint_tolerates_partial_artifact_and_log_corruption(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Corrupt Trace Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": {
                    "routing_mode": "local_first",
                    "final_provider": "local_qwen",
                    "fallback_reasons": [],
                },
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    preview = store.save_preview_run(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        preview_payload={
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [],
            "notes": ["Corrupt preview."],
            "provider_trace": {
                "routing_mode": "local_first",
                "final_provider": "gemini",
                "fallback_reasons": ["local_provider_error"],
            },
        },
    )
    preview_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PREVIEW_RENDER,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=preview_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=preview["preview_id"],
    )
    preview_path = tmp_path / "projects" / project.project_id / "previews" / "preview_001.json"
    preview_path.unlink()
    audit_log_path = tmp_path / "projects" / project.project_id / "logs" / "provider_trace_audit.jsonl"
    audit_log_path.write_text("{bad json}\n", encoding="utf-8")

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["artifact_type"] == "segment_analysis"
    assert entries[0]["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_includes_failed_segment_analysis_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Segment Audit Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["job_id"].startswith("segment_analysis_job_")
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["error_message"] == "local_first_router: segment provider failed"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": ["local_provider_error"],
    }


def test_provider_trace_audit_endpoint_includes_failed_gemini_fallback_recommendation_run(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Broll Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    runner = LocalPipelineRunner(store, broll_recommender=FailingBrollRecommender())

    with pytest.raises(LocalFirstStructuredGenerationError, match="broll Gemini fallback failed"):
        runner.start_broll_recommendation(
            project_id=project.project_id,
            segment_analysis_job_id=segment_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "broll_recommendation"
    )
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }
    assert failed_entry["source_job_id"] == segment_job["job_id"]
    assert failed_entry["artifact_id"] == failed_entry["job_id"]


def test_provider_trace_audit_endpoint_uses_default_trace_for_failed_provider_job_without_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Music Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    runner = LocalPipelineRunner(store, music_recommender=FailingMusicRecommenderWithoutTrace())

    with pytest.raises(RuntimeError, match="music provider exploded without trace"):
        runner.start_music_recommendation(
            project_id=project.project_id,
            segment_analysis_job_id=segment_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "music_recommendation"
    )
    success_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "succeeded" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "unknown_failure",
        "fallback_reasons": ["missing_provider_trace"],
    }
    assert failed_entry["error_message"] == "music provider exploded without trace"
    assert success_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_includes_failed_preview_render_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Preview Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="preview_render provider failed"):
        runner.start_preview_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "preview_render"
    )
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["provider_trace"]["final_provider"] == "gemini"


def test_provider_trace_audit_endpoint_includes_failed_capcut_export_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Export Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="capcut_export provider failed"):
        runner.start_capcut_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "capcut_export"
    )
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["provider_trace"]["final_provider"] == "gemini"


def test_start_segment_analysis_marks_job_failed_without_provider_trace_for_missing_source_job(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Missing Source Segment Project")
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(KeyError, match="missing_transcription_job"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id="missing_transcription_job",
            script_asset_id=None,
        )

    jobs = store.list_jobs(project_id=project.project_id)
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "segment_analysis"
    assert jobs[0]["status"] == "failed"

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    assert not [
        entry
        for entry in audit_response.json()["entries"]
        if entry["job_type"] == "segment_analysis" and entry["status"] == "failed"
    ]


def test_provider_trace_audit_endpoint_uses_authoritative_failed_run_when_audit_log_append_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Log Append Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )

    def fail_append(*, project_id: str, event: dict[str, object]) -> None:
        del project_id, event
        raise OSError("provider trace audit log offline")

    monkeypatch.setattr(store, "_append_provider_trace_audit_event", fail_append)
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["error_message"] == "local_first_router: segment provider failed"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": ["local_provider_error"],
    }


def test_provider_trace_audit_endpoint_backfills_partial_authoritative_failed_run_without_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Failed Persistence Project")
    failed_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.MUSIC_RECOMMENDATION,
        input_ref="segment_analysis_job_001",
        status=JobStatus.RUNNING,
    )
    failed_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_job["job_id"],
        status=JobStatus.FAILED,
        error_message="music provider exploded without trace",
    )

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_trace_failed_runs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                source_job_id TEXT,
                artifact_id TEXT,
                timeline_id TEXT,
                error_message TEXT,
                provider_trace_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_trace_failed_runs (
                job_id,
                project_id,
                job_type,
                source_job_id,
                artifact_id,
                timeline_id,
                error_message,
                provider_trace_json,
                created_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                failed_job["job_id"],
                project.project_id,
                "music_recommendation",
                "segment_analysis_job_001",
                failed_job["job_id"],
                None,
                "music provider exploded without trace",
                None,
                "2026-06-29T00:00:00+00:00",
                failed_job["finished_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "music_recommendation"
    )
    assert failed_entry["artifact_id"] == failed_job["job_id"]
    assert failed_entry["error_message"] == "music provider exploded without trace"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "unknown_failure",
        "fallback_reasons": ["missing_provider_trace"],
    }


def test_provider_trace_audit_endpoint_deduplicates_failed_run_between_authoritative_store_and_log(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Deduplicated Failed Run Project")
    failed_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref="segment_analysis_job_001",
        status=JobStatus.RUNNING,
    )
    failed_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_job["job_id"],
        status=JobStatus.FAILED,
        error_message="local_first_router: broll Gemini fallback failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project.project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_job["job_id"],
            "source_job_id": "segment_analysis_job_001",
            "status": "failed",
            "finished_at": failed_job["finished_at"],
            "error_message": "local_first_router: broll Gemini fallback failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        },
    )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entries = [
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_id"] == failed_job["job_id"]
    ]
    assert len(failed_entries) == 1
    assert failed_entries[0]["provider_trace"]["final_provider"] == "gemini"


def test_provider_trace_audit_endpoint_falls_back_to_log_when_authoritative_failed_run_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed SQLite Persist Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )

    def fail_authoritative_persist(*, project_id: str, event: dict[str, object]) -> None:
        del project_id, event
        raise sqlite3.OperationalError("failed runs table locked")

    monkeypatch.setattr(store, "_save_failed_provider_trace_run", fail_authoritative_persist)
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_read_path_does_not_require_failed_run_schema_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Read Only Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )

    def fail_schema_mutation(self, *, project_id: str) -> None:  # noqa: ANN001
        del self, project_id
        raise AssertionError("read path must not mutate failed-run schema")

    monkeypatch.setattr(LocalProjectStore, "_ensure_provider_trace_failed_runs_table", fail_schema_mutation)
    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["artifact_type"] == "segment_analysis"


def test_provider_trace_audit_endpoint_includes_review_guidance_attempt_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Audit local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Audit local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["job_id"] == timeline_job_id
    assert attempt_entry["source_job_id"] == timeline_job_id
    assert attempt_entry["timeline_id"]
    assert attempt_entry["status"] == "unpersisted"
    assert attempt_entry["error_message"] == "review guidance persistence offline"
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }


def test_provider_trace_audit_endpoint_reflects_heuristic_review_guidance_fallback_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_provider_trace_audit_endpoint_keeps_gemini_review_guidance_attempt_when_guidance_is_not_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Unpersisted Gemini review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Unpersisted Gemini review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Unpersisted Review Gemini",
        "api_key": "AIza-unpersisted-review",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["job_id"] == timeline_job_id
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }


def test_review_snapshot_tolerates_review_guidance_audit_append_failure_without_unpersisted_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_append(self, *, project_id: str, event: dict[str, object]) -> None:  # noqa: ANN001
        del self, project_id
        if str(event.get("artifact_type") or "") == "review_guidance":
            raise OSError("review guidance audit log offline")

    monkeypatch.setattr(LocalProjectStore, "_append_provider_trace_audit_event", fail_append)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Append failure local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Append failure local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 200
    assert audit_response.status_code == 200
    artifact_types = [entry["artifact_type"] for entry in audit_response.json()["entries"]]
    assert "review_guidance" in artifact_types
    assert "review_guidance_attempt" not in artifact_types


def test_provider_trace_audit_endpoint_deduplicates_repeated_unpersisted_review_guidance_attempts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Retry one review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Retry one review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Retry two review summary.",
                    "action_items": ["Check seg_001 narration alignment again"],
                },
                raw_text='{"summary":"Retry two review summary.","action_items":["Check seg_001 narration alignment again"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    second_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert first_snapshot.status_code == 500
    assert second_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entries = [
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    ]
    assert len(attempt_entries) == 1
