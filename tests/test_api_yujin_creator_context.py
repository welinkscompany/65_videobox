from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from videobox_api.agent_gateway_client import (
    AgentGatewayEvent,
    AgentGatewayReservation,
    AgentGatewayUnavailable,
)
from videobox_api.hermes_run_service import (
    HermesContextPreparationUnavailable,
    HermesRunService,
)
from videobox_api.models import HermesRunCreateRequest
from videobox_storage.local_project_store import LocalProjectStore


class _Store:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.completions: list[dict] = []
        self.capabilities: dict[str, dict] = {}

    def begin_director_hermes_run(self, **_kwargs):
        self.order.append("durable_begin")
        return {
            "run_id": "run-a",
            "status": "pending",
            "owner_token": "owner-a",
            "dispatch": True,
        }

    def complete_director_hermes_run(self, **kwargs):
        self.order.append("durable_complete")
        self.completions.append(kwargs)
        return True

    def register_hermes_run_capabilities(self, **kwargs):
        self.capabilities[str(kwargs["run_id"])] = kwargs

    def get_expected_hermes_capability(self, **kwargs):
        registered = self.capabilities[str(kwargs["run_id"])]
        metadata = next(
            capability
            for capability in registered["capabilities"]
            if capability["action"] == kwargs["action"]
        )
        return {
            "capability_id": metadata["capability_id"],
            "project_id": registered["project_id"],
            "conversation_id": registered["conversation_id"],
            "run_id": registered["run_id"],
            "session_id": registered["session_id"],
            "session_revision": registered["session_revision"],
            "asset_index_revision": registered["asset_index_revision"],
            "action": metadata["action"],
            "state": "issued",
            "expires_at": metadata["expires_at"],
        }

    def consume_registered_hermes_capability(self, **_kwargs):
        return "accepted"

    def record_hermes_capability_denial(self, **kwargs):
        return kwargs

    def revoke_issued_hermes_capabilities(self, **_kwargs):
        return 0


def _reservation(run_id: str) -> AgentGatewayReservation:
    return AgentGatewayReservation.model_validate(
        {
            "run_id": run_id,
            "attach_context": "a" * 64,
            "expires_in_seconds": 30,
            "read_capability_token": "header.read.signature",
            "capabilities": (
                {
                    "capability_id": f"{run_id}-cap-read",
                    "action": "read_context",
                    "expires_at": 2_000_000_300,
                },
                {
                    "capability_id": f"{run_id}-cap-publish",
                    "action": "publish_proposal",
                    "expires_at": 2_000_000_300,
                },
            ),
        }
    )


class _Verifier:
    def verify(self, _token: str, *, expected):
        return SimpleNamespace(
            capability_id=expected.capability_id,
            action=expected.action,
        )


class _Gateway:
    def __init__(self, order: list[str], *, fail_prepare: bool = False) -> None:
        self.order = order
        self.fail_prepare = fail_prepare
        self.prepared: list[dict] = []
        self.stream_calls = 0

    async def reserve_run(self, **kwargs):
        self.order.append("gateway_prepare")
        if self.fail_prepare:
            raise AgentGatewayUnavailable("agent_gateway_unavailable")
        return _reservation(str(kwargs["run_id"]))

    async def attach_run_context(self, **kwargs):
        self.prepared.append(kwargs)

    async def release_run(self, **_kwargs):
        if self.fail_prepare:
            self.order.append("gateway_release")
        return None

    async def stream_run(self, **_kwargs):
        self.order.append("gateway_stream")
        self.stream_calls += 1
        yield AgentGatewayEvent("run_completed", "answer")


def _context_builder(order: list[str], *, stale: bool = False):
    def build(**kwargs):
        order.append("context_build")
        if stale:
            raise ValueError("creator_context_session_revision_mismatch")
        payload = {
            "schema_version": "videobox.yujin-context.v1",
            "project_id": kwargs["project_id"],
            "session_id": kwargs["session_id"],
            "session_revision": kwargs["expected_session_revision"],
            "asset_index_revision": 13,
        }
        return SimpleNamespace(
            session_revision=kwargs["expected_session_revision"],
            asset_index_revision=13,
            model_dump=lambda **_: payload,
        )

    return build


