from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from starter_media_pack import ReleasePackValidationError, verify_release_pack
from videobox_core_engine.media_pack_release import is_cbr_320_mp3


def _write_release_pack(
    root: Path,
    *,
    media_type: str = "music",
    extension: str = ".mp3",
    include_evidence: bool = True,
) -> Path:
    asset_id = f"{media_type}-001"
    asset_path = root / "assets" / f"{asset_id}{extension}"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"synthetic media")
    evidence_path = root / "evidence" / f"{asset_id}.txt"
    if include_evidence:
        evidence_path.parent.mkdir(parents=True)
        evidence_path.write_text("official source evidence", encoding="utf-8")
    manifest = {
        "pack_id": "starter-001",
        "version": "1.0.0",
        "declared_bytes": 300 * 1024**2,
        "sha256": "a" * 64,
        "assets": [
            {
                "asset_id": asset_id,
                "pack_path": f"assets/{asset_id}{extension}",
                "sha256": hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                "media_type": media_type,
                "duration_seconds": 3.0,
                "source": "Official source",
                "creator": "Example creator",
                "license": {
                    "official_url": "https://example.com/license",
                    "commercial_use": True,
                    "redistribution": True,
                    "evidence_timestamp": "2026-07-13T00:00:00Z",
                    "evidence_sha256": hashlib.sha256(
                        evidence_path.read_bytes() if include_evidence else b"official source evidence"
                    ).hexdigest(),
                },
            }
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _valid_integrity(_root: Path) -> tuple[int, str]:
    return 300 * 1024**2, "a" * 64


def _mpeg1_layer3_frame(*, bitrate_index: int = 14) -> bytes:
    header = (0x7FF << 21) | (3 << 19) | (1 << 17) | (1 << 16) | (bitrate_index << 12)
    bitrate_kbps = {13: 256, 14: 320}[bitrate_index]
    frame_size = 144000 * bitrate_kbps // 44100
    return header.to_bytes(4, "big") + bytes(frame_size - 4)


def test_cbr_parser_accepts_id3v24_footer_before_valid_cbr_frames(tmp_path: Path) -> None:
    path = tmp_path / "footer.mp3"
    path.write_bytes(b"ID3" + bytes([4, 0, 0x10, 0, 0, 0, 0]) + b"3DI" + bytes([4, 0, 0x10, 0, 0, 0, 0]) + _mpeg1_layer3_frame())

    assert is_cbr_320_mp3(path) is True


def test_cbr_parser_does_not_treat_id3v23_experimental_flag_as_a_footer(tmp_path: Path) -> None:
    path = tmp_path / "v23-experimental.mp3"
    path.write_bytes(b"ID3" + bytes([3, 0, 0x10, 0, 0, 0, 0]) + _mpeg1_layer3_frame())

    assert is_cbr_320_mp3(path) is True


def test_cbr_parser_rejects_vbr_frames_even_when_average_bitrate_can_be_320k(tmp_path: Path) -> None:
    path = tmp_path / "vbr-average-320.mp3"
    path.write_bytes(_mpeg1_layer3_frame() + _mpeg1_layer3_frame(bitrate_index=13) + _mpeg1_layer3_frame())

    assert is_cbr_320_mp3(path) is False


def test_release_verifier_rejects_music_that_is_not_cbr_320k_mp3(tmp_path: Path) -> None:
    root = _write_release_pack(tmp_path / "pack")

    with pytest.raises(ReleasePackValidationError, match="320 kbps"):
        verify_release_pack(
            root,
            media_probe=lambda _path: {"codec_name": "mp3", "bit_rate": "192000"},
            integrity_calculator=_valid_integrity,
        )


def test_release_verifier_rejects_sfx_that_is_not_48khz_mono_pcm_wav(tmp_path: Path) -> None:
    root = _write_release_pack(tmp_path / "pack", media_type="sfx", extension=".wav")

    with pytest.raises(ReleasePackValidationError, match="48 kHz mono PCM WAV"):
        verify_release_pack(
            root,
            media_probe=lambda _path: {
                "codec_name": "pcm_s16le",
                "sample_rate": "44100",
                "channels": 1,
            },
            integrity_calculator=_valid_integrity,
        )


def test_release_verifier_rejects_missing_immutable_evidence_snapshot(tmp_path: Path) -> None:
    root = _write_release_pack(tmp_path / "pack", include_evidence=False)

    with pytest.raises(ReleasePackValidationError, match="evidence"):
        verify_release_pack(
            root,
            media_probe=lambda _path: {"codec_name": "mp3", "bit_rate": "320000", "is_cbr": True},
            integrity_calculator=_valid_integrity,
        )


def test_release_verifier_rejects_actual_pack_size_outside_manifest_bounds(tmp_path: Path) -> None:
    root = _write_release_pack(tmp_path / "pack")

    with pytest.raises(ReleasePackValidationError, match="integrity"):
        verify_release_pack(
            root,
            media_probe=lambda _path: {"codec_name": "mp3", "bit_rate": "320000", "is_cbr": True},
            integrity_calculator=lambda _root: (299 * 1024**2, "a" * 64),
        )


def test_release_script_labels_media_contract_failures_before_install(tmp_path: Path) -> None:
    root = _write_release_pack(tmp_path / "pack")
    repository_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/verify-starter-media-pack.py", str(root), "--ffprobe", "missing-ffprobe"],
        cwd=repository_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "FAILED [release_contract]" in result.stdout
