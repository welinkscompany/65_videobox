from __future__ import annotations

from copy import deepcopy
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest.mock import patch
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_core_engine.editing_session import select_segment_tts_replacement
from videobox_storage.postgres_project_store import PostgresProjectStore, _PostgresConnection
from videobox_storage.local_project_store import EditingSessionRevisionConflict, LocalProjectStore


def _approve_postgres_brief(store: PostgresProjectStore, project_id: str) -> dict:
    source = store.project_root(project_id) / "brief-source.txt"
    source.write_text("동시 요청을 검증하는 짧은 대본입니다.", encoding="utf-8")
    script_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.SCRIPT_DOCUMENT,
        source_path=source,
    )
    brief = store.create_creation_brief(
        project_id=project_id,
        script_filename="script.txt",
        script_text="동시 요청을 검증하는 짧은 대본입니다.",
        idempotency_key="brief",
        capability_profile={},
        script_asset_id=script_asset.asset_id,
        runtime=type("NoQuestions", (), {"plan_questions": lambda *_args, **_kwargs: []})(),
    )
    brief = store.bypass_creation_interview(
        project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"]
    )
    brief = store.update_creation_brief_summary(
        project_id=project_id, brief_id=brief["brief_id"], summary="동시성 확인", expected_revision=brief["revision"]
    )
    return store.approve_creation_brief(
        project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"]
    )


def _run_two_requests_at_same_insert(*, statement_marker: str, request) -> list[dict]:
    """Make both real PostgreSQL transactions observe the pre-insert state."""
    barrier = Barrier(2)
    original_execute = _PostgresConnection.execute

    def gate_insert(self, statement: str, parameters=None):
        if statement_marker in statement:
            barrier.wait(timeout=10)
        return original_execute(self, statement, parameters)

    with patch.object(_PostgresConnection, "execute", gate_insert):
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: request(), range(2)))


