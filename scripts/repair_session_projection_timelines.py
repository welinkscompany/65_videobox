"""세션 투영 클립이 박힌 편집판을 찾고, 승인 뒤 걷어 낸다 (2026-10-08 계획 H Task 5, 한 번 쓰는 수리 도구).

2026-09-20 되돌린 커밋이 materialize 결과(`session-overlay-…`·`session-broll-…`)를 저장된
편집판 `timeline_NNN.json`의 `tracks`에 박아 넣었다. 지금 코드(Task 4)는 읽을 때 그 클립을
건너뛰므로 **고치지 않아도 동작한다.** 남은 것은 파일 속 쓰레기다. 지우는 것은 대표님 실제
프로젝트 데이터를 바꾸는 일이라 **owner 결정 뒤에만** 한다. 그래서 기본은 미리보기다.

트랙은 그대로 두고 `clips`만 비운다(트랙 수가 같아 DB `summary_json`이 안 바뀐다).

    .venv/Scripts/python.exe scripts/repair_session_projection_timelines.py                          # 미리보기(기본, 아무것도 안 쓴다)
    .venv/Scripts/python.exe scripts/repair_session_projection_timelines.py --apply --project <id>   # 한 프로젝트만 고치기
    .venv/Scripts/python.exe scripts/repair_session_projection_timelines.py --undo <목록.json>       # 되돌리기

`--apply`는 `--project` 없이는 거절한다. 순서는 (1) 되돌릴 목록(고치기 전/후 해시, 백업 경로)을
`artifacts/timeline-projection-repair/<UTC>.json`에 먼저 쓰고 fsync (2) 같은 폴더에
`<이름>.bak-h-<UTC>` 복사 (3) 임시 파일에 쓰고 `os.replace`로 바꿔 끼우기(원자적)다.
`--undo`는 지금 파일 해시가 고친 직후 해시와 같을 때만 백업으로 되돌린다. 그 뒤 누가 손댔으면
멈춘다(`--force-undo`로만 덮는다).

**되돌릴 목록은 지우지 않는다.** 원래 내용은 고친 뒤 이 목록·백업 말고는 다시 만들 수 없다
(`docs/development-fast-path.ko.md` §10.16의 "다시 만들 수 있는가" 기준).

주의: 실행 중인 컨테이너(API)가 같은 파일을 읽고 쓴다. **적용 전에 화면에서 이 프로젝트를
편집 중이 아닌지 확인**하고, 가능하면 스택을 멈춘 뒤 적용한다. 이 도구는 데이터베이스를 열지
않는다(파일만 쓴다). 같은 폴더에 `*.lock` 표지가 있으면 거절한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for _source_path in (
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
):
    if str(_source_path) not in sys.path:
        sys.path.insert(0, str(_source_path))

from videobox_core_engine.composition_plan import (  # noqa: E402
    is_session_projection_clip,
    without_session_projection_clips,
)
from videobox_core_engine.settings import resolve_projects_root  # noqa: E402

DEFAULT_REVERT_DIR = REPO_ROOT / "artifacts" / "timeline-projection-repair"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _projection_clip_ids(payload: object) -> list[str]:
    tracks = payload.get("tracks") if isinstance(payload, dict) else None
    ids: list[str] = []
    for track in tracks if isinstance(tracks, list) else []:
        if not isinstance(track, dict):
            continue
        for clip in track.get("clips") or []:
            if isinstance(clip, dict) and is_session_projection_clip(clip):
                ids.append(str(clip.get("clip_id")))
    return ids


def strip_projection_clips(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """투영 클립만 뺀 사본과 뺀 개수. 트랙·다른 칸은 그대로다."""

    removed = len(_projection_clip_ids(payload))
    return {**payload, "tracks": without_session_projection_clips(payload.get("tracks"))}, removed


def find_contaminated_timelines(projects_dir: Path) -> list[dict[str, Any]]:
    """읽기만 한다. 읽지 못하는 파일은 건너뛴다."""

    found: list[dict[str, Any]] = []
    if not projects_dir.is_dir():
        return found
    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        timelines = project_dir / "timelines"
        if not timelines.is_dir():
            continue
        for path in sorted(timelines.glob("timeline_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            ids = _projection_clip_ids(payload)
            if not ids:
                continue
            counts = Counter(ids)
            found.append({
                "project_id": project_dir.name,
                "timeline_file": path.name,
                "projection_clip_count": len(ids),
                "duplicate_clip_ids": sorted(clip_id for clip_id, n in counts.items() if n > 1),
            })
    return found


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _print_preview(found: Sequence[dict[str, Any]]) -> None:
    for item in found:
        print(
            f"{item['project_id']}  {item['timeline_file']}  "
            f"투영 {item['projection_clip_count']} · 겹친 id {len(item['duplicate_clip_ids'])}"
        )
    print(f"오염된 편집판 {len(found)}개")


def _undo(arguments: argparse.Namespace) -> int:
    try:
        record = json.loads(Path(arguments.undo).read_text(encoding="utf-8"))
        entries = record["repaired"]
        if not isinstance(entries, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("timeline_path", "backup_path", "before_sha256", "after_sha256"))
            for e in entries
        ):
            raise ValueError("repaired 목록 모양이 다릅니다")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"되돌릴 목록을 읽지 못했습니다: {arguments.undo} ({type(exc).__name__}). 아무것도 바꾸지 않았습니다.")
        return 2
    problems = 0
    restored = 0
    for entry in entries:
        target = Path(entry["timeline_path"])
        backup = Path(entry["backup_path"])
        try:
            current = _sha256_bytes(target.read_bytes())
            saved = backup.read_bytes()
        except OSError as exc:
            print(f"건너뜀: {target} 또는 백업을 읽지 못함 ({type(exc).__name__})")
            problems += 1
            continue
        if _sha256_bytes(saved) != entry["before_sha256"]:
            print(f"건너뜀: 백업이 목록의 원래 해시와 다릅니다: {backup}")
            problems += 1
            continue
        if current == entry["before_sha256"]:
            print(f"이미 원래 상태: {target}")
            restored += 1
            continue
        if current != entry["after_sha256"] and not arguments.force_undo:
            print(f"건너뜀: 고친 뒤에 파일이 또 바뀌었습니다: {target}. 그래도 되돌리려면 --force-undo 를 붙이세요.")
            problems += 1
            continue
        try:
            _atomic_write(target, saved)
        except OSError as exc:
            print(f"실패: {target} ({type(exc).__name__}: {exc})")
            problems += 1
            continue
        restored += 1
        print(f"되돌림: {target}")
    print(f"되돌림 {restored}/{len(entries)}")
    return 1 if problems else 0


def _apply(arguments: argparse.Namespace, projects_dir: Path, found: Sequence[dict[str, Any]], now: datetime | None) -> int:
    project_id = arguments.project
    targets = [item for item in found if item["project_id"] == project_id]
    if not (projects_dir / project_id).is_dir():
        print(f"프로젝트를 찾지 못했습니다: {project_id}. 아무것도 바꾸지 않았습니다.")
        return 2
    if not targets:
        print(f"{project_id}에는 고칠 편집판이 없습니다.")
        return 0
    timelines_dir = projects_dir / project_id / "timelines"
    locks = sorted(timelines_dir.glob("*.lock")) + sorted((projects_dir / project_id).glob("*.lock"))
    if locks:
        print(f"쓰는 중일 수 있어 멈춥니다(잠금 표지 {locks[0]}). 아무것도 바꾸지 않았습니다.")
        return 2

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    plans: list[dict[str, Any]] = []
    for item in targets:
        path = timelines_dir / item["timeline_file"]
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            print(f"읽지 못했습니다: {path} ({type(exc).__name__}). 아무것도 바꾸지 않았습니다.")
            return 2
        cleaned, removed = strip_projection_clips(payload)
        data = json.dumps(cleaned, ensure_ascii=False, indent=2).encode("utf-8")
        plans.append({
            "timeline_path": str(path), "backup_path": str(path.with_name(f"{path.name}.bak-h-{stamp}")),
            "before_sha256": _sha256_bytes(raw), "after_sha256": _sha256_bytes(data),
            "removed_clip_count": removed, "_raw": raw, "_data": data,
        })

    revert_dir = Path(arguments.revert_dir) if arguments.revert_dir else DEFAULT_REVERT_DIR
    revert_path = revert_dir / f"{stamp}.json"
    record = {"project_id": project_id, "created_at": stamp,
              "repaired": [{k: v for k, v in plan.items() if not k.startswith("_")} for plan in plans]}
    try:
        revert_dir.mkdir(parents=True, exist_ok=True)
        # "x": 이미 있는 되돌릴 목록을 절대 덮어쓰지 않는다. 앞서 돌린 목록이 원래 내용의 유일한 기록이다.
        with revert_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        print(f"되돌릴 목록이 이미 있습니다: {revert_path}. 덮어쓰지 않고 멈춥니다.")
        return 2
    except OSError as exc:
        print(f"되돌릴 목록을 쓰지 못해 멈춥니다 ({type(exc).__name__}). 아무것도 바꾸지 않았습니다.")
        return 1
    print(f"되돌릴 목록: {revert_path}  (지우지 마세요)")

    failures = 0
    for plan in plans:
        path = Path(plan["timeline_path"])
        backup = Path(plan["backup_path"])
        try:
            if backup.exists():
                raise FileExistsError(f"백업이 이미 있습니다: {backup}")
            shutil.copy2(path, backup)
            if _sha256_bytes(backup.read_bytes()) != plan["before_sha256"]:
                raise OSError("백업이 원본과 다릅니다")
            if _sha256_bytes(path.read_bytes()) != plan["before_sha256"]:
                raise OSError("읽은 뒤 파일이 바뀌었습니다(쓰는 중일 수 있음)")
            _atomic_write(path, plan["_data"])
        except OSError as exc:
            failures += 1
            print(f"실패: {path} ({type(exc).__name__}: {exc}). 원본은 그대로입니다.")
            continue
        print(f"고침: {path}  투영 {plan['removed_clip_count']}개 제거, 백업 {backup.name}")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="저장된 편집판에 박힌 세션 투영 클립을 찾고(기본), 승인 뒤 걷어 낸다.")
    parser.add_argument("--projects-dir", default=None, help="기본은 저장 루트의 runtime/projects.")
    parser.add_argument("--apply", action="store_true", help="실제로 고친다. --project 가 꼭 필요하다.")
    parser.add_argument("--project", default=None, help="고칠 프로젝트 id(--apply 와 함께).")
    parser.add_argument("--revert-dir", default=None, help="되돌릴 목록을 쓸 폴더. 기본은 artifacts/timeline-projection-repair/.")
    parser.add_argument("--undo", default=None, help="되돌릴 목록 파일을 주면 백업으로 되돌린다.")
    parser.add_argument("--force-undo", action="store_true", help="고친 뒤 파일이 또 바뀌었어도 되돌린다.")
    arguments = parser.parse_args(argv)

    if arguments.undo:
        return _undo(arguments)

    if arguments.apply and not arguments.project:
        print("--apply 는 --project <id> 와 함께만 쓸 수 있습니다. 아무것도 바꾸지 않았습니다.")
        return 2
    projects_dir = Path(arguments.projects_dir) if arguments.projects_dir else resolve_projects_root() / "runtime" / "projects"
    if not projects_dir.is_dir():
        print(f"프로젝트 폴더를 찾지 못했습니다: {projects_dir}")
        return 2

    found = find_contaminated_timelines(projects_dir)
    if not arguments.apply:
        _print_preview(found)
        print("미리보기만 했습니다. 고치려면 --apply --project <id> 를 붙이세요.")
        return 0
    return _apply(arguments, projects_dir, found, now)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
