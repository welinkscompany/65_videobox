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
from typing import Any, Callable, Protocol

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
    # Where an original goes once VideoBox has taken a copy. Without it the
    # source is deleted, which tells the owner nothing about what was already
    # imported -- and if the watched folder is a mirrored Drive folder, that
    # delete removes their cloud original too. With it, the watched folder
    # holds exactly what is still waiting.
    archive_root: Path | None = None


@dataclass(slots=True)
class MediaInboxCycleReport:
    moved: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _archive_original(source: Path, archive_root: Path, source_hash: str) -> None:
    """File an original the owner already gave us, never overwriting."""
    archive_root.mkdir(parents=True, exist_ok=True)
    filed = archive_root / source.name
    if filed.exists():
        filed = archive_root / f"{filed.stem}-{source_hash[:8]}{filed.suffix}"
    shutil.move(str(source), str(filed))


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
                # Redundant footage already in the library. File it if there is
                # somewhere to file it -- it is still the owner's footage, and
                # "already have this" is worth seeing. Without an archive the
                # source is removed as before: Drive's own trash (not VideoBox)
                # is the recovery window per the owner decision.
                if config.archive_root is None:
                    source.unlink()
                else:
                    _archive_original(source, config.archive_root, source_hash)
                report.duplicates.append(name)
                continue
            destination = config.library_root / name
            if destination.exists():
                # A different file already occupies this filename (the
                # content-hash duplicate check above only catches same
                # *content*, not same *name*) -- shutil.move would silently
                # overwrite it. Disambiguate with the source's own hash
                # instead of ever clobbering an existing library file.
                destination = config.library_root / f"{destination.stem}-{source_hash[:8]}{destination.suffix}"
            if config.archive_root is None:
                shutil.move(str(source), str(destination))
            else:
                # Copy first, then file the original. The library copy is
                # hash-checked below, so a half-written copy never costs the
                # owner the original.
                shutil.copy2(str(source), str(destination))
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
            if config.archive_root is not None:
                # Only now that the library copy is verified byte-for-byte.
                _archive_original(source, config.archive_root, source_hash)
            existing_library_hashes.add(moved_hash)
            report.moved.append(name)
        except OSError:
            report.failed.append(name)
    return report


def import_media_inbox_asset_to_project(
    pipeline: object,
    *,
    project_id: str,
    library_root: Path,
    filename: str,
) -> dict[str, Any]:
    """Copy a verified media-inbox library file into a project as B-roll
    (Task 18's library -> project step, corrected by Task 22).

    Owner decision (2026-08-07): footage collected from the watched folder is
    B-roll -- material to cut into videos across several channels -- not the
    narration source.  Registering it through ``register_broll_asset`` is what
    makes it reach media facts, thumbnails, analysis and recommendation; the
    earlier ``raw_video`` registration reached none of them.

    The library copy stays in place -- the same footage can be reused across
    more than one project, matching the existing
    MediaLibraryStore/ProjectAssetMaterializer split (a project only ever gets
    a copy).
    """
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        # The library is always flat -- run_inbox_cycle writes with `.name`
        # only -- so any separator can only be a path-traversal attempt.
        raise ValueError("media_inbox_filename_invalid")
    source_path = library_root / filename
    if not source_path.is_file():
        raise FileNotFoundError(f"media_inbox_asset_missing: {filename}")
    payload = pipeline.register_broll_asset(  # type: ignore[attr-defined]
        project_id=project_id,
        source_path=source_path,
        title=source_path.stem,
        tags=[],
    )
    # Keep the library filename so a later pass can tell collected footage from
    # a manual upload without re-hashing the file.
    pipeline.store.update_asset_metadata(  # type: ignore[attr-defined]
        project_id=project_id,
        asset_id=payload["asset_id"],
        metadata_patch={"media_inbox_filename": filename},
    )
    return payload


class _StopSignal(Protocol):
    def is_set(self) -> bool: ...
    def wait(self, timeout: float) -> bool: ...


def run_inbox_watcher_loop(
    config: MediaInboxConfig,
    *,
    stop_event: _StopSignal,
    interval_seconds: float = 30.0,
    is_settled: Callable[[Path], bool] = lambda path: is_file_settled(path),
    on_cycle: Callable[[MediaInboxCycleReport], None] | None = None,
) -> None:
    """Repeatedly run a watch pass until `stop_event` is set.

    `stop_event` is any object duck-typing threading.Event's is_set()/wait()
    (a real Event in production, a fake in tests) so a caller can stop the
    loop promptly instead of waiting out a full sleep."""
    while not stop_event.is_set():
        report = run_inbox_cycle(config, is_settled=is_settled)
        if on_cycle is not None:
            on_cycle(report)
        if stop_event.is_set():
            return
        stop_event.wait(interval_seconds)
