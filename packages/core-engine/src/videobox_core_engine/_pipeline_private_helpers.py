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


class _PipelinePrivateHelpersMixin:
    def _asset_payload(self, asset: Any) -> dict[str, Any]:
        return {
            "asset_id": asset.asset_id,
            "project_id": asset.project_id,
            "asset_type": asset.asset_type.value,
            "storage_uri": asset.storage_uri,
        }

    def _candidate_payload(self, candidate: Any) -> dict[str, Any]:
        return {
            "target_segment_id": candidate.target_segment_id,
            "selected_asset_id": candidate.selected_asset_id,
            "score": candidate.score,
            "reason": candidate.reason,
            "auto_apply_allowed": candidate.auto_apply_allowed,
            "review_required": candidate.review_required,
            "payload": candidate.payload,
            "provider_trace": candidate.payload.get("provider_trace"),
        }

    def _save_failed_provider_trace_audit_event(
        self,
        *,
        project_id: str,
        job: dict[str, Any],
        source_job_id: str,
        exc: Exception,
    ) -> None:
        provider_trace = getattr(exc, "provider_trace", None)
        if not isinstance(provider_trace, dict):
            provider_trace = build_provider_trace(
                final_provider="unknown_failure",
                fallback_reasons=["missing_provider_trace"],
            )
        try:
            self.store.save_provider_trace_audit_event(
                project_id=project_id,
                event={
                    "artifact_type": str(job.get("job_type") or ""),
                    "artifact_id": str(job.get("job_id") or ""),
                    "job_type": str(job.get("job_type") or ""),
                    "job_id": str(job.get("job_id") or ""),
                    "source_job_id": source_job_id,
                    "status": JobStatus.FAILED.value,
                    "finished_at": str(job.get("finished_at") or ""),
                    "error_message": str(exc),
                    "provider_trace": provider_trace,
                },
            )
        except Exception:
            # Provider audit logging should not hide the original generation failure.
            return

    def _save_review_guidance_attempt_audit_event(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        timeline_job_type: str,
        timeline_id: str,
        operator_guidance: dict[str, Any],
        error_message: str | None = None,
    ) -> None:
        try:
            self.store.save_provider_trace_audit_event(
                project_id=project_id,
                event={
                    "artifact_type": "review_guidance_attempt",
                    "artifact_id": f"{timeline_id}:review_guidance_attempt:{self.store._next_provider_trace_event_sequence(project_id=project_id):03d}",
                    "job_type": timeline_job_type,
                    "job_id": timeline_job_id,
                    "source_job_id": timeline_job_id,
                    "timeline_id": timeline_id,
                    "status": "unpersisted",
                    "error_message": error_message,
                    "provider_trace": operator_guidance.get("provider_trace")
                    or build_provider_trace(final_provider="heuristic_fallback"),
                },
            )
        except Exception:
            # Attempt-level audit should not break review guidance delivery or persistence.
            return

    def _normalize_output_copy(
        self,
        output_copy: dict[str, Any] | list[str],
    ) -> dict[str, Any]:
        if isinstance(output_copy, dict):
            notes = output_copy.get("notes")
            provider_trace = output_copy.get("provider_trace")
            return {
                "notes": [str(item) for item in notes if isinstance(item, str) and item.strip()]
                if isinstance(notes, list)
                else [],
                "provider_trace": provider_trace
                if isinstance(provider_trace, dict)
                else build_provider_trace(final_provider="static_fallback"),
            }

        return {
            "notes": [str(item) for item in output_copy if isinstance(item, str) and item.strip()],
            "provider_trace": build_provider_trace(final_provider="static_fallback"),
        }

    def _load_script_text(self, *, project_id: str, script_asset_id: str | None) -> str | None:
        if script_asset_id is None:
            return None
        asset = self.store.get_asset(project_id=project_id, asset_id=script_asset_id)
        script_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        return script_path.read_text(encoding="utf-8")

    def _load_segment_analysis_from_job(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
    ) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=segment_analysis_job_id)
        return self.store.get_segment_analysis(
            project_id=project_id,
            segment_analysis_id=job["output_ref"],
        )

    def _ensure_timeline_ready_for_output(self, timeline: dict[str, Any]) -> None:
        self._ensure_timeline_has_no_blockers(timeline)
        review_state = self.store.get_review_state(
            project_id=str(timeline["project_id"]),
            timeline_id=str(timeline["timeline_id"]),
        )
        if review_state["status"] != "approved":
            raise ValueError("Timeline requires explicit approval before preview, subtitle, or export.")

    def _ensure_timeline_has_no_blockers(self, timeline: dict[str, Any]) -> None:
        review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
        if review_flags or pending_recommendations:
            review_flag_codes = [
                f"{str(flag.get('code') or '')}@{str(flag.get('segment_id') or '')}"
                for flag in review_flags
            ]
            pending_codes = [
                (
                    f"{str(item.get('recommendation_type') or '')}:"
                    f"{str(item.get('recommendation_id') or '')}@"
                    f"{str(item.get('target_segment_id') or '')}"
                )
                for item in pending_recommendations
            ]
            raise ValueError(
                "Timeline still has review blockers. "
                f"review_flags={review_flag_codes}; "
                f"pending_recommendations={pending_codes}. "
                "Clear review flags and pending recommendations before approval or output."
            )

    def _normalized_timeline_blockers(
        self,
        timeline: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        review_flags = [
            flag
            for flag in self._normalized_timeline_review_flags(timeline)
            if _canonical_runtime_review_flag_code(flag.get("code")) in VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES
        ]
        recommendation_blocker_sources: list[Any] = []
        pending_recommendations = timeline.get("pending_recommendations", [])
        if isinstance(pending_recommendations, list):
            recommendation_blocker_sources.extend(pending_recommendations)
        applied_recommendations = timeline.get("applied_recommendations", [])
        if isinstance(applied_recommendations, list):
            recommendation_blocker_sources.extend(applied_recommendations)
        normalized_pending_recommendations = _normalized_runtime_pending_recommendations(
            recommendation_blocker_sources
        )
        return review_flags, normalized_pending_recommendations

    def _normalized_timeline_review_flags(
        self,
        timeline: dict[str, Any],
    ) -> list[dict[str, Any]]:
        review_flags = timeline.get("review_flags", [])
        normalized_review_flags: list[dict[str, Any]] = []
        existing_review_flag_keys: set[tuple[str, str]] = set()
        if isinstance(review_flags, list):
            for flag in review_flags:
                if not _is_runtime_blocking_review_flag(flag):
                    continue
                code = _canonical_runtime_review_flag_code(flag.get("code"))
                segment_id = str(flag.get("segment_id") or "").strip()
                review_flag_key = (code, segment_id)
                if review_flag_key in existing_review_flag_keys:
                    continue
                existing_review_flag_keys.add(review_flag_key)
                normalized_review_flags.append(
                    {
                        **flag,
                        "code": code,
                        "segment_id": segment_id,
                    }
                )

        for segment in timeline.get("segments", []):
            if not isinstance(segment, dict):
                continue
            segment_id = str(segment.get("segment_id") or "").strip()
            if (
                segment_id
                and _normalize_runtime_boolish(segment.get("review_required", False))
                and ("segment_review_required", segment_id) not in existing_review_flag_keys
            ):
                existing_review_flag_keys.add(("segment_review_required", segment_id))
                normalized_review_flags.append(
                    {
                        "code": "segment_review_required",
                        "segment_id": segment_id,
                        "message": "Segment requires operator review before export.",
                    }
                )
        return normalized_review_flags

    def _prepare_pending_recommendation_decision(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        recommendation_id: str,
        decision: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        job = self.store.get_job(project_id=project_id, job_id=timeline_job_id)
        if str(job.get("job_type")) == JobType.PARTIAL_REGENERATION.value:
            original_timeline = deepcopy(
                self.store.get_partial_regeneration_run(
                    project_id=project_id,
                    partial_regeneration_id=str(job["output_ref"]),
                )["timeline"]
            )
        else:
            original_timeline = deepcopy(
                self.store.get_timeline_run(project_id=project_id, timeline_id=job["output_ref"])
            )
        timeline = deepcopy(original_timeline)
        original_review_state = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(original_timeline["timeline_id"]),
        )
        original_recommendation, decided_recommendation, remaining_pending = (
            extract_pending_recommendation_decision(
                timeline=timeline,
                recommendation_id=recommendation_id,
                decision=decision,
            )
        )
        timeline["pending_recommendations"] = remaining_pending
        if decision == "approved":
            timeline["applied_recommendations"] = [
                *deepcopy(timeline.get("applied_recommendations", [])),
                decided_recommendation,
            ]
            apply_approved_recommendation_to_timeline(
                timeline=timeline,
                decided_recommendation=decided_recommendation,
            )
        timeline["recommendation_decisions"] = timeline_recommendation_decisions(
            timeline=timeline,
            recommendation_id=recommendation_id,
            decision=decision,
        )
        timeline["review_flags"] = filtered_review_flags_after_recommendation_decision(
            timeline=timeline,
            decided_recommendation=decided_recommendation,
            remaining_pending=remaining_pending,
        )
        return (
            original_timeline,
            original_review_state,
            timeline,
            original_recommendation,
            remaining_pending,
        )

    def _persist_pending_recommendation_decision(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        timeline: dict[str, Any],
        recommendation_id: str,
        auto_apply_allowed: bool,
        review_required: bool,
        decision_state: str,
        rollback_recommendation: dict[str, Any],
        original_timeline: dict[str, Any],
        original_review_status: str,
    ) -> None:
        try:
            review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
            timeline["review_flags"] = review_flags
            timeline["pending_recommendations"] = pending_recommendations
            self.store.update_timeline_run(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                timeline_payload=timeline,
            )
            job = self.store.get_job(project_id=project_id, job_id=timeline_job_id)
            if str(job.get("job_type") or "") == JobType.PARTIAL_REGENERATION.value:
                partial_regeneration_id = str(job.get("output_ref") or "").strip()
                if not partial_regeneration_id:
                    raise ValueError("Partial regeneration review decision requires an output reference.")
                self.store.update_partial_regeneration_run(
                    project_id=project_id,
                    partial_regeneration_id=partial_regeneration_id,
                    payload={"timeline": timeline},
                )
            provider_trace = rollback_recommendation.get("provider_trace")
            if not isinstance(provider_trace, dict):
                payload = rollback_recommendation.get("payload")
                provider_trace = payload.get("provider_trace") if isinstance(payload, dict) else {}
            is_editing_session_manual_recommendation = (
                isinstance(provider_trace, dict)
                and str(provider_trace.get("final_provider") or "").strip()
                == "editing_session_manual"
            )
            if not is_editing_session_manual_recommendation:
                self.store.update_recommendation_review(
                    project_id=project_id,
                    recommendation_id=recommendation_id,
                    auto_apply_allowed=auto_apply_allowed,
                    review_required=review_required,
                    decision_state=decision_state,
                )
            status = "blocked" if review_flags or pending_recommendations else "draft"
            self.store.save_review_state(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                status=status,
            )
        except Exception:
            self._rollback_recommendation_review_mutation(
                project_id=project_id,
                timeline_id=str(original_timeline["timeline_id"]),
                recommendation=rollback_recommendation,
                original_timeline=original_timeline,
                original_review_status=original_review_status,
            )
            raise

    def _rollback_recommendation_review_mutation(
        self,
        *,
        project_id: str,
        timeline_id: str,
        recommendation: dict[str, Any],
        original_timeline: dict[str, Any],
        original_review_status: str,
    ) -> None:
        try:
            self.store.update_timeline_run(
                project_id=project_id,
                timeline_id=timeline_id,
                timeline_payload=original_timeline,
            )
        except Exception as exc:
            warnings.warn(
                (
                    "Failed to roll back timeline review mutation after downstream error. "
                    f"project_id={project_id} timeline_id={timeline_id} stage=timeline error={exc}"
                ),
                stacklevel=2,
            )
        try:
            connection = self.store._connection(project_id)
            try:
                connection.execute(
                    """
                    UPDATE recommendations
                    SET auto_apply_allowed = ?, review_required = ?, decision_state = ?
                    WHERE recommendation_id = ? AND project_id = ?
                    """,
                    (
                        1 if _normalize_runtime_boolish(recommendation.get("auto_apply_allowed", False)) else 0,
                        1 if _normalize_runtime_boolish(recommendation.get("review_required", False)) else 0,
                        recommendation.get("decision_state"),
                        str(recommendation["recommendation_id"]),
                        project_id,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        except Exception as exc:
            warnings.warn(
                (
                    "Failed to roll back recommendation review mutation after downstream error. "
                    f"project_id={project_id} timeline_id={timeline_id} stage=recommendation error={exc}"
                ),
                stacklevel=2,
            )
        try:
            self.store.save_review_state(
                project_id=project_id,
                timeline_id=timeline_id,
                status=original_review_status,
            )
        except Exception as exc:
            warnings.warn(
                (
                    "Failed to roll back review state after downstream error. "
                    f"project_id={project_id} timeline_id={timeline_id} stage=review_state error={exc}"
                ),
                stacklevel=2,
            )

    def _segments_for_timeline(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> list[dict[str, Any]]:
        persisted_segments = timeline.get("caption_segments")
        if isinstance(persisted_segments, list):
            normalized_segments = []
            for segment in persisted_segments:
                if not isinstance(segment, dict):
                    continue
                normalized = deepcopy(segment)
                if not str(normalized.get("segment_id") or "").strip():
                    continue
                normalized["segment_id"] = str(normalized["segment_id"]).strip()
                normalized["text"] = str(
                    normalized.get("text")
                    or normalized.get("narration_text")
                    or normalized.get("transcript_text")
                    or normalized.get("script_text")
                    or normalized.get("summary")
                    or ""
                )
                normalized["review_required"] = _normalize_runtime_boolish(
                    normalized.get("review_required", False)
                )
                normalized_segments.append(normalized)
            if normalized_segments:
                return normalized_segments
        all_segments = self.store.list_segments(project_id=project_id)
        segment_lookup = {
            str(segment.get("segment_id") or "").strip(): segment
            for segment in all_segments
            if str(segment.get("segment_id") or "").strip()
        }
        ordered_segment_ids: list[str] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            if _canonical_runtime_track_type(track.get("track_type")) not in VALID_RUNTIME_TRACK_TYPES:
                continue
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            for clip in clips:
                if not isinstance(clip, dict):
                    continue
                segment_id = str(clip.get("segment_id") or "").strip()
                if segment_id and segment_id not in ordered_segment_ids:
                    ordered_segment_ids.append(segment_id)
        if not ordered_segment_ids:
            return all_segments
        return [segment_lookup[segment_id] for segment_id in ordered_segment_ids if segment_id in segment_lookup]

    def _execute_partial_regeneration(
        self,
        *,
        project_id: str,
        session: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        source_timeline = self.store.get_timeline_run(
            project_id=project_id,
            timeline_id=str(session["timeline_id"]),
        )
        session_segments = {
            str(segment.get("segment_id") or "").strip(): segment
            for segment in session.get("segments", [])
            if isinstance(segment, dict)
            if str(segment.get("segment_id") or "").strip()
        }
        target_segment_ids = set(request["segment_ids"])
        target_fields = set(request["fields"])
        source_segments = self._segments_for_timeline(project_id=project_id, timeline=source_timeline)
        if not source_segments:
            source_segments = [
                {
                    "segment_id": str(segment.get("segment_id") or "").strip(),
                    "text": str(segment.get("caption_text") or ""),
                    "start_sec": float(segment.get("start_sec") or 0.0),
                    "end_sec": float(segment.get("end_sec") or 0.0),
                    "confidence": 1.0,
                    "review_required": _normalize_runtime_boolish(
                        segment.get("review_required", False)
                    ),
                    "cleanup_decision": _normalize_runtime_cut_action(segment.get("cut_action")),
                }
                for segment in session.get("segments", [])
                if isinstance(segment, dict)
                if str(segment.get("segment_id") or "").strip()
            ]

        if "timeline_structure" in target_fields:
            source_by_id = {
                str(segment.get("segment_id") or "").strip(): segment
                for segment in source_segments
                if str(segment.get("segment_id") or "").strip()
            }
            structured_segments: list[dict[str, Any]] = []
            for session_segment in session.get("segments", []):
                if not isinstance(session_segment, dict):
                    continue
                segment_id = str(session_segment.get("segment_id") or "").strip()
                if not segment_id:
                    continue
                lineage = session_segment.get("lineage")
                root_segment_id = (
                    str(lineage.get("root_segment_id") or "").strip()
                    if isinstance(lineage, dict)
                    else ""
                ) or segment_id
                source_segment = source_by_id.get(root_segment_id, {})
                structured_segments.append(
                    {
                        **deepcopy(source_segment),
                        "segment_id": segment_id,
                        "text": str(session_segment.get("caption_text") or source_segment.get("text") or ""),
                        "start_sec": float(session_segment.get("start_sec") or 0.0),
                        "end_sec": float(session_segment.get("end_sec") or 0.0),
                        "cleanup_decision": _normalize_runtime_cut_action(session_segment.get("cut_action") or source_segment.get("cleanup_decision")),
                        "editing_session_lineage": deepcopy(lineage) if isinstance(lineage, dict) else {"root_segment_id": root_segment_id},
                    }
                )
            source_segments = structured_segments

        source_pending_recommendations = _normalized_runtime_pending_recommendations(
            source_timeline.get("pending_recommendations", [])
        )
        source_review_flags = [
            {
                **deepcopy(flag),
                "code": _canonical_runtime_review_flag_code(flag.get("code")),
                "segment_id": str(flag.get("segment_id") or "").strip(),
                "message": _canonical_runtime_operator_review_text(flag.get("message")),
            }
            for flag in source_timeline.get("review_flags", [])
            if _is_runtime_blocking_review_flag(flag)
            and _canonical_runtime_review_flag_code(flag.get("code"))
            in VALID_RUNTIME_BLOCKING_REVIEW_FLAG_CODES
        ]

        state = {
            "timeline_segments": deepcopy(source_segments),
            "regenerated_segments": [],
            "recommendations": deepcopy(source_timeline.get("applied_recommendations", []))
            + deepcopy(source_pending_recommendations),
            "export_overlays": deepcopy(source_timeline.get("export_overlays", [])),
        }

        for step in request["downstream_steps"]:
            if step == "segment_refresh":
                self._execute_partial_regeneration_segment_refresh_step(
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                    target_fields=target_fields,
                )
                continue
            if step == "broll_refresh":
                self._execute_partial_regeneration_broll_refresh_step(
                    project_id=project_id,
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                )
                continue
            if step == "music_refresh":
                self._execute_partial_regeneration_music_refresh_step(
                    project_id=project_id,
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                )
                continue
            if step == "sfx_refresh":
                self._execute_partial_regeneration_sfx_refresh_step(
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                )
                continue
            if step == "overlay_refresh":
                self._execute_partial_regeneration_overlay_refresh_step(
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                    target_fields=target_fields,
                )
                continue
            if step == "tts_refresh":
                self._execute_partial_regeneration_tts_refresh_step(
                    project_id=project_id,
                    state=state,
                    session_segments=session_segments,
                    target_segment_ids=target_segment_ids,
                )

        timeline = self.timeline_builder.build(
            project_id=project_id,
            segments=state["timeline_segments"],
            recommendations=state["recommendations"],
            narration_source_uri=source_timeline.get("narration_source_uri"),
            export_overlays=state["export_overlays"],
        )
        timeline_payload = {
            "project_id": timeline.project_id,
            "narration_source_uri": timeline.narration_source_uri,
            "tracks": [
                {
                    "track_id": track.track_id,
                    "track_type": track.track_type,
                    "clips": [
                        {
                            "clip_id": clip.clip_id,
                            "segment_id": clip.segment_id,
                            "asset_uri": clip.asset_uri,
                            "start_sec": clip.start_sec,
                            "end_sec": clip.end_sec,
                            "clip_type": clip.clip_type,
                            "recommendation_id": clip.recommendation_id,
                            "media_controls": clip.media_controls,
                        }
                        for clip in track.clips
                    ],
                }
                for track in timeline.tracks
            ],
            "review_flags": [
                {
                    "code": flag.code,
                    "segment_id": flag.segment_id,
                    "message": flag.message,
                }
                for flag in timeline.review_flags
            ],
            "caption_segments": timeline.caption_segments,
            "applied_recommendations": timeline.applied_recommendations,
            "pending_recommendations": timeline.pending_recommendations,
            "recommendation_decisions": timeline.recommendation_decisions,
            "export_overlays": timeline.export_overlays,
            "lineage": {
                **deepcopy(source_timeline.get("lineage", {})),
                "partial_regeneration": {
                    "session_id": request["session_id"],
                    "source_timeline_id": str(session["timeline_id"]),
                    "segment_ids": request["segment_ids"],
                    "fields": request["fields"],
                    "downstream_steps": request["downstream_steps"],
                },
            },
        }
        existing_review_flag_keys = {
            (
                _canonical_runtime_review_flag_code(item.get("code")),
                str(item.get("segment_id") or "").strip(),
            )
            for item in timeline_payload["review_flags"]
            if isinstance(item, dict)
        }
        for flag in source_review_flags:
            review_flag_key = (
                _canonical_runtime_review_flag_code(flag.get("code")),
                str(flag.get("segment_id") or "").strip(),
            )
            if review_flag_key in existing_review_flag_keys:
                continue
            existing_review_flag_keys.add(review_flag_key)
            timeline_payload["review_flags"].append(flag)
        existing_pending_keys = {
            _runtime_pending_recommendation_identity_key(item)
            for item in timeline_payload["pending_recommendations"]
            if isinstance(item, dict)
        }
        for item in source_pending_recommendations:
            pending_key = _runtime_pending_recommendation_identity_key(item)
            if pending_key in existing_pending_keys:
                continue
            existing_pending_keys.add(pending_key)
            timeline_payload["pending_recommendations"].append(deepcopy(item))
        persisted = self.store.save_timeline_run(
            project_id=project_id,
            output_mode=timeline.output_mode,
            timeline_payload=timeline_payload,
        )
        return {
            "session_id": str(session["session_id"]),
            "source_timeline_id": str(session["timeline_id"]),
            "timeline_id": persisted["timeline_id"],
            "segment_ids": request["segment_ids"],
            "fields": request["fields"],
            "downstream_steps": request["downstream_steps"],
            "regenerated_segments": state["regenerated_segments"],
            "timeline": persisted["timeline"],
        }

    def _execute_partial_regeneration_segment_refresh_step(
        self,
        *,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
        target_fields: set[str],
    ) -> None:
        regenerated_segments: list[dict[str, Any]] = []
        timeline_segments: list[dict[str, Any]] = []
        for source_segment in state["timeline_segments"]:
            segment_id = str(source_segment["segment_id"]).strip()
            session_segment = session_segments.get(segment_id)
            caption_text = str(source_segment.get("text") or "")
            cut_action = _normalize_runtime_cut_action(source_segment.get("cleanup_decision"))
            if segment_id in target_segment_ids and session_segment is not None:
                if "caption" in target_fields:
                    caption_text = str(session_segment.get("caption_text") or caption_text)
                if "cut_action" in target_fields:
                    cut_action = _normalize_runtime_cut_action(
                        session_segment.get("cut_action") or cut_action
                    )
                regenerated_segments.append(
                    {
                        "segment_id": segment_id,
                        "caption_text": caption_text,
                        "cut_action": cut_action,
                    }
                )
            if cut_action == "remove":
                continue
            timeline_segments.append(
                {
                    **source_segment,
                    "segment_id": segment_id,
                    "text": caption_text,
                    "cleanup_decision": cut_action,
                }
            )
        state["timeline_segments"] = timeline_segments
        state["regenerated_segments"] = regenerated_segments

    def _execute_partial_regeneration_broll_refresh_step(
        self,
        *,
        project_id: str,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
    ) -> None:
        state["recommendations"] = [
            item
            for item in state["recommendations"]
            if not (
                _canonical_runtime_recommendation_type(item.get("recommendation_type"))
                == RecommendationType.BROLL.value
                and str(item.get("target_segment_id") or "").strip() in target_segment_ids
            )
        ]
        manual_segment_ids: set[str] = set()
        for segment_id in sorted(target_segment_ids):
            session_segment = session_segments.get(segment_id)
            if not session_segment:
                continue
            override = session_segment.get("broll_override")
            if not isinstance(override, dict) or not str(override.get("asset_id") or "").strip():
                continue
            manual_segment_ids.add(segment_id)
            state["recommendations"].append(
                self._manual_recommendation_payload(
                    segment_id=segment_id,
                recommendation_type=RecommendationType.BROLL,
                asset_id=str(override["asset_id"]),
                reason="Manual B-roll override from editing session.",
                media_controls=override.get("media_controls"),
                )
            )

        segments_to_regenerate = [
            segment
            for segment in state["timeline_segments"]
            if str(segment.get("segment_id") or "").strip() in target_segment_ids - manual_segment_ids
        ]
        if not segments_to_regenerate:
            return
        candidates = self.broll_recommender.recommend(
            RecommendationRequest(
                project_id=project_id,
                recommendation_type=RecommendationType.BROLL,
                segments=segments_to_regenerate,
                assets=self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO),
            )
        )
        for candidate in candidates:
            recommendation = self._candidate_payload(candidate)
            recommendation["recommendation_type"] = RecommendationType.BROLL.value
            state["recommendations"].append(
                self._normalize_generated_recommendation(
                    recommendation,
                    fallback_provider="heuristic_fallback",
                )
            )

    def _execute_partial_regeneration_music_refresh_step(
        self,
        *,
        project_id: str,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
    ) -> None:
        state["recommendations"] = [
            item
            for item in state["recommendations"]
            if not (
                _canonical_runtime_recommendation_type(item.get("recommendation_type"))
                == RecommendationType.BGM.value
                and str(item.get("target_segment_id") or "").strip() in target_segment_ids
            )
        ]
        manual_segment_ids: set[str] = set()
        for segment_id in sorted(target_segment_ids):
            session_segment = session_segments.get(segment_id)
            if not session_segment:
                continue
            override = session_segment.get("music_override")
            if not isinstance(override, dict) or not str(override.get("asset_id") or "").strip():
                continue
            manual_segment_ids.add(segment_id)
            state["recommendations"].append(
                self._manual_recommendation_payload(
                    segment_id=segment_id,
                recommendation_type=RecommendationType.BGM,
                asset_id=str(override["asset_id"]),
                reason="Manual music override from editing session.",
                media_controls=override.get("media_controls"),
                )
            )

        segments_to_regenerate = [
            segment
            for segment in state["timeline_segments"]
            if str(segment.get("segment_id") or "").strip() in target_segment_ids - manual_segment_ids
        ]
        if not segments_to_regenerate:
            return
        candidates = self.music_recommender.recommend(
            RecommendationRequest(
                project_id=project_id,
                recommendation_type=RecommendationType.BGM,
                segments=segments_to_regenerate,
                assets=[],
            )
        )
        for candidate in candidates:
            recommendation = self._candidate_payload(candidate)
            recommendation["recommendation_type"] = RecommendationType.BGM.value
            state["recommendations"].append(
                self._normalize_generated_recommendation(
                    recommendation,
                    fallback_provider="rule_based_fallback",
                )
            )

    def _execute_partial_regeneration_sfx_refresh_step(
        self,
        *,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
    ) -> None:
        state["recommendations"] = [
            item for item in state["recommendations"]
            if not (
                _canonical_runtime_recommendation_type(item.get("recommendation_type")) == RecommendationType.SFX.value
                and str(item.get("target_segment_id") or "").strip() in target_segment_ids
            )
        ]
        for segment_id in sorted(target_segment_ids):
            session_segment = session_segments.get(segment_id)
            override = session_segment.get("sfx_override") if session_segment else None
            if not isinstance(override, dict) or not str(override.get("asset_id") or "").strip():
                continue
            recommendation = self._manual_recommendation_payload(
                segment_id=segment_id,
                recommendation_type=RecommendationType.SFX,
                asset_id=str(override["asset_id"]),
                reason="Manual SFX override from editing session requires operator review.",
                media_controls=override.get("media_controls"),
            )
            recommendation["auto_apply_allowed"] = False
            recommendation["review_required"] = True
            state["recommendations"].append(recommendation)

    def _execute_partial_regeneration_overlay_refresh_step(
        self,
        *,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
        target_fields: set[str],
    ) -> None:
        existing_overlays = deepcopy(state["export_overlays"])
        preserved_overlays = [
            overlay
            for overlay in existing_overlays
            if str(overlay.get("segment_id") or "").strip() not in target_segment_ids
            and _is_valid_runtime_overlay(overlay)
        ]
        refreshed_overlays: list[dict[str, Any]] = []
        refresh_all_overlay_types = "visual_overlay" in target_fields
        field_overlay_types = {
            "explanation_card": {"explanation_card"},
            "image_overlay": {"image", "image_card", "image_overlay"},
            "table_overlay": {"table_card", "table_overlay"},
        }
        for segment_id in sorted(target_segment_ids):
            session_segment = session_segments.get(segment_id)
            if not session_segment:
                continue
            targeted_overlay_types = {
                overlay_type
                for field_name, overlay_types in field_overlay_types.items()
                if field_name in target_fields
                for overlay_type in overlay_types
            }
            if not refresh_all_overlay_types:
                preserved_overlays.extend(
                    [
                        overlay
                        for overlay in existing_overlays
                        if str(overlay.get("segment_id") or "").strip() == segment_id
                        and str(overlay.get("overlay_type") or "") not in targeted_overlay_types
                        and _is_valid_runtime_overlay(overlay)
                    ]
                )
            overlays = session_segment.get("visual_overlays")
            if not isinstance(overlays, list) or not overlays:
                continue
            for overlay in overlays:
                if not _is_valid_runtime_overlay(overlay):
                    continue
                if not refresh_all_overlay_types and str(overlay.get("overlay_type") or "") not in targeted_overlay_types:
                    continue
                base_overlay = next(
                    (
                        existing
                        for existing in existing_overlays
                        if str(existing.get("segment_id") or "").strip() == segment_id
                        and str(existing.get("overlay_type") or "") == str(overlay.get("overlay_type") or "")
                    ),
                    {},
                )
                refreshed_overlays.append(
                    {
                        **base_overlay,
                        **deepcopy(overlay),
                        "segment_id": segment_id,
                        "overlay_type": str(overlay.get("overlay_type") or ""),
                        "start_sec": base_overlay.get("start_sec", session_segment.get("start_sec")),
                        "end_sec": base_overlay.get("end_sec", session_segment.get("end_sec")),
                    }
                )
        state["export_overlays"] = preserved_overlays + refreshed_overlays

    def _execute_partial_regeneration_tts_refresh_step(
        self,
        *,
        project_id: str,
        state: dict[str, Any],
        session_segments: dict[str, dict[str, Any]],
        target_segment_ids: set[str],
    ) -> None:
        state["recommendations"] = [
            item
            for item in state["recommendations"]
            if not (
                _canonical_runtime_recommendation_type(item.get("recommendation_type"))
                == RecommendationType.TTS_REPLACEMENT.value
                and str(item.get("target_segment_id") or "").strip() in target_segment_ids
            )
        ]
        for segment_id in sorted(target_segment_ids):
            session_segment = session_segments.get(segment_id)
            if not session_segment:
                continue
            selection = session_segment.get("tts_replacement")
            if not isinstance(selection, dict):
                continue
            recommendation_id = str(selection.get("recommendation_id") or "").strip()
            asset_id = str(selection.get("asset_id") or "").strip()
            if not recommendation_id or not asset_id:
                continue
            asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
            if str(asset.get("asset_type") or "") not in {
                AssetType.GENERATED_TTS_AUDIO.value,
                AssetType.NARRATION_AUDIO.value,
            }:
                raise ValueError("TTS replacement must reference a generated_tts_audio or narration_audio asset.")
            provider_trace = build_provider_trace(
                final_provider="editing_session_manual",
                routing_mode="single_provider",
            )
            state["recommendations"].append(
                {
                    "recommendation_id": recommendation_id,
                    "target_segment_id": segment_id,
                    "recommendation_type": RecommendationType.TTS_REPLACEMENT.value,
                    "selected_asset_id": asset_id,
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selection_source": "editing_session",
                        "selected_asset_uri": str(asset["storage_uri"]),
                        "provider_trace": provider_trace,
                    },
                    "created_at": self.store._now_iso(),
                    "provider_trace": provider_trace,
                }
            )

    def _manual_recommendation_payload(
        self,
        *,
        segment_id: str,
        recommendation_type: RecommendationType,
        asset_id: str,
        reason: str,
        media_controls: object = None,
    ) -> dict[str, Any]:
        provider_trace = build_provider_trace(final_provider="editing_session_manual")
        return {
            "recommendation_id": f"manual_{recommendation_type.value}_{segment_id}",
            "target_segment_id": segment_id,
            "recommendation_type": recommendation_type.value,
            "selected_asset_id": asset_id,
            "score": 1.0,
            "reason": reason,
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {"provider_trace": provider_trace, "media_controls": deepcopy(media_controls) if isinstance(media_controls, dict) else {}},
            "created_at": self.store._now_iso(),
            "provider_trace": provider_trace,
        }

    def _normalize_generated_recommendation(
        self,
        recommendation: dict[str, Any],
        *,
        fallback_provider: str,
    ) -> dict[str, Any]:
        recommendation.setdefault(
            "recommendation_id",
            f"generated_{recommendation.get('recommendation_type', 'recommendation')}_{recommendation.get('target_segment_id', 'segment')}",
        )
        recommendation.setdefault("created_at", self.store._now_iso())
        provider_trace = recommendation.get("provider_trace")
        if not isinstance(provider_trace, dict):
            provider_trace = build_provider_trace(final_provider=fallback_provider)
            recommendation["provider_trace"] = provider_trace
        payload = recommendation.get("payload")
        if not isinstance(payload, dict):
            payload = {}
            recommendation["payload"] = payload
        payload.setdefault("provider_trace", provider_trace)
        return recommendation
