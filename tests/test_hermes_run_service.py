from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from videobox_api.agent_gateway_client import AgentGatewayEvent
from videobox_api.hermes_run_service import HermesRunService
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.postgres_compat import translate_sql


def _scope(tmp_path: Path, *, now=None):
    store = LocalProjectStore(tmp_path / "projects", now=now)
    project = store.bootstrap_project("hermes")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conv",
    )
    return store, project.project_id, session["session_id"]


class _Gateway:
    def __init__(self, events=None) -> None:
        self.calls = 0
        self.events = events or [
            AgentGatewayEvent("text_delta", "안녕"),
            AgentGatewayEvent("run_completed", "안녕하세요"),
        ]

    async def stream_run(self, **_):
        self.calls += 1
        for event in self.events:
            yield event


def test_run_persists_user_before_dispatch_and_final_before_terminal_event(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    gateway = _Gateway()
    service = HermesRunService(store=store, gateway_client=gateway)

    async def scenario():
        run = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="client-1",
            text="질문",
        )
        assert [
            item["role"]
            for item in store.list_director_messages(
                project_id=project_id, conversation_id="conv"
            )
        ] == ["user"]
        await run.task
        events = [event async for event in service.subscribe(run.run_id)]
        retry = await service.create_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="client-1",
            text="질문",
        )
        return run, retry, events

    run, retry, events = asyncio.run(scenario())
    assert retry.run_id == run.run_id
    assert gateway.calls == 1
    assert [event.event_type for event in events] == [
        "run_started",
        "text_delta",
        "run_completed",
    ]
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert [(item["role"], item["text"]) for item in messages] == [
        ("user", "질문"),
        ("assistant", "안녕하세요"),
    ]
    assert messages[1]["metadata"]["hermes_status"] == "completed"


def test_changed_text_conflicts_and_owner_token_fences_stale_finalizer(
    tmp_path: Path,
) -> None:
    clock = [datetime(2026, 7, 26, tzinfo=UTC)]
    store, project_id, session_id = _scope(tmp_path, now=lambda: clock[0])
    first = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="same",
        user_text="one",
    )
    with pytest.raises(
        ValueError, match="client_message_id_reused_with_different_content"
    ):
        store.begin_director_hermes_run(
            project_id=project_id,
            session_id=session_id,
            conversation_id="conv",
            client_message_id="same",
            user_text="changed",
        )
    clock[0] += timedelta(seconds=301)
    restarted = LocalProjectStore(tmp_path / "projects", now=lambda: clock[0])
    reclaimed = restarted.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id="same",
        user_text="one",
    )
    assert reclaimed["run_id"] == first["run_id"]
    assert reclaimed["dispatch"] is True
    assert reclaimed["owner_token"] != first["owner_token"]
    assert (
        store.complete_director_hermes_run(
            project_id=project_id,
            run_id=first["run_id"],
            owner_token=first["owner_token"],
            status="completed",
            assistant_text="stale",
            retryable=False,
        )
        is False
    )
    assert restarted.complete_director_hermes_run(
        project_id=project_id,
        run_id=first["run_id"],
        owner_token=reclaimed["owner_token"],
        status="completed",
        assistant_text="winner",
        retryable=False,
    )
    assert [item["text"] for item in restarted.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )] == ["one", "winner"]


def test_postgres_translation_preserves_atomic_upsert_contract() -> None:
    statement = (
        "INSERT INTO director_hermes_runs (run_id, conversation_id, "
        "client_message_id) VALUES (?, ?, ?) "
        "ON CONFLICT (conversation_id, client_message_id) DO NOTHING"
    )
    translated = translate_sql(statement)
    assert "ON CONFLICT (conversation_id, client_message_id) DO NOTHING" in translated
    assert translated.count("%s") == 3
