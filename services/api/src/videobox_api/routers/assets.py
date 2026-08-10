from __future__ import annotations

import logging
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from videobox_api.asset_browser_preview_service import AssetBrowserPreviewService, AssetBrowserPreviewUnsupported
from videobox_api.content_delivery import deliver_file
from videobox_api.errors import _http_error
from videobox_api.models import (
    AssetArchiveItemResponse,
    AssetListResponse,
    AssetRegistrationRequest,
    AssetResponse,
    AutoCutDetectRequest,
    AutoCutPlanRequest,
    AutoCutPlanResponse,
    BrollAssetRegistrationRequest,
    BrollBatchAssetRegistrationRequest,
    BrowserPreviewResponse,
    TTSCandidateListResponse,
    TTSCandidateResponse,
    TTSCandidateRecordResponse,
    TTSCandidateRequest,
    TTSListeningReviewRequest,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_core_engine.asset_browser_preview import BrowserPreviewError
from videobox_storage.local_project_store import LocalProjectStore

_LOGGER = logging.getLogger(__name__)

MAX_VOICE_SAMPLE_UPLOAD_BYTES = 128 * 1024 * 1024
VOICE_SAMPLE_UPLOAD_CHUNK_BYTES = 1024 * 1024


def build_assets_router(
    orchestrator: ApiOrchestrator,
    store: LocalProjectStore,
    browser_preview_service: AssetBrowserPreviewService | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/assets/narration-audio", status_code=status.HTTP_201_CREATED)
    def register_narration_audio(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_narration_audio(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.post("/api/projects/{project_id}/assets/script-document", status_code=status.HTTP_201_CREATED)
    def register_script_document(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_script_document(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.post("/api/projects/{project_id}/assets/broll-video", status_code=status.HTTP_201_CREATED)
    def register_broll_asset(project_id: str, payload: BrollAssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_broll_asset(
                project_id=project_id,
                source_path=Path(payload.source_path),
                title=payload.title,
                tags=payload.tags,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.get("/api/projects/{project_id}/assets/broll-video", response_model_exclude_none=True)
    def list_broll_assets(project_id: str) -> AssetListResponse:
        try:
            assets = orchestrator.list_broll_assets(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetListResponse(assets=[AssetArchiveItemResponse(**asset) for asset in assets])

    @router.post("/api/projects/{project_id}/assets/broll-video/batch", status_code=status.HTTP_201_CREATED)
    def register_broll_assets_batch(
        project_id: str,
        payload: BrollBatchAssetRegistrationRequest,
        background_tasks: BackgroundTasks,
    ) -> dict:
        try:
            batch = orchestrator.register_broll_assets_batch(
                project_id=project_id,
                source_paths=[Path(source_path) for source_path in payload.source_paths],
                source_directory=Path(payload.source_directory) if payload.source_directory else None,
                tags=payload.tags,
                title_by_source_path=payload.title_by_source_path,
                recursive=payload.recursive,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        service = getattr(orchestrator, "media_analysis_service", None)
        analyses = []
        # 예약이 실패한 파일은 `failures`에 들어가지 않는다 -- 자산은 실제로
        # 등록됐으니 가져오기 실패로 보고하면 거짓말이 된다. 대신 태그가 안
        # 붙어 검색에서 없는 것이 되므로, 어느 파일이 그렇게 됐는지는 남긴다.
        unqueued: list[str] = []
        first_error: Exception | None = None
        for asset in batch["assets"]:
            if service is None:
                continue
            try:
                analysis = service.enqueue_analysis(project_id=project_id, asset_id=asset["asset_id"])
                dispatcher = getattr(orchestrator, "media_analysis_dispatcher", None)
                if dispatcher is not None:
                    background_tasks.add_task(dispatcher, project_id=project_id, analysis_id=analysis["analysis_id"])
                analyses.append(service.get_analysis(project_id, analysis["analysis_id"]))
            except Exception as exc:  # noqa: BLE001 - 한 파일이 나머지를 막지 않는다
                # Asset registration is durable even if analysis cannot start.
                unqueued.append(str(asset.get("asset_id") or "(이름 없음)"))
                if first_error is None:
                    first_error = exc
                continue
        if unqueued:
            # 한 번에 수백 개를 넣을 수 있는 경로다. 파일마다 찍지 않고 모아 남긴다.
            _LOGGER.warning(
                "가져온 촬영본 %d개의 분석을 시작하지 못했습니다. 태그가 붙지 않아 "
                "검색에 나오지 않습니다 (project=%s, 자산=%s).",
                len(unqueued),
                project_id,
                ", ".join(unqueued[:10]),
                exc_info=first_error,
            )
        return {"assets": [AssetArchiveItemResponse(**asset).model_dump() for asset in batch["assets"]], "analysis_jobs": analyses, "failures": batch["failures"]}

    @router.post("/api/projects/{project_id}/assets/raw-video", status_code=status.HTTP_201_CREATED)
    def register_raw_video(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_raw_video_asset(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.post("/api/projects/{project_id}/assets/sfx", status_code=status.HTTP_201_CREATED)
    def register_sfx(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_sfx_asset(project_id=project_id, source_path=Path(payload.source_path))
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(asset_id=asset.asset_id, asset_type=asset.asset_type, storage_uri=asset.storage_uri)

    @router.post("/api/projects/{project_id}/assets/voice-sample", status_code=status.HTTP_201_CREATED)
    def register_voice_sample(project_id: str, payload: AssetRegistrationRequest) -> AssetResponse:
        try:
            asset = orchestrator.register_voice_sample_asset(
                project_id=project_id,
                source_path=Path(payload.source_path),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.get("/api/projects/{project_id}/assets/voice-sample")
    def list_voice_sample_assets(project_id: str) -> AssetListResponse:
        try:
            assets = orchestrator.list_voice_sample_assets(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetListResponse(assets=[AssetArchiveItemResponse(**asset) for asset in assets])

    @router.post("/api/projects/{project_id}/assets/voice-sample/upload", status_code=status.HTTP_201_CREATED)
    async def upload_voice_sample(
        project_id: str,
        file: UploadFile = File(...),
    ) -> AssetResponse:
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}:
            raise _http_error(ValueError("Voice sample must be an audio file with a supported extension."))
        # Keep the project-owned upload component short so long Windows
        # work/artifact roots do not exceed MAX_PATH.
        staged_path = (
            store.project_root(project_id)
            / "tmp"
            / "voice_sample_uploads"
            / f".v{uuid4().hex[:8]}{suffix}"
        )
        try:
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            with staged_path.open("wb") as staged_file:
                while chunk := await file.read(VOICE_SAMPLE_UPLOAD_CHUNK_BYTES):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VOICE_SAMPLE_UPLOAD_BYTES:
                        raise ValueError("Voice sample upload exceeds the 128 MiB limit.")
                    staged_file.write(chunk)
            if total_bytes == 0:
                raise ValueError("Voice sample upload is empty.")
            asset = orchestrator.register_voice_sample_asset(
                project_id=project_id,
                source_path=staged_path,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        finally:
            await file.close()
            staged_path.unlink(missing_ok=True)
        return AssetResponse(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            storage_uri=asset.storage_uri,
        )

    @router.post("/api/projects/{project_id}/tts-candidates", status_code=status.HTTP_201_CREATED)
    def generate_tts_candidate(project_id: str, payload: TTSCandidateRequest) -> TTSCandidateResponse:
        try:
            asset = orchestrator.generate_tts_replacement_candidate(
                project_id=project_id,
                segment_text=payload.segment_text,
                voice_sample_asset_id=payload.voice_sample_asset_id,
                segment_id=payload.segment_id,
                target_duration_sec=payload.target_duration_sec,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return TTSCandidateResponse(**asset)

    @router.get("/api/projects/{project_id}/segments/{segment_id}/tts-candidates")
    def list_tts_candidates(project_id: str, segment_id: str) -> TTSCandidateListResponse:
        try:
            candidates = orchestrator.list_tts_replacement_candidates(
                project_id=project_id, segment_id=segment_id
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return TTSCandidateListResponse(
            candidates=[TTSCandidateRecordResponse(**candidate) for candidate in candidates]
        )

    @router.patch("/api/projects/{project_id}/tts-candidates/{candidate_id}/listening-review")
    def review_tts_candidate(
        project_id: str,
        candidate_id: str,
        payload: TTSListeningReviewRequest,
    ) -> TTSCandidateRecordResponse:
        try:
            candidate = orchestrator.review_tts_replacement_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                decision=payload.decision,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return TTSCandidateRecordResponse(**candidate)

    @router.get("/api/projects/{project_id}/assets/{asset_id}/content")
    def get_asset_content(project_id: str, asset_id: str, request: Request):
        try:
            asset = store.get_asset(project_id=project_id, asset_id=asset_id)
            resolved_path = store.resolve_storage_uri(
                project_id=project_id, storage_uri=asset["storage_uri"]
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        if not resolved_path.exists():
            raise _http_error(FileNotFoundError(f"Asset file not found: '{resolved_path}'."))
        return deliver_file(request=request, path=resolved_path, media_type=asset.get("mime_type"))

    @router.post("/api/projects/{project_id}/assets/{asset_id}/browser-preview")
    def prepare_browser_preview(project_id: str, asset_id: str):
        if browser_preview_service is None:
            return JSONResponse(status_code=503, content={"detail": "browser_preview_unavailable"})
        try:
            payload, created, input_ref = browser_preview_service.prepare(
                project_id=project_id,
                asset_id=asset_id,
            )
        except AssetBrowserPreviewUnsupported as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        except BrowserPreviewError as exc:
            return JSONResponse(status_code=422, content={"detail": exc.code})
        except Exception as exc:
            raise _http_error(exc) from exc
        if created and input_ref and payload["job_id"]:
            threading.Thread(
                target=browser_preview_service.run,
                kwargs={
                    "project_id": project_id,
                    "asset_id": asset_id,
                    "input_ref": input_ref,
                    "job_id": payload["job_id"],
                },
                name=f"asset-browser-preview-{payload['job_id']}",
                daemon=True,
            ).start()
        body = BrowserPreviewResponse(**payload).model_dump()
        return JSONResponse(status_code=202 if payload["status"] in {"pending", "running"} else 200, content=body)

    @router.get("/api/projects/{project_id}/assets/{asset_id}/browser-preview")
    def get_browser_preview(project_id: str, asset_id: str):
        if browser_preview_service is None:
            return JSONResponse(status_code=503, content={"detail": "browser_preview_unavailable"})
        try:
            return BrowserPreviewResponse(
                **browser_preview_service.status(project_id=project_id, asset_id=asset_id)
            )
        except AssetBrowserPreviewUnsupported as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        except BrowserPreviewError as exc:
            return JSONResponse(status_code=422, content={"detail": exc.code})
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/assets/{asset_id}/browser-preview/content")
    def get_browser_preview_content(project_id: str, asset_id: str, request: Request):
        if browser_preview_service is None:
            return JSONResponse(status_code=503, content={"detail": "browser_preview_unavailable"})
        try:
            path = browser_preview_service.content_path(project_id=project_id, asset_id=asset_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return deliver_file(request=request, path=path, media_type="video/mp4")

    @router.get("/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    def get_asset_thumbnail(project_id: str, asset_id: str) -> FileResponse:
        try:
            store.get_asset(project_id=project_id, asset_id=asset_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        thumbnail_path = store.thumbnail_storage_path(project_id=project_id, asset_id=asset_id)
        if not thumbnail_path.exists():
            raise _http_error(FileNotFoundError(f"No thumbnail generated for asset '{asset_id}'."))
        return FileResponse(thumbnail_path)

    @router.post("/api/projects/{project_id}/jobs/auto-cut-plan")
    def plan_auto_cut(project_id: str, payload: AutoCutPlanRequest) -> AutoCutPlanResponse:
        try:
            result = orchestrator.plan_auto_cut_segments(
                project_id=project_id,
                raw_video_asset_id=payload.raw_video_asset_id,
                total_duration=payload.total_duration,
                scene_timestamps=payload.scene_timestamps,
                black_regions=[region.model_dump() for region in payload.black_regions],
                segment_samples=[segment.model_dump() for segment in payload.segment_samples],
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AutoCutPlanResponse(**result)

    @router.post("/api/projects/{project_id}/jobs/auto-cut-detect")
    def detect_auto_cut(project_id: str, payload: AutoCutDetectRequest) -> AutoCutPlanResponse:
        try:
            result = orchestrator.run_auto_cut_detection(
                project_id=project_id,
                raw_video_asset_id=payload.raw_video_asset_id,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return AutoCutPlanResponse(**result)

    return router
