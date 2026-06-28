from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from videobox_core_engine.gemini_runtime import (
    GeminiStructuredGenerationError,
    GeminiStructuredRuntime,
)
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError, LocalFirstStructuredRuntime
from videobox_api import orchestration as orchestration_module
from videobox_api.orchestration import GeminiRuntimeService, LocalFirstRuntimeService
from videobox_core_engine import settings as settings_module
from videobox_provider_interfaces.gemini import GeminiHTTPTransport, GeminiRESTStructuredProvider
from videobox_provider_interfaces.local_qwen import LocalQwenHTTPTransport, LocalQwenStructuredProvider
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from videobox_storage.local_project_store import LocalProjectStore


@dataclass
class RecordingGeminiTransport:
    response_payload: dict[str, Any] | None = None
    error: LLMProviderError | None = None
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def generate_content(self, *, model_name: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((model_name, api_key, payload))
        if self.error is not None:
            raise self.error
        assert self.response_payload is not None
        return self.response_payload


@dataclass
class FakeStructuredProvider:
    responses_by_key: dict[str, list[StructuredLLMResponse]] = field(default_factory=dict)
    errors_by_key: dict[str, list[Exception]] = field(default_factory=dict)
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        key_id = str(request.provider_context["gemini_key_id"])
        if self.errors_by_key.get(key_id):
            raise self.errors_by_key[key_id].pop(0)
        if self.responses_by_key.get(key_id):
            return self.responses_by_key[key_id].pop(0)
        raise AssertionError(f"No fake structured response configured for {key_id}")


@dataclass
class FakeLocalStructuredProvider:
    responses: list[StructuredLLMResponse] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        raise AssertionError("No fake local structured response configured.")


@dataclass
class FakeHTTPResponse:
    status: int
    payload: dict[str, Any]

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


@dataclass
class RecordingHTTPClient:
    response: FakeHTTPResponse | None = None
    error: HTTPError | None = None
    calls: list[Request] = field(default_factory=list)

    def __call__(self, request: Request, timeout: int) -> FakeHTTPResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _create_store(tmp_path: Path) -> tuple[LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Gemini Runtime Project")
    return store, project.project_id


def _local_runtime_config(
    *,
    enabled: bool = True,
    base_url: str = "http://127.0.0.1:1234/v1",
    model_name: str = "qwen3-35b",
    timeout_seconds: int = 30,
) -> Any:
    return settings_module.LocalOpenAICompatibleRuntimeConfig(
        enabled=enabled,
        base_url=base_url,
        model_name=model_name,
        timeout_seconds=timeout_seconds,
    )


def test_gemini_rest_structured_provider_builds_generate_content_payload_and_parses_json() -> None:
    transport = RecordingGeminiTransport(
        response_payload={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"summary":"Office overview","keywords":["office","team"]}'
                            }
                        ]
                    }
                }
            ]
        }
    )
    provider = GeminiRESTStructuredProvider(transport=transport)

    response = provider.complete_structured(
        StructuredLLMRequest(
            task_type=LLMTaskType.KEYWORD_EXPANSION,
            prompt="Extract keywords.",
            response_schema={
                "type": "object",
                "required": ["summary", "keywords"],
                "properties": {
                    "summary": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
            },
            provider_context={
                "model_name": "gemini-2.5-flash",
                "api_key_secret": "AIzaSECRET9999",
                "gemini_key_id": "gemini_key_001",
            },
        )
    )

    assert response.output_data == {
        "summary": "Office overview",
        "keywords": ["office", "team"],
    }
    assert response.model_name == "gemini-2.5-flash"
    assert transport.calls[0][0] == "gemini-2.5-flash"
    assert transport.calls[0][1] == "AIzaSECRET9999"
    assert transport.calls[0][2]["generationConfig"]["responseMimeType"] == "application/json"
    assert transport.calls[0][2]["generationConfig"]["responseSchema"]["required"] == [
        "summary",
        "keywords",
    ]


def test_gemini_runtime_falls_back_to_next_key_and_persists_cooldown_state(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 15, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    first_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Primary Gemini",
        api_key_secret="AIzaSECRET1111",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    second_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaSECRET2222",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    provider = FakeStructuredProvider(
        errors_by_key={
            first_key["key_id"]: [
                LLMProviderError(
                    provider_name="gemini",
                    message="Quota exhausted",
                    retryable=True,
                    error_code="RESOURCE_EXHAUSTED",
                    occurred_at=now,
                )
            ]
        },
        responses_by_key={
            second_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash-lite",
                    output_data={"keywords": ["office", "team"]},
                    raw_text='{"keywords":["office","team"]}',
                    metadata={},
                )
            ]
        },
    )
    runtime = GeminiStructuredRuntime(
        store=store,
        provider=provider,
        provider_config=LLMProviderConfig(provider_name="gemini", enabled=True),
        cooldown_seconds=180,
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Extract B-roll keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
        },
        now=now,
    )

    assert response.output_data["keywords"] == ["office", "team"]
    assert [call.provider_context["gemini_key_id"] for call in provider.calls] == [
        first_key["key_id"],
        second_key["key_id"],
    ]
    first_state = store.get_gemini_provider_key(project_id=project_id, key_id=first_key["key_id"])
    second_state = store.get_gemini_provider_key(project_id=project_id, key_id=second_key["key_id"])
    assert first_state["status"] == "cooldown"
    assert first_state["consecutive_failures"] == 1
    assert first_state["cooldown_until"] == (now + timedelta(seconds=180)).isoformat()
    assert first_state["last_used_at"] == now.isoformat()
    assert "AIzaSECRET1111" not in str(first_state["last_error"])
    assert second_state["status"] == "active"
    assert second_state["consecutive_failures"] == 0
    assert second_state["last_used_at"] == now.isoformat()


