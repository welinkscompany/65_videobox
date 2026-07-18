from __future__ import annotations

import hashlib
import json
import shutil
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


def migrate_container_data(source: Path, target: Path) -> dict:
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise MigrationError("source and target must differ")
    if not source.is_dir() or not (source / "projects").is_dir():
        raise MigrationError("source must contain projects")
    if source in target.parents:
        raise MigrationError("target must not be inside source")
    manifest_path = target / "container-migration-manifest.json"
    source_hashes = _hashes(source)
    if target.exists():
        if not manifest_path.is_file():
            raise MigrationError("target is not a recognized migration")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["file_hashes"] != source_hashes:
            raise MigrationError("target content does not match source")
        return manifest
    staging = target.with_name(target.name + ".staging")
    if staging.exists():
        raise MigrationError("staging path already exists")
    shutil.copytree(source, staging)
    if not any((project / "db" / "project.sqlite").is_file() for project in (staging / "projects").iterdir() if project.is_dir()):
        shutil.rmtree(staging)
        raise MigrationError("source has no project sqlite")
    manifest = {"source": str(source), "target": str(target), "source_preserved": True, "file_hashes": source_hashes}
    (staging / "container-migration-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    staging.rename(target)
    return manifest
