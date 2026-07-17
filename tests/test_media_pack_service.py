from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from videobox_core_engine.media_pack_service import MediaPackService, compute_pack_integrity
from videobox_storage.media_library_store import MediaLibraryStore


def _media_probe(_path: Path) -> dict[str, object]:
    return {"codec_name": "mp3", "bit_rate": "320000", "is_cbr": True}


def _write_pack(root: Path, *, contents: bytes = b"synthetic audio", declared_sha256: str | None = None) -> Path:
    asset_path = root / "assets" / "music-001.mp3"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(contents)
    asset_sha256 = declared_sha256 or hashlib.sha256(contents).hexdigest()
    evidence = b"official evidence"
    (root / "evidence").mkdir()
    (root / "evidence" / "music-001.txt").write_bytes(evidence)
    manifest = {
        "pack_id": "starter-001",
        "version": "1.0.0",
        "declared_bytes": 300 * 1024**2,
        "sha256": "a" * 64,
        "assets": [
            {
                "asset_id": "music-001",
                "sha256": asset_sha256, "pack_path": "assets/custom-name.mp3",
                "media_type": "music",
                "duration_seconds": 12.5,
                "source": "Example Archive",
                "creator": "Example Creator",
                "license": {
                    "official_url": "https://example.com/license",
                    "commercial_use": True,
                    "redistribution": True,
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
                },
            }
        ],
    }
    custom_asset_path = root / "assets" / "custom-name.mp3"
    asset_path.replace(custom_asset_path)
    (root / "padding.bin").touch()
    (root / "padding.bin").open("r+b").truncate(300 * 1024**2 - len(contents))
    manifest["declared_bytes"], manifest["sha256"] = compute_pack_integrity(root)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _service(tmp_path: Path) -> MediaPackService:
    return MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=MediaLibraryStore(tmp_path / "global-library"),
        duration_probe=lambda _path: 12.5,
        media_probe=_media_probe,
    )


def test_interrupted_staged_install_removes_only_staging_and_does_not_activate(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    service = _service(tmp_path)

    result = service.install(source, before_activation=lambda _staging: (_ for _ in ()).throw(RuntimeError("interrupted")))

    destination = tmp_path / "user-library" / "packs" / "starter-001"
    assert result.status == "failed"
    assert result.error_code == "install_failed"
    assert not (destination / "1.0.0.staging").exists()
    assert not (destination / "1.0.0").exists()
    assert service.library_store.search() == []


def test_checksum_mismatch_does_not_activate_or_index_pack(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source", declared_sha256="0" * 64)
    service = _service(tmp_path)

    result = service.install(source)

    assert result.status == "failed"
    assert result.error_code == "checksum_mismatch"
    assert not (tmp_path / "user-library" / "packs" / "starter-001" / "1.0.0").exists()
    assert service.library_store.search() == []


def test_duration_mismatch_returns_a_distinct_structured_error(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    service = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=MediaLibraryStore(tmp_path / "global-library"),
            duration_probe=lambda _path: 10.0,
            media_probe=_media_probe,
    )

    result = service.install(source)

    assert result.status == "failed"
    assert result.error_code == "duration_mismatch"


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), 0.0])
def test_non_finite_or_zero_probe_duration_is_rejected(tmp_path: Path, duration: float) -> None:
    source = _write_pack(tmp_path / "source")
    service = MediaPackService(user_library_root=tmp_path / "user-library", library_store=MediaLibraryStore(tmp_path / "global-library"), duration_probe=lambda _path: duration, media_probe=_media_probe)

    assert service.install(source).error_code == "duration_mismatch"


