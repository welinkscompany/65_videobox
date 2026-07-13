from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from collections.abc import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
for _source_path in (
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
):
    sys.path.insert(0, str(_source_path))

from videobox_core_engine.media_pack_release import ffprobe_media
from videobox_core_engine.media_pack_service import compute_pack_integrity
from videobox_domain_models.media_pack import MediaPackManifest


_HASH = re.compile(r"`([a-f0-9]{64})`")
_LINK = re.compile(r"\]\((https://[^)]+)\)")
_ASSET_ID = re.compile(r"`([a-z0-9-]+)`")
_VARIOUS = re.compile(r"`(sfx-various-[a-z0-9-]+)=([^`]+)`")
_SELECTION_TIMESTAMP = "2026-07-14T01:13:16+09:00"
_APPROVED_CANDIDATE_FINGERPRINT = "672dc23e794399edbd1fe2cb81d91eb9d30519eaf9d572b8c3a7a23e0e52d7a8"


@dataclass(frozen=True, slots=True)
class ApprovedCandidate:
    asset_id: str
    media_type: str
    title: str
    creator: str
    official_url: str
    selection_evidence_sha256: str
    source_url: str
    selection_timestamp: str = _SELECTION_TIMESTAMP


def load_approved_candidates(ledger_path: Path) -> list[ApprovedCandidate]:
    """Load only the explicitly approved source set from the research SSOT.

    The ledger intentionally retains human-readable table inheritance
    (``same page/hash``) and a compact list for 47 Spring Spring WAV files.
    This parser resolves those forms before any network access, then enforces
    the fixed v1 release set rather than accepting a best-effort subset.
    """
    text = Path(ledger_path).read_text(encoding="utf-8")
    candidates: list[ApprovedCandidate] = []
    media_type: str | None = None
    previous_page: str | None = None
    previous_hash: str | None = None
    previous_creator: str | None = None
    for line in text.splitlines():
        if line.startswith("## 승인 후보 — music") or line.startswith("### 승인 확장 — FMA") or line.startswith("### 승인 확장 — OpenGameArt individual music"):
            media_type = "music"
        elif line.startswith("## 승인 후보 — SFX") or line.startswith("### 승인 확장 — OpenGameArt individual SFX") or line.startswith("### 승인 확장 — RPG"):
            media_type = "sfx"
        if not line.startswith("| `"):
            continue
        asset_id_match = _ASSET_ID.search(line)
        if asset_id_match is None or media_type is None:
            continue
        asset_id = asset_id_match.group(1)
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        urls = _LINK.findall(line)
        source_urls = [url for url in urls if _is_source_url(url)]
        official_urls = [url for url in urls if url not in source_urls]
        hashes = _HASH.findall(line)
        if official_urls:
            previous_page = official_urls[0]
        if hashes:
            previous_hash = hashes[0]
        detail = cells[1] if len(cells) > 1 else asset_id
        title, creator = _title_and_creator(detail, fallback_creator=previous_creator)
        if creator:
            previous_creator = creator
        if not source_urls:
            continue
        if previous_page is None or previous_hash is None or previous_creator is None:
            raise ValueError(f"ledger provenance is incomplete: {asset_id}")
        candidates.append(ApprovedCandidate(
            asset_id=asset_id,
            media_type=media_type,
            title=title,
            creator=previous_creator,
            official_url=previous_page,
            selection_evidence_sha256=previous_hash,
            source_url=source_urls[-1],
        ))
    candidates.extend(_various_sound_effects(text))
    _validate_candidate_set(candidates)
    return candidates


def _is_source_url(url: str) -> bool:
    return "/sites/default/files/" in url or "files.freemusicarchive.org/" in url


def _title_and_creator(detail: str, *, fallback_creator: str | None) -> tuple[str, str | None]:
    clean = _LINK.sub("", detail).replace("`", "").strip()
    if "—" in clean:
        title, creator = (part.strip() for part in clean.rsplit("—", 1))
        return title or "Approved asset", creator or fallback_creator
    if "·" in clean:
        creator = clean.split("·", 1)[0].strip()
        return "Approved asset", creator or fallback_creator
    return clean or "Approved asset", fallback_creator


def _various_sound_effects(text: str) -> list[ApprovedCandidate]:
    page = "https://opengameart.org/content/various-sound-effects-0"
    evidence_hash = "925a53041ff971e46ad4b5e8ac0857ce753ba0dcad4e6ddf30dac20031f14682"
    base = "https://opengameart.org/sites/default/files/"
    return [
        ApprovedCandidate(
            asset_id=asset_id,
            media_type="sfx",
            title=filename,
            creator="Spring Spring",
            official_url=page,
            selection_evidence_sha256=evidence_hash,
            source_url=base + filename,
        )
        for asset_id, filename in _VARIOUS.findall(text)
    ]


