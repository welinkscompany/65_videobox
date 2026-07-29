from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from videobox_agent_gateway.hermes_rpc_client import HermesRpcEvent
from videobox_agent_gateway.main import _stream_public_lines, create_app


class _Hermes:
    calls = 0

    async def stream_prompt(self, *, text: str, run_id: str | None = None):
        self.calls += 1
        yield HermesRpcEvent("message.delta", "a")
        yield HermesRpcEvent("message.complete", "answer")


def _prepare_gateway_run(
    client: TestClient,
    *,
    token: str,
    run_id: str = "run-a",
) -> tuple[dict[str, str], str]:
    headers = {"Authorization": f"Bearer {token}"}
    identity = {
        "project_id": "project-a",
        "conversation_id": "conversation-a",
        "run_id": run_id,
        "session_id": "s",
        "session_revision": 1,
        "asset_index_revision": 0,
    }
    reservation = client.post(
        "/internal/hermes/runs",
        headers=headers,
        json=identity,
    )
    assert reservation.status_code == 200
    context = {
        "schema_version": "videobox.yujin-context.v1",
        "project_id": "project-a",
        "session_id": "s",
        "session_revision": 1,
        "asset_index_revision": 0,
        "timeline_id": "timeline-a",
        "timeline_version": "v001",
        "selected_script_id": None,
        "selected_segment_id": None,
        "segment_summaries": [],
        "media_candidates": [],
        "timeline_summary": {
            "duration_sec": 0.0,
            "track_count": 0,
            "clip_count": 0,
            "gap_count": 0,
        },
        "supported_controls": [],
    }
    attached = client.post(
        f"/internal/hermes/runs/{run_id}/context",
        headers={
            **headers,
            "X-VideoBox-Attach-Ticket": reservation.json()["attach_context"],
        },
        json={"identity": identity, "context": context},
    )
    assert attached.status_code == 204
    return headers, f"/internal/hermes/runs/{run_id}/stream"


def test_gateway_has_only_health_and_authenticated_bounded_run_flow() -> None:
    hermes = _Hermes()
    token = "service-secret-that-is-at-least-32-bytes"
    app = create_app(hermes_client=hermes, service_token=token)
    client = TestClient(app)
    assert app.openapi_url is None
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200
    body = {"client_message_id": "c", "text": "hello"}
    assert client.post("/internal/hermes/runs", json={
        "project_id": "project-a",
        "conversation_id": "conversation-a",
        "run_id": "run-a",
        "session_id": "s",
        "session_revision": 1,
        "asset_index_revision": 0,
    }).status_code == 401
    assert hermes.calls == 0
    headers, stream_path = _prepare_gateway_run(client, token=token)
    rejected = client.post(
        stream_path,
        headers=headers,
        json={**body, "tool_name": "shell", "provider": "x", "path": "C:/db"},
    )
    assert rejected.status_code == 422
    assert hermes.calls == 0
    response = client.post(
        stream_path,
        headers=headers,
        json=body,
    )
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text.splitlines() == [
        '{"event_type":"text_delta","text":"answer"}',
        '{"event_type":"run_completed","text":"answer"}',
    ]
    assert hermes.calls == 1


def test_gateway_cancel_is_authenticated_and_targets_only_the_named_run() -> None:
    class InterruptibleHermes(_Hermes):
        def __init__(self) -> None:
            self.interruptions: list[str] = []

        async def interrupt(self, *, run_id: str) -> bool:
            self.interruptions.append(run_id)
            return False

    hermes = InterruptibleHermes()
    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=hermes, service_token=token))

    assert client.post(
        "/internal/hermes/runs/run-a/cancel"
    ).status_code == 401
    response = client.post(
        "/internal/hermes/runs/run-a/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
    assert hermes.interruptions == ["run-a"]


def test_unconfigured_gateway_remains_health_only() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert paths == {"/health"}


def test_validation_and_unsafe_output_are_redacted() -> None:
    sentinel = "do-not-reflect-this-secret"

    class UnsafeHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            yield HermesRpcEvent("message.delta", "safe prefix")
            yield HermesRpcEvent(
                "message.complete",
                f"password={sentinel} path=/opt/data/private provider=openrouter",
            )

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=UnsafeHermes(), service_token=token))
    headers, stream_path = _prepare_gateway_run(client, token=token)
    invalid = client.post(
        stream_path,
        headers=headers,
        json={
            "client_message_id": "c",
            "text": "hello",
            "secret": sentinel,
        },
    )
    assert invalid.status_code == 422
    assert sentinel not in invalid.text
    response = client.post(
        stream_path,
        headers=headers,
        json={"client_message_id": "c", "text": "hello"},
    )
    assert response.text.splitlines() == [
        '{"event_type":"blocked","text":"","retryable":true}'
    ]
    assert sentinel not in response.text
    assert "/opt/data" not in response.text


