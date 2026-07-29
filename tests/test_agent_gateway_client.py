from __future__ import annotations

import asyncio

import pytest

from videobox_api.agent_gateway_client import AgentGatewayClient
from videobox_api.agent_gateway_client import AgentGatewayUnavailable


SERVICE_TOKEN = "workspace-service-token-that-is-at-least-32"


class _Response:
    def __init__(self) -> None:
        self.lines = [
            '{"event_type":"text_delta","text":"answer"}',
            '{"event_type":"run_completed","text":"answer"}',
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class _Http:
    def __init__(self) -> None:
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def stream(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return _Response()

    async def delete(self, path, **kwargs):
        self.calls.append(("DELETE", path, kwargs))
        return _PostResponse()


class _PostResponse:
    def __init__(self, payload=None) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_prepare_run_keeps_ticket_in_private_attach_header() -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        if path == "/internal/hermes/runs":
            return _PostResponse(
                {
                    "run_id": "run-a",
                    "attach_context": "a" * 64,
                    "expires_in_seconds": 30,
                }
            )
        return _PostResponse()

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )
    context = {
        "schema_version": "videobox.yujin-context.v1",
        "project_id": "project-a",
    }

    asyncio.run(
        client.prepare_run(
            project_id="project-a",
            conversation_id="conversation-a",
            run_id="run-a",
            session_id="session-a",
            session_revision=7,
            asset_index_revision=13,
            context=context,
        )
    )
    asyncio.run(client.release_run(run_id="run-a"))

    assert [call[1] for call in http.calls] == [
        "/internal/hermes/runs",
        "/internal/hermes/runs/run-a/context",
        "/internal/hermes/runs/run-a",
    ]
    attach = http.calls[1][2]
    assert attach["headers"]["X-VideoBox-Attach-Ticket"] == "a" * 64
    assert "attach_context" not in str(attach["json"])
    assert attach["json"]["context"] == context


def test_cancelled_prepare_releases_created_reservation() -> None:
    class _CancellingHttp(_Http):
        async def __aexit__(self, *_):
            await asyncio.sleep(0)
            return None

    http = _CancellingHttp()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        if path == "/internal/hermes/runs":
            return _PostResponse(
                {
                    "run_id": "run-cancelled",
                    "attach_context": "b" * 64,
                    "expires_in_seconds": 30,
                }
            )
        asyncio.current_task().cancel()
        return _PostResponse()

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            await client.prepare_run(
                project_id="project-a",
                conversation_id="conversation-a",
                run_id="run-cancelled",
                session_id="session-a",
                session_revision=7,
                asset_index_revision=13,
                context={
                    "schema_version": "videobox.yujin-context.v1",
                    "project_id": "project-a",
                },
            )

    asyncio.run(scenario())

    assert [call[0:2] for call in http.calls] == [
        ("POST", "/internal/hermes/runs"),
        ("POST", "/internal/hermes/runs/run-cancelled/context"),
        ("DELETE", "/internal/hermes/runs/run-cancelled"),
    ]


def test_cancel_run_uses_the_authenticated_internal_interrupt_endpoint() -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        return _PostResponse()

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    asyncio.run(client.cancel_run(run_id="run-active"))

    assert http.calls == [
        (
            "POST",
            "/internal/hermes/runs/run-active/cancel",
            {"headers": {"Authorization": f"Bearer {SERVICE_TOKEN}"}},
        )
    ]


def test_internal_url_and_service_credential_only() -> None:
    http = _Http()
    factory_calls = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return http

    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=factory,
    )

    async def collect():
        return [
            event
            async for event in client.stream_run(
                session_id="s", client_message_id="c", text="hello"
            )
        ]

    events = asyncio.run(collect())
    assert [(item.event_type, item.text) for item in events] == [
        ("text_delta", "answer"),
        ("run_completed", "answer"),
    ]
    assert factory_calls == [
        {"base_url": "http://videobox-agent-gateway:8081", "timeout": 35.0}
    ]
    assert http.calls[0][2]["headers"] == {
        "Authorization": f"Bearer {SERVICE_TOKEN}"
    }
    assert http.calls[0][1] == "/internal/hermes/runs/s/stream"
    assert set(http.calls[0][2]["json"]) == {
        "client_message_id",
        "text",
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://videobox-agent-gateway:8081",
        "http://evil.example:8081",
        "http://user:pass@videobox-agent-gateway:8081",
        "http://videobox-agent-gateway:8082",
        "http://videobox-agent-gateway:8081/path",
        "http://videobox-agent-gateway:8081?redirect=http://evil",
        "http://videobox-agent-gateway:8081#fragment",
    ],
)
def test_ssrf_matrix_rejected_before_transport(url: str) -> None:
    calls = []
    with pytest.raises(ValueError, match="internal"):
        AgentGatewayClient(
            base_url=url,
            service_token=SERVICE_TOKEN,
            http_client_factory=lambda **kwargs: calls.append(kwargs),
        )
    assert calls == []


