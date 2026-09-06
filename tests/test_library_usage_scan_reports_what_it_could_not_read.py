"""쓰이는 자산을 "안 쓰는 것"으로 보고할 수 있었다 — 코드리뷰 2026-09-06.

`/api/library/assets/{id}/usage?deep=true`는 **자산을 지우기 전** 안전장치다.
옛 프로젝트가 쓰고 있는 자산을 지우면 되돌릴 수 없어서, 모든 프로젝트를 훑어
"어디에 쓰이는지"를 모은다(그 함수의 머리말이 그렇게 적어 두었다).

그 훑기가 프로젝트 하나에서 예외를 만나면 `except Exception: continue`로 **통째로
삼켰다.** 그러면:

1. 그 프로젝트의 사용처가 조용히 0건이 된다
2. 화면은 "안 쓰는 자산"이라고 말한다
3. 창작자가 쓰고 있는 자산을 지운다
4. 사유가 로그에도 응답에도 없어 나중에 왜 그랬는지 알 수 없다

**삼키는 것 자체는 맞다** -- 프로젝트 하나를 못 읽는다고 나머지 검사를 포기하면
지우기가 통째로 막힌다. 잘못은 **못 읽었다는 사실을 안 알리는 것**이다.

`local_project_store.py`의 `_skipped` 헬퍼가 같은 문제를 이미 그렇게 풀었다 --
그 방식을 따른다: 계속 훑되, 무엇을 못 읽었는지 응답에 담는다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _ingest_one(client: TestClient, tag: str) -> str:
    """실제 자산을 하나 만든다. 없는 자산으로 물으면 404라 아무것도 안 재게 된다.

    **바이트를 시험마다 다르게 한다.** 자료실은 내용 해시로 같은 파일을 하나로
    합치므로, 모든 시험이 같은 바이트를 넣으면 **한 자산을 나눠 쓰게 된다** --
    앞 시험이 만든 프로젝트가 그 자산을 참조한 채로 남아, 이 시험이 기대한
    `usage_scan_incomplete` 대신 `asset_referenced`가 나온다(전체 실행에서만
    실패하는 종류의 사고다).
    """
    response = client.post(
        "/api/library/ingest",
        data={"media_type": "broll", "idempotency_key": f"usage-scan-{tag}"},
        files=[("files", (f"clip-{tag}.mp4", f"not a real video, {tag}".encode(), "video/mp4"))],
    )
    assert response.status_code == 201, response.text
    return str(response.json()["items"][0]["library_asset_id"])


def test_a_project_that_cannot_be_read_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    store = app.state.store
    asset_id = _ingest_one(client, "reported")
    project_id = client.post("/api/projects", json={"name": "훑을 수 없는 프로젝트"}).json()["project_id"]

    original = store.list_assets

    def exploding(**kwargs: object):
        if str(kwargs.get("project_id")) == project_id:
            raise RuntimeError("project index is unreadable")
        return original(**kwargs)  # type: ignore[arg-type]

    store.list_assets = exploding  # type: ignore[assignment]

    response = client.get(f"/api/library/assets/{asset_id}/usage", params={"deep": "true"})

    assert response.status_code == 200, response.text
    body = response.json()
    # **못 읽은 프로젝트가 응답에 남는다.** 이게 없으면 화면은 "안 쓰는 자산"과
    # "확인 못 한 자산"을 구분할 수 없다.
    assert body.get("unreadable_projects"), "못 읽은 프로젝트를 조용히 삼켰다"
    assert project_id in body["unreadable_projects"]


def test_a_clean_scan_says_nothing_was_unreadable(tmp_path: Path) -> None:
    """다 읽었으면 빈 목록이다 -- 화면이 경고를 띄울지 말지 이걸로 가른다."""
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    asset_id = _ingest_one(client, "clean")
    client.post("/api/projects", json={"name": "멀쩡한 프로젝트"})

    response = client.get(f"/api/library/assets/{asset_id}/usage", params={"deep": "true"})

    assert response.status_code == 200, response.text
    assert response.json().get("unreadable_projects") == []


def test_deleting_is_refused_while_a_project_could_not_be_read(tmp_path: Path) -> None:
    """**확인 못 한 것은 "안 쓴다"가 아니다** (코드리뷰 2026-09-06).

    지우기는 깊은 검사의 `locations`만 보고 판단했다. 프로젝트 하나를 못 읽어
    그 사용처가 0건이 된 상태에서도 목록이 비어 있으면 그대로 지웠다 -- 쓰고
    있는 자산이 사라지고, 되돌릴 수 없다.

    막는 쪽이 맞다. 창작자는 다시 눌러 볼 수 있지만, 지워진 자산은 못 되돌린다.
    """
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    store = app.state.store
    asset_id = _ingest_one(client, "refused")
    project_id = client.post("/api/projects", json={"name": "훑을 수 없는 프로젝트"}).json()["project_id"]

    original = store.list_assets

    def exploding(**kwargs: object):
        if str(kwargs.get("project_id")) == project_id:
            raise RuntimeError("project index is unreadable")
        return original(**kwargs)  # type: ignore[arg-type]

    store.list_assets = exploding  # type: ignore[assignment]

    response = client.post(f"/api/library/assets/{asset_id}/trash")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "usage_scan_incomplete"
    assert project_id in detail["unreadable_projects"]
