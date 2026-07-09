from __future__ import annotations

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import BuildTimelineRequest, StartJobResponse, TimelineJobResponse, TimelinePayloadResponse
from videobox_api.orchestration import ApiOrchestrator
from videobox_api.response_normalizers import _normalize_timeline_payload_for_response


def build_timeline_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/jobs/build-timeline", status_code=status.HTTP_202_ACCEPTED)
    def build_timeline(project_id: str, payload: BuildTimelineRequest) -> StartJobResponse:
        try:
            result = orchestrator.build_timeline(
                project_id=project_id,
                segment_analysis_job_id=payload.segment_analysis_job_id,
                recommendation_job_ids=payload.recommendation_job_ids,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/timelines/{job_id}")
    def get_timeline(project_id: str, job_id: str) -> TimelineJobResponse:
        try:
            result = orchestrator.get_timeline_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return TimelineJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            timeline=TimelinePayloadResponse(**_normalize_timeline_payload_for_response(result["timeline"])),
        )

    return router
