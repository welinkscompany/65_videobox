from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, Response, UploadFile, status
from starlette.applications import Starlette

from videobox_api.errors import _http_error
from videobox_api.models import (
    CreationBriefAnswerRequest, CreationBriefCreateRequest, CreationBriefRevisionRequest,
    CreationBriefPreviousQuestionRequest, CreationBriefSummaryRequest,
)
from videobox_api.orchestration import ApiOrchestrator
from videobox_storage.local_project_store import LocalProjectStore

MAX_CREATION_BRIEF_SCRIPT_BYTES = 1024 * 1024

# CLAUDE.md §8이 못박은 호칭이다 -- 결재함 큐로 나가는 항목도 같은 이름을 쓴다.
_APPROVAL_TARGET = "루이스 대표님"

_LOGGER = logging.getLogger("uvicorn.error")


async def _notify_script_confirmation_queue(
    app: Starlette, *, project_id: str, brief: dict[str, object]
) -> None:
    """AK-System Hermes 결재함 큐(§10.14 2-D, W1015)에 pending 항목을 넣는다.

    **이 호출이 실패해도 대본 확정 자체는 이미 끝난 뒤다.** 결재함 큐는
    부가 알림 경로이지 이 승인의 사실 원본이 아니다 -- 큐가 안 켜져 있거나
    (agent_gateway_client 없음) 응답이 없어도 owner의 실제 승인은
    creation_briefs 저장소에 이미 반영돼 있다.

    대본 확정과 같은 순간에 **제목 후보도 함께 뽑아 올린다** — 제목 선택도
    같은 사람 게이트 셋의 하나다. 제목 생성이 실패해도 대본 확정 큐 전송은
    막지 않는다 — 서로 독립된 최선노력이다.

    코드리뷰(2026-09-24): 이 알림은 `approve()`가 이미 저장을 끝낸 뒤에
    붙는 부가 경로라서, 응답을 기다리게 하지 않고 `BackgroundTasks`로
    돈다 -- owner의 "대본 확정" 클릭이 LLM/네트워크 왕복만큼 느려지지
    않는다.
    """
    client = getattr(app.state, "agent_gateway_client", None)
    if client is None:
        return
    script_text = str(brief.get("script_text") or "").strip()
    summary = str(brief.get("summary") or "").strip()
    if not script_text:
        return
    cycle_id = str(brief.get("brief_id") or "")
    try:
        await client.submit_script_confirmation(
            project_id=project_id,
            cycle_id=cycle_id,
            script_candidates=[{"index": 0, "text": script_text}],
            question=summary or "이 대본을 확정해도 될까요?",
            target=_APPROVAL_TARGET,
        )
    except Exception:  # noqa: BLE001 - 결재함 알림은 최선노력이다
        _LOGGER.warning(
            "AK-System Hermes 결재함 큐에 대본 확정 항목을 넣지 못했습니다.",
            exc_info=True,
        )
    await _notify_title_candidates_queue(
        app, project_id=project_id, cycle_id=cycle_id, script_text=script_text,
    )


async def _notify_title_candidates_queue(
    app: Starlette, *, project_id: str, cycle_id: str, script_text: str
) -> None:
    client = getattr(app.state, "agent_gateway_client", None)
    writer = getattr(app.state, "title_candidate_writer", None)
    if client is None or writer is None:
        return
    try:
        # 코드리뷰(2026-09-24): `write()`는 로컬 LLM을 동기로 부른다 --
        # 실측상 GPU 경합 시 수십 초까지 걸린다(§10.14 관련 메모). 이 함수는
        # 백그라운드 태스크로 도는 이벤트 루프 위에서 실행되므로, 스레드로
        # 안 빼면 그동안 다른 owner 요청까지 같이 멈춘다.
        titles = await asyncio.to_thread(writer.write, project_id=project_id, script_text=script_text)
        await client.submit_title_candidates(
            project_id=project_id,
            cycle_id=cycle_id,
            title_candidates=[
                {"index": index, "text": title}
                for index, title in enumerate(titles)
            ],
            question="어느 제목이 좋을까요?",
            target=_APPROVAL_TARGET,
        )
    except Exception:  # noqa: BLE001 - 결재함 알림은 최선노력이다
        _LOGGER.warning(
            "AK-System Hermes 결재함 큐에 제목 후보 항목을 넣지 못했습니다.",
            exc_info=True,
        )


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
    def approve(
        project_id: str, brief_id: str, payload: CreationBriefRevisionRequest,
        request: Request, background_tasks: BackgroundTasks,
    ) -> dict[str, object]:
        try:
            brief = store.approve_creation_brief(project_id=project_id, brief_id=brief_id, expected_revision=payload.expected_revision)
        except Exception as exc:
            raise _http_error(exc) from exc
        background_tasks.add_task(_notify_script_confirmation_queue, request.app, project_id=project_id, brief=brief)
        return brief

    @router.delete("/api/projects/{project_id}/creation-briefs/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(project_id: str, brief_id: str) -> Response:
        try:
            store.delete_creation_brief(project_id=project_id, brief_id=brief_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
