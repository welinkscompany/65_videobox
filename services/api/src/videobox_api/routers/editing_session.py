from __future__ import annotations

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    BrollOverrideRequest,
    CaptionOverrideRequest,
    CreateEditingSessionRequest,
    CutActionOverrideRequest,
    EditingSessionResponse,
    ExplanationCardRequest,
    ImageOverlayRequest,
    PartialRegenerationJobResponse,
    PartialRegenerationRequest,
    PartialRegenerationResponse,
    TableOverlayRequest,
    TimelinePayloadResponse,
    TTSReplacementRequest,
    VisualOverlayRequest,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_api.response_normalizers import (
    _build_affected_output_areas,
    _build_preflight_review_prediction,
    _build_targeted_segments,
    _normalize_timeline_payload_for_response,
)
from videobox_storage.local_project_store import LocalProjectStore


def build_editing_session_router(orchestrator: ApiOrchestrator, store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/editing-sessions", status_code=status.HTTP_201_CREATED)
    def create_editing_session(project_id: str, payload: CreateEditingSessionRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.create_editing_session(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.get("/api/projects/{project_id}/editing-sessions/latest")
    def get_latest_editing_session(project_id: str) -> EditingSessionResponse:
        try:
            result = orchestrator.get_latest_editing_session(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.get("/api/projects/{project_id}/editing-sessions/{session_id}")
    def get_editing_session(project_id: str, session_id: str) -> EditingSessionResponse:
        try:
            result = orchestrator.get_editing_session(
                project_id=project_id,
                session_id=session_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption")
    def patch_editing_session_caption(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: CaptionOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_caption(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                caption_text=payload.caption_text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/cut-action")
    def patch_editing_session_cut_action(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: CutActionOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_cut_action(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                cut_action=payload.cut_action,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll")
    def patch_editing_session_broll_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: BrollOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_broll_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/sfx")
    def patch_editing_session_sfx_override(project_id: str, session_id: str, segment_id: str, payload: BrollOverrideRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_sfx_override(project_id=project_id, session_id=session_id, segment_id=segment_id, asset_id=payload.asset_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll")
    def delete_editing_session_broll_override(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_broll_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.post(
        "/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        response_model_exclude_none=True,
    )
    def preview_editing_session_partial_regeneration(
        project_id: str,
        session_id: str,
        payload: PartialRegenerationRequest,
    ) -> PartialRegenerationResponse:
        try:
            request_preview = orchestrator.build_editing_session_partial_regeneration_request(
                project_id=project_id,
                session_id=session_id,
                segment_ids=payload.segment_ids,
                fields=payload.fields,
            )
            session = orchestrator.get_editing_session(project_id=project_id, session_id=session_id)
            source_timeline = store.get_timeline_run(
                project_id=project_id,
                timeline_id=str(session["timeline_id"]),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        targeted_segments = _build_targeted_segments(
            session=session,
            segment_ids=request_preview["segment_ids"],
        )
        request_preview["targeted_segments"] = targeted_segments
        request_preview["affected_output_areas"] = _build_affected_output_areas(
            request_preview["downstream_steps"],
        )
        predicted_review_status_after_rerun, prediction_reasons = _build_preflight_review_prediction(
            source_timeline=source_timeline,
            targeted_segments=targeted_segments,
            fields=request_preview["fields"],
        )
        request_preview["predicted_review_status_after_rerun"] = predicted_review_status_after_rerun
        request_preview["prediction_reasons"] = prediction_reasons
        return PartialRegenerationResponse(**request_preview)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration", status_code=status.HTTP_202_ACCEPTED)
    def start_editing_session_partial_regeneration(
        project_id: str,
        session_id: str,
        payload: PartialRegenerationRequest,
    ) -> PartialRegenerationResponse:
        try:
            result = orchestrator.start_editing_session_partial_regeneration(
                project_id=project_id,
                session_id=session_id,
                segment_ids=payload.segment_ids,
                fields=payload.fields,
            )
            session = orchestrator.get_editing_session(project_id=project_id, session_id=session_id)
            job_result = orchestrator.get_partial_regeneration_result(
                project_id=project_id,
                job_id=str(result["job_id"]),
            )
            source_timeline = store.get_timeline_run(
                project_id=project_id,
                timeline_id=str(job_result["source_timeline_id"]),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        result["targeted_segments"] = _build_targeted_segments(
            session=session,
            segment_ids=result["segment_ids"],
        )
        result["affected_output_areas"] = _build_affected_output_areas(result["downstream_steps"])
        predicted_review_status_after_rerun, prediction_reasons = _build_preflight_review_prediction(
            source_timeline=source_timeline,
            targeted_segments=result["targeted_segments"],
            fields=result["fields"],
        )
        result["predicted_review_status_after_rerun"] = predicted_review_status_after_rerun
        result["prediction_reasons"] = prediction_reasons
        result["delta"] = {
            "regenerated_segments": job_result["regenerated_segments"],
            "timeline_id": job_result["timeline_id"],
        }
        return PartialRegenerationResponse(**result)

    @router.get("/api/projects/{project_id}/partial-regenerations/{job_id}")
    def get_partial_regeneration_result(project_id: str, job_id: str) -> PartialRegenerationJobResponse:
        try:
            result = orchestrator.get_partial_regeneration_result(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return PartialRegenerationJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            partial_regeneration_id=result["partial_regeneration_id"],
            session_id=result["session_id"],
            session_updated_at=result.get("session_updated_at"),
            source_timeline_id=result["source_timeline_id"],
            timeline_id=result["timeline_id"],
            segment_ids=result["segment_ids"],
            fields=result["fields"],
            downstream_steps=result["downstream_steps"],
            regenerated_segments=result["regenerated_segments"],
            timeline=TimelinePayloadResponse(
                **_normalize_timeline_payload_for_response(result["timeline"])
            ),
            created_at=result.get("created_at"),
        )

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/visual-overlay")
    def patch_editing_session_visual_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: VisualOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_visual_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                overlay_type=payload.overlay_type,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/visual-overlay")
    def delete_editing_session_visual_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_visual_overlays(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/explanation-card")
    def patch_editing_session_explanation_card(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: ExplanationCardRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_explanation_card(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                title=payload.title,
                body=payload.body,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/explanation-card")
    def delete_editing_session_explanation_card(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_explanation_card(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/image-overlay")
    def patch_editing_session_image_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: ImageOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_image_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/image-overlay")
    def delete_editing_session_image_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_image_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/table-overlay")
    def patch_editing_session_table_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: TableOverlayRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_table_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                columns=payload.columns,
                rows=payload.rows,
                text=payload.text,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/table-overlay")
    def delete_editing_session_table_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_table_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/music")
    def patch_editing_session_music_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: BrollOverrideRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_music_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/music")
    def delete_editing_session_music_override(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_music_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/tts-replacement")
    def patch_editing_session_tts_replacement(
        project_id: str,
        session_id: str,
        segment_id: str,
        payload: TTSReplacementRequest,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.select_segment_tts_replacement(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                recommendation_id=payload.recommendation_id,
                asset_id=payload.asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/tts-replacement")
    def delete_editing_session_tts_replacement(
        project_id: str,
        session_id: str,
        segment_id: str,
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_tts_replacement(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    return router
