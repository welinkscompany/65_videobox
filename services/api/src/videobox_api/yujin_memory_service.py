"""Explicit-store coordinator for approved Yujin memory candidates."""

from __future__ import annotations

import logging

import asyncio
import hashlib
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from videobox_domain_models.yujin_creator_context import (
    UserApprovedPreference,
)
from videobox_core_engine.yujin_memory_policy import (
    is_yujin_memory_retrieval_query_safe,
)


_RETRIEVAL_TIMEOUT_SECONDS = 0.75
_RETRIEVAL_LIMIT = 5
_RETRIEVAL_TEXT_BUDGET = 1400
_MEMORY_CREATE_ACTION = "기억 후보 만들기"


class MemoryStoreUnavailable(RuntimeError):
    pass


class ApprovedMemoryStoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1, max_length=280)
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    operation_id: str = Field(pattern=r"^op-[0-9a-f]{64}$")


class MemoryReconcileRequest(ApprovedMemoryStoreRequest):
    event_ref: str | None = Field(default=None, min_length=1, max_length=256)


class GatewayMemoryWriteOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "stored", "event_pending", "failed_retryable", "ambiguous"
    ]
    memory_ref: str | None = None
    event_ref: str | None = None


class GatewayMemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    query: str = Field(min_length=1, max_length=280)
    limit: int = Field(ge=1, le=5, strict=True)


class GatewayRetrievedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=280)
    category: Literal["pacing", "caption", "audio", "tone", "workflow"]
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")


class GatewayMemorySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memories: tuple[GatewayRetrievedMemory, ...] = Field(max_length=5)


class GatewayMemoryDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    memory_ref: str = Field(min_length=1, max_length=256)
    external_ref: str = Field(pattern=r"^ext-[0-9a-f]{64}$")
    allow_absent: bool


class GatewayMemoryDeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    deleted: Literal[True]


