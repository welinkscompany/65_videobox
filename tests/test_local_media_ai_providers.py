from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import socket
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from videobox_api.main import create_app
import videobox_api.main as api_main
from videobox_api.orchestration import LocalOnlyRuntimeService
from videobox_core_engine.local_only_runtime import (
    LocalOnlyStructuredGenerationError,
    LocalOnlyStructuredRuntime,
)
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.lm_studio import (
    LMStudioCapabilityProfile,
    LMStudioEmbeddingProvider,
    LMStudioHTTPTransport,
    LMStudioProviderError,
    LMStudioVisionProvider,
)
from videobox_provider_interfaces.vision import FIXED_VISION_LAYERS, VisionAnalysisRequest


SCHEMA = {
    "type": "object",
    "required": ["summary"],
    "properties": {"summary": {"type": "string"}},
}


class FakeLMStudioClient:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def __call__(self, request: object, *, timeout: int, allow_redirects: bool = False) -> object:
        assert allow_redirects is False
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        raw = __import__("json").dumps(result).encode("utf-8")
        return _FakeHTTPResponse(raw)


class _FakeHTTPResponse:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def read(self) -> bytes:
        return self.raw

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _loaded_models(*, capabilities: list[str]) -> dict[str, object]:
    return {"data": [{"id": "local-media", "loaded": True, "native_capabilities": capabilities}]}


VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["layers", "summary", "confidence", "review_reasons"],
    "properties": {
        "layers": {"type": "object"},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "review_reasons": {"type": "array", "items": {"type": "string"}},
    },
}


def _valid_vision_response() -> dict[str, object]:
    return {
        "choices": [{"message": {"content": __import__("json").dumps({
            "layers": {name: [] for name in FIXED_VISION_LAYERS},
            "summary": "ok",
            "confidence": 1,
            "review_reasons": [],
        })}}],
    }


def _image_bytes() -> bytes:
    from io import BytesIO
    from PIL import Image
    buffer = BytesIO()
    Image.new("RGB", (16, 8), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def test_lm_studio_preflight_selects_loaded_native_capability_profile() -> None:
    client = FakeLMStudioClient([_loaded_models(capabilities=["vision", "structured_json", "embedding"])])
    transport = LMStudioHTTPTransport(http_client=client)

    assert transport.preflight(model_name="local-media", capability="vision") == "vision"
    assert len(client.requests) == 1


def test_lm_studio_transport_records_only_exact_validated_requested_endpoints() -> None:
    client = FakeLMStudioClient([_loaded_models(capabilities=["embedding"])])
    transport = LMStudioHTTPTransport(http_client=client)

    transport.preflight(model_name="local-media", capability="embedding")

    assert transport.requested_endpoints == ["http://127.0.0.1:1234/v1/models"]


def test_lm_studio_preflight_blocks_unloaded_or_missing_model() -> None:
    client = FakeLMStudioClient([{"data": [{"id": "local-media", "loaded": False, "native_capabilities": ["vision"]}]}])

    with pytest.raises(LMStudioProviderError, match="unavailable") as captured:
        LMStudioHTTPTransport(http_client=client).preflight(model_name="local-media", capability="vision")

    assert captured.value.code == "blocked"


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_embedding_provider_rejects_non_finite_vectors(non_finite: float) -> None:
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["embedding"]),
        {"data": [{"embedding": [non_finite]}]},
    ])

    with pytest.raises(LMStudioProviderError, match="finite") as captured:
        LMStudioEmbeddingProvider(transport=LMStudioHTTPTransport(http_client=client)).embed(
            EmbeddingRequest(model_name="local-media", inputs=("local summary",))
        )

    assert captured.value.code == "failed"


def test_vision_provider_limits_prepared_images_and_requires_fixed_schema() -> None:
    image = _image_bytes()
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        _valid_vision_response(),
    ])
    provider = LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client))

    response = provider.analyze_images(VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(image,) * 7, response_schema=VISION_RESPONSE_SCHEMA))

    assert response.output_data["summary"] == "ok"
    payload = __import__("json").loads(client.requests[1].data.decode("utf-8"))
    assert len(payload["messages"][0]["content"]) == 7  # text plus at most six images
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"] != VISION_RESPONSE_SCHEMA
    assert provider.timeout_seconds == 120


def test_vision_provider_rejects_arbitrary_or_malformed_structured_output() -> None:
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        {"choices": [{"message": {"content": '{"layers":{},"summary":"ok","confidence":1,"review_reasons":[],"extra":true}'}}]},
    ])

    with pytest.raises(LMStudioProviderError) as captured:
        LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
            VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=VISION_RESPONSE_SCHEMA)
        )

    assert captured.value.code == "failed"


