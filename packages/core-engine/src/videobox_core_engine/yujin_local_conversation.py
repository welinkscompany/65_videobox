"""Local-first Yujin conversation reply path.

Owner decision (2026-08-05): docs/decisions/2026-08-05-local-first-assistant-decision.ko.md.
Yujin's primary conversation route runs on the local model instead of waiting
for the (undeployed) Hermes agent gateway. This module deliberately stays
outside that gateway's capability-token protocol: it grants no publish/tool
capability, so its output cannot mutate the project by itself. Editing
mutation still goes through the existing human-approval UI; a chat "네" is
never treated as approval. Script and title suggestions are allowed (owner,
2026-08-16), and so are thumbnail *prompt* suggestions -- text the owner
pastes into an external image tool (owner, 2026-08-19). Generating the
thumbnail image itself or a recommended video stays out of scope
(docs/implementation-plan.ko.md §23.3B) -- those requests are rejected
before the model is ever called, since that boundary must not depend on the
model choosing to comply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from videobox_domain_models.yujin_creator_context import UserApprovedPreference
from videobox_provider_interfaces.llm import LLMTaskType, StructuredLLMResponse

YUJIN_CONVERSATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}

_YUJIN_SYSTEM_PROMPT = (
    "너는 VideoBox의 창작 도우미 유진이다. 항상 한국어로, 영상을 만드는 창작자에게 "
    "말하듯 답한다. 다음은 절대 하지 않는다: 데이터베이스나 파일시스템 조작, 셸 명령 실행, "
    "자격증명·API key 요청 또는 노출, CapCut이나 렌더러를 직접 조작, 썸네일·추천 영상 자체를 생성. "
    "대본과 제목은 먼저 쓰거나 제안해도 된다. 썸네일 이미지를 직접 만들지는 않지만, 창작자가 "
    "이미지 생성 도구에 붙여 넣을 썸네일 프롬프트 문구를 제안하는 것은 된다. "
    "편집이 실제로 반영되려면 사람이 화면에서 직접 승인해야 하며, "
    "대화 중 '네'라는 대답은 승인이 아니다. 응답은 JSON 객체 {\"reply\": \"...\"} 형태로만 낸다."
)

# 답 형식 가이드: 썸네일 프롬프트 요청일 때만 붙는다. 이미지 생성 도구(GPT,
# ComfyUI 등)가 대체로 영문 프롬프트에서 더 좋은 결과를 내므로 프롬프트는
# 영문으로, 창작자가 고르기 쉽게 설명은 한국어로 요구한다.
_THUMBNAIL_PROMPT_GUIDE = (
    "\n\n창작자가 썸네일 이미지를 만들 때 붙여 넣을 프롬프트를 요청했다. "
    "이미지를 직접 만드는 것이 아니라 문구만 제안한다. "
    "영문 이미지 생성 프롬프트 5개를 번호를 붙여 제안하고, 각 프롬프트 바로 아래에 "
    "그 프롬프트로 어떤 썸네일이 나오는지 한 줄 한국어 설명을 붙인다. "
    "아래에 프로젝트 정보(제목·대본·장면 자막)가 주어지면 그 내용을 프롬프트에 반영한다."
)

# Deterministic pre-check: the boundary a chat assistant must not cross can't
# depend on the model choosing to comply, so restricted intents are rejected
# before any model call is made. Korean and English phrasing are both
# covered -- an English-only pattern set would leave the boundary porous to
# an English-phrased request even though the product is Korean-first.
_BLOCKED_INTENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(delete|drop|truncate|remove)\s+(the\s+)?(\w+\s+)?(table|database|db)\b",
        r"(데이터베이스|database|테이블|table).{0,10}(삭제|지워|drop|truncate)",
        r"sql",
        r"(쉘|셸|shell|bash|powershell|cmd)\s*(명령|실행|command)",
        r"\b(run|execute)\s+(this\s+)?(in\s+)?(shell|bash|powershell|cmd)\b",
        r"(파일|디렉터리|폴더).{0,4}(삭제|지워)",
        r"\bdelete\s+(the\s+)?(file|folder|directory)\b",
        r"(api\s*key|credential|비밀번호|자격\s*증명|access\s*token|password)",
        r"capcut.{0,6}(직접|바로).{0,6}(실행|조작|열어)",
        r"\b(open|run|launch)\s+capcut\s+(directly|myself)?\b",
        # 대본·제목은 **더 이상 막지 않는다.** owner가 2026-08-16에 풀었다
        # (`docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md` B).
        # 유진이 대본과 제목을 제안하는 것이 자율 창작 루프의 출발점이고, 그것을
        # 막아 두면 루프가 첫 칸에서 멈춘다. **제안까지만이다** -- owner가 확정하기
        # 전에는 어떤 장면도 만들지 않는다는 규칙은 그대로다.
        r"추천\s*영상.{0,6}(만들어|생성)",
        r"\b(make|generate|create)\s+(me\s+)?(a\s+)?recommended\s+video\b",
    )
)

# 썸네일 **이미지 생성** 요청은 계속 막는다. 다만 owner가 2026-08-19에 승인한
# 썸네일 **프롬프트 추천**("썸네일 생성 프롬프트 추천해 줘")이 같은 단어를
# 쓰므로, 이 묶음만 프롬프트 요청 여부를 먼저 보고 적용한다.
_THUMBNAIL_GENERATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"썸네일.{0,6}(만들어|생성)",
        r"\b(generate|make|create)\s+(me\s+)?(a\s+)?thumbnail\b",
    )
)

_THUMBNAIL_PROMPT_REQUEST_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(썸네일|thumbnail).{0,24}(프롬프트|prompt)",
        r"(프롬프트|prompt).{0,24}(썸네일|thumbnail)",
    )
)


def detect_thumbnail_prompt_request(user_text: str) -> bool:
    """True if the creator is asking for thumbnail *prompt text* to paste into
    an external image tool -- an allowed request (owner, 2026-08-19), distinct
    from asking Yujin to generate the thumbnail image itself."""
    return any(pattern.search(user_text) for pattern in _THUMBNAIL_PROMPT_REQUEST_PATTERNS)


def detect_blocked_intent(user_text: str) -> str | None:
    """Return the matched pattern source if `user_text` requests a restricted
    action, otherwise None. Exposed separately so callers can log/test the
    guard without going through the full reply path."""
    for pattern in _BLOCKED_INTENT_PATTERNS:
        if pattern.search(user_text):
            return pattern.pattern
    if not detect_thumbnail_prompt_request(user_text):
        for pattern in _THUMBNAIL_GENERATION_PATTERNS:
            if pattern.search(user_text):
                return pattern.pattern
    return None


@dataclass(slots=True, frozen=True)
class YujinLocalConversationResult:
    status: str  # "ok" | "blocked"
    reply: str
    blocked_reason: str | None = None


# 썸네일 프롬프트 추천에 실어 줄 프로젝트 사실들. 대본 전체·자막 전부를 그대로
# 실으면 로컬 모델 컨텍스트가 넘치므로 섹션을 만들 때 아래 한도로 자른다.
MAX_PROJECT_CONTEXT_TITLE_BYTES = 200
MAX_PROJECT_CONTEXT_SCRIPT_BYTES = 4_000
MAX_PROJECT_CONTEXT_CAPTIONS = 32
MAX_PROJECT_CONTEXT_CAPTION_BYTES = 200


@dataclass(slots=True, frozen=True)
class YujinProjectContext:
    """Read-only project facts a reply prompt may cite. Purely advisory:
    carrying this grants no capability and mutates nothing."""

    title: str = ""
    script_excerpt: str = ""
    scene_captions: tuple[str, ...] = ()


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _project_context_section(context: YujinProjectContext | None) -> str:
    if context is None:
        return ""
    title = _truncate_utf8(context.title.strip(), MAX_PROJECT_CONTEXT_TITLE_BYTES)
    script = _truncate_utf8(
        context.script_excerpt.strip(), MAX_PROJECT_CONTEXT_SCRIPT_BYTES
    )
    captions = tuple(
        _truncate_utf8(caption.strip(), MAX_PROJECT_CONTEXT_CAPTION_BYTES)
        for caption in context.scene_captions
        if caption.strip()
    )[:MAX_PROJECT_CONTEXT_CAPTIONS]
    if not (title or script or captions):
        return ""
    lines = [
        "\n\n지금 열려 있는 프로젝트 정보다. 썸네일 프롬프트를 추천할 때 이 내용을 근거로 쓴다."
    ]
    if title:
        lines.append(f"- 제목: {title}")
    if script:
        lines.append(f"- 대본 일부: {script}")
    if captions:
        lines.append("- 장면 자막:")
        lines.extend(f"  - {caption}" for caption in captions)
    return "\n".join(lines)


class _StructuredGenerator(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict,
    ) -> StructuredLLMResponse: ...


_MEMORY_CATEGORY_LABELS = {
    "pacing": "편집 템포",
    "caption": "자막",
    "audio": "음악과 소리",
    "tone": "영상 분위기",
    "workflow": "작업 방식",
}


def _memory_section(memories: tuple[UserApprovedPreference, ...]) -> str:
    """Render the memories the owner explicitly approved, or nothing at all.

    An empty section would still cost prompt room and invite the model to
    invent preferences, so no memory means no heading.
    """
    if not memories:
        return ""
    lines = "\n".join(
        f"- [{_MEMORY_CATEGORY_LABELS.get(item.category, item.category)}] {item.text}"
        for item in memories
    )
    return (
        "\n\n창작자가 직접 승인해 저장해 둔 편집 취향이다. 관련이 있을 때만 참고하고, "
        "여기 없는 취향은 지어내지 않는다.\n" + lines
    )


@dataclass(slots=True)
class YujinLocalConversationService:
    runtime: _StructuredGenerator

    def reply(
        self,
        *,
        project_id: str,
        user_text: str,
        memories: tuple[UserApprovedPreference, ...] = (),
        project_context: YujinProjectContext | None = None,
    ) -> YujinLocalConversationResult:
        if not user_text.strip():
            raise ValueError("user_text must not be blank")

        blocked_pattern = detect_blocked_intent(user_text)
        if blocked_pattern is not None:
            return YujinLocalConversationResult(
                status="blocked",
                reply=(
                    "이 요청은 유진이 직접 할 수 없어요. 데이터·파일·자격정보 조작이나 "
                    "썸네일·추천 영상 생성은 유진의 대화 범위 밖이에요. "
                    "대본과 제목, 썸네일에 쓸 프롬프트 추천은 말씀해 주세요."
                ),
                blocked_reason="policy_restricted_intent",
            )

        thumbnail_prompt_request = detect_thumbnail_prompt_request(user_text)
        response = self.runtime.generate_structured(
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=(
                f"{_YUJIN_SYSTEM_PROMPT}"
                f"{_THUMBNAIL_PROMPT_GUIDE if thumbnail_prompt_request else ''}"
                f"{_project_context_section(project_context)}"
                f"{_memory_section(memories)}"
                f"\n\n창작자: {user_text}"
            ),
            response_schema=YUJIN_CONVERSATION_RESPONSE_SCHEMA,
        )
        reply_text = str(response.output_data.get("reply") or "").strip()
        if not reply_text:
            raise ValueError("local model returned an empty reply")
        return YujinLocalConversationResult(status="ok", reply=reply_text)