def test_gemini_runtime_skips_disabled_and_invalid_keys_and_reactivates_expired_cooldown_key(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 28, 16, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    cooldown_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Cooldown Gemini",
        api_key_secret="AIzaSECRET3333",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    disabled_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Disabled Gemini",
        api_key_secret="AIzaSECRET4444",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    invalid_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Invalid Gemini",
        api_key_secret="AIzaSECRET5555",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    store.update_gemini_provider_key_runtime_state(
        project_id=project_id,
        key_id=cooldown_key["key_id"],
        status="cooldown",
        cooldown_until=(now - timedelta(seconds=5)).isoformat(),
        consecutive_failures=1,
        last_error="transient",
        last_used_at=(now - timedelta(minutes=1)).isoformat(),
    )
    store.set_gemini_provider_key_status(
        project_id=project_id,
        key_id=disabled_key["key_id"],
        status="disabled",
    )
    store.update_gemini_provider_key_runtime_state(
        project_id=project_id,
        key_id=invalid_key["key_id"],
        status="invalid",
        cooldown_until=None,
        consecutive_failures=2,
        last_error="auth",
        last_used_at=(now - timedelta(minutes=2)).isoformat(),
    )

    provider = FakeStructuredProvider(
        responses_by_key={
            cooldown_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash",
                    output_data={"decision": "use_broll"},
                    raw_text='{"decision":"use_broll"}',
                    metadata={},
                )
            ]
        }
    )
    runtime = GeminiStructuredRuntime(
        store=store,
        provider=provider,
        provider_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.SCENE_PLANNING,
        prompt="Classify this segment.",
        response_schema={
            "type": "object",
            "required": ["decision"],
            "properties": {"decision": {"type": "string"}},
        },
        now=now,
    )

    assert response.output_data["decision"] == "use_broll"
    assert [call.provider_context["gemini_key_id"] for call in provider.calls] == [cooldown_key["key_id"]]
    assert store.get_gemini_provider_key(project_id=project_id, key_id=cooldown_key["key_id"])[
        "status"
    ] == "active"