def test_public_request_requires_a_strict_current_revision() -> None:
    with pytest.raises(ValidationError):
        HermesRunCreateRequest.model_validate(
            {"session_id": "s", "client_message_id": "c", "text": "hello"}
        )
    with pytest.raises(ValidationError):
        HermesRunCreateRequest.model_validate(
            {
                "session_id": "s",
                "client_message_id": "c",
                "text": "hello",
                "expected_session_revision": "7",
            }
        )


def test_context_is_built_before_durable_begin_and_attached_before_dispatch() -> None:
    order: list[str] = []
    store = _Store(order)
    gateway = _Gateway(order)
    service = HermesRunService(
        store=store,
        gateway_client=gateway,
        context_builder=_context_builder(order),
        capability_verifier=_Verifier(),
    )

    async def scenario():
        run = await service.create_run(
            project_id="project-a",
            session_id="session-a",
            conversation_id="conversation-a",
            client_message_id="message-a",
            text="help",
            expected_session_revision=7,
            selected_segment_id="segment-a",
        )
        assert order[:3] == [
            "context_build",
            "durable_begin",
            "gateway_prepare",
        ]
        await run.task
        await service.shutdown()

    asyncio.run(scenario())

    assert order == [
        "context_build",
        "durable_begin",
        "gateway_prepare",
        "gateway_stream",
        "durable_complete",
    ]
    assert gateway.prepared[0]["session_revision"] == 7
    assert gateway.prepared[0]["asset_index_revision"] == 13
    assert gateway.prepared[0]["context"]["session_revision"] == 7


def test_stale_or_preparation_failure_keeps_prompt_at_zero_and_settles_owned_row() -> None:
    stale_order: list[str] = []
    stale_store = _Store(stale_order)
    stale_gateway = _Gateway(stale_order)
    stale_service = HermesRunService(
        store=stale_store,
        gateway_client=stale_gateway,
        context_builder=_context_builder(stale_order, stale=True),
        capability_verifier=_Verifier(),
    )
    with pytest.raises(ValueError, match="revision"):
        asyncio.run(
            stale_service.create_run(
                project_id="project-a",
                session_id="session-a",
                conversation_id="conversation-a",
                client_message_id="stale",
                text="help",
                expected_session_revision=6,
            )
        )
    assert stale_order == ["context_build"]
    assert stale_gateway.stream_calls == 0

    failed_order: list[str] = []
    failed_store = _Store(failed_order)
    failed_gateway = _Gateway(failed_order, fail_prepare=True)
    failed_service = HermesRunService(
        store=failed_store,
        gateway_client=failed_gateway,
        context_builder=_context_builder(failed_order),
        capability_verifier=_Verifier(),
    )
    with pytest.raises(
        HermesContextPreparationUnavailable,
        match="^hermes_context_preparation_unavailable$",
    ) as caught:
        asyncio.run(
            failed_service.create_run(
                project_id="project-a",
                session_id="session-a",
                conversation_id="conversation-a",
                client_message_id="failed",
                text="help",
                expected_session_revision=7,
            )
        )
    assert "agent_gateway_unavailable" not in str(caught.value)
    assert failed_order == [
        "context_build",
        "durable_begin",
        "gateway_prepare",
        "gateway_release",
        "durable_complete",
    ]
    assert failed_store.completions[0]["status"] == "blocked"
    assert failed_gateway.stream_calls == 0


