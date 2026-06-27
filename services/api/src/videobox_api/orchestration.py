from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


@dataclass(slots=True, frozen=True)
class RegisteredAsset:
    asset_id: str
    asset_type: str
    storage_uri: str


class ApiOrchestrator:
    def __init__(self, store: LocalProjectStore) -> None:
        self.pipeline = LocalPipelineRunner(store)

    def register_narration_audio(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_narration_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_script_document(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_script_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_broll_asset(
        self,
        *,
        project_id: str,
        source_path: Path,
        title: str | None,
        tags: list[str],
    ) -> RegisteredAsset:
        asset = self.pipeline.register_broll_asset(
            project_id=project_id,
            source_path=source_path,
            title=title,
            tags=tags,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        result = self.pipeline.start_transcription(
            project_id=project_id,
            narration_asset_id=narration_asset_id,
        )
        transcription = self.pipeline.get_transcription_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": transcription["transcript_uri"],
        }

    def get_transcription_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_transcription_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": result["transcript_uri"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        result = self.pipeline.start_segment_analysis(
            project_id=project_id,
            transcription_job_id=transcription_job_id,
            script_asset_id=script_asset_id,
        )
        analysis = self.pipeline.get_segment_analysis_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments_uri": analysis["file_uri"],
        }

    def get_segment_analysis_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_segment_analysis_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments": result["segments"],
        }

    def start_broll_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_broll_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_broll_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_broll_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "broll",
            "recommendations": result["recommendations"],
        }

    def start_music_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_music_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_music_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_music_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "bgm",
            "recommendations": result["recommendations"],
        }

    def build_timeline(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        return self.pipeline.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
            recommendation_job_ids=recommendation_job_ids,
        )

    def get_timeline_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_timeline_result(project_id=project_id, job_id=job_id)

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_review_snapshot(project_id=project_id, job_id=job_id)

    def start_preview_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_preview_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_preview_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_preview_result(project_id=project_id, job_id=job_id)

    def start_capcut_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_export(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_capcut_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_capcut_export_result(project_id=project_id, job_id=job_id)
