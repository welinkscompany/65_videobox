from __future__ import annotations

from pathlib import Path
import hashlib

import pytest
import videobox_storage.media_library_store as media_library_store_module

from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


def test_search_returns_only_active_verified_existing_assets(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    asset_path = tmp_path / "packs" / "starter-001" / "1.0.0" / "assets" / "music-001.mp3"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"audio")

    store.index_verified_pack(
        pack_id="starter-001",
        version="1.0.0",
        install_path=asset_path.parents[2],
        assets=[
            {
                "library_asset_id": "pack:starter-001:music-001",
                "asset_id": "music-001",
                "media_type": "music",
                "duration_seconds": 12.5,
                    "sha256": hashlib.sha256(b"audio").hexdigest(),
                "path": asset_path,
                "source": "Example Archive",
                "creator": "Example Creator",
                "license": {
                    "official_url": "https://example.com/license",
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "b" * 64,
                },
            }
        ],
    )

    assert [item["library_asset_id"] for item in store.search()] == ["pack:starter-001:music-001"]
    assert store.remove_inactive_versions(pack_id="starter-001") == []
    assert [item["library_asset_id"] for item in store.search()] == ["pack:starter-001:music-001"]


def test_removing_inactive_versions_keeps_active_version_searchable(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    active_path = tmp_path / "packs" / "starter-001" / "2.0.0" / "assets" / "music-001.mp3"
    inactive_path = tmp_path / "packs" / "starter-001" / "1.0.0" / "assets" / "music-001.mp3"
    for path in (active_path, inactive_path):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"audio")
    for version, path in (("1.0.0", inactive_path), ("2.0.0", active_path)):
        store.index_verified_pack(
            pack_id="starter-001",
            version=version,
            install_path=path.parents[2],
            assets=[
                {
                    "library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001",
                        "media_type": "music", "duration_seconds": 1.0, "sha256": hashlib.sha256(b"audio").hexdigest(),
                    "path": path, "source": "Example", "creator": "Creator",
                    "license": {"official_url": "https://example.com/license", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64},
                }
            ],
            active=version == "2.0.0",
        )

    assert store.remove_inactive_versions(pack_id="starter-001") == ["1.0.0"]
    assert [item["version"] for item in store.search()] == ["2.0.0"]


def test_unavailable_global_library_db_does_not_block_project_edit(tmp_path: Path) -> None:
    unavailable_root = tmp_path / "global-library"
    unavailable_root.write_text("not a directory", encoding="utf-8")
    library_store = MediaLibraryStore(unavailable_root)

    project = LocalProjectStore(tmp_path / "project-data").bootstrap_project("Editable project")

    assert project.name == "Editable project"
    # The global library remains lazy and is never a dependency of project edits.
    assert library_store.database_path == unavailable_root / "media_library.sqlite"


def test_removing_active_pack_version_is_rejected(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[])

    with pytest.raises(ValueError, match="active"):
        store.remove_pack(pack_id="starter-001", version="1.0.0")


def test_favorites_and_recent_usage_round_trip(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    store.set_favorite(library_asset_id="pack:starter-001:music-001", enabled=True)
    store.mark_recent_usage(library_asset_id="pack:starter-001:music-001")

    assert store.list_favorites() == ["pack:starter-001:music-001"]
    assert store.list_recent_usage() == ["pack:starter-001:music-001"]


def test_reindex_does_not_replace_immutable_license_evidence(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    path = tmp_path / "asset.mp3"
    path.write_bytes(b"audio")
    asset = {"library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001", "media_type": "music", "duration_seconds": 1.0, "sha256": "a" * 64, "path": path, "source": "Example", "creator": "Creator", "license": {"official_url": "https://example.com/first", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64}}
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[asset])
    asset["license"] = {"official_url": "https://example.com/replaced", "evidence_timestamp": "2026-07-13T10:00:00Z", "evidence_sha256": "c" * 64}
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[asset])

    assert store.get_license_evidence(pack_id="starter-001", version="1.0.0", library_asset_id="pack:starter-001:music-001")["official_url"] == "https://example.com/first"


def test_search_hides_asset_when_on_disk_checksum_no_longer_matches(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    path = tmp_path / "asset.mp3"
    path.write_bytes(b"original")
    import hashlib
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[{"library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001", "media_type": "music", "duration_seconds": 1.0, "sha256": hashlib.sha256(b"original").hexdigest(), "path": path, "source": "Example", "creator": "Creator", "license": {"official_url": "https://example.com/license", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64}}])
    path.write_bytes(b"tampered")

    assert store.search() == []


def test_search_reuses_checksum_verification_when_file_metadata_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    path = tmp_path / "asset.mp3"
    contents = b"original"
    path.write_bytes(contents)
    digest = hashlib.sha256(contents).hexdigest()
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[{"library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001", "media_type": "music", "duration_seconds": 1.0, "sha256": digest, "path": path, "source": "Example", "creator": "Creator", "license": {"official_url": "https://example.com/license", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64}}])
    calls = 0
    original = media_library_store_module._sha256_file
    def counted(file_path: Path) -> str:
        nonlocal calls
        calls += 1
        return original(file_path)
    monkeypatch.setattr(media_library_store_module, "_sha256_file", counted)

    assert store.search()
    assert store.search()
    assert calls == 1
    path.write_bytes(b"changed")
    assert store.search() == []
    assert calls == 2


def test_search_hides_asset_replaced_by_directory_without_raising(tmp_path: Path) -> None:
    store = MediaLibraryStore(tmp_path / "library")
    path = tmp_path / "asset.mp3"
    contents = b"original"
    path.write_bytes(contents)
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=tmp_path, assets=[{"library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001", "media_type": "music", "duration_seconds": 1.0, "sha256": hashlib.sha256(contents).hexdigest(), "path": path, "source": "Example", "creator": "Creator", "license": {"official_url": "https://example.com/license", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64}}])
    path.unlink()
    path.mkdir()

    assert store.search() == []
