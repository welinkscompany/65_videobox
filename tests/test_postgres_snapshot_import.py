from __future__ import annotations

import os
import importlib.util
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg

from videobox_core_engine.container_snapshot import MANIFEST_FILENAME, snapshot_file_hashes
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


def _write_verified_manifest(snapshot_root: Path) -> None:
    manifest = {
        "layout_version": 1,
        "source": "test-source",
        "target": "test-target",
        "snapshot_root": "snapshot",
        "runtime_root": "runtime",
        "source_preserved": True,
        "file_hashes": snapshot_file_hashes(snapshot_root),
    }
    (snapshot_root / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")


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
    _write_verified_manifest(source)

    source_uri = _MODULE._snapshot_sqlite_uri(database_path)
    assert "mode=ro&immutable=1" in source_uri

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
    _write_verified_manifest(source)
    import_sqlite_snapshot(source_root=source, database_url=postgres_url)

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE projects SET name = ?", ("changed after import",))

    with pytest.raises(SnapshotImportError, match="snapshot hash mismatch"):
        import_sqlite_snapshot(source_root=source, database_url=postgres_url)


def test_snapshot_import_rejects_source_without_verified_manifest(tmp_path: Path, postgres_url: str) -> None:
    source = tmp_path / "snapshot"
    LocalProjectStore(source).bootstrap_project(f"Unverified snapshot {uuid4().hex}")

    with pytest.raises(SnapshotImportError, match="verified container snapshot manifest"):
        import_sqlite_snapshot(source_root=source, database_url=postgres_url)


def test_snapshot_import_rejects_existing_rows_without_an_import_marker(
    tmp_path: Path, postgres_url: str
) -> None:
    source = tmp_path / "snapshot"
    store = LocalProjectStore(source)
    project = store.bootstrap_project(f"Conflicting snapshot {uuid4().hex}")
    _write_verified_manifest(source)
    import_sqlite_snapshot(source_root=source, database_url=postgres_url)
    with psycopg.connect(postgres_url) as connection:
        connection.execute("DELETE FROM videobox_snapshot_imports WHERE project_id = %s", (project.project_id,))
        connection.commit()

    with pytest.raises(SnapshotImportError, match="snapshot row conflict"):
        import_sqlite_snapshot(source_root=source, database_url=postgres_url)
