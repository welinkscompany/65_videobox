from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from videobox_api.hermes_capabilities import (
    HermesCapabilityError,
    HermesCapabilityUnavailableError,
    HermesCapabilityVerifier,
)
from videobox_api.models import HermesProjectStatusResponse
from videobox_storage.local_project_store import LocalProjectStore


def build_hermes_internal_router(store: LocalProjectStore, verifier: HermesCapabilityVerifier) -> APIRouter:
    router = APIRouter()

    @router.get("/internal/hermes/projects/{project_id}/status", response_model=HermesProjectStatusResponse)
    def get_project_status(project_id: str, authorization: str | None = Header(default=None)) -> HermesProjectStatusResponse:
        try:
            token = _bearer_token(authorization)
            verifier.verify_for_project_status(token, project_id=project_id)
        except HermesCapabilityUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="hermes_capability_unavailable",
            ) from exc
        except HermesCapabilityError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        try:
            project = store.get_project(project_id=project_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found") from exc
        try:
            session = store.get_latest_editing_session(project_id=project_id)
        except KeyError:
            session = None
        return HermesProjectStatusResponse(
            project_id=str(project["project_id"]),
            name=str(project["name"]),
            status=str(project["status"]),
            updated_at=str(project["updated_at"]),
            has_editing_session=session is not None,
            latest_session_revision=(int(session["session_revision"]) if session is not None else None),
        )

    return router


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HermesCapabilityError("hermes_capability_missing")
    scheme, separator, token = authorization.partition(" ")
    if scheme != "Bearer" or not separator or not token or token.strip() != token:
        raise HermesCapabilityError("hermes_capability_malformed")
    return token
