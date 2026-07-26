from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from videobox_api.agent_gateway_client import AgentGatewayEvent
from videobox_api.main import create_app


SERVICE_TOKEN = "service-token-that-is-at-least-thirty-two"


class _Gateway:
    calls = 0
    preparations = 0

    async def prepare_run(self, **_):
        self.preparations += 1

    async def stream_run(self, **_):
        self.calls += 1
        yield AgentGatewayEvent("text_delta", "a")
        yield AgentGatewayEvent("run_completed", "answer")


def _configured_app(tmp_path: Path):
    app = create_app(
        projects_root=tmp_path / "projects",
        agent_gateway_url="http://videobox-agent-gateway:8081",
        agent_gateway_service_token=SERVICE_TOKEN,
        agent_gateway_http_client_factory=lambda **_: None,
    )
    gateway = _Gateway()
    app.state.hermes_run_service.gateway_client = gateway
    app.state.hermes_run_service._context_builder = lambda **kwargs: SimpleNamespace(
        session_revision=kwargs["expected_session_revision"],
        asset_index_revision=0,
        model_dump=lambda **_: {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": kwargs["project_id"],
            "session_id": kwargs["session_id"],
            "session_revision": kwargs["expected_session_revision"],
            "asset_index_revision": 0,
        },
    )
    return app, gateway


def test_router_is_absent_without_config_and_external_url_is_rejected(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "manual")
    assert not any("hermes-runs" in route.path for route in app.routes)
    with pytest.raises(ValueError, match="internal"):
        create_app(
            projects_root=tmp_path / "external",
            agent_gateway_url="http://evil.example:8081",
            agent_gateway_service_token=SERVICE_TOKEN,
        )


def test_create_and_sse_preserve_manual_conversation_and_headers(
    tmp_path: Path,
) -> None:
    app, gateway = _configured_app(tmp_path)
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "chat"}).json()[
            "project_id"
        ]
        session = app.state.store.save_editing_session(
            project_id=project_id,
            timeline_id="timeline",
            session_payload={"segments": [], "history": []},
        )
        conversation = client.post(
            f"/api/projects/{project_id}/director/conversations",
            json={"session_id": session["session_id"]},
        ).json()
        create_url = (
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation['conversation_id']}/hermes-runs"
        )
        payload = {
            "session_id": session["session_id"],
            "client_message_id": "client-1",
            "text": "hello",
            "expected_session_revision": session["session_revision"],
        }
        created = client.post(create_url, json=payload)
        assert created.status_code == 201
        duplicate = client.post(create_url, json=payload)
        assert duplicate.json()["run_id"] == created.json()["run_id"]
        response = client.get(created.json()["events_url"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache, no-transform"
        assert response.headers["x-accel-buffering"] == "no"
        assert "event: run_started" in response.text
        assert "event: text_delta" in response.text
        assert "event: run_completed" in response.text
        assert client.get(created.json()["events_url"]).status_code == 409
        assert gateway.calls == 1
        manual = client.post(
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation['conversation_id']}/messages",
            json={
                "session_id": session["session_id"],
                "client_message_id": "manual-1",
                "text": "manual",
            },
        )
        assert manual.status_code == 200


def test_hermes_request_validation_does_not_reflect_rejected_input(
    tmp_path: Path,
) -> None:
    app, _gateway = _configured_app(tmp_path)
    sentinel = "do-not-reflect-hermes-secret"
    with TestClient(app) as client:
        response = client.post(
            "/api/projects/p/director/conversations/c/hermes-runs",
            json={
                "session_id": "s",
                "client_message_id": "m",
                "text": "hello",
                "provider_secret": sentinel,
            },
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "hermes_run_request_invalid"}
    assert sentinel not in response.text
