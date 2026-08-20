"""글꼴 고르기 화면이 부르는 길.

목록·즐겨찾기·최근을 **한 번에** 돌려준다. 화면이 세 번 나눠 부르면 그중
하나만 실패해도 owner에게는 아무것도 안 보인다 -- 이 저장소가 실제로 겪은
실패 방식이라 부르는 횟수를 하나로 줄였다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.caption_fonts import (
    CAPTION_FONTS,
    default_caption_font_family,
    installed_caption_fonts,
)


@pytest.fixture(name="client")
def _client(tmp_path) -> TestClient:
    # 사용자 서랍은 `projects_root`의 **부모** 아래에 잡힌다. `tmp_path`를 그대로
    # 넘기면 그 부모가 pytest 세션 공용 폴더라서 앞선 시험이 남긴 즐겨찾기가
    # 그대로 보인다. 한 겹 내려서 시험마다 따로 쓰게 한다.
    return TestClient(create_app(projects_root=tmp_path / "projects"))


def test_caption_font_list_is_what_this_machine_can_actually_draw(client: TestClient) -> None:
    """화면과 이 길이 같은 사실을 말해야 한다.

    목록 전체가 아니라 **글꼴 파일이 있는 것만** 나간다. 개발기에는 apt가 넣어
    주는 셋이 없으므로 여기서 목록보다 짧을 수 있다 -- 컨테이너에서는 전부 있다.
    """
    response = client.get("/api/caption-fonts")

    assert response.status_code == 200
    body = response.json()
    assert [font["family"] for font in body["fonts"]] == [
        font.family for font in installed_caption_fonts()
    ]
    assert body["fonts"], "고를 것이 하나도 없으면 자막을 만들 수 없다"
    assert {font["family"] for font in body["fonts"]} <= {font.family for font in CAPTION_FONTS}
    assert body["default_family"] == default_caption_font_family()
    assert body["default_family"] in {font["family"] for font in body["fonts"]}
    assert body["favorites"] == []
    assert body["recents"] == []
    assert all(font["label"] and font["group"] for font in body["fonts"])


def test_font_favourite_and_recent_survive_a_reload_and_are_not_tied_to_a_project(client: TestClient) -> None:
    """글꼴 취향은 사람에게 붙는다. 다음 영상은 보통 새 프로젝트다."""
    assert client.put("/api/caption-fonts/Gaegu/favorite", json={"enabled": True}).status_code == 200
    assert client.put("/api/caption-fonts/Do Hyeon/recent").status_code == 200

    body = client.get("/api/caption-fonts").json()

    assert body["favorites"] == ["Gaegu"]
    assert body["recents"] == ["Do Hyeon"]


def test_marking_a_font_recent_puts_the_newest_first(client: TestClient) -> None:
    client.put("/api/caption-fonts/Jua/recent")
    client.put("/api/caption-fonts/Gugi/recent")
    client.put("/api/caption-fonts/Jua/recent")

    assert client.get("/api/caption-fonts").json()["recents"] == ["Jua", "Gugi"]


def test_unfavouriting_removes_it(client: TestClient) -> None:
    client.put("/api/caption-fonts/Gaegu/favorite", json={"enabled": True})
    client.put("/api/caption-fonts/Gaegu/favorite", json={"enabled": False})

    assert client.get("/api/caption-fonts").json()["favorites"] == []


def test_a_font_nobody_installed_cannot_be_favourited_or_marked_recent(client: TestClient) -> None:
    """없는 글꼴을 담아 두면 다음에 골랐을 때 조용히 대체된다."""
    assert client.put("/api/caption-fonts/Comic Sans MS/favorite", json={"enabled": True}).status_code == 422
    assert client.put("/api/caption-fonts/Comic Sans MS/recent").status_code == 422


def test_caption_preset_favourites_still_work_the_old_way(client: TestClient) -> None:
    """글꼴을 담으려고 저장소를 넓혔지만 자막 모양 쪽은 그대로여야 한다."""
    toggled = client.put(
        "/api/projects/project_001/editor-library/favorites/pack:starter:asset_001",
        json={"favorite_type": "media", "enabled": True},
    )

    assert toggled.status_code == 200
    assert client.get("/api/projects/project_001/editor-library/favorites").json() == [
        {"favorite_id": "pack:starter:asset_001", "favorite_type": "media"}
    ]
