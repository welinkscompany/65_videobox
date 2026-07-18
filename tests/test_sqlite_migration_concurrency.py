from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
