from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any, Callable, Sequence

import psycopg

from videobox_domain_models.projects import ProjectRecord
from videobox_storage.local_project_store import LocalProjectStore, sha256_file
from videobox_storage.postgres_compat import translate_sql
from videobox_storage.postgres_schema import (
    POSTGRES_IMPORT_SCHEMA_STATEMENTS,
    POSTGRES_MIGRATION_STATEMENTS,
    POSTGRES_SCHEMA_STATEMENTS,
)


class _CompatRow(dict[str, Any]):
    """A mapping that also preserves sqlite3.Row's integer indexing contract."""

    def __init__(self, names: Sequence[str], values: Sequence[Any]) -> None:
        super().__init__(zip(names, values, strict=True))
        self._values = tuple(values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def _row(self, value: tuple[Any, ...] | None) -> _CompatRow | None:
        if value is None:
            return None
        names = [column.name for column in self._cursor.description or ()]
        return _CompatRow(names, value)

    def fetchone(self) -> _CompatRow | None:
        return self._row(self._cursor.fetchone())

    def fetchall(self) -> list[_CompatRow]:
        return [self._row(value) for value in self._cursor.fetchall() if value is not None]


class _PostgresConnection:
    """Narrow sqlite3.Connection compatibility surface for LocalProjectStore."""

    def __init__(self, database_url: str) -> None:
        self._connection = psycopg.connect(database_url)
        self.row_factory = None

    @property
    def in_transaction(self) -> bool:
        return self._connection.info.transaction_status.name != "IDLE"

    def execute(self, statement: str, parameters: Sequence[Any] | None = None) -> _PostgresCursor:
        translated = translate_sql(statement)
        if translated == "BEGIN":
            return _PostgresCursor(self._connection.cursor())
        cursor = self._connection.cursor()
        try:
            cursor.execute(translated, parameters or ())
        except psycopg.errors.UniqueViolation as error:
            # LocalProjectStore's durable idempotency branches deliberately
            # handle SQLite's integrity contract.  Preserve that narrow
            # contract at this adapter boundary without treating unrelated
            # PostgreSQL errors as idempotent duplicate requests.
            raise sqlite3.IntegrityError(str(error)) from error
        return _PostgresCursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "_PostgresConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is not None:
            self.rollback()
        self.close()


class PostgresProjectStore(LocalProjectStore):
    """PostgreSQL-backed operational store retaining the existing asset layout."""

    def __init__(
        self,
        projects_root: Path,
        *,
        database_url: str,
        now: Callable[[], datetime] | None = None,
        atomic_bundle_fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.database_url = database_url
        self._ensure_schema()
        super().__init__(projects_root, now=now, atomic_bundle_fault_hook=atomic_bundle_fault_hook)

    def _ensure_schema(self) -> None:
        connection = _PostgresConnection(self.database_url)
        try:
            for statement in POSTGRES_SCHEMA_STATEMENTS + POSTGRES_MIGRATION_STATEMENTS + POSTGRES_IMPORT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _connection(self, project_id: str) -> _PostgresConnection:
        return _PostgresConnection(self.database_url)

    def _batch_destination_is_registered(self, project_id: str, destination: Path, digest: str) -> bool:
        """Use PostgreSQL, not a copied SQLite snapshot, for crash recovery truth."""
        try:
            root = self.project_root(project_id).resolve()
            resolved = destination.resolve()
            if root not in resolved.parents or not digest or not resolved.is_file() or sha256_file(resolved) != digest:
                return False
            uri = self._path_to_uri(project_id, resolved)
            connection = self._connection(project_id)
            try:
                row = connection.execute(
                    "SELECT asset_id FROM assets WHERE project_id = ? AND storage_uri = ?",
                    (project_id, uri),
                ).fetchone()
                return row is not None
            finally:
                connection.close()
        except (OSError, ValueError, psycopg.Error):
            return False

    def _bootstrap_database(self, database_path: Path, project: ProjectRecord) -> None:
        connection = self._connection(project.project_id)
        try:
            connection.execute(
                """
                INSERT INTO projects (project_id, name, status, root_storage_uri, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (project_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    root_storage_uri = EXCLUDED.root_storage_uri,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    project.project_id,
                    project.name,
                    project.status.value,
                    project.root_storage_uri,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def list_projects(self) -> list[dict[str, Any]]:
        connection = self._connection("")
        try:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT project_id, name, status, root_storage_uri, created_at, updated_at FROM projects ORDER BY project_id"
                ).fetchall()
            ]
        finally:
            connection.close()
