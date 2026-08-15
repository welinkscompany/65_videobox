from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


def test_broll_ingest_persists_probe_metadata_without_blocking_copy(tmp_path: Path) -> None:
    class Probe:
        duration_sec = 18.0
        width = 640
        height = 360
        audio_codec = None

    store = LibraryUserAssetStore(tmp_path / "db")
    service = LibraryIngestService(
        store=store,
        managed_root=tmp_path / "managed",
        probe_metadata=lambda _path: Probe(),
    )
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video bytes")

    result = service.ingest(
        media_type="broll",
        source=source,
        filename="clip.mp4",
        idempotency_key="probe-1",
    )

    asset = store.get_asset(result["library_asset_id"])
    assert asset is not None
    assert asset.technical_metadata == {
        "duration_seconds": 18.0,
        "width": 640,
        "height": 360,
        "has_audio": False,
    }


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


def test_same_hash_with_different_media_type_is_explicitly_rejected(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    source = tmp_path / "asset.bin"
    source.write_bytes(b"same content")
    service.ingest(media_type="music", source=source, filename="asset.mp3", idempotency_key="music")

    try:
        service.ingest(media_type="sfx", source=source, filename="asset.wav", idempotency_key="sfx")
    except ValueError as error:
        assert str(error) == "content_hash_media_type_conflict"
    else:
        raise AssertionError("same content under a different media type must not reuse silently")
    assert len(store.list_assets()) == 1


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


def test_concurrent_same_idempotency_key_different_bytes_conflicts_atomically(tmp_path: Path, monkeypatch) -> None:
    service, store = _service(tmp_path)
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.write_bytes(b"first bytes")
    second.write_bytes(b"second bytes")
    barrier = Barrier(2)
    original_get = store.get_ingest_item

    def synchronized_get(key: str):
        result = original_get(key)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(store, "get_ingest_item", synchronized_get)

    def run(source: Path):
        try:
            return service.ingest(media_type="sfx", source=source, filename=source.name, idempotency_key="race")
        except Exception as error:  # noqa: BLE001 - assert the durable conflict below
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (first, second)))

    assert sum(isinstance(result, ValueError) and str(result) == "idempotency_key_conflict" for result in results) == 1
    assert sum(isinstance(result, dict) for result in results) == 1
    assert len(store.list_assets()) == 1
