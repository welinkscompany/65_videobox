from __future__ import annotations

import json
import re
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


# Qwen3 계열은 "생각" 모드가 켜지면 실제 답 앞에 <think>...</think> 추론
# 블록을 content에 그대로 얹어 보낸다. LM Studio가 이걸 골라내는지는
# 그때그때(로드 방식·프리셋에 따라) 다르다는 것이 2026-09-17에 실측으로
# 드러났다 -- 같은 모델을 CLI로 다시 올렸더니(재부팅 뒤) 골라내기가 멈췄고,
# 그 순간 실제 화면 채팅이 전부 "invalid_json"으로 죽었다(json.loads가
# "<think>...")로 시작하는 문자열을 못 읽는다). LM Studio 설정에 기대는
# 대신 여기서 직접 걷어내 그 설정과 무관하게 항상 통하게 한다.
#
# **문자열 맨 앞에 붙은 블록만** 지운다(`^`로 고정). 아무 데나 있는
# `<think>...</think>`를 다 지우면, 답변 텍스트 자체가 정당하게 그 낱말을
# 담고 있는 드문 경우(예: 창작자가 태그 이름을 물어봐서 유진이 인용하는
# 경우) JSON 값 안쪽을 잘라내 오히려 망가뜨릴 수 있다. 실제 관찰된 누출은
# 전부 맨 앞이었으므로 이 좁힘으로 충분하다.
_REASONING_BLOCK_PATTERN = re.compile(r"^\s*<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_reasoning_block(text: str) -> str:
    return _REASONING_BLOCK_PATTERN.sub("", text).strip()


class LocalChatTransport(Protocol):
    def complete_chat(
        self,
        *,
        model_name: str,
        prompt: str,
        response_schema: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Execute a local structured chat completion and return the raw response payload.

        `timeout_seconds`는 **이 한 호출만** 기다리는 상한이다. 없으면 설정값을 쓴다.
        숏폼 판단처럼 오래 걸리는 일(2026-09-12 실측: 훑기 130초·짜기 267초)이
        전역 기본값 30초에 통째로 끊기던 것을 여기서 연다.
        """


@dataclass(slots=True)
class LocalQwenHTTPTransport(LocalChatTransport):
    base_url: str = "http://127.0.0.1:1234/v1"
    timeout_seconds: int = 30
    http_client: Callable[..., Any] = urlopen
    provider_name: str = "local_qwen"

    def complete_chat(
        self,
        *,
        model_name: str,
        prompt: str,
        response_schema: dict[str, Any],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        wait_seconds = int(timeout_seconds) if timeout_seconds else self.timeout_seconds
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
            with self.http_client(request, timeout=wait_seconds) as response:
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
        # 이 한 호출만 기다릴 상한. 부르는 쪽이 안 주면 설정값(기본 30초)이다 --
        # 숏폼 판단이 이 칸으로 더 기다린다(2026-09-12).
        raw_timeout = request.provider_context.get("timeout_seconds")
        try:
            timeout_seconds = int(raw_timeout) if raw_timeout else None
        except (TypeError, ValueError):
            timeout_seconds = None
        payload = self.transport.complete_chat(
            model_name=model_name,
            prompt=request.prompt,
            response_schema=request.response_schema,
            timeout_seconds=timeout_seconds,
        )
        raw_text = _strip_reasoning_block(self._extract_message_content(payload))
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