def test_vision_provider_rejects_undecodable_oversized_bytes() -> None:
    client = FakeLMStudioClient([_loaded_models(capabilities=["vision", "structured_json"])])
    provider = LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client))

    with pytest.raises(LMStudioProviderError, match="decodable") as captured:
        provider.analyze_images(
            VisionAnalysisRequest(
                model_name="local-media",
                prompt="describe",
                images=(b"x" * (int(1.5 * 1024 * 1024) + 1),), response_schema=VISION_RESPONSE_SCHEMA,
            )
        )

    assert captured.value.code == "failed"


def test_embedding_provider_uses_embedding_profile_and_timeout() -> None:
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["embedding"]),
        {"data": [{"embedding": [0.1, 0.2]}]},
    ])
    provider = LMStudioEmbeddingProvider(transport=LMStudioHTTPTransport(http_client=client))

    response = provider.embed(EmbeddingRequest(model_name="local-media", inputs=("hello",)))

    assert response.vectors == ((0.1, 0.2),)
    assert provider.timeout_seconds == 15


def test_transport_revalidates_endpoint_and_disallows_redirects_per_request() -> None:
    client = FakeLMStudioClient([_loaded_models(capabilities=["embedding"]), _loaded_models(capabilities=["embedding"])])
    transport = LMStudioHTTPTransport(http_client=client)
    transport.preflight(model_name="local-media", capability="embedding")
    transport.base_url = "http://127.0.0.1:9999/v1"

    with pytest.raises(LMStudioProviderError, match="loopback"):
        transport.preflight(model_name="local-media", capability="embedding")


def test_transport_maps_redirect_response_to_blocked_without_following_it() -> None:
    redirect = HTTPError("http://127.0.0.1:1234/v1/models", 302, "Found", {}, None)
    transport = LMStudioHTTPTransport(http_client=FakeLMStudioClient([redirect]))

    with pytest.raises(LMStudioProviderError) as captured:
        transport.preflight(model_name="local-media", capability="embedding")

    assert captured.value.code == "blocked"


def test_vision_provider_resizes_real_images_to_a_768_pixel_long_edge() -> None:
    from io import BytesIO
    from PIL import Image

    original = BytesIO()
    Image.new("RGB", (1200, 400), "red").save(original, format="PNG")
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        _valid_vision_response(),
    ])
    provider = LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client))

    provider.analyze_images(VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(original.getvalue(),), response_schema=VISION_RESPONSE_SCHEMA))

    payload = __import__("json").loads(client.requests[1].data.decode("utf-8"))
    data_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    resized = Image.open(BytesIO(__import__("base64").b64decode(data_url.split(",", 1)[1])))
    assert max(resized.size) == 768


def test_vision_requires_exactly_thirteen_nonempty_named_layers() -> None:
    assert len(FIXED_VISION_LAYERS) == 13
    layers = {name: [] for name in FIXED_VISION_LAYERS}
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        {"choices": [{"message": {"content": __import__("json").dumps({"layers": layers, "summary": "ok", "confidence": 1, "review_reasons": []})}}]},
    ])

    result = LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
        VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=VISION_RESPONSE_SCHEMA)
    )
    assert set(result.output_data["layers"]) == set(FIXED_VISION_LAYERS)


def test_vision_rejects_empty_or_string_layers() -> None:
    for layers in ({}, "not-a-layer-map"):
        client = FakeLMStudioClient([
            _loaded_models(capabilities=["vision", "structured_json"]),
            {"choices": [{"message": {"content": __import__("json").dumps({"layers": layers, "summary": "ok", "confidence": 1, "review_reasons": []})}}]},
        ])
        with pytest.raises(LMStudioProviderError, match="fixed schema"):
            LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
                VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=VISION_RESPONSE_SCHEMA)
            )


def test_vision_rejects_non_string_layer_items() -> None:
    layers = {name: [] for name in FIXED_VISION_LAYERS}
    layers["place"] = ["studio", 7]
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        {"choices": [{"message": {"content": __import__("json").dumps({"layers": layers, "summary": "ok", "confidence": 1, "review_reasons": []})}}]},
    ])

    with pytest.raises(LMStudioProviderError, match="fixed schema"):
        LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
            VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=VISION_RESPONSE_SCHEMA)
        )


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf")])
def test_vision_rejects_non_finite_confidence(confidence: float) -> None:
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        {"choices": [{"message": {"content": __import__("json").dumps({"layers": {name: [] for name in FIXED_VISION_LAYERS}, "summary": "ok", "confidence": confidence, "review_reasons": []})}}]},
    ])

    with pytest.raises(LMStudioProviderError, match="fixed schema"):
        LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
            VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=VISION_RESPONSE_SCHEMA)
        )