def _cleanup_postgres_hermes_project(
    store: PostgresProjectStore,
    project_id: str,
) -> None:
    connection = store._connection(project_id)
    try:
        for table in (
            "director_hermes_run_events",
            "director_hermes_runs",
            "director_messages",
            "director_conversations",
            "editing_sessions",
            "director_asset_index_revisions",
            "projects",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE project_id = ?",
                (project_id,),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("VIDEOBOX_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set VIDEOBOX_TEST_POSTGRES_URL to run PostgreSQL store integration tests")
    return value


def test_postgres_store_bootstraps_and_lists_a_project(tmp_path: Path, postgres_url: str) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)

    project = store.bootstrap_project(f"Postgres project {uuid4().hex}")

    assert next(item for item in store.list_projects() if item["project_id"] == project.project_id) == {
        "project_id": project.project_id,
        "name": project.name,
        "status": "draft",
        "root_storage_uri": f"local://projects/{project.project_id}",
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def test_postgres_store_durably_consumes_and_revokes_hermes_capabilities(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes ledger {uuid4().hex}")

    assert store.consume_hermes_capability(
        project_id=project.project_id, jti="consumed-jti", expires_at=1_900_000_000
    ) == "accepted"
    assert store.consume_hermes_capability(
        project_id=project.project_id, jti="consumed-jti", expires_at=1_900_000_000
    ) == "consumed"

    store.revoke_hermes_capability(
        project_id=project.project_id, jti="revoked-jti", expires_at=1_900_000_000
    )
    assert store.consume_hermes_capability(
        project_id=project.project_id, jti="revoked-jti", expires_at=1_900_000_000
    ) == "revoked"
    store.revoke_hermes_capability(project_id=project.project_id, jti="expired-jti", expires_at=1)
    assert store.consume_hermes_capability(
        project_id=project.project_id, jti="fresh-jti", expires_at=1_900_000_000
    ) == "accepted"
    connection = store._connection(project.project_id)
    try:
        assert connection.execute(
            "SELECT jti FROM hermes_capability_ledger WHERE project_id = ? AND jti = ?",
            (project.project_id, "expired-jti"),
        ).fetchone() is None
    finally:
        connection.close()


def test_postgres_hermes_events_use_durable_cursor_and_terminal_cas(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes events {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert store.append_director_hermes_draft_event(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        assistant_draft_text="visible",
        event_text="visible",
        expected_event_id=2,
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="visible answer",
        public_text="visible",
        retryable=False,
    )
    assert [
        item["event_id"]
        for item in store.list_director_hermes_run_events(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=run["run_id"],
        )
    ] == [1, 2, 3, 4]


def test_postgres_hermes_cursor_and_terminal_have_one_concurrent_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes CAS {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        draft_results = list(
            executor.map(
                lambda suffix: store.append_director_hermes_draft_event(
                    project_id=project.project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    assistant_draft_text=f"visible {suffix}",
                    event_text=f"visible {suffix}",
                    expected_event_id=2,
                ),
                ("one", "two"),
            )
        )
    assert sorted(draft_results) == [False, True]
    durable = store.get_director_hermes_run(
        project_id=project.project_id, run_id=run["run_id"]
    )
    public_text = durable["assistant_draft_text"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        terminal_results = list(
            executor.map(
                lambda _: store.complete_director_hermes_run(
                    project_id=project.project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    status="completed",
                    assistant_text=f"{public_text} final",
                    public_text=public_text,
                    retryable=False,
                ),
                range(2),
            )
        )
    assert sorted(terminal_results) == [False, True]
    events = store.list_director_hermes_run_events(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=run["run_id"],
    )
    assert [item["event_id"] for item in events] == [1, 2, 3, 4]
    assert sum(item["event_type"] == "run_completed" for item in events) == 1


def test_postgres_pre_c1_terminal_tombstone_backfills_exact_replay(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes legacy {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="legacy answer",
        public_text="",
        retryable=False,
    )
    connection = store._connection(project.project_id)
    try:
        connection.execute(
            "DELETE FROM director_hermes_run_events "
            "WHERE project_id = ? AND run_id = ?",
            (project.project_id, run["run_id"]),
        )
        connection.execute(
            "UPDATE director_hermes_runs SET next_event_id = 1 "
            "WHERE project_id = ? AND run_id = ?",
            (project.project_id, run["run_id"]),
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = PostgresProjectStore(tmp_path, database_url=postgres_url)
    assert upgraded.list_director_hermes_run_events(
        project_id=project.project_id,
        conversation_id=conversation_id,
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
            "text": "legacy answer",
            "retryable": False,
        },
    ]


def test_postgres_pre_c2_retry_column_migrates_without_losing_existing_run(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes retry migration {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="migration source",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )

    try:
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "ALTER TABLE director_hermes_runs "
                "DROP COLUMN retry_of_run_id"
            )
            connection.commit()
        finally:
            connection.close()

        upgraded = PostgresProjectStore(tmp_path, database_url=postgres_url)
        preserved = upgraded.get_director_hermes_run(
            project_id=project.project_id,
            run_id=run["run_id"],
        )
        assert preserved["run_id"] == run["run_id"]
        assert preserved["user_text"] == "migration source"
        assert preserved["status"] == "pending"
        assert preserved["retry_of_run_id"] is None
    finally:
        recovered = PostgresProjectStore(tmp_path, database_url=postgres_url)
        _cleanup_postgres_hermes_project(recovered, project.project_id)


def test_postgres_pre_message_order_migration_preserves_fixed_clock_exchanges(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Director message order migration {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    first = store.append_director_exchange(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="message-1",
        user_text="user-1",
        assistant_text="assistant-1",
    )
    store.append_director_exchange(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="message-2",
        user_text="user-2",
        assistant_text="assistant-2",
    )

    try:
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "DROP INDEX IF EXISTS "
                "director_messages_conversation_order_idx"
            )
            connection.execute(
                "ALTER TABLE director_messages DROP COLUMN message_order"
            )
            connection.commit()
        finally:
            connection.close()

        upgraded = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        replay = upgraded.append_director_exchange(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            client_message_id="message-1",
            user_text="user-1",
            assistant_text="must-not-replace",
        )
        assert replay == first
        assert [
            message["text"]
            for message in upgraded.list_director_messages(
                project_id=project.project_id,
                conversation_id=conversation_id,
            )
        ] == ["user-1", "assistant-1", "user-2", "assistant-2"]

        connection = upgraded._connection(project.project_id)
        try:
            order_row = connection.execute(
                """
                SELECT COUNT(*) AS message_count,
                       COUNT(message_order) AS non_null_count,
                       COUNT(DISTINCT message_order) AS unique_count
                FROM director_messages
                WHERE project_id = ? AND conversation_id = ?
                """,
                (project.project_id, conversation_id),
            ).fetchone()
        finally:
            connection.close()
        assert order_row is not None
        assert (
            int(order_row["message_count"]),
            int(order_row["non_null_count"]),
            int(order_row["unique_count"]),
        ) == (4, 4, 4)

        repeated = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        assert [
            message["text"]
            for message in repeated.list_director_messages(
                project_id=project.project_id,
                conversation_id=conversation_id,
            )
        ] == ["user-1", "assistant-1", "user-2", "assistant-2"]
    finally:
        recovered = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        _cleanup_postgres_hermes_project(recovered, project.project_id)


@pytest.mark.parametrize("source_status", ("blocked", "interrupted"))
def test_postgres_retry_is_linked_and_identity_atomic(
    tmp_path: Path,
    postgres_url: str,
    source_status: str,
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(
        f"Hermes retry atomic {source_status} {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "caption_text": "장면",
                }
            ],
            "history": [],
        },
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    source = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"source-{uuid4().hex}",
        user_text="retry exact text",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
        selected_segment_id="segment-1",
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=source["run_id"],
        owner_token=source["owner_token"],
        status=source_status,
        assistant_text="terminal",
        public_text="",
        retryable=True,
    )

    try:
        before_messages = store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        )
        with pytest.raises(
            ValueError,
            match="hermes_run_retry_identity_mismatch",
        ):
            store.begin_director_hermes_run(
                project_id=project.project_id,
                session_id=session["session_id"],
                conversation_id=conversation_id,
                client_message_id=f"invalid-{uuid4().hex}",
                user_text="changed text",
                expected_session_revision=session["session_revision"],
                expected_asset_index_revision=0,
                selected_segment_id="segment-1",
                retry_of_run_id=source["run_id"],
            )
        with pytest.raises(KeyError, match="director_hermes_run_missing"):
            store.begin_director_hermes_run(
                project_id=project.project_id,
                session_id=session["session_id"],
                conversation_id="wrong-conversation",
                client_message_id=f"wrong-scope-{uuid4().hex}",
                user_text="retry exact text",
                expected_session_revision=session["session_revision"],
                expected_asset_index_revision=0,
                selected_segment_id="segment-1",
                retry_of_run_id=source["run_id"],
            )
        assert store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        ) == before_messages

        retried = store.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            client_message_id=f"retry-{uuid4().hex}",
            user_text="retry exact text",
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
            selected_segment_id="segment-1",
            retry_of_run_id=source["run_id"],
        )
        durable = store.get_director_hermes_run(
            project_id=project.project_id,
            run_id=retried["run_id"],
        )
        assert durable["retry_of_run_id"] == source["run_id"]
        assert durable["status"] == "pending"
        assert [
            event["event_type"]
            for event in store.list_director_hermes_run_events(
                project_id=project.project_id,
                conversation_id=conversation_id,
                run_id=retried["run_id"],
            )
        ] == ["run_started"]
        after_messages = store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        )
        assert len(after_messages) == len(before_messages) + 1
        assert after_messages[-1]["role"] == "user"
        assert after_messages[-1]["text"] == "retry exact text"
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_sqlite_store_purges_expired_hermes_capability_ledger_rows(tmp_path: Path) -> None:
    instant = datetime(2026, 7, 19, tzinfo=UTC)
    store = LocalProjectStore(tmp_path, now=lambda: instant)
    project = store.bootstrap_project("Hermes expiry cleanup")

    store.revoke_hermes_capability(project_id=project.project_id, jti="expired-jti", expires_at=1)
    assert store.consume_hermes_capability(
        project_id=project.project_id,
        jti="fresh-jti",
        expires_at=int(instant.timestamp()) + 120,
    ) == "accepted"

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        rows = connection.execute("SELECT jti FROM hermes_capability_ledger ORDER BY jti").fetchall()
    assert rows == [("fresh-jti",)]


def test_sqlite_concurrent_hermes_capability_consumption_has_one_winner(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Hermes concurrent SQLite ledger")
    barrier = Barrier(2)
    original_connection = store._connection

    class GateConnection:
        def __init__(self, connection) -> None:
            self._connection = connection

        def execute(self, statement: str, parameters=None):
            if "INSERT INTO hermes_capability_ledger" in statement:
                barrier.wait(timeout=10)
            return self._connection.execute(statement, parameters or ())

        def __getattr__(self, name: str):
            return getattr(self._connection, name)

    def gated_connection(project_id: str):
        return GateConnection(original_connection(project_id))

    with patch.object(store, "_connection", side_effect=gated_connection):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: store.consume_hermes_capability(
                        project_id=project.project_id,
                        jti="concurrent-jti",
                        expires_at=1_900_000_000,
                    ),
                    range(2),
                )
            )

    assert sorted(results) == ["accepted", "consumed"]


def test_postgres_concurrent_hermes_capability_consumption_has_one_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes concurrent ledger {uuid4().hex}")

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO hermes_capability_ledger",
        request=lambda: {
            "state": store.consume_hermes_capability(
                project_id=project.project_id,
                jti="concurrent-jti",
                expires_at=1_784_000_000,
            )
        },
    )

    assert sorted(item["state"] for item in results) == ["accepted", "consumed"]


