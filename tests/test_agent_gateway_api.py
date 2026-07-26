from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from videobox_agent_gateway.hermes_rpc_client import HermesRpcEvent
from videobox_agent_gateway.main import create_app


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
        '{"event_type":"text_delta","text":"a"}',
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


@pytest.mark.parametrize(
    "token",
    ["short", "changeme-changeme-changeme-changeme", "REPLACE_ME_123456789012345678901234"],
)
def test_weak_or_placeholder_service_tokens_are_rejected(token: str) -> None:
    with pytest.raises(ValueError, match="service_token"):
        create_app(hermes_client=_Hermes(), service_token=token)
