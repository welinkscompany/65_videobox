"""Copy-only, content-addressed ingest for the personal media library.

The source is never moved or deleted by this module.  A staged copy is fully
written, fsynced and hashed before an atomic rename makes it visible.  The
SQLite ingest item is the durable idempotency fence used to reconcile a
browser response that was lost after the server committed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import mimetypes
import os
from pathlib import Path
import shutil
from typing import Any, BinaryIO, Callable, Iterable, Mapping
from uuid import uuid4

from videobox_domain_models.library_assets import LibraryAssetLifecycle, LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_filename(filename: str, source: object) -> str:
    value = str(filename or getattr(source, "name", "") or "asset")
    name = Path(value).name
    if not name or name in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("ingest_filename_invalid")
    return name


@dataclass(slots=True, frozen=True)
class LibraryIngestService:
    store: LibraryUserAssetStore
    managed_root: Path
    enqueue: Callable[[str], None] | None = None

    def ingest(
        self,
        *,
        media_type: LibraryMediaType | str,
        source: Path | str | BinaryIO,
        filename: str | None = None,
        idempotency_key: str,
        provenance: Mapping[str, Any] | None = None,
        batch_idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Copy one source and return a stable ingest response.

        A retry with the same item idempotency key returns the committed item;
        a retry after a process interruption resumes an item that is still
        ``processing`` and never creates a second asset row.
        """
        resolved_type = LibraryMediaType(media_type)
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        name = _safe_filename(filename or "", source)
        batch = self.store.create_ingest_batch(
            idempotency_key=batch_idempotency_key or f"batch:{idempotency_key}",
            provenance=provenance,
        )
        existing_item = self.store.get_ingest_item(idempotency_key)
        if existing_item and existing_item.get("library_asset_id"):
            asset = self.store.get_asset(str(existing_item["library_asset_id"]))
            if asset is not None:
                return self._response(asset, existing_item, duplicate=True)
        item = existing_item or self.store.record_ingest_item(
            batch_id=str(batch["ingest_batch_id"]),
            idempotency_key=idempotency_key,
            library_asset_id=None,
            filename=name,
            state=LibraryAssetLifecycle.PROCESSING.value,
        )
        staging: Path | None = None
        destination: Path | None = None
        created_destination = False
        try:
            staging = self._stage(source, name)
            content_sha256, byte_count = _hash_file(staging)
            existing_asset = self.store.find_by_content_sha256(content_sha256)
            if existing_asset is not None:
                staging.unlink(missing_ok=True)
                item = self.store.update_ingest_item(
                    idempotency_key=idempotency_key,
                    library_asset_id=existing_asset.library_asset_id,
                    state=existing_asset.lifecycle.value,
                    error_code=None,
                )
                return self._response(existing_asset, item, duplicate=True)
            relative = self._relative_destination(resolved_type, content_sha256, name)
            destination = self.managed_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing_hash, _ = _hash_file(destination)
                if existing_hash != content_sha256:
                    raise IOError("ingest_destination_hash_mismatch")
                staging.unlink(missing_ok=True)
            else:
                self._atomic_publish(staging, destination)
                created_destination = True
            asset = self.store.register_asset(
                library_asset_id=f"user_{uuid4().hex}",
                media_type=resolved_type,
                origin="user",
                lifecycle=LibraryAssetLifecycle.PROCESSING,
                content_sha256=content_sha256,
                managed_relative_path=relative.as_posix(),
                byte_count=byte_count,
                mime_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                provenance=dict(provenance or {}),
                user_metadata={"filename": name},
            )
            if asset.lifecycle is LibraryAssetLifecycle.PROCESSING:
                asset = self.store.update_lifecycle(asset.library_asset_id, LibraryAssetLifecycle.READY)
            item = self.store.update_ingest_item(
                idempotency_key=idempotency_key,
                library_asset_id=asset.library_asset_id,
                state=LibraryAssetLifecycle.READY.value,
                error_code=None,
            )
            if self.enqueue is not None:
                try:
                    self.enqueue(asset.library_asset_id)
                except Exception:
                    # Bytes and identity are durable; analysis can be retried.
                    asset = self.store.update_lifecycle(asset.library_asset_id, LibraryAssetLifecycle.NEEDS_ATTENTION)
                    item = self.store.update_ingest_item(
                        idempotency_key=idempotency_key,
                        state=LibraryAssetLifecycle.NEEDS_ATTENTION.value,
                        error_code="derivative_enqueue_failed",
                    )
            return self._response(asset, item, duplicate=False)
        except Exception as error:
            if staging is not None:
                staging.unlink(missing_ok=True)
            if created_destination and destination is not None:
                destination.unlink(missing_ok=True)
            try:
                item = self.store.update_ingest_item(
                    idempotency_key=idempotency_key,
                    state=LibraryAssetLifecycle.NEEDS_ATTENTION.value,
                    error_code=type(error).__name__,
                )
            except Exception:
                pass
            raise

    def ingest_batch(
        self,
        *,
        media_type: LibraryMediaType | str,
        items: Iterable[tuple[Path | str | BinaryIO, str, str]],
        batch_idempotency_key: str,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        succeeded: list[str] = []
        failed: list[dict[str, str]] = []
        for source, filename, idempotency_key in items:
            try:
                self.ingest(
                    media_type=media_type,
                    source=source,
                    filename=filename,
                    idempotency_key=idempotency_key,
                    batch_idempotency_key=batch_idempotency_key,
                    provenance=provenance,
                )
                succeeded.append(filename)
            except Exception as error:
                failed.append({"filename": filename, "error_code": type(error).__name__})
        return {"succeeded": succeeded, "failed": failed, "partial": bool(succeeded and failed)}

    def _stage(self, source: Path | str | BinaryIO, filename: str) -> Path:
        self.managed_root.mkdir(parents=True, exist_ok=True)
        staging_root = self.managed_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{uuid4().hex}-{filename}"
        try:
            with staging.open("wb") as destination:
                if isinstance(source, (str, Path)):
                    with Path(source).open("rb") as origin:
                        shutil.copyfileobj(origin, destination, length=1024 * 1024)
                else:
                    while chunk := source.read(1024 * 1024):  # type: ignore[union-attr]
                        destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            return staging
        except Exception:
            staging.unlink(missing_ok=True)
            raise

    @staticmethod
    def _relative_destination(media_type: LibraryMediaType, digest: str, filename: str) -> Path:
        suffix = Path(filename).suffix.lower() or ".bin"
        return Path("assets") / media_type.value / digest[:2] / f"{digest}{suffix}"

    @staticmethod
    def _atomic_publish(staging: Path, destination: Path) -> None:
        os.replace(staging, destination)
        try:
            flags = os.O_DIRECTORY
        except AttributeError:
            flags = 0
        if flags:
            descriptor = os.open(destination.parent, os.O_RDONLY | flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _response(asset: Any, item: Mapping[str, Any], *, duplicate: bool) -> dict[str, Any]:
        return {
            "library_asset_id": asset.library_asset_id,
            "managed_relative_path": asset.managed_relative_path,
            "content_sha256": asset.content_sha256,
            "media_type": asset.media_type.value,
            "state": asset.lifecycle.value,
            "ingest_item_id": str(item["ingest_item_id"]),
            "idempotency_key": str(item["idempotency_key"]),
            "duplicate": duplicate,
        }


__all__ = ["LibraryIngestService"]
