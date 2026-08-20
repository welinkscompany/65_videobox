"""Local-only approval workflow for Yujin memory candidates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from videobox_api.models import (
    YujinMemoryCandidateCreateRequest,
    YujinMemoryCandidateListResponse,
    YujinMemoryCandidateResponse,
    YujinMemoryStoreRequest,
    YujinMemoryStoreResponse,
)
from videobox_core_engine.yujin_memory_policy import (
    validate_yujin_memory_candidate,
)
from videobox_api.yujin_memory_service import MemoryStoreUnavailable

_PUBLIC_POLICY_ERRORS = frozenset(
    {
        "memory_candidate_category_unsupported",
        "memory_candidate_text_empty",
        "memory_candidate_text_too_long",
        "memory_candidate_text_too_many_bytes",
        "memory_candidate_text_multiline",
        "memory_candidate_control_character_forbidden",
        "memory_candidate_raw_transcript_forbidden",
        "memory_candidate_sensitive_text_forbidden",
        "memory_candidate_full_source_message_forbidden",
    }
)


def build_yujin_memory_router(store, memory_service=None) -> APIRouter:
    router = APIRouter()
    base = "/api/projects/{project_id}/director/memory-candidates"

    @router.post(
        base,
        response_model=YujinMemoryCandidateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_candidate(
        project_id: str,
        body: YujinMemoryCandidateCreateRequest,
    ) -> dict:
        try:
            source_texts = store.get_yujin_memory_source_texts(
                project_id=project_id,
                conversation_id=body.conversation_id,
                source_message_ids=body.source_message_ids,
            )
            proposed_text = validate_yujin_memory_candidate(
                category=body.category,
                proposed_text=body.proposed_text,
                source_texts=source_texts,
            )
            return store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=body.conversation_id,
                client_request_id=body.client_request_id,
                source_message_ids=body.source_message_ids,
                memory_scope=body.memory_scope,
                category=body.category,
                proposed_text=proposed_text,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail="memory_candidate_source_missing",
            ) from error
        except ValueError as error:
            detail = str(error)
            if detail == "memory_candidate_request_conflict":
                raise HTTPException(status_code=409, detail=detail) from error
            if detail in _PUBLIC_POLICY_ERRORS:
                raise HTTPException(status_code=422, detail=detail) from error
            raise HTTPException(
                status_code=503,
                detail="memory_candidate_unavailable",
            ) from error

    @router.get(
        base,
        response_model=YujinMemoryCandidateListResponse,
    )
    def list_candidates(
        project_id: str,
        conversation_id: Annotated[
            str,
            Query(
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                strict=True,
            ),
        ],
    ) -> dict:
        try:
            return {
                "candidates": store.list_yujin_memory_candidates(
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
            }
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail="memory_candidate_conversation_missing",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="memory_candidate_unavailable",
            ) from error

    def transition(
        *,
        project_id: str,
        candidate_id: str,
        action: str,
    ) -> dict:
        try:
            return store.transition_yujin_memory_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                action=action,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail="memory_candidate_missing",
            ) from error
        except ValueError as error:
            detail = str(error)
            if detail == "memory_candidate_terminal_conflict":
                raise HTTPException(status_code=409, detail=detail) from error
            raise HTTPException(
                status_code=503,
                detail="memory_candidate_unavailable",
            ) from error

    @router.post(
        base + "/{candidate_id}/approve",
        response_model=YujinMemoryCandidateResponse,
    )
    def approve_candidate(project_id: str, candidate_id: str) -> dict:
        return transition(
            project_id=project_id,
            candidate_id=candidate_id,
            action="approve",
        )

    @router.post(
        base + "/{candidate_id}/reject",
        response_model=YujinMemoryCandidateResponse,
    )
    def reject_candidate(project_id: str, candidate_id: str) -> dict:
        return transition(
            project_id=project_id,
            candidate_id=candidate_id,
            action="reject",
        )

    @router.post(
        base + "/{candidate_id}/store",
        response_model=YujinMemoryStoreResponse,
    )
    async def store_candidate(
        project_id: str,
        candidate_id: str,
        body: YujinMemoryStoreRequest,
    ) -> dict:
        if memory_service is None:
            raise HTTPException(
                status_code=503, detail="memory_save_unavailable"
            )
        try:
            return await memory_service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id=body.client_request_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="memory_candidate_missing"
            ) from error
        except ValueError as error:
            detail = str(error)
            if detail in {
                "memory_candidate_deleted",
                "memory_candidate_not_approved",
                "memory_candidate_store_in_progress",
            }:
                raise HTTPException(status_code=409, detail=detail) from error
            raise HTTPException(
                status_code=503, detail="memory_save_unavailable"
            ) from error
        except MemoryStoreUnavailable as error:
            # 꺼져 있는 것은 실패가 아니다. 화면이 `켜 주세요`와 `다시 눌러
            # 주세요`를 갈라 말할 수 있도록 이름을 그대로 흘려보낸다.
            raise HTTPException(
                status_code=503,
                detail="memory_not_configured" if str(error) == "memory_not_configured" else "memory_save_unavailable",
            ) from error

    @router.delete(
        base + "/{candidate_id}/stored-memory",
        response_model=YujinMemoryStoreResponse,
    )
    async def delete_stored_memory(
        project_id: str, candidate_id: str
    ) -> dict:
        if memory_service is None:
            raise HTTPException(
                status_code=503, detail="memory_delete_unavailable"
            )
        try:
            return await memory_service.delete_candidate_memory(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="memory_candidate_missing"
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=409, detail="memory_candidate_not_stored"
            ) from error
        except MemoryStoreUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="memory_not_configured" if str(error) == "memory_not_configured" else "memory_delete_unavailable",
            ) from error

    return router


__all__ = ["build_yujin_memory_router"]
