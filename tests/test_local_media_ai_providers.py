from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import socket
from types import SimpleNamespace

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


SCHEMA = {
    "type": "object",
    "required": ["summary"],
    "properties": {"summary": {"type": "string"}},
}


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
