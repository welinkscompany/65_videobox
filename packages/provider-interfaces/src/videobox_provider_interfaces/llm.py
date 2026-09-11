from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class LLMTaskType(str, Enum):
    SCENE_PLANNING = "scene_planning"
    KEYWORD_EXPANSION = "keyword_expansion"
    MUSIC_RECOMMENDATION = "music_recommendation"
    ALIGNMENT_REVIEW = "alignment_review"
    OPERATOR_COPY = "operator_copy"
    YUJIN_CONVERSATION = "yujin_conversation"
    # 대본 한 줄을 그림 만드는 프로그램이 알아듣는 영어 묘사로 바꾼다.
    # 한국어를 그대로 넣으면 전혀 다른 그림이 나온다 -- 2026-08-21 실측.
    SCENE_IMAGE_PROMPT = "scene_image_prompt"
    # 주제 한 줄에서 대본 초안을 쓴다. **구조화 출력으로만 부른다** --
    # 자유형 대화로 물으면 생각 과정이 영어로 새어 나온다(2026-08-21 실측).
    SCRIPT_DRAFT = "script_draft"
    # 자막을 다른 언어로 옮긴다. 원본은 그대로 두고 나란히 쌓는다.
    CAPTION_TRANSLATION = "caption_translation"
    # 인포그래픽 한 장을 HTML로 쓴다. **대본보다 훨씬 길다** -- 로컬 런타임
    # 기본 상한 30초로는 모자라서 이 일만 따로 상한을 준다
    # (`infographic_service`, 2026-09-07 실측).
    INFOGRAPHIC_HTML = "infographic_html"
    # 롱폼에서 마케팅용 숏폼에 넣을 대목을 고른다. 훅·결론·숫자를 보고 판단한다
    # (`short_form_scene_pick`, 2026-09-11). 자막을 묶음으로 나눠 여러 번 부른다.
    SHORT_FORM_SCENE_PICK = "short_form_scene_pick"
    # 밤사이 대화 기록을 훑어 owner가 승인할 만한 기억 후보를 뽑는다
    # (기억 사서, 2026-09-08 착수). 도구 호출 없이 순수 구조화 응답 한 번뿐.
    MEMORY_LIBRARIAN_DISTILL = "memory_librarian_distill"


@dataclass(slots=True, frozen=True)
class LLMProviderConfig:
    provider_name: str
    enabled: bool = True
    timeout_seconds: int = 30
    retry_limit: int = 1


@dataclass(slots=True, frozen=True)
class LLMRequest:
    task_type: LLMTaskType
    prompt: str
    provider_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LLMResponse:
    provider_name: str
    model_name: str
    output_text: str
    metadata: dict[str, Any]


@dataclass(slots=True, frozen=True)
class StructuredLLMRequest:
    task_type: LLMTaskType
    prompt: str
    response_schema: dict[str, Any]
    provider_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class StructuredLLMResponse:
    provider_name: str
    model_name: str
    output_data: dict[str, Any]
    raw_text: str
    metadata: dict[str, Any]


@dataclass(slots=True, frozen=True)
class LLMProviderError(Exception):
    provider_name: str
    message: str
    retryable: bool = False
    error_code: str | None = None
    occurred_at: datetime | None = None

    def __str__(self) -> str:
        return f"{self.provider_name}: {self.message}"


class LLMProvider(Protocol):
    provider_name: str
    supported_tasks: set[LLMTaskType]

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return a text response for a routing task."""


class StructuredLLMProvider(Protocol):
    provider_name: str
    supported_tasks: set[LLMTaskType]

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        """Return a structured response for a routing task."""
