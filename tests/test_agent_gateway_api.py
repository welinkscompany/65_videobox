from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import count
import json
import threading

from fastapi.testclient import TestClient
import pytest

import videobox_agent_gateway.main as gateway_main
from videobox_agent_gateway.hermes_rpc_client import (
    HermesRpcEvent,
    HermesTransportError,
)
from videobox_agent_gateway.context_capabilities import YujinCapabilityIssuer
from videobox_agent_gateway.main import (
    _app_from_environment,
    _stream_public_lines,
    create_app,
)


class _Hermes:
    calls = 0

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def stream_prompt(self, *, text: str, run_id: str | None = None):
        self.calls += 1
        self.prompts.append(text)
        yield HermesRpcEvent("message.delta", "a")
        yield HermesRpcEvent("message.complete", "answer")


def _capability_issuer() -> YujinCapabilityIssuer:
    identifiers = count(1)
    return YujinCapabilityIssuer(
        key_id="test-key-1",
        private_key=b"\x11" * 32,
        now=lambda: datetime(2026, 7, 30, tzinfo=UTC),
        capability_id_factory=lambda: f"capability-{next(identifiers)}",
    )


def _decode_capability_claims(token: str) -> dict[str, object]:
    encoded = token.split(".")[1]
    padded = encoded + ("=" * (-len(encoded) % 4))
    return json.loads(base64.urlsafe_b64decode(padded))


def _live_app(hermes_client, service_token: str, **kwargs):
    return create_app(
        hermes_client=hermes_client,
        service_token=service_token,
        capability_issuer=_capability_issuer(),
        **kwargs,
    )


def _operational_observer(
    clock,
):
    return gateway_main._GatewayOperationalObserver(
        clock=clock,
        observation_epoch="epoch-test-1",
    )


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
    app = _live_app(hermes, token)
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
    frames = [json.loads(line) for line in response.text.splitlines()]
    assert frames[0] == {"event_type": "text_delta", "text": "answer"}
    assert frames[1]["event_type"] == "run_completed"
    assert frames[1]["text"] == "answer"
    assert _decode_capability_claims(
        frames[1]["publish_capability_token"]
    )["action"] == "publish_proposal"
    assert hermes.calls == 1


def test_health_uses_only_the_injected_probe_and_emits_strict_observation() -> None:
    instant = datetime(2026, 7, 30, 1, 2, 3, tzinfo=UTC)
    probe_calls = 0

    async def probe() -> bool:
        nonlocal probe_calls
        probe_calls += 1
        return True

    app = _live_app(
        _Hermes(),
        "service-secret-that-is-at-least-32-bytes",
        hermes_http_probe=probe,
        operational_clock=lambda: instant,
        observation_epoch="epoch-health-1",
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "scope": "gateway_http_process",
        "gateway_configured": True,
        "capability_routes_ready": True,
        "hermes_http_ready": True,
        "provider_ready": False,
        "chat_ready": False,
        "degraded": False,
        "observation_epoch": "epoch-health-1",
        "process_started_at": "2026-07-30T01:02:03Z",
        "provider_observed_at": None,
        "last_chat_verified_at": None,
        "evidence_valid_until": None,
        "status_basis": "gateway_observation",
    }
    assert probe_calls == 1


def test_delayed_false_probe_and_later_false_probe_cannot_downgrade_public_completion(
) -> None:
    probe_started = threading.Event()
    release_probe = threading.Event()
    probe_calls = 0

    async def delayed_false_probe() -> bool:
        nonlocal probe_calls
        probe_calls += 1
        probe_started.set()
        await asyncio.to_thread(release_probe.wait)
        return False

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(_live_app(
        _Hermes(),
        token,
        hermes_http_probe=delayed_false_probe,
        observation_epoch="epoch-probe-fence",
    ))
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_health = executor.submit(client.get, "/health")
        assert probe_started.wait(timeout=2)
        headers, stream_path = _prepare_gateway_run(client, token=token)
        completed = client.post(
            stream_path,
            headers=headers,
            json={"client_message_id": "c", "text": "hello"},
        )
        assert completed.status_code == 200
        assert json.loads(completed.text.splitlines()[-1])["event_type"] == (
            "run_completed"
        )
        release_probe.set()
        raced_health = pending_health.result(timeout=3)

    assert raced_health.status_code == 200
    assert raced_health.json()["hermes_http_ready"] is True
    assert raced_health.json()["provider_ready"] is True
    assert raced_health.json()["chat_ready"] is True

    later_health = client.get("/health")

    assert later_health.status_code == 200
    assert later_health.json()["hermes_http_ready"] is False
    assert later_health.json()["provider_ready"] is False
    assert later_health.json()["chat_ready"] is False
    assert probe_calls == 2