def test_vision_uses_the_exact_fixed_layer_taxonomy_and_never_caller_schema() -> None:
    assert FIXED_VISION_LAYERS == (
        "place", "action", "time_of_day", "weather", "people_objects", "emotion",
        "mood", "topic_links", "scene", "color_tone", "camera", "season", "country_region",
    )
    generic_schema = {"type": "object", "properties": {"untrusted": {"type": "string"}}}
    client = FakeLMStudioClient([
        _loaded_models(capabilities=["vision", "structured_json"]),
        _valid_vision_response(),
    ])

    LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
        VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(_image_bytes(),), response_schema=generic_schema)
    )

    payload = __import__("json").loads(client.requests[1].data.decode("utf-8"))
    schema = payload["response_format"]["json_schema"]["schema"]
    assert "untrusted" not in schema["properties"]
    assert schema["properties"]["layers"]["required"] == list(FIXED_VISION_LAYERS)


def test_vision_rejects_undecodable_image_bytes() -> None:
    client = FakeLMStudioClient([_loaded_models(capabilities=["vision", "structured_json"])])
    with pytest.raises(LMStudioProviderError, match="decodable") as captured:
        LMStudioVisionProvider(transport=LMStudioHTTPTransport(http_client=client)).analyze_images(
            VisionAnalysisRequest(model_name="local-media", prompt="describe", images=(b"not an image",), response_schema=VISION_RESPONSE_SCHEMA)
        )
    assert captured.value.code == "failed"


def test_capability_profile_selects_only_loaded_native_models() -> None:
    payload = {"data": [
        {"id": "vision", "loaded": True, "native_capabilities": ["vision", "structured_json"]},
        {"id": "text", "loaded": True, "native_capabilities": ["text", "structured_json"]},
        {"id": "embed", "loaded": True, "native_capabilities": ["embedding"]},
        {"id": "fake", "loaded": True, "capabilities": ["vision", "embedding", "text", "structured_json"]},
    ]}
    profile = LMStudioHTTPTransport(http_client=FakeLMStudioClient([payload])).capability_profile()

    assert profile == LMStudioCapabilityProfile(vision_model_name="vision", text_model_name="text", embedding_model_name="embed", structured_json=True)


def test_native_capability_is_required_and_arbitrary_capabilities_are_ignored() -> None:
    client = FakeLMStudioClient([{"data": [{"id": "local-media", "loaded": True, "capabilities": ["vision"]}]}])
    with pytest.raises(LMStudioProviderError) as captured:
        LMStudioHTTPTransport(http_client=client).preflight(model_name="local-media", capability="vision")
    assert captured.value.code == "blocked"


@dataclass
class FakeLocalProvider:
    response: StructuredLLMResponse | None = None
    error: Exception | None = None
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@dataclass
class ForbiddenExternalProvider:
    calls: list[object] = field(default_factory=list)

    def complete_structured(self, request: object) -> object:
        self.calls.append(request)
        raise AssertionError("Automatic runtime must not invoke an external provider.")


def test_local_runtime_config_rejects_every_non_lm_studio_endpoint() -> None:
    for base_url in (
        "https://api.example.com/v1",
        "http://127.0.0.1:1234/v1/extra",
        "http://127.0.0.1:1234/v1/",
        "http://localhost:1234/v1",
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:1234/v2",
        "http://127.0.0.1:1234/v1?token=unexpected",
    ):
        with pytest.raises(ValueError, match=r"127\.0\.0\.1:1234"):
            LocalOpenAICompatibleRuntimeConfig(base_url=base_url)


def test_local_only_runtime_raises_without_external_fallback_on_local_failure() -> None:
    local_provider = FakeLocalProvider(
        error=LLMProviderError(
            provider_name="local_qwen",
            message="local model unavailable",
            retryable=True,
            error_code="LOCAL_UNAVAILABLE",
        )
    )
    forbidden_external_provider = ForbiddenExternalProvider()
    runtime = LocalOnlyStructuredRuntime(local_provider=local_provider)
    assert not hasattr(runtime, "gemini_provider")

    with pytest.raises(LocalOnlyStructuredGenerationError, match="local model unavailable"):
        runtime.generate(
            project_id="project_001",
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="Summarize this segment.",
            response_schema=SCHEMA,
        )

    assert len(local_provider.calls) == 1
    assert forbidden_external_provider.calls == []


def test_local_only_runtime_marks_success_trace_as_local_only() -> None:
    runtime = LocalOnlyStructuredRuntime(
        local_provider=FakeLocalProvider(
            response=StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen3-35b",
                output_data={"summary": "local-only"},
                raw_text='{"summary":"local-only"}',
                metadata={},
            )
        )
    )

    response = runtime.generate(
        project_id="project_001",
        task_type=LLMTaskType.OPERATOR_COPY,
        prompt="Summarize this segment.",
        response_schema=SCHEMA,
    )

    assert response.metadata["provider_trace"]["routing_mode"] == "local_only"


