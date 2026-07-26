from __future__ import annotations

import asyncio
import json

import pytest

from videobox_agent_gateway.hermes_rpc_client import (
    HermesRpcClient,
    HermesTransportError,
)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _Http:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, path: str, json: dict | None = None):
        self.posts.append((path, json))
        return _Response(
            {"ok": True, "next": ""}
            if path == "/auth/password-login"
            else {"ticket": "fresh ticket", "ttl_seconds": 30}
        )


class _WebSocket:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = [json.dumps(item) for item in messages]
        self.sent: list[dict] = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def recv(self) -> str:
        return self.messages.pop(0)


def test_official_password_cookie_ticket_and_rpc_order_are_allowlisted() -> None:
    http = _Http()
    websocket = _WebSocket(
        [
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {"type": "gateway.ready", "payload": {"skin": "x"}},
            },
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
            {"jsonrpc": "2.0", "id": 2, "result": {"status": "streaming"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "tool.complete",
                    "session_id": "sid-1",
                    "payload": {"provider": "secret", "path": "C:/private"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.delta",
                    "session_id": "sid-1",
                    "payload": {"text": "안녕"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "sid-1",
                    "payload": {"text": "안녕하세요"},
                },
            },
        ]
    )
    ws_calls: list[tuple[str, dict]] = []

    def ws_factory(url: str, **kwargs):
        ws_calls.append((url, kwargs))
        return websocket

    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="gateway-user",
        password="never-log-this",
        http_client_factory=lambda **_: http,
        websocket_factory=ws_factory,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="질문")]

    events = asyncio.run(collect())
    assert http.posts == [
        (
            "/auth/password-login",
            {
                "provider": "basic",
                "username": "gateway-user",
                "password": "never-log-this",
                "next": "",
            },
        ),
        ("/api/auth/ws-ticket", None),
    ]
    assert ws_calls[0][0].endswith("/api/ws?ticket=fresh%20ticket")
    assert [item["method"] for item in websocket.sent] == [
        "session.create",
        "prompt.submit",
    ]
    assert websocket.sent[0]["id"] == 1
    assert websocket.sent[1] == {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "prompt.submit",
        "params": {"session_id": "sid-1", "text": "질문"},
    }
    assert [(item.event_type, item.text) for item in events] == [
        ("message.delta", "안녕"),
        ("message.complete", "안녕하세요"),
    ]
    assert websocket.closed is True


def test_protocol_error_is_redacted() -> None:
    http = _Http()
    websocket = _WebSocket([{"not": "json-rpc", "password": "leak"}])
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="hermes_protocol_invalid") as exc:
        asyncio.run(collect())
    assert "leak" not in str(exc.value)
