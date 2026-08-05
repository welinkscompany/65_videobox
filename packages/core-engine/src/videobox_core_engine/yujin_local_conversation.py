"""Local-first Yujin conversation reply path.

Owner decision (2026-08-05): docs/decisions/2026-08-05-local-first-assistant-decision.ko.md.
Yujin's primary conversation route runs on the local model instead of waiting
for the (undeployed) Hermes agent gateway. This module deliberately stays
outside that gateway's capability-token protocol: it grants no publish/tool
capability, so its output cannot mutate the project by itself. Editing
mutation still goes through the existing human-approval UI; a chat "네" is
never treated as approval. Script/title/thumbnail/recommended-video
generation stay out of scope (see docs/implementation-plan.ko.md §23.3B) --
those requests are rejected before the model is ever called, since that
boundary must not depend on the model choosing to comply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from videobox_provider_interfaces.llm import LLMTaskType, StructuredLLMResponse

YUJIN_CONVERSATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}

_YUJIN_SYSTEM_PROMPT = (
    "너는 VideoBox의 창작 도우미 유진이다. 항상 한국어로, 영상을 만드는 창작자에게 "
    "말하듯 답한다. 다음은 절대 하지 않는다: 데이터베이스나 파일시스템 조작, 셸 명령 실행, "
    "자격증명·API key 요청 또는 노출, CapCut이나 렌더러를 직접 조작, 대본·제목·썸네일· "
    "추천 영상 자체를 생성. 편집이 실제로 반영되려면 사람이 화면에서 직접 승인해야 하며, "
    "대화 중 '네'라는 대답은 승인이 아니다. 응답은 JSON 객체 {\"reply\": \"...\"} 형태로만 낸다."
)

# Deterministic pre-check: the boundary a chat assistant must not cross can't
# depend on the model choosing to comply, so restricted intents are rejected
# before any model call is made.
_BLOCKED_INTENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(delete|drop|truncate)\s+(table|database|from)",
        r"(데이터베이스|database|테이블|table).{0,10}(삭제|지워|drop|truncate)",
        r"sql",
        r"(쉘|셸|shell|bash|powershell|cmd)\s*(명령|실행|command)",
        r"(파일|디렉터리|폴더).{0,4}(삭제|지워)",
        r"(api\s*key|credential|비밀번호|자격\s*증명|access\s*token)",
        r"capcut.{0,6}(직접|바로).{0,6}(실행|조작|열어)",
        r"(대본|스크립트).{0,6}(써|작성|만들어)\s*줘",
        r"제목.{0,6}(만들어|지어)\s*줘",
        r"썸네일.{0,6}(만들어|생성)",
        r"추천\s*영상.{0,6}(만들어|생성)",
    )
)


def detect_blocked_intent(user_text: str) -> str | None:
    """Return the matched pattern source if `user_text` requests a restricted
    action, otherwise None. Exposed separately so callers can log/test the
    guard without going through the full reply path."""
    for pattern in _BLOCKED_INTENT_PATTERNS:
        if pattern.search(user_text):
            return pattern.pattern
    return None


@dataclass(slots=True, frozen=True)
class YujinLocalConversationResult:
    status: str  # "ok" | "blocked"
    reply: str
    blocked_reason: str | None = None


class _StructuredGenerator(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict,
    ) -> StructuredLLMResponse: ...


@dataclass(slots=True)
class YujinLocalConversationService:
    runtime: _StructuredGenerator

    def reply(self, *, project_id: str, user_text: str) -> YujinLocalConversationResult:
        if not user_text.strip():
            raise ValueError("user_text must not be blank")

        blocked_pattern = detect_blocked_intent(user_text)
        if blocked_pattern is not None:
            return YujinLocalConversationResult(
                status="blocked",
                reply=(
                    "이 요청은 유진이 직접 할 수 없어요. 데이터·파일·자격정보 조작이나 "
                    "대본·제목·썸네일·추천 영상 생성은 유진의 대화 범위 밖이에요."
                ),
                blocked_reason="policy_restricted_intent",
            )

        response = self.runtime.generate_structured(
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=f"{_YUJIN_SYSTEM_PROMPT}\n\n창작자: {user_text}",
            response_schema=YUJIN_CONVERSATION_RESPONSE_SCHEMA,
        )
        reply_text = str(response.output_data.get("reply") or "").strip()
        if not reply_text:
            raise ValueError("local model returned an empty reply")
        return YujinLocalConversationResult(status="ok", reply=reply_text)
