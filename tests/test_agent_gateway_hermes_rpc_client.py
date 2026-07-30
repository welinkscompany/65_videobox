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


def test_expired_ticket_before_prompt_acceptance_is_refreshed_once() -> None:
    class TicketHttp(_Http):
        def __init__(self) -> None:
            super().__init__()
            self.ticket_count = 0

        async def post(self, path: str, json: dict | None = None):
            self.posts.append((path, json))
            if path == "/auth/password-login":
                return _Response({"ok": True, "next": ""})
            self.ticket_count += 1
            return _Response(
                {"ticket": f"ticket-{self.ticket_count}", "ttl_seconds": 30}
            )

    class ExpiredTicketSocket:
        async def __aenter__(self):
            raise HermesTransportError("hermes_ticket_expired")

        async def __aexit__(self, *_):
            return None

    http = TicketHttp()
    accepted = _WebSocket(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
            {"jsonrpc": "2.0", "id": 2, "result": {"status": "accepted"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "sid-1",
                    "payload": {"status": "complete", "text": "answer"},
                },
            },
        ]
    )
    sockets = [ExpiredTicketSocket(), accepted]
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: sockets.pop(0),
    )

    async def collect():
        return [
            event
            async for event in client.stream_prompt(text="x", run_id="run-a")
        ]

    events = asyncio.run(collect())
    assert http.ticket_count == 2
    assert [(event.event_type, event.text) for event in events] == [
        ("message.complete", "answer")
    ]


def test_repeated_expired_ticket_uses_stable_public_code() -> None:
    http = _Http()
    sockets = [
        _WebSocket(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": "ticket_expired"},
                },
            ]
        ),
        _WebSocket(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-2"}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": "ticket_expired"},
                },
            ]
        ),
    ]
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: sockets.pop(0),
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_ticket_expired$") as exc:
        asyncio.run(collect())
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 2
    assert "PRIVATE" not in str(exc.value)


def test_login_unauthorized_is_unavailable_without_ticket_retry() -> None:
    class UnauthorizedResponse(_Response):
        def raise_for_status(self) -> None:
            error = RuntimeError("PRIVATE login failure")
            error.response = type("Response", (), {"status_code": 401})()
            raise error

    class UnauthorizedHttp(_Http):
        async def post(self, path: str, json: dict | None = None):
            self.posts.append((path, json))
            return UnauthorizedResponse({})

    http = UnauthorizedHttp()
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: pytest.fail(
            "websocket must not open"
        ),
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_unavailable$") as exc:
        asyncio.run(collect())
    assert len(http.posts) == 1
    assert "PRIVATE" not in str(exc.value)


def test_prompt_acceptance_must_be_exact_before_events() -> None:
    http = _Http()
    websocket = _WebSocket(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
            {"jsonrpc": "2.0", "id": 2, "result": {"status": "streaming"}},
        ]
    )
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_invalid_response$"):
        asyncio.run(collect())
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 1


def test_ticket_expiry_after_session_create_retries_before_prompt_acceptance() -> None:
    http = _Http()
    sockets = [
        _WebSocket(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": "ticket_expired"},
                },
            ]
        ),
        _WebSocket(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-2"}},
                {"jsonrpc": "2.0", "id": 2, "result": {"status": "accepted"}},
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "message.complete",
                        "session_id": "sid-2",
                        "payload": {"status": "complete", "text": "answer"},
                    },
                },
            ]
        ),
    ]
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: sockets.pop(0),
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    events = asyncio.run(collect())
    assert [(event.event_type, event.text) for event in events] == [
        ("message.complete", "answer")
    ]
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 2


def test_session_create_ticket_expiry_refreshes_once_before_prompt_acceptance() -> None:
    http = _Http()
    sockets = [
        _WebSocket(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": "ticket_expired",
                        "detail": "PRIVATE stale ticket",
                    },
                },
            ]
        ),
        _WebSocket(
            [
                {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-2"}},
                {"jsonrpc": "2.0", "id": 2, "result": {"status": "accepted"}},
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "message.complete",
                        "session_id": "sid-2",
                        "payload": {"status": "complete", "text": "answer"},
                    },
                },
            ]
        ),
    ]
    ws_calls = 0

    def websocket_factory(*_args, **_kwargs):
        nonlocal ws_calls
        ws_calls += 1
        return sockets.pop(0)

    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=websocket_factory,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    events = asyncio.run(collect())
    assert [(event.event_type, event.text) for event in events] == [
        ("message.complete", "answer")
    ]
    assert ws_calls == 2
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 2


