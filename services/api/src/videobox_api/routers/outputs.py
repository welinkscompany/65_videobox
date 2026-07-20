from __future__ import annotations

import threading

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse

from videobox_api.content_delivery import deliver_file
from videobox_api.errors import _http_error
from videobox_api.models import (
    CapCutHandoffDiagnosticsResponse,
    CapCutDraftExportArtifactResponse,
    CapCutDraftHandoffResponse,
    CapCutDraftExportJobResponse,
    ExportArtifactResponse,
    ExportJobResponse,
    FinalRenderArtifactResponse,
    FinalRenderJobResponse,
    OutputJobRequest,
    ExactPreviewRequestBody,
    ExactPreviewResponse,
    PreviewArtifactResponse,
    PreviewJobResponse,
    ProviderTraceAuditEntryResponse,
    ProviderTraceAuditResponse,
    ProviderTraceAuditSummaryResponse,
    StartJobResponse,
    SubtitleArtifactResponse,
    SubtitleJobResponse,
)
from videobox_api.orchestration import ApiOrchestrator


def build_outputs_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/editing-sessions/{session_id}/exact-preview", status_code=status.HTTP_202_ACCEPTED)
    def start_exact_preview(project_id: str, session_id: str, payload: ExactPreviewRequestBody) -> ExactPreviewResponse:
        try:
            result = orchestrator.start_exact_preview(
                project_id=project_id, session_id=session_id, expected_revision=payload.expected_revision,
                start_sec=payload.start_sec, end_sec=payload.end_sec,
            )
            threading.Thread(
                target=orchestrator.run_exact_preview,
                kwargs={"project_id": project_id, "generation_id": result["generation_id"]}, daemon=True,
            ).start()
        except Exception as exc:
            raise _http_error(exc) from exc
        return ExactPreviewResponse(**result)

    @router.get("/api/projects/{project_id}/exact-previews/{generation_id}")
    def get_exact_preview(project_id: str, generation_id: str) -> ExactPreviewResponse:
        try:
            return ExactPreviewResponse(**orchestrator.get_exact_preview_status(
                project_id=project_id, generation_id=generation_id
            ))
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/exact-previews/{generation_id}/content")
    def get_exact_preview_content(project_id: str, generation_id: str, request: Request):
        try:
            return deliver_file(
                request=request,
                path=orchestrator.get_exact_preview_content_path(project_id=project_id, generation_id=generation_id),
                media_type="video/mp4",
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/capcut/handoff-diagnostics")
    def get_capcut_handoff_diagnostics() -> CapCutHandoffDiagnosticsResponse:
        try:
            diagnostics = orchestrator.get_capcut_handoff_diagnostics()
        except Exception as exc:
            raise _http_error(exc) from exc
        return CapCutHandoffDiagnosticsResponse(**diagnostics)

    @router.post("/api/projects/{project_id}/jobs/subtitle-render", status_code=status.HTTP_202_ACCEPTED)
    def start_subtitle_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_subtitle_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/subtitles/{job_id}")
    def get_subtitle_result(project_id: str, job_id: str) -> SubtitleJobResponse:
        try:
            result = orchestrator.get_subtitle_result(project_id=project_id, job_id=job_id)
            result["subtitle"] = orchestrator.pipeline.store.get_subtitle_run(project_id=project_id, subtitle_id=result["subtitle"]["subtitle_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return SubtitleJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            subtitle=SubtitleArtifactResponse(**result["subtitle"]),
        )

    @router.post("/api/projects/{project_id}/jobs/preview-render", status_code=status.HTTP_202_ACCEPTED)
    def start_preview_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_preview_render(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/previews/{job_id}")
    def get_preview_result(project_id: str, job_id: str) -> PreviewJobResponse:
        try:
            result = orchestrator.get_preview_result(project_id=project_id, job_id=job_id)
            result["preview"] = orchestrator.pipeline.store.get_preview_run(project_id=project_id, preview_id=result["preview"]["preview_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return PreviewJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            preview=PreviewArtifactResponse(**result["preview"]),
        )

    @router.post("/api/projects/{project_id}/jobs/capcut-export", status_code=status.HTTP_202_ACCEPTED)
    def start_capcut_export(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            result = orchestrator.start_capcut_export(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/exports/{job_id}")
    def get_export_result(project_id: str, job_id: str) -> ExportJobResponse:
        try:
            result = orchestrator.get_capcut_export_result(project_id=project_id, job_id=job_id)
            result["export"] = orchestrator.pipeline.store.get_export_run(project_id=project_id, export_id=result["export"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return ExportJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            export=ExportArtifactResponse(**result["export"]),
        )

    @router.post("/api/projects/{project_id}/jobs/final-render", status_code=status.HTTP_202_ACCEPTED)
    def start_final_render(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=payload.timeline_job_id)
            result = orchestrator.start_final_render_job(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        threading.Thread(
            target=orchestrator.run_final_render_job,
            kwargs={
                "project_id": project_id,
                "timeline_job_id": payload.timeline_job_id,
                "job": {"job_id": result["job_id"]},
            },
            daemon=True,
        ).start()
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/final-renders/{job_id}")
    def get_final_render_result(project_id: str, job_id: str) -> FinalRenderJobResponse:
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            if result.get("render"):
                result["render"] = orchestrator.pipeline.store.get_final_render_export(project_id=project_id, export_id=result["render"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return FinalRenderJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            render=FinalRenderArtifactResponse(**result["render"]) if result["render"] else None,
        )

    @router.get("/api/projects/{project_id}/final-renders/{job_id}/content")
    def get_final_render_content(project_id: str, job_id: str, request: Request):
        """Project-scoped browser playback for the composited MP4 artifact."""
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            render = result.get("render")
            if not render or str(result.get("status")) != "succeeded":
                raise KeyError("final_render_not_ready")
            path = orchestrator.store.resolve_storage_uri(project_id=project_id, storage_uri=str(render["file_uri"]))
            if not path.is_file(): raise KeyError("final_render_content_missing")
            return deliver_file(request=request, path=path, media_type="video/mp4")
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/jobs/capcut-draft-export", status_code=status.HTTP_202_ACCEPTED)
    def start_capcut_draft_export(project_id: str, payload: OutputJobRequest) -> StartJobResponse:
        try:
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=payload.timeline_job_id)
            result = orchestrator.start_capcut_draft_export_job(
                project_id=project_id,
                timeline_job_id=payload.timeline_job_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        threading.Thread(
            target=orchestrator.run_capcut_draft_export_job,
            kwargs={
                "project_id": project_id,
                "timeline_job_id": payload.timeline_job_id,
                "job": {"job_id": result["job_id"]},
            },
            daemon=True,
        ).start()
        return StartJobResponse(**result)

    @router.get("/api/projects/{project_id}/capcut-draft-exports/{job_id}")
    def get_capcut_draft_export_result(project_id: str, job_id: str) -> CapCutDraftExportJobResponse:
        try:
            result = orchestrator.get_capcut_draft_export_result(project_id=project_id, job_id=job_id)
            if result.get("export"):
                result["export"] = orchestrator.pipeline.store.get_capcut_draft_export(project_id=project_id, export_id=result["export"]["export_id"])
        except Exception as exc:
            raise _http_error(exc) from exc
        return CapCutDraftExportJobResponse(
            job_id=result["job_id"],
            status=result["status"],
            export=CapCutDraftExportArtifactResponse(**result["export"]) if result["export"] else None,
            error_message=result.get("error_message"),
        )

    @router.post("/api/projects/{project_id}/capcut-draft-exports/{job_id}/handoff")
    def register_capcut_draft_handoff(project_id: str, job_id: str) -> dict[str, CapCutDraftHandoffResponse]:
        try:
            handoff = orchestrator.register_capcut_draft_handoff(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return {"handoff": CapCutDraftHandoffResponse(**handoff)}

    @router.get("/api/projects/{project_id}/provider-traces")
    def get_provider_trace_audit(
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> ProviderTraceAuditResponse:
        try:
            result = orchestrator.get_provider_trace_audit(
                project_id=project_id,
                timeline_id=timeline_id,
                include_upstream=include_upstream,
                job_type=job_type,
                artifact_type=artifact_type,
                final_provider=final_provider,
                fallback_reason=fallback_reason,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProviderTraceAuditResponse(
            summary=ProviderTraceAuditSummaryResponse(**result["summary"]),
            entries=[ProviderTraceAuditEntryResponse(**item) for item in result["entries"]],
            direct_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("direct_entries", [])
            ],
            upstream_entries=[
                ProviderTraceAuditEntryResponse(**item) for item in result.get("upstream_entries", [])
            ],
        )

    return router
