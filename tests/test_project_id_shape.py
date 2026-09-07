"""`project_id`에 `%2e%2e`가 라우터까지 통과하던 것 (코드리뷰 2026-09-07).

`project_root(project_id)`가 모양 검사 없이 `projects_root / "projects" /
project_id`를 그대로 돌려줬다. `project_id=".."`는 `projects/`(부모 폴더)를
가리켜, 프로젝트 삭제(`DELETE /api/projects/{id}`)와 겹치면 그 폴더 전체가
`shutil.rmtree`될 위험이 있었다 -- `docs/handoffs/2026-09-07-full-audit-docs-tests-boundaries.ko.md`
§1-4. `local_project_store.py`의 `_PROJECT_ID_SHAPE` 화이트리스트
(`^[A-Za-z0-9_-]+$`)로 막는다. `§1-1`이 쓰는 `store.projects_root` 봉쇄의
심층 방어이기도 하다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "projects"))


def test_traversal_project_id_is_rejected_without_touching_the_parent_folder(
    client: TestClient, tmp_path: Path,
) -> None:
    """**빈 `projects_root`에서는 이 결함이 안 보인다.** `project_root("..")`가
    가리키는 `projects/`(부모 폴더)가 아직 없으면 `delete_project_permanently`의
    "존재하는지" 확인이 우연히 걸러 준다 -- 실제 사고 시나리오는 프로젝트가
    이미 여럿 있는 살아 있는 시스템이다. 그래서 프로젝트를 하나 실제로 만들어
    `projects_root/projects`가 존재하는 상태를 먼저 만든다.

    URL의 `..`는 httpx가 보내기 전에 조용히 지워 버려(`/api/projects/..`가
    `/api`가 된다) 우리 코드를 아예 안 거친다 -- 그래서 percent-encoding
    (`%2e%2e`)을 쓴다.
    """
    other_project_id = client.post("/api/projects", json={"name": "살아남아야 하는 프로젝트"}).json()["project_id"]
    projects_directory = tmp_path / "projects" / "projects"
    assert projects_directory.is_dir()

    response = client.delete("/api/projects/%2e%2e", params={"confirm": "true"})

    assert response.status_code in (404, 422), response.text
    # 부모 폴더가 통째로 지워지지 않았다 -- 다른 프로젝트가 그대로 남아 있다.
    assert projects_directory.is_dir()
    assert (projects_directory / other_project_id).is_dir()


def test_project_root_refuses_a_parent_directory_escape(tmp_path: Path) -> None:
    """저장소 함수를 직접 재는 단위 시험 -- 라우팅 계층을 거치지 않아도 막힌다."""
    store = LocalProjectStore(tmp_path / "projects")
    with pytest.raises(KeyError):
        store.project_root("..")
    with pytest.raises(KeyError):
        store.delete_project_permanently(project_id="..")
    # projects_root의 부모(= tmp_path)는 손대지 않은 채로 남아 있다.
    assert tmp_path.is_dir()


def test_a_normal_project_id_still_works(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("정상 프로젝트")
    assert store.project_root(project.project_id).is_dir()
