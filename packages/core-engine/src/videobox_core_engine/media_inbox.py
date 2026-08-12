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

import logging
import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from videobox_core_engine.library_ingest import LibraryIngestService
from videobox_storage.library_user_asset_store import LibraryUserAssetStore

# Mirrors services/api/src/videobox_api/orchestration.py's
# BROLL_VIDEO_EXTENSIONS. Duplicated rather than imported: core-engine must
# not depend on the services/api layer above it.
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})

# 음악과 효과음. 어느 쪽인지는 **파일이 들어온 폴더**가 정한다 -- owner 결정
# (2026-08-10). 내용을 듣고 프로그램이 음악인지 효과음인지 판단하는 방식은
# 틀릴 수 있어 채택하지 않았다. 그래서 확장자 집합은 둘이 같고, 감시 설정마다
# 어느 집합을 받을지만 다르다.
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"})

_IGNORED_FILENAMES = frozenset({"desktop.ini"})

_LOGGER = logging.getLogger(__name__)

# owner가 넣었는데 받지 못한 파일을 이미 말한 적 있는지. 감시가 30초마다 도니까
# 이것이 없으면 같은 파일 하나가 로그를 통째로 채운다.
_REPORTED_UNSUPPORTED: set[str] = set()


def _is_hidden(path: Path, *, watch_root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(watch_root).parts)


def scan_inbox_candidates(
    watch_root: Path, *, accepted_extensions: frozenset[str] = VIDEO_EXTENSIONS
) -> list[Path]:
    """Find the files this folder takes, skipping hidden files/folders and
    Windows' own desktop.ini. Returns an empty list if the folder doesn't
    exist yet (e.g. Drive desktop isn't installed/synced).

    `accepted_extensions` differs per watched folder: one folder takes video,
    another music, another sound effects. That is the whole of how VideoBox
    knows which kind a file is -- it never inspects the contents to guess.
    """
    if not watch_root.is_dir():
        return []
    candidates: list[Path] = []
    for path in watch_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _IGNORED_FILENAMES:
            continue
        if _is_hidden(path, watch_root=watch_root):
            continue
        if path.suffix.lower() not in accepted_extensions:
            # owner가 넣은 것인데 이 폴더가 받지 못하는 종류다. 예전에는 조용히
            # 넘어가서, 넣은 사람은 고장인지 기다려야 하는지 알 수가 없었다.
            # 숨김 파일과 desktop.ini는 owner가 넣은 것이 아니므로 위에서 먼저
            # 걸러 여기까지 오지 않는다.
            key = str(path)
            if key not in _REPORTED_UNSUPPORTED:
                _REPORTED_UNSUPPORTED.add(key)
                _LOGGER.warning(
                    "가져올 수 없는 종류라 그대로 둡니다: %s (%s 폴더가 받는 종류: %s)",
                    path.name,
                    watch_root.name,
                    ", ".join(sorted(accepted_extensions)),
                )
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
    # 이 폴더가 받는 종류. 종류를 폴더로 나눈다는 owner 결정이 코드에서 사는
    # 자리가 여기다 -- `새 영상`은 영상만, `새 음악`과 `새 효과음`은 오디오만
    # 받는다. 보관함은 셋이 함께 쓴다(`감시폴더.parent / "자산화_완료"`).
    accepted_extensions: frozenset[str] = VIDEO_EXTENSIONS
    # New Drive-mirror callers opt into the shared copy-only ingest pipeline.
    # ``False`` retains the historical local-watch move contract for callers
    # that have not migrated yet; the API bootstrap sets this to ``True``.
    copy_only: bool = False
    archive_source: bool = False
    media_type: str = "broll"
    ingest_store: LibraryUserAssetStore | None = None


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
    # The scan recurses, so an archive folder placed inside the watched folder
    # would feed itself: every pass would re-file what it filed last time,
    # multiplying the owner's footage under hash-suffixed names instead of
    # tidying it.
    archive_root = config.archive_root.resolve() if config.archive_root is not None else None
    candidates = [
        source
        for source in scan_inbox_candidates(
            config.watch_path, accepted_extensions=config.accepted_extensions
        )
        # Drop what the archive already holds before deciding the pass is
        # busy: with the archive inside the watched folder every pass would
        # otherwise look like it had work and read the library for nothing.
        if archive_root is None or archive_root not in source.resolve().parents
    ]
    if not candidates:
        # Almost every pass lands here. Hashing the whole library first cost a
        # full read of it every 30 seconds -- 760 MB at the time this was
        # found, and the library only ever grows -- for a pass with nothing to
        # compare against. The reads are invisible on screen; they just take
        # CPU and disk away from rendering.
        return report
    existing_library_hashes = {
        _sha256_file(existing) for existing in config.library_root.iterdir() if existing.is_file()
    }
    for source in candidates:
        name = source.name
        try:
            if not is_settled(source):
                report.skipped.append(name)
                continue
            source_hash = _sha256_file(source)
            if config.copy_only:
                ingest_store = config.ingest_store or LibraryUserAssetStore(
                    config.library_root.parent / ".videobox-library-state"
                )
                result = LibraryIngestService(
                    store=ingest_store, managed_root=config.library_root
                ).ingest(
                    media_type=config.media_type,
                    source=source,
                    filename=name,
                    idempotency_key=f"media-inbox:{source.resolve()}:{source_hash}",
                    provenance={"source": "drive_mirror", "watch_path": str(config.watch_path)},
                )
                if result.get("duplicate"):
                    report.duplicates.append(name)
                else:
                    report.moved.append(name)
                # Archiving is a separate, explicit policy.  The normal Drive
                # mirror path leaves its source untouched after copying.
                if config.archive_source and config.archive_root is not None:
                    _archive_original(source, config.archive_root, source_hash)
                continue
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
    source_hash = _sha256_file(source_path)
    # The browser retries after a response timeout. Reconcile by the watched
    # filename and bytes before registering a second project asset.
    store = getattr(pipeline, "store", None)
    list_assets = getattr(store, "list_assets", None)
    existing_assets = list_assets(project_id=project_id) if callable(list_assets) else []
    for existing in existing_assets:
        metadata = dict(existing.get("metadata") or {})
        if metadata.get("media_inbox_filename") != filename:
            continue
        resolve_storage_uri = getattr(store, "resolve_storage_uri", None)
        if not callable(resolve_storage_uri):
            continue
        stored_path = resolve_storage_uri(
            project_id=project_id, storage_uri=str(existing["storage_uri"])
        )
        if stored_path.is_file() and _sha256_file(stored_path) == source_hash:
            return {
                "asset_id": str(existing["asset_id"]),
                "project_id": project_id,
                "asset_type": str(existing["asset_type"]),
                "storage_uri": str(existing["storage_uri"]),
            }
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
        metadata_patch={"media_inbox_filename": filename, "media_inbox_sha256": source_hash},
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
