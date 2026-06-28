from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_capcut_export import CapCutExportAdapter
from videobox_core_engine.preview_renderer import PreviewRenderer
from videobox_core_engine.recommenders import KeywordBrollRecommender, RuleBasedMusicRecommender
from videobox_core_engine.review_guidance import HeuristicReviewGuidanceBuilder, ReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import HeuristicSegmentAnalyzer, SegmentAnalyzer
from videobox_core_engine.timeline_builder import TimelineBuilder
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
        timeline_builder: TimelineBuilder | None = None,
        preview_renderer: PreviewRenderer | None = None,
        capcut_exporter: CapCutExportAdapter | None = None,
    ) -> None:
        self.store = store
        self.stt_provider = stt_provider or MockSTTProvider()
        self.segment_analyzer = segment_analyzer or HeuristicSegmentAnalyzer()
        self.broll_recommender = broll_recommender or KeywordBrollRecommender()
        self.music_recommender = music_recommender or RuleBasedMusicRecommender()
        self.review_guidance_builder = review_guidance_builder or HeuristicReviewGuidanceBuilder()
        self.timeline_builder = timeline_builder or TimelineBuilder()
        self.preview_renderer = preview_renderer or PreviewRenderer()
        self.capcut_exporter = capcut_exporter or CapCutExportAdapter()

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
        transcription_job = self.store.get_job(project_id=project_id, job_id=transcription_job_id)
        transcript = self.store.get_transcript(
            project_id=project_id,
            transcript_id=transcription_job["output_ref"],
        )
        script_text = self._load_script_text(project_id=project_id, script_asset_id=script_asset_id)
        segments = self.segment_analyzer.analyze(
            project_id=project_id,
            transcript_segments=transcript["segments"],
            script_text=script_text,
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.SEGMENT_ANALYSIS,
            input_ref=transcription_job_id,
            status=JobStatus.RUNNING,
        )
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
        analysis = self._load_segment_analysis_from_job(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )
        assets = self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        candidates = self.broll_recommender.recommend(
            RecommendationRequest(
                project_id=project_id,
                recommendation_type=RecommendationType.BROLL,
                segments=analysis["segments"],
                assets=assets,
            )
        )
        run = self.store.save_recommendation_run(
            project_id=project_id,
            recommendation_type=RecommendationType.BROLL,
            source_job_id=segment_analysis_job_id,
            recommendations=[self._candidate_payload(candidate) for candidate in candidates],
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.BROLL_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=run["recommendation_run_id"],
        )
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
        analysis = self._load_segment_analysis_from_job(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )
        candidates = self.music_recommender.recommend(
            RecommendationRequest(
                project_id=project_id,
                recommendation_type=RecommendationType.BGM,
                segments=analysis["segments"],
                assets=[],
            )
        )
        run = self.store.save_recommendation_run(
            project_id=project_id,
            recommendation_type=RecommendationType.BGM,
            source_job_id=segment_analysis_job_id,
            recommendations=[self._candidate_payload(candidate) for candidate in candidates],
        )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.MUSIC_RECOMMENDATION,
            input_ref=segment_analysis_job_id,
            status=JobStatus.RUNNING,
        )
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=run["recommendation_run_id"],
        )
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
        timeline = self.timeline_builder.build(
            project_id=project_id,
            segments=analysis["segments"],
            recommendations=recommendations,
        )
        timeline_payload = {
            "project_id": timeline.project_id,
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
        snapshot["operator_guidance"] = self.review_guidance_builder.build(
            project_id=project_id,
            review_snapshot=snapshot,
        )
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
            segments = self.store.list_segments(project_id=project_id)
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
