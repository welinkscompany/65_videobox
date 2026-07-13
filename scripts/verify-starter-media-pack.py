from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
):
    sys.path.insert(0, str(source_path))

from videobox_core_engine.media_pack_service import MediaPackService
from videobox_storage.media_library_store import MediaLibraryStore
from starter_media_pack import ReleasePackValidationError, ffprobe_media, verify_release_pack


def _probe_duration(path: Path, *, ffprobe_binary: str) -> float:
    result = subprocess.run(
        [ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a starter media-pack directory without downloading media.")
    parser.add_argument("pack_directory", type=Path)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    root = args.pack_directory.resolve()
    try:
        verify_release_pack(
            root,
            media_probe=lambda path: ffprobe_media(path, ffprobe_binary=args.ffprobe),
        )
    except ReleasePackValidationError as error:
        print(f"FAILED [release_contract]: {error}")
        return 1
    with tempfile.TemporaryDirectory(prefix="videobox-pack-verify-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        service = MediaPackService(
            user_library_root=temporary_root / "library",
            library_store=MediaLibraryStore(temporary_root / "index"),
            duration_probe=lambda path: _probe_duration(path, ffprobe_binary=args.ffprobe),
        )
        result = service.install(root)
    if result.status not in {"installed", "already_installed"}:
        print(f"FAILED [{result.error_code}]: {result.message}")
        return 1
    print(f"OK: {result.pack_id}@{result.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
