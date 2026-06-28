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
