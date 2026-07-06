from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import json
import warnings

from videobox_core_engine.canonical_boolish import (
    normalize_strict_boolish as _normalize_runtime_boolish,
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
from videobox_storage.local_project_store import LocalProjectStore


def _canonical_runtime_review_flag_message(value: object) -> str:
    message = str(value or "").strip()
    return message or "Operator review required before approval or output."


def _canonical_runtime_pending_recommendation_reason(value: object) -> str:
    reason = str(value or "").strip()
    return reason or "Operator review required before approval or output."


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
    return (
        str(item.get("recommendation_id") or "").strip(),
        str(item.get("target_segment_id") or "").strip(),
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


class LocalPipelineRunner:
    def __init__(
        self,
        store: LocalProjectStore,
        *,
        stt_provider: STTProvider | None = None,
        segment_analyzer: SegmentAnalyzer | None = None,
        broll_recommender: RecommendationProvider | None = None,
        music_recommender: RecommendationProvider | None = None,
        review_guidance_builder: ReviewGuidanceBuilder | None = None,
        output_operator_copy_builder: OutputOperatorCopyBuilder | None = None,
        timeline_builder: TimelineBuilder | None = None,
        preview_renderer: PreviewRenderer | None = None,
        capcut_exporter: CapCutExportAdapter | None = None,
        auto_cut_planner: AutoCutPlanner | None = None,
        transcript_aligner: TranscriptAligner | None = None,
    ) -> None:
        self.store = store
        self.stt_provider = stt_provider or MockSTTProvider()
        self.segment_analyzer = segment_analyzer or HeuristicSegmentAnalyzer()
        self.broll_recommender = broll_recommender or KeywordBrollRecommender()
        self.music_recommender = music_recommender or RuleBasedMusicRecommender()
        self.review_guidance_builder = review_guidance_builder or HeuristicReviewGuidanceBuilder()
        self.output_operator_copy_builder = output_operator_copy_builder or StaticOutputOperatorCopyBuilder()
        self.timeline_builder = timeline_builder or TimelineBuilder()
        self.preview_renderer = preview_renderer or PreviewRenderer()
        self.capcut_exporter = capcut_exporter or CapCutExportAdapter()
        self.auto_cut_planner = auto_cut_planner or AutoCutPlanner()
        self.transcript_aligner = transcript_aligner or HeuristicTranscriptAligner()

    def register_narration_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.NARRATION_AUDIO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def register_script_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.SCRIPT_DOCUMENT,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def register_broll_asset(
        self,
        *,
        project_id: str,
        source_path: Path,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.BROLL_VIDEO,
            source_path=source_path,
            metadata={"title": title or source_path.stem, "tags": tags or []},
        )
        return self._asset_payload(asset)

    def register_raw_video_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.RAW_VIDEO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def plan_auto_cut_segments(
        self,
        *,
        project_id: str,
        raw_video_asset_id: str,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
        segment_samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        asset = self.store.get_asset(project_id=project_id, asset_id=raw_video_asset_id)
        if asset["asset_type"] != AssetType.RAW_VIDEO.value:
            raise ValueError("auto_cut planning requires a raw_video asset.")

        should_auto_cut = self.auto_cut_planner.should_auto_cut(total_duration=total_duration)
        planned_segments = (
            self.auto_cut_planner.plan_segments(
                total_duration=total_duration,
                scene_timestamps=scene_timestamps,
                black_regions=black_regions,
            )
            if should_auto_cut
            else []
        )
        if should_auto_cut:
            planned_boundaries = sorted(
                (round(segment.start_sec, 2), round(segment.end_sec, 2))
                for segment in planned_segments
            )
            sample_boundaries = sorted(
                (round(float(sample["start_sec"]), 2), round(float(sample["end_sec"]), 2))
                for sample in segment_samples
            )
            if sample_boundaries != planned_boundaries:
                raise ValueError("auto_cut segment_samples must match planned segment boundaries.")
        kept_segments = (
            sorted(
                self.auto_cut_planner.filter_segments(segment_samples),
                key=lambda segment: (segment.start_sec, segment.end_sec),
            )
            if should_auto_cut
            else []
        )
        return {
            "asset_id": asset["asset_id"],
            "storage_uri": asset["storage_uri"],
            "should_auto_cut": should_auto_cut,
            "scene_detection_filter": self.auto_cut_planner.build_scene_detection_filter(),
            "blackdetect_filter": self.auto_cut_planner.build_blackdetect_filter(),
            "planned_segments": [
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                }
                for segment in planned_segments
            ],
            "kept_segments": [
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "duration_sec": segment.duration_sec,
                    "avg_brightness": segment.avg_brightness,
                    "scene_change_count": segment.scene_change_count,
                    "reasons": list(segment.reasons),
                }
                for segment in kept_segments
            ],
        }

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.TRANSCRIPTION,
            input_ref=narration_asset_id,
            status=JobStatus.RUNNING,
        )
        asset = self.store.get_asset(project_id=project_id, asset_id=narration_asset_id)
        asset_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        stt_result = self.stt_provider.transcribe(STTRequest(source_path=asset_path))
        transcript = self.store.save_transcript(
            project_id=project_id,
            source_asset_id=narration_asset_id,
            transcript_text=stt_result.text,
            segments=[
                {
                    "start_sec": segment.start_sec,
                    "end_sec": segment.end_sec,
                    "text": segment.text,
                    "confidence": segment.confidence,
                }
                for segment in stt_result.segments
            ],
            provider_name=stt_result.provider_name,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=transcript["transcript_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_transcription_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        transcript = self.store.get_transcript(project_id=project_id, transcript_id=job["output_ref"])
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "transcript_id": transcript["transcript_id"],
            "transcript_uri": transcript["transcript_uri"],
            "transcript_text": transcript["transcript_text"],
            "segments": transcript["segments"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SEGMENT_ANALYSIS,
            input_ref=transcription_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            transcription_job = self.store.get_job(project_id=project_id, job_id=transcription_job_id)
            transcript = self.store.get_transcript(
                project_id=project_id,
                transcript_id=transcription_job["output_ref"],
            )
            script_text = self._load_script_text(project_id=project_id, script_asset_id=script_asset_id)
            aligned_transcript_segments = self.transcript_aligner.align(
                transcript_segments=transcript["segments"],
                script_text=script_text,
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            segments = self.segment_analyzer.analyze(
                project_id=project_id,
                transcript_segments=aligned_transcript_segments,
                script_text=script_text,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=transcription_job_id,
                exc=exc,
            )
            raise
        try:
            analysis = self.store.save_segment_analysis(
                project_id=project_id,
                transcript_id=transcript["transcript_id"],
                script_asset_id=script_asset_id,
                segments=segments,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=analysis["segment_analysis_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_segment_analysis_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        analysis = self.store.get_segment_analysis(
            project_id=project_id,
            segment_analysis_id=job["output_ref"],
        )
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "segment_analysis_id": analysis["segment_analysis_id"],
            "segments": analysis["segments"],
            "file_uri": analysis["file_uri"],
        }

    def start_broll_recommendation(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.BROLL_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            analysis = self._load_segment_analysis_from_job(
                project_id=project_id,
                segment_analysis_job_id=segment_analysis_job_id,
            )
            assets = self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            candidates = self.broll_recommender.recommend(
                RecommendationRequest(
                    project_id=project_id,
                    recommendation_type=RecommendationType.BROLL,
                    segments=analysis["segments"],
                    assets=assets,
                )
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=segment_analysis_job_id,
                exc=exc,
            )
            raise
        try:
            run = self.store.save_recommendation_run(
                project_id=project_id,
                recommendation_type=RecommendationType.BROLL,
                source_job_id=segment_analysis_job_id,
                recommendations=[self._candidate_payload(candidate) for candidate in candidates],
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=run["recommendation_run_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_broll_recommendation_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        run = self.store.get_recommendation_run(
            project_id=project_id,
            recommendation_run_id=job["output_ref"],
            recommendation_type=RecommendationType.BROLL,
        )
        return {"job_id": job["job_id"], "status": job["status"], "recommendations": run["recommendations"]}

    def start_music_recommendation(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
    ) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.MUSIC_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            analysis = self._load_segment_analysis_from_job(
                project_id=project_id,
                segment_analysis_job_id=segment_analysis_job_id,
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        try:
            candidates = self.music_recommender.recommend(
                RecommendationRequest(
                    project_id=project_id,
                    recommendation_type=RecommendationType.BGM,
                    segments=analysis["segments"],
                    assets=[],
                )
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=segment_analysis_job_id,
                exc=exc,
            )
            raise
        try:
            run = self.store.save_recommendation_run(
                project_id=project_id,
                recommendation_type=RecommendationType.BGM,
                source_job_id=segment_analysis_job_id,
                recommendations=[self._candidate_payload(candidate) for candidate in candidates],
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=run["recommendation_run_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_music_recommendation_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        run = self.store.get_recommendation_run(
            project_id=project_id,
            recommendation_run_id=job["output_ref"],
            recommendation_type=RecommendationType.BGM,
        )
        return {"job_id": job["job_id"], "status": job["status"], "recommendations": run["recommendations"]}

    def build_timeline(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        analysis = self._load_segment_analysis_from_job(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )
        recommendations: list[dict[str, Any]] = []
        for recommendation_job_id in recommendation_job_ids:
            job = self.store.get_job(project_id=project_id, job_id=recommendation_job_id)
            job_type = str(job["job_type"])
            recommendation_type = (
                RecommendationType.BROLL
                if job_type == JobType.BROLL_RECOMMENDATION.value
                else RecommendationType.BGM
            )
            run = self.store.get_recommendation_run(
                project_id=project_id,
                recommendation_run_id=job["output_ref"],
                recommendation_type=recommendation_type,
            )
            recommendations.extend(
                [
                    {
                        **item,
                        "recommendation_type": recommendation_type.value,
                    }
                    for item in run["recommendations"]
                ]
            )
        transcript = self.store.get_transcript(
            project_id=project_id,
            transcript_id=str(analysis["transcript_id"]),
        )
        narration_asset = self.store.get_asset(
            project_id=project_id,
            asset_id=str(transcript["source_asset_id"]),
        )
        timeline = self.timeline_builder.build(
            project_id=project_id,
            segments=analysis["segments"],
            recommendations=recommendations,
            narration_source_uri=str(narration_asset["storage_uri"]),
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
            "applied_recommendations": timeline.applied_recommendations,
            "pending_recommendations": timeline.pending_recommendations,
            "recommendation_decisions": timeline.recommendation_decisions,
            "export_overlays": timeline.export_overlays,
            "lineage": {
                "segment_analysis_job_id": segment_analysis_job_id,
                "recommendation_job_ids": recommendation_job_ids,
            },
        }
        persisted = self.store.save_timeline_run(
            project_id=project_id,
            output_mode=timeline.output_mode,
            timeline_payload=timeline_payload,
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.TIMELINE_BUILD,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["timeline_id"],
        )
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def create_editing_session(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        segments = self._segments_for_timeline(project_id=project_id, timeline=timeline)
        session_payload = build_editing_session(
            project_id=project_id,
            timeline=timeline,
            segments=segments,
        )
        return self.store.save_editing_session(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            session_payload=session_payload,
        )

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

    def start_timeline_build(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        return self.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
            recommendation_job_ids=recommendation_job_ids,
        )

    def get_timeline_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if str(job.get("job_type")) == JobType.PARTIAL_REGENERATION.value:
            partial_regeneration = self.store.get_partial_regeneration_run(
                project_id=project_id,
                partial_regeneration_id=str(job["output_ref"]),
            )
            timeline = partial_regeneration["timeline"]
        else:
            timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=job["output_ref"])
        timeline = self._hydrate_timeline_review_status(project_id=project_id, timeline=timeline)
        return {"job_id": job["job_id"], "status": job["status"], "timeline": timeline}

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        timeline = self.get_timeline_result(project_id=project_id, job_id=job_id)["timeline"]
        timeline_applied_recommendations = timeline.get("applied_recommendations", [])
        if not isinstance(timeline_applied_recommendations, list):
            timeline_applied_recommendations = []
        else:
            timeline_applied_recommendations = [
                item
                for item in timeline_applied_recommendations
                if isinstance(item, dict) and not _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline_pending_recommendations = timeline.get("pending_recommendations", [])
        if not isinstance(timeline_pending_recommendations, list):
            timeline_pending_recommendations = []
        else:
            timeline_pending_recommendations = [
                item
                for item in timeline_pending_recommendations
                if _is_runtime_blocking_pending_recommendation(item)
            ]
        timeline_review_flags = timeline.get("review_flags", [])
        if not isinstance(timeline_review_flags, list):
            timeline_review_flags = []
        else:
            timeline_review_flags = [
                item for item in timeline_review_flags if _is_runtime_blocking_review_flag(item)
            ]
        snapshot = self.store.build_review_snapshot(
            project_id=project_id,
            timeline_id=str(timeline.get("timeline_id") or ""),
            segments=self.store.list_segments(project_id=project_id),
            timeline_applied_recommendations=deepcopy(timeline_applied_recommendations),
            timeline_pending_recommendations=deepcopy(timeline_pending_recommendations),
            timeline_review_flags=timeline_review_flags,
        )
        snapshot["review_status"] = timeline["review_status"]
        current_review_status = _canonical_runtime_review_status(
            timeline["review_status"],
            default="draft",
        )
        current_operator_guidance_reuse_key = _build_review_guidance_reuse_key(snapshot)
        persisted_review_status = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )["status"]
        persisted_operator_guidance = self.store.get_persisted_operator_guidance(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        persisted_operator_guidance_reuse_key = None
        get_operator_guidance_reuse_key = getattr(
            self.store,
            "get_operator_guidance_reuse_key",
            None,
        )
        if callable(get_operator_guidance_reuse_key):
            persisted_operator_guidance_reuse_key = get_operator_guidance_reuse_key(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
        should_reuse_persisted_guidance = (
            persisted_operator_guidance is not None and current_review_status == persisted_review_status
        )
        if should_reuse_persisted_guidance and current_review_status == "blocked":
            should_reuse_persisted_guidance = (
                current_operator_guidance_reuse_key is not None
                and persisted_operator_guidance_reuse_key == current_operator_guidance_reuse_key
            )
        if should_reuse_persisted_guidance:
            snapshot["operator_guidance"] = persisted_operator_guidance
            return snapshot
        snapshot["operator_guidance"] = self.review_guidance_builder.build(
            project_id=project_id,
            review_snapshot=snapshot,
        )
        if current_review_status != persisted_review_status:
            return snapshot
        try:
            self.store.save_operator_guidance(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                operator_guidance=snapshot["operator_guidance"],
            )
        except Exception as exc:
            self._save_review_guidance_attempt_audit_event(
                project_id=project_id,
                timeline_job_id=job_id,
                timeline_job_type=str(job.get("job_type") or JobType.TIMELINE_BUILD.value),
                timeline_id=str(timeline["timeline_id"]),
                operator_guidance=snapshot["operator_guidance"],
                error_message=str(exc),
            )
            raise
        if current_operator_guidance_reuse_key is not None:
            save_operator_guidance_reuse_key = getattr(
                self.store,
                "save_operator_guidance_reuse_key",
                None,
            )
            if callable(save_operator_guidance_reuse_key):
                try:
                    save_operator_guidance_reuse_key(
                        project_id=project_id,
                        timeline_id=str(timeline["timeline_id"]),
                        reuse_key=current_operator_guidance_reuse_key,
                    )
                except Exception:
                    pass
        return snapshot

    def get_review_snapshot_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.get_review_snapshot(project_id=project_id, job_id=job_id)

    def approve_pending_recommendation(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        (
            original_timeline,
            original_review_state,
            timeline,
            original_recommendation,
            _,
        ) = self._prepare_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            recommendation_id=recommendation_id,
            decision="approved",
        )
        self._persist_pending_recommendation_decision(
            project_id=project_id,
            timeline=timeline,
            recommendation_id=recommendation_id,
            auto_apply_allowed=True,
            review_required=False,
            decision_state="approved",
            rollback_recommendation=original_recommendation,
            original_timeline=original_timeline,
            original_review_status=str(original_review_state["status"]),
        )
        return self.get_review_snapshot(project_id=project_id, job_id=timeline_job_id)

    def reject_pending_recommendation(
        self,
        *,
        project_id: str,
        timeline_job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        (
            original_timeline,
            original_review_state,
            timeline,
            original_recommendation,
            _,
        ) = self._prepare_pending_recommendation_decision(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            recommendation_id=recommendation_id,
            decision="rejected",
        )
        self._persist_pending_recommendation_decision(
            project_id=project_id,
            timeline=timeline,
            recommendation_id=recommendation_id,
            auto_apply_allowed=False,
            review_required=False,
            decision_state="rejected",
            rollback_recommendation=original_recommendation,
            original_timeline=original_timeline,
            original_review_status=str(original_review_state["status"]),
        )
        return self.get_review_snapshot(project_id=project_id, job_id=timeline_job_id)

    def approve_timeline_review(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        self._ensure_timeline_has_no_blockers(timeline)
        return self.store.save_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            status="approved",
        )

    def reopen_timeline_review(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
        review_flags, pending_recommendations = self._normalized_timeline_blockers(timeline)
        status = "blocked" if review_flags or pending_recommendations else "draft"
        return self.store.save_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
            status=status,
        )

    def start_subtitle_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SUBTITLE_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            segments = self._segments_for_timeline(project_id=project_id, timeline=timeline)
            subtitle_payload = {
                "format": "srt",
                "entries": [
                    {
                        "index": index,
                        "start_sec": float(segment["start_sec"]),
                        "end_sec": float(segment["end_sec"]),
                        "text": str(segment["text"]),
                    }
                    for index, segment in enumerate(segments, start=1)
                ],
                "notes": ["Subtitle file generated from approved review timeline."],
            }
            persisted = self.store.save_subtitle_run(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                subtitle_payload=subtitle_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["subtitle_id"],
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_subtitle_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        subtitle = self.store.get_subtitle_run(project_id=project_id, subtitle_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "subtitle": subtitle}

    def start_preview_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.PREVIEW_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            preview_payload = self.preview_renderer.build_preview_payload(
                project_id=project_id,
                timeline=timeline,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self.output_operator_copy_builder.build(
                project_id=project_id,
                timeline=timeline,
                output_target=JobType.PREVIEW_RENDER.value,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self._normalize_output_copy(output_copy)
            preview_payload["notes"] = output_copy["notes"]
            preview_payload["provider_trace"] = output_copy["provider_trace"]
            persisted = self.store.save_preview_run(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                preview_payload=preview_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["preview_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_preview_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        preview = self.store.get_preview_run(project_id=project_id, preview_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "preview": preview}

    def start_capcut_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.CAPCUT_EXPORT,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            export_payload = self.capcut_exporter.build_payload(
                project_id=project_id,
                timeline=timeline,
                subtitle_file_uri=latest_subtitle["file_uri"] if latest_subtitle else None,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self.output_operator_copy_builder.build(
                project_id=project_id,
                timeline=timeline,
                output_target=JobType.CAPCUT_EXPORT.value,
                subtitle_file_uri=latest_subtitle["file_uri"] if latest_subtitle else None,
            )
        except Exception as exc:
            failed_job = self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            self._save_failed_provider_trace_audit_event(
                project_id=project_id,
                job=failed_job,
                source_job_id=timeline_job_id,
                exc=exc,
            )
            raise
        try:
            output_copy = self._normalize_output_copy(output_copy)
            export_payload["notes"] = output_copy["notes"]
            export_payload["provider_trace"] = output_copy["provider_trace"]
            persisted = self.store.save_capcut_export(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
                export_payload=export_payload,
            )
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.SUCCEEDED,
                output_ref=persisted["export_id"],
            )
        except Exception as exc:
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
            )
            raise
        return {"job_id": job["job_id"], "status": JobStatus.SUCCEEDED.value}

    def get_capcut_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        export = self.store.get_export_run(project_id=project_id, export_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "export": export}

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

        source_pending_recommendations = _normalized_runtime_pending_recommendations(
            source_timeline.get("pending_recommendations", [])
        )
        source_review_flags = [
            {
                **deepcopy(flag),
                "code": _canonical_runtime_review_flag_code(flag.get("code")),
                "segment_id": str(flag.get("segment_id") or "").strip(),
                "message": str(flag.get("message") or "").strip()
                or "Operator review required before approval or output.",
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
            "payload": {"provider_trace": provider_trace},
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
