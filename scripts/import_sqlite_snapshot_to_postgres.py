from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from videobox_core_engine.container_snapshot import ContainerSnapshotError, verify_container_snapshot

from videobox_storage.postgres_schema import (
    POSTGRES_IMPORT_SCHEMA_STATEMENTS,
    POSTGRES_MIGRATION_STATEMENTS,
    POSTGRES_SCHEMA_STATEMENTS,
)


_TABLE_PATTERN = re.compile(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", re.IGNORECASE)
_PROJECT_TABLES = tuple(
    match.group(1)
    for statement in POSTGRES_SCHEMA_STATEMENTS
    if (match := _TABLE_PATTERN.search(statement)) is not None
)


class SnapshotImportError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_schema(connection) -> None:
    for statement in POSTGRES_SCHEMA_STATEMENTS + POSTGRES_MIGRATION_STATEMENTS + POSTGRES_IMPORT_SCHEMA_STATEMENTS:
        connection.execute(statement)


def _snapshot_sqlite_uri(database_path: Path) -> str:
    return f"{database_path.resolve().as_uri()}?mode=ro&immutable=1"


def _copy_project_database(connection, database_path: Path, project_id: str) -> None:
    source = sqlite3.connect(_snapshot_sqlite_uri(database_path), uri=True)
    try:
        for table in _PROJECT_TABLES:
            columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})").fetchall()]
            if not columns:
                continue
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            quoted_columns = ", ".join(columns)
            placeholders = ", ".join("%s" for _ in columns)
            with connection.cursor() as cursor:
                cursor.executemany(
                    f"INSERT INTO {table} ({quoted_columns}) VALUES ({placeholders})",
                    rows,
                )
    finally:
        source.close()


def import_sqlite_snapshot(*, source_root: Path, database_url: str) -> dict[str, list[str]]:
    source_root = Path(source_root).resolve()
    try:
        verify_container_snapshot(source_root)
    except ContainerSnapshotError as error:
        raise SnapshotImportError(str(error)) from error
    projects_root = source_root / "projects"
    if not projects_root.is_dir():
        raise SnapshotImportError("source root must contain projects")

    imported: list[str] = []
    already_imported: list[str] = []
    try:
        with psycopg.connect(database_url) as connection:
            _ensure_schema(connection)
            for project_root in sorted(path for path in projects_root.iterdir() if path.is_dir()):
                database_path = project_root / "db" / "project.sqlite"
                if not database_path.is_file():
                    continue
                project_id = project_root.name
                source_sha256 = _sha256(database_path)
                existing = connection.execute(
                    "SELECT source_sha256 FROM videobox_snapshot_imports WHERE project_id = %s",
                    (project_id,),
                ).fetchone()
                if existing is not None:
                    if existing[0] != source_sha256:
                        raise SnapshotImportError(f"snapshot hash changed for imported project: {project_id}")
                    already_imported.append(project_id)
                    continue
                _copy_project_database(connection, database_path, project_id)
                connection.execute(
                    "INSERT INTO videobox_snapshot_imports (project_id, source_sha256, imported_at) VALUES (%s, %s, %s)",
                    (project_id, source_sha256, datetime.now(UTC).isoformat()),
                )
                imported.append(project_id)
            connection.commit()
    except psycopg.errors.UniqueViolation as error:
        raise SnapshotImportError("snapshot row conflict during import") from error
    return {"imported_project_ids": imported, "already_imported_project_ids": already_imported}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a read-only VideoBox SQLite snapshot into PostgreSQL.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    print(import_sqlite_snapshot(source_root=args.source, database_url=args.database_url))


if __name__ == "__main__":
    main()
