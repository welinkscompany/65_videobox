from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from videobox_domain_models.media_pack import MediaPackManifest
from videobox_storage.media_library_store import MediaLibraryStore


@dataclass(frozen=True, slots=True)
class MediaPackInstallResult:
    status: str
    pack_id: str | None = None
    version: str | None = None
    error_code: str | None = None
    message: str | None = None


class MediaPackValidationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def compute_pack_integrity(directory: Path) -> tuple[int, str]:
    """Return (bytes, digest) for a directory pack, excluding manifest.json.

    The digest is SHA-256 over sorted POSIX relative paths followed by NUL and
    each file's raw bytes. This is deterministic across directory installs and
    avoids the manifest self-reference problem.
    """
    root = Path(directory)
    digest = hashlib.sha256()
    total = 0
    files = sorted(
        ((path.relative_to(root).as_posix(), path) for path in root.rglob("*") if path.is_file() and path.relative_to(root).as_posix() != "manifest.json"),
        key=lambda item: item[0],
    )
    for relative_path, path in files:
        digest.update(relative_path.encode("utf-8") + b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                total += len(chunk)
                digest.update(chunk)
    return total, digest.hexdigest()


class MediaPackService:
    def __init__(
        self, *, user_library_root: Path, library_store: MediaLibraryStore,
        duration_probe: Callable[[Path], float],
    ) -> None:
        self.user_library_root = Path(user_library_root)
        self.library_store = library_store
        self.duration_probe = duration_probe

    def install(
        self, source_directory: Path, *, before_activation: Callable[[Path], None] | None = None,
    ) -> MediaPackInstallResult:
        source_directory = Path(source_directory)
        try:
            manifest = MediaPackManifest.from_dict(json.loads((source_directory / "manifest.json").read_text(encoding="utf-8")))
        except Exception as error:
            return MediaPackInstallResult(status="failed", error_code="invalid_manifest", message=str(error))
        version_root = self.user_library_root / "packs" / manifest.pack_id
        destination = version_root / manifest.version
        staging = version_root / f"{manifest.version}.staging"
        if destination.is_dir():
            try:
                is_healthy = self.library_store.is_active_verified_pack(
                    pack_id=manifest.pack_id, version=manifest.version, install_path=destination
                )
            except Exception as error:
                return MediaPackInstallResult(status="failed", pack_id=manifest.pack_id, version=manifest.version, error_code="install_failed", message=str(error))
            if is_healthy:
                return MediaPackInstallResult(status="already_installed", pack_id=manifest.pack_id, version=manifest.version)
        if destination.exists():
            return MediaPackInstallResult(status="failed", pack_id=manifest.pack_id, version=manifest.version, error_code="destination_collision", message="Destination version already exists but is not a healthy active install.")
        if staging.exists():
            shutil.rmtree(staging)
        created_destination = False
        try:
            version_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_directory, staging)
            declared_bytes, digest = compute_pack_integrity(staging)
            if declared_bytes != manifest.declared_bytes or digest != manifest.sha256:
                raise MediaPackValidationError("pack_integrity_mismatch", "Pack content size or SHA-256 does not match manifest.")
            indexed_assets = self._validate_assets(manifest, staging)
            if self.library_store.get_pack(pack_id=manifest.pack_id, version=manifest.version) is not None:
                raise MediaPackValidationError("indexed_pack_collision", "A pack index already exists for this version without its destination directory.")
            for asset in indexed_assets:
                asset["path"] = destination / Path(str(asset["path"])).relative_to(staging)
            # This indexes verified assets while inactive.  They cannot be found until the
            # directory rename succeeds and the activation transaction completes.
            self.library_store.index_verified_pack(
                pack_id=manifest.pack_id, version=manifest.version, install_path=destination,
                assets=indexed_assets, active=False,
            )
            if before_activation is not None:
                before_activation(staging)
            staging.replace(destination)
            created_destination = True
            self.library_store.activate_pack(pack_id=manifest.pack_id, version=manifest.version, install_path=destination)
            return MediaPackInstallResult(status="installed", pack_id=manifest.pack_id, version=manifest.version)
        except MediaPackValidationError as error:
            self._cleanup_failed_attempt(staging=staging, destination=destination, created_destination=created_destination, pack_id=manifest.pack_id, version=manifest.version)
            return MediaPackInstallResult(status="failed", pack_id=manifest.pack_id, version=manifest.version, error_code=error.error_code, message=str(error))
        except Exception as error:
            self._cleanup_failed_attempt(staging=staging, destination=destination, created_destination=created_destination, pack_id=manifest.pack_id, version=manifest.version)
            return MediaPackInstallResult(status="failed", pack_id=manifest.pack_id, version=manifest.version, error_code="install_failed", message=str(error))

    def _validate_assets(self, manifest: MediaPackManifest, staging: Path) -> list[dict[str, object]]:
        indexed: list[dict[str, object]] = []
        for asset in manifest.assets:
            path = staging / Path(asset.pack_path)
            try:
                path.resolve().relative_to(staging.resolve())
            except ValueError as error:
                raise MediaPackValidationError("asset_missing", f"unsafe asset file path: {asset.asset_id}") from error
            if not path.is_file():
                raise MediaPackValidationError("asset_missing", f"missing or ambiguous asset file: {asset.asset_id}")
            digest = _sha256_file(path)
            if digest != asset.sha256:
                raise MediaPackValidationError("checksum_mismatch", f"checksum mismatch: {asset.asset_id}")
            duration = float(self.duration_probe(path))
            if not math.isfinite(duration) or duration <= 0 or abs(duration - asset.duration_seconds) > 0.05:
                raise MediaPackValidationError("duration_mismatch", f"duration mismatch: {asset.asset_id}")
            indexed.append({
                "library_asset_id": asset.library_asset_id, "asset_id": asset.asset_id,
                "media_type": asset.media_type, "duration_seconds": asset.duration_seconds,
                "sha256": asset.sha256, "path": path, "source": asset.source,
                "creator": asset.creator, "license": {
                    "official_url": asset.license.official_url,
                    "evidence_timestamp": asset.license.evidence_timestamp.isoformat(),
                    "evidence_sha256": asset.license.evidence_sha256,
                    "attribution_required": asset.license.attribution_required,
                    "attribution_text": asset.license.attribution_text,
                },
                "tags": list(asset.tags),
            })
        return indexed

    def _cleanup_failed_attempt(self, *, staging: Path, destination: Path, created_destination: bool, pack_id: str, version: str) -> None:
        try:
            if staging.exists():
                shutil.rmtree(staging)
            if created_destination and destination.exists():
                shutil.rmtree(destination)
        finally:
            try:
                self.library_store.remove_pack(pack_id=pack_id, version=version)
            except Exception:
                pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
