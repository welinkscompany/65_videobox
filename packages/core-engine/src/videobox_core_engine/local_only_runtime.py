from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMRequest,
    StructuredLLMResponse,
)


@dataclass(slots=True)
class LocalOnlyStructuredGenerationError(Exception):
    message: str
    error_code: str
    provider_name: str = "local_only_runtime"
    provider_trace: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.provider_name}: {self.message}"


@dataclass(slots=True)
class LocalOnlyStructuredRuntime:
    local_provider: StructuredLLMProvider
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig = field(
        default_factory=LocalOpenAICompatibleRuntimeConfig
    )

    def generate(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> StructuredLLMResponse:
        del project_id
        if not self.local_runtime_config.enabled:
            raise LocalOnlyStructuredGenerationError(
                message="Local structured generation is disabled.",
                error_code="local_disabled",
                provider_trace=build_provider_trace(
                    final_provider="local_qwen",
                    fallback_reasons=["local_disabled"],
                    routing_mode="local_only",
                ),
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
                        "routing_policy": "local_only",
                        "task_type": task_type.value,
                    },
                )
            )
            self._validate_response_schema(response.output_data, response_schema)
        except LocalOnlyStructuredGenerationError:
            raise
        except LLMProviderError as exc:
            raise LocalOnlyStructuredGenerationError(
                message=exc.message,
                error_code=exc.error_code or "local_provider_error",
                provider_name=exc.provider_name,
                provider_trace=build_provider_trace(
                    final_provider=exc.provider_name,
                    fallback_reasons=["local_provider_error"],
                    routing_mode="local_only",
                ),
            ) from exc

        metadata = dict(response.metadata)
        metadata["provider_trace"] = build_provider_trace(
            final_provider=response.provider_name,
            fallback_reasons=[],
            routing_mode="local_only",
        )
        return StructuredLLMResponse(
            provider_name=response.provider_name,
            model_name=response.model_name,
            output_data=response.output_data,
            raw_text=response.raw_text,
            metadata=metadata,
        )

    def _validate_request(self, *, prompt: str, response_schema: dict[str, Any]) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise LocalOnlyStructuredGenerationError(
                message="Invalid request: prompt must be a non-empty string.",
                error_code="invalid_request",
            )
        if not isinstance(response_schema, dict) or response_schema.get("type") != "object":
            raise LocalOnlyStructuredGenerationError(
                message="Invalid request: response schema must declare type 'object'.",
                error_code="invalid_request",
            )
        if not isinstance(response_schema.get("properties"), dict) or not response_schema["properties"]:
            raise LocalOnlyStructuredGenerationError(
                message="Invalid request: response schema must define object properties.",
                error_code="invalid_request",
            )
        if not isinstance(response_schema.get("required", []), list):
            raise LocalOnlyStructuredGenerationError(
                message="Invalid request: response schema required fields must be a list.",
                error_code="invalid_request",
            )

    def _validate_response_schema(self, output_data: dict[str, Any], response_schema: dict[str, Any]) -> None:
        if not isinstance(output_data, dict):
            raise LocalOnlyStructuredGenerationError(
                message="Structured response validation failed: output must be an object.",
                error_code="structured_output_invalid",
            )
        for field_name in response_schema.get("required", []):
            if field_name not in output_data:
                raise LocalOnlyStructuredGenerationError(
                    message=f"Structured response validation failed: missing required field '{field_name}'.",
                    error_code="structured_output_invalid",
                )
        for field_name, schema in response_schema.get("properties", {}).items():
            if field_name in output_data and not self._matches_type(output_data[field_name], schema):
                raise LocalOnlyStructuredGenerationError(
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
            return isinstance(value, list) and (
                not isinstance(schema.get("items"), dict)
                or all(self._matches_type(item, schema["items"]) for item in value)
            )
        return True
