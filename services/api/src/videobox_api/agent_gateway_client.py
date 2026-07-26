"""Strict internal-only client for the VideoBox agent gateway."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict


class AgentGatewayUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentGatewayEvent:
    event_type: str
    text: str = ""
    retryable: bool = False


class _GatewayFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_type: Literal["text_delta", "run_completed", "blocked"]
    text: str = ""
    retryable: bool = False


class _GatewayReservationFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str
    attach_context: str
    expires_in_seconds: Literal[30]


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
        identity = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "session_id": session_id,
            "session_revision": session_revision,
            "asset_index_revision": asset_index_revision,
        }
        reservation_created = False
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
                reservation_created = True
                reservation = _GatewayReservationFrame.model_validate(
                    reserved.json()
                )
                if (
                    reservation.run_id != run_id
                    or len(reservation.attach_context) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in reservation.attach_context
                    )
                ):
                    raise ValueError("agent_gateway_reservation_invalid")
                attached = await client.post(
                    f"/internal/hermes/runs/{run_id}/context",
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "X-VideoBox-Attach-Ticket": reservation.attach_context,
                    },
                    json={"identity": identity, "context": context},
                )
                attached.raise_for_status()
        except asyncio.CancelledError:
            if reservation_created:
                cleanup = asyncio.create_task(self.release_run(run_id=run_id))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    # A repeated cancellation may interrupt the waiter, but
                    # the shielded best-effort release remains independently
                    # owned until it finishes.
                    pass
            raise
        except Exception as error:
            if reservation_created:
                await self.release_run(run_id=run_id)
            raise AgentGatewayUnavailable("agent_gateway_unavailable") from error

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
                        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        payload = _GatewayFrame.model_validate_json(line)
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
                        yield AgentGatewayEvent(
                            event_type=payload.event_type,
                            text=payload.text,
                            retryable=payload.retryable,
                        )
                        if payload.event_type in {"run_completed", "blocked"}:
                            return
        except AgentGatewayUnavailable:
            raise
        except Exception as error:
            raise AgentGatewayUnavailable("agent_gateway_unavailable") from error
