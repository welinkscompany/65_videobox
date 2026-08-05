"""One interface for Yujin's conversation provider, switchable between the
local model and (once §23.1's egress gate and Hermes OAuth exist) external
GPT providers (Task 14).

implementation-plan.ko.md §23.3A.3: provider switching must always be
explicit and recorded -- never a silent fallback to a different provider or
model. This module is the enforcement point for that rule: switching is a
deliberate call that appends to an audit trail, and replying on a provider
that isn't actually wired up ends in `blocked`, never in quietly answering
from a different provider instead.

GPT-5.4 / GPT-5.4-mini themselves are out of scope here. §23.1's egress
allowlist gate and the Hermes OAuth login are both still unbuilt, so no
external call can be made no matter how this adapter is configured -- it
structurally cannot dispatch to either GPT provider yet. That is deliberate,
not a placeholder to fill in casually later; opening it is a separate,
security-relevant decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

YUJIN_PROVIDER_NAMES = ("local", "gpt-5.4", "gpt-5.4-mini")


class YujinConversationResult(Protocol):
    status: str
    reply: str


class _LocalConversationService(Protocol):
    def reply(self, *, project_id: str, user_text: str) -> YujinConversationResult: ...


@dataclass(slots=True, frozen=True)
class YujinProviderSwitchRecord:
    from_provider: str | None
    to_provider: str
    switched_at: datetime
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class YujinAdapterReplyResult:
    status: str  # "ok" | "blocked"
    reply: str
    provider: str
    blocked_reason: str | None = None


class YujinProviderAdapter:
    """Routes a conversation turn to whichever provider is currently
    selected. Local is adopt-as-is (Task 13's YujinLocalConversationService).
    GPT providers are named and switchable now so Task 14's contract exists,
    but every reply on them ends in `blocked` until §23.1/OAuth land --
    there is no external HTTP client wired up here to accidentally call."""

    def __init__(
        self,
        *,
        local_conversation_service: _LocalConversationService,
        initial_provider: str = "local",
        clock: "callable[[], datetime]" = lambda: datetime.now(UTC),
    ) -> None:
        if initial_provider not in YUJIN_PROVIDER_NAMES:
            raise ValueError(f"initial_provider must be one of {YUJIN_PROVIDER_NAMES}, got {initial_provider!r}")
        self._local_conversation_service = local_conversation_service
        self._clock = clock
        self.current_provider = initial_provider
        self.switch_history: list[YujinProviderSwitchRecord] = []

    def switch_provider(self, *, provider: str, reason: str | None = None) -> YujinProviderSwitchRecord:
        if provider not in YUJIN_PROVIDER_NAMES:
            raise ValueError(f"provider must be one of {YUJIN_PROVIDER_NAMES}, got {provider!r}")
        record = YujinProviderSwitchRecord(
            from_provider=self.current_provider,
            to_provider=provider,
            switched_at=self._clock(),
            reason=reason,
        )
        self.current_provider = provider
        self.switch_history.append(record)
        return record

    def reply(self, *, project_id: str, user_text: str) -> YujinAdapterReplyResult:
        provider = self.current_provider
        if provider == "local":
            result = self._local_conversation_service.reply(project_id=project_id, user_text=user_text)
            return YujinAdapterReplyResult(
                status=result.status,
                reply=result.reply,
                provider=provider,
                blocked_reason=getattr(result, "blocked_reason", None),
            )
        # gpt-5.4 / gpt-5.4-mini: structurally blocked. Deliberately not a
        # "not implemented yet" placeholder that later gets wired to any
        # convenient HTTP client -- the block reason names the actual
        # precondition (§23.1 egress gate + Hermes OAuth) that must be
        # satisfied and recorded before this branch may call out.
        return YujinAdapterReplyResult(
            status="blocked",
            reply=(
                "지금은 외부 provider로 대화할 수 없어요. 로컬 모델로 계속하거나, "
                "외부 연결이 준비되면 다시 시도해 주세요."
            ),
            provider=provider,
            blocked_reason="external_provider_egress_not_configured",
        )
