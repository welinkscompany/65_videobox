from __future__ import annotations

from inspect import signature
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


SERVICE_TOKEN = "workspace-service-token-that-is-at-least-32"


def test_retired_hermes_project_status_route_cannot_be_conditionally_enabled(
    tmp_path: Path,
) -> None:
    assert "hermes_capability_verifier" not in signature(
        create_app
    ).parameters
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    assert client.get(
        "/internal/hermes/projects/anything/status"
    ).status_code == 404
    assert (
        "/internal/hermes/projects/{project_id}/status"
        not in client.get("/openapi.json").json()["paths"]
    )
    assert not Path(
        "services/api/src/videobox_api/routers/hermes_internal.py"
    ).exists()


def test_retired_project_route_stays_absent_when_global_status_is_configured(
    tmp_path: Path,
) -> None:
    app = create_app(
        projects_root=tmp_path,
        agent_gateway_url="http://videobox-agent-gateway:8081",
        agent_gateway_service_token=SERVICE_TOKEN,
        agent_gateway_http_client_factory=lambda **_: None,
    )
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/hermes-yujin/status" in paths
    assert "/internal/hermes/projects/{project_id}/status" not in paths
    assert client.get(
        "/internal/hermes/projects/anything/status"
    ).status_code == 404
