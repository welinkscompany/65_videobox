"""진짜 FastAPI + 진짜 저장소로 e2e 시험 프로젝트를 띄운다 (2026-10-08 계획 H Task 1).

임시 데이터 폴더에만 시드하고, 실제 DB/스냅샷 환경 변수는 비운다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # scripts/ 형제 모듈 import (경로 준비는 e2e_editor_fixture가 한다)

from scripts.e2e_editor_fixture import seed_editor_fixtures  # noqa: E402


def _camel(ids: dict[str, str]) -> dict[str, str]:
    return {"projectId": ids["project_id"], "sessionId": ids["session_id"], "timelineId": ids["timeline_id"]}


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixture-file", required=True)
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args(argv)

    # 실제 데이터에 닿지 않게 환경을 비운다.
    os.environ.pop("VIDEOBOX_DATABASE_URL", None)
    os.environ.pop("VIDEOBOX_SNAPSHOT_ROOT", None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    data_root = Path(args.data_root) if args.data_root else REPO_ROOT / "apps" / "web" / "test-results" / "real-flow-data" / stamp
    data_root = data_root.resolve()
    os.environ["VIDEOBOX_DATA_ROOT"] = str(data_root)

    from videobox_core_engine.settings import DEFAULT_PROJECTS_ROOT

    real_root = Path(DEFAULT_PROJECTS_ROOT)
    if _is_under(data_root, real_root):
        raise SystemExit("실제 데이터 폴더에는 시드하지 않습니다")

    ids = seed_editor_fixtures(projects_root=data_root / "projects", media_dir=data_root / "media")
    fixture_file = Path(args.fixture_file)
    fixture_file.parent.mkdir(parents=True, exist_ok=True)
    fixture_file.write_text(
        json.dumps({"clean": _camel(ids["clean"]), "duplicatedOverlays": _camel(ids["duplicated_overlays"])}, indent=2),
        encoding="utf-8",
    )

    import uvicorn
    from videobox_api.main import create_app
    from videobox_storage.media_library_store import MediaLibraryStore

    app = create_app(
        projects_root=data_root / "projects",
        media_library_store=MediaLibraryStore(data_root / "library"),
        media_analysis_poll_interval_seconds=3600,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
