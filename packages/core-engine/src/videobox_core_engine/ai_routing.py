from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from videobox_domain_models.ai_providers import GeminiApiKeyPool
from videobox_provider_interfaces.llm import (
    LLMProvider,
    LLMProviderConfig,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTaskType,
)
from videobox_provider_interfaces.visual_generation import (
    VisualGenerationProvider,
    VisualGenerationRequest,
    VisualGenerationResponse,
)


@dataclass(slots=True)
class LLMTaskRouter:
    local_provider: LLMProvider
    gemini_provider: LLMProvider
    gemini_key_pool: GeminiApiKeyPool
    local_config: LLMProviderConfig
    gemini_config: LLMProviderConfig
    openai_provider: LLMProvider | None = None
    openai_config: LLMProviderConfig | None = None
    visual_provider: VisualGenerationProvider | None = None

    def complete(
        self,
        *,
        task_type: LLMTaskType,
        prompt: str,
        now: datetime | None = None,
    ) -> LLMResponse:
        timestamp = now or datetime.now(UTC)
        request = LLMRequest(task_type=task_type, prompt=prompt)

        local_result = self._try_local(request)
        if local_result is not None:
            return local_result

        gemini_result = self._try_gemini(task_type=task_type, prompt=prompt, now=timestamp)
        if gemini_result is not None:
            return gemini_result

        openai_result = self._try_openai(request)
        if openai_result is not None:
            return openai_result

        return LLMResponse(
            provider_name="rule_based_fallback",
            model_name="manual_review_gate",
            output_text="Manual review required after provider fallback exhaustion.",
            metadata={"task_type": task_type.value},
        )

    def generate_visual(self, *, prompt: str, project_id: str) -> VisualGenerationResponse:
        if self.visual_provider is None:
            raise ValueError("No visual generation provider configured.")
        return self.visual_provider.generate(
            VisualGenerationRequest(prompt=prompt, project_id=project_id)
        )

    def _try_local(self, request: LLMRequest) -> LLMResponse | None:
        if not self.local_config.enabled or request.task_type not in self.local_provider.supported_tasks:
            return None
        try:
            return self.local_provider.complete(request)
        except LLMProviderError:
            return None

    def _try_gemini(
        self,
        *,
        task_type: LLMTaskType,
        prompt: str,
        now: datetime,
    ) -> LLMResponse | None:
        if not self.gemini_config.enabled or task_type not in self.gemini_provider.supported_tasks:
            return None
        available_keys = self.gemini_key_pool.available_keys(now=now)
        if not available_keys:
            return None
        key = available_keys[0]
        request = LLMRequest(
            task_type=task_type,
            prompt=prompt,
            provider_context={
                "gemini_key_id": key.key_id,
                "model_name": self._gemini_model_for_task(key, task_type),
            },
        )
        try:
            return self.gemini_provider.complete(request)
        except LLMProviderError:
            return None

    def _try_openai(self, request: LLMRequest) -> LLMResponse | None:
        if (
            self.openai_provider is None
            or self.openai_config is None
            or not self.openai_config.enabled
            or request.task_type not in self.openai_provider.supported_tasks
        ):
            return None
        try:
            return self.openai_provider.complete(request)
        except LLMProviderError:
            return None

    def _gemini_model_for_task(self, key, task_type: LLMTaskType) -> str:
        if task_type is LLMTaskType.KEYWORD_EXPANSION:
            return key.cheap_model
        if task_type is LLMTaskType.ALIGNMENT_REVIEW:
            return key.high_quality_model
        return key.primary_model
