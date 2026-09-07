"""새 세션에서 유진에게 사진을 시켜 본다 — 실기 확인.

**유진 시험은 반드시 새 세션에서.** 앞 요청이 세션 상태를 바꿔 놓아서 같은
이유로 두 번 틀렸다. 여기서는 매번 빈 편집판을 새로 연다.

시험이 아니라 **도는 컨테이너에 실제로 말을 거는 것**이다. 층별 시험이 초록인데
기능이 안 도는 것을 2026-09-06에 두 번 겪었다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from drive import BASE, call  # noqa: E402

INSTRUCTIONS = [
    ("사진을 화면 위에 얹기", "1번 장면 오른쪽 위에 사진 하나 작게 얹어줘"),
    ("사진 움직임 고르기", "1번 장면 사진을 천천히 다가가게 해줘"),
    ("사진을 장면으로 깔기", "1번 장면에 바다 사진 깔아줘"),
]


def fresh_session(project_id: str) -> str | None:
    code, body = call("POST", f"/api/projects/{project_id}/editing-sessions/blank")
    if code != 201:
        print(f"!! 빈 편집판을 못 열었다: {code} {json.dumps(body, ensure_ascii=False)[:200]}")
        return None
    return str(body.get("session_id") or body.get("editing_session", {}).get("session_id") or "")


def main() -> int:
    project_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not project_id:
        code, body = call("GET", "/api/projects")
        projects = body.get("projects") or []
        if not projects:
            print("!! 프로젝트가 없다")
            return 1
        project_id = str(projects[0]["project_id"])
    print(f"프로젝트: {project_id}\n")

    failures = 0
    for label, instruction in INSTRUCTIONS:
        session_id = fresh_session(project_id)
        if not session_id:
            failures += 1
            continue
        code, body = call(
            "POST",
            f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals",
            {"instruction": instruction},
            timeout=600.0,
        )
        operations = ((body.get("diff") or {}).get("operations")) or []
        intents = [str(item.get("intent") or "") for item in operations]
        reply = str(body.get("reply_text") or body.get("detail") or "")
        mark = "  " if code == 201 and operations else "!!"
        if mark == "!!":
            failures += 1
        print(f"{mark} {label}")
        print(f"     시킨 말: {instruction}")
        print(f"     응답 {code}, 편집 {len(operations)}개: {intents}")
        print(f"     유진: {reply[:180]}")
        if operations:
            print(f"     첫 편집: {json.dumps(operations[0], ensure_ascii=False)[:260]}")
        print()

    print(f"{len(INSTRUCTIONS) - failures}/{len(INSTRUCTIONS)} 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
