"""Bounded, allowlisted client for Hermes Agent v0.18.2 dashboard transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
import json
from urllib.parse import quote


class HermesTransportError(RuntimeError):
    """A deliberately redacted Hermes transport failure."""


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
            if event_type not in {"gateway.ready", "message.delta", "message.complete"}:
                continue
            event_session = params.get("session_id")
            if event_session and event_session != session_id:
                continue
            payload = params.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if event_type == "gateway.ready":
                yield HermesRpcEvent("gateway.ready")
            elif event_type == "message.delta":
                yield HermesRpcEvent("message.delta", str(payload.get("text") or ""))
            else:
                yield HermesRpcEvent(
                    "message.complete", str(payload.get("text") or "")
                )
                return

    @staticmethod
    def _decode(raw: object) -> dict:
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
            if isinstance(params, dict) and params.get("type") in {
                "gateway.ready",
                "message.delta",
                "message.complete",
            }:
                return

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
