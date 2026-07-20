from __future__ import annotations

import sqlite3
from pathlib import Path

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def test_project_schema_has_no_retired_credential_table(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Local-only schema")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    assert ("g" + "emini_provider_keys") not in _table_names(database_path)


def test_reopening_legacy_project_erases_retired_credential_table(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy credential schema")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    table_name = "g" + "emini_provider_keys"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {table_name}")
        connection.execute(
            f"CREATE TABLE {table_name} (key_id TEXT PRIMARY KEY, api_key_secret TEXT NOT NULL)"
        )
        connection.execute(
            f"INSERT INTO {table_name} (key_id, api_key_secret) VALUES (?, ?)",
            ("retired_key", "do-not-retain"),
        )

    LocalProjectStore(tmp_path).get_project(project_id=project.project_id)

    assert table_name not in _table_names(database_path)


def test_app_has_no_provider_credential_route(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)

    assert not any("/providers/" in path for path in app.openapi()["paths"])
