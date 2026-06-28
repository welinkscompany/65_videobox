from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

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
