"""Compatibility wrapper for the shared starter-pack release contract.

The install service owns the policy.  This script-facing module only parses a
manifest and adds directory-integrity validation for build/release tooling.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
):
    sys.path.insert(0, str(source_path))

from videobox_core_engine.media_pack_release import (  # noqa: E402
    ReleasePackValidationError,
    ffprobe_media,
    validate_release_contract,
)
from videobox_core_engine.media_pack_service import compute_pack_integrity  # noqa: E402
from videobox_domain_models.media_pack import MediaPackManifest  # noqa: E402


MediaProbe = Callable[[Path], Mapping[str, object]]
IntegrityCalculator = Callable[[Path], tuple[int, str]]


def verify_release_pack(
    root: Path,
    *,
    media_probe: MediaProbe,
    integrity_calculator: IntegrityCalculator = compute_pack_integrity,
) -> MediaPackManifest:
    root = Path(root).resolve()
    try:
        manifest = MediaPackManifest.from_dict(
            json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ReleasePackValidationError(f"invalid manifest: {error}") from error
    validate_release_contract(manifest=manifest, root=root, media_probe=media_probe)
    for asset in manifest.assets:
        path = root / asset.pack_path
        if _sha256_file(path) != asset.sha256:
            raise ReleasePackValidationError(f"asset checksum mismatch: {asset.asset_id}")
    actual_bytes, actual_digest = integrity_calculator(root)
    if actual_bytes != manifest.declared_bytes or actual_digest != manifest.sha256:
        raise ReleasePackValidationError("pack integrity does not match manifest")
    return manifest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