def test_local_only_service_preserves_local_failure_trace() -> None:
    service = LocalOnlyRuntimeService(
        local_provider=FakeLocalProvider(
            error=LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                error_code="LOCAL_UNAVAILABLE",
            )
        )
    )

    with pytest.raises(LLMProviderError) as captured:
        service.generate_structured(
            project_id="project_001",
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="Summarize this segment.",
            response_schema=SCHEMA,
        )

    assert captured.value.provider_trace == {
        "routing_mode": "local_only",
        "final_provider": "local_qwen",
        "fallback_reasons": ["local_provider_error"],
    }


def test_create_app_uses_injected_local_runtime_without_external_provider_calls(tmp_path: Path) -> None:
    local_provider = FakeLocalProvider(
        response=StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="qwen3-35b",
            output_data={"summary": "local-only"},
            raw_text='{"summary":"local-only"}',
            metadata={},
        )
    )
    forbidden_external_provider = ForbiddenExternalProvider()
    factory_calls: list[Path] = []
    runtime_service: LocalOnlyStructuredRuntime | None = None

    def local_runtime_factory(project_store: object) -> LocalOnlyStructuredRuntime:
        nonlocal runtime_service
        factory_calls.append(project_store.projects_root)
        runtime_service = LocalOnlyStructuredRuntime(local_provider=local_provider)
        return runtime_service

    app = create_app(
        projects_root=tmp_path,
        local_only_runtime_service_factory=local_runtime_factory,
    )

    assert runtime_service is not None
    response = runtime_service.generate(
        project_id="project_001",
        task_type=LLMTaskType.OPERATOR_COPY,
        prompt="Summarize this segment.",
        response_schema=SCHEMA,
    )

    assert response.output_data == {"summary": "local-only"}
    assert factory_calls == [tmp_path]
    assert len(local_provider.calls) == 1
    assert forbidden_external_provider.calls == []


def test_create_app_default_wiring_constructs_only_local_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_provider = FakeLocalProvider(
        response=StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="qwen3-35b",
            output_data={"summary": "local-only"},
            raw_text='{"summary":"local-only"}',
            metadata={},
        )
    )
    forbidden_external_provider = ForbiddenExternalProvider()
    builder_calls: list[Path] = []

    def forbidden_gemini_constructor(*args: object, **kwargs: object) -> object:
        forbidden_external_provider.calls.append((args, kwargs))
        raise AssertionError("create_app must not construct a Gemini provider.")

    def build_fake_local_service(**kwargs: object) -> LocalOnlyRuntimeService:
        builder_calls.append(kwargs["store"].projects_root)
        return LocalOnlyRuntimeService(local_provider=local_provider)

    monkeypatch.setattr(api_main, "build_local_only_runtime_service", build_fake_local_service)
    monkeypatch.setattr(
        api_main,
        "GeminiRESTStructuredProvider",
        forbidden_gemini_constructor,
        raising=False,
    )
    create_app(projects_root=tmp_path)

    assert builder_calls == [tmp_path]
    assert forbidden_external_provider.calls == []


def test_network_guard_blocks_non_lm_studio_destinations() -> None:
    with pytest.raises(AssertionError, match="network connections"):
        socket.create_connection(("8.8.8.8", 53))

    with socket.socket() as client:
        with pytest.raises(AssertionError, match="network connections"):
            client.connect(("example.com", 443))

    with socket.socket() as client:
        with pytest.raises(AssertionError, match="network connections"):
            client.connect_ex(("example.com", 443))


def test_network_guard_blocks_arbitrary_loopback_even_with_socketpair_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conftest

    monkeypatch.setattr(
        conftest.inspect,
        "stack",
        lambda: [SimpleNamespace(function="_fallback_socketpair", filename="C:/Python/socket.py")],
    )

    with socket.socket() as client:
        with pytest.raises(AssertionError, match="network connections"):
            client.connect(("127.0.0.1", 54321))


def test_network_guard_consumes_socketpair_listener_port_after_one_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import conftest

    monkeypatch.setattr(
        conftest.inspect,
        "stack",
        lambda: [SimpleNamespace(function="_fallback_socketpair", filename="C:/Python/socket.py")],
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener_port = listener.getsockname()[1]

    with socket.socket() as first_client:
        with pytest.raises(ConnectionRefusedError):
            first_client.connect(("127.0.0.1", listener_port))

    with socket.socket() as reused_client:
        with pytest.raises(AssertionError, match="network connections"):
            reused_client.connect(("127.0.0.1", listener_port))
