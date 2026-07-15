from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from videobox_core_engine.director_proposal_service import DirectorProposalBlockedError, DirectorProposalService
from videobox_core_engine.director_proposals import proposal_to_payload
from videobox_storage.local_project_store import LocalProjectStore


class ProposalCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    expires_at: str | None = None


class PreferencesRequest(BaseModel):
    pin_asset: list[str] = []
    exclude_asset: list[str] = []
    exclude_creator: list[str] = []
    exclude_tag: list[str] = []


def build_director_proposals_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()
    service = DirectorProposalService(store)

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
