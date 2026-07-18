from __future__ import annotations

import json
import shutil
import sqlite3
import argparse
from pathlib import Path

from videobox_core_engine.container_snapshot import (
    MANIFEST_FILENAME,
    ContainerSnapshotError,
    snapshot_file_hashes,
    verify_container_snapshot,
)


class MigrationError(ValueError):
    pass


def _copy_sqlite_snapshot(source: Path, target: Path) -> None:
    """Copy a consistent, read-only SQLite snapshot without touching source files."""
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def _copy_source_to_staging(source: Path, staging: Path) -> None:
    sqlite_paths = [
        path.relative_to(source)
        for path in source.rglob("project.sqlite")
        if path.parent.name == "db"
    ]
    sqlite_path_set = {path.as_posix() for path in sqlite_paths}
    shutil.copytree(
        source,
        staging,
        ignore=lambda directory, names: [
            name
            for name in names
            if (Path(directory).relative_to(source) / name).as_posix() in sqlite_path_set
        ],
    )
    for relative_path in sqlite_paths:
        target = staging / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_sqlite_snapshot(source / relative_path, target)


def _verified_legacy_manifest(
    source: Path, target: Path, *, declared_target: Path | None = None
) -> dict | None:
    """Return a verified pre-snapshot-layout manifest, if ``target`` has one."""
    manifest_path = target / MANIFEST_FILENAME
    if not manifest_path.is_file() or (target / "snapshot").exists() or (target / "runtime").exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MigrationError("target legacy manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise MigrationError("target legacy manifest is invalid")
    expected_target = declared_target or target
    if manifest.get("source") != str(source) or manifest.get("target") != str(expected_target):
        raise MigrationError("target migration identity does not match source")
    if manifest.get("source_preserved") is not True:
        raise MigrationError("target legacy manifest does not prove source preservation")
    expected = manifest.get("file_hashes")
    if not isinstance(expected, dict) or expected != snapshot_file_hashes(target):
        raise MigrationError("target legacy content does not match its verified snapshot")
    return manifest


def _verified_completed_target(
    source: Path, target: Path, *, declared_target: Path | None = None
) -> dict | None:
    """Return a verified snapshot/runtime layout, or ``None`` when it is absent."""
    snapshot_root = target / "snapshot"
    runtime_root = target / "runtime"
    manifest_path = snapshot_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = verify_container_snapshot(snapshot_root)
    except ContainerSnapshotError as error:
        raise MigrationError(str(error)) from error
    expected_target = declared_target or target
    if manifest.get("source") != str(source) or manifest.get("target") != str(expected_target):
        raise MigrationError("target migration identity does not match source")
    if not runtime_root.is_dir():
        raise MigrationError("target runtime data directory is missing")
    return manifest


def _remove_verified_legacy_backup(source: Path, target: Path, backup: Path) -> None:
    """Delete a legacy backup only after the published target has verified completely."""
    if _verified_completed_target(source, target) is None:
        raise MigrationError("cannot remove legacy backup before target verification")
    if _verified_legacy_manifest(source, backup, declared_target=target) is None:
        raise MigrationError("legacy backup is incomplete or unrecognized")
    shutil.rmtree(backup)


def _publish_legacy_upgrade(source: Path, target: Path, staging: Path, backup: Path) -> dict:
    """Publish a complete staging layout, retaining the old copy until verification passes."""
    target.rename(backup)
    try:
        staging.rename(target)
    except Exception:
        backup.rename(target)
        raise
    manifest = _verified_completed_target(source, target)
    if manifest is None:
        raise MigrationError("published legacy upgrade is incomplete or unrecognized")
    _remove_verified_legacy_backup(source, target, backup)
    return manifest


def _recover_interrupted_legacy_upgrade(source: Path, target: Path) -> dict | None:
    """Resume only proven legacy-upgrade states; preserve every unknown recovery artifact."""
    staging = target.with_name(target.name + ".staging")
    backup = target.with_name(target.name + ".legacy-backup")
    if not staging.exists() and not backup.exists():
        return None

    if not target.exists():
        if backup.exists() and not staging.exists():
            if _verified_legacy_manifest(source, backup, declared_target=target) is None:
                raise MigrationError("legacy backup is incomplete or unrecognized")
            backup.rename(target)
            return None
        if backup.exists() and staging.exists():
            if _verified_legacy_manifest(source, backup, declared_target=target) is None:
                raise MigrationError("legacy backup is incomplete or unrecognized")
            if _verified_completed_target(source, staging, declared_target=target) is None:
                raise MigrationError("legacy upgrade staging is incomplete or unrecognized")
            staging.rename(target)
            manifest = _verified_completed_target(source, target)
            if manifest is None:
                raise MigrationError("published legacy upgrade is incomplete or unrecognized")
            _remove_verified_legacy_backup(source, target, backup)
            return manifest
        raise MigrationError("legacy upgrade recovery state is incomplete or unrecognized")

    completed = _verified_completed_target(source, target)
    if completed is not None:
        if staging.exists():
            raise MigrationError("legacy upgrade staging is incomplete or unrecognized")
        if backup.exists():
            _remove_verified_legacy_backup(source, target, backup)
        return completed

    if _verified_legacy_manifest(source, target) is None:
        raise MigrationError("target is not a recognized migration")
    if not staging.exists() or backup.exists():
        raise MigrationError("legacy upgrade staging is incomplete or unrecognized")
    if _verified_completed_target(source, staging, declared_target=target) is None:
        raise MigrationError("legacy upgrade staging is incomplete or unrecognized")
    return _publish_legacy_upgrade(source, target, staging, backup)


def _upgrade_legacy_target(source: Path, target: Path) -> dict | None:
    """Atomically convert a verified legacy flat copy into snapshot/runtime layout."""
    if _verified_legacy_manifest(source, target) is None:
        return None
    staging = target.with_name(target.name + ".staging")
    backup = target.with_name(target.name + ".legacy-backup")
    if staging.exists() or backup.exists():
        raise MigrationError("legacy upgrade staging is incomplete or unrecognized")
    snapshot_staging = staging / "snapshot"
    runtime_staging = staging / "runtime"
    shutil.copytree(target, snapshot_staging, ignore=shutil.ignore_patterns(MANIFEST_FILENAME))
    manifest = {
        "layout_version": 1,
        "source": str(source),
        "target": str(target),
        "snapshot_root": "snapshot",
        "runtime_root": "runtime",
        "source_preserved": True,
        "file_hashes": snapshot_file_hashes(snapshot_staging),
    }
    (snapshot_staging / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copytree(snapshot_staging, runtime_staging, ignore=shutil.ignore_patterns(MANIFEST_FILENAME))
    return _publish_legacy_upgrade(source, target, staging, backup)


def migrate_container_data(source: Path, target: Path) -> dict:
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise MigrationError("source and target must differ")
    if not source.is_dir() or not (source / "projects").is_dir():
        raise MigrationError("source must contain projects")
    if source in target.parents:
        raise MigrationError("target must not be inside source")
    recovered = _recover_interrupted_legacy_upgrade(source, target)
    if recovered is not None:
        return recovered
    snapshot_root = target / "snapshot"
    runtime_root = target / "runtime"
    manifest_path = snapshot_root / MANIFEST_FILENAME
    if target.exists():
        upgraded = _upgrade_legacy_target(source, target)
        if upgraded is not None:
            return upgraded
        if not manifest_path.is_file():
            raise MigrationError("target is not a recognized migration")
        manifest = _verified_completed_target(source, target)
        if manifest is None:
            raise MigrationError("target is not a recognized migration")
        return manifest
    staging = target.with_name(target.name + ".staging")
    if staging.exists():
        raise MigrationError("staging path already exists")
    snapshot_staging = staging / "snapshot"
    runtime_staging = staging / "runtime"
    _copy_source_to_staging(source, snapshot_staging)
    if not any((project / "db" / "project.sqlite").is_file() for project in (snapshot_staging / "projects").iterdir() if project.is_dir()):
        shutil.rmtree(staging)
        raise MigrationError("source has no project sqlite")
    manifest = {
        "layout_version": 1,
        "source": str(source),
        "target": str(target),
        "snapshot_root": "snapshot",
        "runtime_root": "runtime",
        "source_preserved": True,
        "file_hashes": snapshot_file_hashes(snapshot_staging),
    }
    (snapshot_staging / MANIFEST_FILENAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copytree(snapshot_staging, runtime_staging, ignore=shutil.ignore_patterns(MANIFEST_FILENAME))
    staging.rename(target)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy a verified, non-destructive VideoBox data snapshot.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate_container_data(args.source, args.target), indent=2))


if __name__ == "__main__":
    main()
