from __future__ import annotations

import threading

from fastapi import APIRouter, BackgroundTasks, status

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
# `start_transcription`'s own kwargs shape differs (2026-09-08, §1-6 -- it
# went from doing the STT call inline to only creating the job row), so the
# retry route needs to build each runner's kwargs from its own shape rather
# than assuming the timeline_job_id/job pair every other retryable job uses.
_RETRY_BACKGROUND_RUNNERS = {
    "final_render": "run_final_render_job",
    "capcut_draft_export": "run_capcut_draft_export_job",
    "transcription": "run_transcription_job",
}


def _retry_background_kwargs(job_type: str, *, project_id: str, job_id: str, input_ref: str) -> dict[str, object]:
    if job_type == "transcription":
        return {"project_id": project_id, "job_id": job_id, "narration_asset_id": input_ref}
    return {"project_id": project_id, "timeline_job_id": input_ref, "job": {"job_id": job_id}}


def build_jobs_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/jobs/transcription", status_code=status.HTTP_202_ACCEPTED)
    def start_transcription(
        project_id: str, payload: StartTranscriptionRequest, background_tasks: BackgroundTasks,
    ) -> TranscriptionJobResponse:
        """받아쓰기를 걸어 두고 바로 돌아온다. 진행 상황은 `GET .../transcription/{job_id}`.

        **비동기여야 한다(2026-09-08, §1-6).** Whisper 호출에 시간 제한이 없어서
        긴 내레이션은 nginx 330초 벽을 넘길 수 있다 -- 자막 번역·더빙을 비동기로
        바꾼 것과 같은 이유이고 같은 방식이다.
        """
        try:
            result = orchestrator.start_transcription(
                project_id=project_id,
                narration_asset_id=payload.narration_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        background_tasks.add_task(
            orchestrator.run_transcription_job,
            project_id=project_id, job_id=result["job_id"], narration_asset_id=payload.narration_asset_id,
        )
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
                kwargs=_retry_background_kwargs(
                    result["job_type"], project_id=project_id, job_id=result["job_id"], input_ref=result["input_ref"],
                ),
                daemon=True,
            ).start()
        return StartJobResponse(job_id=result["job_id"], status=result["status"])

    return router
