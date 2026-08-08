from __future__ import annotations

import asyncio
import traceback

import pytest

from videobox_api.agent_gateway_client import AgentGatewayClient
from videobox_api.agent_gateway_client import AgentGatewayReservation
from videobox_api.agent_gateway_client import AgentGatewayUnavailable
from videobox_api.yujin_memory_service import ApprovedMemoryStoreRequest
from videobox_api.yujin_memory_service import GatewayMemoryDeleteRequest
from videobox_api.yujin_memory_service import GatewayMemorySearchRequest


SERVICE_TOKEN = "workspace-service-token-that-is-at-least-32"
NOW_EPOCH = 2_000_000_000
PUBLISH_TOKEN = "header.publish.signature"


def _reservation_payload(
    *,
    run_id: str = "run-a",
    expires_in_seconds: int = 30,
    expires_at: int = NOW_EPOCH + 300,
    **patch,
) -> dict:
    payload = {
        "run_id": run_id,
        "attach_context": "a" * 64,
        "expires_in_seconds": expires_in_seconds,
        "read_capability_token": "header.read.signature",
        "capabilities": [
            {
                "capability_id": "cap-read",
                "action": "read_context",
                "expires_at": expires_at,
            },
            {
                "capability_id": "cap-publish",
                "action": "publish_proposal",
                "expires_at": expires_at,
            },
        ],
    }
    payload.update(patch)
    return payload


