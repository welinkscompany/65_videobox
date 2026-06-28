from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMRequest,
    StructuredLLMResponse,
)


class LocalChatTransport(Protocol):
    def complete_chat(self, *, model_name: str, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        """Execute a local structured chat completion and return the raw response payload."""


@dataclass(slots=True)
class LocalQwenHTTPTransport(LocalChatTransport):
    base_url: str = "http://127.0.0.1:1234/v1"
    timeout_seconds: int = 30
    http_client: Callable[..., Any] = urlopen
    provider_name: str = "local_qwen"

    def complete_chat(self, *, model_name: str, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "videobox_structured_output",
                    "schema": response_schema,
                },
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.http_client(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Local Qwen request timed out.",
                retryable=True,
                error_code="LOCAL_TIMEOUT",
                occurred_at=datetime.now(UTC),
            ) from exc
        except HTTPError as exc:
            raise self._normalize_http_error(exc) from exc
        except URLError as exc:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Local Qwen request failed due to a transient network error.",
                retryable=True,
                error_code="LOCAL_NETWORK_ERROR",
                occurred_at=datetime.now(UTC),
            ) from exc

    def _normalize_http_error(self, exc: HTTPError) -> LLMProviderError:
        payload = self._read_error_payload(exc)
        error_block = payload.get("error", {}) if isinstance(payload, dict) else {}
        status_code = int(getattr(exc, "code", 0) or 0)
        message = str(error_block.get("message") or exc.reason or exc.msg or "Local Qwen request failed.")
        retryable = status_code in {408, 409, 429, 500, 502, 503, 504}
        error_code = str(error_block.get("code") or f"HTTP_{status_code}")
        return LLMProviderError(
            provider_name=self.provider_name,
            message=message,
            retryable=retryable,
            error_code=error_code,
            occurred_at=datetime.now(UTC),
        )

    def _read_error_payload(self, exc: HTTPError) -> dict[str, Any]:
        if exc.fp is None:
            return {}
        try:
            raw = exc.fp.read()
            if not raw:
                return {}
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


@dataclass(slots=True)
class LocalQwenStructuredProvider(StructuredLLMProvider):
    transport: LocalChatTransport
    provider_name: str = "local_qwen"
    supported_tasks: set[LLMTaskType] = field(default_factory=lambda: set(LLMTaskType))

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        model_name = str(request.provider_context.get("model_name") or "qwen3-35b")
        payload = self.transport.complete_chat(
            model_name=model_name,
            prompt=request.prompt,
            response_schema=request.response_schema,
        )
        raw_text = self._extract_message_content(payload)
        try:
            output_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Local Qwen returned invalid JSON content.",
                retryable=False,
                error_code="invalid_json",
            ) from exc
        if not isinstance(output_data, dict):
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Local Qwen structured response must be a JSON object.",
                retryable=False,
                error_code="invalid_json_shape",
            )
        return StructuredLLMResponse(
            provider_name=self.provider_name,
            model_name=model_name,
            output_data=output_data,
            raw_text=raw_text,
            metadata={"routing_policy": request.provider_context.get("routing_policy")},
        )

    def _extract_message_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Local Qwen returned no choices.",
                retryable=True,
                error_code="empty_choices",
            )
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text_parts = [part.get("text") for part in content if isinstance(part, dict)]
            combined = "".join(part for part in text_parts if isinstance(part, str))
            if combined.strip():
                return combined
        raise LLMProviderError(
            provider_name=self.provider_name,
            message="Local Qwen returned no usable message content.",
            retryable=True,
            error_code="empty_content",
        )
