from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from videobox_api.errors import _http_error
from videobox_api.models import (
    BrollOverrideRequest,
    CaptionOverrideRequest,
    CaptionStyleMutationRequest,
    CreateEditingSessionRequest,
    CutActionOverrideRequest,
    EditingSessionResponse,
    EditingSessionRevisionRequest,
    ExplanationCardRequest,
    ImageOverlayRequest,
    PartialRegenerationJobResponse,
    PartialRegenerationPreflightRequest,
    PartialRegenerationRequest,
    PartialRegenerationResponse,
    SegmentBoundsRequest,
    SegmentMergeRequest,
    SegmentOrderRequest,
    SegmentSplitRequest,
    SelectedRangePreviewRequest,
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
from videobox_core_engine.editing_session_and_regeneration import EditingSessionConflict


def _editing_session_conflict_response(exc: EditingSessionConflict) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"latest_session": exc.latest_session},
    )


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

    @router.get("/api/projects/{project_id}/editing-sessions/{session_id}/fixed-timeline")
    def get_editing_session_fixed_timeline(project_id: str, session_id: str) -> dict[str, object]:
        try:
            return orchestrator.get_editing_session_fixed_timeline(project_id=project_id, session_id=session_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/selected-range-preview")
    def preview_editing_session_selected_range(project_id: str, session_id: str, payload: SelectedRangePreviewRequest) -> dict[str, object]:
        try:
            return orchestrator.preview_editing_session_selected_range(project_id=project_id, session_id=session_id, start_sec=payload.start_sec, end_sec=payload.end_sec)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/caption-style/preflight")
    def preview_caption_style_scope(project_id: str, session_id: str, payload: CaptionStyleMutationRequest) -> dict[str, object]:
        try:
            return orchestrator.preview_caption_style_scope(project_id=project_id, session_id=session_id, scope=payload.scope, segment_ids=payload.segment_ids)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/caption-style")
    def patch_caption_style(project_id: str, session_id: str, payload: CaptionStyleMutationRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.update_caption_style(project_id=project_id, session_id=session_id, style=payload.style, scope=payload.scope, segment_ids=payload.segment_ids, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/split")
    def split_editing_session_segment(project_id: str, session_id: str, segment_id: str, payload: SegmentSplitRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.split_editing_session_segment(project_id=project_id, session_id=session_id, segment_id=segment_id, split_sec=payload.split_sec, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/segments/merge")
    def merge_editing_session_segments(project_id: str, session_id: str, payload: SegmentMergeRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.merge_editing_session_segments(project_id=project_id, session_id=session_id, left_segment_id=payload.left_segment_id, right_segment_id=payload.right_segment_id, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/bounds")
    def patch_editing_session_segment_bounds(project_id: str, session_id: str, segment_id: str, payload: SegmentBoundsRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.set_editing_session_segment_bounds(project_id=project_id, session_id=session_id, segment_id=segment_id, start_sec=payload.start_sec, end_sec=payload.end_sec, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.put("/api/projects/{project_id}/editing-sessions/{session_id}/segment-order")
    def put_editing_session_segment_order(project_id: str, session_id: str, payload: SegmentOrderRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.reorder_editing_session_segments(project_id=project_id, session_id=session_id, segment_ids=payload.segment_ids, bounds_by_id=payload.bounds_by_id, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/undo")
    def undo_editing_session(project_id: str, session_id: str, payload: EditingSessionRevisionRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.undo_editing_session(project_id=project_id, session_id=session_id, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/redo")
    def redo_editing_session(project_id: str, session_id: str, payload: EditingSessionRevisionRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.redo_editing_session(project_id=project_id, session_id=session_id, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                media_controls=payload.media_controls,
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.patch("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/sfx")
    def patch_editing_session_sfx_override(project_id: str, session_id: str, segment_id: str, payload: BrollOverrideRequest) -> EditingSessionResponse:
        try:
            result = orchestrator.update_segment_sfx_override(project_id=project_id, session_id=session_id, segment_id=segment_id, asset_id=payload.asset_id, media_controls=payload.media_controls, expected_revision=payload.expected_revision)
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/sfx")
    def delete_editing_session_sfx_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_sfx_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll")
    def delete_editing_session_broll_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_broll_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
        payload: PartialRegenerationPreflightRequest,
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
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
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
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/visual-overlay")
    def delete_editing_session_visual_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_visual_overlays(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/explanation-card")
    def delete_editing_session_explanation_card(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_explanation_card(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/image-overlay")
    def delete_editing_session_image_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_image_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/table-overlay")
    def delete_editing_session_table_overlay(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.remove_segment_table_overlay(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                media_controls=payload.media_controls,
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/music")
    def delete_editing_session_music_override(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_music_override(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
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
                expected_revision=payload.expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    @router.delete("/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/tts-replacement")
    def delete_editing_session_tts_replacement(
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int = Query(ge=1),
    ) -> EditingSessionResponse:
        try:
            result = orchestrator.clear_segment_tts_replacement(
                project_id=project_id,
                session_id=session_id,
                segment_id=segment_id,
                expected_revision=expected_revision,
            )
        except EditingSessionConflict as exc:
            return _editing_session_conflict_response(exc)
        except Exception as exc:
            raise _http_error(exc) from exc
        return EditingSessionResponse(**result)

    return router
