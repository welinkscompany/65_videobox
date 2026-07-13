from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for _source_path in (
    REPOSITORY_ROOT / "packages" / "domain-models" / "src",
    REPOSITORY_ROOT / "packages" / "core-engine" / "src",
):
    sys.path.insert(0, str(_source_path))

from videobox_core_engine.media_pack_service import compute_pack_integrity
from videobox_domain_models.media_pack import MediaPackManifest


MediaProbe = Callable[[Path], Mapping[str, object]]
IntegrityCalculator = Callable[[Path], tuple[int, str]]


class ReleasePackValidationError(ValueError):
    pass


def ffprobe_media(path: Path, *, ffprobe_binary: str = "ffprobe") -> Mapping[str, object]:
    try:
        result = subprocess.run(
            [
                ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,bit_rate,sample_rate,channels:format=bit_rate",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleasePackValidationError(f"ffprobe failed for {path.name}: {error}") from error
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ReleasePackValidationError(f"ffprobe returned invalid JSON: {path.name}") from error
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams or not isinstance(streams[0], Mapping):
        raise ReleasePackValidationError(f"no audio stream: {path.name}")
    stream = streams[0]
    format_data = payload.get("format")
    format_bit_rate = format_data.get("bit_rate") if isinstance(format_data, Mapping) else None
    return {
        "codec_name": stream.get("codec_name"),
        "bit_rate": stream.get("bit_rate") or format_bit_rate,
        "sample_rate": stream.get("sample_rate"),
        "channels": stream.get("channels"),
    }


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

    for asset in manifest.assets:
        evidence_path = root / "evidence" / f"{asset.asset_id}.txt"
        if not evidence_path.is_file():
            raise ReleasePackValidationError(f"missing immutable evidence: {asset.asset_id}")
        if _sha256_file(evidence_path) != asset.license.evidence_sha256:
            raise ReleasePackValidationError(f"evidence checksum mismatch: {asset.asset_id}")

        asset_path = root / asset.pack_path
        if not asset_path.is_file():
            raise ReleasePackValidationError(f"missing asset: {asset.asset_id}")
        if _sha256_file(asset_path) != asset.sha256:
            raise ReleasePackValidationError(f"asset checksum mismatch: {asset.asset_id}")
        _validate_media_contract(asset_id=asset.asset_id, media_type=asset.media_type, path=asset_path, probe=media_probe(asset_path))

    actual_bytes, actual_digest = integrity_calculator(root)
    if actual_bytes != manifest.declared_bytes or actual_digest != manifest.sha256:
        raise ReleasePackValidationError("pack integrity does not match manifest")
    return manifest


def _validate_media_contract(*, asset_id: str, media_type: str, path: Path, probe: Mapping[str, object]) -> None:
    codec_name = str(probe.get("codec_name") or "").lower()
    if media_type == "music":
        if path.suffix.lower() != ".mp3" or codec_name != "mp3" or _integer(probe.get("bit_rate")) != 320_000:
            raise ReleasePackValidationError(f"music must be CBR 320 kbps MP3: {asset_id}")
        return
    if media_type == "sfx":
        if (
            path.suffix.lower() != ".wav"
            or not codec_name.startswith("pcm_")
            or _integer(probe.get("sample_rate")) != 48_000
            or _integer(probe.get("channels")) != 1
        ):
            raise ReleasePackValidationError(f"SFX must be 48 kHz mono PCM WAV: {asset_id}")
        return
    raise ReleasePackValidationError(f"unsupported media type: {asset_id}")


def _integer(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
