"""자료실에서 자산 하나를 보는 데 1.67초가 걸렸다 — 실측 2026-09-05.

owner: "영상 만들 때 어느 화면이 느린지 다시 재봐".

재 보니 `/api/library/assets/{id}/usage` **한 요청이 1.67초**였다(응답은
375바이트). 원인은 그 요청이 **모든 프로젝트를 훑는 것**이다 -- 프로젝트마다
자산 목록·편집 세션 전부·타임라인을 읽는다. 9p 마운트라 파일 하나하나가 비싸고,
**프로젝트가 늘수록 그대로 늘어난다**.

그런데 이 전수 검사를 없앨 수는 없다. **같은 검사가 자산을 지우기 전 안전장치**
로도 쓰인다(`trash_library_asset`) -- 옛 프로젝트에서 쓰고 있는 자산을 지우면
되돌릴 수 없다.

그래서 나눈다(owner 승인 2026-09-05):

| 언제 | 무엇을 |
|---|---|
| 화면이 "어디에 쓰이나" 물을 때 | **빠른 검사**(명시적 참조만) |
| 지우기 전 | **전수 검사**(옛 프로젝트까지 훑는다) |
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_the_screen_asks_a_cheap_question_by_default(tmp_path: Path) -> None:
    """기본 요청은 모든 프로젝트를 훑지 않는다."""
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    scanned: list[str] = []

    store = app.state.store
    original = store.list_editing_sessions

    def counting(**kwargs: object):
        scanned.append(str(kwargs.get("project_id")))
        return original(**kwargs)  # type: ignore[arg-type]

    store.list_editing_sessions = counting  # type: ignore[assignment]

    response = client.get("/api/library/assets/user_missing/usage")

    # 없는 자산이든 있는 자산이든, **기본 요청은 프로젝트를 훑지 않는다.**
    assert response.status_code in {200, 404}
    assert scanned == [], f"기본 요청이 프로젝트를 훑었다: {scanned}"


def test_the_deep_question_is_still_available_for_deletion(tmp_path: Path) -> None:
    """지우기 전 검사는 그대로 깊게 본다 -- 그 자리를 없애면 자산을 잃는다."""
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.get("/api/library/assets/user_missing/usage", params={"deep": "true"})

    assert response.status_code in {200, 404}
