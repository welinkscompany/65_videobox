from __future__ import annotations

import hashlib
import json
from pathlib import Path


MANIFEST_FILENAME = "container-migration-manifest.json"


class ContainerSnapshotError(ValueError):
    pass


def snapshot_file_hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    manifest_path = root / MANIFEST_FILENAME
    for item in sorted(path for path in root.rglob("*") if path.is_file() and path != manifest_path):
        digest = hashlib.sha256()
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result[item.relative_to(root).as_posix()] = digest.hexdigest()
    return result


def verify_container_snapshot(root: Path) -> dict[str, object]:
    root = Path(root).resolve()
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ContainerSnapshotError("verified container snapshot manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContainerSnapshotError("verified container snapshot manifest is invalid") from error
    if not isinstance(manifest, dict) or manifest.get("layout_version") != 1:
        raise ContainerSnapshotError("verified container snapshot manifest has an unsupported layout")
    if manifest.get("snapshot_root") != "snapshot" or manifest.get("source_preserved") is not True:
        raise ContainerSnapshotError("verified container snapshot manifest does not match its snapshot root")
    expected = manifest.get("file_hashes")
    if not isinstance(expected, dict) or not expected:
        raise ContainerSnapshotError("verified container snapshot manifest has no file hashes")
    actual = snapshot_file_hashes(root)
    if expected != actual:
        raise ContainerSnapshotError("verified container snapshot hash mismatch")
    return manifest
