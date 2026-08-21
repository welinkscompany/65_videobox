from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile, status

from videobox_api.errors import _http_error
from videobox_api.models import DraftReadinessCandidateRangeRequest, DraftReadinessCandidateRequest, DraftReadinessCreateRequest, DraftReadinessRevisionRequest, SourceVideoStartResponse
from videobox_api.orchestration import ApiOrchestrator

MAX_NARRATION_UPLOAD_BYTES = 128 * 1024 * 1024
NARRATION_UPLOAD_CHUNK_BYTES = 64 * 1024


class _NoSpeech(ValueError):
    """말이 없는 영상. 화면이 옮길 수 있게 코드로 말한다(§10.13)."""


def _no_speech() -> _NoSpeech:
    return _NoSpeech("source_video_has_no_speech")


def build_draft_readiness_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter(); store = orchestrator.store

    @router.post("/api/projects/{project_id}/draft-readiness", status_code=status.HTTP_201_CREATED)
    def start(project_id: str, payload: DraftReadinessCreateRequest) -> dict[str, object]:
        try: return orchestrator.start_draft_readiness(project_id=project_id, **payload.model_dump())
        except Exception as exc: raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/draft-readiness/narration-options")
    def narration_options(project_id: str) -> dict[str, object]:
        try:
            allowed = {"raw_video", "narration_audio"}
            return {"assets": [{"asset_id": item["asset_id"], "asset_type": item["asset_type"]} for item in store.list_assets(project_id=project_id) if item["asset_type"] in allowed]}
        except Exception as exc: raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/draft-readiness/{readiness_id}")
    def get(project_id: str, readiness_id: str) -> dict[str, object]:
        try: return store.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        except Exception as exc: raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/draft-readiness")
    def list_runs(project_id: str) -> dict[str, object]:
        try: return {"runs": store.list_draft_readiness(project_id=project_id)}
        except Exception as exc: raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/draft-readiness/{readiness_id}/cancel")
    def cancel(project_id: str, readiness_id: str, payload: DraftReadinessRevisionRequest) -> dict[str, object]:
        try: return store.cancel_draft_readiness(project_id=project_id, readiness_id=readiness_id, expected_revision=payload.expected_revision)
        except Exception as exc: raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/draft-readiness/{readiness_id}/retry")
    def retry(project_id: str, readiness_id: str, payload: DraftReadinessRevisionRequest) -> dict[str, object]:
        try: return store.begin_draft_readiness_planning(project_id=project_id, readiness_id=readiness_id, expected_revision=payload.expected_revision)
        except Exception as exc: raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/draft-readiness/{readiness_id}/complete")
    def complete(project_id: str, readiness_id: str, payload: DraftReadinessRevisionRequest) -> dict[str, object]:
        try: return store.complete_draft_readiness(project_id=project_id, readiness_id=readiness_id, expected_revision=payload.expected_revision)
        except Exception as exc: raise _http_error(exc) from exc

    @router.patch("/api/projects/{project_id}/draft-readiness/{readiness_id}/candidates")
    def update_candidate(project_id: str, readiness_id: str, payload: DraftReadinessCandidateRequest) -> dict[str, object]:
        try: return store.update_draft_readiness_candidate(project_id=project_id, readiness_id=readiness_id, **payload.model_dump())
        except Exception as exc: raise _http_error(exc) from exc

    @router.patch("/api/projects/{project_id}/draft-readiness/{readiness_id}/candidates/range")
    def update_candidate_range(project_id: str, readiness_id: str, payload: DraftReadinessCandidateRangeRequest) -> dict[str, object]:
        try: return store.update_draft_readiness_candidate_range(project_id=project_id, readiness_id=readiness_id, **payload.model_dump())
        except Exception as exc: raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/draft-readiness/narration/upload", status_code=status.HTTP_201_CREATED)
    async def upload_narration(project_id: str, file: UploadFile = File(...), filename: str | None = Form(None)) -> dict[str, object]:
        stage: Path | None = None
        try:
            # Validate ownership before deriving any project-scoped path.
            store.get_project(project_id=project_id)
            if not (file.filename or "").lower().endswith((".wav", ".mp3", ".m4a", ".ogg", ".webm")): raise ValueError("draft_readiness_narration_upload_invalid")
            if (declared := file.headers.get("content-length")) is not None and int(declared) > MAX_NARRATION_UPLOAD_BYTES: raise ValueError("draft_readiness_narration_upload_too_large")
            stage = store.project_root(project_id) / "staging" / f"narration-{uuid4().hex}.webm"
            stage.parent.mkdir(parents=True, exist_ok=True); total = 0
            with stage.open("wb") as handle:
                while chunk := await file.read(NARRATION_UPLOAD_CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_NARRATION_UPLOAD_BYTES: raise ValueError("draft_readiness_narration_upload_too_large")
                    handle.write(chunk)
            asset = orchestrator.register_narration_audio(project_id=project_id, source_path=stage)
            return {"asset_id": asset.asset_id, "asset_type": asset.asset_type}
        except Exception as exc: raise _http_error(exc) from exc
        finally:
            if stage is not None: stage.unlink(missing_ok=True)
            await file.close()

    #: 찍어 둔 영상으로 시작하는 길. 대본이 없어도 첫 걸음을 뗄 수 있는 **유일한 길**이다.
    SOURCE_VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".mkv", ".m4v")

    @router.post("/api/projects/{project_id}/source-video/upload", status_code=status.HTTP_201_CREATED)
    async def upload_source_video(project_id: str, file: UploadFile = File(...)) -> SourceVideoStartResponse:
        """올린 영상에서 말을 받아써 대본으로 돌려준다.

        지금까지는 `create_creation_brief`가 `script_text`를 요구해서 **대본이 없으면
        시작 자체가 안 됐다.** 부품은 다 있었다 -- 받아쓰기는 자산 종류를 가리지 않아
        영상 파일에도 그대로 돈다. 없던 것은 이 한 걸음뿐이다.

        올린 영상은 버리지 않고 프로젝트 자산으로 남긴다. 그 영상이 곧 본편이라
        내레이션으로도 골라야 하기 때문이다.
        """
        stage: Path | None = None
        try:
            store.get_project(project_id=project_id)
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in SOURCE_VIDEO_SUFFIXES:
                raise ValueError("source_video_upload_invalid")
            stage = store.project_root(project_id) / "staging" / f"source-{uuid4().hex}{suffix}"
            stage.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with stage.open("wb") as handle:
                while chunk := await file.read(NARRATION_UPLOAD_CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_NARRATION_UPLOAD_BYTES:
                        raise ValueError("source_video_upload_too_large")
                    handle.write(chunk)
            asset = orchestrator.register_raw_video_asset(project_id=project_id, source_path=stage)
            heard = orchestrator.transcribe_source_video(project_id=project_id, asset_id=asset.asset_id)
            spoken = [item for item in (heard.get("segments") or []) if str(item.get("text") or "").strip()]
            if not str(heard.get("transcript_text") or "").strip() or not spoken:
                # 무음 영상으로 빈 대본을 만들면 다음 화면이 전부 빈 채로 흘러간다.
                # 2026-08-16에 완전 무음 완성본이 그렇게 나갔다 -- 여기서 멈춘다.
                raise _no_speech()
            return SourceVideoStartResponse(
                asset_id=asset.asset_id,
                script_text=str(heard["transcript_text"]).strip(),
                spoken_segment_count=len(spoken),
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)
            await file.close()

    @router.post("/api/projects/{project_id}/draft-readiness/broll/upload", status_code=status.HTTP_201_CREATED)
    async def upload_broll(project_id: str, file: UploadFile = File(...)) -> dict[str, object]:
        stage: Path | None = None
        try:
            store.get_project(project_id=project_id)
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".mp4", ".mov", ".webm", ".mkv"}: raise ValueError("draft_readiness_broll_upload_invalid")
            if (declared := file.headers.get("content-length")) is not None and int(declared) > MAX_NARRATION_UPLOAD_BYTES: raise ValueError("draft_readiness_broll_upload_too_large")
            stage = store.project_root(project_id) / "staging" / f"broll-{uuid4().hex}{suffix}"
            stage.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with stage.open("wb") as handle:
                while chunk := await file.read(NARRATION_UPLOAD_CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_NARRATION_UPLOAD_BYTES: raise ValueError("draft_readiness_broll_upload_too_large")
                    handle.write(chunk)
            if total == 0: raise ValueError("draft_readiness_broll_upload_empty")
            asset = orchestrator.register_broll_asset(project_id=project_id, source_path=stage, title=Path(file.filename or "영상").stem, tags=[])
            return {"asset_id": asset.asset_id, "asset_type": asset.asset_type, "scan_status": "local_ready"}
        except Exception as exc: raise _http_error(exc) from exc
        finally:
            if stage is not None: stage.unlink(missing_ok=True)
            await file.close()
    return router
