from __future__ import annotations

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import AtomicDraftBundleCreateRequest
from videobox_api.orchestration import ApiOrchestrator


def build_atomic_draft_bundles_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/draft-bundles", status_code=status.HTTP_201_CREATED)
    def create(project_id: str, payload: AtomicDraftBundleCreateRequest) -> dict[str, object]:
        try:
            return orchestrator.materialize_atomic_draft_bundle(project_id=project_id, **payload.model_dump())
        except Exception as exc:
            raise _http_error(exc) from exc

    return router
