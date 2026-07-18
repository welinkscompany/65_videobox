from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile, status

from videobox_api.errors import _http_error
from videobox_api.models import DraftReadinessCandidateRangeRequest, DraftReadinessCandidateRequest, DraftReadinessCreateRequest, DraftReadinessRevisionRequest
from videobox_api.orchestration import ApiOrchestrator

MAX_NARRATION_UPLOAD_BYTES = 128 * 1024 * 1024
NARRATION_UPLOAD_CHUNK_BYTES = 64 * 1024


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