def _validate_candidate_set(candidates: list[ApprovedCandidate]) -> None:
    if len(candidates) != 130:
        raise ValueError(f"approved release set must contain 130 candidates, got {len(candidates)}")
    if sum(candidate.media_type == "music" for candidate in candidates) != 30:
        raise ValueError("approved release set must contain 30 music candidates")
    if sum(candidate.media_type == "sfx" for candidate in candidates) != 100:
        raise ValueError("approved release set must contain 100 SFX candidates")
    if len({candidate.asset_id for candidate in candidates}) != len(candidates):
        raise ValueError("approved release set contains duplicate asset IDs")
    if any(not candidate.source_url.startswith("https://") or not candidate.official_url.startswith("https://") for candidate in candidates):
        raise ValueError("approved release set must use HTTPS provenance URLs")
    if _candidate_fingerprint(candidates) != _APPROVED_CANDIDATE_FINGERPRINT:
        raise ValueError("approved release set fingerprint does not match the license ledger")


def _candidate_fingerprint(candidates: list[ApprovedCandidate]) -> str:
    records = [
        {
            "asset_id": candidate.asset_id,
            "media_type": candidate.media_type,
            "official_url": candidate.official_url,
            "selection_evidence_sha256": candidate.selection_evidence_sha256,
            "selection_timestamp": candidate.selection_timestamp,
            "source_url": candidate.source_url,
        }
        for candidate in sorted(candidates, key=lambda item: item.asset_id)
    ]
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_asset(
    candidate: ApprovedCandidate,
    *,
    output_root: Path,
    source_root: Path,
    download: Callable[[str, Path], None],
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
) -> dict[str, object]:
    """Download, transcode, probe and evidence one approved candidate."""
    source_suffix = Path(urlparse(candidate.source_url).path).suffix or ".source"
    source_path = Path(source_root) / f"{candidate.asset_id}{source_suffix}"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    download(candidate.source_url, source_path)
    if not source_path.is_file() or not source_path.stat().st_size:
        raise ValueError(f"download produced no source bytes: {candidate.asset_id}")
    source_duration_seconds = _probe_duration(source_path, ffprobe_binary=ffprobe_binary)
    source_probe = ffprobe_media(source_path, ffprobe_binary=ffprobe_binary)
    source_archive_path = Path(output_root) / "source-archive" / f"{candidate.asset_id}{source_suffix}"
    source_archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, source_archive_path)
    output_suffix = ".mp3" if candidate.media_type == "music" else ".wav"
    output_path = Path(output_root) / "assets" / f"{candidate.asset_id}{output_suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg_binary, "-y", "-v", "error", "-i", str(source_path), "-vn"]
    if candidate.media_type == "music":
        command.extend(["-ar", "44100", "-c:a", "libmp3lame", "-b:a", "320k", "-minrate", "320k", "-maxrate", "320k", "-bufsize", "320k"])
    elif candidate.media_type == "sfx":
        command.extend(["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1"])
    else:
        raise ValueError(f"unsupported media type: {candidate.media_type}")
    command.append(str(output_path))
    subprocess.run(command, check=True, capture_output=True, text=True)
    duration_seconds = _probe_duration(output_path, ffprobe_binary=ffprobe_binary)
    if duration_seconds <= 0:
        raise ValueError(f"non-positive converted duration: {candidate.asset_id}")
    probe = ffprobe_media(output_path, ffprobe_binary=ffprobe_binary)
    _validate_converted_asset(candidate, output_path, probe)
    source_sha256 = _sha256(source_path)
    converted_sha256 = _sha256(output_path)
    evidence_path = Path(output_root) / "evidence" / f"{candidate.asset_id}.txt"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("\n".join((
        f"asset_id={candidate.asset_id}",
        f"media_type={candidate.media_type}",
        f"title={candidate.title}",
        f"creator={candidate.creator}",
        f"source_url={candidate.source_url}",
        f"source_sha256={source_sha256}",
        f"source_duration_seconds={source_duration_seconds:.6f}",
        f"source_format={json.dumps(source_probe, sort_keys=True)}",
        f"source_archive_path={source_archive_path.relative_to(output_root).as_posix()}",
        f"official_url={candidate.official_url}",
        f"selection_evidence_sha256={candidate.selection_evidence_sha256}",
        f"selection_timestamp={candidate.selection_timestamp}",
        f"converted_sha256={converted_sha256}",
        f"duration_seconds={duration_seconds:.6f}",
        "conversion=ffmpeg verified output",
        "",
    )), encoding="utf-8")
    return {
        "asset_id": candidate.asset_id,
        "pack_path": output_path.relative_to(output_root).as_posix(),
        "sha256": converted_sha256,
        "media_type": candidate.media_type,
        "duration_seconds": duration_seconds,
        "source": candidate.source_url,
        "creator": candidate.creator,
    }


