from __future__ import annotations

from datetime import datetime, UTC

import pytest

from videobox_core_engine.yujin_provider_adapter import (
    YUJIN_PROVIDER_NAMES,
    YujinProviderAdapter,
)


class _FakeLocalService:
    def __init__(self, *, status="ok", reply="안녕하세요", blocked_reason=None) -> None:
        self.status = status
        self.reply_text = reply
        self.blocked_reason = blocked_reason
        self.calls: list[dict] = []

    def reply(self, *, project_id, user_text):
        self.calls.append({"project_id": project_id, "user_text": user_text})
        return type(
            "Result", (), {"status": self.status, "reply": self.reply_text, "blocked_reason": self.blocked_reason}
        )()


def test_defaults_to_local_and_answers_through_it():
    local = _FakeLocalService(reply="이 장면엔 카페 클립이 어울려요.")
    adapter = YujinProviderAdapter(local_conversation_service=local)

    result = adapter.reply(project_id="proj-1", user_text="이 장면에 뭐가 어울려?")

    assert adapter.current_provider == "local"
    assert result.provider == "local"
    assert result.status == "ok"
    assert result.reply == "이 장면엔 카페 클립이 어울려요."
    assert local.calls == [{"project_id": "proj-1", "user_text": "이 장면에 뭐가 어울려?"}]


def test_switching_provider_actually_changes_where_the_next_reply_goes():
    local = _FakeLocalService()
    adapter = YujinProviderAdapter(local_conversation_service=local)

    adapter.switch_provider(provider="gpt-5.4")
    result = adapter.reply(project_id="proj-1", user_text="안녕")

    assert adapter.current_provider == "gpt-5.4"
    assert result.provider == "gpt-5.4"
    assert local.calls == []  # never silently fell back to local


def test_an_unconfigured_provider_ends_in_blocked_not_a_silent_local_fallback():
    local = _FakeLocalService()
    adapter = YujinProviderAdapter(local_conversation_service=local)
    adapter.switch_provider(provider="gpt-5.4-mini")

    result = adapter.reply(project_id="proj-1", user_text="안녕")

    assert result.status == "blocked"
    assert result.blocked_reason == "external_provider_egress_not_configured"
    assert local.calls == []


def test_switching_is_always_explicit_and_recorded():
    adapter = YujinProviderAdapter(local_conversation_service=_FakeLocalService())

    record = adapter.switch_provider(provider="gpt-5.4", reason="owner requested a GPT comparison")

    assert record.from_provider == "local"
    assert record.to_provider == "gpt-5.4"
    assert record.reason == "owner requested a GPT comparison"
    assert isinstance(record.switched_at, datetime)
    assert adapter.switch_history == [record]

    second = adapter.switch_provider(provider="local")
    assert second.from_provider == "gpt-5.4"
    assert second.to_provider == "local"
    assert adapter.switch_history == [record, second]


def test_switching_to_an_unknown_provider_name_is_rejected():
    adapter = YujinProviderAdapter(local_conversation_service=_FakeLocalService())
    with pytest.raises(ValueError):
        adapter.switch_provider(provider="claude-opus")
    assert adapter.switch_history == []
    assert adapter.current_provider == "local"


def test_constructing_with_an_unknown_initial_provider_is_rejected():
    with pytest.raises(ValueError):
        YujinProviderAdapter(local_conversation_service=_FakeLocalService(), initial_provider="not-a-provider")


def test_all_three_provider_names_are_declared():
    assert set(YUJIN_PROVIDER_NAMES) == {"local", "gpt-5.4", "gpt-5.4-mini"}


def test_switch_history_uses_an_injectable_clock_for_deterministic_tests():
    fixed = datetime(2026, 8, 6, 12, 0, 0, tzinfo=UTC)
    adapter = YujinProviderAdapter(local_conversation_service=_FakeLocalService(), clock=lambda: fixed)

    record = adapter.switch_provider(provider="gpt-5.4")

    assert record.switched_at == fixed


def test_a_blocked_local_reply_still_reports_its_own_blocked_reason():
    local = _FakeLocalService(status="blocked", reply="이건 못 해요.", blocked_reason="policy_restricted_intent")
    adapter = YujinProviderAdapter(local_conversation_service=local)

    result = adapter.reply(project_id="proj-1", user_text="데이터베이스 지워줘")

    assert result.status == "blocked"
    assert result.blocked_reason == "policy_restricted_intent"
    assert result.provider == "local"