def test_safe_public_frames_drive_provider_then_chat_observation() -> None:
    instant = datetime(2026, 7, 30, 2, 0, 0, tzinfo=UTC)
    observer = _operational_observer(lambda: instant)
    safe_delta = "a" * 300

    class SafeHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            yield HermesRpcEvent("message.delta", safe_delta)
            yield HermesRpcEvent("message.complete", safe_delta)

    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        stream = _stream_public_lines(
            SafeHermes(),
            text="hello",
            operational_observer=observer,
        )
        first = json.loads((await anext(stream)).decode())
        after_delta = observer.snapshot()
        remaining = []
        async for line in stream:
            remaining.append(json.loads(line.decode()))
        after_complete = observer.snapshot()
        assert first["event_type"] == "text_delta"
        assert remaining[-1]["event_type"] == "run_completed"
        return after_delta, after_complete

    after_delta, after_complete = asyncio.run(scenario())

    assert after_delta["provider_ready"] is True
    assert after_delta["chat_ready"] is False
    assert after_delta["provider_observed_at"] == "2026-07-30T02:00:00Z"
    assert after_complete["provider_ready"] is True
    assert after_complete["chat_ready"] is True
    assert after_complete["last_chat_verified_at"] == (
        "2026-07-30T02:00:00Z"
    )
    assert after_complete["evidence_valid_until"] == (
        "2026-07-30T02:10:00Z"
    )


def test_observation_ordering_sticky_degraded_and_new_complete_recovery() -> None:
    clock = [datetime(2026, 7, 30, 3, 0, 0, tzinfo=UTC)]
    observer = _operational_observer(lambda: clock[0])
    older = observer.begin_run()
    newer = observer.begin_run()

    newer.public_completion()
    older.final_failure("hermes_unavailable")
    assert observer.snapshot()["chat_ready"] is True
    assert observer.snapshot()["degraded"] is False

    clock[0] += timedelta(seconds=1)
    failed = observer.begin_run()
    failed.final_failure("hermes_timeout")
    assert observer.snapshot()["chat_ready"] is False
    assert observer.snapshot()["degraded"] is True

    clock[0] += timedelta(seconds=1)
    partial_recovery = observer.begin_run()
    partial_recovery.public_delta()
    assert observer.snapshot()["degraded"] is True

    clock[0] += timedelta(seconds=1)
    recovered = observer.begin_run()
    recovered.public_completion()
    snapshot = observer.snapshot()
    assert snapshot["chat_ready"] is True
    assert snapshot["degraded"] is False
    assert snapshot["last_chat_verified_at"] == "2026-07-30T03:00:03Z"


def test_degraded_failure_keeps_chat_reference_and_renews_failure_ttl() -> None:
    clock = [datetime(2026, 7, 30, 3, 30, 0, tzinfo=UTC)]
    observer = _operational_observer(lambda: clock[0])
    observer.begin_run().public_completion()
    completed = observer.snapshot()

    clock[0] += timedelta(seconds=9)
    observer.begin_run().final_failure("hermes_unavailable")
    degraded = observer.snapshot()

    assert completed["last_chat_verified_at"] == "2026-07-30T03:30:00Z"
    assert completed["evidence_valid_until"] == "2026-07-30T03:40:00Z"
    assert degraded["provider_ready"] is False
    assert degraded["chat_ready"] is False
    assert degraded["degraded"] is True
    assert degraded["last_chat_verified_at"] == completed["last_chat_verified_at"]
    assert degraded["evidence_valid_until"] == "2026-07-30T03:40:09Z"


