from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import time

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
        second_replay = client.get(created.json()["events_url"])
        assert second_replay.status_code == 200
        assert second_replay.text == response.text
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


def test_completed_events_replay_after_service_restart_and_cursor_is_strict(
    tmp_path: Path,
) -> None:
    app, _gateway = _configured_app(tmp_path)
    with TestClient(app) as client:
        project_id = client.post(
            "/api/projects", json={"name": "restart replay"}
        ).json()["project_id"]
        session = app.state.store.save_editing_session(
            project_id=project_id,
            timeline_id="timeline",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = client.post(
            f"/api/projects/{project_id}/director/conversations",
            json={"session_id": session["session_id"]},
        ).json()["conversation_id"]
        created = client.post(
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation_id}/hermes-runs",
            json={
                "session_id": session["session_id"],
                "client_message_id": "restart",
                "text": "hello",
                "expected_session_revision": session["session_revision"],
            },
        ).json()
        assert client.get(created["events_url"]).status_code == 200

    restarted, _ = _configured_app(tmp_path)
    with TestClient(restarted) as client:
        replay = client.get(
            created["events_url"], headers={"Last-Event-ID": "1"}
        )
        assert replay.status_code == 200
        assert "id: 1\n" not in replay.text
        assert "event: text_delta" in replay.text
        assert "event: run_completed" in replay.text
        assert client.get(
            created["events_url"], headers={"Last-Event-ID": "-1"}
        ).status_code == 400
        assert client.get(
            created["events_url"], headers={"Last-Event-ID": "not-an-int"}
        ).status_code == 400
        assert client.get(
            created["events_url"], headers={"Last-Event-ID": "9" * 1_000}
        ).status_code == 400
        assert client.get(
            created["events_url"], headers={"Last-Event-ID": "999"}
        ).status_code == 409


def test_event_scope_hides_other_project_and_expired_stream_is_gone(
    tmp_path: Path,
) -> None:
    app, _gateway = _configured_app(tmp_path)
    with TestClient(app) as client:
        project_id = client.post(
            "/api/projects", json={"name": "scope"}
        ).json()["project_id"]
        session = app.state.store.save_editing_session(
            project_id=project_id,
            timeline_id="timeline",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = client.post(
            f"/api/projects/{project_id}/director/conversations",
            json={"session_id": session["session_id"]},
        ).json()["conversation_id"]
        created = client.post(
            f"/api/projects/{project_id}/director/conversations/"
            f"{conversation_id}/hermes-runs",
            json={
                "session_id": session["session_id"],
                "client_message_id": "scope",
                "text": "hello",
                "expected_session_revision": session["session_revision"],
            },
        ).json()
        assert client.get(created["events_url"]).status_code == 200
        assert client.get(
            created["events_url"].replace(project_id, "other-project")
        ).status_code == 404
        assert client.get(
            created["events_url"].replace(conversation_id, "other-conversation")
        ).status_code == 404
        connection = app.state.store._connection(project_id)
        try:
            connection.execute(
                "DELETE FROM director_hermes_run_events "
                "WHERE project_id = ? AND run_id = ?",
                (project_id, created["run_id"]),
            )
            connection.execute(
                "UPDATE director_hermes_runs SET events_pruned_at = ? "
                "WHERE project_id = ? AND run_id = ?",
                ("2026-01-01T00:00:00+00:00", project_id, created["run_id"]),
            )
            connection.commit()
        finally:
            connection.close()
        expired = client.get(created["events_url"])
        assert expired.status_code == 410
        assert expired.json() == {"detail": "hermes_run_events_expired"}


def test_startup_interrupts_orphan_without_gateway_dispatch(tmp_path: Path) -> None:
    seed, _ = _configured_app(tmp_path)
    project = seed.state.store.bootstrap_project("startup recovery")
    session = seed.state.store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    seed.state.store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conv-orphan",
    )
    orphan = seed.state.store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conv-orphan",
        client_message_id="orphan",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )

    restarted, gateway = _configured_app(tmp_path)
    with TestClient(restarted) as client:
        response = client.get(
            f"/api/projects/{project.project_id}/director/conversations/"
            f"conv-orphan/hermes-runs/{orphan['run_id']}/events"
        )
        assert response.status_code == 200
        assert "event: blocked" in response.text
    assert gateway.calls == 0
    assert restarted.state.store.get_director_hermes_run(
        project_id=project.project_id, run_id=orphan["run_id"]
    )["status"] == "interrupted"
    messages = restarted.state.store.list_director_messages(
        project_id=project.project_id, conversation_id="conv-orphan"
    )
    assert sum(message["role"] == "assistant" for message in messages) == 1

    second, second_gateway = _configured_app(tmp_path)
    with TestClient(second) as client:
        replay = client.get(
            f"/api/projects/{project.project_id}/director/conversations/"
            f"conv-orphan/hermes-runs/{orphan['run_id']}/events"
        )
        assert replay.status_code == 200
        assert replay.text.count("event: blocked") == 1
    assert second_gateway.calls == 0
    second_messages = second.state.store.list_director_messages(
        project_id=project.project_id, conversation_id="conv-orphan"
    )
    assert sum(message["role"] == "assistant" for message in second_messages) == 1


def test_periodic_maintenance_prunes_31_day_terminal_without_restart(
    tmp_path: Path,
) -> None:
    instant = [datetime(2026, 1, 1, tzinfo=UTC)]
    app = create_app(
        projects_root=tmp_path / "projects",
        media_analysis_poll_interval_seconds=0.01,
    )
    app.state.store._clock = lambda: instant[0]
    with TestClient(app):
        project = app.state.store.bootstrap_project("periodic retention")
        session = app.state.store.save_editing_session(
            project_id=project.project_id,
            timeline_id="timeline",
            session_payload={"segments": [], "history": []},
        )
        app.state.store.create_director_conversation(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conv",
        )
        run = app.state.store.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conv",
            client_message_id="old-in-process",
            user_text="hello",
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
        )
        assert app.state.store.complete_director_hermes_run(
            project_id=project.project_id,
            run_id=run["run_id"],
            owner_token=run["owner_token"],
            status="completed",
            assistant_text="answer",
            public_text="",
            retryable=False,
        )
        instant[0] += timedelta(days=31)
        expired = False
        for _ in range(100):
            try:
                app.state.store.list_director_hermes_run_events(
                    project_id=project.project_id,
                    conversation_id="conv",
                    run_id=run["run_id"],
                )
            except ValueError as error:
                assert str(error) == "hermes_run_events_expired"
                expired = True
                break
            time.sleep(0.01)
        assert expired


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
