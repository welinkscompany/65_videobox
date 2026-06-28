from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from videobox_core_engine.gemini_runtime import (
    GeminiStructuredGenerationError,
    GeminiStructuredRuntime,
)
from videobox_api.orchestration import GeminiRuntimeService
from videobox_provider_interfaces.gemini import GeminiRESTStructuredProvider
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


def _create_store(tmp_path: Path) -> tuple[LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Gemini Runtime Project")
    return store, project.project_id


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
