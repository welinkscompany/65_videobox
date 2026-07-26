from __future__ import annotations

from fastapi.testclient import TestClient

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
    app = create_app(hermes_client=hermes, service_token="service-secret")
    client = TestClient(app)
    assert app.openapi_url is None
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200
    body = {"session_id": "s", "client_message_id": "c", "text": "hello"}
    assert client.post("/internal/hermes/stream", json=body).status_code == 401
    assert hermes.calls == 0
    rejected = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": "Bearer service-secret"},
        json={**body, "tool_name": "shell", "provider": "x", "path": "C:/db"},
    )
    assert rejected.status_code == 422
    assert hermes.calls == 0
    response = client.post(
        "/internal/hermes/stream",
        headers={"Authorization": "Bearer service-secret"},
        json=body,
    )
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text.splitlines() == [
        '{"event_type": "text_delta", "text": "a"}',
        '{"event_type": "run_completed", "text": "answer"}',
    ]
    assert hermes.calls == 1


def test_unconfigured_gateway_remains_health_only() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert paths == {"/health"}