@pytest.mark.parametrize(
    "line",
    [
        '{"event_type":"text_delta","text":"ok","provider":"leak"}',
        '{"event_type":"unknown","text":"ignored"}',
        '{"event_type":"blocked","text":"must-be-empty","retryable":true}',
        '{"event_type":"blocked","text":"","retryable":"true"}',
        "not-json",
    ],
)
def test_malformed_or_extra_upstream_frames_fail_closed(line: str) -> None:
    response = _Response()
    response.lines = [line]
    http = _Http()
    http.stream = lambda *_args, **_kwargs: response
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    async def collect():
        return [
            event
            async for event in client.stream_run(
                session_id="s", client_message_id="c", text="hello"
            )
        ]

    with pytest.raises(AgentGatewayUnavailable, match="unavailable"):
        asyncio.run(collect())


def test_oversized_upstream_line_fails_closed() -> None:
    response = _Response()
    response.lines = [
        '{"event_type":"text_delta","text":"' + ("x" * 70_000) + '"}'
    ]
    http = _Http()
    http.stream = lambda *_args, **_kwargs: response
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    async def collect():
        return [event async for event in client.stream_run(
            session_id="s", client_message_id="c", text="hello"
        )]

    with pytest.raises(AgentGatewayUnavailable):
        asyncio.run(collect())


@pytest.mark.parametrize("token", ["a" * 32, "abcd" * 8])
def test_low_entropy_service_token_is_rejected_before_transport(token: str) -> None:
    with pytest.raises(ValueError, match="service_token"):
        AgentGatewayClient(
            base_url="http://videobox-agent-gateway:8081",
            service_token=token,
            http_client_factory=lambda **_: pytest.fail("transport called"),
        )


def test_cumulative_delta_text_is_bounded_even_when_each_frame_is_small() -> None:
    response = _Response()
    response.lines = [
        '{"event_type":"text_delta","text":"' + ("x" * 31_000) + '"}'
        for _ in range(7)
    ]
    http = _Http()
    http.stream = lambda *_args, **_kwargs: response
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    async def collect():
        return [
            event
            async for event in client.stream_run(
                session_id="s", client_message_id="c", text="hello"
            )
        ]

    with pytest.raises(AgentGatewayUnavailable):
        asyncio.run(collect())


def test_completion_text_must_equal_the_assembled_delta_truth() -> None:
    response = _Response()
    response.lines = [
        '{"event_type":"text_delta","text":"safe"}',
        '{"event_type":"run_completed","text":"different"}',
    ]
    http = _Http()
    http.stream = lambda *_args, **_kwargs: response
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )

    async def collect():
        return [
            event
            async for event in client.stream_run(
                session_id="s", client_message_id="c", text="hello"
            )
        ]

    with pytest.raises(AgentGatewayUnavailable):
        asyncio.run(collect())
