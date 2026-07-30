from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.sqlite_schema import PROJECT_SCHEMA_STATEMENTS


def _write_pre_freshness_database(store: LocalProjectStore, project_id: str) -> None:
    """Create the schema shape that still needs the freshness-column migration."""
    database = store.database_path(project_id)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        for statement in PROJECT_SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def test_concurrent_connections_migrate_artifact_freshness_columns_once(tmp_path: Path) -> None:
    """New connections to one legacy project must not race on ALTER TABLE."""
    store = LocalProjectStore(tmp_path)

    # A fresh legacy-shaped database has five missing columns on several
    # artifact tables.  Repeating on independent project files makes the old
    # check-then-ALTER race observable without test-only production hooks.
    for number in range(16):
        project_id = f"migration-race-{number}"
        _write_pre_freshness_database(store, project_id)

        def connect_and_close(_: int) -> None:
            connection = store._connection(project_id)
            connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(connect_and_close, range(8)))

        connection = sqlite3.connect(store.database_path(project_id))
        try:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(review_approvals)").fetchall()
            }
        finally:
            connection.close()
        assert "source_session_id" in columns


def test_concurrent_connections_migrate_d2_memory_columns_once(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id = "memory-migration-race"
    database = store.database_path(project_id)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE yujin_memory_candidates (
                candidate_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                client_request_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                source_message_ids_json TEXT NOT NULL,
                memory_scope TEXT NOT NULL,
                category TEXT NOT NULL,
                proposed_text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    def connect_and_close(_: int) -> None:
        opened = store._connection(project_id)
        opened.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(connect_and_close, range(8)))

    connection = sqlite3.connect(database)
    try:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(yujin_memory_candidates)"
            ).fetchall()
        }
    finally:
        connection.close()
    assert {
        "external_ref",
        "operation_id",
        "provider_event_ref",
        "provider_memory_ref",
        "store_client_request_id",
        "write_claim_token",
        "write_claimed_at",
        "provider_call_started_at",
        "attempt_count",
        "storage_status",
    } <= columns


class _DuplicateColumnRaceConnection:
    def __init__(
        self,
        *,
        column_exists_after_race: bool,
        error_message: str = "duplicate column name: external_ref",
    ) -> None:
        self.column_exists_after_race = column_exists_after_race
        self.error_message = error_message
        self.schema_reads = 0

    def execute(self, statement: str):
        if statement == "PRAGMA table_info(yujin_memory_candidates)":
            self.schema_reads += 1
            columns = [
                "operation_id",
                "provider_event_ref",
                "provider_memory_ref",
                "store_client_request_id",
                "write_claim_token",
                "write_claimed_at",
                "provider_call_started_at",
                "attempt_count",
                "storage_status",
            ]
            if self.schema_reads > 1 and self.column_exists_after_race:
                columns.append("external_ref")
            return type(
                "Rows",
                (),
                {
                    "fetchall": lambda _self: [
                        (index, column)
                        for index, column in enumerate(columns)
                    ]
                },
            )()
        if statement.endswith("ADD COLUMN external_ref TEXT"):
            raise sqlite3.OperationalError(self.error_message)
        raise AssertionError(statement)


def test_duplicate_column_race_is_accepted_only_after_schema_recheck() -> None:
    LocalProjectStore._ensure_yujin_memory_operation_columns(
        _DuplicateColumnRaceConnection(column_exists_after_race=True)
    )

    with pytest.raises(
        sqlite3.OperationalError,
        match="duplicate column name: external_ref",
    ):
        LocalProjectStore._ensure_yujin_memory_operation_columns(
            _DuplicateColumnRaceConnection(column_exists_after_race=False)
        )

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        LocalProjectStore._ensure_yujin_memory_operation_columns(
            _DuplicateColumnRaceConnection(
                column_exists_after_race=True,
                error_message="database is locked",
            )
        )

    with pytest.raises(
        sqlite3.OperationalError,
        match="duplicate column name: external_ref",
    ):
        LocalProjectStore._ensure_yujin_memory_operation_columns(
            _DuplicateColumnRaceConnection(
                column_exists_after_race=True,
                error_message="duplicate column name: external_ref ",
            )
        )
