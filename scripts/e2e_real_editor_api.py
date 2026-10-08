"""진짜 FastAPI + 진짜 저장소로 e2e 시험 프로젝트를 띄운다 (2026-10-08 계획 H Task 1).

임시 데이터 폴더에만 시드하고, 실제 DB/스냅샷 환경 변수는 비운다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # scripts/ 형제 모듈 import (경로 준비는 e2e_editor_fixture가 한다)

from scripts.e2e_editor_fixture import seed_editor_fixtures  # noqa: E402


def _camel(ids: dict[str, str]) -> dict[str, str]:
    return {"projectId": ids["project_id"], "sessionId": ids["session_id"], "timelineId": ids["timeline_id"]}


SAFE_ENV_NAMES = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "USERPROFILE",
    "LOCALAPPDATA", "APPDATA", "HOME", "HOMEDRIVE", "HOMEPATH", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "OS", "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8", "NODE", "FFMPEG_PATH",
    "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_WEB_PORT", "PLAYWRIGHT_FAKE_API_PORT",
    "VIDEOBOX_E2E_FIXTURE_FILE", "VIDEOBOX_E2E_PROTECT_ROOT", "VIDEOBOX_LOG_LEVEL",
})
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "KEY")


def build_child_env(parent_env: dict[str, str], *, data_root: Path | None = None) -> dict[str, str]:
    """허용 목록으로만 자식 환경을 만든다. 나머지 VIDEOBOX_*와 비밀 이름은 전부 버린다."""
    child: dict[str, str] = {}
    for name, value in parent_env.items():
        upper = name.upper()
        if upper not in SAFE_ENV_NAMES or any(marker in upper for marker in _SECRET_MARKERS):
            continue
        child[name] = value
    if data_root is not None:
        child["VIDEOBOX_DATA_ROOT"] = str(data_root)
    return child


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _assert_not_real_root(data_root: Path, real_roots: list[Path], allowed_parents: list[Path]) -> None:
    """실제 폴더와 같거나 그 안이거나 그 상위이면 거절하고, 허용 위치(임시 폴더 등) 밖이어도 거절한다."""
    resolved = Path(data_root).resolve()
    for real in real_roots:
        if _is_under(resolved, real) or _is_under(real, resolved):
            raise SystemExit("실제 데이터 폴더에는 시드하지 않습니다")
    if not any(_is_under(resolved, parent) and resolved != Path(parent).resolve() for parent in allowed_parents):
        raise SystemExit("시험 데이터는 임시 폴더나 real-flow-data 아래에만 만듭니다")


def _clean_old_runs(real_flow_data: Path, max_age_sec: float = 86400.0) -> None:
    """real-flow-data 안의 하루 지난 실행 폴더만 지운다. 다른 곳은 건드리지 않는다."""
    if real_flow_data.name != "real-flow-data" or not real_flow_data.is_dir():
        return
    now = time.time()
    for child in real_flow_data.iterdir():
        if child.is_dir() and now - child.stat().st_mtime > max_age_sec:
            shutil.rmtree(child, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixture-file", required=True)
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args(argv)

    # 실제 데이터에 닿지 않게: 소유자의 VIDEOBOX_DATA_ROOT는 덮어쓰기 전에 읽어 보호 대상에 넣는다.
    # (러너 JS가 이미 걸러서 VIDEOBOX_DATA_ROOT는 못 오고, 소유자 값은 VIDEOBOX_E2E_PROTECT_ROOT로 온다.)
    owner_data_root = os.environ.get("VIDEOBOX_DATA_ROOT", "").strip()
    protected_roots = [Path(v) for v in (owner_data_root, os.environ.get("VIDEOBOX_E2E_PROTECT_ROOT", "").strip()) if v]
    safe_env = build_child_env(dict(os.environ))
    os.environ.clear()
    os.environ.update(safe_env)

    from videobox_core_engine.settings import DEFAULT_PROJECTS_ROOT, resolve_user_library_root

    real_flow_data = REPO_ROOT / "apps" / "web" / "test-results" / "real-flow-data"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    data_root = (Path(args.data_root) if args.data_root else real_flow_data / stamp).resolve()
    real_roots = [Path(DEFAULT_PROJECTS_ROOT), Path(DEFAULT_PROJECTS_ROOT).parent / "videobox-user-library",
                  resolve_user_library_root(), REPO_ROOT / "projects", REPO_ROOT / "artifacts"]
    for protected in protected_roots:
        real_roots += [protected, protected / "videobox-user-library"]
    _assert_not_real_root(data_root, real_roots, [Path(tempfile.gettempdir()), real_flow_data])
    _clean_old_runs(real_flow_data)
    os.environ["VIDEOBOX_DATA_ROOT"] = str(data_root)

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