@pytest.mark.parametrize(
    "reason",
    [
        "hermes_interrupted",
        "gateway_output_unsafe",
        "gateway_event_invalid",
        "hermes_invalid_response",
        "hermes_capability_expired",
    ],
)
def test_non_operational_failures_never_degrade_verified_chat(
    reason: str,
) -> None:
    instant = datetime(2026, 7, 30, 4, 0, 0, tzinfo=UTC)
    observer = _operational_observer(lambda: instant)
    observer.begin_run().public_completion()

    observer.begin_run().final_failure(reason)

    snapshot = observer.snapshot()
    assert snapshot["chat_ready"] is True
    assert snapshot["degraded"] is False


def test_expired_observation_falls_back_without_erasing_reference_time() -> None:
    clock = [datetime(2026, 7, 30, 5, 0, 0, tzinfo=UTC)]
    observer = _operational_observer(lambda: clock[0])
    observer.begin_run().public_completion()
    clock[0] += timedelta(minutes=10, microseconds=1)

    snapshot = observer.snapshot()

    assert snapshot["provider_ready"] is False
    assert snapshot["chat_ready"] is False
    assert snapshot["degraded"] is False
    assert snapshot["last_chat_verified_at"] == "2026-07-30T05:00:00Z"
    assert snapshot["evidence_valid_until"] == "2026-07-30T05:10:00Z"


def test_allowlisted_transport_failure_is_redacted_in_public_stream() -> None:
    instant = datetime(2026, 7, 30, 6, 0, 0, tzinfo=UTC)
    observer = _operational_observer(lambda: instant)
    observer.begin_run().public_completion()

    class FailedHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            raise HermesTransportError("hermes_unavailable")
            yield  # pragma: no cover

    async def collect() -> list[dict[str, object]]:
        return [
            json.loads(line)
            async for line in _stream_public_lines(
                FailedHermes(),
                text="PRIVATE password=secret",
                operational_observer=observer,
            )
        ]

    frames = asyncio.run(collect())

    assert frames == [
        {"event_type": "blocked", "text": "", "retryable": True}
    ]
    assert observer.snapshot()["degraded"] is True
    assert "PRIVATE" not in json.dumps(observer.snapshot())


def test_gateway_cancel_is_authenticated_and_targets_only_the_named_run() -> None:
    class InterruptibleHermes(_Hermes):
        def __init__(self) -> None:
            self.interruptions: list[str] = []

        async def interrupt(self, *, run_id: str) -> bool:
            self.interruptions.append(run_id)
            return False

    hermes = InterruptibleHermes()
    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(_live_app(hermes, token))

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


def test_reserve_returns_read_token_and_metadata_but_terminal_alone_gets_publish_token() -> None:
    hermes = _Hermes()
    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(
        create_app(
            hermes_client=hermes,
            service_token=token,
            capability_issuer=_capability_issuer(),
        )
    )
    headers = {"Authorization": f"Bearer {token}"}
    identity = {
        "project_id": "project-a",
        "conversation_id": "conversation-a",
        "run_id": "run-capabilities",
        "session_id": "s",
        "session_revision": 1,
        "asset_index_revision": 0,
    }

    reserved = client.post(
        "/internal/hermes/runs",
        headers=headers,
        json=identity,
    )
    assert reserved.status_code == 200
    reservation = reserved.json()
    assert set(reservation) == {
        "run_id",
        "attach_context",
        "expires_in_seconds",
        "read_capability_token",
        "capabilities",
    }
    assert reservation["run_id"] == "run-capabilities"
    assert reservation["expires_in_seconds"] == 30
    assert [item["action"] for item in reservation["capabilities"]] == [
        "read_context",
        "publish_proposal",
    ]
    assert all(
        set(item) == {"capability_id", "action", "expires_at"}
        for item in reservation["capabilities"]
    )
    read_token = reservation["read_capability_token"]
    read_claims = _decode_capability_claims(read_token)
    assert read_claims["action"] == "read_context"
    assert read_claims["capability_id"] == reservation["capabilities"][0][
        "capability_id"
    ]
    assert (
        reservation["capabilities"][0]["capability_id"]
        != reservation["capabilities"][1]["capability_id"]
    )
    assert "publish_capability_token" not in json.dumps(reservation)

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
    assert client.post(
        "/internal/hermes/runs/run-capabilities/context",
        headers={
            **headers,
            "X-VideoBox-Attach-Ticket": reservation["attach_context"],
        },
        json={"identity": identity, "context": context},
    ).status_code == 204
    streamed = client.post(
        "/internal/hermes/runs/run-capabilities/stream",
        headers=headers,
        json={"client_message_id": "c", "text": "hello"},
    )
    frames = [json.loads(line) for line in streamed.text.splitlines()]

    assert frames[0] == {"event_type": "text_delta", "text": "answer"}
    assert set(frames[1]) == {
        "event_type",
        "text",
        "publish_capability_token",
    }
    assert frames[1]["event_type"] == "run_completed"
    publish_token = frames[1]["publish_capability_token"]
    publish_claims = _decode_capability_claims(publish_token)
    assert publish_claims["action"] == "publish_proposal"
    assert publish_claims["capability_id"] == reservation["capabilities"][1][
        "capability_id"
    ]
    assert read_token not in streamed.text
    assert read_token not in hermes.prompts[0]
    assert publish_token not in frames[0].values()
    assert publish_token not in hermes.prompts[0]
    assert publish_token not in repr(hermes.__dict__)