def test_gemini_runtime_raises_secret_safe_error_when_all_keys_fail(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 17, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Only Gemini",
        api_key_secret="AIzaVERYSECRET0000",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    provider = FakeStructuredProvider(
        responses_by_key={
            key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash",
                    output_data={"wrong_field": True},
                    raw_text='{"wrong_field":true}',
                    metadata={},
                )
            ]
        }
    )
    runtime = GeminiStructuredRuntime(
        store=store,
        provider=provider,
        provider_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    try:
        runtime.generate(
            project_id=project_id,
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="Return operator summary.",
            response_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            now=now,
        )
    except GeminiStructuredGenerationError as exc:
        assert exc.error_code == "structured_output_invalid"
        assert "AIzaVERYSECRET0000" not in str(exc)
        assert "structured response validation failed" in str(exc).lower()
    else:
        raise AssertionError("Expected a secret-safe Gemini runtime error.")

    failed_state = store.get_gemini_provider_key(project_id=project_id, key_id=key["key_id"])
    assert failed_state["consecutive_failures"] == 1
    assert failed_state["last_used_at"] == now.isoformat()


def test_gemini_runtime_service_exposes_project_scoped_backend_entrypoint(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 18, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Service Gemini",
        api_key_secret="AIzaSERVICE1234",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    provider = FakeStructuredProvider(
        responses_by_key={
            key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash",
                    output_data={"summary": "segment ready"},
                    raw_text='{"summary":"segment ready"}',
                    metadata={},
                )
            ]
        }
    )
    service = GeminiRuntimeService(
        store=store,
        provider=provider,
        provider_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = service.generate_structured(
        project_id=project_id,
        task_type=LLMTaskType.OPERATOR_COPY,
        prompt="Summarize this segment.",
        response_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        now=now,
    )

    assert response.output_data == {"summary": "segment ready"}
    assert provider.calls[0].provider_context["gemini_key_id"] == key["key_id"]


def test_gemini_http_transport_posts_generate_content_request() -> None:
    client = RecordingHTTPClient(
        response=FakeHTTPResponse(
            status=200,
            payload={"candidates": [{"content": {"parts": [{"text": "{\"ok\":true}"}]}}]},
        )
    )
    transport = GeminiHTTPTransport(http_client=client, timeout_seconds=12)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    response = transport.generate_content(
        model_name="gemini-2.5-flash",
        api_key="AIzaHTTPSECRET0001",
        payload=payload,
    )

    assert response["candidates"][0]["content"]["parts"][0]["text"] == "{\"ok\":true}"
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request.full_url.endswith(
        "/models/gemini-2.5-flash:generateContent?key=AIzaHTTPSECRET0001"
    )
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data.decode("utf-8")) == payload


