"""자료실의 깨진 파일 이름을 되살린다 (2026-10-02, 점검 후속 A4, 한 번 쓰는 수리 도구).

2026-10-01 점검: 자료실 영상 이름 24개가 `³ìÀ½ 2026-02-07 163617.mp4` 꼴이었다.
윈도우가 cp949로 적은 이름 바이트를 라틴1로 읽은 것이다. 거꾸로 하면 돌아온다.
`name.encode("latin-1").decode("cp949")`.

고치는 것은 셋이 모두 맞을 때뿐이다.
1. 원래 이름에 U+0080~U+00FF 글자가 있다.
2. 라틴1→cp949로 오류 없이 풀린다.
3. 풀린 이름에 한글 음절이 있고 U+0080~U+00FF 글자가 남지 않는다.
그래서 `café.mp3` 같은 진짜 라틴 이름은 건드리지 않는다.

**실행 중인 VideoBox API를 부른다**(기본 http://127.0.0.1:5173). 컨테이너가 쥔 데이터베이스를
호스트에서 직접 열지 않는다. 이름 바꾸기는 화면과 같은 길(`PATCH .../filename`)을 지난다.

    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py            # 미리보기
    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py --apply    # 실제로 바꾸기
    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py --undo <되돌릴 목록.json>

`--apply`는 바꾸기 **전에** 되돌릴 목록을 `artifacts/library-filename-repair/`에 쓴다.
**이 파일은 지우지 않는다.** 원래 이름은 바꾼 뒤에는 어디에도 남지 않아 다시 만들 수 없다
(`docs/development-fast-path.ko.md` §10.16의 "다시 만들 수 있는가" 기준).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:5173"
MEDIA_TYPES = ("broll", "image", "music", "sfx")
#: API가 한 번에 주는 최대 개수(`/api/library/assets`의 `limit` 상한).
PAGE_LIMIT = 500
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVERT_DIR = REPO_ROOT / "artifacts" / "library-filename-repair"

Transport = Callable[[str, str, "dict[str, Any] | None"], "dict[str, Any]"]


def _has_latin1_range(text: str) -> bool:
    return any("\x80" <= ch <= "\xff" for ch in text)


def repaired_name(name: str) -> str | None:
    """되살린 이름. 고칠 것이 아니면 `None`."""

    if not _has_latin1_range(name):
        return None
    try:
        fixed = name.encode("latin-1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if fixed == name or _has_latin1_range(fixed):
        return None
    if not any("가" <= ch <= "힣" for ch in fixed):
        return None
    # cp949(UHC)는 선행 바이트 0xC0~0xC6 뒤에 ASCII 글자가 오면 확장 한글로 읽는다
    # (`Àla`→`픩a`). 진짜 깨진 이름은 모든 한글이 KS X 1001 두 바이트(선행 0xB0~0xC8,
    # 후행 0xA1~0xFE)다. 하나라도 아니면 진짜 라틴 이름으로 보고 건드리지 않는다.
    for ch in fixed:
        if ch.isascii():
            continue
        try:
            pair = ch.encode("cp949")
        except UnicodeEncodeError:
            return None
        if len(pair) != 2 or not (0xB0 <= pair[0] <= 0xC8 and 0xA1 <= pair[1] <= 0xFE):
            return None
    return fixed


def http_transport(base_url: str) -> Transport:
    root = base_url.rstrip("/")

    def send(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = Request(root + path, data=data, method=method, headers=headers)
        with urlopen(request, timeout=30) as response:  # noqa: S310 - 이 컴퓨터의 VideoBox만 부른다
            return json.loads(response.read().decode("utf-8"))

    return send


def plan_repairs(send: Transport) -> list[dict[str, str]]:
    plans: list[dict[str, str]] = []
    for media_type in MEDIA_TYPES:
        page = send("GET", f"/api/library/assets?media_type={media_type}&include_trashed=true&limit={PAGE_LIMIT}", None)
        assets = list(page.get("assets") or [])
        if int(page.get("total") or 0) > len(assets):
            raise SystemExit(f"{media_type} 자산이 {PAGE_LIMIT}개를 넘어 한 번에 다 못 읽었습니다. 아무것도 바꾸지 않고 멈춥니다.")
        for asset in assets:
            if asset.get("origin") != "user":
                continue
            before = str((asset.get("user_metadata") or {}).get("filename") or "")
            after = repaired_name(before)
            if after:
                plans.append({"library_asset_id": str(asset["library_asset_id"]), "media_type": media_type, "before": before, "after": after})
    return plans


def apply_renames(send: Transport, renames: Sequence[Mapping[str, str]], *, key_to: str = "after") -> list[dict[str, str]]:
    """하나씩 바꾼다. 하나가 실패해도 나머지는 계속하고, 실패는 모아서 돌려준다."""

    failures: list[dict[str, str]] = []
    for item in renames:
        target = str(item[key_to])
        path = f"/api/library/assets/{quote(str(item['library_asset_id']), safe='')}/filename"
        try:
            reply = send("PATCH", path, {"filename": target})
        except Exception as exc:  # noqa: BLE001 - 한 줄의 실패가 나머지를 가리면 안 된다. 아래에서 전부 보고한다
            failures.append({**item, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        saved = str(((reply.get("asset") or {}).get("user_metadata") or {}).get("filename") or "")
        if saved != target:
            failures.append({**item, "error": "name_not_saved"})
    return failures


def main(argv: Sequence[str] | None = None, *, send: Transport | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="자료실의 깨진(라틴1로 읽힌) 한국어 파일 이름을 되살린다.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다. 없으면 미리보기만 한다.")
    parser.add_argument("--revert-file", default=None, help="되돌릴 목록을 쓸 자리. 기본은 artifacts/library-filename-repair/.")
    parser.add_argument("--undo", default=None, help="되돌릴 목록 파일을 주면 원래 이름으로 돌린다.")
    parser.add_argument("--force-undo", action="store_true", help="지금 이름이 목록의 바뀐 이름과 달라도(나중에 손으로 바꿨어도) 되돌린다.")
    arguments = parser.parse_args(argv)
    transport = send or http_transport(arguments.base_url)

    if arguments.undo:
        try:
            renamed = json.loads(Path(arguments.undo).read_text(encoding="utf-8"))["renamed"]
            if not isinstance(renamed, list) or not all(
                isinstance(item, dict) and "library_asset_id" in item and "before" in item for item in renamed
            ):
                raise ValueError("renamed 목록 모양이 다릅니다")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"되돌릴 목록을 읽지 못했습니다: {arguments.undo} ({type(exc).__name__}). 아무것도 바꾸지 않았습니다.")
            return 2
        # 나중에 손으로 바꾼 이름을 덮어쓰지 않는다: 지금 이름이 우리가 바꾼 이름(after)일 때만 되돌린다.
        todo: list[Mapping[str, str]] = []
        skipped: list[dict[str, str]] = []
        for item in renamed:
            if arguments.force_undo or "after" not in item:
                todo.append(item)
                continue
            asset_path = f"/api/library/assets/{quote(str(item['library_asset_id']), safe='')}"
            try:
                reply = transport("GET", asset_path, None)
                current = str(((reply.get("asset") or {}).get("user_metadata") or {}).get("filename") or "")
            except Exception as exc:  # noqa: BLE001 - 읽지 못하면 안전하다고 말할 수 없다. 건너뛰고 보고한다
                skipped.append({**item, "error": f"현재 이름을 읽지 못함 ({type(exc).__name__})"})
                continue
            if current != str(item["after"]):
                skipped.append({**item, "error": f"지금 이름이 달라 건너뜀: {current!r}"})
                continue
            todo.append(item)
        failures = apply_renames(transport, todo, key_to="before")
        print(f"되돌림 {len(todo) - len(failures)}/{len(renamed)}")
        for failure in skipped + failures:
            print(f"실패: {failure['library_asset_id']} {failure['error']}")
        if skipped:
            print(f"건너뜀 {len(skipped)}개. 그래도 되돌리려면 --force-undo 를 붙이세요.")
        return 1 if failures or skipped else 0

    plans = plan_repairs(transport)
    for item in plans:
        print(f"{item['library_asset_id']}  {ascii(item['before'])}  ->  {item['after']}")
    print(f"고칠 이름 {len(plans)}개")
    if not arguments.apply:
        print("미리보기만 했습니다. 실제로 바꾸려면 --apply 를 붙이세요.")
        return 0
    if not plans:
        return 0

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    revert_path = Path(arguments.revert_file) if arguments.revert_file else DEFAULT_REVERT_DIR / f"revert-{stamp}.json"
    revert_path.parent.mkdir(parents=True, exist_ok=True)
    # "x": 이미 있는 되돌릴 목록을 **절대 덮어쓰지 않는다.** 앞서 돌린 목록이 원래 이름의
    # 유일한 기록이다. 같은 초에 두 번 돌리거나 같은 --revert-file을 다시 주면 멈춘다.
    try:
        with revert_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"base_url": arguments.base_url, "created_at": stamp, "renamed": plans}, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        print(f"되돌릴 목록이 이미 있습니다: {revert_path}. 덮어쓰지 않고 멈춥니다. 다른 --revert-file을 주세요.")
        return 2
    print(f"되돌릴 목록: {revert_path}  (지우지 마세요)")

    failures = apply_renames(transport, plans)
    print(f"바꿈 {len(plans) - len(failures)}/{len(plans)}")
    for failure in failures:
        print(f"실패: {failure['library_asset_id']} {failure['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