def test_durable_idempotency_binds_revision_and_selection_across_restart(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("creator-context")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-a",
        session_payload={
            "segments": [{"segment_id": "segment-a"}],
            "history": [],
        },
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
    )
    arguments = {
        "project_id": project.project_id,
        "session_id": session["session_id"],
        "conversation_id": "conversation-a",
        "client_message_id": "message-a",
        "user_text": "help",
        "expected_session_revision": session["session_revision"],
        "expected_asset_index_revision": 0,
        "selected_segment_id": None,
    }
    first = store.begin_director_hermes_run(**arguments)
    restarted = LocalProjectStore(tmp_path / "projects")
    duplicate = restarted.begin_director_hermes_run(**arguments)
    assert duplicate["run_id"] == first["run_id"]
    assert duplicate["dispatch"] is False

    with pytest.raises(ValueError, match="different_context"):
        restarted.begin_director_hermes_run(
            **{**arguments, "selected_segment_id": "segment-a"}
        )
    updated = restarted.update_editing_session(
        project_id=project.project_id,
        session_id=session["session_id"],
        expected_revision=session["session_revision"],
        session_payload=session,
    )
    with pytest.raises(ValueError, match="different_context"):
        restarted.begin_director_hermes_run(
            **{
                **arguments,
                "expected_session_revision": updated["session_revision"],
            }
        )
    assert restarted.bump_asset_index_revision(project.project_id) == 1
    with pytest.raises(ValueError, match="different_context"):
        restarted.begin_director_hermes_run(
            **{
                **arguments,
                "expected_session_revision": updated["session_revision"],
                "expected_asset_index_revision": 1,
            }
        )


def test_durable_begin_rechecks_session_and_asset_revision_after_context_build(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("creator-context-race")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-a",
        session_payload={
            "segments": [{"segment_id": "segment-a"}],
            "history": [],
        },
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
    )
    arguments = {
        "project_id": project.project_id,
        "session_id": session["session_id"],
        "conversation_id": "conversation-a",
        "client_message_id": "message-a",
        "user_text": "help",
        "expected_session_revision": session["session_revision"],
        "expected_asset_index_revision": 0,
        "selected_segment_id": "segment-a",
    }

    store.update_editing_session(
        project_id=project.project_id,
        session_id=session["session_id"],
        expected_revision=session["session_revision"],
        session_payload={
            **session,
            "segments": [{"segment_id": "segment-a"}],
        },
    )
    with pytest.raises(ValueError, match="session_revision_mismatch"):
        store.begin_director_hermes_run(**arguments)

    current = store.get_editing_session(
        project_id=project.project_id,
        session_id=session["session_id"],
    )
    arguments["expected_session_revision"] = current["session_revision"]
    assert store.bump_asset_index_revision(project.project_id) == 1
    with pytest.raises(ValueError, match="asset_revision_mismatch"):
        store.begin_director_hermes_run(**arguments)


def test_stale_pending_is_interrupted_without_redispatch_after_process_restart(
    tmp_path: Path,
) -> None:
    clock = [datetime(2026, 7, 27, tzinfo=UTC)]
    store = LocalProjectStore(tmp_path / "projects", now=lambda: clock[0])
    project = store.bootstrap_project("creator-context-restart")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-a",
        session_payload={"segments": [], "history": []},
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
    )
    identity = {
        "project_id": project.project_id,
        "session_id": session["session_id"],
        "conversation_id": "conversation-a",
        "client_message_id": "message-a",
        "user_text": "help",
        "expected_session_revision": session["session_revision"],
        "expected_asset_index_revision": 0,
        "selected_segment_id": None,
    }
    crashed = store.begin_director_hermes_run(**identity)
    clock[0] += timedelta(seconds=301)
    restarted = LocalProjectStore(
        tmp_path / "projects", now=lambda: clock[0]
    )
    recovered = restarted.recover_interrupted_director_hermes_runs(
        project_id=project.project_id
    )
    assert [item["run_id"] for item in recovered] == [crashed["run_id"]]
    order: list[str] = []
    gateway = _Gateway(order)
    service = HermesRunService(
        store=restarted,
        gateway_client=gateway,
        context_builder=lambda **kwargs: SimpleNamespace(
            session_revision=kwargs["expected_session_revision"],
            asset_index_revision=0,
            model_dump=lambda **_: {
                "schema_version": "videobox.yujin-context.v1",
                "project_id": kwargs["project_id"],
                "session_id": kwargs["session_id"],
                "session_revision": kwargs["expected_session_revision"],
                "asset_index_revision": 0,
            },
        ),
    )

    async def scenario():
        run = await service.create_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conversation-a",
            client_message_id="message-a",
            text="help",
            expected_session_revision=session["session_revision"],
        )
        events = [
            event
            async for event in service.subscribe(
                run.run_id,
                project_id=project.project_id,
                conversation_id="conversation-a",
            )
        ]
        await service.shutdown()
        return events

    events = asyncio.run(scenario())
    durable = restarted.get_director_hermes_run(
        project_id=project.project_id,
        run_id=crashed["run_id"],
    )
    assert durable["status"] == "interrupted"
    assert events[-1].event_type == "blocked"
    assert gateway.stream_calls == 0


