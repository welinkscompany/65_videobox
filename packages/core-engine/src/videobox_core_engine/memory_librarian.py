"""기억 사서 -- 대화 하나를 훑어 owner가 승인할 만한 기억 후보를 만든다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md`에서 이어지는
작업. **owner 승인 큐(`create_yujin_memory_candidate`)를 그대로 거친다** --
사서가 mem0에 직접 쓰지 않는다. CLAUDE.md §6("승인 저장한 기억 문구만
mem0로 나간다")을 우회하는 새 경로를 만들지 않기 위해서다.

**대화 하나 단위로 돈다.** `create_yujin_memory_candidate`가 `source_message_ids`를
같은 대화 안에서만 검증하기 때문이다 -- 여러 대화를 가로질러 한 후보를
만들 수 없다(스키마 제약, 바꾸지 않는다).

**도구 호출이 없다.** `runtime.generate_structured`는 순수 구조화 응답
한 번이고, 이 함수는 어떤 MCP·에이전트 루프도 태우지 않는다 -- 참고 구현
(Rumi Wiki Librarian)이 04:00 배치 작업에 도구 있는 에이전트를 썼다가
전체 예산의 절반을 "무엇을 쓸지 고르는 데" 날린 실패를 그대로 피한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from videobox_core_engine.memory_librarian_boilerplate import (
    TimestampedParagraph,
    strip_boilerplate,
)
from videobox_provider_interfaces.llm import LLMTaskType

MAX_USER_PARAGRAPH_CHARS = 800

_DISTILL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["category", "text"],
            },
        }
    },
    "required": ["facts"],
}

_ALLOWED_CATEGORIES = frozenset({"pacing", "caption", "audio", "tone", "workflow"})

_DISTILL_INSTRUCTION = (
    "다음은 창작자가 VideoBox 편집기에서 나눈 대화 중 창작자 본인이 한 말이다. "
    "이 안에서 앞으로도 계속 적용할 만한 **편집 취향**(예: 컷 템포, 자막 스타일, "
    "음악·효과음 크기, 영상 분위기, 작업 방식)을 찾아라. 그 순간에만 해당하는 "
    "일회성 지시(예: '이번 장면만 늘려줘')는 취향이 아니다. 찾은 각 취향을 "
    "{category, text} 형태로 낸다 -- category는 pacing·caption·audio·tone·workflow "
    "중 하나. 찾은 게 없으면 빈 목록을 낸다. 지어내지 않는다."
)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class _StructuredGenerator(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> Any: ...


class DistillationStore(Protocol):
    def get_memory_librarian_watermark(
        self, *, project_id: str, conversation_id: str
    ) -> dict[str, Any] | None: ...

    def list_director_messages_after(
        self, *, project_id: str, conversation_id: str, after_message_order: int
    ) -> list[dict[str, Any]]: ...

    def create_yujin_memory_candidate(
        self,
        *,
        project_id: str,
        conversation_id: str,
        client_request_id: str,
        source_message_ids: tuple[str, ...],
        memory_scope: str,
        category: str,
        proposed_text: str,
    ) -> dict[str, Any]: ...

    def record_memory_librarian_run(
        self,
        *,
        project_id: str,
        conversation_id: str,
        last_message_order: int,
        status: str,
        candidates_created: int,
    ) -> dict[str, Any]: ...


def distill_conversation_memories(
    store: DistillationStore,
    *,
    project_id: str,
    conversation_id: str,
    runtime: _StructuredGenerator,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """대화 하나를 증류한다. 모든 종료 경로에서 워터마크를 남기고 돌아온다."""
    as_of = as_of or datetime.now(timezone.utc)
    watermark = store.get_memory_librarian_watermark(
        project_id=project_id, conversation_id=conversation_id
    )
    previous_order = int(watermark["last_message_order"]) if watermark is not None else 0

    all_messages = store.list_director_messages_after(
        project_id=project_id, conversation_id=conversation_id, after_message_order=0
    )
    new_messages = [m for m in all_messages if int(m["message_order"]) > previous_order]

    if not new_messages:
        store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=previous_order, status="nothing_new", candidates_created=0,
        )
        return {"status": "nothing_new", "candidates_created": 0}

    latest_order = max(int(m["message_order"]) for m in new_messages)

    # 정형구 판정은 90일 창 전체를 봐야 한다(새로 온 것만 보면 반복 횟수를
    # 못 다 센다) -- 걸러내는 대상은 새 사용자 발화뿐이다.
    all_paragraphs = [
        TimestampedParagraph(text=str(m["text"]), occurred_at=_parse_iso(str(m["created_at"])))
        for m in all_messages
    ]
    kept = strip_boilerplate(
        all_paragraphs, as_of=as_of, max_user_paragraph_chars=MAX_USER_PARAGRAPH_CHARS
    )
    kept_texts = {p.text.strip() for p in kept}
    new_user_messages = [
        m for m in new_messages
        if m["role"] == "user" and str(m["text"]).strip() in kept_texts
    ]

    if not new_user_messages:
        store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=latest_order, status="nothing_new", candidates_created=0,
        )
        return {"status": "nothing_new", "candidates_created": 0}

    try:
        transcript = "\n".join(f"- {m['text']}" for m in new_user_messages)
        response = runtime.generate_structured(
            project_id=project_id,
            task_type=LLMTaskType.MEMORY_LIBRARIAN_DISTILL,
            prompt=f"{_DISTILL_INSTRUCTION}\n\n{transcript}",
            response_schema=_DISTILL_RESPONSE_SCHEMA,
        )
        facts = response.output_data.get("facts") or []
        source_message_ids = tuple(str(m["message_id"]) for m in new_user_messages)
        created = 0
        for index, fact in enumerate(facts):
            category = str(fact.get("category") or "")
            text = str(fact.get("text") or "").strip()
            if category not in _ALLOWED_CATEGORIES or not text:
                continue
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"librarian-{conversation_id}-{latest_order}-{index}",
                source_message_ids=source_message_ids,
                memory_scope="creator",
                category=category,
                proposed_text=text,
            )
            created += 1
    except Exception:
        # 실패한 실행은 워터마크를 안 밀어 준다 -- 다음 실행이 같은 메시지를
        # 다시 시도할 수 있게. 예외 원문은 이 함수 밖(호출부 로그)이 다룬다.
        store.record_memory_librarian_run(
            project_id=project_id, conversation_id=conversation_id,
            last_message_order=previous_order, status="failed", candidates_created=0,
        )
        raise

    store.record_memory_librarian_run(
        project_id=project_id, conversation_id=conversation_id,
        last_message_order=latest_order, status="succeeded", candidates_created=created,
    )
    return {"status": "succeeded", "candidates_created": created}
