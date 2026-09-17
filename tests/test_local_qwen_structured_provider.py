from __future__ import annotations

import pytest

from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType, StructuredLLMRequest
from videobox_provider_interfaces.local_qwen import LocalQwenStructuredProvider


class _FakeTransport:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def complete_chat(self, *, model_name, prompt, response_schema, timeout_seconds=None):
        self.calls.append(
            {
                "model_name": model_name,
                "prompt": prompt,
                "response_schema": response_schema,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"choices": [{"message": {"content": self._content}}]}


def _request(prompt: str = "hello") -> StructuredLLMRequest:
    return StructuredLLMRequest(
        task_type=LLMTaskType.YUJIN_CONVERSATION,
        prompt=prompt,
        response_schema={"type": "object", "properties": {"reply": {"type": "string"}}},
        provider_context={"model_name": "qwen/qwen3.8-27b"},
    )


def test_parses_clean_json_content_with_no_reasoning_block() -> None:
    """기준 동작: 평소처럼 순수 JSON만 오면 그대로 통과한다(회귀 없음)."""
    provider = LocalQwenStructuredProvider(transport=_FakeTransport('{"reply": "안녕하세요"}'))

    response = provider.complete_structured(_request())

    assert response.output_data == {"reply": "안녕하세요"}


def test_strips_a_leading_think_block_before_parsing_json() -> None:
    """2026-09-17 실물 확인 회귀 시험.

    컴퓨터 재부팅 뒤 LM Studio가 같은 모델을 다시 올리면서 <think> 추론
    블록을 걸러내지 않게 됐고, 그 상태에서 화면의 실제 유진 채팅이 전부
    "invalid_json"으로 죽는 것을 curl로 직접 확인했다(LM Studio가 실제로
    보낸 원문 그대로를 아래 fixture에 옮겨 썼다). LM Studio 쪽 설정에
    기대지 않고 여기서 직접 걷어내 항상 통하게 한다.
    """
    raw_content = (
        '<think>We need respond to user in Korean, JSON only.\n'
        'Multi-line reasoning here.\n</think>'
        '{"reply": "네, 그 내용으로 적용해 드릴게요."}'
    )
    provider = LocalQwenStructuredProvider(transport=_FakeTransport(raw_content))

    response = provider.complete_structured(_request())

    assert response.output_data == {"reply": "네, 그 내용으로 적용해 드릴게요."}


def test_still_raises_invalid_json_when_nothing_usable_survives_stripping() -> None:
    """추론 블록을 걷어내도 남는 게 JSON이 아니면 여전히 명확히 실패해야 한다."""
    provider = LocalQwenStructuredProvider(transport=_FakeTransport("<think>only reasoning, no answer</think>"))

    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete_structured(_request())

    assert exc_info.value.error_code == "invalid_json"


def test_an_unclosed_think_tag_still_fails_clearly_instead_of_silently_guessing() -> None:
    """생성이 <think> 도중 잘리면 복구할 방법이 없다 -- 조용히 이상한 값을 만들지 않고 명확히 실패해야 한다."""
    provider = LocalQwenStructuredProvider(
        transport=_FakeTransport('<think>reasoning that got cut off mid-sentence and never clos')
    )

    with pytest.raises(LLMProviderError) as exc_info:
        provider.complete_structured(_request())

    assert exc_info.value.error_code == "invalid_json"
