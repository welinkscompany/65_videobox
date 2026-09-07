"""제목을 바꿀 길이 아예 없었다.

만들 때 적은 이름이 끝이었고, 유진이 제목을 추천해도 넣을 자리가 없었다
(승인된 사람 게이트 `제목 추천 -> [사람: 선택]`,
`docs/decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`).

경계 하나를 여기서 못박는다: **이름만 바뀌고 `project_id`와 저장 위치는 그대로다.**
그 둘은 디스크 경로이자 이미 만들어진 자산·완성본이 가리키는 주소라, 제목을 고칠
때마다 따라 움직이면 지난 결과물이 통째로 미아가 된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> LocalProjectStore:
    return LocalProjectStore(tmp_path)


def test_renaming_changes_the_display_name_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("첫 영상")
    root_before = store.project_root(project.project_id)

    renamed = store.rename_project(project_id=project.project_id, name="출근길 브이로그")

    assert renamed["name"] == "출근길 브이로그"
    assert renamed["project_id"] == project.project_id
    assert renamed["root_storage_uri"] == project.root_storage_uri
    assert store.project_root(project.project_id) == root_before
    assert (root_before / "db" / "project.sqlite").is_file()


def test_the_new_name_is_what_every_later_read_returns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("첫 영상")

    store.rename_project(project_id=project.project_id, name="출근길 브이로그")

    assert store.get_project(project_id=project.project_id)["name"] == "출근길 브이로그"
    listed = {item["project_id"]: item for item in store.list_projects()}
    assert listed[project.project_id]["name"] == "출근길 브이로그"


def test_renaming_keeps_the_archived_state_it_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("보관한 영상")
    store.archive_project(project_id=project.project_id)

    renamed = store.rename_project(project_id=project.project_id, name="보관한 브이로그")

    assert renamed["status"] == "archived"


def test_surrounding_blanks_are_trimmed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("첫 영상")

    renamed = store.rename_project(project_id=project.project_id, name="  출근길 브이로그  ")

    assert renamed["name"] == "출근길 브이로그"


def test_a_blank_name_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.bootstrap_project("첫 영상")

    with pytest.raises(ValueError):
        store.rename_project(project_id=project.project_id, name="   ")

    assert store.get_project(project_id=project.project_id)["name"] == "첫 영상"


def test_renaming_a_nonexistent_project_fails_safely(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.rename_project(project_id="does-not-exist", name="아무 이름")


def test_api_rename_reaches_every_screen_that_reads_the_name(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "첫 영상"}).json()["project_id"]

    renamed = client.patch(f"/api/projects/{project_id}", json={"name": "출근길 브이로그"})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "출근길 브이로그"
    # 화면은 이름을 세 곳에서 읽는다. 하나라도 옛 이름을 돌려주면 owner는
    # 바뀌지 않았다고 본다.
    assert client.get(f"/api/projects/{project_id}").json()["name"] == "출근길 브이로그"
    listed = {item["project_id"]: item for item in client.get("/api/projects").json()["projects"]}
    assert listed[project_id]["name"] == "출근길 브이로그"
    summary = client.get(f"/api/projects/{project_id}/workspace-summary")
    assert summary.status_code == 200
    assert summary.json()["display_name"] == "출근길 브이로그"


def test_api_rename_of_a_nonexistent_project_is_a_404(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))

    response = client.patch("/api/projects/does-not-exist", json={"name": "아무 이름"})

    assert response.status_code == 404


def test_api_rename_refuses_an_empty_name(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "첫 영상"}).json()["project_id"]

    assert client.patch(f"/api/projects/{project_id}", json={"name": ""}).status_code == 422
    assert client.patch(f"/api/projects/{project_id}", json={"name": "   "}).status_code == 400
    assert client.get(f"/api/projects/{project_id}").json()["name"] == "첫 영상"


def test_api_rename_refuses_unknown_fields(tmp_path: Path) -> None:
    # `project_id`나 `status`를 같이 보내면 조용히 무시하지 않고 거절한다 --
    # 무시하면 부른 쪽은 바뀐 줄 안다.
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "첫 영상"}).json()["project_id"]

    response = client.patch(f"/api/projects/{project_id}", json={"name": "새 이름", "status": "archived"})

    assert response.status_code == 422
    assert client.get(f"/api/projects/{project_id}").json()["name"] == "첫 영상"
