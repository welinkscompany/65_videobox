from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from videobox_core_engine.gemini_runtime import GeminiStructuredGenerationError, GeminiStructuredRuntime
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from videobox_storage.local_project_store import LocalProjectStore


@dataclass(slots=True)
class LocalFirstStructuredGenerationError(Exception):
    message: str
    error_code: str
    provider_name: str = "local_first_router"
    provider_trace: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.provider_name}: {self.message}"


@dataclass(slots=True)
class LocalFirstStructuredRuntime:
    store: LocalProjectStore
    local_provider: StructuredLLMProvider
    gemini_provider: StructuredLLMProvider
    local_config: LLMProviderConfig
    gemini_config: LLMProviderConfig
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig = field(
        default_factory=LocalOpenAICompatibleRuntimeConfig
    )
    cooldown_seconds: int = 180
    local_preferred_tasks: set[LLMTaskType] = field(
        default_factory=lambda: {
            LLMTaskType.SCENE_PLANNING,
            LLMTaskType.KEYWORD_EXPANSION,
            LLMTaskType.MUSIC_RECOMMENDATION,
            LLMTaskType.OPERATOR_COPY,
        }
    )

    def generate(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        timestamp = now or datetime.now(UTC)
        gemini_runtime = GeminiStructuredRuntime(
            store=self.store,
            provider=self.gemini_provider,
            provider_config=self.gemini_config,
            cooldown_seconds=self.cooldown_seconds,
        )
        local_enabled = self.local_config.enabled and self.local_runtime_config.enabled
        fallback_reasons: list[str] = []
        if not local_enabled or task_type not in self.local_preferred_tasks:
            if not local_enabled:
                fallback_reasons.append("local_disabled")
            else:
                fallback_reasons.append("task_not_local_preferred")
            return self._with_provider_trace(
                gemini_runtime.generate(
                    project_id=project_id,
                    task_type=task_type,
                    prompt=prompt,
                    response_schema=response_schema,
                    now=timestamp,
                ),
                fallback_reasons=fallback_reasons,
            )

        try:
            self._validate_request(prompt=prompt, response_schema=response_schema)
            response = self.local_provider.complete_structured(
                StructuredLLMRequest(
                    task_type=task_type,
                    prompt=prompt,
                    response_schema=response_schema,
                    provider_context={
                        "model_name": self.local_runtime_config.model_name,
                        "routing_policy": "local_first",
                        "task_type": task_type.value,
                    },
                )
            )
            self._validate_response_schema(response.output_data, response_schema)
            return self._with_provider_trace(response, fallback_reasons=fallback_reasons)
        except LLMProviderError:
            fallback_reasons.append("local_provider_error")
        except LocalFirstStructuredGenerationError as exc:
            fallback_reasons.append(self._local_failure_reason(exc.error_code))

        try:
            return self._with_provider_trace(
                gemini_runtime.generate(
                    project_id=project_id,
                    task_type=task_type,
                    prompt=prompt,
                    response_schema=response_schema,
                    now=timestamp,
                ),
                fallback_reasons=fallback_reasons,
            )
        except GeminiStructuredGenerationError as exc:
            raise LocalFirstStructuredGenerationError(
                message=exc.message,
                error_code=exc.error_code,
                provider_name=exc.provider_name,
                provider_trace=build_provider_trace(
                    final_provider=exc.provider_name,
                    fallback_reasons=[*fallback_reasons, "gemini_unavailable"],
                ),
            ) from exc

    def _with_provider_trace(
        self,
        response: StructuredLLMResponse,
        *,
        fallback_reasons: list[str],
    ) -> StructuredLLMResponse:
        metadata = dict(response.metadata)
        metadata["provider_trace"] = build_provider_trace(
            final_provider=response.provider_name,
            fallback_reasons=fallback_reasons,
        )
        return StructuredLLMResponse(
            provider_name=response.provider_name,
            model_name=response.model_name,
            output_data=response.output_data,
            raw_text=response.raw_text,
            metadata=metadata,
        )

    def _local_failure_reason(self, error_code: str) -> str:
        if error_code == "structured_output_invalid":
            return "local_response_invalid"
        if error_code == "invalid_request":
            return "local_request_invalid"
        return "local_provider_error"

    def _validate_request(self, *, prompt: str, response_schema: dict[str, Any]) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise LocalFirstStructuredGenerationError(
                message="Invalid request: prompt must be a non-empty string.",
                error_code="invalid_request",
            )
        if not isinstance(response_schema, dict):
            raise LocalFirstStructuredGenerationError(
                message="Invalid request: response schema must be an object schema.",
                error_code="invalid_request",
            )
        if response_schema.get("type") != "object":
            raise LocalFirstStructuredGenerationError(
                message="Invalid request: response schema must declare type 'object'.",
                error_code="invalid_request",
            )
        properties = response_schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise LocalFirstStructuredGenerationError(
                message="Invalid request: response schema must define object properties.",
                error_code="invalid_request",
            )
        required_fields = response_schema.get("required", [])
        if not isinstance(required_fields, list):
            raise LocalFirstStructuredGenerationError(
                message="Invalid request: response schema required fields must be a list.",
                error_code="invalid_request",
            )

    def _validate_response_schema(self, output_data: dict[str, Any], response_schema: dict[str, Any]) -> None:
        if response_schema.get("type") != "object" or not isinstance(output_data, dict):
            raise LocalFirstStructuredGenerationError(
                message="Structured response validation failed: output must be an object.",
                error_code="structured_output_invalid",
            )
        required_fields = response_schema.get("required", [])
        properties = response_schema.get("properties", {})
        for field_name in required_fields:
            if field_name not in output_data:
                raise LocalFirstStructuredGenerationError(
                    message=f"Structured response validation failed: missing required field '{field_name}'.",
                    error_code="structured_output_invalid",
                )
        for field_name, schema in properties.items():
            if field_name not in output_data:
                continue
            if not self._matches_type(output_data[field_name], schema):
                raise LocalFirstStructuredGenerationError(
                    message=f"Structured response validation failed: field '{field_name}' has invalid type.",
                    error_code="structured_output_invalid",
                )

    def _matches_type(self, value: Any, schema: dict[str, Any]) -> bool:
        expected_type = schema.get("type")
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "boolean":
            return isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "object":
            return isinstance(value, dict)
        if expected_type == "array":
            if not isinstance(value, list):
                return False
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                return all(self._matches_type(item, item_schema) for item in value)
            return True
        return True