def test_gemini_http_transport_maps_http_errors_to_safe_provider_errors() -> None:
    error_body = {
        "error": {
            "code": 429,
            "message": "Quota exhausted for key AIzaERRORSECRET0002",
            "status": "RESOURCE_EXHAUSTED",
        }
    }
    client = RecordingHTTPClient(
        error=HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=BytesIO(json.dumps(error_body).encode("utf-8")),
        )
    )
    transport = GeminiHTTPTransport(http_client=client, timeout_seconds=30)

    try:
        transport.generate_content(
            model_name="gemini-2.5-flash",
            api_key="AIzaERRORSECRET0002",
            payload={"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
        )
    except LLMProviderError as exc:
        assert exc.provider_name == "gemini"
        assert exc.error_code == "RESOURCE_EXHAUSTED"
        assert exc.retryable is True
        assert "AIzaERRORSECRET0002" not in str(exc)
        assert "Quota exhausted" in str(exc)
    else:
        raise AssertionError("Expected GeminiHTTPTransport to normalize the HTTP error.")


def test_gemini_runtime_validates_input_prompt_and_schema_before_execution(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 19, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    store.save_gemini_provider_key(
        project_id=project_id,
        label="Validation Gemini",
        api_key_secret="AIzaVALIDATE0003",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    provider = FakeStructuredProvider()
    runtime = GeminiStructuredRuntime(
        store=store,
        provider=provider,
        provider_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    try:
        runtime.generate(
            project_id=project_id,
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="   ",
            response_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            now=now,
        )
    except GeminiStructuredGenerationError as exc:
        assert exc.error_code == "invalid_request"
        assert "prompt" in str(exc).lower()
    else:
        raise AssertionError("Expected blank prompts to be rejected before provider execution.")

    try:
        runtime.generate(
            project_id=project_id,
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="Summarize this segment.",
            response_schema={"type": "array"},
            now=now,
        )
    except GeminiStructuredGenerationError as exc:
        assert exc.error_code == "invalid_request"
        assert "schema" in str(exc).lower()
    else:
        raise AssertionError("Expected invalid response schemas to be rejected before provider execution.")

    assert provider.calls == []


def test_gemini_http_transport_maps_auth_and_transient_errors() -> None:
    auth_client = RecordingHTTPClient(
        error=HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(
                json.dumps(
                    {
                        "error": {
                            "code": 403,
                            "message": "API key AIzaAUTHSECRET0004 is not valid.",
                            "status": "PERMISSION_DENIED",
                        }
                    }
                ).encode("utf-8")
            ),
        )
    )
    auth_transport = GeminiHTTPTransport(http_client=auth_client, timeout_seconds=30)

    try:
        auth_transport.generate_content(
            model_name="gemini-2.5-flash",
            api_key="AIzaAUTHSECRET0004",
            payload={"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
        )
    except LLMProviderError as exc:
        assert exc.error_code == "PERMISSION_DENIED"
        assert exc.retryable is False
        assert "AIzaAUTHSECRET0004" not in str(exc)
    else:
        raise AssertionError("Expected auth errors to be normalized.")

    transient_client = RecordingHTTPClient(
        error=HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=BytesIO(
                json.dumps(
                    {
                        "error": {
                            "code": 503,
                            "message": "Service temporarily unavailable.",
                            "status": "UNAVAILABLE",
                        }
                    }
                ).encode("utf-8")
            ),
        )
    )
    transient_transport = GeminiHTTPTransport(http_client=transient_client, timeout_seconds=30)

    try:
        transient_transport.generate_content(
            model_name="gemini-2.5-flash",
            api_key="AIzaTRANSIENT0005",
            payload={"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
        )
    except LLMProviderError as exc:
        assert exc.error_code == "UNAVAILABLE"
        assert exc.retryable is True
    else:
        raise AssertionError("Expected transient Gemini errors to be retryable.")


def test_local_first_runtime_returns_local_result_without_hitting_gemini(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 0, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaFALLBACK1001",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen3-35b",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider()
    runtime = LocalFirstStructuredRuntime(
        store=store,
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Expand keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
        now=now,
    )

    assert response.provider_name == "local_qwen"
    assert response.output_data == {"keywords": ["office", "desk"]}
    assert len(local_provider.calls) == 1
    assert local_provider.calls[0].provider_context["model_name"] == "qwen3-35b"
    assert gemini_provider.calls == []


def test_local_first_runtime_uses_configured_local_model_name(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 5, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaMODEL1001",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B-GGUF",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            )
        ]
    )
    runtime = LocalFirstStructuredRuntime(
        store=store,
        local_provider=local_provider,
        gemini_provider=FakeStructuredProvider(),
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
        local_runtime_config=_local_runtime_config(
            base_url="http://127.0.0.1:11434/v1",
            model_name="Qwen3-32B-GGUF",
            timeout_seconds=45,
        ),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Expand keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
        now=now,
    )

    assert response.provider_name == "local_qwen"
    assert local_provider.calls[0].provider_context["model_name"] == "Qwen3-32B-GGUF"


def test_local_first_runtime_falls_back_to_gemini_after_local_retryable_failure(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 15, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    gemini_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaFALLBACK2002",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local model timed out",
                retryable=True,
                error_code="LOCAL_TIMEOUT",
                occurred_at=now,
            )
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses_by_key={
            gemini_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash-lite",
                    output_data={"keywords": ["fallback", "broll"]},
                    raw_text='{"keywords":["fallback","broll"]}',
                    metadata={},
                )
            ]
        }
    )
    runtime = LocalFirstStructuredRuntime(
        store=store,
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Expand keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
        now=now,
    )

    assert response.provider_name == "gemini"
    assert len(local_provider.calls) == 1
    assert [call.provider_context["gemini_key_id"] for call in gemini_provider.calls] == [gemini_key["key_id"]]


