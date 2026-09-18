"""유진의 승인된 기억 -- 저장·조회·삭제를 전부 로컬에서 처리한다.

**2026-09-18에 Mem0(외부 provider)를 걷어내고 이 파일로 바꿨다.** 이전에는
`store_candidate`/`retrieve_approved_memories`/`delete_candidate_memory`가
`agent-gateway`를 거쳐 `hermes-memory-adapter` 컨테이너의 Mem0로 나갔다.
owner가 실측한 사용량(2026-09-18, Postgres 직접 조회) -- 5주 넘게 서로 다른
기억 **3개**만 승인됐고, 그중 하나는 저장 전 중복 확인이 없어 **9번** 중복
저장됐다(`docs/mem0-memory-backup-2026-09-10.ko.md`) -- 이 Mem0 경로가
"쓰지도 않고 정리도 안 된다"는 owner 판단을 뒷받침한다. 설계 근거는
`docs/decisions/2026-09-18-mem0-removed-native-memory-librarian.ko.md`.

**승인 큐 자체는 그대로다.** `yujin_memory_candidates`의 승인 상태 기계
(`_store_yujin_memory.py`의 claim → 결과 기록 → finalize)는 원래 "믿을 수
없는 외부 provider에 멱등하게 쓴다"는 목적으로 만들어졌지만, 그 상태 이름
(`event_pending`/`ambiguous`/`retryable`)이 Mem0 전용이 아니라 일반적인
"멱등 쓰기" 개념이라 그대로 재사용한다 -- 로컬 DB 쓰기는 성공 아니면 예외뿐이라
실제로는 `stored`로만 끝나지만, 스키마·감사 로그·CLAUDE.md §6이 요구하는
"owner가 승인한 것만 저장된다"는 계약은 한 글자도 안 바뀐다.

**저장 = 기존 값 그대로 두고 memory_ref만 로컬로 계산한다.** 같은 문장이
이미 저장돼 있으면(project_id+category+proposed_text 완전 일치) 그
memory_ref를 재사용한다(mem0의 9번 중복 결함을 로컬로 고정 방지) --
`_store_yujin_memory.find_stored_yujin_memory_ref`.

**조회 = Mem0의 뜻 기반 검색 대신 로컬 순위 매기기.** 외부 검색이 없으니
CLAUDE.md §6의 "게이트웨이가 돌려준 것 중 로컬과 정확히 일치하는 것만
채택한다"는 대조는 더 이상 실행 가능한 코드 경로가 없다 -- 반환값이
`self._store`가 준 행에서만 나오므로 그 원칙이 **구조적으로** 지켜진다.
그 취지를 지키는 시험은 `tests/test_yujin_memory_retrieval.py`에 남긴다.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from videobox_domain_models.yujin_creator_context import (
    UserApprovedPreference,
)
from videobox_core_engine.yujin_memory_policy import (
    is_yujin_memory_retrieval_query_safe,
)

_RETRIEVAL_LIMIT = 5
_RETRIEVAL_TEXT_BUDGET = 1400
_MEMORY_CREATE_ACTION = "기억 후보 만들기"

#: 승인 큐가 실제로 만드는 카테고리 5종(`yujin_memory_policy.py`와 같은 집합).
#: 로컬 행의 category가 이 밖의 값이면 스키마가 어긋난 것이라 읽지 못한
#: 줄로 취급한다 -- 조용히 통과시키면 화면에 처음 보는 분류가 나온다.
_ALLOWED_CATEGORIES = frozenset({"pacing", "caption", "audio", "tone", "workflow"})

# 카테고리별로 이 낱말이 질의에 있으면 그 카테고리 기억을 더 위로 올린다.
# 유진의 기억 후보는 5개 고정 카테고리뿐이라 이 정도 낱말 대조로 충분하다 --
# 임베딩·LLM 호출은 매 채팅 턴마다 도는 hot path라 넣지 않는다
# (`docs/development-fast-path.ko.md` §10.6).
_CATEGORY_QUERY_HINTS: dict[str, tuple[str, ...]] = {
    "pacing": ("컷", "템포", "편집속도", "전환", "박자", "pacing"),
    "caption": ("자막", "글자", "폰트", "줄바꿈", "caption"),
    "audio": ("음악", "소리", "효과음", "볼륨", "음량", "배경음", "audio"),
    "tone": ("분위기", "톤", "느낌", "무드", "tone"),
    "workflow": ("작업", "순서", "방식", "루틴", "workflow"),
}


class MemoryStoreUnavailable(RuntimeError):
    pass


class YujinMemoryService:
    def __init__(self, *, store) -> None:
        self._store = store

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
        try:
            rows = self._store.list_yujin_memory_retrieval_rows(
                project_id=project_id,
                conversation_id=conversation_id,
            )
        except Exception:
            # 로컬 DB 읽기 실패다 -- 외부 provider가 없으니 폴백할 다른
            # 원본이 없다. 조용히 비우는 대신 로그를 남기고 빈 결과를 준다.
            _LOGGER.warning(
                "유진 기억 조회가 실패했습니다 (project=%s, conversation=%s).",
                project_id,
                conversation_id,
                exc_info=True,
            )
            return ()
        local = self._eligible_local_memories(
            rows, project_id=project_id, conversation_id=conversation_id
        )
        if not local:
            return ()
        ranked = sorted(
            local,
            key=lambda item: (
                -self._relevance_score(
                    category=item[0], text=item[1], query=bounded_query
                ),
                item[0],
                item[1],
            ),
        )
        return self._cap_preferences(
            UserApprovedPreference(
                kind="user_approved_preference", category=category, text=text
            )
            for category, text in ranked
        )

    @staticmethod
    def _relevance_score(*, category: str, text: str, query: str) -> int:
        score = 0
        for hint in _CATEGORY_QUERY_HINTS.get(category, ()):
            if hint in query:
                score += 2
        haystack = f"{category} {text}"
        for token in query.replace(",", " ").split():
            token = token.strip("?!.~()[]{}\"'")
            if len(token) >= 2 and token in haystack:
                score += 1
        return score

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
    def _eligible_local_memories(
        rows,
        *,
        project_id: str,
        conversation_id: str,
    ) -> set[tuple[str, str]]:
        """(category, text) 중 이 프로젝트가 승인·저장까지 마친 것만.

        `list_yujin_memory_retrieval_rows`가 이미 project_id로 걸러서
        돌려준다 -- 여기서는 승인·저장 상태만 다시 확인한다(대조 원칙,
        CLAUDE.md §6). 반환값이 `rows`에 없던 것을 절대 만들어내지 않는다는
        것이 이 함수의 전체 계약이다 -- 로컬이 유일한 원본이므로.
        """
        eligible: set[tuple[str, str]] = set()
        unreadable: list[str] = []
        first_error: Exception | None = None
        for row in rows if isinstance(rows, (list, tuple)) else ():
            if not isinstance(row, dict):
                continue
            if (
                row.get("project_id") != project_id
                or row.get("status") != "approved"
                or row.get("storage_status") != "stored"
            ):
                continue
            try:
                category = str(row["category"])
                text = str(row["text"])
                if not text or category not in _ALLOWED_CATEGORIES:
                    raise ValueError("memory_row_schema_drifted")
            except Exception as exc:  # noqa: BLE001 - 한 줄이 나머지를 막지 않는다
                unreadable.append(str(row.get("memory_ref") or "(이름 없음)"))
                if first_error is None:
                    first_error = exc
                continue
            eligible.add((category, text))
        if unreadable:
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

        # `claim["action"]`이 "add"든 "reconcile"이든 이제는 같다 -- 외부
        # provider가 없으니 "다시 맞춰 본다"는 개념 자체가 없다. 로컬 쓰기는
        # 성공 아니면 예외뿐이다.
        try:
            self._store.mark_yujin_memory_store_call_started(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
            )
            memory_ref = self._store.find_stored_yujin_memory_ref(
                project_id=project_id,
                category=claim["category"],
                proposed_text=claim["text"],
            )
            if memory_ref is None:
                memory_ref = "local-" + hashlib.sha256(
                    claim["external_ref"].encode("utf-8")
                ).hexdigest()
            self._store.record_yujin_memory_provider_outcome(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                status="stored",
                memory_ref=memory_ref,
                event_ref=None,
            )
        except Exception as error:
            self._store.release_yujin_memory_store_claim(
                project_id=project_id,
                candidate_id=candidate_id,
                claim_token=claim_token,
                storage_status="ambiguous",
                event_ref=None,
            )
            raise MemoryStoreUnavailable(
                "memory_store_unavailable"
            ) from error

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
        try:
            self._store.mark_yujin_memory_delete_call_started(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        except (KeyError, ValueError):
            raise
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
    "MemoryStoreUnavailable",
    "YujinMemoryService",
]
