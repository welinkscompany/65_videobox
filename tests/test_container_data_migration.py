import importlib.util
import sqlite3
from pathlib import Path

import pytest


def _migration_module():
    path = Path(__file__).parents[1] / "scripts" / "migrate_container_data.py"
    spec = importlib.util.spec_from_file_location("container_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _source(root: Path) -> Path:
    (root / "projects" / "demo" / "db").mkdir(parents=True)
    database_path = root / "projects" / "demo" / "db" / "project.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE fixture (value TEXT NOT NULL)")
        connection.execute("INSERT INTO fixture (value) VALUES ('source')")
    (root / "projects" / "demo" / "asset.bin").write_bytes(b"source-bytes")
    return root


def test_migration_copies_projects_preserves_source_and_is_idempotent(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "target"

    first = module.migrate_container_data(source, target)
    second = module.migrate_container_data(source, target)

    assert (target / "projects" / "demo" / "db" / "project.sqlite").is_file()
    assert (target / "container-migration-manifest.json").is_file()
    assert (source / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert first["source_preserved"] is True
    assert second["file_hashes"] == first["file_hashes"]


def test_migration_rejects_source_equal_target(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")

    with pytest.raises(module.MigrationError, match="source and target"):
        module.migrate_container_data(source, source)
