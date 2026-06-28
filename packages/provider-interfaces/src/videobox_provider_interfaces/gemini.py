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


class GeminiContentTransport(Protocol):
    def generate_content(self, *, model_name: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a Gemini content request and return the raw response payload."""


@dataclass(slots=True)
class GeminiHTTPTransport(GeminiContentTransport):
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: int = 30
    http_client: Callable[..., Any] = urlopen
    provider_name: str = "gemini"

    def generate_content(self, *, model_name: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=f"{self.base_url}/models/{model_name}:generateContent?key={api_key}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.http_client(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._normalize_http_error(exc=exc, api_key=api_key) from exc
        except URLError as exc:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Gemini request failed due to a transient network error.",
                retryable=True,
                error_code="NETWORK_ERROR",
                occurred_at=datetime.now(UTC),
            ) from exc

    def _normalize_http_error(self, *, exc: HTTPError, api_key: str) -> LLMProviderError:
        payload = self._read_error_payload(exc)
        error_block = payload.get("error", {}) if isinstance(payload, dict) else {}
        status_code = int(getattr(exc, "code", 0) or 0)
        provider_status = str(error_block.get("status") or f"HTTP_{status_code}")
        message = str(error_block.get("message") or exc.reason or exc.msg or "Gemini request failed.")
        sanitized_message = message.replace(api_key, "[REDACTED]")
        return LLMProviderError(
            provider_name=self.provider_name,
            message=sanitized_message,
            retryable=self._is_retryable(status_code=status_code, provider_status=provider_status),
            error_code=provider_status,
            occurred_at=datetime.now(UTC),
        )

    def _read_error_payload(self, exc: HTTPError) -> dict[str, Any]:
        if exc.fp is None:
            return {}
        try:
            raw = exc.fp.read()
            if not raw:
                return {}
            decoded = raw.decode("utf-8")
            payload = json.loads(decoded)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _is_retryable(self, *, status_code: int, provider_status: str) -> bool:
        if status_code in {408, 429, 500, 502, 503, 504}:
            return True
        return provider_status.upper() in {"RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED"}


@dataclass(slots=True)
class GeminiRESTStructuredProvider(StructuredLLMProvider):
    transport: GeminiContentTransport
    provider_name: str = "gemini"
    supported_tasks: set[LLMTaskType] = field(default_factory=lambda: set(LLMTaskType))

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        model_name = str(request.provider_context["model_name"])
        api_key_secret = str(request.provider_context["api_key_secret"])
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.prompt}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": request.response_schema,
            },
        }
        response_payload = self.transport.generate_content(
            model_name=model_name,
            api_key=api_key_secret,
            payload=payload,
        )
        raw_text = self._extract_response_text(response_payload)
        try:
            output_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Gemini returned invalid JSON content.",
                retryable=False,
                error_code="invalid_json",
            ) from exc
        if not isinstance(output_data, dict):
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Gemini structured response must be a JSON object.",
                retryable=False,
                error_code="invalid_json_shape",
            )
        return StructuredLLMResponse(
            provider_name=self.provider_name,
            model_name=model_name,
            output_data=output_data,
            raw_text=raw_text,
            metadata={"gemini_key_id": request.provider_context.get("gemini_key_id")},
        )

    def _extract_response_text(self, response_payload: dict[str, Any]) -> str:
        candidates = response_payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Gemini returned no candidates.",
                retryable=True,
                error_code="empty_candidates",
            )
        parts = candidates[0].get("content", {}).get("parts", [])
        if not isinstance(parts, list):
            raise LLMProviderError(
                provider_name=self.provider_name,
                message="Gemini returned malformed content parts.",
                retryable=True,
                error_code="malformed_response",
            )
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text
        raise LLMProviderError(
            provider_name=self.provider_name,
            message="Gemini returned no text parts.",
            retryable=True,
            error_code="empty_text",
        )
