from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from datetime import timedelta

from videobox_domain_models.ai_providers import GeminiApiKeyPool, GeminiApiKeyRecord, GeminiKeyStatus
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
class GeminiStructuredGenerationError(Exception):
    message: str
    error_code: str
    provider_name: str = "gemini"

    def __str__(self) -> str:
        return f"{self.provider_name}: {self.message}"


@dataclass(slots=True)
class GeminiStructuredRuntime:
    store: LocalProjectStore
    provider: StructuredLLMProvider
    provider_config: LLMProviderConfig
    cooldown_seconds: int = 180

    def generate(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        if not self.provider_config.enabled:
            raise GeminiStructuredGenerationError(
                message="Gemini runtime is disabled.",
                error_code="provider_disabled",
            )
        self._validate_request(prompt=prompt, response_schema=response_schema)
        timestamp = now or datetime.now(UTC)
        key_pool = self._load_key_pool(project_id=project_id)
        available_keys = key_pool.available_keys(now=timestamp)
        if not available_keys:
            raise GeminiStructuredGenerationError(
                message="No usable Gemini keys are available.",
                error_code="no_available_keys",
            )

        last_error: GeminiStructuredGenerationError | None = None
        for key in available_keys:
            request = StructuredLLMRequest(
                task_type=task_type,
                prompt=prompt,
                response_schema=response_schema,
                provider_context={
                    "gemini_key_id": key.key_id,
                    "model_name": self._model_for_task(key=key, task_type=task_type),
                    "api_key_secret": key.api_key,
                },
            )
            try:
                response = self.provider.complete_structured(request)
                self._validate_response_schema(response.output_data, response_schema)
                self._persist_success(project_id=project_id, key_id=key.key_id, now=timestamp)
                return response
            except LLMProviderError as exc:
                last_error = self._handle_provider_error(
                    project_id=project_id,
                    key_id=key.key_id,
                    error=exc,
                    now=timestamp,
                )
                continue
            except GeminiStructuredGenerationError as exc:
                last_error = self._handle_validation_error(
                    project_id=project_id,
                    key_id=key.key_id,
                    error=exc,
                    now=timestamp,
                )
                continue

        if last_error is not None:
            raise last_error
        raise GeminiStructuredGenerationError(
            message="Gemini runtime failed without a recoverable result.",
            error_code="unknown_runtime_failure",
        )

    def _load_key_pool(self, *, project_id: str) -> GeminiApiKeyPool:
        records = self.store.list_gemini_provider_keys_with_secrets(project_id=project_id)
        keys = tuple(
            GeminiApiKeyRecord(
                key_id=str(record["key_id"]),
                label=str(record["label"]),
                api_key=str(record["api_key_secret"]),
                primary_model=str(record["primary_model"]),
                cheap_model=str(record["cheap_model"]),
                high_quality_model=str(record["high_quality_model"]),
                status=GeminiKeyStatus(str(record["status"])),
                cooldown_until=self._parse_optional_datetime(record.get("cooldown_until")),
                consecutive_failures=int(record.get("consecutive_failures") or 0),
                last_error=record.get("last_error"),
                last_used_at=self._parse_optional_datetime(record.get("last_used_at")),
            )
            for record in records
        )
        return GeminiApiKeyPool(keys=keys)

    def _persist_success(self, *, project_id: str, key_id: str, now: datetime) -> None:
        self.store.update_gemini_provider_key_runtime_state(
            project_id=project_id,
            key_id=key_id,
            status="active",
            cooldown_until=None,
            consecutive_failures=0,
            last_error=None,
            last_used_at=now.isoformat(),
        )

    def _handle_provider_error(
        self,
        *,
        project_id: str,
        key_id: str,
        error: LLMProviderError,
        now: datetime,
    ) -> GeminiStructuredGenerationError:
        current = self.store.get_gemini_provider_key(
            project_id=project_id,
            key_id=key_id,
            include_secret=True,
        )
        sanitized_message = self._sanitize_message(
            message=error.message,
            secret=current["api_key_secret"],
        )
        next_state = self._next_state_for_provider_error(error=error, current=current)
        cooldown_until = (now + self._cooldown_delta()).isoformat() if next_state == "cooldown" else None
        self.store.update_gemini_provider_key_runtime_state(
            project_id=project_id,
            key_id=key_id,
            status=next_state,
            cooldown_until=cooldown_until,
            consecutive_failures=int(current["consecutive_failures"]) + 1,
            last_error=sanitized_message,
            last_used_at=now.isoformat(),
        )
        return GeminiStructuredGenerationError(
            message=sanitized_message,
            error_code=error.error_code or "provider_error",
        )

    def _handle_validation_error(
        self,
        *,
        project_id: str,
        key_id: str,
        error: GeminiStructuredGenerationError,
        now: datetime,
    ) -> GeminiStructuredGenerationError:
        current = self.store.get_gemini_provider_key(
            project_id=project_id,
            key_id=key_id,
            include_secret=True,
        )
        sanitized_message = self._sanitize_message(
            message=error.message,
            secret=current["api_key_secret"],
        )
        self.store.update_gemini_provider_key_runtime_state(
            project_id=project_id,
            key_id=key_id,
            status="active",
            cooldown_until=None,
            consecutive_failures=int(current["consecutive_failures"]) + 1,
            last_error=sanitized_message,
            last_used_at=now.isoformat(),
        )
        return GeminiStructuredGenerationError(
            message=sanitized_message,
            error_code=error.error_code,
        )

    def _validate_request(self, *, prompt: str, response_schema: dict[str, Any]) -> None:
        if not isinstance(prompt, str) or not prompt.strip():
            raise GeminiStructuredGenerationError(
                message="Invalid request: prompt must be a non-empty string.",
                error_code="invalid_request",
            )
        if not isinstance(response_schema, dict):
            raise GeminiStructuredGenerationError(
                message="Invalid request: response schema must be an object schema.",
                error_code="invalid_request",
            )
        if response_schema.get("type") != "object":
            raise GeminiStructuredGenerationError(
                message="Invalid request: response schema must declare type 'object'.",
                error_code="invalid_request",
            )
        properties = response_schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise GeminiStructuredGenerationError(
                message="Invalid request: response schema must define object properties.",
                error_code="invalid_request",
            )
        required_fields = response_schema.get("required", [])
        if not isinstance(required_fields, list):
            raise GeminiStructuredGenerationError(
                message="Invalid request: response schema required fields must be a list.",
                error_code="invalid_request",
            )

    def _validate_response_schema(self, output_data: dict[str, Any], response_schema: dict[str, Any]) -> None:
        if response_schema.get("type") != "object" or not isinstance(output_data, dict):
            raise GeminiStructuredGenerationError(
                message="Structured response validation failed: output must be an object.",
                error_code="structured_output_invalid",
            )
        required_fields = response_schema.get("required", [])
        properties = response_schema.get("properties", {})
        for field_name in required_fields:
            if field_name not in output_data:
                raise GeminiStructuredGenerationError(
                    message=f"Structured response validation failed: missing required field '{field_name}'.",
                    error_code="structured_output_invalid",
                )
        for field_name, schema in properties.items():
            if field_name not in output_data:
                continue
            if not self._matches_type(output_data[field_name], schema):
                raise GeminiStructuredGenerationError(
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

    def _next_state_for_provider_error(self, *, error: LLMProviderError, current: dict[str, Any]) -> str:
        normalized_code = (error.error_code or "").upper()
        if normalized_code in {"RESOURCE_EXHAUSTED", "RATE_LIMITED"} and error.retryable:
            return "cooldown"
        if normalized_code in {"INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "API_KEY_INVALID"}:
            return "invalid"
        failures = int(current["consecutive_failures"]) + 1
        return "disabled" if failures >= 3 else str(current["status"])

    def _model_for_task(self, *, key: GeminiApiKeyRecord, task_type: LLMTaskType) -> str:
        if task_type is LLMTaskType.KEYWORD_EXPANSION:
            return key.cheap_model
        if task_type is LLMTaskType.ALIGNMENT_REVIEW:
            return key.high_quality_model
        return key.primary_model

    def _sanitize_message(self, *, message: str, secret: str) -> str:
        return str(message).replace(secret, "[REDACTED]")

    def _parse_optional_datetime(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _cooldown_delta(self):
        return timedelta(seconds=self.cooldown_seconds)