class YujinMemoryService:
    def __init__(self, *, store, gateway) -> None:
        self._store = store
        self._gateway = gateway

    def _public(self, *, project_id: str, candidate_id: str) -> dict:
        return self._store.get_yujin_memory_store_state(
            project_id=project_id,
            candidate_id=candidate_id,
        )

    async def retrieve_for_new_owned_dispatch(
        self,
        *,
        dispatch: bool,
        owner_token: str | None,
        project_id: str,
        conversation_id: str,
        query: str,
    ) -> tuple[UserApprovedPreference, ...]:
        if (
            not dispatch
            or not owner_token
            or query.strip() == _MEMORY_CREATE_ACTION
        ):
            return ()
        return await self.retrieve_approved_memories(
            project_id=project_id,
            conversation_id=conversation_id,
            query=query,
        )

    async def retrieve_approved_memories(
        self,
        *,
        project_id: str,
        conversation_id: str,
        query: str,
    ) -> tuple[UserApprovedPreference, ...]:
        if not is_yujin_memory_retrieval_query_safe(query):
            return ()
        bounded_query = query.strip()[:280]
        if not bounded_query:
            return ()
        rows: list[dict] = []
        result: GatewayMemorySearchResult | None = None
        try:
            # 이 안에서 실패하는 모든 것(DB 읽기든 게이트웨이 호출이든)은
            # 같은 하나의 예산 안에서 끝나야 한다 -- 둘로 쪼개면 최악의 경우
            # 지연이 두 배가 된다.
            async with asyncio.timeout(_RETRIEVAL_TIMEOUT_SECONDS):
                rows = await asyncio.to_thread(
                    self._store.list_yujin_memory_retrieval_rows,
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
                local = self._eligible_local_memories(
                    rows,
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
                if not local:
                    return ()
                # 게이트웨이가 아예 없으면(설정 안 됨) 순위를 매길 검색 자체가
                # 없다. 예전엔 여기서 빈 결과를 돌려줘 owner가 기억을 승인해
                # 뒀어도 유진이 처음 만난 사람처럼 대화했다 -- 로컬 원본은 늘
                # 그대로 있으니, 뜻으로 고르지 못할 뿐 **아예 안 꺼내는 것보다는
                # 낫다**는 owner 판단(2026-08-31)으로 이 폴백을 넣는다. 순위는
                # 저장 순서(`list_yujin_memory_retrieval_rows`가 이미 정렬해
                # 준 순서)를 그대로 쓴다 -- 뜻 기반 순위가 아니라는 것을 스스로
                # 부풀리지 않는다.
                if self._gateway is not None:
                    raw = await self._gateway.search_memory(
                        GatewayMemorySearchRequest(
                            query=bounded_query,
                            limit=_RETRIEVAL_LIMIT,
                        )
                    )
                    payload = (
                        raw.model_dump(mode="python")
                        if hasattr(raw, "model_dump")
                        else raw
                    )
                    if (
                        isinstance(payload, dict)
                        and isinstance(payload.get("memories"), list)
                    ):
                        payload = {
                            **payload,
                            "memories": tuple(payload["memories"]),
                        }
                    result = GatewayMemorySearchResult.model_validate(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 조회 실패와 "기억이 원래 없음"이 화면에서 똑같이 보인다. 로컬
            # 원본은 있으니(위에서 `local`이 비었으면 이미 돌아갔다) 저장
            # 순서 폴백으로 내려간다 -- 위 주석과 같은 이유.
            _LOGGER.warning(
                "유진 기억 조회가 실패해 저장 순서 폴백으로 돌려줍니다 (project=%s, conversation=%s).",
                project_id,
                conversation_id,
                exc_info=True,
            )
            return self._cap_preferences(self._local_fallback_order(rows))

        if result is None:
            return self._cap_preferences(self._local_fallback_order(rows))

        matched: dict[tuple[str, str], UserApprovedPreference] = {}
        for item in result.memories:
            exact = (
                item.memory_ref,
                item.external_ref,
                item.text,
                item.category,
            )
            if exact not in local:
                continue
            public_key = (item.category, item.text)
            matched[public_key] = UserApprovedPreference(
                kind="user_approved_preference",
                category=item.category,
                text=item.text,
            )
        return self._cap_preferences(
            matched[key] for key in sorted(matched)
        )

    @staticmethod
    def _cap_preferences(
        preferences,
    ) -> tuple[UserApprovedPreference, ...]:
        output: list[UserApprovedPreference] = []
        total = 0
        for item in preferences:
            if len(output) >= _RETRIEVAL_LIMIT:
                break
            next_total = total + len(item.text)
            if next_total > _RETRIEVAL_TEXT_BUDGET:
                continue
            output.append(item)
            total = next_total
        return tuple(output)

    @staticmethod
    def _local_fallback_order(rows):
        """뜻 기반 순위가 없을 때 쓸 순서.

        `list_yujin_memory_retrieval_rows`가 이미 project_id로 걸러서(SQL의
        `WHERE project_id = ?`) `category, proposed_text, candidate_id` 순으로
        정렬해 돌려준다 -- 새 검색을 또 만들지 않고 그 순서를 그대로 쓴다.
        승인·저장 상태 확인은 `_eligible_local_memories`와 같은 기준이다(한쪽만
        확인이 아니라 저장 폴백에서도 owner가 승인한 것만 나가야 한다).
        """
        for row in rows if isinstance(rows, (list, tuple)) else ():
            if not isinstance(row, dict):
                continue
            if row.get("status") != "approved" or row.get("storage_status") != "stored":
                continue
            try:
                text = str(row["text"])
                category = row["category"]
            except (KeyError, TypeError):
                continue
            yield UserApprovedPreference(
                kind="user_approved_preference",
                category=category,
                text=text,
            )

    @staticmethod
    def _eligible_local_memories(
        rows,
        *,
        project_id: str,
        conversation_id: str,
    ) -> set[tuple[str, str, str, str]]:
        eligible: set[tuple[str, str, str, str]] = set()
        # 읽지 못한 줄은 조회가 성공한 뒤에 빠지므로 위의 조회 실패 기록이
        # 이 경우를 볼 수 없다. 스키마가 한 칸만 어긋나도 기억이 전부 사라지고
        # 화면에는 "기억이 원래 없음"과 똑같이 보인다.
        unreadable: list[str] = []
        first_error: Exception | None = None
        for row in rows if isinstance(rows, (list, tuple)) else ():
            if not isinstance(row, dict):
                continue
            # 소속·승인 확인을 먼저 한다. 걸러 낼 줄까지 "읽지 못했다"고
            # 세면 기록이 시끄러워진다. 두 조건을 모두 통과해야 채택되는
            # 것은 그대로다.
            # 대화는 가리지 않는다 -- 기억은 대화보다 오래 산다. 프로젝트와
            # 승인·저장 상태는 그대로 본다: 이 대조가 게이트웨이가 돌려준 항목
            # 중 owner가 실제로 승인한 것만 채택하게 만드는 문이다(CLAUDE.md §6).
            if (
                row.get("project_id") != project_id
                or row.get("status") != "approved"
                or row.get("storage_status") != "stored"
            ):
                continue
            try:
                parsed = GatewayRetrievedMemory(
                    memory_ref=row["memory_ref"],
                    external_ref=row["external_ref"],
                    text=row["text"],
                    category=row["category"],
                )
            except Exception as exc:  # noqa: BLE001 - 한 줄이 나머지를 막지 않는다
                unreadable.append(str(row.get("memory_ref") or "(이름 없음)"))
                if first_error is None:
                    first_error = exc
                continue
            eligible.add(
                (
                    parsed.memory_ref,
                    parsed.external_ref,
                    parsed.text,
                    parsed.category,
                )
            )
        if unreadable:
            # 대화마다 지나는 길이라 줄마다 찍지 않고 한 번에 모아 남긴다.
            _LOGGER.warning(
                "승인된 기억 %d개를 읽지 못해 후보에서 뺐습니다 "
                "(project=%s, conversation=%s, 기억=%s).",
                len(unreadable),
                project_id,
                conversation_id,
                ", ".join(unreadable[:10]),
                exc_info=first_error,
            )
        return eligible

    async def store_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        client_request_id: str,
    ) -> dict:
        current = self._public(
            project_id=project_id, candidate_id=candidate_id
        )
        if current["status"] != "approved":
            raise ValueError("memory_candidate_not_approved")
        if current["storage_status"] == "stored":
            return current
        if current["storage_status"] == "deleted":
            raise ValueError("memory_candidate_deleted")
        # 켜져 있지 않은 것과 부르다 실패한 것은 owner가 할 일이 다르다.
        # 하나는 켜는 일이고 하나는 다시 눌러 보는 일이다 -- 이름을 나눈다.
        if self._gateway is None:
            raise MemoryStoreUnavailable("memory_not_configured")
        claim_token = "claim-" + hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        claim = self._store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id=client_request_id,
            claim_token=claim_token,
        )
        if claim["action"] in {"stored", "replay"}:
            return self._public(
                project_id=project_id, candidate_id=candidate_id
            )
        if claim["action"] == "finalize":
            self._store.finalize_yujin_memory_store(
                project_id=project_id,
                candidate_id=candidate_id,
            )
            return self._public(
                project_id=project_id, candidate_id=candidate_id
            )

        request_data = {
            "text": claim["text"],
            "category": claim["category"],
            "external_ref": claim["external_ref"],
            "operation_id": claim["operation_id"],
        }
        parsed = None
        try:
            self._store.mark_yujin_memory_store_call_started(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
            )
            if claim["action"] == "reconcile":
                outcome = await self._gateway.reconcile_memory(
                    MemoryReconcileRequest(
                        **request_data,
                        event_ref=claim["event_ref"],
                    )
                )
            else:
                outcome = await self._gateway.add_approved_memory(
                    ApprovedMemoryStoreRequest(**request_data)
                )
            parsed = GatewayMemoryWriteOutcome.model_validate(
                outcome.model_dump()
                if hasattr(outcome, "model_dump")
                else outcome
            )
            self._store.record_yujin_memory_provider_outcome(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                status=parsed.status,
                memory_ref=parsed.memory_ref,
                event_ref=parsed.event_ref,
            )
        except Exception as error:
            self._store.release_yujin_memory_store_claim(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                storage_status="ambiguous",
                event_ref=(
                    parsed.event_ref if parsed is not None else None
                ),
            )
            raise MemoryStoreUnavailable(
                "memory_store_unavailable"
            ) from error

        if parsed.status == "stored":
            self._store.finalize_yujin_memory_store(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        return self._public(
            project_id=project_id, candidate_id=candidate_id
        )

    async def delete_candidate_memory(
        self, *, project_id: str, candidate_id: str
    ) -> dict:
        current = self._public(
            project_id=project_id, candidate_id=candidate_id
        )
        if current["storage_status"] == "deleted":
            return current
        mapping = self._store.get_yujin_memory_private_mapping(
            project_id=project_id,
            candidate_id=candidate_id,
        )
        # 위와 같은 이유로 같은 이름을 쓴다.
        if self._gateway is None:
            raise MemoryStoreUnavailable("memory_not_configured")
        try:
            delete_state = (
                self._store.mark_yujin_memory_delete_call_started(
                    project_id=project_id,
                    candidate_id=candidate_id,
                )
            )
        except (KeyError, ValueError):
            raise
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error
        try:
            result = await self._gateway.delete_memory(
                GatewayMemoryDeleteRequest(
                    memory_ref=delete_state["memory_ref"],
                    external_ref=delete_state["external_ref"],
                    allow_absent=delete_state["allow_absent"],
                )
            )
            GatewayMemoryDeleteResult.model_validate(
                result.model_dump()
                if hasattr(result, "model_dump")
                else result
            )
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error
        try:
            return self._store.mark_yujin_memory_deleted(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        except Exception as error:
            raise MemoryStoreUnavailable(
                "memory_delete_unavailable"
            ) from error


_LOGGER = logging.getLogger(__name__)

__all__ = [
    "ApprovedMemoryStoreRequest",
    "GatewayMemoryWriteOutcome",
    "GatewayMemoryDeleteRequest",
    "GatewayMemoryDeleteResult",
    "GatewayMemorySearchRequest",
    "GatewayMemorySearchResult",
    "GatewayRetrievedMemory",
    "MemoryReconcileRequest",
    "MemoryStoreUnavailable",
    "YujinMemoryService",
]