@pytest.mark.parametrize(
    ("private_key_b64", "key_id"),
    [
        (None, "test-key-1"),
        ("not-base64", "test-key-1"),
        (
            base64.urlsafe_b64encode(b"\x11" * 32).rstrip(b"=").decode("ascii"),
            "token=bad",
        ),
    ],
)
def test_environment_missing_or_invalid_capability_key_stays_health_only(
    monkeypatch: pytest.MonkeyPatch,
    private_key_b64: str | None,
    key_id: str,
) -> None:
    monkeypatch.setenv(
        "HERMES_YUJIN_URL",
        "http://videobox-hermes-yujin:9120",
    )
    monkeypatch.setenv("HERMES_YUJIN_GATEWAY_USERNAME", "gateway-user")
    monkeypatch.setenv("HERMES_YUJIN_GATEWAY_PASSWORD", "gateway-password")
    monkeypatch.setenv(
        "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN",
        "service-secret-that-is-at-least-32-bytes",
    )
    if private_key_b64 is None:
        monkeypatch.delenv(
            "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64",
            raising=False,
        )
    else:
        monkeypatch.setenv(
            "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64",
            private_key_b64,
        )
    monkeypatch.setenv("VIDEOBOX_HERMES_CAPABILITY_KEY_ID", key_id)

    app = _app_from_environment()

    assert {route.path for route in app.routes} == {"/health"}


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
    client = TestClient(_live_app(UnsafeHermes(), token))
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
    assert "capability" not in response.text
    assert "token" not in response.text
    assert "key" not in response.text
    assert sentinel not in response.text
    assert "/opt/data" not in response.text


def test_unsafe_output_split_across_events_is_quarantined() -> None:
    class SplitHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            yield HermesRpcEvent("message.delta", "pass")
            yield HermesRpcEvent("message.delta", "word=private")
            yield HermesRpcEvent("message.complete", "never publish")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(_live_app(SplitHermes(), token))
    headers, stream_path = _prepare_gateway_run(client, token=token)
    response = client.post(
        stream_path,
        headers=headers,
        json={"client_message_id": "c", "text": "hello"},
    )
    assert response.text == '{"event_type":"blocked","text":"","retryable":true}\n'
    assert "private" not in response.text


def test_excessive_empty_event_stream_is_bounded() -> None:
    from videobox_agent_gateway.main import _MAX_PUBLIC_EVENTS

    class NoisyHermes:
        async def stream_prompt(self, *, text: str, run_id: str | None = None):
            # 상한을 바꿔도 "상한을 넘으면 막는다"는 계약은 그대로여야 한다.
            for _ in range(_MAX_PUBLIC_EVENTS + 1):
                yield HermesRpcEvent("message.delta", "")
            yield HermesRpcEvent("message.complete", "answer")

    token = "service-secret-that-is-at-least-32-bytes"
    client = TestClient(_live_app(NoisyHermes(), token))
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


