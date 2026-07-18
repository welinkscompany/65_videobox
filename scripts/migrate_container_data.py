from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import argparse
from pathlib import Path


class MigrationError(ValueError):
    pass


def _hashes(root: Path) -> dict[str, str]:
    result = {}
    for item in sorted(path for path in root.rglob("*") if path.is_file() and path.name != "container-migration-manifest.json"):
        digest = hashlib.sha256()
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result[item.relative_to(root).as_posix()] = digest.hexdigest()
    return result


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


def migrate_container_data(source: Path, target: Path) -> dict:
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise MigrationError("source and target must differ")
    if not source.is_dir() or not (source / "projects").is_dir():
        raise MigrationError("source must contain projects")
    if source in target.parents:
        raise MigrationError("target must not be inside source")
    manifest_path = target / "container-migration-manifest.json"
    if target.exists():
        if not manifest_path.is_file():
            raise MigrationError("target is not a recognized migration")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source") != str(source) or manifest.get("target") != str(target):
            raise MigrationError("target migration identity does not match source")
        if manifest.get("file_hashes") != _hashes(target):
            raise MigrationError("target content does not match its verified snapshot")
        return manifest
    staging = target.with_name(target.name + ".staging")
    if staging.exists():
        raise MigrationError("staging path already exists")
    _copy_source_to_staging(source, staging)
    if not any((project / "db" / "project.sqlite").is_file() for project in (staging / "projects").iterdir() if project.is_dir()):
        shutil.rmtree(staging)
        raise MigrationError("source has no project sqlite")
    manifest = {
        "source": str(source),
        "target": str(target),
        "source_preserved": True,
        "file_hashes": _hashes(staging),
    }
    (staging / "container-migration-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
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
