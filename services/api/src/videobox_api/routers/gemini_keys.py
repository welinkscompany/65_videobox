from __future__ import annotations

from fastapi import APIRouter, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    GeminiProviderKeyCreateRequest,
    GeminiProviderKeyListResponse,
    GeminiProviderKeyResponse,
    GeminiProviderKeyUpdateRequest,
)
from videobox_api.orchestration import ApiOrchestrator


def build_gemini_keys_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/providers/gemini/keys")
    def list_gemini_provider_keys(project_id: str) -> GeminiProviderKeyListResponse:
        try:
            keys = orchestrator.list_gemini_provider_keys(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyListResponse(
            keys=[GeminiProviderKeyResponse(**item) for item in keys]
        )

    @router.post("/api/projects/{project_id}/providers/gemini/keys", status_code=status.HTTP_201_CREATED)
    def create_gemini_provider_key(
        project_id: str,
        payload: GeminiProviderKeyCreateRequest,
    ) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.save_gemini_provider_key(
                project_id=project_id,
                label=payload.label,
                api_key_secret=payload.api_key,
                primary_model=payload.primary_model,
                cheap_model=payload.cheap_model,
                high_quality_model=payload.high_quality_model,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @router.patch("/api/projects/{project_id}/providers/gemini/keys/{key_id}")
    def update_gemini_provider_key(
        project_id: str,
        key_id: str,
        payload: GeminiProviderKeyUpdateRequest,
    ) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.update_gemini_provider_key(
                project_id=project_id,
                key_id=key_id,
                label=payload.label,
                primary_model=payload.primary_model,
                cheap_model=payload.cheap_model,
                high_quality_model=payload.high_quality_model,
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @router.post("/api/projects/{project_id}/providers/gemini/keys/{key_id}/disable")
    def disable_gemini_provider_key(project_id: str, key_id: str) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.set_gemini_provider_key_status(
                project_id=project_id,
                key_id=key_id,
                status="disabled",
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    @router.post("/api/projects/{project_id}/providers/gemini/keys/{key_id}/enable")
    def enable_gemini_provider_key(project_id: str, key_id: str) -> GeminiProviderKeyResponse:
        try:
            result = orchestrator.set_gemini_provider_key_status(
                project_id=project_id,
                key_id=key_id,
                status="active",
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return GeminiProviderKeyResponse(**result)

    return router
