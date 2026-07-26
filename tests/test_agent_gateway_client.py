from __future__ import annotations

import asyncio

import pytest

from videobox_api.agent_gateway_client import AgentGatewayClient
from videobox_api.agent_gateway_client import AgentGatewayUnavailable


SERVICE_TOKEN = "workspace-service-token-that-is-at-least-32"


class _Response:
    def __init__(self) -> None:
        self.lines = [
            '{"event_type":"text_delta","text":"a"}',
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
        ("text_delta", "a"),
        ("run_completed", "answer"),
    ]
    assert factory_calls == [
        {"base_url": "http://videobox-agent-gateway:8081", "timeout": 35.0}
    ]
    assert http.calls[0][2]["headers"] == {
        "Authorization": f"Bearer {SERVICE_TOKEN}"
    }
    assert set(http.calls[0][2]["json"]) == {
        "session_id",
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
