from __future__ import annotations

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    OperatorGuidanceResponse,
    RecommendationItemResponse,
    ReviewApprovalResponse,
    ReviewFlagResponse,
    ReviewSnapshotResponse,
    SegmentAnalysisRecord,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_api.response_normalizers import (
    _normalize_operator_guidance_response,
    _normalize_recommendations_for_response,
    _normalize_review_flags_for_response,
)


def _build_review_snapshot_response(result: dict) -> ReviewSnapshotResponse:
    normalized_review_flags = _normalize_review_flags_for_response(result["review_flags"])
    normalized_applied_recommendations = _normalize_recommendations_for_response(
        result["applied_recommendations"]
    )
    normalized_pending_recommendations = _normalize_recommendations_for_response(
        result["pending_recommendations"]
    )
    return ReviewSnapshotResponse(
        project_id=result["project_id"],
        timeline_id=result["timeline_id"],
        source_variant_id=result.get("source_variant_id"),
        source_variant_revision=result.get("source_variant_revision"),
        review_status=result["review_status"],
        segments=[SegmentAnalysisRecord(**item) for item in result["segments"]],
        applied_recommendations=[
            RecommendationItemResponse(**item) for item in normalized_applied_recommendations
        ],
        pending_recommendations=[
            RecommendationItemResponse(**item) for item in normalized_pending_recommendations
        ],
        review_flags=[ReviewFlagResponse(**item) for item in normalized_review_flags],
        operator_guidance=OperatorGuidanceResponse(
            **_normalize_operator_guidance_response(result["operator_guidance"])
        ),
    )


def build_review_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/review-approvals/timelines/{timeline_id}")
    def get_review_approval(project_id: str, timeline_id: str) -> ReviewApprovalResponse:
        """Read durable review freshness, independent of an old job snapshot."""
        try:
            result = orchestrator.pipeline.store.get_review_state(project_id=project_id, timeline_id=timeline_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"], project_id=result["project_id"], review_status=result["status"],
            approved_at=result.get("approved_at"), updated_at=result["updated_at"],
            source_session_id=result.get("source_session_id"),
            source_session_revision=result.get("source_session_revision"),
            source_variant_id=result.get("source_variant_id"),
            source_variant_revision=result.get("source_variant_revision"),
            is_current=result.get("is_current", True),
            invalidated_at=result.get("invalidated_at"),
            invalidated_reason=result.get("invalidated_reason"),
        )

    @router.get("/api/projects/{project_id}/review-snapshots/{job_id}")
    def get_review_snapshot(project_id: str, job_id: str) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.get_review_snapshot(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return _build_review_snapshot_response(result)

    @router.post("/api/projects/{project_id}/review-snapshots/{job_id}/recommendations/{recommendation_id}/approve")
    def approve_pending_recommendation(
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.approve_pending_recommendation(
                project_id=project_id,
                job_id=job_id,
                recommendation_id=recommendation_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return _build_review_snapshot_response(result)

    @router.post("/api/projects/{project_id}/review-snapshots/{job_id}/recommendations/{recommendation_id}/reject")
    def reject_pending_recommendation(
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> ReviewSnapshotResponse:
        try:
            result = orchestrator.reject_pending_recommendation(
                project_id=project_id,
                job_id=job_id,
                recommendation_id=recommendation_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return _build_review_snapshot_response(result)

    @router.post("/api/projects/{project_id}/review-approvals/{job_id}/approve", status_code=status.HTTP_202_ACCEPTED)
    def approve_review(project_id: str, job_id: str) -> ReviewApprovalResponse:
        try:
            result = orchestrator.approve_timeline_review(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"],
            project_id=result["project_id"],
            review_status=result["status"],
            approved_at=result["approved_at"],
            updated_at=result["updated_at"],
            source_session_id=result.get("source_session_id"),
            source_session_revision=result.get("source_session_revision"),
            source_variant_id=result.get("source_variant_id"),
            source_variant_revision=result.get("source_variant_revision"),
            is_current=result.get("is_current", True),
            invalidated_at=result.get("invalidated_at"),
            invalidated_reason=result.get("invalidated_reason"),
        )

    @router.post(
        "/api/projects/{project_id}/review-approvals/sessions/{session_id}/refresh",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def refresh_review_for_current_edit(project_id: str, session_id: str) -> ReviewApprovalResponse:
        """검토본을 지금 편집본으로 다시 세운다.

        편집은 승인 기록을 내린다. 그것을 다시 세우는 곳이 초안 생성 한 곳뿐이라
        한 번 편집하면 내보내기까지 갈 길이 없었다. 승인까지 올리지는 않는다 --
        승인은 owner가 검토 화면에서 누를 일이다.
        """
        try:
            result = orchestrator.pipeline.store.refresh_review_for_current_edit(
                project_id=project_id, session_id=session_id
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"],
            project_id=result["project_id"],
            review_status=result["status"],
            approved_at=result.get("approved_at"),
            updated_at=result["updated_at"],
            source_session_id=result.get("source_session_id"),
            source_session_revision=result.get("source_session_revision"), is_current=result.get("is_current", True),
            source_variant_id=result.get("source_variant_id"), source_variant_revision=result.get("source_variant_revision"),
            invalidated_at=result.get("invalidated_at"), invalidated_reason=result.get("invalidated_reason"),
        )

    @router.post("/api/projects/{project_id}/review-approvals/{job_id}/reopen", status_code=status.HTTP_202_ACCEPTED)
    def reopen_review(project_id: str, job_id: str) -> ReviewApprovalResponse:
        try:
            result = orchestrator.reopen_timeline_review(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ReviewApprovalResponse(
            timeline_id=result["timeline_id"],
            project_id=result["project_id"],
            review_status=result["status"],
            approved_at=result["approved_at"],
            updated_at=result["updated_at"],
            source_session_id=result.get("source_session_id"),
            source_session_revision=result.get("source_session_revision"),
            source_variant_id=result.get("source_variant_id"),
            source_variant_revision=result.get("source_variant_revision"),
            is_current=result.get("is_current", True),
            invalidated_at=result.get("invalidated_at"),
            invalidated_reason=result.get("invalidated_reason"),
        )

    return router
