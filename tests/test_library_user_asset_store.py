from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from videobox_domain_models.library_assets import (
    LibraryAssetLifecycle,
    LibraryAssetOrigin,
    LibraryMediaType,
    LibraryUserAsset,
)
from videobox_storage.library_user_asset_store import LibraryUserAssetStore


def _asset_kwargs(tmp_path: Path, *, digest: str | None = None) -> dict:
    content = b"hello media"
    return {
        "library_asset_id": "user:asset-1",
        "media_type": LibraryMediaType.BROLL,
        "origin": LibraryAssetOrigin.USER,
        "content_sha256": digest or hashlib.sha256(content).hexdigest(),
        "managed_relative_path": "user-assets/broll/asset-1.mp4",
        "byte_count": len(content),
        "mime_type": "video/mp4",
        "technical_metadata": {"duration_seconds": 1.5, "width": 1920},
        "machine_metadata": {"description": "a person walking"},
        "user_metadata": {"title": "출근 장면"},
        "provenance": {"source": "local_upload", "filename": "walk.mp4"},
    }


def test_strict_library_asset_vocabulary_and_metadata_separation(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    asset = store.register_asset(**_asset_kwargs(tmp_path))

    assert isinstance(asset, LibraryUserAsset)
    assert asset.media_type is LibraryMediaType.BROLL
    assert asset.origin is LibraryAssetOrigin.USER
    assert asset.lifecycle is LibraryAssetLifecycle.PROCESSING
    assert asset.machine_metadata == {"description": "a person walking"}
    assert asset.user_metadata == {"title": "출근 장면"}
    assert store.get_asset(asset.library_asset_id) == asset

    with pytest.raises(ValueError, match="media_type"):
        store.register_asset(**{**_asset_kwargs(tmp_path), "library_asset_id": "bad", "media_type": "image"})


def test_content_hash_is_global_idempotency_key(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    first = store.register_asset(**_asset_kwargs(tmp_path))
    second = store.register_asset(**{**_asset_kwargs(tmp_path), "library_asset_id": "user:asset-2", "managed_relative_path": "user-assets/other.mp4"})

    assert second.library_asset_id == first.library_asset_id
    assert len(store.list_assets()) == 1


def test_builtin_and_referenced_assets_are_protected_from_trash_and_delete(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    builtin = store.register_asset(**{**_asset_kwargs(tmp_path), "library_asset_id": "builtin:broll-1", "origin": LibraryAssetOrigin.BUILTIN})
    with pytest.raises(ValueError, match="builtin"):
        store.trash_asset(builtin.library_asset_id)

    user = store.register_asset(**{**_asset_kwargs(tmp_path), "library_asset_id": "user:asset-2", "content_sha256": "a" * 64})
    reference = store.add_project_reference(project_id="project-1", library_asset_id=user.library_asset_id, location={"timeline": "main", "at": 2.0})
    assert reference["project_id"] == "project-1"
    with pytest.raises(ValueError, match="reference"):
        store.trash_asset(user.library_asset_id)
    with pytest.raises(ValueError, match="reference"):
        store.permanently_delete_asset(user.library_asset_id)

    store.remove_project_reference(reference["reference_id"])
    store.trash_asset(user.library_asset_id)
    assert store.get_asset(user.library_asset_id).lifecycle is LibraryAssetLifecycle.TRASHED
    store.restore_asset(user.library_asset_id)
    assert store.get_asset(user.library_asset_id).lifecycle is LibraryAssetLifecycle.READY
    store.trash_asset(user.library_asset_id)
    store.permanently_delete_asset(user.library_asset_id)
    assert store.get_asset(user.library_asset_id) is None


def test_ingest_records_and_derivatives_are_idempotent(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    batch = store.create_ingest_batch(idempotency_key="batch-1", provenance={"source": "pc"})
    assert store.create_ingest_batch(idempotency_key="batch-1", provenance={})["ingest_batch_id"] == batch["ingest_batch_id"]
    asset = store.register_asset(**_asset_kwargs(tmp_path))
    item = store.record_ingest_item(batch_id=batch["ingest_batch_id"], idempotency_key="item-1", library_asset_id=asset.library_asset_id, filename="walk.mp4", state="ready")
    assert store.record_ingest_item(batch_id=batch["ingest_batch_id"], idempotency_key="item-1", library_asset_id=asset.library_asset_id, filename="walk.mp4", state="ready")["ingest_item_id"] == item["ingest_item_id"]
    derivative = store.upsert_derivative(library_asset_id=asset.library_asset_id, kind="thumbnail", managed_relative_path="derivatives/asset-1.jpg", content_sha256="b" * 64, byte_count=3, mime_type="image/jpeg")
    assert store.upsert_derivative(library_asset_id=asset.library_asset_id, kind="thumbnail", managed_relative_path="derivatives/new.jpg", content_sha256="c" * 64, byte_count=4, mime_type="image/jpeg")["derivative_id"] == derivative["derivative_id"]


def test_concurrent_constructors_share_additive_schema(tmp_path: Path) -> None:
    root = tmp_path / "library"

    def open_and_register(index: int) -> str:
        store = LibraryUserAssetStore(root)
        return store.register_asset(**{**_asset_kwargs(tmp_path), "library_asset_id": f"user:{index}", "content_sha256": f"{index:064x}"}).library_asset_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(open_and_register, range(8)))
    assert len(values) == 8
    assert len(LibraryUserAssetStore(root).list_assets()) == 8