def test_unsafe_output_split_across_events_is_quarantined() -> None:
    class SplitHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            yield HermesRpcEvent("message.delta", "pass")
            yield HermesRpcEvent("message.delta", "word=private")
            yield HermesRpcEvent("message.complete", "never publish")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=SplitHermes(), service_token=token))
    headers, stream_path = _prepare_gateway_run(client, token=token)
    response = client.post(
        stream_path,
        headers=headers,
        json={"client_message_id": "c", "text": "hello"},
    )
    assert response.text == '{"event_type":"blocked","text":"","retryable":true}\n'
    assert "private" not in response.text


def test_excessive_empty_event_stream_is_bounded() -> None:
    class NoisyHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            for _ in range(513):
                yield HermesRpcEvent("message.delta", "")
            yield HermesRpcEvent("message.complete", "answer")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(create_app(hermes_client=NoisyHermes(), service_token=token))
    headers, stream_path = _prepare_gateway_run(client, token=token)
    response = client.post(
        stream_path,
        headers=headers,
        json={"client_message_id": "c", "text": "hello"},
    )
    assert response.text == '{"event_type":"blocked","text":"","retryable":true}\n'


def test_safe_prefix_streams_before_hermes_completion_barrier() -> None:
    safe_text = "x" * 300

    class BarrierHermes:
        def __init__(self) -> None:
            self.delta_sent = asyncio.Event()
            self.release_completion = asyncio.Event()

        async def stream_prompt(self, *, text: str, run_id: str | None = None):
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
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
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


def _stream_events_for_chunks(chunks: tuple[str, ...], final_text: str) -> list[dict]:
    class ChunkedHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            for chunk in chunks:
                yield HermesRpcEvent("message.delta", chunk)
            yield HermesRpcEvent("message.complete", final_text)

    async def scenario() -> list[dict]:
        return [
            json.loads(line.decode())
            async for line in _stream_public_lines(ChunkedHermes(), text="hello")
        ]

    return asyncio.run(scenario())


def _published_text(events: list[dict]) -> str:
    return "".join(
        event["text"]
        for event in events
        if event["event_type"] == "text_delta"
    )


def test_sensitive_assignment_with_whitespace_longer_than_rolling_window_is_blocked() -> None:
    sentinel = "PRIVATE"
    chunks = (
        "token",
        " " * 300,
        f"={sentinel}",
        "z" * 300,
    )

    events = _stream_events_for_chunks(chunks, "".join(chunks))

    assert events[-1] == {
        "event_type": "blocked",
        "text": "",
        "retryable": True,
    }
    assert sentinel not in _published_text(events)


@pytest.mark.parametrize(
    ("label", "separator"),
    [
        ("authorization", ":"),
        ("proxy-authorization", ":"),
        ("cookie", ":"),
        ("set-cookie", ":"),
        ("token", "="),
        ("password", "="),
        ("passwd", "="),
        ("secret", "="),
        ("api key", "="),
        ("api_key", "="),
        ("api-key", "="),
        ("provider", "="),
        ("oauth", "="),
        ("oauth token", "="),
        ("access token", "="),
        ("refresh token", "="),
        ("client secret", "="),
        ("mem0", "="),
        ("mem0 api key", "="),
    ],
)
def test_sensitive_label_quarantine_survives_arbitrary_whitespace(
    label: str,
    separator: str,
) -> None:
    sentinel = "PRIVATE"
    safe_prefix = ("s" * 300) + "\n"
    chunks = (
        safe_prefix + label,
        " \t" * 150,
        separator,
        sentinel,
        "z" * 300,
    )

    events = _stream_events_for_chunks(chunks, "".join(chunks))

    assert events[-1]["event_type"] == "blocked"
    assert sentinel not in _published_text(events)


