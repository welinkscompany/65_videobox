from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from videobox_agent_gateway.hermes_rpc_client import HermesRpcEvent
from videobox_agent_gateway.main import _stream_public_lines, create_app


class _Hermes:
    calls = 0

    async def stream_prompt(self, *, text: str):
        self.calls += 1
        yield HermesRpcEvent("message.delta", "a")
        yield HermesRpcEvent("message.complete", "answer")


def test_gateway_has_only_health_and_authenticated_narrow_stream() -> None:
    hermes = _Hermes()
    token = "service-secret-that-is-at-least-32-bytes"
    app = create_app(hermes_client=hermes, service_token=token)
    client = TestClient(app)
    assert app.openapi_url is None
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200
    body = {"session_id": "s", "client_message_id": "c", "text": "hello"}
    assert client.post("/internal/hermes/stream", json=body).status_code == 401
    assert hermes.calls == 0
    rejected = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={**body, "tool_name": "shell", "provider": "x", "path": "C:/db"},
    )
    assert rejected.status_code == 422
    assert hermes.calls == 0
    response = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text.splitlines() == [
        '{"event_type":"text_delta","text":"answer"}',
        '{"event_type":"run_completed","text":"answer"}',
    ]
    assert hermes.calls == 1


def test_unconfigured_gateway_remains_health_only() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert paths == {"/health"}


def test_validation_and_unsafe_output_are_redacted() -> None:
    sentinel = "do-not-reflect-this-secret"

    class UnsafeHermes:
        async def stream_prompt(self, *, text: str):
            yield HermesRpcEvent("message.delta", "safe prefix")
            yield HermesRpcEvent(
                "message.complete",
                f"password={sentinel} path=/opt/data/private provider=openrouter",
            )

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=UnsafeHermes(), service_token=token))
    headers = {"Authorization": f"Bearer {token}"}
    invalid = client.post(
        "/internal/hermes/stream",
        headers=headers,
        json={
            "session_id": "s",
            "client_message_id": "c",
            "text": "hello",
            "secret": sentinel,
        },
    )
    assert invalid.status_code == 422
    assert sentinel not in invalid.text
    response = client.post(
        "/internal/hermes/stream",
        headers=headers,
        json={"session_id": "s", "client_message_id": "c", "text": "hello"},
    )
    assert response.text.splitlines() == [
        '{"event_type":"blocked","text":"","retryable":true}'
    ]
    assert sentinel not in response.text
    assert "/opt/data" not in response.text


def test_unsafe_output_split_across_events_is_quarantined() -> None:
    class SplitHermes:
        async def stream_prompt(self, *, text: str):
            yield HermesRpcEvent("message.delta", "pass")
            yield HermesRpcEvent("message.delta", "word=private")
            yield HermesRpcEvent("message.complete", "never publish")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=SplitHermes(), service_token=token))
    response = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": "s", "client_message_id": "c", "text": "hello"},
    )
    assert response.text == '{"event_type":"blocked","text":"","retryable":true}\n'
    assert "private" not in response.text


def test_excessive_empty_event_stream_is_bounded() -> None:
    class NoisyHermes:
        async def stream_prompt(self, *, text: str):
            for _ in range(513):
                yield HermesRpcEvent("message.delta", "")
            yield HermesRpcEvent("message.complete", "answer")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=NoisyHermes(), service_token=token))
    response = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": "s", "client_message_id": "c", "text": "hello"},
    )
    assert response.text == '{"event_type":"blocked","text":"","retryable":true}\n'