def test_repeated_session_create_ticket_expiry_uses_stable_public_code() -> None:
    http = _Http()
    sockets = [
        _WebSocket(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": "ticket_expired",
                        "detail": "PRIVATE stale ticket",
                    },
                },
            ]
        ),
        _WebSocket(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": "ticket_expired",
                        "detail": "PRIVATE stale ticket again",
                    },
                },
            ]
        ),
    ]
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: sockets.pop(0),
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_ticket_expired$") as exc:
        asyncio.run(collect())
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 2
    assert "PRIVATE" not in str(exc.value)


def test_generic_session_create_error_is_unavailable_without_ticket_retry() -> None:
    http = _Http()
    websocket = _WebSocket(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": "provider_unavailable",
                    "detail": "PRIVATE provider detail",
                },
            },
        ]
    )
    ws_calls = 0

    def websocket_factory(*_args, **_kwargs):
        nonlocal ws_calls
        ws_calls += 1
        return websocket

    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=websocket_factory,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_unavailable$") as exc:
        asyncio.run(collect())
    assert ws_calls == 1
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 1
    assert "PRIVATE" not in str(exc.value)


def test_connection_loss_after_prompt_acceptance_is_never_retried() -> None:
    class AcceptedThenLost(_WebSocket):
        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            raise ConnectionError("PRIVATE provider disconnect")

    http = _Http()
    websocket = AcceptedThenLost(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
            {"jsonrpc": "2.0", "id": 2, "result": {"status": "accepted"}},
        ]
    )
    ws_calls = 0

    def websocket_factory(*_args, **_kwargs):
        nonlocal ws_calls
        ws_calls += 1
        return websocket

    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=websocket_factory,
    )

    async def collect():
        return [
            event
            async for event in client.stream_prompt(text="x", run_id="run-a")
        ]

    with pytest.raises(HermesTransportError, match="^hermes_unavailable$") as exc:
        asyncio.run(collect())
    assert ws_calls == 1
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 1
    assert "PRIVATE" not in str(exc.value)


def test_connection_loss_before_prompt_acceptance_is_unavailable_without_ticket_retry() -> None:
    class LostBeforeAcceptance(_WebSocket):
        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            raise ConnectionError(
                "PRIVATE provider disconnect password=p ticket=fresh-ticket"
            )

    http = _Http()
    websocket = LostBeforeAcceptance(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
        ]
    )
    ws_calls = 0

    def websocket_factory(*_args, **_kwargs):
        nonlocal ws_calls
        ws_calls += 1
        return websocket

    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=websocket_factory,
    )

    async def collect():
        return [
            event
            async for event in client.stream_prompt(text="x", run_id="run-a")
        ]

    with pytest.raises(HermesTransportError, match="^hermes_unavailable$") as exc:
        asyncio.run(collect())
    assert ws_calls == 1
    assert http.posts.count(("/api/auth/ws-ticket", None)) == 1
    assert [item["method"] for item in websocket.sent] == [
        "session.create",
        "prompt.submit",
    ]
    assert websocket.closed is True
    assert "PRIVATE" not in str(exc.value)
    assert "password" not in str(exc.value)
    assert "ticket" not in str(exc.value)


