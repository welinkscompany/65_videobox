from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from videobox_domain_models.media_pack import MediaPackManifest


MediaProbe = Callable[[Path], Mapping[str, object]]


class ReleasePackValidationError(ValueError):
    """The pack cannot be distributed or activated under the release contract."""


def ffprobe_media(path: Path, *, ffprobe_binary: str = "ffprobe") -> Mapping[str, object]:
    try:
        result = subprocess.run(
            [ffprobe_binary, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels:format=bit_rate", "-of", "json", str(path)],
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
        "is_cbr": is_cbr_320_mp3(path) if str(path.suffix).lower() == ".mp3" else None,
    }


def is_cbr_320_mp3(path: Path) -> bool:
    """Accept only complete MPEG-1 Layer III streams whose every frame is 320 kbps."""
    data = path.read_bytes()
    position = _skip_id3v2(data)
    end = len(data) - 128 if data[-128:-125] == b"TAG" else len(data)
    frames = 0
    while position < end:
        if position + 4 > end:
            return False
        header = int.from_bytes(data[position:position + 4], "big")
        if header >> 21 != 0x7FF:
            return False
        version = (header >> 19) & 0x3
        layer = (header >> 17) & 0x3
        bitrate_index = (header >> 12) & 0xF
        sample_rate_index = (header >> 10) & 0x3
        padding = (header >> 9) & 0x1
        if version != 3 or layer != 1 or bitrate_index != 14 or sample_rate_index == 3:
            return False
        sample_rate = (44100, 48000, 32000)[sample_rate_index]
        frame_length = (144000 * 320 // sample_rate) + padding
        if position + frame_length > end:
            return False
        position += frame_length
        frames += 1
    return frames > 0 and position == end


def validate_release_contract(*, manifest: MediaPackManifest, root: Path, media_probe: MediaProbe) -> None:
    for asset in manifest.assets:
        evidence = _rooted_file(root, Path("evidence") / f"{asset.asset_id}.txt")
        if not evidence.is_file() or _sha256(evidence) != asset.license.evidence_sha256:
            raise ReleasePackValidationError(f"immutable evidence invalid: {asset.asset_id}")
        path = _rooted_file(root, Path(asset.pack_path))
        if not path.is_file():
            raise ReleasePackValidationError(f"missing asset: {asset.asset_id}")
        probe = media_probe(path)
        codec = str(probe.get("codec_name") or "").lower()
        if asset.media_type == "music":
            if path.suffix.lower() != ".mp3" or codec != "mp3" or _integer(probe.get("bit_rate")) != 320000 or probe.get("is_cbr") is not True:
                raise ReleasePackValidationError(f"music must be CBR 320 kbps MP3: {asset.asset_id}")
        elif asset.media_type == "sfx":
            if path.suffix.lower() != ".wav" or not codec.startswith("pcm_") or _integer(probe.get("sample_rate")) != 48000 or _integer(probe.get("channels")) != 1:
                raise ReleasePackValidationError(f"SFX must be 48 kHz mono PCM WAV: {asset.asset_id}")
        else:
            raise ReleasePackValidationError(f"unsupported media type: {asset.asset_id}")


def _skip_id3v2(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    size = 0
    for byte in data[6:10]:
        if byte & 0x80:
            return len(data)
        size = (size << 7) | byte
    has_footer = data[3] == 4 and bool(data[5] & 0x10)
    return min(10 + size + (10 if has_footer else 0), len(data))


def _rooted_file(root: Path, relative_path: Path) -> Path:
    root = root.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ReleasePackValidationError(f"unsafe pack file path: {relative_path}") from error
    return path


def _integer(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()
