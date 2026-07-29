from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore


def _scope(tmp_path: Path, *, now=None):
    store = LocalProjectStore(tmp_path / "projects", now=now)
    project = store.bootstrap_project("durable Hermes events")
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


def _begin(
    store: LocalProjectStore,
    *,
    project_id: str,
    session_id: str,
    client_message_id: str,
):
    return store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id="conv",
        client_message_id=client_message_id,
        user_text=f"question {client_message_id}",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )


def test_run_events_are_atomic_ordered_and_restart_replayable(tmp_path: Path) -> None:
    store, project_id, session_id = _scope(tmp_path)
    run = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="one",
    )

    assert store.list_director_hermes_run_events(
        project_id=project_id,
        conversation_id="conv",
        run_id=run["run_id"],
    ) == [
        {
            "event_id": 1,
            "event_type": "run_started",
            "text": "",
            "retryable": False,
        }
    ]

    assert store.append_director_hermes_draft_event(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        assistant_draft_text="visible draft",
        event_text="visible draft",
        expected_event_id=2,
    )
    assert not store.append_director_hermes_draft_event(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        assistant_draft_text="visible draft duplicate",
        event_text=" duplicate",
        expected_event_id=2,
    )
    assert store.get_director_hermes_run(
        project_id=project_id, run_id=run["run_id"]
    )["status"] == "streaming"

    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="visible draft and final",
        public_text="visible draft",
        retryable=False,
    )
    assert not store.complete_director_hermes_run(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="duplicate",
        public_text="",
        retryable=False,
    )

    restarted = LocalProjectStore(tmp_path / "projects")
    assert restarted.list_director_hermes_run_events(
        project_id=project_id,
        conversation_id="conv",
        run_id=run["run_id"],
        after_event_id=2,
    ) == [
        {
            "event_id": 3,
            "event_type": "text_delta",
            "text": " and final",
            "retryable": False,
        },
        {
            "event_id": 4,
            "event_type": "run_completed",
            "text": "visible draft and final",
            "retryable": False,
        },
    ]
    messages = restarted.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert [(item["role"], item["text"]) for item in messages] == [
        ("user", "question one"),
        ("assistant", "visible draft and final"),
    ]


def test_recovery_interrupts_orphans_once_without_provider_redispatch(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    pending = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="pending",
    )
    streaming = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="streaming",
    )
    assert store.append_director_hermes_draft_event(
        project_id=project_id,
        run_id=streaming["run_id"],
        owner_token=streaming["owner_token"],
        assistant_draft_text="already visible",
        event_text="already visible",
        expected_event_id=2,
    )

    recovered = store.recover_interrupted_director_hermes_runs(
        project_id=project_id
    )
    assert {item["run_id"] for item in recovered} == {
        pending["run_id"],
        streaming["run_id"],
    }
    assert (
        store.recover_interrupted_director_hermes_runs(project_id=project_id)
        == []
    )
    for run in (pending, streaming):
        durable = store.get_director_hermes_run(
            project_id=project_id, run_id=run["run_id"]
        )
        assert durable["status"] == "interrupted"
        events = store.list_director_hermes_run_events(
            project_id=project_id,
            conversation_id="conv",
            run_id=run["run_id"],
        )
        assert events[-1]["event_type"] == "blocked"
        assert events[-1]["retryable"] is True
    messages = store.list_director_messages(
        project_id=project_id, conversation_id="conv"
    )
    assert [item["role"] for item in messages].count("assistant") == 2


def test_retention_prunes_old_terminal_payload_but_keeps_tombstone_and_active(
    tmp_path: Path,
) -> None:
    instant = [datetime(2026, 1, 1, tzinfo=UTC)]
    store, project_id, session_id = _scope(tmp_path, now=lambda: instant[0])
    old = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="old",
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=old["run_id"],
        owner_token=old["owner_token"],
        status="blocked",
        assistant_text="safe fallback",
        public_text="",
        retryable=True,
    )
    instant[0] += timedelta(days=31)
    newest = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="newest",
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=newest["run_id"],
        owner_token=newest["owner_token"],
        status="completed",
        assistant_text="answer",
        public_text="",
        retryable=False,
    )
    active = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="active",
    )

    with pytest.raises(ValueError, match="hermes_run_events_expired"):
        store.list_director_hermes_run_events(
            project_id=project_id,
            conversation_id="conv",
            run_id=old["run_id"],
        )
    assert store.get_director_hermes_run(
        project_id=project_id, run_id=old["run_id"]
    )["status"] == "blocked"
    assert store.list_director_hermes_run_events(
        project_id=project_id,
        conversation_id="conv",
        run_id=active["run_id"],
    )[0]["event_type"] == "run_started"


def test_retention_prunes_the_129th_recent_terminal_stream(tmp_path: Path) -> None:
    store, project_id, session_id = _scope(tmp_path)
    runs = []
    for index in range(129):
        run = _begin(
            store,
            project_id=project_id,
            session_id=session_id,
            client_message_id=f"recent-{index:03d}",
        )
        assert store.complete_director_hermes_run(
            project_id=project_id,
            run_id=run["run_id"],
            owner_token=run["owner_token"],
            status="completed",
            assistant_text=f"answer {index}",
            public_text="",
            retryable=False,
        )
        runs.append(run)

    expired = 0
    for run in runs:
        try:
            store.list_director_hermes_run_events(
                project_id=project_id,
                conversation_id="conv",
                run_id=run["run_id"],
            )
        except ValueError as error:
            assert str(error) == "hermes_run_events_expired"
            expired += 1
    assert expired == 1


def test_event_rows_store_only_the_public_contract(tmp_path: Path) -> None:
    store, project_id, session_id = _scope(tmp_path)
    run = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="redaction",
    )
    connection = store._connection(project_id)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(director_hermes_run_events)"
            ).fetchall()
        }
    finally:
        connection.close()
    assert columns == {
        "project_id",
        "run_id",
        "event_id",
        "event_type",
        "text",
        "retryable",
        "created_at",
    }
    assert "secret" not in repr(
        store.list_director_hermes_run_events(
            project_id=project_id,
            conversation_id="conv",
            run_id=run["run_id"],
        )
    ).lower()


def test_pre_c1_terminal_tombstone_backfills_replay_events_on_upgrade(
    tmp_path: Path,
) -> None:
    store, project_id, session_id = _scope(tmp_path)
    run = _begin(
        store,
        project_id=project_id,
        session_id=session_id,
        client_message_id="pre-c1",
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="durable old answer",
        public_text="",
        retryable=False,
    )
    connection = store._connection(project_id)
    try:
        connection.execute(
            "DELETE FROM director_hermes_run_events "
            "WHERE project_id = ? AND run_id = ?",
            (project_id, run["run_id"]),
        )
        connection.execute(
            "UPDATE director_hermes_runs SET next_event_id = 1 "
            "WHERE project_id = ? AND run_id = ?",
            (project_id, run["run_id"]),
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = LocalProjectStore(tmp_path / "projects")
    assert upgraded.list_director_hermes_run_events(
        project_id=project_id,
        conversation_id="conv",
        run_id=run["run_id"],
    ) == [
        {
            "event_id": 1,
            "event_type": "run_started",
            "text": "",
            "retryable": False,
        },
        {
            "event_id": 2,
            "event_type": "run_completed",
            "text": "durable old answer",
            "retryable": False,
        },
    ]
