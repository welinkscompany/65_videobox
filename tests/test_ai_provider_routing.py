from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from videobox_core_engine.ai_routing import LLMTaskRouter
from videobox_domain_models.ai_providers import GeminiApiKeyPool, GeminiKeyStatus
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTaskType,
)
from videobox_provider_interfaces.visual_generation import (
    VisualGenerationProvider,
    VisualGenerationRequest,
    VisualGenerationResponse,
)


@dataclass
class FakeLLMProvider:
    provider_name: str
    supported_tasks: set[LLMTaskType]
    responses: list[LLMResponse] = field(default_factory=list)
    errors: list[LLMProviderError] = field(default_factory=list)
    calls: list[LLMRequest] = field(default_factory=list)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        return LLMResponse(
            provider_name=self.provider_name,
            model_name="default-model",
            output_text=f"{self.provider_name}:{request.task_type.value}",
            metadata={},
        )


@dataclass
class FakeVisualProvider:
    provider_name: str = "comfyui"
    calls: list[VisualGenerationRequest] = field(default_factory=list)

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResponse:
        self.calls.append(request)
        return VisualGenerationResponse(
            provider_name=self.provider_name,
            asset_uri="local://projects/demo/generated/visual_001.png",
            metadata={"prompt": request.prompt},
        )


def _response(provider_name: str, model_name: str, output_text: str) -> LLMResponse:
    return LLMResponse(
        provider_name=provider_name,
        model_name=model_name,
        output_text=output_text,
        metadata={},
    )


def test_router_prefers_local_provider_for_local_first_tasks() -> None:
    local_provider = FakeLLMProvider(
        provider_name="local_qwen",
        supported_tasks={LLMTaskType.SCENE_PLANNING},
        responses=[_response("local_qwen", "qwen3-35b", "local plan")],
    )
    gemini_provider = FakeLLMProvider(
        provider_name="gemini",
        supported_tasks={LLMTaskType.SCENE_PLANNING},
    )
    router = LLMTaskRouter(
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        gemini_key_pool=GeminiApiKeyPool.empty(),
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    result = router.complete(
        task_type=LLMTaskType.SCENE_PLANNING,
        prompt="Split this script into scenes.",
    )

    assert result.output_text == "local plan"
    assert len(local_provider.calls) == 1
    assert gemini_provider.calls == []


def test_router_falls_back_to_first_available_gemini_key_when_local_fails() -> None:
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    local_provider = FakeLLMProvider(
        provider_name="local_qwen",
        supported_tasks={LLMTaskType.KEYWORD_EXPANSION},
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="Local model unavailable",
                retryable=True,
            )
        ],
    )
    gemini_provider = FakeLLMProvider(
        provider_name="gemini",
        supported_tasks={LLMTaskType.KEYWORD_EXPANSION},
        responses=[_response("gemini", "gemini-2.5-flash", "gemini keywords")],
    )
    pool = GeminiApiKeyPool.empty().add_key(
        key_id="gem_001",
        label="Primary Gemini",
        api_key="secret-1",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )
    router = LLMTaskRouter(
        local_provider=local_provider,
        gemini_provider=gemini_provider,
        gemini_key_pool=pool,
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    result = router.complete(
        task_type=LLMTaskType.KEYWORD_EXPANSION,
        prompt="Expand B-roll tags for this segment.",
        now=now,
    )

    assert result.output_text == "gemini keywords"
    assert len(local_provider.calls) == 1
    assert len(gemini_provider.calls) == 1
    assert gemini_provider.calls[0].provider_context["gemini_key_id"] == "gem_001"
    assert gemini_provider.calls[0].provider_context["model_name"] == "gemini-2.5-flash-lite"


def test_router_keeps_openai_optional_when_not_configured() -> None:
    router = LLMTaskRouter(
        local_provider=FakeLLMProvider(
            provider_name="local_qwen",
            supported_tasks={LLMTaskType.ALIGNMENT_REVIEW},
            errors=[
                LLMProviderError(
                    provider_name="local_qwen",
                    message="local unavailable",
                    retryable=True,
                )
            ],
        ),
        gemini_provider=FakeLLMProvider(
            provider_name="gemini",
            supported_tasks={LLMTaskType.ALIGNMENT_REVIEW},
            errors=[
                LLMProviderError(
                    provider_name="gemini",
                    message="gemini unavailable",
                    retryable=True,
                )
            ],
        ),
        gemini_key_pool=GeminiApiKeyPool.empty(),
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
    )

    result = router.complete(
        task_type=LLMTaskType.ALIGNMENT_REVIEW,
        prompt="Review this borderline transcript alignment.",
    )

    assert result.provider_name == "rule_based_fallback"
    assert "manual review" in result.output_text.lower()


def test_gemini_key_pool_marks_rate_limited_keys_as_cooldown_and_disables_after_repeated_failures() -> None:
    now = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    pool = GeminiApiKeyPool.empty().add_key(
        key_id="gem_001",
        label="Primary Gemini",
        api_key="secret-1",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )

    pool = pool.mark_rate_limited("gem_001", now=now, cooldown_seconds=120)
    state = pool.get_key("gem_001")
    assert state.status is GeminiKeyStatus.COOLDOWN
    assert state.cooldown_until == now + timedelta(seconds=120)

    pool = pool.mark_failure("gem_001", now=now + timedelta(minutes=3), error_message="quota")
    pool = pool.mark_failure("gem_001", now=now + timedelta(minutes=4), error_message="quota")
    pool = pool.mark_failure("gem_001", now=now + timedelta(minutes=5), error_message="quota")

    assert pool.get_key("gem_001").status is GeminiKeyStatus.DISABLED


def test_gemini_key_pool_limits_dashboard_managed_keys_to_ten() -> None:
    pool = GeminiApiKeyPool.empty()

    for index in range(10):
        pool = pool.add_key(
            key_id=f"gem_{index:03d}",
            label=f"Gemini {index}",
            api_key=f"secret-{index}",
            primary_model="gemini-2.5-flash",
            cheap_model="gemini-2.5-flash-lite",
            high_quality_model="gemini-2.5-pro",
        )

    try:
        pool.add_key(
            key_id="gem_010",
            label="Gemini 10",
            api_key="secret-10",
            primary_model="gemini-2.5-flash",
            cheap_model="gemini-2.5-flash-lite",
            high_quality_model="gemini-2.5-pro",
        )
    except ValueError as exc:
        assert "10" in str(exc)
    else:
        raise AssertionError("Expected Gemini key pool to reject the 11th key")


def test_router_exposes_visual_provider_hook_without_affecting_llm_routing() -> None:
    visual_provider: VisualGenerationProvider = FakeVisualProvider()
    router = LLMTaskRouter(
        local_provider=FakeLLMProvider(
            provider_name="local_qwen",
            supported_tasks={LLMTaskType.SCENE_PLANNING},
            responses=[_response("local_qwen", "qwen3-35b", "scene plan")],
        ),
        gemini_provider=FakeLLMProvider(
            provider_name="gemini",
            supported_tasks={LLMTaskType.SCENE_PLANNING},
        ),
        gemini_key_pool=GeminiApiKeyPool.empty(),
        local_config=LLMProviderConfig(provider_name="local_qwen", enabled=True),
        gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
        visual_provider=visual_provider,
    )

    visual = router.generate_visual(
        prompt="Create a simple office overview illustration.",
        project_id="project_001",
    )
    llm = router.complete(
        task_type=LLMTaskType.SCENE_PLANNING,
        prompt="Split narration into scene groups.",
    )

    assert visual.asset_uri.endswith(".png")
    assert llm.output_text == "scene plan"
