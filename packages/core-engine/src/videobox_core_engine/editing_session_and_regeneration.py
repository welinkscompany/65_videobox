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
from videobox_core_engine._pipeline_shared_helpers import (
    _build_review_guidance_reuse_key,
    _canonical_runtime_pending_recommendation_reason,
    _canonical_runtime_review_flag_message,
    _is_runtime_blocking_pending_recommendation,
    _is_runtime_blocking_review_flag,
    _is_valid_runtime_overlay,
    _normalize_runtime_cut_action,
    _normalized_runtime_pending_recommendations,
    _runtime_pending_recommendation_identity_key,
)


class EditingSessionRegenerationMixin:
    def update_editing_session_segment_caption(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        caption_text: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_caption(
            session=session,
            segment_id=segment_id,
            caption_text=caption_text,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.store.get_editing_session(project_id=project_id, session_id=session_id)

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return self.store.get_latest_editing_session(project_id=project_id)

    def update_editing_session_segment_cut_action(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        cut_action: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_cut_action(
            session=session,
            segment_id=segment_id,
            cut_action=cut_action,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def update_editing_session_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_broll_override(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def clear_editing_session_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_broll_override(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def build_editing_session_partial_regeneration_request(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        return build_partial_regeneration_request(
            session=session,
            segment_ids=segment_ids,
            fields=fields,
        )

    def start_editing_session_partial_regeneration(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        request = build_partial_regeneration_request(
            session=session,
            segment_ids=segment_ids,
            fields=fields,
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.PARTIAL_REGENERATION,
            input_ref=session_id,
            status=JobStatus.RUNNING,
        )
        try:
            result = self._execute_partial_regeneration(
                project_id=project_id,
                session=session,
                request=request,
            )
            refreshed_session = self.store.update_editing_session(
                project_id=project_id,
                session_id=session_id,
                session_payload=session,
                timeline_id=result["timeline_id"],
            )
            persisted = self.store.save_partial_regeneration_run(
                project_id=project_id,
                payload={
                    **result,
                    "session_updated_at": refreshed_session["updated_at"],
                },
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["partial_regeneration_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {
            "job_id": job["job_id"],
            "status": JobStatus.SUCCEEDED.value,
            "session_id": session_id,
            "segment_ids": request["segment_ids"],
            "fields": request["fields"],
            "downstream_steps": request["downstream_steps"],
        }

    def get_partial_regeneration_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        result = self.store.get_partial_regeneration_run(
            project_id=project_id,
            partial_regeneration_id=str(job["output_ref"]),
        )
        result["timeline"] = self._hydrate_timeline_review_status(
            project_id=project_id,
            timeline=result["timeline"],
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            **result,
        }

    def _hydrate_timeline_review_status(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> dict[str, Any]:
        review_state = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        review_flags = self._normalized_timeline_review_flags(timeline)
        blocker_review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
        applied_recommendations = timeline.get("applied_recommendations", [])
        if not isinstance(applied_recommendations, list):
            applied_recommendations = []
        else:
            applied_recommendations = [
                item
                for item in applied_recommendations
                if isinstance(item, dict)
                and _canonical_runtime_recommendation_type(item.get("recommendation_type"))
                in VALID_RESTORED_RECOMMENDATION_TYPES
                and not _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline["applied_recommendations"] = applied_recommendations
        timeline["review_flags"] = review_flags
        timeline["pending_recommendations"] = pending_recommendations
        timeline["review_status"] = (
            "blocked" if blocker_review_flags or pending_recommendations else review_state["status"]
        )
        return timeline

    def update_editing_session_segment_visual_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        overlay_type: str,
        asset_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_visual_overlay(
            session=session,
            segment_id=segment_id,
            overlay_type=overlay_type,
            asset_id=asset_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def clear_editing_session_segment_visual_overlays(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_visual_overlays(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def update_editing_session_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        title: str,
        body: str,
        text: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_explanation_card(
            session=session,
            segment_id=segment_id,
            title=title,
            body=body,
            text=text,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def remove_editing_session_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_explanation_card(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def update_editing_session_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        text: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_image_overlay(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
            text=text,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def update_editing_session_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        columns: list[str],
        rows: list[list[str]],
        text: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_table_overlay(
            session=session,
            segment_id=segment_id,
            columns=columns,
            rows=rows,
            text=text,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def remove_editing_session_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_image_overlay(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def remove_editing_session_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = remove_segment_table_overlay(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def update_editing_session_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = update_segment_music_override(
            session=session,
            segment_id=segment_id,
            asset_id=asset_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def clear_editing_session_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_music_override(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def select_editing_session_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        recommendation_id: str,
        asset_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = select_segment_tts_replacement(
            session=session,
            segment_id=segment_id,
            recommendation_id=recommendation_id,
            asset_id=asset_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

    def clear_editing_session_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        session = self.store.get_editing_session(project_id=project_id, session_id=session_id)
        updated_session = clear_segment_tts_replacement(
            session=session,
            segment_id=segment_id,
        )
        return self.store.update_editing_session(
            project_id=project_id,
            session_id=session_id,
            session_payload=updated_session,
        )

