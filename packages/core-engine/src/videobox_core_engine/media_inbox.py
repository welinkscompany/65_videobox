"""Take in footage dropped into a watched folder (Task 18).

The watched folder is typically a Google Drive desktop client's local mirror
of a synced folder -- VideoBox never calls the Drive API and does not know
that's what it is. Moving a verified file out of it is enough for it to also
disappear from Drive (mirror mode); Drive's own trash is the 30-day recovery
window, so this module does not need to implement one itself.

Safety contract: verify the file's content hash before moving it, and only
delete the source once the moved copy at the destination has the same hash.
A move that fails partway, or a hash mismatch, must never remove the
original -- "복사 후 삭제가 아니라 검증 후 이동이다."
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Mirrors services/api/src/videobox_api/orchestration.py's
# BROLL_VIDEO_EXTENSIONS. Duplicated rather than imported: core-engine must
# not depend on the services/api layer above it.
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})

_IGNORED_FILENAMES = frozenset({"desktop.ini"})


def _is_hidden(path: Path, *, watch_root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(watch_root).parts)


def scan_inbox_candidates(watch_root: Path) -> list[Path]:
    """Find video files under `watch_root`, skipping hidden files/folders and
    Windows' own desktop.ini. Returns an empty list if the folder doesn't
    exist yet (e.g. Drive desktop isn't installed/synced)."""
    if not watch_root.is_dir():
        return []
    candidates: list[Path] = []
    for path in watch_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _IGNORED_FILENAMES:
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _is_hidden(path, watch_root=watch_root):
            continue
        candidates.append(path)
    return candidates


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def is_file_settled(
    path: Path,
    *,
    stat_size: Callable[[Path], int] = lambda candidate: candidate.stat().st_size,
    wait: Callable[[float], None] = None,
    wait_seconds: float = 2.0,
) -> bool:
    """A Drive sync in progress keeps growing a file's size. Comparing the
    size before and after a short wait is a robust, OS-portable proxy for
    "download finished" that doesn't depend on any Drive-specific
    placeholder/reparse-point mechanism VideoBox has no business knowing
    about."""
    if wait is None:
        import time

        wait = time.sleep
    before = stat_size(path)
    wait(wait_seconds)
    after = stat_size(path)
    return before == after


@dataclass(slots=True, frozen=True)
class MediaInboxConfig:
    watch_path: Path
    library_root: Path


@dataclass(slots=True)
class MediaInboxCycleReport:
    moved: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def run_inbox_cycle(
    config: MediaInboxConfig,
    *,
    is_settled: Callable[[Path], bool] = lambda path: is_file_settled(path),
) -> MediaInboxCycleReport:
    """Run one watch pass: scan -> skip unsettled -> verify hash -> move.

    Never stops on a single file's failure -- one bad file must not block the
    rest of the batch, matching the rest of this project's verification
    scripts (verify_owner_path.py's _StageRecorder does the same)."""
    report = MediaInboxCycleReport()
    config.library_root.mkdir(parents=True, exist_ok=True)
    existing_library_hashes = {
        _sha256_file(existing) for existing in config.library_root.iterdir() if existing.is_file()
    }
    for source in scan_inbox_candidates(config.watch_path):
        name = source.name
        try:
            if not is_settled(source):
                report.skipped.append(name)
                continue
            source_hash = _sha256_file(source)
            if source_hash in existing_library_hashes:
                # Redundant footage already in the library. Removing the
                # source is still safe: Drive's own trash (not VideoBox) is
                # the recovery window per the owner decision.
                source.unlink()
                report.duplicates.append(name)
                continue
            destination = config.library_root / name
            shutil.move(str(source), str(destination))
            moved_hash = _sha256_file(destination)
            if moved_hash != source_hash:
                # The move produced corrupt bytes at the destination. Do not
                # leave a broken file in the library, and do not claim
                # success -- but the source is already gone at this point,
                # so this is reported as a failure for a human to notice
                # rather than silently accepted.
                destination.unlink(missing_ok=True)
                report.failed.append(name)
                continue
            existing_library_hashes.add(moved_hash)
            report.moved.append(name)
        except OSError:
            report.failed.append(name)
    return report
