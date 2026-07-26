"""Strict internal-only client for the VideoBox agent gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Literal
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


_MAX_LINE_BYTES = 64_000
_MAX_TEXT_BYTES = 32_000


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
            or "changeme" in lowered_token
            or "replace_me" in lowered_token
            or "placeholder" in lowered_token
        ):
            raise ValueError("agent_gateway_service_token_invalid")
        self._base_url = base_url.rstrip("/")
        self._token = service_token
        self._factory = http_client_factory
        self._timeout = timeout_seconds

    async def stream_run(
        self, *, session_id: str, client_message_id: str, text: str
    ) -> AsyncIterator[AgentGatewayEvent]:
        try:
            async with self._factory(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                async with client.stream(
                    "POST",
                    "/internal/hermes/stream",
                    headers={"Authorization": f"Bearer {self._token}"},
                    json={
                        "session_id": session_id,
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
                        if len(payload.text.encode("utf-8")) > _MAX_TEXT_BYTES:
                            raise AgentGatewayUnavailable("agent_gateway_unavailable")
                        if payload.event_type == "blocked" and payload.text:
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