def test_bearer_quarantine_survives_arbitrary_whitespace() -> None:
    sentinel = "PRIVATE"
    safe_prefix = ("s" * 300) + "\n"
    chunks = (
        safe_prefix + "bearer",
        " \t" * 150,
        sentinel,
        "z" * 300,
    )

    events = _stream_events_for_chunks(chunks, "".join(chunks))

    assert events[-1]["event_type"] == "blocked"
    assert sentinel not in _published_text(events)


@pytest.mark.parametrize(
    "label_chunks",
    [
        ("api", "key"),
        ("oauth", "token"),
        ("access", "token"),
        ("refresh", "token"),
        ("client", "secret"),
        ("mem0", "api", "key"),
    ],
)
def test_compound_sensitive_prefix_quarantine_survives_long_internal_gaps(
    label_chunks: tuple[str, ...],
) -> None:
    sentinel = "PRIVATE"
    safe_prefix = ("s" * 300) + "\n"
    chunks: list[str] = [safe_prefix + label_chunks[0]]
    for label_chunk in label_chunks[1:]:
        chunks.extend((" \t" * 150, label_chunk))
    chunks.extend((" \t" * 150, "=", sentinel, "z" * 300))
    chunk_tuple = tuple(chunks)

    events = _stream_events_for_chunks(chunk_tuple, "".join(chunk_tuple))

    assert events[-1]["event_type"] == "blocked"
    assert sentinel not in _published_text(events)


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "authorization : PRIVATE",
        "cookie\t:\tPRIVATE",
        "bearer PRIVATE",
        "api key = PRIVATE",
        "oauth token = PRIVATE",
        "mem0 api key = PRIVATE",
        "/opt/data/PRIVATE",
        "/videobox-data/PRIVATE",
        "/etc/PRIVATE",
        "/home/PRIVATE",
        "C:\\PRIVATE",
    ],
)
def test_sensitive_syntax_fuzz_like_split_points_never_publish_sentinel(
    unsafe_text: str,
) -> None:
    sentinel = "PRIVATE"
    safe_prefix = ("s" * 300) + "\n"
    for split_at in range(1, len(unsafe_text)):
        chunks = (
            safe_prefix + unsafe_text[:split_at],
            unsafe_text[split_at:],
            "z" * 300,
        )
        events = _stream_events_for_chunks(chunks, "".join(chunks))
        assert events[-1]["event_type"] == "blocked"
        assert sentinel not in _published_text(events)


def test_unresolved_sensitive_quarantine_has_a_fail_closed_memory_cap() -> None:
    safe_prefix = ("s" * 300) + "\n"
    chunks = (safe_prefix + "token", " " * 5_000)

    events = _stream_events_for_chunks(chunks, "".join(chunks))

    assert events[-1]["event_type"] == "blocked"
    published = _published_text(events)
    assert published
    assert "token" not in published


@pytest.mark.parametrize(
    "safe_text",
    [
        ("ordinary " * 2_000),
        ("authorization is required. " * 600),
        ("cookie preferences are optional. " * 500),
        ("a token bucket controls throughput. " * 600),
    ],
)
def test_long_non_sensitive_prose_still_streams_incrementally(
    safe_text: str,
) -> None:
    class BarrierHermes:
        def __init__(self) -> None:
            self.release_completion = asyncio.Event()

        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            yield HermesRpcEvent("message.delta", safe_text)
            await self.release_completion.wait()
            yield HermesRpcEvent("message.complete", safe_text)

    async def scenario() -> tuple[dict, list[dict]]:
        hermes = BarrierHermes()
        lines = _stream_public_lines(hermes, text="hello")
        first = json.loads((await asyncio.wait_for(anext(lines), timeout=1)).decode())
        assert not hermes.release_completion.is_set()
        hermes.release_completion.set()
        rest = [json.loads(line.decode()) async for line in lines]
        return first, rest

    first, rest = asyncio.run(scenario())
    assert first["event_type"] == "text_delta"
    assert _published_text([first, *rest]) == safe_text
    assert rest[-1] == {"event_type": "run_completed", "text": safe_text}


def test_single_oversized_hermes_chunk_fails_closed() -> None:
    class OversizedHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
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
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
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
