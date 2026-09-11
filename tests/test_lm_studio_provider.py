from __future__ import annotations

import json


class _FakeHTTPResponse:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def read(self) -> bytes:
        return self.raw

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _FakeLMStudioClient:
    """`/api/v1/models`를 한 번 흉내 낸다. 실제 응답 모양(2026-09-11 실측):
    `{"models":[{"type":"llm","key":...,"capabilities":{"vision":true},
    "loaded_instances":[{"id":...}]}]}` -- 모양이 다르면 이 시험이 아무것도
    안 지킨다."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requests: list[object] = []

    def __call__(self, request: object, *, timeout: int, allow_redirects: bool = False) -> object:
        self.requests.append(request)
        return _FakeHTTPResponse(json.dumps(self.payload).encode("utf-8"))


def _models_payload(*models: dict[str, object]) -> dict[str, object]:
    return {"models": list(models)}


def _llm(model_id: str, *, vision: bool) -> dict[str, object]:
    return {
        "key": model_id,
        "type": "llm",
        "capabilities": {"vision": vision, "trained_for_tool_use": True},
        "loaded_instances": [{"id": model_id}],
    }


def _embedding(model_id: str) -> dict[str, object]:
    return {
        "key": model_id,
        "type": "embedding",
        "capabilities": None,
        "loaded_instances": [{"id": model_id}],
    }


def test_configured_model_is_loaded_and_vision_capable_so_it_is_chosen() -> None:
    """Case 1: 설정한 모델이 올라와 있고 비전이 된다 -> 목록에서 뒤에 있어도 그것을 쓴다."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport

    payload = _models_payload(
        _llm("old-model", vision=True),  # 목록 첫 번째 -- 옛 규칙이라면 이게 뽑힌다.
        _llm("qwen/qwen3.8-27b", vision=True),  # 설정한 모델. 뒤에 있다.
        _embedding("text-embedding-bge-m3"),
    )
    client = _FakeLMStudioClient(payload)
    transport = LMStudioHTTPTransport(http_client=client)

    profile = transport.capability_profile(configured_model_name="qwen/qwen3.8-27b")

    assert profile.vision_model_name == "qwen/qwen3.8-27b"
    assert profile.text_model_name == "qwen/qwen3.8-27b"
    assert profile.configured_model_name == "qwen/qwen3.8-27b"


def test_configured_model_is_loaded_but_not_vision_capable_so_it_falls_back_and_is_discoverable() -> None:
    """Case 2: 설정한 모델이 올라와 있는데 비전이 안 된다 -> 옛 규칙(첫 비전 모델)으로
    물러나고, `configured_model_name`과 `vision_model_name`이 달라서 그 사실이 드러난다."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport

    payload = _models_payload(
        _llm("vision-capable-model", vision=True),
        _llm("qwen/qwen3.8-27b", vision=False),  # 설정한 모델. 비전이 안 된다.
        _embedding("text-embedding-bge-m3"),
    )
    client = _FakeLMStudioClient(payload)
    transport = LMStudioHTTPTransport(http_client=client)

    profile = transport.capability_profile(configured_model_name="qwen/qwen3.8-27b")

    assert profile.vision_model_name == "vision-capable-model"  # 옛 규칙으로 물러났다.
    assert profile.configured_model_name == "qwen/qwen3.8-27b"
    # 설정한 모델과 실제로 쓴 비전 모델이 다르다는 사실이 여기서 드러난다.
    assert profile.vision_model_name != profile.configured_model_name
    # 텍스트는 설정한 모델이 llm이라 그대로 쓴다 (별도 정렬 대상).
    assert profile.text_model_name == "qwen/qwen3.8-27b"


def test_configured_model_is_not_loaded_at_all_so_it_falls_back_and_is_discoverable() -> None:
    """Case 3: 설정한 모델이 아예 안 올라와 있다 -> 옛 규칙으로 물러나고,
    `configured_model_name`이 로드된 모델 어디에도 없으므로 그 사실이 드러난다."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport

    payload = _models_payload(
        _llm("vision-capable-model", vision=True),
        _embedding("text-embedding-bge-m3"),
    )
    client = _FakeLMStudioClient(payload)
    transport = LMStudioHTTPTransport(http_client=client)

    profile = transport.capability_profile(configured_model_name="qwen/qwen3.8-27b")

    assert profile.vision_model_name == "vision-capable-model"
    assert profile.configured_model_name == "qwen/qwen3.8-27b"
    assert profile.vision_model_name != profile.configured_model_name


def test_embedding_selection_ignores_configured_model_name() -> None:
    """임베딩은 텍스트/비전과 다른 모델(`text-embedding-bge-m3`)이다. 설정 이름을
    거기 들이밀면 안 된다 -- 첫 번째 로드된 embedding 모델을 그대로 쓴다."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport

    payload = _models_payload(
        _llm("qwen/qwen3.8-27b", vision=True),
        _embedding("text-embedding-bge-m3"),
    )
    client = _FakeLMStudioClient(payload)
    transport = LMStudioHTTPTransport(http_client=client)

    profile = transport.capability_profile(configured_model_name="qwen/qwen3.8-27b")

    assert profile.embedding_model_name == "text-embedding-bge-m3"


def test_no_configured_model_name_keeps_the_first_loaded_rule() -> None:
    """`configured_model_name`을 안 넘기면(기존 호출자) 옛 규칙 그대로 -- 회귀 없음."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport

    payload = _models_payload(
        _llm("old-model", vision=True),
        _llm("new-model", vision=True),
    )
    client = _FakeLMStudioClient(payload)
    transport = LMStudioHTTPTransport(http_client=client)

    profile = transport.capability_profile()

    assert profile.vision_model_name == "old-model"
    assert profile.configured_model_name is None


def test_a_timeout_is_classified_separately_from_a_hard_block() -> None:
    """Task 29: the transport collapsed every transport-level failure into
    'blocked', which the analysis worker treats as terminal. A timeout is
    transient -- LM Studio was busy -- and must stay distinguishable so it can
    be retried instead of stranding the asset."""
    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport, LMStudioProviderError

    def timing_out(_request, **_kwargs):
        raise TimeoutError("timed out")

    transport = LMStudioHTTPTransport(http_client=timing_out)
    try:
        transport.request_json("/chat/completions", {"model": "m"}, timeout_seconds=1)
    except LMStudioProviderError as exc:
        assert exc.code == "timeout", exc.code
    else:
        raise AssertionError("a timeout must raise LMStudioProviderError")


def test_a_connection_failure_still_reports_blocked() -> None:
    from urllib.error import URLError

    from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport, LMStudioProviderError

    def refused(_request, **_kwargs):
        raise URLError("connection refused")

    transport = LMStudioHTTPTransport(http_client=refused)
    try:
        transport.request_json("/chat/completions", {"model": "m"}, timeout_seconds=1)
    except LMStudioProviderError as exc:
        assert exc.code == "blocked", exc.code
    else:
        raise AssertionError("a refused connection must raise LMStudioProviderError")
