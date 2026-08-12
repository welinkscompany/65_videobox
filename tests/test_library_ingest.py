from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from videobox_core_engine.library_ingest import LibraryIngestService
from videobox_storage.library_user_asset_store import LibraryUserAssetStore


def _service(tmp_path: Path) -> tuple[LibraryIngestService, LibraryUserAssetStore]:
    store = LibraryUserAssetStore(tmp_path / "db")
    return LibraryIngestService(store=store, managed_root=tmp_path / "managed"), store


def test_ingest_copies_and_keeps_source_bytes(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video bytes")
    before = source.read_bytes()

    result = service.ingest(
        media_type="broll",
        source=source,
        filename="clip.mp4",
        idempotency_key="drop-1",
        provenance={"source": "pc"},
    )

    assert source.read_bytes() == before
    assert result["state"] == "ready"
    asset = store.get_asset(result["library_asset_id"])
    assert asset is not None
    managed = tmp_path / "managed" / asset.managed_relative_path
    assert managed.read_bytes() == before
    assert not list((tmp_path / "managed" / ".staging").glob("*"))


def test_same_hash_reuses_asset_and_same_name_different_hash_gets_distinct_path(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    first = tmp_path / "same.mp4"
    first.write_bytes(b"one")
    second = tmp_path / "same-again.mp4"
    second.write_bytes(b"one")
    a = service.ingest(media_type="broll", source=first, filename="same.mp4", idempotency_key="a")
    b = service.ingest(media_type="broll", source=second, filename="same.mp4", idempotency_key="b")
    third = tmp_path / "same-different.mp4"
    third.write_bytes(b"two")
    c = service.ingest(media_type="broll", source=third, filename="same.mp4", idempotency_key="c")

    assert a["library_asset_id"] == b["library_asset_id"]
    assert a["managed_relative_path"] == b["managed_relative_path"]
    assert c["library_asset_id"] != a["library_asset_id"]
    assert c["managed_relative_path"] != a["managed_relative_path"]
    assert len(store.list_assets()) == 2


def test_response_loss_retry_is_idempotent(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    source = tmp_path / "music.mp3"
    source.write_bytes(b"music")
    first = service.ingest(media_type="music", source=source, filename="music.mp3", idempotency_key="retry")
    retry = service.ingest(media_type="music", source=source, filename="music.mp3", idempotency_key="retry")

    assert retry["library_asset_id"] == first["library_asset_id"]
    assert retry["ingest_item_id"] == first["ingest_item_id"]
    assert len(store.list_assets()) == 1


def test_stream_ingest_hashes_after_copy_and_accepts_bytesio(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    payload = b"effect sound"
    result = service.ingest(
        media_type="sfx",
        source=BytesIO(payload),
        filename="effect.wav",
        idempotency_key="stream-1",
    )
    asset = store.get_asset(result["library_asset_id"])
    assert asset is not None
    assert asset.content_sha256 == hashlib.sha256(payload).hexdigest()


def test_batch_keeps_partial_success_and_retries_failed_item(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    good = tmp_path / "good.mp4"
    good.write_bytes(b"good")
    missing = tmp_path / "missing.mp4"

    report = service.ingest_batch(
        media_type="broll",
        items=[(good, "good.mp4", "batch-good"), (missing, "missing.mp4", "batch-bad")],
        batch_idempotency_key="batch-1",
    )
    assert report["succeeded"] == ["good.mp4"]
    assert report["failed"][0]["filename"] == "missing.mp4"
    assert len(store.list_assets()) == 1
