"""Keep what we know about each library asset, and keep it current.

The point is not one pass over today's 130 files. The owner will add music
and effects later, and those have to become findable without anyone
remembering to run something. Analysis is therefore keyed on the file's own
checksum: an asset that has never been measured, or whose bytes changed, is
pending; everything else is already done.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from videobox_storage.media_library_store import MediaLibraryStore


def _store(tmp_path: Path) -> MediaLibraryStore:
    return MediaLibraryStore(tmp_path / "library")


def _install(store: MediaLibraryStore, root: Path, assets: list[dict]) -> None:
    install_path = root / "pack"
    (install_path / "assets").mkdir(parents=True, exist_ok=True)
    manifest_assets = []
    for asset in assets:
        path = install_path / "assets" / f"{asset['asset_id']}.wav"
        path.write_bytes(asset["payload"])
        manifest_assets.append({
            "library_asset_id": f"pack:test-pack:{asset['asset_id']}",
            "asset_id": asset["asset_id"],
            "media_type": asset["media_type"],
            "duration_seconds": 1.0,
            "sha256": hashlib.sha256(asset["payload"]).hexdigest(),
            "path": str(path),
            "source": "https://example.test",
            "creator": "tester",
            "tags": [asset["media_type"]],
            "license": {
                "official_url": "https://example.test/l",
                "evidence_timestamp": "2026-01-01T00:00:00+00:00",
                "evidence_sha256": "0" * 64,
            },
        })
    store.index_verified_pack(
        pack_id="test-pack", version="1.0.0", install_path=install_path, assets=manifest_assets
    )
    store.activate_pack(pack_id="test-pack", version="1.0.0", install_path=install_path)


def test_every_installed_asset_starts_out_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _install(store, tmp_path, [
        {"asset_id": "music-a", "media_type": "music", "payload": b"aaaa"},
        {"asset_id": "sfx-b", "media_type": "sfx", "payload": b"bbbb"},
    ])

    pending = store.list_assets_needing_audio_analysis()

    assert sorted(item["library_asset_id"] for item in pending) == [
        "pack:test-pack:music-a",
        "pack:test-pack:sfx-b",
    ]


def test_an_analysed_asset_stops_being_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _install(store, tmp_path, [{"asset_id": "music-a", "media_type": "music", "payload": b"aaaa"}])
    pending = store.list_assets_needing_audio_analysis()

    store.save_audio_descriptor(
        library_asset_id="pack:test-pack:music-a",
        sha256=str(pending[0]["sha256"]),
        measurements={"duration_seconds": 12.0, "loudness_rms": 0.2, "brightness_hz": 2000.0, "onset_rate_per_second": 3.0},
        words={"세기": "강함", "밝기": "중간", "빠르기": "빠름"},
        description="강한 밝기 중간 빠른 음악",
        embedding=[0.1, 0.2, 0.3],
    )

    assert store.list_assets_needing_audio_analysis() == []
    saved = store.get_audio_descriptor(library_asset_id="pack:test-pack:music-a")
    assert saved["words"] == {"세기": "강함", "밝기": "중간", "빠르기": "빠름"}
    assert saved["embedding"] == [0.1, 0.2, 0.3]


def test_replacing_the_file_makes_it_pending_again(tmp_path: Path) -> None:
    # This is what makes "add more music later" work without anyone
    # remembering to re-run anything.
    store = _store(tmp_path)
    _install(store, tmp_path, [{"asset_id": "music-a", "media_type": "music", "payload": b"aaaa"}])
    original = store.list_assets_needing_audio_analysis()[0]
    store.save_audio_descriptor(
        library_asset_id="pack:test-pack:music-a",
        sha256=str(original["sha256"]),
        measurements={"duration_seconds": 1.0, "loudness_rms": 0.1, "brightness_hz": 900.0, "onset_rate_per_second": 0.2},
        words={"세기": "보통", "밝기": "어두움", "빠르기": "느림"},
        description="설명",
        embedding=[1.0, 0.0],
    )
    assert store.list_assets_needing_audio_analysis() == []

    _install(store, tmp_path, [{"asset_id": "music-a", "media_type": "music", "payload": b"cccc-different"}])

    pending = store.list_assets_needing_audio_analysis()
    assert [item["library_asset_id"] for item in pending] == ["pack:test-pack:music-a"]


def test_a_descriptor_without_an_embedding_is_still_kept_but_stays_pending(tmp_path: Path) -> None:
    # Measuring never needs the model; embedding does. When the local model is
    # unreachable the measurements are still worth keeping -- and the asset
    # must come back for its embedding once the model returns.
    store = _store(tmp_path)
    _install(store, tmp_path, [{"asset_id": "music-a", "media_type": "music", "payload": b"aaaa"}])
    sha = str(store.list_assets_needing_audio_analysis()[0]["sha256"])

    store.save_audio_descriptor(
        library_asset_id="pack:test-pack:music-a",
        sha256=sha,
        measurements={"duration_seconds": 1.0, "loudness_rms": 0.1, "brightness_hz": 900.0, "onset_rate_per_second": 0.2},
        words={"세기": "보통", "밝기": "어두움", "빠르기": "느림"},
        description="설명",
        embedding=None,
    )

    assert store.get_audio_descriptor(library_asset_id="pack:test-pack:music-a")["words"]["세기"] == "보통"
    assert [item["library_asset_id"] for item in store.list_assets_needing_audio_analysis()] == [
        "pack:test-pack:music-a"
    ]


def test_search_ranks_by_similarity_and_stays_within_the_kind_asked_for(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _install(store, tmp_path, [
        {"asset_id": "music-near", "media_type": "music", "payload": b"1"},
        {"asset_id": "music-far", "media_type": "music", "payload": b"2"},
        {"asset_id": "sfx-near", "media_type": "sfx", "payload": b"3"},
    ])
    by_id = {item["library_asset_id"]: item for item in store.list_assets_needing_audio_analysis()}
    vectors = {
        "pack:test-pack:music-near": [1.0, 0.0],
        "pack:test-pack:music-far": [0.0, 1.0],
        "pack:test-pack:sfx-near": [1.0, 0.0],
    }
    for library_asset_id, vector in vectors.items():
        store.save_audio_descriptor(
            library_asset_id=library_asset_id,
            sha256=str(by_id[library_asset_id]["sha256"]),
            measurements={"duration_seconds": 1.0, "loudness_rms": 0.1, "brightness_hz": 900.0, "onset_rate_per_second": 0.2},
            words={"세기": "보통", "밝기": "어두움", "빠르기": "느림"},
            description="설명",
            embedding=vector,
        )

    matches = store.find_audio_matches(query_embedding=[1.0, 0.0], media_type="music", limit=5)

    assert [match["library_asset_id"] for match in matches] == [
        "pack:test-pack:music-near",
        "pack:test-pack:music-far",
    ]
    assert matches[0]["score"] > matches[1]["score"]


def test_search_refuses_a_query_it_cannot_rank(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ValueError):
        store.find_audio_matches(query_embedding=[], media_type="music", limit=3)
    with pytest.raises(ValueError):
        store.find_audio_matches(query_embedding=[0.0, 0.0], media_type="music", limit=3)


def test_a_newer_description_version_makes_everything_pending_again(tmp_path: Path) -> None:
    """Stored vectors describe the wording that was current when they were
    made. Change the wording and the whole library is ranked against sentences
    that no longer exist -- so the version is part of what "already done"
    means, exactly like the checksum."""
    store = _store(tmp_path)
    _install(store, tmp_path, [{"asset_id": "music-a", "media_type": "music", "payload": b"aaaa"}])
    sha = str(store.list_assets_needing_audio_analysis()[0]["sha256"])
    store.save_audio_descriptor(
        library_asset_id="pack:test-pack:music-a",
        sha256=sha,
        measurements={"duration_seconds": 1.0, "loudness_rms": 0.1, "brightness_hz": 900.0, "onset_rate_per_second": 0.2},
        words={"세기": "보통", "밝기": "어두움", "빠르기": "느림"},
        description="옛 문장",
        embedding=[1.0, 0.0],
        description_version=1,
    )

    assert store.list_assets_needing_audio_analysis(description_version=1) == []
    assert [item["library_asset_id"] for item in store.list_assets_needing_audio_analysis(description_version=2)] == [
        "pack:test-pack:music-a"
    ]