def test_safe_prefix_streams_before_hermes_completion_barrier() -> None:
    safe_text = "x" * 300

    class BarrierHermes:
        def __init__(self) -> None:
            self.delta_sent = asyncio.Event()
            self.release_completion = asyncio.Event()

        async def stream_prompt(self, *, text: str):
            self.delta_sent.set()
            yield HermesRpcEvent("message.delta", safe_text)
            await self.release_completion.wait()
            yield HermesRpcEvent("message.complete", safe_text)

    async def scenario() -> tuple[dict, list[dict]]:
        hermes = BarrierHermes()
        lines = _stream_public_lines(hermes, text="hello")
        first = json.loads(
            (await asyncio.wait_for(anext(lines), timeout=1)).decode()
        )
        assert hermes.delta_sent.is_set()
        assert not hermes.release_completion.is_set()
        hermes.release_completion.set()
        rest = [json.loads(line.decode()) async for line in lines]
        return first, rest

    first, rest = asyncio.run(scenario())
    assert first == {"event_type": "text_delta", "text": "x" * 44}
    assert "".join(
        event["text"] for event in [first, *rest]
        if event["event_type"] == "text_delta"
    ) == safe_text
    assert rest[-1] == {"event_type": "run_completed", "text": safe_text}


@pytest.mark.parametrize(
    "chunks",
    [
        ("Author", "ization: Bearer private"),
        ("Coo", "kie: session=private"),
        ("Bea", "rer private"),
        ("to", "ken=private"),
        ("/opt/", "data/private"),
        ("/video", "box-data/private"),
        ("/e", "tc/passwd"),
        ("provi", "der=openrouter"),
    ],
)
def test_split_sensitive_markers_are_blocked_before_any_marker_bytes_escape(
    chunks: tuple[str, str],
) -> None:
    safe_prefix = ("s" * 300) + "\n"

    class SplitHermes:
        async def stream_prompt(self, *, text: str):
            yield HermesRpcEvent("message.delta", safe_prefix + chunks[0])
            yield HermesRpcEvent("message.delta", chunks[1])
            yield HermesRpcEvent("message.complete", safe_prefix + "".join(chunks))

    async def scenario() -> list[dict]:
        return [
            json.loads(line.decode())
            async for line in _stream_public_lines(SplitHermes(), text="hello")
        ]

    events = asyncio.run(scenario())
    assert events[-1] == {
        "event_type": "blocked",
        "text": "",
        "retryable": True,
    }
    published = "".join(
        event["text"]
        for event in events
        if event["event_type"] == "text_delta"
    )
    assert published and set(published) == {"s"}
    assert chunks[0] not in published
    assert chunks[1] not in published


def test_single_oversized_hermes_chunk_fails_closed() -> None:
    class OversizedHermes:
        async def stream_prompt(self, *, text: str):
            yield HermesRpcEvent("message.delta", "x" * 200_001)
            yield HermesRpcEvent("message.complete", "x" * 200_001)

    async def scenario() -> list[dict]:
        return [
            json.loads(line.decode())
            async for line in _stream_public_lines(OversizedHermes(), text="hello")
        ]

    assert asyncio.run(scenario()) == [
        {"event_type": "blocked", "text": "", "retryable": True}
    ]


def test_public_delta_frames_are_chunked_below_api_client_text_limit() -> None:
    safe_text = "x" * 63_000

    class LargeHermes:
        async def stream_prompt(self, *, text: str):
            yield HermesRpcEvent("message.delta", safe_text)
            yield HermesRpcEvent("message.complete", safe_text)

    async def scenario() -> list[dict]:
        return [
            json.loads(line.decode())
            async for line in _stream_public_lines(LargeHermes(), text="hello")
        ]

    events = asyncio.run(scenario())
    deltas = [
        event["text"] for event in events if event["event_type"] == "text_delta"
    ]
    assert max(len(delta.encode("utf-8")) for delta in deltas) <= 32_000
    assert "".join(deltas) == safe_text
    assert events[-1] == {"event_type": "run_completed", "text": safe_text}


@pytest.mark.parametrize(
    "token",
    [
        "short",
        "changeme-changeme-changeme-changeme",
        "REPLACE_ME_123456789012345678901234",
        "a" * 32,
        "abcd" * 8,
    ],
)
def test_weak_or_placeholder_service_tokens_are_rejected(token: str) -> None:
    with pytest.raises(ValueError, match="service_token"):
        create_app(hermes_client=_Hermes(), service_token=token)
