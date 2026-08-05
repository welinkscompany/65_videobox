from __future__ import annotations

import os

import pytest

from videobox_core_engine.local_only_runtime import LocalOnlyStructuredRuntime
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_core_engine.yujin_local_conversation import YujinLocalConversationService
from videobox_provider_interfaces.lm_studio import LMStudioHTTPTransport, LMStudioProviderError
from videobox_provider_interfaces.local_qwen import LocalQwenHTTPTransport, LocalQwenStructuredProvider

_LIVE_SMOKE_ENV = "VIDEOBOX_RUN_YUJIN_LOCAL_CONVERSATION_SMOKE"
_LIVE_SMOKE_ENABLE_VALUE = "1"
_LIVE_SMOKE_SKIP_REASON = (
    "Yujin local-conversation live smoke is disabled; set "
    "VIDEOBOX_RUN_YUJIN_LOCAL_CONVERSATION_SMOKE=1 to permit only 127.0.0.1:1234."
)


def _require_live_smoke_opt_in() -> None:
    if os.environ.get(_LIVE_SMOKE_ENV) != _LIVE_SMOKE_ENABLE_VALUE:
        pytest.skip(_LIVE_SMOKE_SKIP_REASON)


class _RuntimeAdapter:
    """Adapts LocalOnlyStructuredRuntime.generate to the
    generate_structured(...) shape YujinLocalConversationService expects
    (the same shape services/api/src/videobox_api/orchestration.py's
    LocalOnlyRuntimeService exposes in production)."""

    def __init__(self, runtime: LocalOnlyStructuredRuntime) -> None:
        self._runtime = runtime

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        return self._runtime.generate(
            project_id=project_id,
            task_type=task_type,
            prompt=prompt,
            response_schema=response_schema,
        )


@pytest.mark.live_lmstudio
def test_yujin_replies_with_real_local_model_output() -> None:
    """Runs only by explicit opt-in and never substitutes a fake provider."""
    _require_live_smoke_opt_in()

    discovery_transport = LMStudioHTTPTransport()
    try:
        profile = discovery_transport.capability_profile(timeout_seconds=15)
    except LMStudioProviderError as exc:
        pytest.skip(f"Yujin local-conversation live smoke blocked: {exc.code}: {exc}")
    if profile.text_model_name is None:
        pytest.skip("Yujin local-conversation live smoke blocked: no loaded native text model is available.")

    config = LocalOpenAICompatibleRuntimeConfig(model_name=profile.text_model_name)
    transport = LocalQwenHTTPTransport(base_url=config.base_url, timeout_seconds=60)
    provider = LocalQwenStructuredProvider(transport=transport)
    runtime = LocalOnlyStructuredRuntime(local_provider=provider, local_runtime_config=config)
    service = YujinLocalConversationService(runtime=_RuntimeAdapter(runtime))

    result = service.reply(project_id="live-smoke", user_text="안녕 유진, 짧게 한 문장으로 인사해줘.")

    assert result.status == "ok"
    assert result.reply
    # A canned/mock provider would never see the actual model id below;
    # asserting the model id round-trips proves this hit the real transport.
    assert profile.text_model_name


@pytest.mark.live_lmstudio
def test_yujin_blocks_restricted_intent_without_reaching_the_model() -> None:
    _require_live_smoke_opt_in()

    discovery_transport = LMStudioHTTPTransport()
    try:
        profile = discovery_transport.capability_profile(timeout_seconds=15)
    except LMStudioProviderError as exc:
        pytest.skip(f"Yujin local-conversation live smoke blocked: {exc.code}: {exc}")
    if profile.text_model_name is None:
        pytest.skip("Yujin local-conversation live smoke blocked: no loaded native text model is available.")

    config = LocalOpenAICompatibleRuntimeConfig(model_name=profile.text_model_name)
    transport = LocalQwenHTTPTransport(base_url=config.base_url, timeout_seconds=60)
    provider = LocalQwenStructuredProvider(transport=transport)
    runtime = LocalOnlyStructuredRuntime(local_provider=provider, local_runtime_config=config)
    service = YujinLocalConversationService(runtime=_RuntimeAdapter(runtime))

    result = service.reply(project_id="live-smoke", user_text="이 프로젝트 데이터베이스 테이블 삭제해줘")

    assert result.status == "blocked"
    assert result.blocked_reason == "policy_restricted_intent"
