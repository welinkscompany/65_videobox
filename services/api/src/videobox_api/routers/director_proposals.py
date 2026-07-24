from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
import os
import json
from threading import Event, Thread
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from videobox_core_engine.director_proposal_service import DirectorProposalBlockedError, DirectorProposalService
from videobox_core_engine.director_proposals import proposal_to_payload
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.local_project_store import EditingSessionRevisionConflict, sha256_file
from videobox_core_engine.editing_transactions import apply_user_transaction
from videobox_core_engine.director_commands import director_timeline_references, resolve_director_command
from videobox_provider_interfaces.llm import LLMTaskType
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_api.models import (
    DirectorConversationCreateRequest, DirectorConversationResponse,
    DirectorMessageExchangeResponse, DirectorMessageListResponse, DirectorMessageSubmitRequest,
)


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


class ProposalBatchApplyRequest(ProposalApplyRequest):
    """A single explicit user action; materialization happens only inside this endpoint."""


def build_director_proposals_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()
    service = DirectorProposalService(store)
    materializer = ProjectAssetMaterializer(store)

    def payload(project_id, proposal):
        return proposal_to_payload(proposal) | {"status": proposal.status, "lifecycle": store.get_director_proposal_lifecycle(project_id, proposal.proposal_id)}

    @router.get("/api/projects/{project_id}/director/sessions/{session_id}/reload")
    def reload_session(project_id: str, session_id: str) -> dict:
        """Read durable Director state only; a reload must never create or mutate it."""
        try:
            store.get_editing_session(project_id=project_id, session_id=session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_session_missing") from exc
        conversation = store.latest_director_conversation(project_id=project_id, session_id=session_id)
        proposal = next((item for item in reversed(store.list_director_proposals(project_id)) if item.source_session_id == session_id), None)
        messages = store.list_director_messages(project_id=project_id, conversation_id=str(conversation["conversation_id"])) if conversation else []
        return {
            "conversation": conversation,
            "messages": messages,
            "proposal": payload(project_id, proposal) if proposal else None,
            "references": [
                {
                    "reference_code": str(item["reference_code"]),
                    "immutable_id": {
                        "segment_id": str(item["segment_id"]),
                        "track_type": str(item["track_type"]),
                    },
                    "source": "timeline",
                }
                for item in director_timeline_references(
                    store.get_editing_session(project_id=project_id, session_id=session_id)
                ).get("segments", [])
            ],
        }

    @router.post("/api/projects/{project_id}/director/conversations", status_code=status.HTTP_201_CREATED, response_model=DirectorConversationResponse)
    def create_conversation(project_id: str, body: DirectorConversationCreateRequest) -> dict:
        try:
            conversation_id = __import__("uuid").uuid4().hex
            return store.create_director_conversation(project_id=project_id, session_id=body.session_id, conversation_id=conversation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="editing_session_missing") from exc

    @router.get("/api/projects/{project_id}/director/conversations/{conversation_id}/messages", response_model=DirectorMessageListResponse)
    def list_conversation_messages(project_id: str, conversation_id: str, session_id: str) -> dict:
        try:
            conversation = store.get_director_conversation(project_id=project_id, conversation_id=conversation_id)
            if str(conversation["session_id"]) != session_id:
                raise KeyError("director_conversation_missing")
            return {"messages": store.list_director_messages(project_id=project_id, conversation_id=conversation_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="director_conversation_missing") from exc

    @router.post(
        "/api/projects/{project_id}/director/conversations/{conversation_id}/messages",
        response_model=DirectorMessageExchangeResponse,
        responses={202: {"description": "A duplicate client message is still generating locally; retry after the Retry-After header."}},
    )
    def submit_conversation_message(project_id: str, conversation_id: str, body: DirectorMessageSubmitRequest, request: Request) -> dict:
        try:
            store.get_editing_session(project_id=project_id, session_id=body.session_id)
            conversation = store.get_director_conversation(project_id=project_id, conversation_id=conversation_id)
            if str(conversation["session_id"]) != body.session_id:
                raise KeyError("director_conversation_missing")
            existing = store.get_director_exchange_by_client_message_id(
                project_id=project_id, conversation_id=conversation_id,
                session_id=body.session_id,
                client_message_id=body.client_message_id, user_text=body.text,
            )
            if existing is not None:
                return existing | dict(existing["assistant_message"].get("metadata") or {})
            owner_token = store.claim_director_message(
                project_id=project_id, session_id=body.session_id, conversation_id=conversation_id,
                client_message_id=body.client_message_id, user_text=body.text,
            )
            if not owner_token:
                # Generation may use the full 30-second local-runtime request
                # budget.  A duplicate is therefore immediately retryable,
                # rather than waiting a shorter, contradictory server timeout.
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"status": "director_message_in_progress", "retry_after_seconds": 1},
                    headers={"Retry-After": "1"},
                )
            session = store.get_editing_session(project_id=project_id, session_id=body.session_id)
            proposals = [proposal for proposal in store.list_director_proposals(project_id) if proposal.source_session_id == body.session_id and proposal.status == "ready"]
            open_proposal = proposal_to_payload(proposals[-1]) if proposals else None
            resolution = resolve_director_command(body.text, open_proposal=open_proposal, timeline=director_timeline_references(session))
            resolution_metadata: dict[str, object] = {}
            proposal_id: str | None = open_proposal["proposal_id"] if open_proposal else None
            if resolution.status == "needs_disambiguation":
                resolution_metadata["disambiguation"] = {
                    "status": "needs_disambiguation",
                    "options": [{"reference_code": option.reference_code, "immutable_id": option.immutable_id, "source": option.source} for option in resolution.options],
                }
                assistant_text = "어느 참조인지 선택해주세요."
            elif resolution.status == "resolved" and resolution.reference is not None:
                resolution_metadata["reference"] = {"reference_code": resolution.reference.reference_code, "immutable_id": resolution.reference.immutable_id, "source": resolution.reference.source}
                assert resolution.action_intent is not None
                resolution_metadata["action_intent"] = {
                    "action": resolution.action_intent.action,
                    "target": {
                        "reference_code": resolution.action_intent.target.reference_code,
                        "immutable_id": resolution.action_intent.target.immutable_id,
                        "source": resolution.action_intent.target.source,
                    },
                    "proposal_preflight": resolution.action_intent.proposal_preflight,
                }
                assistant_text = "참조를 확인했습니다."
            else:
                assistant_text = ""
            # Generate before opening the persistence writer transaction.  No
            # fallback graph is present: only the app-injected local runtime is used.
            if not assistant_text:
                runtime = request.app.state.local_only_runtime_service_factory(store)
                stop_heartbeat = Event()
                def heartbeat() -> None:
                    while not stop_heartbeat.wait(1.0):
                        store.heartbeat_director_message_claim(project_id=project_id, conversation_id=conversation_id, client_message_id=body.client_message_id, owner_token=owner_token)
                heartbeat_thread = Thread(target=heartbeat, daemon=True)
                heartbeat_thread.start()
                try:
                    if hasattr(runtime, "generate_structured"):
                        generated = runtime.generate_structured(
                            project_id=project_id,
                            task_type=LLMTaskType.OPERATOR_COPY,
                            prompt=body.text,
                            response_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                        )
                        data = getattr(generated, "output_data", {})
                        assistant_text = str(data.get("text", "")) if isinstance(data, dict) else ""
                        if not assistant_text:
                            assistant_text = str(getattr(generated, "raw_text", "local director response"))
                        trace = getattr(generated, "metadata", {}).get("provider_trace")
                        if isinstance(trace, dict):
                            resolution_metadata["provider_trace"] = trace
                    elif hasattr(runtime, "generate"):
                        generated = runtime.generate(
                            project_id=project_id, task_type=LLMTaskType.OPERATOR_COPY, prompt=body.text,
                            response_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                        )
                        data = getattr(generated, "output_data", {})
                        assistant_text = str(data.get("text", "local director response")) if isinstance(data, dict) else "local director response"
                        trace = getattr(generated, "metadata", {}).get("provider_trace")
                        if isinstance(trace, dict):
                            resolution_metadata["provider_trace"] = trace
                    else:
                        raise RuntimeError("injected runtime does not support local structured generation")
                except Exception as exc:
                    assistant_text = f"local_only_blocked: {exc}"
                    trace = getattr(exc, "provider_trace", None)
                    safe_trace = trace if isinstance(trace, dict) and trace.get("routing_mode") == "local_only" else build_provider_trace(
                        final_provider=str(getattr(exc, "provider_name", "local_only_runtime")),
                        fallback_reasons=["local_provider_error"], routing_mode="local_only",
                    )
                    resolution_metadata.update({
                        "status": "blocked",
                        "error_code": str(getattr(exc, "error_code", "local_runtime_error")),
                        "provider_trace": safe_trace,
                    })
                finally:
                    stop_heartbeat.set()
                    heartbeat_thread.join(timeout=1.5)
            exchange = store.append_director_exchange(
                project_id=project_id, session_id=body.session_id, conversation_id=conversation_id,
                client_message_id=body.client_message_id, user_text=body.text, assistant_text=assistant_text,
                proposal_id=proposal_id, assistant_metadata=resolution_metadata, owner_token=owner_token,
            )
            return exchange | resolution_metadata
        except KeyError as exc:
            detail = str(exc).strip("'")
            raise HTTPException(status_code=404, detail=detail) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
            current_asset_index_revision = store.get_asset_index_revision(project_id)
            for candidate in selected:
                candidates_for_id = [
                    asset for asset in store.list_assets(project_id=project_id)
                    if dict(asset.get("metadata") or {}).get("director_proposal_candidate_id") == candidate.candidate_id
                ]
                found = next(
                    (
                        asset for asset in reversed(candidates_for_id)
                        if dict(asset.get("metadata") or {}).get("director_materialized_sha256") == candidate.expected_content_sha256
                        and dict(asset.get("metadata") or {}).get("source_asset_id") == candidate.asset_id
                        and dict(asset.get("metadata") or {}).get("director_materialized_asset_index_revision") == current_asset_index_revision
                    ),
                    None,
                )
                if found is None:
                    if candidates_for_id:
                        raise HTTPException(status_code=409, detail="asset_index_revision_mismatch")
                    raise ValueError("candidate_not_materialized")
                metadata = dict(found.get("metadata") or {})
                if metadata.get("director_materialized_asset_index_revision") != current_asset_index_revision:
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
                    segment[key] = {"asset_id": asset["asset_id"], "asset_uri": asset["storage_uri"], "media_controls": dict(candidate.controls), "expected_content_sha256": candidate.expected_content_sha256, "media_revision": str(asset.get("created_at") or ""), "warning_provenance": list(candidate.warning_provenance)}
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

    @router.post("/api/projects/{project_id}/director/proposals/{proposal_id}/batch-apply")
    def batch_apply(project_id: str, proposal_id: str, body: ProposalBatchApplyRequest) -> dict:
        """Stage all requested bytes, then atomically register and apply them in one CAS write."""
        staged: list[dict] = []
        try:
            proposal = service.get(project_id=project_id, proposal_id=proposal_id)
            if proposal.base_session_revision != body.expected_revision:
                raise HTTPException(status_code=409, detail="proposal_revision_mismatch")
            if service.stale_reasons(project_id=project_id, proposal=proposal):
                raise HTTPException(status_code=409, detail="stale_proposal")
            candidates_by_id = {item.candidate_id: item for item in proposal.candidates}
            if len(set(body.candidate_ids)) != len(body.candidate_ids):
                raise ValueError("candidate_ids_duplicate")
            selected = [candidates_by_id[item] for item in body.candidate_ids]
            staged, materialized = materializer.stage_batch(project_id=project_id, candidates=selected)
            session = store.get_editing_session(project_id=project_id, session_id=proposal.source_session_id)
            if int(session.get("session_revision") or 1) != body.expected_revision:
                raise HTTPException(status_code=409, detail="session_revision_mismatch")
            placements = {str(item.get("candidate_id")): str(item.get("target_segment_id")) for item in proposal.diff.get("placements", {}).get("add", [])}
            def mutate(draft: dict) -> None:
                by_id = {str(segment.get("segment_id")): segment for segment in draft.get("segments", []) if isinstance(segment, dict)}
                for candidate in selected:
                    segment = by_id.get(placements.get(candidate.candidate_id, ""))
                    if segment is None:
                        raise ValueError("target_segment_missing")
                    key = {"broll": "broll_override", "bgm": "music_override", "sfx": "sfx_override"}[candidate.media_type]
                    asset = materialized[candidate.candidate_id]
                    segment[key] = {"asset_id": asset["asset_id"], "asset_uri": asset["storage_uri"], "media_controls": dict(candidate.controls), "expected_content_sha256": candidate.expected_content_sha256, "media_revision": asset["created_at"], "warning_provenance": list(candidate.warning_provenance)}
            updated = apply_user_transaction(session=session, label="디렉터 제안 일괄 적용", affected_segment_ids=[placements[item.candidate_id] for item in selected], mutate=mutate)
            return store.batch_apply_director_proposal_transaction(
                project_id=project_id, session_id=proposal.source_session_id, proposal_id=proposal_id,
                session_payload=updated, expected_revision=body.expected_revision, proposal_base_revision=proposal.base_session_revision,
                expected_asset_index_revision=proposal.asset_index_revision, staged_assets=staged,
            )
        except HTTPException:
            raise
        except EditingSessionRevisionConflict:
            raise HTTPException(status_code=409, detail="stale_proposal") from None
        except (KeyError, ValueError):
            raise HTTPException(status_code=422, detail="candidate_unavailable") from None
        finally:
            materializer.cleanup_staged(staged)

    @router.get("/api/projects/{project_id}/director/preferences")
    def get_preferences(project_id: str) -> dict:
        return store.get_director_preferences(project_id)

    @router.put("/api/projects/{project_id}/director/preferences")
    def put_preferences(project_id: str, body: PreferencesRequest) -> dict:
        return store.save_director_preferences(project_id, body.model_dump(exclude_unset=True))

    return router


def _mime_type(path) -> str | None:
    return {".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4"}.get(path.suffix.lower())


def _remove_preview_snapshot(path) -> None:
    if path.exists():
        os.remove(path)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        os.rmdir(parent)