def test_reinstalling_verified_pack_is_idempotent(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    service = _service(tmp_path)

    first = service.install(source)
    second = service.install(source)

    assert first.status == "installed"
    assert second.status == "already_installed"
    assert [item["library_asset_id"] for item in service.library_store.search()] == ["pack:starter-001:music-001"]


def test_source_archive_bytes_are_not_indexed_as_selectable_library_assets(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = source / "source-archive" / "original-source.mp3"
    archive.parent.mkdir()
    archive.write_bytes(b"approved source bytes")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["declared_bytes"], manifest["sha256"] = compute_pack_integrity(source)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _service(tmp_path).install(source)

    assert result.status == "installed"
    assert [item["library_asset_id"] for item in _service(tmp_path).library_store.search()] == ["pack:starter-001:music-001"]


def test_pack_content_size_or_digest_mismatch_does_not_activate(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["declared_bytes"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _service(tmp_path).install(source)

    assert result.error_code == "pack_integrity_mismatch"


def test_pack_content_digest_mismatch_does_not_activate(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    (source / "padding.bin").write_bytes(b"changed")

    result = _service(tmp_path).install(source)

    assert result.error_code == "pack_integrity_mismatch"


def test_preexisting_destination_collision_is_preserved(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    destination = tmp_path / "user-library" / "packs" / "starter-001" / "1.0.0"
    destination.mkdir(parents=True)
    sentinel = destination / "keep.txt"
    sentinel.write_text("existing", encoding="utf-8")

    result = _service(tmp_path).install(source)

    assert result.error_code == "destination_collision"
    assert sentinel.read_text(encoding="utf-8") == "existing"


def test_existing_destination_with_unavailable_library_db_returns_structured_failure(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    destination = tmp_path / "user-library" / "packs" / "starter-001" / "1.0.0"
    destination.mkdir(parents=True)
    unavailable = tmp_path / "global-library"
    unavailable.write_text("not a directory", encoding="utf-8")
    service = MediaPackService(user_library_root=tmp_path / "user-library", library_store=MediaLibraryStore(unavailable), duration_probe=lambda _path: 12.5, media_probe=_media_probe)

    result = service.install(source)

    assert result.status == "failed"
    assert result.error_code == "install_failed"


def test_failed_reinstall_with_stale_index_preserves_existing_index_and_evidence(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    store = MediaLibraryStore(tmp_path / "global-library")
    stale_path = tmp_path / "missing-destination"
    asset = {
        "library_asset_id": "pack:starter-001:music-001", "asset_id": "music-001",
        "media_type": "music", "duration_seconds": 12.5, "sha256": "a" * 64,
        "path": stale_path / "assets" / "custom-name.mp3", "source": "Original source",
        "creator": "Original creator", "license": {"official_url": "https://example.com/original", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64},
    }
    store.index_verified_pack(pack_id="starter-001", version="1.0.0", install_path=stale_path, assets=[asset])
    service = MediaPackService(user_library_root=tmp_path / "user-library", library_store=store, duration_probe=lambda _path: 12.5, media_probe=_media_probe)

    result = service.install(source)

    assert result.error_code == "indexed_pack_collision"
    assert store.get_license_evidence(pack_id="starter-001", version="1.0.0", library_asset_id="pack:starter-001:music-001")["official_url"] == "https://example.com/original"
    assert store.get_pack(pack_id="starter-001", version="1.0.0")["install_path"] == str(stale_path)


@pytest.mark.parametrize(
    ("mutate_source", "media_probe"),
    [
        (lambda source: (source / "evidence" / "music-001.txt").unlink(), _media_probe),
        (lambda source: (source / "evidence" / "music-001.txt").write_bytes(b"tampered evidence"), _media_probe),
        (lambda _source: None, lambda _path: {"codec_name": "aac", "bit_rate": "320000", "is_cbr": True}),
        (lambda _source: None, lambda _path: {"codec_name": "mp3", "bit_rate": "320000", "is_cbr": False}),
    ],
    ids=["missing-evidence", "tampered-evidence", "wrong-codec", "vbr-average-320k"],
)
def test_release_contract_failure_never_indexes_or_activates_pack(
    tmp_path: Path,
    mutate_source: Callable[[Path], None],
    media_probe: Callable[[Path], dict[str, object]],
) -> None:
    source = _write_pack(tmp_path / "source")
    mutate_source(source)
    service = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=MediaLibraryStore(tmp_path / "global-library"),
        duration_probe=lambda _path: 12.5,
        media_probe=media_probe,
    )

    result = service.install(source)

    assert result.error_code == "release_contract"
    assert not (tmp_path / "user-library" / "packs" / "starter-001" / "1.0.0").exists()
    assert service.library_store.get_pack(pack_id="starter-001", version="1.0.0") is None
    assert service.library_store.search() == []


def test_release_contract_is_checked_on_source_before_creating_staging_copy(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    probed_paths: list[Path] = []
    service = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=MediaLibraryStore(tmp_path / "global-library"),
        duration_probe=lambda _path: 12.5,
        media_probe=lambda path: (probed_paths.append(path) or {"codec_name": "aac", "bit_rate": "320000", "is_cbr": True}),
    )

    result = service.install(source)

    assert result.error_code == "release_contract"
    assert probed_paths == [source / "assets" / "custom-name.mp3"]
    assert not (tmp_path / "user-library" / "packs" / "starter-001" / "1.0.0.staging").exists()


def test_release_contract_failure_does_not_remove_preexisting_inactive_index(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    (source / "evidence" / "music-001.txt").unlink()
    store = MediaLibraryStore(tmp_path / "global-library")
    stale_path = tmp_path / "stale"
    store.index_verified_pack(
        pack_id="starter-001",
        version="1.0.0",
        install_path=stale_path,
        active=False,
        assets=[{
            "library_asset_id": "pack:starter-001:music-001",
            "asset_id": "music-001",
            "media_type": "music",
            "duration_seconds": 12.5,
            "sha256": "a" * 64,
            "path": stale_path / "assets" / "custom-name.mp3",
            "source": "Original source",
            "creator": "Original creator",
            "license": {"official_url": "https://example.com/original", "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "b" * 64},
        }],
    )
    service = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=store,
        duration_probe=lambda _path: 12.5,
        media_probe=_media_probe,
    )

    result = service.install(source)

    assert result.error_code == "release_contract"
    assert store.get_pack(pack_id="starter-001", version="1.0.0")["install_path"] == str(stale_path)


def test_library_cleanup_failure_does_not_mask_primary_validation_error(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source", declared_sha256="0" * 64)
    unavailable = tmp_path / "global-library"
    unavailable.write_text("not a directory", encoding="utf-8")
    service = MediaPackService(user_library_root=tmp_path / "user-library", library_store=MediaLibraryStore(unavailable), duration_probe=lambda _path: 12.5, media_probe=_media_probe)

    result = service.install(source)

    assert result.error_code == "checksum_mismatch"


def test_pack_integrity_orders_relative_posix_paths_not_host_paths(tmp_path: Path) -> None:
    (tmp_path / "z").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "z" / "x.bin").write_bytes(b"x")
    (tmp_path / "a" / "y.bin").write_bytes(b"y")

    _, digest = compute_pack_integrity(tmp_path)
    expected = hashlib.sha256(b"a/y.bin\0y" + b"z/x.bin\0x").hexdigest()

    assert digest == expected


def test_verifier_script_can_start_from_repository_root() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/verify-starter-media-pack.py", "--help"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_verifier_does_not_leave_verification_library_or_index(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/verify-starter-media-pack.py", str(source), "--ffprobe", "missing-ffprobe"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert not (source.parent / ".verification-library").exists()
    assert not (source.parent / ".verification-index").exists()
