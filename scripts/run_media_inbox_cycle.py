"""Run one media-inbox watch pass (Task 18): scan -> skip unsettled -> verify
hash -> move. Reads the same environment-resolved paths the container/dev
factory would use (VIDEOBOX_MEDIA_INBOX_WATCH_PATH / VIDEOBOX_DATA_ROOT).

`--dry-run` only lists what scan_inbox_candidates() sees; it never touches
disk. Without it, this performs the real hash-verified move.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_path in (
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "provider-interfaces" / "src",
    REPO_ROOT / "packages" / "timeline-schema" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
    REPO_ROOT / "packages" / "capcut-export" / "src",
):
    sys.path.insert(0, str(src_path))

from videobox_core_engine.media_inbox import MediaInboxConfig, run_inbox_cycle, scan_inbox_candidates
from videobox_core_engine.settings import (
    resolve_media_inbox_library_root,
    resolve_media_inbox_reject_path,
    resolve_media_inbox_sorting_enabled,
    resolve_media_inbox_watch_path,
    resolve_owner_audio_library_root,
    resolve_user_library_root,
)
from videobox_storage.library_user_asset_store import LibraryUserAssetStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list candidates only, move nothing")
    args = parser.parse_args()

    watch_path = resolve_media_inbox_watch_path()
    library_root = resolve_media_inbox_library_root()
    print(f"watch_path:   {watch_path}")
    print(f"library_root: {library_root}")

    if watch_path is None:
        print("Watching disabled (VIDEOBOX_MEDIA_INBOX_WATCH_PATH=\"\").")
        return

    # 앱이 배선하는 것과 **같은 설정**을 만든다. 예전에는 여기서 옛 설정을
    # 손으로 만들어서, 이 스크립트로 돌리면 앱과 다르게 동작했다 -- 지금은 넣는
    # 폴더가 영상 말고도 다 받는 한 폴더라 그 차이가 파일을 잃는 차이가 된다.
    sorting = resolve_media_inbox_sorting_enabled()
    user_library_root = resolve_user_library_root()
    owner_audio_library_root = resolve_owner_audio_library_root()
    reject_root = resolve_media_inbox_reject_path(watch_path) if sorting else None
    config = MediaInboxConfig(
        watch_path=watch_path,
        library_root=library_root,
        archive_root=watch_path.parent / "자산화_완료",
        copy_only=True,
        ingest_store=LibraryUserAssetStore(user_library_root),
        media_type="broll",
        sort_by_content=sorting,
        sorted_library_roots={
            "broll": library_root,
            "image": user_library_root,
            "music": owner_audio_library_root / "music",
            "sfx": owner_audio_library_root / "sfx",
        }
        if sorting
        else {},
        reject_root=reject_root,
    )
    print(f"sort_by_content: {sorting}")
    print(f"reject_root:  {reject_root}")

    if args.dry_run:
        candidates = scan_inbox_candidates(
            watch_path, accepted_extensions=None if sorting else config.accepted_extensions
        )
        print(f"{len(candidates)} candidate file(s):")
        for candidate in candidates:
            print(f"  {candidate}")
        return

    report = run_inbox_cycle(config)
    print(f"moved:      {report.moved}")
    print(f"duplicates: {report.duplicates}")
    print(f"skipped:    {report.skipped}")
    print(f"rejected:   {report.rejected}")
    print(f"failed:     {report.failed}")


if __name__ == "__main__":
    main()
