from __future__ import annotations

import os
import importlib.util
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.postgres_project_store import PostgresProjectStore


_SPEC = importlib.util.spec_from_file_location(
    "import_sqlite_snapshot_to_postgres",
    Path(__file__).parents[1] / "scripts" / "import_sqlite_snapshot_to_postgres.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
import_sqlite_snapshot = _MODULE.import_sqlite_snapshot
SnapshotImportError = _MODULE.SnapshotImportError


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("VIDEOBOX_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set VIDEOBOX_TEST_POSTGRES_URL to run PostgreSQL snapshot import tests")
    return value


def test_snapshot_import_preserves_sqlite_source_and_is_idempotent(
    tmp_path: Path, postgres_url: str
) -> None:
    source = tmp_path / "snapshot"
    source_store = LocalProjectStore(source)
    project = source_store.bootstrap_project(f"Imported project {uuid4().hex}")
    database_path = source_store.database_path(project.project_id)
    source_before = database_path.read_bytes()

    first = import_sqlite_snapshot(source_root=source, database_url=postgres_url)
    second = import_sqlite_snapshot(source_root=source, database_url=postgres_url)

    assert source_before == database_path.read_bytes()
    assert first["imported_project_ids"] == [project.project_id]
    assert second["already_imported_project_ids"] == [project.project_id]
    assert any(item["project_id"] == project.project_id for item in PostgresProjectStore(source, database_url=postgres_url).list_projects())


def test_snapshot_import_rejects_a_changed_source_after_initial_import(
    tmp_path: Path, postgres_url: str
) -> None:
    source = tmp_path / "snapshot"
    source_store = LocalProjectStore(source)
    project = source_store.bootstrap_project(f"Changed snapshot {uuid4().hex}")
    database_path = source_store.database_path(project.project_id)
    import_sqlite_snapshot(source_root=source, database_url=postgres_url)

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE projects SET name = ?", ("changed after import",))

    with pytest.raises(SnapshotImportError, match="snapshot hash changed"):
        import_sqlite_snapshot(source_root=source, database_url=postgres_url)
