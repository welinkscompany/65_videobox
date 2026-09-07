"""Take in assets dropped into a watched folder (Task 18).

**owner 결정 2026-09-07**
(`docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`): owner는
영상·그림·음악·효과음을 **폴더 하나**에만 넣고, 종류는 VideoBox가 내용을 보고
가른다(`sort_by_content` + `media_inbox_sorter`). 자산 가치가 없다고 본 것은
`불필요`로 **옮긴다 -- 지우지 않는다.** 종류를 폴더로 나누던 2026-08-10 결정을
뒤집은 것이고, 옛 길은 `sort_by_content=False`로 그대로 남아 있다.

The watched folder is typically a desktop sync client's local mirror
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
from typing import Any, Callable, Mapping, Protocol

from videobox_core_engine.library_ingest import LibraryIngestIdempotencyConflict, LibraryIngestService
from videobox_core_engine.media_inbox_sorter import SortedDrop, classify_drop
from videobox_storage.library_user_asset_store import LibraryUserAssetStore

# Mirrors services/api/src/videobox_api/orchestration.py's
# BROLL_VIDEO_EXTENSIONS. Duplicated rather than imported: core-engine must
# not depend on the services/api layer above it.
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})

# 음악과 효과음. 어느 쪽인지를 **파일이 들어온 폴더**가 정하던 옛 길에서 쓰던
# 집합이다(2026-08-10). 2026-09-07부터는 길이가 정한다
# (`media_inbox_sorter.SFX_MAX_SECONDS`) -- 확장자는 아예 보지 않는다.
# 옛 폴더가 아직 남아 있을 수 있어 집합은 그대로 둔다.
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"})

_IGNORED_FILENAMES = frozenset({"desktop.ini"})

_LOGGER = logging.getLogger(__name__)

# owner가 넣었는데 받지 못한 파일을 이미 말한 적 있는지. 감시가 30초마다 도니까
# 이것이 없으면 같은 파일 하나가 로그를 통째로 채운다.
_REPORTED_UNSUPPORTED: set[str] = set()


def _is_hidden(path: Path, *, watch_root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(watch_root).parts)


def scan_inbox_candidates(
    watch_root: Path, *, accepted_extensions: frozenset[str] | None = VIDEO_EXTENSIONS
) -> list[Path]:
    """Find the files this folder takes, skipping hidden files/folders and
    Windows' own desktop.ini. Returns an empty list if the folder doesn't
    exist yet (e.g. Drive desktop isn't installed/synced).

    `accepted_extensions` differs per watched folder: one folder takes video,
    another music, another sound effects. That was the whole of how VideoBox
    knew which kind a file is, until the owner reversed it on 2026-09-07.

    `None` means "take everything" -- the one drop folder
    (`docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`). There
    the kind is decided by content (`media_inbox_sorter`), and anything that
    turns out not to be media is moved to `불필요` rather than left in place
    with a log line nobody reads.
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
        if accepted_extensions is not None and path.suffix.lower() not in accepted_extensions:
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
    # 이 폴더가 받는 종류. 종류를 폴더로 나누던 2026-08-10 결정이 코드에서 살던
    # 자리다 -- `새 영상`은 영상만, `새 음악`과 `새 효과음`은 오디오만 받았다.
    # **2026-09-07부터 기본 길은 이게 아니다**: `sort_by_content`가 켜지면 이
    # 칸은 쓰이지 않고, 넣는 폴더는 무엇이든 받아 내용으로 가른다.
    accepted_extensions: frozenset[str] | None = VIDEO_EXTENSIONS
    # New Drive-mirror callers opt into the shared copy-only ingest pipeline.
    # ``False`` retains the historical local-watch move contract for callers
    # that have not migrated yet; the API bootstrap sets this to ``True``.
    copy_only: bool = False
    archive_source: bool = False
    media_type: str = "broll"
    ingest_store: LibraryUserAssetStore | None = None
    # --- 한 폴더에 넣으면 내용을 보고 가른다 (owner 결정 2026-09-07) ---
    # 켜면 `accepted_extensions`와 `media_type`은 쓰이지 않는다. 종류는
    # `media_inbox_sorter.classify_drop`이 ffprobe로 정하고, 바이트가 갈 자리는
    # `sorted_library_roots`가 정한다.
    sort_by_content: bool = False
    # 종류별 라이브러리 자리. 한군데 섞으면 촬영본 색인이 음원을 영상으로 알고
    # 화면 분석을 시도한다.
    sorted_library_roots: Mapping[str, Path] = field(default_factory=dict)
    # 자산 가치가 없다고 본 파일이 가는 곳. **지우지 않는다** -- owner가 직접
    # 보고 지운다. `None`이면 그대로 둔다.
    reject_root: Path | None = None
    # 감시 폴더가 없을 때 만들어 줄 것인가. 옛 종류별 폴더는 만들지 않는다 --
    # owner는 이제 폴더 하나만 쓴다.
    create_watch_path: bool = True


@dataclass(slots=True)
class MediaInboxCycleReport:
    moved: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    #: 자산 가치가 없다고 보고 `불필요`로 옮긴 것 (owner 결정 2026-09-07).
    rejected: list[str] = field(default_factory=list)


def _archive_original(source: Path, archive_root: Path, source_hash: str) -> None:
    """File an original the owner already gave us, never overwriting."""
    archive_root.mkdir(parents=True, exist_ok=True)
    filed = archive_root / source.name
    if filed.exists():
        filed = archive_root / f"{filed.stem}-{source_hash[:8]}{filed.suffix}"
    shutil.move(str(source), str(filed))


def _reject_original(source: Path, reject_root: Path | None, source_hash: str) -> None:
    """자산 가치가 없다고 본 파일을 `불필요`로 옮긴다.

    **지우지 않는다** (owner 결정 2026-09-07): owner가 직접 보고 지운다.
    프로그램이 지우면 되돌릴 수 없고, 잘못 분류한 것과 진짜 쓰레기를 구별할
    기회가 사라진다. 옮길 자리가 없으면 그냥 둔다 -- 그것도 안 지우는 것이다.
    """
    if reject_root is None:
        return
    _archive_original(source, reject_root, source_hash)


def _take_sorted_drop(
    config: MediaInboxConfig,
    source: Path,
    source_hash: str,
    report: MediaInboxCycleReport,
    *,
    classify: Callable[[Path], SortedDrop] = classify_drop,
) -> None:
    """한 폴더에 들어온 파일 하나를 내용대로 갈라 받는다 (owner 결정 2026-09-07).

    **순서가 안전장치다.** 자산으로 들어간 것을 확인한 **뒤에** 원본을 옮긴다.
    뒤집으면 ingest가 실패한 파일이 보관함으로 사라진다.
    """
    decision = classify(source)
    if decision.media_type is None:
        # 미디어가 아니거나 열리지 않는다. 옮기기만 하고 지우지 않는다.
        _reject_original(source, config.reject_root, source_hash)
        report.rejected.append(source.name)
        return
    library_root = config.sorted_library_roots.get(decision.media_type)
    if library_root is None:
        # 갈 자리를 모르는 종류다. 자산으로 받을 수도, 버릴 수도 없으니
        # 그대로 두고 사람이 볼 수 있게 실패로 적는다.
        _LOGGER.warning(
            "받을 자리를 못 찾았습니다: %s (%s)", source.name, decision.media_type
        )
        report.failed.append(source.name)
        return
    library_root.mkdir(parents=True, exist_ok=True)
    ingest_store = config.ingest_store or LibraryUserAssetStore(
        config.library_root.parent / ".videobox-library-state"
    )
    try:
        result = _ingest_sorted(config, ingest_store, library_root, source, source_hash, decision)
    except LibraryIngestIdempotencyConflict:
        # 같은 내용이 이미 자료실에 **다른 종류로** 있다. owner가 손으로 고쳐
        # 둔 것일 수 있으니 덮어쓰지 않는다 -- 이미 가진 것이므로 `불필요`로.
        _reject_original(source, config.reject_root, source_hash)
        report.duplicates.append(source.name)
        return
    if result.get("duplicate"):
        # 이미 자료실에 같은 내용이 있다 -- 결정 문서가 정한 "자산 가치가 없는
        # 것" 셋 중 하나다. 보관함이 아니라 `불필요`로 보낸다.
        _reject_original(source, config.reject_root, source_hash)
        report.duplicates.append(source.name)
        return
    if config.archive_root is not None:
        _archive_original(source, config.archive_root, source_hash)
    report.moved.append(source.name)


def _ingest_sorted(
    config: MediaInboxConfig,
    ingest_store: LibraryUserAssetStore,
    library_root: Path,
    source: Path,
    source_hash: str,
    decision: SortedDrop,
) -> dict[str, Any]:
    return LibraryIngestService(store=ingest_store, managed_root=library_root).ingest(
        media_type=decision.media_type,
        source=source,
        filename=source.name,
        # 같은 파일을 두 번 받지 않는다. 내용 해시가 열쇠라 이름을 바꿔 다시
        # 넣어도 같은 자산으로 걸린다(`find_by_content_sha256`).
        idempotency_key=f"media-inbox:{source_hash}",
        provenance={
            "source": "one_drop_folder",
            "watch_path": str(config.watch_path),
            "sorted_as": decision.media_type,
            "sorted_reason": decision.reason,
        },
    )


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
    # `불필요`도 같은 이유로 걸러야 한다. 안 그러면 owner가 확인하기 전에 매
    # 바퀴 자기가 내보낸 파일을 다시 집어 들고, ffprobe를 30초마다 다시 돈다.
    reject_root = config.reject_root.resolve() if config.reject_root is not None else None
    excluded = tuple(root for root in (archive_root, reject_root) if root is not None)
    candidates = [
        source
        for source in scan_inbox_candidates(
            config.watch_path,
            # 한 폴더 모드에서는 확장자로 거르지 않는다. 종류는 내용이 정하고,
            # 미디어가 아닌 것은 조용히 남겨두는 게 아니라 `불필요`로 옮긴다.
            accepted_extensions=None if config.sort_by_content else config.accepted_extensions,
        )
        # Drop what the archive already holds before deciding the pass is
        # busy: with the archive inside the watched folder every pass would
        # otherwise look like it had work and read the library for nothing.
        if not any(root in source.resolve().parents for root in excluded)
    ]
    if not candidates:
        # Almost every pass lands here. Hashing the whole library first cost a
        # full read of it every 30 seconds -- 760 MB at the time this was
        # found, and the library only ever grows -- for a pass with nothing to
        # compare against. The reads are invisible on screen; they just take
        # CPU and disk away from rendering.
        return report
    existing_library_hashes = (
        set()
        if config.copy_only
        # The copy-only path reconciles by content hash inside the ingest
        # store, so re-reading the whole library folder here buys nothing.
        else {
            _sha256_file(existing)
            for existing in config.library_root.iterdir()
            if existing.is_file()
        }
    )
    for source in candidates:
        name = source.name
        try:
            if not is_settled(source):
                report.skipped.append(name)
                continue
            source_hash = _sha256_file(source)
            if config.sort_by_content:
                _take_sorted_drop(config, source, source_hash, report)
                continue
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
