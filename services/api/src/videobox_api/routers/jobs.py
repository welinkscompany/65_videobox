from __future__ import annotations

import threading

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    RecommendationJobResponse,
    RecommendationItemResponse,
    SegmentAnalysisJobResponse,
    SegmentAnalysisRecord,
    StartJobResponse,
    StartRecommendationRequest,
    StartSegmentAnalysisRequest,
    StartTranscriptionRequest,
    TranscriptionJobResponse,
)
from videobox_api.orchestration import ApiOrchestrator

# Job types whose retry needs a background thread to run the actual work
# after the job row is created, mirroring the dedicated start endpoints in
# routers/outputs.py (run_final_render_job / run_capcut_draft_export_job).
_RETRY_BACKGROUND_RUNNERS = {
    "final_render": "run_final_render_job",
    "capcut_draft_export": "run_capcut_draft_export_job",
}


def build_jobs_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/jobs/transcription", status_code=status.HTTP_202_ACCEPTED)
    def start_transcription(project_id: str, payload: StartTranscriptionRequest) -> TranscriptionJobResponse:
        try:
            result = orchestrator.start_transcription(
                project_id=project_id,
                narration_asset_id=payload.narration_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return TranscriptionJobResponse(**result)

    @router.get("/api/projects/{project_id}/jobs/transcription/{job_id}")
    def get_transcription_job(project_id: str, job_id: str) -> TranscriptionJobResponse:
        try:
            result = orchestrator.get_transcription_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return TranscriptionJobResponse(**result)

    @router.post("/api/projects/{project_id}/jobs/segment-analysis", status_code=status.HTTP_202_ACCEPTED)
    def start_segment_analysis(project_id: str, payload: StartSegmentAnalysisRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_segment_analysis(
                project_id=project_id,
                transcription_job_id=payload.transcription_job_id,
                script_asset_id=payload.script_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(job_id=result["job_id"], status=result["status"])

    @router.get("/api/projects/{project_id}/jobs/segment-analysis/{job_id}")
    def get_segment_analysis_job(project_id: str, job_id: str) -> SegmentAnalysisJobResponse:
        try:
            result = orchestrator.get_segment_analysis_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return SegmentAnalysisJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            segments=[SegmentAnalysisRecord(**segment) for segment in result["segments"]],
        )

    @router.post("/api/projects/{project_id}/jobs/broll-recommendation", status_code=status.HTTP_202_ACCEPTED)
    def start_broll_recommendation(project_id: str, payload: StartRecommendationRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_broll_recommendation(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/jobs/broll-recommendation/{job_id}")
    def get_broll_recommendation(project_id: str, job_id: str) -> RecommendationJobResponse:
        try:
            result = orchestrator.get_broll_recommendation_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return RecommendationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            recommendation_type=result["recommendation_type"],
            recommendations=[RecommendationItemResponse(**item) for item in result["recommendations"]],
        )

    @router.post("/api/projects/{project_id}/jobs/music-recommendation", status_code=status.HTTP_202_ACCEPTED)
    def start_music_recommendation(project_id: str, payload: StartRecommendationRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_music_recommendation(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/jobs/music-recommendation/{job_id}")
    def get_music_recommendation(project_id: str, job_id: str) -> RecommendationJobResponse:
        try:
            result = orchestrator.get_music_recommendation_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return RecommendationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            recommendation_type=result["recommendation_type"],
            recommendations=[RecommendationItemResponse(**item) for item in result["recommendations"]],
        )

    @router.post("/api/projects/{project_id}/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    def retry_job(project_id: str, job_id: str) -> StartJobResponse:
        try:
            result = orchestrator.retry_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        background_runner = _RETRY_BACKGROUND_RUNNERS.get(result["job_type"])
        if background_runner is not None:
            threading.Thread(
                target=getattr(orchestrator, background_runner),
                kwargs={
                    "project_id": project_id,
                    "timeline_job_id": result["input_ref"],
                    "job": {"job_id": result["job_id"]},
                },
                daemon=True,
            ).start()
        return StartJobResponse(job_id=result["job_id"], status=result["status"])

    return router
