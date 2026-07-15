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
from videobox_storage.local_project_store import EditingSessionRevisionConflict, sha256_file
from videobox_core_engine.editing_transactions import apply_user_transaction


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


class ProposalApplyRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1)
    expected_revision: int = Field(ge=1)


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
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            return materializer.materialize(project_id=project_id, candidate=candidate, expected_asset_index_revision=proposal.asset_index_revision)
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail="candidate_unavailable") from None

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/refresh", status_code=status.HTTP_201_CREATED)
    def refresh(project_id: str, proposal_id: str) -> dict:
        try:
            return payload(project_id, service.refresh(project_id=project_id, proposal_id=proposal_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/apply")
    def apply(project_id: str, proposal_id: str, body: ProposalApplyRequest) -> dict:
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            if proposal.base_session_revision != body.expected_revision:
                raise HTTPException(status_code=409, detail="proposal_revision_mismatch")
            candidates = {item.candidate_id: item for item in proposal.candidates}
            selected = [candidates[item] for item in body.candidate_ids]
            materialized: dict[str, dict] = {}
            for candidate in selected:
                found = next((asset for asset in store.list_assets(project_id=project_id)
                    if dict(asset.get("metadata") or {}).get("director_proposal_candidate_id") == candidate.candidate_id), None)
                if found is None:
                    raise ValueError("candidate_not_materialized")
                metadata = dict(found.get("metadata") or {})
                if metadata.get("director_materialized_asset_index_revision") != store.get_asset_index_revision(project_id):
                    raise HTTPException(status_code=409, detail="asset_index_revision_mismatch")
                path = store.resolve_storage_uri(project_id=project_id, storage_uri=str(found["storage_uri"]))
                if not path.is_file() or sha256_file(path) != candidate.expected_content_sha256:
                    raise ValueError("materialized_sha_mismatch")
                materialized[candidate.candidate_id] = found
            session = store.get_editing_session(project_id=project_id, session_id=proposal.source_session_id)
            if int(session.get("session_revision") or 1) != body.expected_revision:
                raise HTTPException(status_code=409, detail="session_revision_mismatch")
            def mutate(draft: dict) -> None:
                by_id = {str(segment.get("segment_id")): segment for segment in draft.get("segments", []) if isinstance(segment, dict)}
                for candidate in selected:
                    target = next((item.get("target_segment_id") for item in proposal.diff.get("placements", {}).get("add", []) if item.get("candidate_id") == candidate.candidate_id), None)
                    segment = by_id.get(str(target))
                    if segment is None:
                        raise ValueError("target_segment_missing")
                    key = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}[candidate.media_type]
                    asset = materialized[candidate.candidate_id]
                    segment[key] = {"asset_id": asset["asset_id"], "asset_uri": asset["storage_uri"], "media_controls": dict(candidate.controls), "expected_content_sha256": candidate.expected_content_sha256, "media_revision": str(asset.get("created_at") or "")}
            updated = apply_user_transaction(session=session, label="디렉터 제안 적용", affected_segment_ids=list(proposal.target_segment_ids), mutate=mutate)
            expectations = [
                (str(materialized[item.candidate_id]["asset_id"]), item.expected_content_sha256,
                 int(dict(materialized[item.candidate_id].get("metadata") or {})["director_materialized_asset_index_revision"]))
                for item in selected
            ]
            return store.apply_director_proposal_transaction(project_id=project_id, session_id=proposal.source_session_id, proposal_id=proposal_id, session_payload=updated, expected_revision=body.expected_revision, proposal_base_revision=proposal.base_session_revision, materialized_expectations=expectations)
        except HTTPException:
            raise
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail="candidate_unavailable") from None
        except EditingSessionRevisionConflict:
            raise HTTPException(status_code=409, detail="session_revision_mismatch") from None

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
