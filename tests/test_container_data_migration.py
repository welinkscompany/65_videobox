import importlib.util
import hashlib
import json
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


def _legacy_file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "container-migration-manifest.json"
    }


def _legacy_target(source: Path, target: Path) -> None:
    import shutil

    shutil.copytree(source, target)
    manifest = {
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "source_preserved": True,
        "file_hashes": _legacy_file_hashes(target),
    }
    (target / "container-migration-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_migration_copies_projects_preserves_source_and_is_idempotent(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "target"

    first = module.migrate_container_data(source, target)
    second = module.migrate_container_data(source, target)

    assert (target / "snapshot" / "projects" / "demo" / "db" / "project.sqlite").is_file()
    assert (target / "snapshot" / "container-migration-manifest.json").is_file()
    assert (target / "runtime" / "projects" / "demo" / "db" / "project.sqlite").is_file()
    assert (source / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert first["source_preserved"] is True
    assert second["file_hashes"] == first["file_hashes"]


def test_migration_does_not_treat_writable_runtime_changes_as_snapshot_changes(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "target"

    module.migrate_container_data(source, target)
    (target / "runtime" / "projects" / "demo" / "asset.bin").write_bytes(b"runtime-change")

    verified = module.migrate_container_data(source, target)

    assert verified["snapshot_root"] == "snapshot"
    assert (target / "snapshot" / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"


def test_migration_upgrades_verified_legacy_flat_target_without_touching_source(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "legacy-target"
    _legacy_target(source, target)
    source_database_before = (source / "projects" / "demo" / "db" / "project.sqlite").read_bytes()

    first = module.migrate_container_data(source, target)
    second = module.migrate_container_data(source, target)

    assert first["layout_version"] == 1
    assert second["file_hashes"] == first["file_hashes"]
    assert (target / "snapshot" / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert (target / "runtime" / "projects" / "demo" / "db" / "project.sqlite").is_file()
    assert not (target / "projects").exists()
    assert source_database_before == (source / "projects" / "demo" / "db" / "project.sqlite").read_bytes()


def test_migration_resumes_after_legacy_target_was_moved_to_backup(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "legacy-target"
    _legacy_target(source, target)
    backup = target.with_name(target.name + ".legacy-backup")
    target.rename(backup)

    result = module.migrate_container_data(source, target)

    assert result["layout_version"] == 1
    assert (target / "snapshot" / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert not backup.exists()
    assert (source / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"


def test_migration_resumes_completed_staging_after_target_backup_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "legacy-target"
    _legacy_target(source, target)
    staging = target.with_name(target.name + ".staging")
    original_rename = Path.rename

    def crash_before_publish(self: Path, destination: Path):
        if self == staging and destination == target:
            raise OSError("simulated publish crash")
        return original_rename(self, destination)

    monkeypatch.setattr(Path, "rename", crash_before_publish)
    with pytest.raises(OSError, match="simulated publish crash"):
        module.migrate_container_data(source, target)
    monkeypatch.setattr(Path, "rename", original_rename)

    result = module.migrate_container_data(source, target)

    assert result["layout_version"] == 1
    assert (target / "snapshot" / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert not target.with_name(target.name + ".legacy-backup").exists()
    assert not staging.exists()


def test_migration_removes_backup_only_after_completed_target_is_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "legacy-target"
    _legacy_target(source, target)
    backup = target.with_name(target.name + ".legacy-backup")
    original_rmtree = module.shutil.rmtree

    def crash_before_backup_cleanup(path: Path, *args, **kwargs):
        if Path(path) == backup:
            raise OSError("simulated cleanup crash")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(module.shutil, "rmtree", crash_before_backup_cleanup)
    with pytest.raises(OSError, match="simulated cleanup crash"):
        module.migrate_container_data(source, target)
    monkeypatch.setattr(module.shutil, "rmtree", original_rmtree)

    assert (target / "snapshot" / "container-migration-manifest.json").is_file()
    assert backup.is_dir()
    module.migrate_container_data(source, target)

    assert not backup.exists()
    assert (target / "snapshot" / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"


def test_migration_retains_backup_when_published_snapshot_cannot_be_verified(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "target"
    module.migrate_container_data(source, target)
    backup = target.with_name(target.name + ".legacy-backup")
    _legacy_target(source, backup)
    (target / "snapshot" / "projects" / "demo" / "asset.bin").write_bytes(b"corrupt")

    with pytest.raises(module.MigrationError, match="snapshot hash"):
        module.migrate_container_data(source, target)

    assert backup.is_dir()
    assert (backup / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"


def test_migration_refuses_incomplete_staging_without_destroying_legacy_copy(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")
    target = tmp_path / "legacy-target"
    _legacy_target(source, target)
    staging = target.with_name(target.name + ".staging")
    staging.mkdir()
    (staging / "incomplete").write_text("do not discard", encoding="utf-8")

    with pytest.raises(module.MigrationError, match="incomplete or unrecognized"):
        module.migrate_container_data(source, target)

    assert (target / "projects" / "demo" / "asset.bin").read_bytes() == b"source-bytes"
    assert (staging / "incomplete").read_text(encoding="utf-8") == "do not discard"


def test_migration_rejects_source_equal_target(tmp_path: Path) -> None:
    module = _migration_module()
    source = _source(tmp_path / "source")

    with pytest.raises(module.MigrationError, match="source and target"):
        module.migrate_container_data(source, source)
