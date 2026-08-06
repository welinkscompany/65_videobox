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
from videobox_core_engine.settings import resolve_media_inbox_library_root, resolve_media_inbox_watch_path


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

    if args.dry_run:
        candidates = scan_inbox_candidates(watch_path)
        print(f"{len(candidates)} candidate file(s):")
        for candidate in candidates:
            print(f"  {candidate}")
        return

    report = run_inbox_cycle(MediaInboxConfig(watch_path=watch_path, library_root=library_root))
    print(f"moved:      {report.moved}")
    print(f"duplicates: {report.duplicates}")
    print(f"skipped:    {report.skipped}")
    print(f"failed:     {report.failed}")


if __name__ == "__main__":
    main()
