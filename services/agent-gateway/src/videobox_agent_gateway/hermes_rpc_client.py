"""Bounded, allowlisted client for Hermes Agent v0.18.2 dashboard transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
import json
from urllib.parse import quote
from urllib.parse import urlsplit


class HermesTransportError(RuntimeError):
    """A deliberately redacted Hermes transport failure."""


_MAX_RPC_FRAME_BYTES = 64_000


@dataclass(frozen=True)
class HermesRpcEvent:
    event_type: str
    text: str = ""


def _default_http_client_factory(*, base_url: str, timeout: float):
    import httpx

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )


def _default_websocket_factory(url: str, **kwargs):
    import websockets

    return websockets.connect(url, proxy=None, **kwargs)


class HermesRpcClient:
    """Authenticate, mint one ticket, and run one prompt on one WebSocket."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        http_client_factory: Callable = _default_http_client_factory,
        websocket_factory: Callable = _default_websocket_factory,
        timeout_seconds: float = 30.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "videobox-hermes-yujin"
            or parsed.port != 9120
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("hermes_url_must_be_internal")
        if not username or not password:
            raise ValueError("hermes_credentials_required")
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._http_factory = http_client_factory
        self._ws_factory = websocket_factory
        self._timeout = timeout_seconds

    async def stream_prompt(self, *, text: str) -> AsyncIterator[HermesRpcEvent]:
        session_id = ""
        websocket = None
        try:
            async with asyncio.timeout(self._timeout):
                async with self._http_factory(
                    base_url=self._base_url, timeout=self._timeout
                ) as http:
                    login = await http.post(
                        "/auth/password-login",
                        json={
                            "provider": "basic",
                            "username": self._username,
                            "password": self._password,
                            "next": "",
                        },
                    )
                    login.raise_for_status()
                    ticket_response = await http.post("/api/auth/ws-ticket")
                    ticket_response.raise_for_status()
                    ticket = str(ticket_response.json().get("ticket") or "")
                    if not ticket:
                        raise HermesTransportError("hermes_transport_unavailable")

                ws_base = self._base_url.replace("http://", "ws://", 1).replace(
                    "https://", "wss://", 1
                )
                ws_url = f"{ws_base}/api/ws?ticket={quote(ticket, safe='')}"
                async with self._ws_factory(
                    ws_url,
                    open_timeout=self._timeout,
                    close_timeout=min(self._timeout, 5.0),
                ) as websocket:
                    await websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "session.create",
                                "params": {"source": "videobox"},
                            }
                        )
                    )
                    session_id = await self._wait_for_session(websocket)
                    await websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": 2,
                                "method": "prompt.submit",
                                "params": {"session_id": session_id, "text": text},
                            }
                        )
                    )
                    async for event in self._read_prompt_events(websocket, session_id):
                        yield event
        except asyncio.CancelledError:
            if websocket is not None and session_id:
                await self._interrupt_best_effort(websocket, session_id)
            raise
        except TimeoutError as error:
            if websocket is not None and session_id:
                await self._interrupt_best_effort(websocket, session_id)
            raise HermesTransportError("hermes_transport_timeout") from error
        except HermesTransportError:
            raise
        except Exception as error:
            raise HermesTransportError("hermes_transport_unavailable") from error

    async def _wait_for_session(self, websocket) -> str:
        while True:
            message = self._decode(await websocket.recv())
            if message.get("id") != 1:
                self._validate_ignored_message(message)
                continue
            if "error" in message:
                raise HermesTransportError("hermes_session_unavailable")
            session_id = str((message.get("result") or {}).get("session_id") or "")
            if not session_id:
                raise HermesTransportError("hermes_session_unavailable")
            return session_id

    async def _read_prompt_events(
        self, websocket, session_id: str
    ) -> AsyncIterator[HermesRpcEvent]:
        while True:
            message = self._decode(await websocket.recv())
            if message.get("id") == 2 and "error" in message:
                raise HermesTransportError("hermes_prompt_unavailable")
            if message.get("method") != "event":
                continue
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            event_type = params.get("type")
            if isinstance(event_type, str) and (
                event_type.startswith("tool.")
                or event_type.startswith("approval.")
                or event_type.startswith("terminal.")
                or event_type.startswith("file.")
            ):
                raise HermesTransportError("hermes_tool_event_forbidden")
            if event_type not in {"gateway.ready", "message.delta", "message.complete"}:
                continue
            event_session = params.get("session_id")
            if event_type != "gateway.ready" and event_session != session_id:
                raise HermesTransportError("hermes_event_session_invalid")
            payload = params.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if event_type == "gateway.ready":
                yield HermesRpcEvent("gateway.ready")
            elif event_type == "message.delta":
                text = payload.get("text", "")
                if not isinstance(text, str):
                    raise HermesTransportError("hermes_protocol_invalid")
                yield HermesRpcEvent("message.delta", text)
            else:
                if payload.get("status") != "complete":
                    raise HermesTransportError("hermes_completion_blocked")
                text = payload.get("text", "")
                if not isinstance(text, str):
                    raise HermesTransportError("hermes_protocol_invalid")
                if not text.strip():
                    raise HermesTransportError("hermes_completion_blocked")
                yield HermesRpcEvent(
                    "message.complete", text
                )
                return

    @staticmethod
    def _decode(raw: object) -> dict:
        if not isinstance(raw, (str, bytes)):
            raise HermesTransportError("hermes_protocol_invalid")
        if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > _MAX_RPC_FRAME_BYTES:
            raise HermesTransportError("hermes_protocol_invalid")
        try:
            message = json.loads(raw)
        except Exception as error:
            raise HermesTransportError("hermes_protocol_invalid") from error
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise HermesTransportError("hermes_protocol_invalid")
        return message

    @staticmethod
    def _validate_ignored_message(message: dict) -> None:
        if message.get("method") == "event":
            params = message.get("params")
            event_type = params.get("type") if isinstance(params, dict) else None
            if event_type == "gateway.ready":
                return
            if isinstance(event_type, str) and (
                event_type.startswith("tool.")
                or event_type.startswith("approval.")
                or event_type.startswith("terminal.")
                or event_type.startswith("file.")
            ):
                raise HermesTransportError("hermes_tool_event_forbidden")
            if event_type in {"message.delta", "message.complete"}:
                raise HermesTransportError("hermes_event_session_invalid")

    @staticmethod
    async def _interrupt_best_effort(websocket, session_id: str) -> None:
        try:
            await websocket.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "session.interrupt",
                        "params": {"session_id": session_id},
                    }
                )
            )
        except Exception:
            pass