def test_postgres_concurrent_creation_brief_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent brief {uuid4().hex}")
    script = tmp_path / "same.txt"
    script.write_text("동일한 클릭은 하나의 brief만 만들어야 합니다.", encoding="utf-8")
    script_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.SCRIPT_DOCUMENT,
        source_path=script,
    )
    payload = {
        "project_id": project.project_id,
        "script_filename": "same.txt",
        "script_text": "동일한 클릭은 하나의 brief만 만들어야 합니다.",
        "idempotency_key": "same-click",
        "capability_profile": {},
        "script_asset_id": script_asset.asset_id,
        "runtime": type("NoQuestions", (), {"plan_questions": lambda *_args, **_kwargs: []})(),
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO creation_briefs",
        request=lambda: store.create_creation_brief(**payload),
    )

    assert {result["brief_id"] for result in results}.__len__() == 1
    assert len(store.list_creation_briefs(project_id=project.project_id)) == 1


def test_postgres_concurrent_readiness_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent readiness {uuid4().hex}")
    brief = _approve_postgres_brief(store, project.project_id)
    payload = {
        "project_id": project.project_id,
        "brief_id": brief["brief_id"],
        "narration_choice": {"kind": "silent"},
        "idempotency_key": "same-click",
        "expected_brief_revision": brief["revision"],
        "defer": False,
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO draft_readiness",
        request=lambda: store.start_draft_readiness(**payload),
    )

    assert {result["readiness_id"] for result in results}.__len__() == 1
    assert len(store.list_draft_readiness(project_id=project.project_id)) == 1


