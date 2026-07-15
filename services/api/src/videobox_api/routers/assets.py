from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status
from fastapi.responses import FileResponse

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
    TTSCandidateListResponse,
    TTSCandidateResponse,
    TTSCandidateRecordResponse,
    TTSCandidateRequest,
    TTSListeningReviewRequest,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_storage.local_project_store import LocalProjectStore

MAX_VOICE_SAMPLE_UPLOAD_BYTES = 128 * 1024 * 1024
VOICE_SAMPLE_UPLOAD_CHUNK_BYTES = 1024 * 1024


def build_assets_router(orchestrator: ApiOrchestrator, store: LocalProjectStore) -> APIRouter:
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

    @router.get("/api/projects/{project_id}/assets/broll-video")
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
        for asset in batch["assets"]:
            if service is None:
                continue
            try:
                analysis = service.enqueue_analysis(project_id=project_id, asset_id=asset["asset_id"])
                dispatcher = getattr(orchestrator, "media_analysis_dispatcher", None)
                if dispatcher is not None:
                    background_tasks.add_task(dispatcher, project_id=project_id, analysis_id=analysis["analysis_id"])
                analyses.append(service.get_analysis(project_id, analysis["analysis_id"]))
            except Exception:
                # Asset registration is durable even if analysis cannot start.
                continue
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
        staged_path = store.project_root(project_id) / "tmp" / "voice_sample_uploads" / f"{uuid4().hex}{suffix}"
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
    def get_asset_content(project_id: str, asset_id: str) -> FileResponse:
        try:
            asset = store.get_asset(project_id=project_id, asset_id=asset_id)
            resolved_path = store.resolve_storage_uri(
                project_id=project_id, storage_uri=asset["storage_uri"]
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        if not resolved_path.exists():
            raise _http_error(FileNotFoundError(f"Asset file not found: '{resolved_path}'."))
        return FileResponse(resolved_path)

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
