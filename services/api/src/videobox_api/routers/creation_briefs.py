from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    CreationBriefAnswerRequest, CreationBriefCreateRequest, CreationBriefRevisionRequest,
    CreationBriefPreviousQuestionRequest, CreationBriefSummaryRequest,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_storage.local_project_store import LocalProjectStore

MAX_CREATION_BRIEF_SCRIPT_BYTES = 1024 * 1024


def build_creation_briefs_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()
    store = orchestrator.store

    @router.post("/api/projects/{project_id}/creation-briefs", status_code=status.HTTP_201_CREATED)
    def create(project_id: str, payload: CreationBriefCreateRequest) -> dict[str, object]:
        try:
            return orchestrator.create_creation_brief(project_id=project_id, **payload.model_dump())
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/creation-briefs/upload", status_code=status.HTTP_201_CREATED)
    async def upload(
        project_id: str,
        script_file: UploadFile = File(...),
        idempotency_key: str = Form(...),
        capability_profile_json: str = Form("{}"),
    ) -> dict[str, object]:
        try:
            content_length = script_file.headers.get("content-length")
            if content_length is not None and int(content_length) > MAX_CREATION_BRIEF_SCRIPT_BYTES:
                raise ValueError("creation_brief_script_too_large")
            chunks: list[bytes] = []
            total = 0
            while chunk := await script_file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_CREATION_BRIEF_SCRIPT_BYTES:
                    raise ValueError("creation_brief_script_too_large")
                chunks.append(chunk)
            raw = b"".join(chunks)
            try:
                script_text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("creation_brief_script_not_utf8") from exc
            try:
                capability_profile = json.loads(capability_profile_json)
            except json.JSONDecodeError as exc:
                raise ValueError("creation_brief_capability_profile_invalid") from exc
            if not isinstance(capability_profile, dict):
                raise ValueError("creation_brief_capability_profile_invalid")
            return orchestrator.create_creation_brief(
                project_id=project_id, script_filename=script_file.filename or "script.txt", script_text=script_text,
                idempotency_key=idempotency_key, capability_profile=capability_profile,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/creation-briefs/{brief_id}")
    def get(project_id: str, brief_id: str) -> dict[str, object]:
        try:
            return store.get_creation_brief(project_id=project_id, brief_id=brief_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/creation-briefs")
    def list_latest(project_id: str) -> dict[str, object]:
        try:
            return {"briefs": store.list_creation_briefs(project_id=project_id)}
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/creation-briefs/{brief_id}/questions/{question_id}")
    def answer(project_id: str, brief_id: str, question_id: str, payload: CreationBriefAnswerRequest) -> dict[str, object]:
        try:
            return store.answer_creation_brief_question(
                project_id=project_id, brief_id=brief_id, question_id=question_id,
                answer=payload.answer, expected_revision=payload.expected_revision,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/creation-briefs/{brief_id}/answers")
    def answer_from_body(project_id: str, brief_id: str, payload: CreationBriefAnswerRequest) -> dict[str, object]:
        if not payload.question_id:
            raise _http_error(ValueError("creation_brief_question_id_required"))
        return answer(project_id, brief_id, payload.question_id, payload)

    @router.post("/api/projects/{project_id}/creation-briefs/{brief_id}/previous-question")
    def previous_question(
        project_id: str, brief_id: str, payload: CreationBriefPreviousQuestionRequest
    ) -> dict[str, object]:
        try:
            return store.previous_creation_brief_question(
                project_id=project_id,
                brief_id=brief_id,
                expected_revision=payload.expected_revision,
            )
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/creation-briefs/{brief_id}/bypass")
    def bypass(project_id: str, brief_id: str, payload: CreationBriefRevisionRequest) -> dict[str, object]:
        try:
            return store.bypass_creation_interview(project_id=project_id, brief_id=brief_id, expected_revision=payload.expected_revision)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.patch("/api/projects/{project_id}/creation-briefs/{brief_id}")
    def update_summary(project_id: str, brief_id: str, payload: CreationBriefSummaryRequest) -> dict[str, object]:
        try:
            return store.update_creation_brief_summary(project_id=project_id, brief_id=brief_id, summary=payload.summary, expected_revision=payload.expected_revision)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/creation-briefs/{brief_id}/approve")
    def approve(project_id: str, brief_id: str, payload: CreationBriefRevisionRequest) -> dict[str, object]:
        try:
            return store.approve_creation_brief(project_id=project_id, brief_id=brief_id, expected_revision=payload.expected_revision)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.delete("/api/projects/{project_id}/creation-briefs/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(project_id: str, brief_id: str) -> Response:
        try:
            store.delete_creation_brief(project_id=project_id, brief_id=brief_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