def test_postgres_concurrent_atomic_bundle_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent bundle {uuid4().hex}")
    brief = _approve_postgres_brief(store, project.project_id)
    readiness = store.start_draft_readiness(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        narration_choice={"kind": "silent"},
        idempotency_key="ready",
        expected_brief_revision=brief["revision"],
        defer=False,
    )
    payload = {
        "project_id": project.project_id,
        "brief_id": brief["brief_id"],
        "expected_brief_revision": brief["revision"],
        "readiness_id": readiness["readiness_id"],
        "expected_readiness_revision": readiness["revision"],
        "idempotency_key": "same-click",
        "allow_placeholder": True,
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO atomic_draft_bundles",
        request=lambda: store.materialize_atomic_draft_bundle(**payload),
    )

    assert {result["bundle_id"] for result in results}.__len__() == 1
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1


def test_api_selects_postgres_store_when_database_url_is_configured(
    monkeypatch, tmp_path: Path, postgres_url: str
) -> None:
    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", postgres_url)

    with TestClient(create_app(projects_root=tmp_path)) as client:
        assert isinstance(client.app.state.store, PostgresProjectStore)
        created = client.post("/api/projects", json={"name": f"API PostgreSQL project {uuid4().hex}"})
        listed = client.get("/api/projects")

    assert created.status_code == 201
    assert created.json()["project_id"] in {item["project_id"] for item in listed.json()["projects"]}


