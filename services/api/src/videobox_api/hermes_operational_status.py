"""Truthful process-local Hermes Yujin operational status mapping."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from videobox_api.agent_gateway_client import AgentGatewayHealth
from videobox_api.models import HermesYujinStatusResponse

_LOGGER = logging.getLogger(__name__)


class HermesOperationalStatusService:
    def __init__(
        self,
        gateway_client=None,
        *,
        admission_ready: bool = True,
        now=None,
    ) -> None:
        self._gateway_client = gateway_client
        self._admission_ready = admission_ready
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = asyncio.Lock()
        self._observation_epoch: str | None = None
        self._last_chat_verified_at: datetime | None = None
        self._evidence_valid_until: datetime | None = None
        self._failure_valid_until: datetime | None = None
        self._reported_health_fault: str | None = None

    @staticmethod
    def _aware(value: datetime) -> bool:
        return value.tzinfo is not None and value.utcoffset() is not None

    @classmethod
    def _fresh_evidence(
        cls,
        *,
        observed_at: datetime | None,
        process_started_at: datetime,
        valid_until: datetime | None,
        checked_at: datetime,
    ) -> bool:
        return bool(
            observed_at is not None
            and valid_until is not None
            and cls._aware(observed_at)
            and cls._aware(process_started_at)
            and cls._aware(valid_until)
            and process_started_at <= observed_at <= checked_at
            and checked_at - observed_at <= timedelta(minutes=10)
            and checked_at < valid_until
        )

    def _remember_chat_reference(
        self,
        health: AgentGatewayHealth,
        *,
        checked_at: datetime,
    ) -> None:
        observed_at = health.last_chat_verified_at
        if (
            observed_at is not None
            and observed_at >= health.process_started_at
            and observed_at <= checked_at
            and (
                self._last_chat_verified_at is None
                or observed_at > self._last_chat_verified_at
            )
        ):
            self._last_chat_verified_at = observed_at.astimezone(UTC)
            self._evidence_valid_until = (
                health.evidence_valid_until.astimezone(UTC)
                if health.evidence_valid_until is not None
                else None
            )

    def _remembered_chat_is_fresh(self, checked_at: datetime) -> bool:
        return bool(
            self._last_chat_verified_at is not None
            and self._last_chat_verified_at <= checked_at
            and (
                (
                    self._evidence_valid_until is not None
                    and checked_at - self._last_chat_verified_at
                    <= timedelta(minutes=10)
                    and checked_at < self._evidence_valid_until
                )
                or (
                    self._failure_valid_until is not None
                    and checked_at < self._failure_valid_until
                )
            )
        )

    def _response(
        self,
        *,
        state: str,
        checked_at: datetime,
        http_ready: bool = False,
        provider_ready: bool = False,
        chat_verified: bool = False,
    ) -> HermesYujinStatusResponse:
        last_chat_verified_at = self._last_chat_verified_at
        if (
            last_chat_verified_at is not None
            and last_chat_verified_at > checked_at
        ):
            last_chat_verified_at = None
        return HermesYujinStatusResponse(
            state=state,
            http_ready=http_ready,
            provider_ready=provider_ready,
            chat_verified=chat_verified,
            checked_at=checked_at,
            last_chat_verified_at=last_chat_verified_at,
        )

    async def get_status(self) -> HermesYujinStatusResponse:
        async with self._lock:
            checked_at = self._now()
            if not self._aware(checked_at):
                raise ValueError("hermes_operational_clock_invalid")
            checked_at = checked_at.astimezone(UTC)
            if self._gateway_client is None or not self._admission_ready:
                return self._response(
                    state="not_configured",
                    checked_at=checked_at,
                )
            try:
                health = await self._gateway_client.get_health()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 상태 화면은 계속 떠야 한다
                # 화면은 "멈춤"이라고만 말하고, 어느 층에서 왜 막혔는지는
                # 어디에도 남지 않았다. 상태를 떨어뜨리는 동작은 그대로 두고
                # 이유만 남긴다. 화면이 계속 되묻는 경로라 같은 사유는 한 번만
                # 찍고, 한 번 응답을 받으면 잊어서 다음 장애를 다시 남긴다.
                fault = f"{type(exc).__name__}|{exc}"
                if fault != self._reported_health_fault:
                    self._reported_health_fault = fault
                    _LOGGER.warning(
                        "유진 상태를 확인하지 못했습니다. 화면에는 멈춘 것으로 보입니다.",
                        exc_info=True,
                    )
                return self._response(
                    state=(
                        "degraded"
                        if self._remembered_chat_is_fresh(checked_at)
                        else "stopped"
                    ),
                    checked_at=checked_at,
                )
            self._reported_health_fault = None

            if health.observation_epoch != self._observation_epoch:
                self._observation_epoch = health.observation_epoch
                self._last_chat_verified_at = None
                self._evidence_valid_until = None
                self._failure_valid_until = None

            self._remember_chat_reference(
                health,
                checked_at=checked_at,
            )
            chat_fresh = self._fresh_evidence(
                observed_at=health.last_chat_verified_at,
                process_started_at=health.process_started_at,
                valid_until=health.evidence_valid_until,
                checked_at=checked_at,
            )
            provider_fresh = self._fresh_evidence(
                observed_at=health.provider_observed_at,
                process_started_at=health.process_started_at,
                valid_until=health.evidence_valid_until,
                checked_at=checked_at,
            )
            degraded_fresh = bool(
                health.degraded
                and health.last_chat_verified_at is not None
                and health.evidence_valid_until is not None
                and health.process_started_at
                <= health.last_chat_verified_at
                <= checked_at
                < health.evidence_valid_until
                and health.evidence_valid_until - checked_at
                <= timedelta(minutes=10)
            )
            if degraded_fresh:
                self._failure_valid_until = (
                    health.evidence_valid_until.astimezone(UTC)
                )
            elif not health.degraded:
                self._failure_valid_until = None
            path_ready = (
                health.gateway_configured
                and health.capability_routes_ready
            )
            if not path_ready:
                return self._response(
                    state=(
                        "degraded"
                        if self._remembered_chat_is_fresh(checked_at)
                        else "stopped"
                    ),
                    checked_at=checked_at,
                )
            if degraded_fresh:
                return self._response(
                    state="degraded",
                    checked_at=checked_at,
                    http_ready=health.hermes_http_ready,
                )
            if not health.hermes_http_ready:
                return self._response(
                    state=(
                        "degraded"
                        if self._remembered_chat_is_fresh(checked_at)
                        else "starting"
                    ),
                    checked_at=checked_at,
                )
            if health.chat_ready and chat_fresh:
                return self._response(
                    state="chat_verified",
                    checked_at=checked_at,
                    http_ready=True,
                    provider_ready=True,
                    chat_verified=True,
                )
            if health.provider_ready and provider_fresh:
                return self._response(
                    state="provider_ready",
                    checked_at=checked_at,
                    http_ready=True,
                    provider_ready=True,
                )
            return self._response(
                state="http_ready",
                checked_at=checked_at,
                http_ready=True,
            )