def test_explicit_interrupt_targets_only_the_active_upstream_session() -> None:
    class InterruptibleSocket(_WebSocket):
        def __init__(self) -> None:
            super().__init__(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"session_id": "sid-1"},
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {"status": "accepted"},
                    },
                ]
            )
            self.interrupted = asyncio.Event()
            self.prompt_submitted = asyncio.Event()

        async def send(self, payload: str) -> None:
            await super().send(payload)
            if self.sent[-1].get("method") == "prompt.submit":
                self.prompt_submitted.set()
            if self.sent[-1].get("method") == "session.interrupt":
                self.interrupted.set()

        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            await self.interrupted.wait()
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "event",
                    "params": {
                        "type": "message.complete",
                        "session_id": "sid-1",
                        "payload": {"status": "interrupted", "text": ""},
                    },
                }
            )

    http = _Http()
    websocket = InterruptibleSocket()
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def scenario():
        async def collect():
            return [
                event
                async for event in client.stream_prompt(
                    text="x", run_id="run-active"
                )
            ]

        task = asyncio.create_task(collect())
        prompt_wait = asyncio.create_task(websocket.prompt_submitted.wait())
        done, _pending = await asyncio.wait(
            {task, prompt_wait},
            timeout=0.5,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            await task
        assert prompt_wait in done
        assert await client.interrupt(run_id="run-missing") is False
        assert await client.interrupt(run_id="run-active") is True
        with pytest.raises(HermesTransportError, match="^hermes_interrupted$"):
            await task
        assert await client.interrupt(run_id="run-active") is False

    asyncio.run(scenario())
    assert [item["method"] for item in websocket.sent] == [
        "session.create",
        "prompt.submit",
        "session.interrupt",
    ]


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
            {"jsonrpc": "2.0", "id": 2, "result": {"status": "accepted"}},
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
                    "payload": {"status": "complete", "text": "안녕하세요"},
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
    upstream_rpc = json.dumps(websocket.sent, sort_keys=True)
    assert "capability" not in upstream_rpc
    assert "private_key" not in upstream_rpc
    assert "publish_proposal" not in upstream_rpc
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

    with pytest.raises(HermesTransportError, match="^hermes_invalid_response$") as exc:
        asyncio.run(collect())
    assert "leak" not in str(exc.value)


def test_oversized_rpc_frame_is_rejected_before_json_decode() -> None:
    http = _Http()
    websocket = _WebSocket([])
    websocket.messages = ['{"jsonrpc":"2.0","padding":"' + ("x" * 64_000) + '"}']
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_invalid_response$"):
        asyncio.run(collect())


def test_tool_event_before_session_creation_is_rejected() -> None:
    http = _Http()
    websocket = _WebSocket(
        [
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "tool.start",
                    "payload": {"provider": "secret"},
                },
            }
        ]
    )
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def collect():
        return [event async for event in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError, match="^hermes_invalid_response$") as exc:
        asyncio.run(collect())
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://videobox-hermes-yujin:9120",
        "http://evil.example:9120",
        "http://user:pass@videobox-hermes-yujin:9120",
        "http://videobox-hermes-yujin:9121",
        "http://videobox-hermes-yujin:9120/path",
        "http://videobox-hermes-yujin:9120?next=http://evil",
        "http://videobox-hermes-yujin:9120#fragment",
    ],
)
def test_hermes_ssrf_matrix_is_rejected_before_transport(url: str) -> None:
    calls = []
    with pytest.raises(ValueError, match="internal"):
        HermesRpcClient(
            base_url=url,
            username="u",
            password="p",
            http_client_factory=lambda **kwargs: calls.append(kwargs),
        )
    assert calls == []


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "message.delta",
            "payload": {"text": "wrong session"},
        },
        {
            "type": "message.complete",
            "payload": {"status": "complete", "text": "wrong session"},
        },
        {
            "type": "tool.complete",
            "session_id": "sid-1",
            "payload": {"provider": "secret", "path": "C:/private"},
        },
        {
            "type": "message.complete",
            "session_id": "sid-1",
            "payload": {"status": "interrupted", "text": "partial"},
        },
        {
            "type": "message.complete",
            "session_id": "sid-1",
            "payload": {"status": "complete", "text": ""},
        },
    ],
)
def test_unsafe_or_non_success_prompt_events_fail_closed_and_redacted(event: dict) -> None:
    http = _Http()
    websocket = _WebSocket(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"session_id": "sid-1"}},
            {"jsonrpc": "2.0", "method": "event", "params": event},
        ]
    )
    client = HermesRpcClient(
        base_url="http://videobox-hermes-yujin:9120",
        username="u",
        password="p",
        http_client_factory=lambda **_: http,
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    async def collect():
        return [item async for item in client.stream_prompt(text="x")]

    with pytest.raises(HermesTransportError) as exc:
        asyncio.run(collect())
    assert "secret" not in str(exc.value)
    assert "C:/private" not in str(exc.value)
