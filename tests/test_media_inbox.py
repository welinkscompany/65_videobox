from __future__ import annotations

import time
from pathlib import Path

import pytest

from videobox_core_engine.media_inbox import (
    MediaInboxConfig,
    import_media_inbox_asset_to_project,
    is_file_settled,
    run_inbox_cycle,
    run_inbox_watcher_loop,
    scan_inbox_candidates,
)


class _FakeStopEvent:
    """Duck-types threading.Event's is_set()/wait() without a real clock."""

    def __init__(self, stop_after_waits: int) -> None:
        self._waits = 0
        self._stop_after_waits = stop_after_waits
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def wait(self, timeout: float) -> bool:
        self.last_timeout = timeout
        self._waits += 1
        if self._waits >= self._stop_after_waits:
            self._set = True
        return self._set


def test_scan_finds_video_files_recursively_and_ignores_noise(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive-folder"
    (watch_root / "가로" / "FHD").mkdir(parents=True)
    top_video = watch_root / "clip.mp4"
    top_video.write_bytes(b"top")
    nested_video = watch_root / "가로" / "FHD" / "nested.mov"
    nested_video.write_bytes(b"nested")
    (watch_root / "desktop.ini").write_text("[.ShellClassInfo]")
    (watch_root / ".hidden_video.mp4").write_bytes(b"hidden")
    (watch_root / "notes.txt").write_text("not a video")
    (watch_root / "thumbnails").mkdir()
    (watch_root / "thumbnails" / "cover.jpg").write_bytes(b"jpg")

    found = scan_inbox_candidates(watch_root)

    assert sorted(path.relative_to(watch_root).as_posix() for path in found) == [
        "clip.mp4",
        "가로/FHD/nested.mov",
    ]


def test_scan_returns_empty_for_a_missing_or_nonexistent_watch_root(tmp_path: Path) -> None:
    assert scan_inbox_candidates(tmp_path / "does-not-exist") == []


def test_is_file_settled_requires_two_stable_stat_reads(tmp_path: Path) -> None:
    path = tmp_path / "growing.mp4"
    path.write_bytes(b"partial")
    sizes = iter([7, 20])  # size changes between reads -> still downloading

    def fake_stat_size(candidate: Path) -> int:
        del candidate
        return next(sizes)

    waited: list[float] = []
    assert is_file_settled(path, stat_size=fake_stat_size, wait=waited.append, wait_seconds=0.5) is False
    assert waited == [0.5]


def test_is_file_settled_is_true_when_size_does_not_change(tmp_path: Path) -> None:
    path = tmp_path / "done.mp4"
    path.write_bytes(b"complete file")
    assert is_file_settled(path, wait=lambda _seconds: None, wait_seconds=0.01) is True


def test_verify_and_move_moves_only_after_hash_matches_and_original_disappears(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    source = watch_root / "clip.mp4"
    source.write_bytes(b"real footage bytes")

    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    report = run_inbox_cycle(config)

    assert report.moved == ["clip.mp4"]
    assert report.failed == []
    assert not source.exists()
    moved_path = library_root / "clip.mp4"
    assert moved_path.read_bytes() == b"real footage bytes"


def test_run_inbox_cycle_skips_unsettled_files_and_leaves_them_for_the_next_pass(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    source = watch_root / "still-syncing.mp4"
    source.write_bytes(b"partial")

    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    report = run_inbox_cycle(config, is_settled=lambda _path: False)

    assert report.moved == []
    assert report.skipped == ["still-syncing.mp4"]
    assert source.exists()
    assert not (library_root / "still-syncing.mp4").exists()


def test_run_inbox_cycle_deduplicates_by_content_hash_against_an_existing_library_file(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "already-here.mp4").write_bytes(b"same bytes")
    duplicate_source = watch_root / "duplicate.mp4"
    duplicate_source.write_bytes(b"same bytes")

    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    report = run_inbox_cycle(config)

    assert report.duplicates == ["duplicate.mp4"]
    assert report.moved == []
    # Duplicate handling still removes the redundant source (matches the
    # decision doc: Drive's own trash is the 30-day safety net, VideoBox
    # does not need to keep redundant copies around forever).
    assert not duplicate_source.exists()


def test_run_inbox_cycle_never_deletes_the_source_when_the_move_itself_fails(tmp_path: Path, monkeypatch) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    source = watch_root / "clip.mp4"
    source.write_bytes(b"real footage bytes")
    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)

    import videobox_core_engine.media_inbox as media_inbox_module

    def broken_move(_src, _dst):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(media_inbox_module.shutil, "move", broken_move)
    report = run_inbox_cycle(config)

    assert report.failed == ["clip.mp4"]
    assert report.moved == []
    assert source.exists()
    assert source.read_bytes() == b"real footage bytes"


def test_run_inbox_cycle_never_overwrites_a_different_file_with_the_same_name(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    library_root.mkdir()
    existing = library_root / "clip.mp4"
    existing.write_bytes(b"original library bytes -- must survive")
    source = watch_root / "clip.mp4"
    source.write_bytes(b"a completely different file that happens to share a name")

    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    report = run_inbox_cycle(config)

    assert report.moved == ["clip.mp4"]
    assert report.failed == []
    # The pre-existing library file must be untouched.
    assert existing.read_bytes() == b"original library bytes -- must survive"
    # The new file landed under a disambiguated name instead of overwriting it.
    other_files = [p for p in library_root.iterdir() if p.name != "clip.mp4"]
    assert len(other_files) == 1
    assert other_files[0].read_bytes() == b"a completely different file that happens to share a name"


def test_run_inbox_cycle_continues_past_one_failure_to_process_the_rest(tmp_path: Path, monkeypatch) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    bad = watch_root / "bad.mp4"
    bad.write_bytes(b"bad bytes")
    good = watch_root / "good.mp4"
    good.write_bytes(b"good bytes")
    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)

    import videobox_core_engine.media_inbox as media_inbox_module
    real_move = media_inbox_module.shutil.move

    def flaky_move(src, dst):
        if Path(src).name == "bad.mp4":
            raise OSError("simulated disk failure")
        return real_move(src, dst)

    monkeypatch.setattr(media_inbox_module.shutil, "move", flaky_move)
    report = run_inbox_cycle(config)

    assert sorted(report.failed) == ["bad.mp4"]
    assert sorted(report.moved) == ["good.mp4"]
    assert bad.exists()
    assert not good.exists()


def test_watcher_loop_runs_cycles_until_stop_event_is_set(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    stop_event = _FakeStopEvent(stop_after_waits=3)
    reports: list = []

    run_inbox_watcher_loop(
        config,
        stop_event=stop_event,
        interval_seconds=5.0,
        on_cycle=reports.append,
    )

    assert len(reports) == 3
    assert stop_event.last_timeout == 5.0


def test_watcher_loop_runs_zero_cycles_when_already_stopped(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    library_root = tmp_path / "library"
    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    stop_event = _FakeStopEvent(stop_after_waits=0)
    stop_event._set = True
    reports: list = []

    run_inbox_watcher_loop(config, stop_event=stop_event, interval_seconds=1.0, on_cycle=reports.append)

    assert reports == []


def test_watcher_loop_actually_moves_files_across_cycles(tmp_path: Path) -> None:
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    config = MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    stop_event = _FakeStopEvent(stop_after_waits=1)
    (watch_root / "clip.mp4").write_bytes(b"footage")

    run_inbox_watcher_loop(config, stop_event=stop_event, interval_seconds=0.01)

    assert (library_root / "clip.mp4").exists()
    assert not (watch_root / "clip.mp4").exists()


def test_import_media_inbox_asset_copies_the_library_file_into_the_project(tmp_path: Path) -> None:
    """Owner decision (2026-08-07, Task 22): footage collected from the watched
    folder is B-roll, not the narration source.  It must register as
    ``broll_video`` so it reaches analysis, tagging and recommendation the same
    way an uploaded clip does."""
    from videobox_core_engine.local_pipeline import LocalPipelineRunner
    from videobox_domain_models.assets import AssetType
    from videobox_storage.local_project_store import LocalProjectStore

    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "clip.mp4").write_bytes(b"library footage")
    store = LocalProjectStore(tmp_path / "projects")
    pipeline = LocalPipelineRunner(store=store)
    project = store.bootstrap_project("import target")

    asset = import_media_inbox_asset_to_project(
        pipeline, project_id=project.project_id, library_root=library_root, filename="clip.mp4",
    )

    assert asset["asset_type"] == AssetType.BROLL_VIDEO.value
    assert asset["project_id"] == project.project_id
    source = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset["storage_uri"])
    assert source.read_bytes() == b"library footage"
    # The library copy stays in place -- the same footage can be reused
    # across more than one project.
    assert (library_root / "clip.mp4").exists()
    # Registered through the same path uploads use, so the picker has a name to
    # show instead of an opaque asset id, and collected footage stays
    # distinguishable from a manual upload.
    stored = store.get_asset(project_id=project.project_id, asset_id=asset["asset_id"])
    assert stored["metadata"]["title"] == "clip"
    assert stored["metadata"]["media_inbox_filename"] == "clip.mp4"


def test_import_media_inbox_asset_raises_for_a_missing_library_file(tmp_path: Path) -> None:
    from videobox_core_engine.local_pipeline import LocalPipelineRunner
    from videobox_storage.local_project_store import LocalProjectStore

    library_root = tmp_path / "library"
    library_root.mkdir()
    store = LocalProjectStore(tmp_path / "projects")
    pipeline = LocalPipelineRunner(store=store)
    project = store.bootstrap_project("import target")

    with pytest.raises(FileNotFoundError):
        import_media_inbox_asset_to_project(
            pipeline, project_id=project.project_id, library_root=library_root, filename="missing.mp4",
        )


def test_import_media_inbox_asset_rejects_a_path_traversal_filename(tmp_path: Path) -> None:
    """filename must never escape library_root -- the library is always flat
    (run_inbox_cycle writes with `.name` only), so any separator is invalid."""
    from videobox_core_engine.local_pipeline import LocalPipelineRunner
    from videobox_storage.local_project_store import LocalProjectStore

    library_root = tmp_path / "library"
    library_root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"outside the library")
    store = LocalProjectStore(tmp_path / "projects")
    pipeline = LocalPipelineRunner(store=store)
    project = store.bootstrap_project("import target")

    for traversal_filename in ("../secret.txt", "..\\secret.txt", "a/b.mp4", "a\\b.mp4"):
        with pytest.raises(ValueError, match="media_inbox_filename_invalid"):
            import_media_inbox_asset_to_project(
                pipeline, project_id=project.project_id, library_root=library_root, filename=traversal_filename,
            )


def test_imported_originals_are_filed_not_deleted(tmp_path: Path) -> None:
    """The owner needs to see in Drive which footage VideoBox already took.

    Deleting the source told them nothing and, once the watched folder is a
    mirrored Drive folder, deleted the cloud original too. With an archive
    folder configured the original is filed there instead, so the watched
    folder holds exactly what is still waiting.
    """
    watch_root = tmp_path / "drive" / "새 영상"
    watch_root.mkdir(parents=True)
    archive_root = tmp_path / "drive" / "가져옴"
    library_root = tmp_path / "library"
    source = watch_root / "clip.mp4"
    source.write_bytes(b"real footage bytes")

    config = MediaInboxConfig(
        watch_path=watch_root, library_root=library_root, archive_root=archive_root
    )
    report = run_inbox_cycle(config)

    assert report.moved == ["clip.mp4"]
    assert (library_root / "clip.mp4").read_bytes() == b"real footage bytes"
    assert not source.exists(), "watched folder must hold only what is still waiting"
    assert (archive_root / "clip.mp4").read_bytes() == b"real footage bytes"


def test_a_duplicate_is_filed_too_rather_than_deleted(tmp_path: Path) -> None:
    """A duplicate is still the owner's footage; filing it says "already have
    this" without destroying anything."""
    watch_root = tmp_path / "drive" / "새 영상"
    watch_root.mkdir(parents=True)
    archive_root = tmp_path / "drive" / "가져옴"
    library_root = tmp_path / "library"
    library_root.mkdir()
    (library_root / "already-here.mp4").write_bytes(b"same bytes")
    duplicate = watch_root / "duplicate.mp4"
    duplicate.write_bytes(b"same bytes")

    config = MediaInboxConfig(
        watch_path=watch_root, library_root=library_root, archive_root=archive_root
    )
    report = run_inbox_cycle(config)

    assert report.duplicates == ["duplicate.mp4"]
    assert not duplicate.exists()
    assert (archive_root / "duplicate.mp4").read_bytes() == b"same bytes"


def test_without_an_archive_folder_the_old_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Callers that never configured an archive keep moving into the library."""
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    library_root = tmp_path / "library"
    (watch_root / "clip.mp4").write_bytes(b"real footage bytes")

    report = run_inbox_cycle(
        MediaInboxConfig(watch_path=watch_root, library_root=library_root)
    )

    assert report.moved == ["clip.mp4"]
    assert not (watch_root / "clip.mp4").exists()


def test_an_archive_inside_the_watched_folder_is_not_re_scanned(tmp_path: Path) -> None:
    """The scan recurses, so a nested archive would feed itself forever.

    Each pass would see an already-filed original, call it a duplicate, and
    file it again under a new hash-suffixed name -- multiplying the owner's
    footage instead of tidying it.
    """
    watch_root = tmp_path / "drive"
    watch_root.mkdir()
    archive_root = watch_root / "가져옴"
    library_root = tmp_path / "library"
    (watch_root / "clip.mp4").write_bytes(b"real footage bytes")

    config = MediaInboxConfig(
        watch_path=watch_root, library_root=library_root, archive_root=archive_root
    )
    first = run_inbox_cycle(config)
    second = run_inbox_cycle(config)
    third = run_inbox_cycle(config)

    assert first.moved == ["clip.mp4"]
    assert second.moved == [] and second.duplicates == []
    assert third.moved == [] and third.duplicates == []
    assert [path.name for path in sorted(archive_root.iterdir())] == ["clip.mp4"]
