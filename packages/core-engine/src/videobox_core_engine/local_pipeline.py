from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_capcut_export import CapCutExportAdapter
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.editing_session import (
    build_editing_session,
    build_partial_regeneration_request,
    update_segment_broll_override,
    update_segment_caption,
    update_segment_cut_action,
    update_segment_music_override,
    update_segment_visual_overlay,
)
from videobox_core_engine.output_operator_copy import (
    OutputOperatorCopyBuilder,
    StaticOutputOperatorCopyBuilder,
)
from videobox_core_engine.preview_renderer import PreviewRenderer
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.recommenders import KeywordBrollRecommender, RuleBasedMusicRecommender
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
        timeline = self.store.get_timeline_run(project_id=project_id, timeline_id=job["output_ref"])
        review_state = self.store.get_review_state(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        timeline["review_status"] = review_state["status"]
        return {"job_id": job["job_id"], "status": job["status"], "timeline": timeline}

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        timeline = self.get_timeline_result(project_id=project_id, job_id=job_id)["timeline"]
        snapshot = self.store.build_review_snapshot(
            project_id=project_id,
            timeline_id=str(timeline.get("timeline_id") or ""),
            segments=self.store.list_segments(project_id=project_id),
            recommendations=self.store.list_recommendation_rows(project_id=project_id),
            timeline_review_flags=timeline.get("review_flags", []),
        )
        persisted_operator_guidance = self.store.get_persisted_operator_guidance(
            project_id=project_id,
            timeline_id=str(timeline["timeline_id"]),
        )
        if persisted_operator_guidance is not None:
            snapshot["operator_guidance"] = persisted_operator_guidance
            return snapshot
        snapshot["operator_guidance"] = self.review_guidance_builder.build(
            project_id=project_id,
            review_snapshot=snapshot,
        )
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
                timeline_id=str(timeline["timeline_id"]),
                operator_guidance=snapshot["operator_guidance"],
                error_message=str(exc),
            )
            raise
        return snapshot

    def get_review_snapshot_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.get_review_snapshot(project_id=project_id, job_id=job_id)

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
        status = "blocked" if timeline.get("review_flags") or timeline.get("pending_recommendations") else "draft"
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
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
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
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
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
            self.store.update_job(
                project_id=project_id,
                job_id=job["job_id"],
                status=JobStatus.FAILED,
                error_message=str(exc),
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
                    "job_type": JobType.TIMELINE_BUILD.value,
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
        review_flags = timeline.get("review_flags", [])
        pending_recommendations = timeline.get("pending_recommendations", [])
        if review_flags or pending_recommendations:
            raise ValueError(
                "Timeline still has review blockers. Clear review flags and pending recommendations before approval or output."
            )

    def _segments_for_timeline(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
    ) -> list[dict[str, Any]]:
        all_segments = self.store.list_segments(project_id=project_id)
        segment_lookup = {str(segment.get("segment_id")): segment for segment in all_segments}
        ordered_segment_ids: list[str] = []
        for track in timeline.get("tracks", []):
            for clip in track.get("clips", []):
                segment_id = str(clip.get("segment_id") or "").strip()
                if segment_id and segment_id not in ordered_segment_ids:
                    ordered_segment_ids.append(segment_id)
        if not ordered_segment_ids:
            return all_segments
        return [segment_lookup[segment_id] for segment_id in ordered_segment_ids if segment_id in segment_lookup]
