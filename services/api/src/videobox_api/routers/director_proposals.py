from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
import os
import json
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from videobox_core_engine.director_proposal_service import DirectorProposalBlockedError, DirectorProposalService
from videobox_core_engine.director_proposals import proposal_to_payload
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_storage.local_project_store import LocalProjectStore


class ProposalCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    expires_at: str | None = None

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_iso8601(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    raise ValueError("expires_at must include timezone")
            except ValueError as exc:
                raise ValueError("expires_at must be ISO-8601") from exc
        return value


class PreferencesRequest(BaseModel):
    pin_asset: list[str] = []
    exclude_asset: list[str] = []
    exclude_creator: list[str] = []
    exclude_tag: list[str] = []


def build_director_proposals_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()
    service = DirectorProposalService(store)
    materializer = ProjectAssetMaterializer(store)

    def payload(project_id, proposal):
        return proposal_to_payload(proposal) | {"status": proposal.status, "lifecycle": store.get_director_proposal_lifecycle(project_id, proposal.proposal_id)}

    @router.post("/api/projects/{project_id}/director/proposals", status_code=status.HTTP_201_CREATED)
    def create(project_id: str, body: ProposalCreateRequest) -> dict:
        try:
            return payload(project_id, service.create(project_id=project_id, session_id=body.session_id, expires_at=body.expires_at))
        except DirectorProposalBlockedError as exc:
            return JSONResponse(status_code=409, content={"code": "director_analysis_blocked", "lifecycle": exc.lifecycle})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/director/proposals/{proposal_id}")
    def get(project_id: str, proposal_id: str) -> dict:
        try:
            return payload(project_id, service.get(project_id=project_id, proposal_id=proposal_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/preflight")
    def preflight(project_id: str, proposal_id: str) -> dict:
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        reasons = service.stale_reasons(project_id=project_id, proposal=proposal)
        immutable_diff = proposal_to_payload(proposal)["diff"]
        if reasons:
            return JSONResponse(status_code=409, content={"code": "stale_proposal", "stale_reasons": reasons, "action": "refresh", "diff": immutable_diff})
        return {"proposal_id": proposal.proposal_id, "status": "ready", "reasons": [], "diff": immutable_diff}

    def candidate_for(project_id: str, proposal_id: str, candidate_id: str):
        proposal = service.get(project_id=project_id, proposal_id=proposal_id)
        if service.stale_reasons(project_id=project_id, proposal=proposal):
            raise HTTPException(status_code=409, detail="stale_proposal")
        candidate = next((item for item in proposal.candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise HTTPException(status_code=404, detail="candidate_missing")
        return candidate

    @router.get("/api/projects/{project_id}/director/proposals/{proposal_id}/candidates/{candidate_id:path}/preview")
    def preview_candidate(project_id: str, proposal_id: str, candidate_id: str):
        try:
            candidate = candidate_for(project_id, proposal_id, candidate_id)
            source = materializer.preview_snapshot(project_id=project_id, candidate=candidate)
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail="candidate_unavailable") from None
        return FileResponse(source, media_type=_mime_type(source), background=BackgroundTask(_remove_preview_snapshot, source), headers={"X-VideoBox-Proposal-Controls": json.dumps(dict(candidate.controls), sort_keys=True), "X-VideoBox-Autoplay": "false", "X-VideoBox-In-Sec": str(candidate.controls.get("in_sec", "")), "X-VideoBox-Out-Sec": str(candidate.controls.get("out_sec", ""))})

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/candidates/{candidate_id:path}/materialize", status_code=status.HTTP_201_CREATED)
    def materialize_candidate(project_id: str, proposal_id: str, candidate_id: str) -> dict:
        try:
            candidate = candidate_for(project_id, proposal_id, candidate_id)
            return materializer.materialize(project_id=project_id, candidate=candidate)
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail="candidate_unavailable") from None

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/refresh", status_code=status.HTTP_201_CREATED)
    def refresh(project_id: str, proposal_id: str) -> dict:
        try:
            return payload(project_id, service.refresh(project_id=project_id, proposal_id=proposal_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/director/preferences")
    def get_preferences(project_id: str) -> dict:
        return store.get_director_preferences(project_id)

    @router.put("/api/projects/{project_id}/director/preferences")
    def put_preferences(project_id: str, body: PreferencesRequest) -> dict:
        return store.save_director_preferences(project_id, body.model_dump())

    return router


def _mime_type(path) -> str | None:
    return {".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4"}.get(path.suffix.lower())


def _remove_preview_snapshot(path) -> None:
    if path.exists():
        os.remove(path)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        os.rmdir(parent)