def test_local_first_runtime_skips_disabled_local_provider_and_uses_gemini(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 20, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    gemini_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaDISABLED2002",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses_by_key={
            gemini_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash-lite",
                    output_data={"keywords": ["fallback", "gemini"]},
                    raw_text='{"keywords":["fallback","gemini"]}',
                    metadata={},
                )
            ]
        }
    )
    runtime = LocalFirstStructuredRuntime(
        store=store,
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=False),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
        local_runtime_config=_local_runtime_config(enabled=False),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Expand keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
        now=now,
    )

    assert response.provider_name == "gemini"
    assert local_provider.calls == []
    assert [call.provider_context["gemini_key_id"] for call in gemini_provider.calls] == [gemini_key["key_id"]]


def test_local_first_runtime_falls_back_to_gemini_when_local_returns_invalid_structure(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 30, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    gemini_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Fallback Gemini",
        api_key_secret="AIzaFALLBACK3003",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen3-35b",
                output_data={"wrong_field": True},
                raw_text='{"wrong_field":true}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses_by_key={
            gemini_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash",
                    output_data={"summary": "fallback summary"},
                    raw_text='{"summary":"fallback summary"}',
                    metadata={},
                )
            ]
        }
    )
    runtime = LocalFirstStructuredRuntime(
        store=store,
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = runtime.generate(
        project_id=project_id,
        task_type=LLMTaskType.OPERATOR_COPY,
        prompt="Summarize this segment.",
        response_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        now=now,
    )

    assert response.provider_name == "gemini"
    assert response.output_data == {"summary": "fallback summary"}
    assert len(local_provider.calls) == 1
    assert len(gemini_provider.calls) == 1


def test_local_first_runtime_service_exposes_local_then_gemini_backend_entrypoint(tmp_path: Path) -> None:
    now = datetime(2026, 6, 28, 20, 45, tzinfo=UTC)
    store, project_id = _create_store(tmp_path)
    gemini_key = store.save_gemini_provider_key(
        project_id=project_id,
        label="Service Fallback Gemini",
        api_key_secret="AIzaFALLBACK4004",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    local_provider = FakeLocalStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
                occurred_at=now,
            )
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses_by_key={
            gemini_key["key_id"]: [
                StructuredLLMResponse(
                    provider_name="gemini",
                    model_name="gemini-2.5-flash",
                    output_data={"decision": "use_broll"},
                    raw_text='{"decision":"use_broll"}',
                    metadata={},
                )
            ]
        }
    )
    service = LocalFirstRuntimeService(
        store=store,
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    response = service.generate_structured(
        project_id=project_id,
        task_type=LLMTaskType.SCENE_PLANNING,
        prompt="Classify this segment.",
        response_schema={
            "type": "object",
            "required": ["decision"],
            "properties": {"decision": {"type": "string"}},
        },
        now=now,
    )

    assert response.provider_name == "gemini"
    assert response.output_data == {"decision": "use_broll"}


def test_build_local_first_runtime_service_wires_configured_local_endpoint() -> None:
    service = orchestration_module.build_local_first_runtime_service(
        store=LocalProjectStore(Path("D:/tmp/videobox-runtime-builder")),
        gemini_provider=FakeStructuredProvider(),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
        local_runtime_config=_local_runtime_config(
            base_url="http://127.0.0.1:11434/v1",
            model_name="Qwen3-32B",
            timeout_seconds=42,
        ),
        local_http_client=RecordingHTTPClient(
            response=FakeHTTPResponse(
                status=200,
                payload={"choices": [{"message": {"content": '{"ok":true}'}}]},
            )
        ),
    )

    assert isinstance(service.local_provider, LocalQwenStructuredProvider)
    assert service.local_runtime_config.base_url == "http://127.0.0.1:11434/v1"
    assert service.local_runtime_config.model_name == "Qwen3-32B"
    assert service.local_runtime_config.timeout_seconds == 42
    assert service.local_config.enabled is True


def test_local_runtime_config_rejects_invalid_values() -> None:
    try:
        settings_module.LocalOpenAICompatibleRuntimeConfig(
            enabled=True,
            base_url=" ",
            model_name="qwen3-35b",
            timeout_seconds=30,
        )
    except ValueError as exc:
        assert "base_url" in str(exc)
    else:
        raise AssertionError("Expected blank local base_url to be rejected.")

    try:
        settings_module.LocalOpenAICompatibleRuntimeConfig(
            enabled=True,
            base_url="http://127.0.0.1:1234/v1",
            model_name="   ",
            timeout_seconds=30,
        )
    except ValueError as exc:
        assert "model_name" in str(exc)
    else:
        raise AssertionError("Expected blank local model_name to be rejected.")

    try:
        settings_module.LocalOpenAICompatibleRuntimeConfig(
            enabled=True,
            base_url="http://127.0.0.1:1234/v1",
            model_name="qwen3-35b",
            timeout_seconds=0,
        )
    except ValueError as exc:
        assert "timeout" in str(exc).lower()
    else:
        raise AssertionError("Expected non-positive local timeout to be rejected.")


def test_build_local_first_runtime_service_rejects_conflicting_local_config() -> None:
    try:
        orchestration_module.build_local_first_runtime_service(
            store=LocalProjectStore(Path("D:/tmp/videobox-runtime-builder-conflict")),
            gemini_provider=FakeStructuredProvider(),
            gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
            local_runtime_config=_local_runtime_config(
                enabled=True,
                base_url="http://127.0.0.1:11434/v1",
                model_name="Qwen3-32B",
                timeout_seconds=42,
            ),
            local_config=LLMProviderConfig(
                provider_name="local_qwen",
                enabled=False,
                timeout_seconds=30,
            ),
            local_http_client=RecordingHTTPClient(
                response=FakeHTTPResponse(
                    status=200,
                    payload={"choices": [{"message": {"content": '{"ok":true}'}}]},
                )
            ),
        )
    except ValueError as exc:
        assert "local_config" in str(exc)
    else:
        raise AssertionError("Expected conflicting local provider configuration to be rejected.")


def test_local_qwen_http_transport_normalizes_network_failures_for_invalid_endpoint() -> None:
    class FailingHTTPClient:
        def __call__(self, request: Request, timeout: int) -> FakeHTTPResponse:
            raise URLError("[Errno 111] Connection refused")

    transport = LocalQwenHTTPTransport(
        base_url="http://127.0.0.1:9999/v1",
        http_client=FailingHTTPClient(),
        timeout_seconds=10,
    )

    try:
        transport.complete_chat(
            model_name="qwen3-35b",
            prompt="Expand keywords.",
            response_schema={
                "type": "object",
                "required": ["keywords"],
                "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
            },
        )
    except LLMProviderError as exc:
        assert exc.provider_name == "local_qwen"
        assert exc.error_code == "LOCAL_NETWORK_ERROR"
        assert exc.retryable is True
        assert "network error" in str(exc).lower()
    else:
        raise AssertionError("Expected invalid local endpoint failures to normalize into LLMProviderError.")


def test_local_qwen_http_transport_posts_openai_compatible_request() -> None:
    client = RecordingHTTPClient(
        response=FakeHTTPResponse(
            status=200,
            payload={
                "choices": [
                    {
                        "message": {
                            "content": '{"keywords":["local","qwen"]}'
                        }
                    }
                ]
            },
        )
    )
    transport = LocalQwenHTTPTransport(
        base_url="http://127.0.0.1:1234/v1",
        http_client=client,
        timeout_seconds=15,
    )

    response = transport.complete_chat(
        model_name="qwen3-35b",
        prompt="Expand keywords.",
        response_schema={
            "type": "object",
            "required": ["keywords"],
            "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        },
    )

    assert response["choices"][0]["message"]["content"] == '{"keywords":["local","qwen"]}'
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request.full_url == "http://127.0.0.1:1234/v1/chat/completions"
    assert request.get_method() == "POST"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "qwen3-35b"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["messages"][0]["content"] == "Expand keywords."


def test_local_qwen_structured_provider_parses_json_and_normalizes_timeout() -> None:
    success_client = RecordingHTTPClient(
        response=FakeHTTPResponse(
            status=200,
            payload={
                "choices": [
                    {
                        "message": {
                            "content": '{"summary":"local summary"}'
                        }
                    }
                ]
            },
        )
    )
    provider = LocalQwenStructuredProvider(
        transport=LocalQwenHTTPTransport(
            base_url="http://127.0.0.1:1234/v1",
            http_client=success_client,
            timeout_seconds=20,
        )
    )

    response = provider.complete_structured(
        StructuredLLMRequest(
            task_type=LLMTaskType.OPERATOR_COPY,
            prompt="Summarize this segment.",
            response_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
            provider_context={"model_name": "qwen3-35b"},
        )
    )

    assert response.provider_name == "local_qwen"
    assert response.output_data == {"summary": "local summary"}

    class TimeoutHTTPClient:
        def __call__(self, request: Request, timeout: int) -> FakeHTTPResponse:
            raise TimeoutError("local timed out")

    timeout_provider = LocalQwenStructuredProvider(
        transport=LocalQwenHTTPTransport(
            base_url="http://127.0.0.1:1234/v1",
            http_client=TimeoutHTTPClient(),
            timeout_seconds=20,
        )
    )

    try:
        timeout_provider.complete_structured(
            StructuredLLMRequest(
                task_type=LLMTaskType.OPERATOR_COPY,
                prompt="Summarize this segment.",
                response_schema={
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                },
                provider_context={"model_name": "qwen3-35b"},
            )
        )
    except LLMProviderError as exc:
        assert exc.provider_name == "local_qwen"
        assert exc.error_code == "LOCAL_TIMEOUT"
        assert exc.retryable is True
    else:
        raise AssertionError("Expected local timeout to normalize into LLMProviderError.")


def test_local_qwen_structured_provider_rejects_malformed_json() -> None:
    client = RecordingHTTPClient(
        response=FakeHTTPResponse(
            status=200,
            payload={"choices": [{"message": {"content": "not-json"}}]},
        )
    )
    provider = LocalQwenStructuredProvider(
        transport=LocalQwenHTTPTransport(
            base_url="http://127.0.0.1:1234/v1",
            http_client=client,
            timeout_seconds=20,
        )
    )

    try:
        provider.complete_structured(
            StructuredLLMRequest(
                task_type=LLMTaskType.KEYWORD_EXPANSION,
                prompt="Expand keywords.",
                response_schema={
                    "type": "object",
                    "required": ["keywords"],
                    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
                },
                provider_context={"model_name": "qwen3-35b"},
            )
        )
    except LLMProviderError as exc:
        assert exc.provider_name == "local_qwen"
        assert exc.error_code == "invalid_json"
        assert exc.retryable is False
    else:
        raise AssertionError("Expected malformed local JSON to be rejected.")
