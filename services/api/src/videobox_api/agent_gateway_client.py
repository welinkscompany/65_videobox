"""Strict internal-only client for the VideoBox agent gateway."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from videobox_api.yujin_memory_service import (
    ApprovedMemoryStoreRequest,
    GatewayMemoryDeleteRequest,
    GatewayMemoryDeleteResult,
    GatewayMemorySearchRequest,
    GatewayMemorySearchResult,
    GatewayMemoryWriteOutcome,
    MemoryReconcileRequest,
)


class AgentGatewayUnavailable(RuntimeError):
    pass


class AgentGatewayHealth(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )

    status: Literal["ready"]
    scope: Literal["gateway_http_process"]
    gateway_configured: bool
    capability_routes_ready: bool
    hermes_http_ready: bool
    provider_ready: bool
    chat_ready: bool
    degraded: bool
    observation_epoch: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    process_started_at: datetime
    provider_observed_at: datetime | None = None
    last_chat_verified_at: datetime | None = None
    evidence_valid_until: datetime | None = None
    status_basis: Literal["gateway_observation"]

    @field_validator(
        "process_started_at",
        "provider_observed_at",
        "last_chat_verified_at",
        "evidence_valid_until",
        mode="before",
    )
    @classmethod
    def parse_strict_utc_timestamp(cls, value):
        if value is None or type(value) is datetime:
            return value
        if (
            type(value) is not str
            or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                r"(?:\.\d+)?(?:Z|\+00:00)",
                value,
            )
            is None
        ):
            raise ValueError("agent_gateway_health_timestamp_invalid")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @model_validator(mode="after")
    def timestamps_are_timezone_aware(self) -> "AgentGatewayHealth":
        timestamps = (
            self.process_started_at,
            self.provider_observed_at,
            self.last_chat_verified_at,
            self.evidence_valid_until,
        )
        if any(
            value is not None
            and (
                value.tzinfo is None
                or value.utcoffset() is None
                or value.utcoffset().total_seconds() != 0
            )
            for value in timestamps
        ):
            raise ValueError("agent_gateway_health_timestamp_invalid")
        if (
            self.capability_routes_ready
            and not self.gateway_configured
        ) or (
            self.hermes_http_ready
            and not (
                self.gateway_configured
                and self.capability_routes_ready
            )
        ) or (
            self.provider_ready and not self.hermes_http_ready
        ) or (
            self.chat_ready and not self.provider_ready
        ) or (
            self.degraded
            and (
                not self.gateway_configured
                or not self.capability_routes_ready
                or self.provider_ready
                or self.chat_ready
                or self.last_chat_verified_at is None
                or self.evidence_valid_until is None
            )
        ) or (
            self.provider_ready and self.provider_observed_at is None
        ) or (
            self.chat_ready and self.last_chat_verified_at is None
        ):
            raise ValueError("agent_gateway_health_invariant_invalid")
        observations = (
            self.provider_observed_at,
            self.last_chat_verified_at,
        )
        if any(
            observed_at is not None
            and (
                observed_at < self.process_started_at
                or self.evidence_valid_until is None
                or observed_at >= self.evidence_valid_until
            )
            for observed_at in observations
        ):
            raise ValueError("agent_gateway_health_evidence_order_invalid")
        return self


@dataclass(frozen=True)
class AgentGatewayEvent:
    event_type: str
    text: str = ""
    retryable: bool = False
    publish_capability_token: str | None = dataclass_field(default=None, repr=False)


class _GatewayFrame(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )

    event_type: Literal["text_delta", "run_completed", "blocked"]
    text: str = ""
    retryable: bool = False
    publish_capability_token: str | None = Field(
        default=None,
        min_length=5,
        max_length=8192,
        pattern=(
            r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"
        ),
    )

    @model_validator(mode="after")
    def terminal_capability_is_exact(self) -> "_GatewayFrame":
        has_publish_field = (
            "publish_capability_token" in self.model_fields_set
        )
        if (
            self.event_type == "run_completed"
            and (
                not has_publish_field
                or self.publish_capability_token is None
            )
        ) or (
            self.event_type != "run_completed"
            and has_publish_field
        ):
            raise ValueError("agent_gateway_terminal_capability_invalid")
        return self


def _parse_gateway_frame(line: str) -> _GatewayFrame | None:
    try:
        return _GatewayFrame.model_validate_json(line)
    except Exception:
        return None


class AgentGatewayCapabilityMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    capability_id: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$",
    )
    action: Literal["read_context", "publish_proposal"]
    expires_at: int = Field(gt=0, strict=True)


class AgentGatewayReservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    run_id: str = Field(min_length=1, max_length=255)
    attach_context: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_in_seconds: int = Field(ge=1, le=30, strict=True)
    read_capability_token: str = Field(
        min_length=5,
        max_length=8192,
        pattern=(
            r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"
        ),
    )
    capabilities: tuple[
        AgentGatewayCapabilityMetadata,
        AgentGatewayCapabilityMetadata,
    ]

    @model_validator(mode="after")
    def exact_capability_pair(self) -> "AgentGatewayReservation":
        if (
            tuple(item.action for item in self.capabilities)
            != ("read_context", "publish_proposal")
            or len(
                {
                    item.capability_id
                    for item in self.capabilities
                }
            )
            != 2
        ):
            raise ValueError("agent_gateway_reservation_invalid")
        return self


_MAX_LINE_BYTES = 256_000
_MAX_DELTA_TEXT_BYTES = 32_000
_MAX_ASSEMBLED_TEXT_BYTES = 200_000


def _default_http_client_factory(*, base_url: str, timeout: float):
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


class AgentGatewayClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        http_client_factory: Callable = _default_http_client_factory,
        timeout_seconds: float = 35.0,
        status_timeout_seconds: float = 3.0,
        epoch_seconds: Callable[[], int] | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "videobox-agent-gateway"
            or parsed.port != 8081
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("agent_gateway_url_must_be_internal")
        lowered_token = service_token.strip().lower()
        if (
            len(service_token.encode("utf-8")) < 32
            or service_token != service_token.strip()
            or len(set(service_token)) < 8
            or "changeme" in lowered_token
            or "replace_me" in lowered_token
            or "placeholder" in lowered_token
        ):
            raise ValueError("agent_gateway_service_token_invalid")
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._factory = http_client_factory
        self._timeout = timeout_seconds
        if (
            isinstance(status_timeout_seconds, bool)
            or not isinstance(status_timeout_seconds, (int, float))
            or not 0 < float(status_timeout_seconds) <= 5
        ):
            raise ValueError("agent_gateway_status_timeout_invalid")
        self._status_timeout = float(status_timeout_seconds)
        self._epoch_seconds = epoch_seconds or (
            lambda: int(time.time())
        )

    async def get_health(self) -> AgentGatewayHealth:
        try:
            async with self._factory(
                base_url=self._base_url,
                timeout=self._status_timeout,
            ) as client:
                response = await client.get("/health")
                if (
                    response.status_code != 200
                    or bool(getattr(response, "is_redirect", False))
                ):
                    raise ValueError("agent_gateway_status_invalid")
                return AgentGatewayHealth.model_validate(response.json())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable(
                "agent_gateway_status_unavailable"
            ) from error

    async def _memory_post(
        self, path: str, payload: dict[str, Any]
    ) -> GatewayMemoryWriteOutcome:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    path,
                    headers={
                        "Authorization": f"Bearer {self._token}"
                    },
                    json=payload,
                )
                if bool(getattr(response, "is_redirect", False)):
                    raise ValueError("agent_gateway_memory_invalid")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if (
                    isinstance(content, (bytes, bytearray))
                    and len(content) > 16_384
                ):
                    raise ValueError("agent_gateway_memory_invalid")
                return GatewayMemoryWriteOutcome.model_validate(
                    response.json()
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable(
                "agent_gateway_memory_unavailable"
            ) from error

    async def add_approved_memory(
        self, request: ApprovedMemoryStoreRequest
    ) -> GatewayMemoryWriteOutcome:
        return await self._memory_post(
            "/internal/hermes/memory/add", request.model_dump()
        )

    async def reconcile_memory(
        self, request: MemoryReconcileRequest
    ) -> GatewayMemoryWriteOutcome:
        return await self._memory_post(
            "/internal/hermes/memory/reconcile",
            request.model_dump(),
        )

    async def search_memory(
        self, request: GatewayMemorySearchRequest
    ) -> GatewayMemorySearchResult:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    "/internal/hermes/memory/search",
                    headers={
                        "Authorization": f"Bearer {self._token}"
                    },
                    json=request.model_dump(),
                )
                if bool(getattr(response, "is_redirect", False)):
                    raise ValueError("agent_gateway_memory_invalid")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if isinstance(content, (bytes, bytearray)) and len(content) > 16_384:
                    raise ValueError("agent_gateway_memory_invalid")
                return GatewayMemorySearchResult.model_validate(
                    response.json()
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable(
                "agent_gateway_memory_unavailable"
            ) from error

    async def delete_memory(
        self, request: GatewayMemoryDeleteRequest
    ) -> GatewayMemoryDeleteResult:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    "/internal/hermes/memory/delete",
                    headers={
                        "Authorization": f"Bearer {self._token}"
                    },
                    json=request.model_dump(),
                )
                if bool(getattr(response, "is_redirect", False)):
                    raise ValueError("agent_gateway_memory_invalid")
                response.raise_for_status()
                content = getattr(response, "content", b"")
                if isinstance(content, (bytes, bytearray)) and len(content) > 16_384:
                    raise ValueError("agent_gateway_memory_invalid")
                return GatewayMemoryDeleteResult.model_validate(
                    response.json()
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable(
                "agent_gateway_memory_unavailable"
            ) from error

    async def reserve_run(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
    ) -> AgentGatewayReservation:
        identity = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "session_id": session_id,
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
        }
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                reserved = await client.post(
                    "/internal/hermes/runs",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=identity,
                )
                reserved.raise_for_status()
                payload = reserved.json()
                if type(payload) is not dict:
                    raise ValueError("agent_gateway_reservation_invalid")
                capabilities = payload.get("capabilities")
                if type(capabilities) is not list:
                    raise ValueError("agent_gateway_reservation_invalid")
                reservation = AgentGatewayReservation.model_validate(
                    {
                        **payload,
                        "capabilities": tuple(capabilities),
                    }
                )
                now = self._epoch_seconds()
                if (
                    reservation.run_id != run_id
                    or any(
                        item.expires_at <= now
                        or item.expires_at - now
                        < reservation.expires_in_seconds
                        for item in reservation.capabilities
                    )
                ):
                    raise ValueError("agent_gateway_reservation_invalid")
                return reservation
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable("agent_gateway_unavailable") from error

    async def attach_run_context(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        reservation: AgentGatewayReservation,
        context: dict[str, Any],
    ) -> None:
        if reservation.run_id != run_id:
            raise AgentGatewayUnavailable("agent_gateway_unavailable")
        identity = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "session_id": session_id,
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
        }
        try:
            async with self._factory(
                base_url=self._base_url,
                timeout=self._timeout,
            ) as client:
                attached = await client.post(
                    f"/internal/hermes/runs/{run_id}/context",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "X-VideoBox-Attach-Ticket": (
                            reservation.attach_context
                        ),
                    },
                    json={"identity": identity, "context": context},
                )
                attached.raise_for_status()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable(
                "agent_gateway_unavailable"
            ) from error

    async def prepare_run(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        context: dict[str, Any],
    ) -> None:
        """Compatibility wrapper; HermesRunService owns split admission."""

        reservation_created = False
        try:
            reservation = await self.reserve_run(
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                session_id=session_id,
                session_revision=session_revision,
                asset_index_revision=asset_index_revision,
            )
            reservation_created = True
            await self.attach_run_context(
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                session_id=session_id,
                session_revision=session_revision,
                asset_index_revision=asset_index_revision,
                reservation=reservation,
                context=context,
            )
        except asyncio.CancelledError:
            if reservation_created:
                await asyncio.shield(self.release_run(run_id=run_id))
            raise
        except Exception:
            if reservation_created:
                await self.release_run(run_id=run_id)
            raise

    async def release_run(self, *, run_id: str) -> None:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.delete(
                    f"/internal/hermes/runs/{run_id}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                response.raise_for_status()
        except Exception:
            # Cleanup is best effort; the gateway ledger remains bounded and
            # has its own attached-context expiry fence.
            return

    async def cancel_run(self, *, run_id: str) -> None:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                response = await client.post(
                    f"/internal/hermes/runs/{run_id}/cancel",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                response.raise_for_status()
        except Exception as error:
            raise AgentGatewayUnavailable("hermes_unavailable") from error

    async def stream_run(
        self,
        *,
        run_id: str | None = None,
        client_message_id: str,
        text: str,
        session_id: str | None = None,
    ) -> AsyncIterator[AgentGatewayEvent]:
        effective_run_id = run_id or session_id
        if not effective_run_id:
            raise AgentGatewayUnavailable("agent_gateway_unavailable")
        assembled = ""
        assembled_bytes = 0
        terminal: AgentGatewayEvent | None = None
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                async with client.stream(
                    "POST",
                    f"/internal/hermes/runs/{effective_run_id}/stream",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={
                        "client_message_id": client_message_id,
                        "text": text,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if terminal is not None:
                            raise AgentGatewayUnavailable(
                                "agent_gateway_unavailable"
                            )
                        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        payload = _parse_gateway_frame(line)
                        if payload is None:
                            raise AgentGatewayUnavailable(
                                "agent_gateway_unavailable"
                            )
                        payload_bytes = len(payload.text.encode("utf-8"))
                        if (
                            payload.event_type == "text_delta"
                            and (
                                payload_bytes > _MAX_DELTA_TEXT_BYTES
                                or assembled_bytes + payload_bytes
                                > _MAX_ASSEMBLED_TEXT_BYTES
                            )
                        ):
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        if payload.event_type == "blocked" and payload.text:
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        if payload.event_type == "text_delta":
                            assembled += payload.text
                            assembled_bytes += payload_bytes
                        elif payload.event_type == "run_completed" and (
                            payload_bytes > _MAX_ASSEMBLED_TEXT_BYTES
                            or payload.text != assembled
                        ):
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        event = AgentGatewayEvent(
                            event_type=payload.event_type,
                            text=payload.text,
                            retryable=payload.retryable,
                            publish_capability_token=(
                                payload.publish_capability_token
                            ),
                        )
                        if payload.event_type in {"run_completed", "blocked"}:
                            terminal = event
                        else:
                            yield event
                    if terminal is None:
                        raise AgentGatewayUnavailable(
                            "agent_gateway_unavailable"
                        )
                    yield terminal
        except AgentGatewayUnavailable:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable("agent_gateway_unavailable") from error