def test_legacy_terminal_replays_and_legacy_pending_is_blocked_without_dispatch(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("creator-context-legacy")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-a",
        session_payload={"segments": [], "history": []},
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
    )

    def begin(client_message_id: str):
        return store.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conversation-a",
            client_message_id=client_message_id,
            user_text=client_message_id,
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
        )

    completed = begin("completed")
    blocked = begin("blocked")
    pending = begin("pending")
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=completed["run_id"],
        owner_token=completed["owner_token"],
        status="completed",
        assistant_text="done",
        retryable=False,
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=blocked["run_id"],
        owner_token=blocked["owner_token"],
        status="blocked",
        assistant_text="manual",
        retryable=True,
    )
    store._execute(
        project.project_id,
        "UPDATE director_hermes_runs SET expected_session_revision = 0, "
        "expected_asset_index_revision = -1, selected_segment_id = NULL",
        (),
    )
    restarted = LocalProjectStore(tmp_path / "projects")

    for client_message_id, status, text in (
        ("completed", "completed", "done"),
        ("blocked", "blocked", "manual"),
    ):
        replay = restarted.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conversation-a",
            client_message_id=client_message_id,
            user_text=client_message_id,
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
        )
        assert replay["status"] == status
        assert replay["assistant_text"] == text
        assert replay["dispatch"] is False

    recovered = restarted.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-a",
        client_message_id="pending",
        user_text="pending",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert recovered["status"] == "blocked"
    assert recovered["dispatch"] is False
    assert recovered["assistant_text"].startswith("Hermes is temporarily")
    assert restarted.get_director_hermes_run(
        project_id=project.project_id,
        run_id=pending["run_id"],
    )["status"] == "blocked"
    with pytest.raises(ValueError, match="different_content"):
        restarted.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id="conversation-a",
            client_message_id="completed",
            user_text="changed",
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
        )


def test_legacy_pending_cas_loser_replays_winner_without_second_assistant(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    pending = {
        "project_id": "project-a",
        "session_id": "session-a",
        "conversation_id": "conversation-a",
        "run_id": "run-a",
        "user_text": "help",
        "expected_session_revision": 0,
        "expected_asset_index_revision": -1,
        "selected_segment_id": None,
        "status": "pending",
        "assistant_message_id": None,
        "owner_token": "legacy-owner",
        "heartbeat_at": "2026-07-27T00:00:00+00:00",
    }
    winner = {
        **pending,
        "status": "blocked",
        "assistant_message_id": "winner-assistant",
    }

    class Cursor:
        def __init__(self, *, rowcount=-1, row=None):
            self.rowcount = rowcount
            self._row = row

        def fetchone(self):
            return self._row

    class LosingConnection:
        def __init__(self):
            self.statements: list[str] = []

        def execute(self, statement, _parameters):
            normalized = " ".join(statement.split())
            self.statements.append(normalized)
            if normalized.startswith("UPDATE director_hermes_runs"):
                return Cursor(rowcount=0)
            if normalized.startswith("SELECT * FROM director_hermes_runs"):
                return Cursor(row=winner)
            if normalized.startswith("SELECT text FROM director_messages"):
                return Cursor(row={"text": "winner fallback"})
            raise AssertionError(normalized)

    connection = LosingConnection()
    replay = store._director_hermes_existing_result(
        connection=connection,
        row=pending,
        project_id="project-a",
        session_id="session-a",
        conversation_id="conversation-a",
        user_text="help",
        expected_session_revision=7,
        expected_asset_index_revision=13,
        selected_segment_id=None,
        now="2026-07-27T00:01:00+00:00",
    )

    assert replay["status"] == "blocked"
    assert replay["assistant_text"] == "winner fallback"
    assert replay["dispatch"] is False
    assert not any(
        statement.startswith("INSERT INTO director_messages")
        for statement in connection.statements
    )