def test_postgres_store_persists_existing_project_asset_and_timeline_mutation(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL mutation project {uuid4().hex}")
    source_audio = tmp_path / "existing-project-narration.wav"
    source_audio.write_bytes(b"narration bytes")

    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=source_audio,
        metadata={"source": "postgres-integration"},
    )
    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    updated = store.update_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
        timeline_payload={
            **saved,
            "version": "v002",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )
    fetched = store.get_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"])

    assert (tmp_path / "projects" / project.project_id / "inputs" / "narration" / source_audio.name).read_bytes() == b"narration bytes"
    assert updated["version"] == "v002"
    assert fetched["tracks"][0]["clips"][0]["asset_id"] == asset.asset_id
    assert fetched["summary"]["track_count"] == 1


def test_postgres_restart_reconciliation_preserves_batch_destination_registered_in_postgres_despite_stale_sqlite(
    tmp_path: Path, postgres_url: str
) -> None:
    root = tmp_path / "projects"
    store = PostgresProjectStore(root, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL reconciliation project {uuid4().hex}")
    source = tmp_path / "registered.mp4"
    source.write_bytes(b"registered-by-postgres")
    registered = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    destination = store.resolve_storage_uri(project_id=project.project_id, storage_uri=registered.storage_uri)
    operations = store.project_root(project.project_id) / ".batch-director-operations"
    stage = operations / "op-postgres-authority" / "stage.mp4"
    stage.parent.mkdir(parents=True)
    stage.write_bytes(b"discarded-stage")
    (store.project_root(project.project_id) / "db").mkdir(exist_ok=True)
    stale_sqlite = store.database_path(project.project_id)
    with sqlite3.connect(stale_sqlite) as stale_connection:
        stale_connection.execute("CREATE TABLE assets (asset_id TEXT, project_id TEXT, storage_uri TEXT)")
        stale_connection.execute(
            "INSERT INTO assets (asset_id, project_id, storage_uri) VALUES (?, ?, ?)",
            ("stale-asset", project.project_id, "local://projects/stale/assets/imported/other.mp4"),
        )
    manifest = operations / "op-postgres-authority.json"
    manifest.write_text(
        json.dumps(
            {
                "operation_id": "op-postgres-authority",
                "status": "staging",
                "entries": [
                    {
                        "staged_path": str(stage),
                        "destination_path": str(destination),
                        "sha256": sha256(destination.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    PostgresProjectStore(root, database_url=postgres_url)

    assert destination.read_bytes() == b"registered-by-postgres"
    assert not stage.exists()
    assert not manifest.exists()


def test_postgres_store_scopes_identical_timeline_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first timeline project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second timeline project {uuid4().hex}")

    first_timeline = store.save_timeline_run(
        project_id=first_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )
    second_timeline = store.save_timeline_run(
        project_id=second_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )

    assert first_timeline["timeline_id"] == second_timeline["timeline_id"] == "timeline_001"
    assert store.get_timeline_run(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"]
    )["project_id"] == first_project.project_id
    assert store.get_timeline_run(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"]
    )["project_id"] == second_project.project_id
    assert store._list_timeline_ids(project_id=first_project.project_id) == ["timeline_001"]
    assert store._list_timeline_ids(project_id=second_project.project_id) == ["timeline_001"]


def test_postgres_store_scopes_identical_session_and_export_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first scoped IDs project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second scoped IDs project {uuid4().hex}")

    def save_timeline(project_id: str) -> dict:
        return store.save_timeline_run(
            project_id=project_id,
            output_mode="review",
            timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
        )

    first_timeline = save_timeline(first_project.project_id)
    second_timeline = save_timeline(second_project.project_id)
    first_session = store.save_editing_session(
        project_id=first_project.project_id,
        timeline_id=first_timeline["timeline_id"],
        session_payload={"caption_style": "first", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    second_session = store.save_editing_session(
        project_id=second_project.project_id,
        timeline_id=second_timeline["timeline_id"],
        session_payload={"caption_style": "second", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    assert first_session["session_id"] == second_session["session_id"] == "editing_session_001"

    store.update_editing_session(
        project_id=first_project.project_id,
        session_id=first_session["session_id"],
        session_payload={"caption_style": "first-updated", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
        expected_revision=1,
    )
    assert store.get_editing_session(project_id=first_project.project_id, session_id=first_session["session_id"])["caption_style"] == "first-updated"
    assert store.get_editing_session(project_id=second_project.project_id, session_id=second_session["session_id"])["caption_style"] == "second"

    first_source = tmp_path / "first-draft"
    second_source = tmp_path / "second-draft"
    first_source.mkdir()
    second_source.mkdir()
    (first_source / "draft.txt").write_text("first", encoding="utf-8")
    (second_source / "draft.txt").write_text("second", encoding="utf-8")
    first_export = store.save_capcut_draft_export(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"], source_draft_path=first_source
    )
    second_export = store.save_capcut_draft_export(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"], source_draft_path=second_source
    )
    assert first_export["export_id"] == second_export["export_id"] == "export_001"

    store.update_capcut_draft_handoff(
        project_id=first_project.project_id, export_id=first_export["export_id"], handoff={"owner": "first"}
    )
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["handoff"] is None
    store._prune_old_exports(project_id=first_project.project_id, export_type="capcut_draft_export", keep_last=0)
    with pytest.raises(KeyError):
        store.get_capcut_draft_export(project_id=first_project.project_id, export_id=first_export["export_id"])
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["export_id"] == "export_001"


def test_postgres_store_scopes_assets_collections_and_jobs_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first operational scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second operational scope project {uuid4().hex}")
    first_source = tmp_path / "first.wav"
    second_source = tmp_path / "second.wav"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first_asset = store.register_asset(project_id=first_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=first_source)
    second_asset = store.register_asset(project_id=second_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=second_source)

    assert [item["asset_id"] for item in store.list_assets(project_id=first_project.project_id)] == [first_asset.asset_id]
    with pytest.raises(KeyError):
        store.get_asset(project_id=second_project.project_id, asset_id=first_asset.asset_id)
    store.update_asset_metadata(project_id=first_project.project_id, asset_id=first_asset.asset_id, metadata_patch={"owner": "first"})
    assert store.get_asset(project_id=second_project.project_id, asset_id=second_asset.asset_id)["metadata"] == {}

    for project, asset, suffix in ((first_project, first_asset, "first"), (second_project, second_asset, "second")):
        store._execute(
            project.project_id,
            "INSERT INTO segments (segment_id, project_id, text) VALUES (?, ?, ?)",
            (f"segment_{suffix}", project.project_id, suffix),
        )
        store._execute(
            project.project_id,
            "INSERT INTO recommendations (recommendation_id, project_id, recommendation_type, auto_apply_allowed, review_required, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"recommendation_{suffix}", project.project_id, "broll", 0, 0, "2026-07-19T00:00:00+00:00"),
        )

    assert [item["segment_id"] for item in store.list_segments(project_id=first_project.project_id)] == ["segment_first"]
    assert [item["recommendation_id"] for item in store.list_recommendation_rows(project_id=second_project.project_id)] == ["recommendation_second"]

    first_job = store.create_job(project_id=first_project.project_id, job_type=JobType.TIMELINE_BUILD)
    second_job = store.create_job(project_id=second_project.project_id, job_type=JobType.TIMELINE_BUILD)
    assert first_job["job_id"] == second_job["job_id"] == "timeline_build_job_001"
    store.update_job(project_id=first_project.project_id, job_id=first_job["job_id"], status=JobStatus.SUCCEEDED)
    assert store.get_job(project_id=second_project.project_id, job_id=second_job["job_id"])["status"] == JobStatus.PENDING.value
    assert [item["job_id"] for item in store.list_jobs(project_id=first_project.project_id)] == [first_job["job_id"]]


def test_postgres_store_scopes_tts_candidates_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first provider scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second provider scope project {uuid4().hex}")
    accepted = SimpleNamespace(technical_status="accepted", operator_review_status="pending")
    first_candidate = store.save_tts_candidate(
        project_id=first_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="first", acceptance=accepted
    )
    second_candidate = store.save_tts_candidate(
        project_id=second_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="second", acceptance=accepted
    )
    assert first_candidate["candidate_id"] == second_candidate["candidate_id"] == "tts_candidate_001"
    store.update_tts_candidate_listening_review(
        project_id=first_project.project_id, candidate_id=first_candidate["candidate_id"], decision="approved"
    )
    assert store.get_tts_candidate(project_id=second_project.project_id, candidate_id=second_candidate["candidate_id"])["operator_review_status"] == "pending"
    assert [item["candidate_id"] for item in store.list_tts_candidates(project_id=first_project.project_id, segment_id="segment_001")] == ["tts_candidate_001"]


def test_postgres_yujin_tts_terminal_attestation_rolls_back_after_asset_bytes_change(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-tts",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin TTS CAS {uuid4().hex}"
    )
    project_id = project.project_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "unchanged",
                "start_sec": 0.0,
                "end_sec": 1.0,
            }],
            "history": [],
        },
    )
    source = tmp_path / f"tts-{uuid4().hex}.wav"
    original_bytes = b"postgres-approved-generated-tts"
    source.write_bytes(original_bytes)
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.GENERATED_TTS_AUDIO,
        source_path=source,
    )
    acceptance = SimpleNamespace(
        technical_status="accepted",
        operator_review_status="approved",
        target_duration_sec=1.0,
        actual_duration_sec=1.0,
        failure_code=None,
    )
    tts_candidate = store.save_tts_candidate(
        project_id=project_id,
        segment_id="seg",
        asset_id=asset.asset_id,
        source_text="approved voice",
        acceptance=acceptance,
    )
    proposal_candidate = DirectorCandidate(
        candidate_id=f"voice-operation-{uuid4().hex}",
        visible_reference_code="P00-VOICE-01",
        media_type="voice",
        asset_id=asset.asset_id,
        library_asset_id=None,
        reason_chips=("voice",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "candidate_id": tts_candidate["candidate_id"],
            "asset_id": asset.asset_id,
        },
        expected_content_sha256=sha256(original_bytes).hexdigest(),
        media_revision=asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "voice",
            "yujin_actionable_operation": True,
            "command_kind": "apply_tts_candidate",
            "candidate_id": tts_candidate["candidate_id"],
            "source_media_kind": "generated_tts_audio",
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id=f"proposal-{uuid4().hex}",
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session["session_id"],
        target_segment_ids=("seg",),
        source_script_segment_ids=("seg",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(proposal_candidate,),
    )
    store.save_director_proposal(project_id, proposal)
    before = deepcopy(store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ))
    updated = select_segment_tts_replacement(
        session=before,
        segment_id="seg",
        recommendation_id=tts_candidate["candidate_id"],
        asset_id=asset.asset_id,
    )
    stored_asset = store.get_asset(
        project_id=project_id,
        asset_id=asset.asset_id,
    )
    stored_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=stored_asset["storage_uri"],
    )
    stored_path.write_bytes(b"tampered-after-proposal")

    with pytest.raises(
        EditingSessionRevisionConflict,
        match="attestation changed",
    ):
        store.update_yujin_b4_command_transaction(
            project_id=project_id,
            session_id=session["session_id"],
            proposal_id=proposal.proposal_id,
            candidate_id=proposal_candidate.candidate_id,
            command_kind="apply_tts_candidate",
            segment_id="seg",
            controls={
                "candidate_id": tts_candidate["candidate_id"],
                "asset_id": asset.asset_id,
            },
            session_payload=updated,
            expected_revision=session["session_revision"],
        )

    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
