from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from videobox_core_engine.mojibake import repair_mojibake_metadata
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
    YoutubeReferenceImportRequest,
    YoutubeReferenceImportResponse,
    YoutubeReferenceImportStartResponse,
    YoutubeReferenceImportStatusResponse,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_core_engine.asset_browser_preview import BrowserPreviewError
from videobox_storage.local_project_store import LocalProjectStore

_LOGGER = logging.getLogger(__name__)

MAX_VOICE_SAMPLE_UPLOAD_BYTES = 128 * 1024 * 1024
VOICE_SAMPLE_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _repaired_asset_response(asset: dict) -> "AssetArchiveItemResponse":
    """자산 한 건을 화면이 읽을 모양으로. 깨진 한글 이름은 여기서 되살린다.

    2026-08-20에 한 묶음으로 들어온 촬영본이 `02-µµ½Ã-Àú³á`처럼 저장돼 있어서
    **화면에도 그대로 깨져 보였다.** 자산 이름을 바꾸는 길이 제품에 없으므로
    저장을 고치는 대신 읽을 때 되살린다(`mojibake.py` -- 되살릴 수 있을 때만 손댄다).

    세 목록(내레이션·촬영본·목소리)이 **같은 함수를 쓴다.** 세 벌로 적으면
    한쪽만 고치는 사고가 난다 -- 이 저장소가 여러 번 겪은 일이다.
    """
    return AssetArchiveItemResponse(**{**asset, "metadata": repair_mojibake_metadata(asset.get("metadata"))})


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

    @router.get("/api/projects/{project_id}/assets/narration-audio")
    def list_narration_audio_assets(project_id: str) -> AssetListResponse:
        """넣는 길만 있고 보는 길이 없으면 잘못 넣은 것을 영영 모른다.

        2026-08-16에 완성본이 완전 무음으로 나갔는데, 내레이션이 무음 파일이라는 것을
        화면 어디에서도 확인할 수 없었다.
        """
        try:
            assets = orchestrator.list_narration_audio_assets(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return AssetListResponse(assets=[_repaired_asset_response(asset) for asset in assets])

    @router.post("/api/projects/{project_id}/assets/narration-audio/upload", status_code=status.HTTP_201_CREATED)
    async def upload_narration_audio(
        project_id: str,
        file: UploadFile = File(...),
    ) -> AssetResponse:
        """음성 샘플은 파일을 바로 올릴 수 있는데 내레이션만 경로를 타이핑해야 했다."""
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}:
            raise _http_error(ValueError("Narration must be an audio file with a supported extension."))
        staged_path = (
            store.project_root(project_id)
            / "tmp"
            / "narration_uploads"
            / f".n{uuid4().hex[:8]}{suffix}"
        )
        try:
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            with staged_path.open("wb") as staged_file:
                while chunk := await file.read(VOICE_SAMPLE_UPLOAD_CHUNK_BYTES):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_VOICE_SAMPLE_UPLOAD_BYTES:
                        raise ValueError("Narration upload exceeds the 128 MiB limit.")
                    staged_file.write(chunk)
            # 빈 파일을 받아 두면 무음 완성본이 다시 나간다.
            if total_bytes == 0:
                raise ValueError("Narration upload is empty.")
            asset = orchestrator.register_narration_audio(
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
        return AssetListResponse(assets=[_repaired_asset_response(asset) for asset in assets])

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
        return AssetListResponse(assets=[_repaired_asset_response(asset) for asset in assets])

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

    @router.post("/api/projects/{project_id}/reference-style/from-youtube", status_code=status.HTTP_202_ACCEPTED)
    def start_youtube_reference_style_import(
        project_id: str, payload: YoutubeReferenceImportRequest, background_tasks: BackgroundTasks,
    ) -> YoutubeReferenceImportStartResponse:
        """owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?"

        **비동기로 바뀌었다(owner 결정 2026-08-29, 2회차).** 다운로드·오디오
        추출·컷/색감 분석을 합치면 긴 영상에서는 nginx 프록시 330초 타임아웃보다
        오래 걸릴 수 있어, 이 요청은 작업만 걸어 두고 바로 202로 돌아온다.
        실제 진행 상황은 `GET .../from-youtube/{job_id}`로 확인한다.
        """
        try:
            started = orchestrator.start_youtube_reference_style_import(project_id=project_id, url=payload.url)
        except Exception as exc:
            raise _http_error(exc) from exc
        background_tasks.add_task(
            orchestrator.run_youtube_reference_style_import_job,
            project_id=project_id, job_id=started["job_id"], url=payload.url,
        )
        return YoutubeReferenceImportStartResponse(**started)

    @router.get("/api/projects/{project_id}/reference-style/from-youtube/{job_id}")
    def get_youtube_reference_style_import(project_id: str, job_id: str) -> YoutubeReferenceImportStatusResponse:
        try:
            job = orchestrator.get_youtube_reference_style_import_job(project_id=project_id, job_id=job_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        result = YoutubeReferenceImportResponse(**job["result"]) if job["result"] is not None else None
        return YoutubeReferenceImportStatusResponse(job_id=job["job_id"], status=job["status"], result=result, error_detail=job["error_detail"])

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

    @router.get("/api/projects/{project_id}/assets/{asset_id}/waveform")
    def get_asset_waveform(project_id: str, asset_id: str) -> FileResponse:
        """소리 클립 위에 그릴 파형 그림.

        캡컷처럼 타임라인에서 **눈으로** 크고 작은 데를 찾으려면 이 그림이 있어야
        한다. 만드는 방법은 라이브러리 자산 쪽(`routers/library_assets.py`)과 같은
        ffmpeg `showwavespic`이다 -- 새 방식을 들이지 않는다.

        한 번 만들고 다시 쓴다. 클립마다, 스크롤마다 ffmpeg를 부르면 타임라인이
        멈춘다.
        """
        try:
            asset = store.get_asset(project_id=project_id, asset_id=asset_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        target = store.waveform_storage_path(project_id=project_id, asset_id=asset_id)
        if not target.exists():
            # 원본 찾기는 저장소가 정본이다. 여기서 uri를 다시 해석하면 같은 규칙이
            # 두 벌이 된다.
            source = store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
            if not source.exists():
                raise _http_error(FileNotFoundError(f"No source for asset '{asset_id}'."))
            target.parent.mkdir(parents=True, exist_ok=True)
            command = [
                "ffmpeg", "-y", "-v", "error", "-i", str(source),
                "-filter_complex", "aformat=channel_layouts=mono,showwavespic=s=640x120:colors=orangered",
                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
            ]
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
            if result.returncode != 0 or not result.stdout:
                # 그림이 없다고 편집이 막히면 안 된다. 없으면 없는 대로 넘어간다.
                raise _http_error(FileNotFoundError(f"No waveform for asset '{asset_id}'."))
            # 같은 소리를 여러 클립이 쓰면 첫 화면에서 같은 파일을 **동시에** 만들려
            # 든다(실측: 클립 12개가 자산 2개를 가리켰다). 곧바로 쓰면 반쯤 쓰인
            # 파일을 옆에서 읽는다. 따로 쓰고 통째로 바꿔 끼운다.
            staging = target.with_name(f"{target.name}.{uuid4().hex}.part")
            staging.write_bytes(result.stdout)
            staging.replace(target)
        return FileResponse(target, media_type="image/png")

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
