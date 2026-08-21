"""이름이 다른 두 프로젝트가 같은 식별자를 받고 있었다.

`project_id`는 이름에서 만들어지는데, 만드는 규칙이 `[^a-z0-9]`를 전부 버렸다.
한글은 한 글자도 남지 않는다. 그래서 `관리화면 점검 A`는 `a`가 됐고, `테스트 A`도
`샘플 A`도 `다른 이름 A`도 똑같이 `a`가 됐다. owner는 프로젝트 이름을 한국어로 짓는다.

**부딪치면 조용히 섞였다.** 2026-08-21 실측: 디렉터리는 `mkdir(exist_ok=True)`라
그대로 재사용되고, `projects` 행은 `INSERT OR REPLACE`라 덮어써진다. 결과적으로
먼저 있던 프로젝트는 목록에서 **사라지고**, 그 안의 영상·자산·편집본은 새 프로젝트
것이 된다. 거절도 경고도 없다. 이게 이 파일이 막는 것이다.

한글만 있는 이름은 원래도 `project-<무작위>`로 떨어져서 부딪치지 않았다.
부딪치는 것은 **한글에 영문·숫자가 한 글자라도 섞인 이름**과, 애초에 **같은 이름**이다.
`My First Video`를 두 번 만들어도 같은 일이 일어났다 — 한글만의 문제가 아니었다.

고친 방향: 이름에서 뽑은 부분 뒤에 **짧은 무작위를 항상 붙인다.** 항상 붙이는 이유는
디스크를 먼저 뒤져 보고 붙이는 방식은 두 요청이 같은 순간에 들어오면 여전히 부딪치고,
식별자 만드는 일이 저장소를 알아야 하는 일로 커지기 때문이다.

**옛 프로젝트의 식별자는 건드리지 않는다.** 식별자는 저장 경로이자 DB 키라서, 이미
만들어진 자산과 완성본이 그 주소를 가리키고 있다. 아래 마지막 시험이 그것을 지킨다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from videobox_domain_models.projects import ProjectRecord
from videobox_storage.local_project_store import LocalProjectStore


# 경로에 쓸 수 있는 글자만 남았는지 보는 자. Windows가 거부하는 글자와
# 경로 구분자, 앞뒤 점·공백을 전부 배제한다.
_PATH_SAFE = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")


def _store(tmp_path: Path) -> LocalProjectStore:
    return LocalProjectStore(tmp_path)


def test_korean_names_that_used_to_collapse_to_one_letter_stay_apart(tmp_path: Path) -> None:
    """`테스트 A`·`샘플 A`·`다른 이름 A`가 전부 `a`였다."""
    store = _store(tmp_path)
    names = ["관리화면 점검 A", "테스트 A", "샘플 A", "다른 이름 A"]

    ids = [store.bootstrap_project(name).project_id for name in names]

    assert len(set(ids)) == len(names), f"식별자가 겹친다: {ids}"


def test_korean_only_names_that_share_a_trailing_number_stay_apart(tmp_path: Path) -> None:
    """`제주도 여행 브이로그 2`·`여행 2`·`요리 2`가 전부 `2`였다."""
    store = _store(tmp_path)
    names = ["제주도 여행 브이로그 2", "여행 2", "요리 2"]

    ids = [store.bootstrap_project(name).project_id for name in names]

    assert len(set(ids)) == len(names), f"식별자가 겹친다: {ids}"


@pytest.mark.parametrize("name", ["My First Video", "출근길 브이로그 2", "출근길 브이로그"])
def test_the_same_name_twice_makes_two_separate_projects(tmp_path: Path, name: str) -> None:
    """한글만의 문제가 아니었다. 같은 이름을 두 번 적어도 같은 일이 났다.

    `My First Video`를 두 번 만들면 둘 다 `my-first-video`였다. 한글만 있는 이름은
    옛 규칙에서도 무작위로 떨어져 우연히 멀쩡했지만, 그 우연에 기대지 않는다.
    """
    store = _store(tmp_path)

    first = store.bootstrap_project(name)
    second = store.bootstrap_project(name)

    assert first.project_id != second.project_id
    assert len(store.list_projects()) == 2


def test_a_new_project_never_swallows_an_existing_projects_work(tmp_path: Path) -> None:
    """이 시험이 진짜로 막는 것 — 조용한 병합."""
    store = _store(tmp_path)

    first = store.bootstrap_project("테스트 A")
    footage = store.project_root(first.project_id) / "inputs" / "raw_video" / "owner.mp4"
    footage.write_text("owner footage", encoding="utf-8")

    second = store.bootstrap_project("샘플 A")

    # 새 프로젝트는 제 폴더를 받는다. 남의 촬영본을 물려받지 않는다.
    assert store.project_root(second.project_id) != store.project_root(first.project_id)
    assert not (store.project_root(second.project_id) / "inputs" / "raw_video" / "owner.mp4").exists()

    # 먼저 있던 프로젝트는 이름도 촬영본도 그대로 있다.
    assert footage.read_text(encoding="utf-8") == "owner footage"
    assert store.get_project(project_id=first.project_id)["name"] == "테스트 A"
    assert {row["name"] for row in store.list_projects()} == {"테스트 A", "샘플 A"}


def test_the_identifier_is_safe_to_use_as_a_folder_name(tmp_path: Path) -> None:
    """식별자는 파일 경로에 쓰인다. 경로에 못 쓰는 글자가 들어가면 안 된다."""
    store = _store(tmp_path)
    names = [
        "관리화면 점검 A",
        "그림 만들기 확인",
        "빈 편집판 점검",
        "My First Video",
        "슬래시/역슬래시\\포함",
        "점.만.있는.이름",
        "  앞뒤 공백  ",
        "!!!",
        "CON",  # Windows 예약 장치 이름
        "아주" * 200,  # 경로 길이가 터지지 않아야 한다
    ]

    for name in names:
        project = store.bootstrap_project(name)
        project_id = project.project_id

        assert _PATH_SAFE.match(project_id), f"경로에 못 쓰는 식별자: {project_id!r} ({name!r})"
        assert len(project_id) <= 64, f"식별자가 너무 길다: {project_id!r}"
        # 실제로 그 이름의 폴더가 만들어졌고, 다시 찾아갈 수 있다.
        assert store.project_root(project_id).is_dir()
        assert store.get_project(project_id=project_id)["name"] == name
        assert project.root_storage_uri == f"local://projects/{project_id}"


def test_projects_made_before_this_fix_still_open(tmp_path: Path) -> None:
    """옛 프로젝트의 식별자는 바꾸지 않는다 — 지금 owner 컨테이너에 들어 있는 것들이다.

    옛 규칙이 만들던 모양(`a`, `my-first-video`, `project-2f0cca18`)을 그대로 디스크에
    놓고, 목록·열기·이름 바꾸기가 여전히 되는지 본다.
    """
    store = _store(tmp_path)
    legacy = {
        "a": "관리화면 점검 A",
        "my-first-video": "My First Video",
        "project-2f0cca18": "그림 만들기 확인",
    }
    for project_id, name in legacy.items():
        record = ProjectRecord.create(name=name, project_id=project_id)
        root = store.project_root(project_id)
        store._create_project_layout(root)
        store._bootstrap_database(root / "db" / "project.sqlite", record)

    listed = {row["project_id"]: row["name"] for row in store.list_projects()}
    assert listed == legacy

    for project_id, name in legacy.items():
        opened = store.get_project(project_id=project_id)
        assert opened["name"] == name
        assert opened["root_storage_uri"] == f"local://projects/{project_id}"

    renamed = store.rename_project(project_id="a", name="이름만 바꾼다")
    assert renamed["project_id"] == "a"
    assert store.project_root("a").is_dir()


def test_a_new_project_never_takes_a_legacy_identifier(tmp_path: Path) -> None:
    """옛 프로젝트가 `a`를 쓰고 있는데 새 프로젝트가 또 `a`를 받으면 안 된다."""
    store = _store(tmp_path)
    record = ProjectRecord.create(name="관리화면 점검 A", project_id="a")
    root = store.project_root("a")
    store._create_project_layout(root)
    store._bootstrap_database(root / "db" / "project.sqlite", record)

    fresh = store.bootstrap_project("샘플 A")

    assert fresh.project_id != "a"
    assert {row["name"] for row in store.list_projects()} == {"관리화면 점검 A", "샘플 A"}