def _probe_duration(path: Path, *, ffprobe_binary: str) -> float:
    result = subprocess.run(
        [ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _validate_converted_asset(candidate: ApprovedCandidate, path: Path, probe: dict[str, object] | object) -> None:
    if not isinstance(probe, dict):
        raise ValueError(f"invalid converted probe: {candidate.asset_id}")
    if candidate.media_type == "music":
        valid = path.suffix == ".mp3" and probe.get("codec_name") == "mp3" and str(probe.get("bit_rate")) == "320000" and probe.get("is_cbr") is True
        if not valid:
            raise ValueError(f"music conversion contract failed: {candidate.asset_id}")
    else:
        valid = path.suffix == ".wav" and str(probe.get("codec_name", "")).startswith("pcm_") and str(probe.get("sample_rate")) == "48000" and str(probe.get("channels")) == "1"
        if not valid:
            raise ValueError(f"SFX conversion contract failed: {candidate.asset_id}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_release_metadata(
    output_root: Path,
    *,
    pack_id: str,
    version: str,
    candidates: list[ApprovedCandidate],
    assets: list[dict[str, object]],
) -> dict[str, object]:
    """Create provenance documents and the manifest after all media exists."""
    candidate_by_id = {candidate.asset_id: candidate for candidate in candidates}
    if set(candidate_by_id) != {str(asset["asset_id"]) for asset in assets}:
        raise ValueError("release assets do not match approved candidates")
    licenses = ["# Starter Media Pack licenses", "", "All bundled media is released under CC0 1.0.", "", "## Source evidence", ""]
    manifest_assets: list[dict[str, object]] = []
    for asset in sorted(assets, key=lambda item: str(item["asset_id"])):
        candidate = candidate_by_id[str(asset["asset_id"])]
        evidence_path = Path(output_root) / "evidence" / f"{candidate.asset_id}.txt"
        if not evidence_path.is_file():
            raise ValueError(f"missing evidence file: {candidate.asset_id}")
        licenses.append(f"- `{candidate.asset_id}` — {candidate.creator}; {candidate.official_url}; CC0-1.0")
        manifest_assets.append({
            **asset,
            "tags": [candidate.media_type],
            "license": {
                "official_url": candidate.official_url,
                "commercial_use": True,
                "redistribution": True,
                "evidence_timestamp": candidate.selection_timestamp,
                "evidence_sha256": _sha256(evidence_path),
                "attribution_required": False,
                "attribution_text": "",
            },
        })
    (Path(output_root) / "LICENSES.md").write_text("\n".join(licenses) + "\n", encoding="utf-8")
    (Path(output_root) / "SOURCE_ARCHIVE.md").write_text(
        "# Source archive\n\n"
        "`source-archive/` contains the exact approved CC0 source bytes used to create each library asset. "
        "They are retained for reproducibility and provenance only; only files listed in `manifest.json` are selectable library assets.\n",
        encoding="utf-8",
    )
    declared_bytes, digest = compute_pack_integrity(Path(output_root))
    manifest = {
        "pack_id": pack_id,
        "version": version,
        "declared_bytes": declared_bytes,
        "sha256": digest,
        "assets": manifest_assets,
    }
    (Path(output_root) / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def build_pack(
    candidates: list[ApprovedCandidate],
    *,
    output_root: Path,
    source_root: Path,
    download: Callable[[str, Path], None],
    pack_id: str = "starter-v1",
    version: str = "1.0.0",
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
) -> dict[str, object]:
    """Build a release candidate only from downloaded approved source bytes."""
    _validate_candidate_set(candidates)
    output_root = Path(output_root)
    if output_root.exists():
        raise ValueError(f"output directory already exists: {output_root}")
    output_root.mkdir(parents=True)
    assets = [
        build_asset(
            candidate,
            output_root=output_root,
            source_root=source_root,
            download=download,
            ffmpeg_binary=ffmpeg_binary,
            ffprobe_binary=ffprobe_binary,
        )
        for candidate in candidates
    ]
    manifest = write_release_metadata(output_root, pack_id=pack_id, version=version, candidates=candidates, assets=assets)
    minimum = 300 * 1024**2
    maximum = 500 * 1024**2
    if not minimum <= int(manifest["declared_bytes"]) <= maximum:
        raise ValueError(f"real pack output must be within 300-500 MiB, got {int(manifest['declared_bytes'])} bytes")
    MediaPackManifest.from_dict(manifest)
    return manifest


def _download(url: str, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        request = Request(url, headers={"User-Agent": "VideoBox/1.0 starter-media-pack-release-builder"})
        with urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the verified Starter Media Pack from approved source bytes.")
    parser.add_argument("--ledger", type=Path, default=REPO_ROOT / "docs" / "starter-media-pack-license-research.ko.md")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist" / "starter-media-pack")
    parser.add_argument("--source-cache", type=Path, default=REPO_ROOT / "artifacts" / "starter-media-pack-sources")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    candidates = load_approved_candidates(args.ledger)
    manifest = build_pack(
        candidates,
        output_root=args.output,
        source_root=args.source_cache,
        download=_download,
        ffmpeg_binary=args.ffmpeg,
        ffprobe_binary=args.ffprobe,
    )
    print(f"OK: {manifest['pack_id']}@{manifest['version']} {manifest['declared_bytes']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