def test_closing_public_stream_immediately_awaits_upstream_cleanup() -> None:
    publish_token = "publish-token-must-not-leak"

    class CloseAwareStream:
        def __init__(self) -> None:
            self.events = [
                HermesRpcEvent("message.delta", "safe " * 100),
                HermesRpcEvent("message.complete", "safe " * 100),
            ]
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self) -> HermesRpcEvent:
            if not self.events:
                raise StopAsyncIteration
            return self.events.pop(0)

        async def aclose(self) -> None:
            try:
                await asyncio.sleep(0)
            finally:
                self.closed = True

    class CleanupHermes:
        def __init__(self) -> None:
            self.upstream = CloseAwareStream()

        def stream_prompt(
            self,
            *,
            text: str,
            run_id: str | None = None,
        ):
            return self.upstream

    async def scenario() -> tuple[CleanupHermes, bytes]:
        hermes = CleanupHermes()
        public_stream = _stream_public_lines(
            hermes,
            text="hello",
            run_id="run-a",
            publish_capability_token=publish_token,
        )
        first = await anext(public_stream)
        await public_stream.aclose()
        return hermes, first

    hermes, first = asyncio.run(scenario())

    assert hermes.upstream.closed is True
    assert b'"event_type":"text_delta"' in first
    assert publish_token.encode() not in first


def test_blocked_stream_awaits_upstream_cleanup_without_token() -> None:
    publish_token = "publish-token-must-not-leak"

    class ErrorStream:
        def __init__(self) -> None:
            self.sent = False
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self) -> HermesRpcEvent:
            if self.sent:
                raise StopAsyncIteration
            self.sent = True
            return HermesRpcEvent("tool.start", "private")

        async def aclose(self) -> None:
            await asyncio.sleep(0)
            self.closed = True

    class ErrorHermes:
        def __init__(self) -> None:
            self.upstream = ErrorStream()

        def stream_prompt(
            self,
            *,
            text: str,
            run_id: str | None = None,
        ):
            return self.upstream

    async def scenario() -> tuple[ErrorHermes, list[bytes]]:
        hermes = ErrorHermes()
        lines = [
            line
            async for line in _stream_public_lines(
                hermes,
                text="hello",
                run_id="run-a",
                publish_capability_token=publish_token,
            )
        ]
        return hermes, lines

    hermes, lines = asyncio.run(scenario())

    assert hermes.upstream.closed is True
    assert lines == [b'{"event_type":"blocked","text":"","retryable":true}\n']
    assert publish_token.encode() not in lines[0]
    assert b"private" not in lines[0]


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
        create_app(
            hermes_client=_Hermes(),
            service_token=token,
            capability_issuer=_capability_issuer(),
        )


def test_blocked_runs_report_a_safe_reason_code_for_logs() -> None:
    """게이트웨이가 실패 사유를 통째로 삼키면 원인을 못 찾는다.

    2026-08-08: 유진 대화가 매번 blocked 로 끝났는데 로그에 아무것도 남지
    않아, 원인을 찾는 데만 여러 시간이 걸렸다. 다만 사유에 사용자 내용이나
    자격 증명이 섞이면 안 되므로 알려진 코드만 통과시킨다.
    """
    from videobox_agent_gateway.main import safe_block_reason

    assert safe_block_reason(ValueError("gateway_output_unsafe")) == (
        "gateway_output_unsafe"
    )
    assert safe_block_reason(ValueError("gateway_completion_missing")) == (
        "gateway_completion_missing"
    )
    # 모르는 예외는 내용을 흘리지 않고 종류만 남긴다.
    leaked = safe_block_reason(RuntimeError("PRIVATE token abc123"))
    assert "PRIVATE" not in leaked
    assert "abc123" not in leaked
    assert leaked == "unexpected:RuntimeError"


def test_public_event_cap_fits_a_token_streaming_local_model() -> None:
    """게이트웨이의 512개 상한이 로컬 모델 대화를 매번 잘랐다.

    2026-08-08 실기: Hermes 가 한 답변에 976~1070개의 델타를 보내는데
    512에서 gateway_event_limit 이 터졌다. 실제 분량은
    _MAX_PUBLIC_TEXT_BYTES 가 따로 막으므로 개수만 넉넉히 둔다.
    """
    from videobox_agent_gateway.main import (
        _MAX_PUBLIC_EVENTS,
        _MAX_PUBLIC_TEXT_BYTES,
    )

    assert _MAX_PUBLIC_EVENTS >= 8_192
    assert _MAX_PUBLIC_TEXT_BYTES == 200_000
