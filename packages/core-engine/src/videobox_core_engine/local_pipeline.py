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
from videobox_core_engine.thumbnail_generator import ThumbnailGenerationError, generate_video_thumbnail
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
from videobox_core_engine.editing_session_and_regeneration import EditingSessionRegenerationMixin
from videobox_core_engine._pipeline_private_helpers import _PipelinePrivateHelpersMixin


class LocalPipelineRunner(EditingSessionRegenerationMixin, _PipelinePrivateHelpersMixin):
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
        auto_cut_executor: FfmpegAutoCutExecutor | None = None,
        final_renderer: FfmpegFinalRenderer | None = None,
        pycapcut_exporter: Any | None = None,
        tts_provider: Any | None = None,
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
        self.auto_cut_executor = auto_cut_executor or FfmpegAutoCutExecutor(planner=self.auto_cut_planner)
        self.final_renderer = final_renderer or FfmpegFinalRenderer(store=store)
        # No eager default: pycapcut pulls in Windows-only automation deps that
        # aren't installed by default, so this stays unset unless the caller
        # (create_app, when CapCutDraftExportConfig.enabled) explicitly injects one.
        self.pycapcut_exporter = pycapcut_exporter
        # No eager default: gtts needs network access, elevenlabs needs an API
        # key, and local_xtts needs a heavy optional install — none of these
        # should run implicitly for callers/tests that don't opt in.
        self.tts_provider = tts_provider
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
        self._try_generate_broll_thumbnail(project_id=project_id, asset=asset)
        return self._asset_payload(asset)

    def _try_generate_broll_thumbnail(self, *, project_id: str, asset: Any) -> None:
        # Best-effort: a fixture/test video that isn't real footage (or a
        # missing ffmpeg binary) shouldn't fail asset registration — the
        # picker just falls back to a text label when no thumbnail exists.
        try:
            video_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri)
            thumbnail_path = self.store.thumbnail_storage_path(project_id=project_id, asset_id=asset.asset_id)
            generate_video_thumbnail(video_path, thumbnail_path)
            self.store.update_asset_metadata(
                project_id=project_id,
                asset_id=asset.asset_id,
                metadata_patch={
                    "thumbnail_uri": self.store.thumbnail_storage_uri(
                        project_id=project_id, asset_id=asset.asset_id
                    )
                },
            )
        except ThumbnailGenerationError:
            pass

    def register_raw_video_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.RAW_VIDEO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def register_voice_sample_asset(self, *, project_id: str, source_path: Path) -> dict[str, Any]:
        asset = self.store.register_asset(
            project_id=project_id,
            asset_type=AssetType.VOICE_SAMPLE_AUDIO,
            source_path=source_path,
        )
        return self._asset_payload(asset)

    def generate_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        segment_text: str,
        voice_sample_asset_id: str,
        segment_id: str | None = None,
    ) -> dict[str, Any]:
        if self.tts_provider is None:
            raise RuntimeError(
                "TTS synthesis is not configured. Enable TTSEngineConfig and install the "
                "matching engine package (see requirements-runtime.txt)."
            )
        voice_sample_asset = self.store.get_asset(project_id=project_id, asset_id=voice_sample_asset_id)
        if voice_sample_asset["asset_type"] != AssetType.VOICE_SAMPLE_AUDIO.value:
            raise ValueError("generate_tts_replacement_candidate requires a voice_sample_audio asset.")
        voice_sample_path = self.store.resolve_storage_uri(
            project_id=project_id, storage_uri=voice_sample_asset["storage_uri"]
        )
        with tempfile.TemporaryDirectory(prefix="videobox_tts_candidate_") as raw_work_dir:
            output_path = Path(raw_work_dir) / "tts_candidate.mp3"
            tts_result = self.tts_provider.synthesize(
                TTSRequest(
                    text=segment_text,
                    voice_sample_uri=str(voice_sample_path),
                    output_path=output_path,
                )
            )
            asset = self.store.register_asset(
                project_id=project_id,
                asset_type=AssetType.GENERATED_TTS_AUDIO,
                source_path=output_path,
                metadata={"provider_name": tts_result.provider_name, "source_text": segment_text},
            )
        # Recorded as a comparable A/B candidate only when the caller
        # associates it with a segment; ad-hoc previews without a segment_id
        # still work exactly as before, just without a saved comparison row.
        if segment_id:
            self.store.save_tts_candidate(
                project_id=project_id,
                segment_id=segment_id,
                asset_id=asset.asset_id,
                source_text=segment_text,
            )
        return self._asset_payload(asset)

    def list_tts_replacement_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        return self.store.list_tts_candidates(project_id=project_id, segment_id=segment_id)

    def run_auto_cut_detection(self, *, project_id: str, raw_video_asset_id: str) -> dict[str, Any]:
        asset = self.store.get_asset(project_id=project_id, asset_id=raw_video_asset_id)
        if asset["asset_type"] != AssetType.RAW_VIDEO.value:
            raise ValueError("auto_cut detection requires a raw_video asset.")
        asset_path = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        detection = self.auto_cut_executor.run_full_detection(asset_path)
        return self.plan_auto_cut_segments(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
            total_duration=detection["total_duration"],
            scene_timestamps=detection["scene_timestamps"],
            black_regions=detection["black_regions"],
            segment_samples=detection["segment_samples"],
        )

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
            "segments": timeline.segments,
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

    def start_final_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Synchronous convenience wrapper: create the job and run it to completion
        inline. Used by direct pipeline callers/tests. Real API usage should prefer
        start_final_render_job + run_final_render_job so the HTTP request does not
        block for the full render duration."""
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.FINAL_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        self.run_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id, job=job)
        refreshed_job = self.store.get_job(project_id=project_id, job_id=job["job_id"])
        if refreshed_job["status"] == JobStatus.FAILED.value:
            raise RuntimeError(refreshed_job["error_message"])
        return {"job_id": job["job_id"], "status": refreshed_job["status"]}

    def start_final_render_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Create a RUNNING final-render job and return immediately. The caller
        (the API layer) is responsible for invoking run_final_render_job in the
        background so the HTTP request does not block for the render duration."""
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.FINAL_RENDER,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        return {"job_id": job["job_id"], "status": job["status"]}

    def run_final_render_job(self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]) -> None:
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            subtitle_file_path = (
                self.store.resolve_storage_uri(project_id=project_id, storage_uri=latest_subtitle["file_uri"])
                if latest_subtitle
                else None
            )
            with tempfile.TemporaryDirectory(prefix="videobox_final_render_") as raw_render_dir:
                render_output_path = Path(raw_render_dir) / "output.mp4"
                self.final_renderer.render_timeline_to_mp4(
                    project_id=project_id,
                    timeline=timeline,
                    output_path=render_output_path,
                    subtitle_file_path=subtitle_file_path,
                    on_progress=lambda percent: self.store.update_job_progress(
                        project_id=project_id, job_id=job["job_id"], progress_percent=percent
                    ),
                )
                persisted = self.store.save_final_render(
                    project_id=project_id,
                    timeline_id=str(timeline["timeline_id"]),
                    source_output_path=render_output_path,
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
            return
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["export_id"],
        )

    def get_final_render_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if not job["output_ref"]:
            return {"job_id": job["job_id"], "status": job["status"], "render": None}
        render = self.store.get_final_render_export(project_id=project_id, export_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "render": render}

    def start_capcut_draft_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Synchronous convenience wrapper: create the job and run it to completion
        inline. Used by direct pipeline callers/tests. Real API usage should prefer
        start_capcut_draft_export_job + run_capcut_draft_export_job so the HTTP
        request does not block for the full export duration."""
        job = self.start_capcut_draft_export_job(project_id=project_id, timeline_job_id=timeline_job_id)
        self.run_capcut_draft_export_job(
            project_id=project_id,
            timeline_job_id=timeline_job_id,
            job={"job_id": job["job_id"]},
        )
        refreshed_job = self.store.get_job(project_id=project_id, job_id=job["job_id"])
        if refreshed_job["status"] == JobStatus.FAILED.value:
            raise RuntimeError(refreshed_job["error_message"])
        return {"job_id": job["job_id"], "status": refreshed_job["status"]}

    def start_capcut_draft_export_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        """Create a RUNNING CapCut draft export job and return immediately. The
        caller (the API layer) is responsible for invoking run_capcut_draft_export_job
        in the background so the HTTP request does not block for the export duration."""
        if self.pycapcut_exporter is None:
            raise RuntimeError(
                "Real CapCut draft export is not configured. Enable CapCutDraftExportConfig "
                "and install the 'pycapcut' package (see requirements-runtime.txt)."
            )
        job = self.store.create_job(
            project_id=project_id,
            job_type=JobType.CAPCUT_DRAFT_EXPORT,
            input_ref=timeline_job_id,
            status=JobStatus.RUNNING,
        )
        return {"job_id": job["job_id"], "status": job["status"]}

    def run_capcut_draft_export_job(
        self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]
    ) -> None:
        try:
            timeline = self.get_timeline_result(project_id=project_id, job_id=timeline_job_id)["timeline"]
            self._ensure_timeline_ready_for_output(timeline)
            latest_subtitle = self.store.get_latest_subtitle_for_timeline(
                project_id=project_id,
                timeline_id=str(timeline["timeline_id"]),
            )
            subtitle_file_path = (
                self.store.resolve_storage_uri(project_id=project_id, storage_uri=latest_subtitle["file_uri"])
                if latest_subtitle
                else None
            )
            with tempfile.TemporaryDirectory(prefix="videobox_capcut_draft_") as raw_drafts_root:
                draft_path = self.pycapcut_exporter.export_timeline(
                    project_id=project_id,
                    timeline=timeline,
                    drafts_root=Path(raw_drafts_root),
                    draft_name=str(timeline["timeline_id"]),
                    subtitle_file_path=subtitle_file_path,
                )
                persisted = self.store.save_capcut_draft_export(
                    project_id=project_id,
                    timeline_id=str(timeline["timeline_id"]),
                    source_draft_path=draft_path,
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
            return
        self.store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=persisted["export_id"],
        )

    def get_capcut_draft_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if not job["output_ref"]:
            return {"job_id": job["job_id"], "status": job["status"], "export": None}
        export = self.store.get_capcut_draft_export(project_id=project_id, export_id=job["output_ref"])
        return {"job_id": job["job_id"], "status": job["status"], "export": export}