class _Response:
    def __init__(self) -> None:
        self.lines = [
            '{"event_type":"text_delta","text":"answer"}',
            (
                '{"event_type":"run_completed","text":"answer",'
                f'"publish_capability_token":"{PUBLISH_TOKEN}"'
                "}"
            ),
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


def test_reserve_then_attach_keeps_ticket_in_private_attach_header() -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        if path == "/internal/hermes/runs":
            return _PostResponse(_reservation_payload())
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

    reservation = asyncio.run(
        client.reserve_run(
            project_id="project-a",
            conversation_id="conversation-a",
            run_id="run-a",
            session_id="session-a",
            session_revision=7,
            asset_index_revision=13,
        )
    )
    assert isinstance(reservation, AgentGatewayReservation)
    assert reservation.expires_in_seconds == 30
    assert tuple(item.action for item in reservation.capabilities) == (
        "read_context",
        "publish_proposal",
    )
    asyncio.run(
        client.attach_run_context(
            project_id="project-a",
            conversation_id="conversation-a",
            run_id="run-a",
            session_id="session-a",
            session_revision=7,
            asset_index_revision=13,
            reservation=reservation,
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


def test_cancelled_attach_propagates_without_hidden_cleanup_owner() -> None:
    class _CancellingHttp(_Http):
        async def __aexit__(self, *_):
            await asyncio.sleep(0)
            return None

    http = _CancellingHttp()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        if path == "/internal/hermes/runs":
            return _PostResponse(
                _reservation_payload(
                    run_id="run-cancelled",
                    attach_context="b" * 64,
                )
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
        reservation = await client.reserve_run(
            project_id="project-a",
            conversation_id="conversation-a",
            run_id="run-cancelled",
            session_id="session-a",
            session_revision=7,
            asset_index_revision=13,
        )
        with pytest.raises(asyncio.CancelledError):
            await client.attach_run_context(
                project_id="project-a",
                conversation_id="conversation-a",
                run_id="run-cancelled",
                session_id="session-a",
                session_revision=7,
                asset_index_revision=13,
                reservation=reservation,
                context={
                    "schema_version": "videobox.yujin-context.v1",
                    "project_id": "project-a",
                },
            )

    asyncio.run(scenario())

    assert [call[0:2] for call in http.calls] == [
        ("POST", "/internal/hermes/runs"),
        ("POST", "/internal/hermes/runs/run-cancelled/context"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        _reservation_payload(expires_in_seconds=0),
        _reservation_payload(expires_in_seconds=31),
        _reservation_payload(expires_at=NOW_EPOCH),
        _reservation_payload(
            capabilities=[
                {
                    "capability_id": "same",
                    "action": "read_context",
                    "expires_at": NOW_EPOCH + 300,
                },
                {
                    "capability_id": "same",
                    "action": "publish_proposal",
                    "expires_at": NOW_EPOCH + 300,
                },
            ]
        ),
        _reservation_payload(publish_capability_token="must-not-exist"),
        _reservation_payload(read_capability_token="not-a-compact-token"),
    ],
)
def test_reserve_rejects_malformed_or_authority_expanding_shape(
    payload: dict,
) -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        return _PostResponse(payload)

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
        epoch_seconds=lambda: NOW_EPOCH,
    )

    with pytest.raises(
        AgentGatewayUnavailable,
        match="^agent_gateway_unavailable$",
    ):
        asyncio.run(
            client.reserve_run(
                project_id="project-a",
                conversation_id="conversation-a",
                run_id="run-a",
                session_id="session-a",
                session_revision=7,
                asset_index_revision=13,
            )
        )

    assert [call[0:2] for call in http.calls] == [
        ("POST", "/internal/hermes/runs"),
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
    assert events[0].publish_capability_token is None
    assert events[1].publish_capability_token == PUBLISH_TOKEN
    assert PUBLISH_TOKEN not in repr(events[1])
    # 로컬 모델 대화가 35초를 넘긴다. 기본값을 그대로 쓰는지 확인한다.
    assert factory_calls == [
        {"base_url": "http://videobox-agent-gateway:8081", "timeout": 300.0}
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
        (
            '{"event_type":"text_delta","text":"ok",'
            f'"publish_capability_token":"{PUBLISH_TOKEN}"'
            "}"
        ),
        (
            '{"event_type":"blocked","text":"","retryable":true,'
            f'"publish_capability_token":"{PUBLISH_TOKEN}"'
            "}"
        ),
        '{"event_type":"run_completed","text":""}',
        (
            '{"event_type":"run_completed","text":"",'
            f'"publish_capability_token":"{PUBLISH_TOKEN}",'
            '"provider":"leak"}'
        ),
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


def test_malformed_terminal_token_is_redacted_from_every_raised_surface() -> None:
    token_fragment = "publish-secret-fragment"
    response = _Response()
    response.lines = [
        (
            '{"event_type":"run_completed","text":"",'
            f'"publish_capability_token":"header.{token_fragment}.bad!"'
            "}"
        )
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
                session_id="s",
                client_message_id="c",
                text="hello",
            )
        ]

    with pytest.raises(AgentGatewayUnavailable) as caught:
        asyncio.run(collect())

    error = caught.value
    rendered = (
        str(error),
        repr(error),
        repr(error.__cause__),
        repr(error.__context__),
        "".join(
            traceback.format_exception(
                type(error),
                error,
                error.__traceback__,
            )
        ),
    )
    assert error.__cause__ is None
    assert error.__context__ is None
    assert all(token_fragment not in surface for surface in rendered)


def test_multiple_terminal_frames_fail_before_terminal_is_exposed() -> None:
    response = _Response()
    response.lines = [
        (
            '{"event_type":"run_completed","text":"",'
            f'"publish_capability_token":"{PUBLISH_TOKEN}"'
            "}"
        ),
        '{"event_type":"blocked","text":"","retryable":true}',
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
                session_id="s",
                client_message_id="c",
                text="hello",
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
        (
            '{"event_type":"run_completed","text":"different",'
            f'"publish_capability_token":"{PUBLISH_TOKEN}"'
            "}"
        ),
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


def test_memory_add_uses_authenticated_narrow_gateway_contract() -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        return _PostResponse(
            {
                "status": "stored",
                "memory_ref": "memory-private",
                "event_ref": None,
            }
        )

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )
    outcome = asyncio.run(
        client.add_approved_memory(
            ApprovedMemoryStoreRequest(
                text="빠른 컷을 선호합니다.",
                category="pacing",
                external_ref="ext-" + "a" * 64,
                operation_id="op-" + "b" * 64,
            )
        )
    )

    assert outcome.status == "stored"
    assert http.calls == [
        (
            "POST",
            "/internal/hermes/memory/add",
            {
                "headers": {
                    "Authorization": f"Bearer {SERVICE_TOKEN}"
                },
                "json": {
                    "text": "빠른 컷을 선호합니다.",
                    "category": "pacing",
                    "external_ref": "ext-" + "a" * 64,
                    "operation_id": "op-" + "b" * 64,
                },
            },
        )
    ]


def test_memory_delete_uses_authenticated_private_gateway_contract() -> None:
    http = _Http()

    async def post(path, **kwargs):
        http.calls.append(("POST", path, kwargs))
        return _PostResponse({"deleted": True})

    http.post = post
    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: http,
    )
    outcome = asyncio.run(
        client.delete_memory(
            GatewayMemoryDeleteRequest(
                memory_ref="memory-private",
                external_ref="ext-" + "a" * 64,
                allow_absent=False,
            )
        )
    )

    assert outcome.deleted is True
    assert http.calls == [
        (
            "POST",
            "/internal/hermes/memory/delete",
            {
                "headers": {
                    "Authorization": f"Bearer {SERVICE_TOKEN}"
                },
                "json": {
                    "memory_ref": "memory-private",
                    "external_ref": "ext-" + "a" * 64,
                    "allow_absent": False,
                },
            },
        )
    ]


def test_search_memory_decodes_a_real_json_gateway_body() -> None:
    """The gateway answers over HTTP, so `memories` arrives as a JSON array."""

    body = (
        '{"memories":[{"memory_ref":"memory-private",'
        '"text":"빠른 컷을 선호합니다.",'
        '"category":"pacing","external_ref":"ext-' + "a" * 64 + '"}]}'
    ).encode("utf-8")

    class Response:
        status_code = 200
        is_redirect = False
        content = body

        def raise_for_status(self) -> None:
            return None

        def json(self):
            import json

            return json.loads(body)

    class Http:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    client = AgentGatewayClient(
        base_url="http://videobox-agent-gateway:8081",
        service_token=SERVICE_TOKEN,
        http_client_factory=lambda **_: Http(),
    )
    result = asyncio.run(
        client.search_memory(
            GatewayMemorySearchRequest(query="편집 템포", limit=5)
        )
    )

    assert result.memories[0].text == "빠른 컷을 선호합니다."
    assert result.memories[0].category == "pacing"
