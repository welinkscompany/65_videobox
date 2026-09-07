"""인포그래픽을 만드는 문(HTTP).

여기서 지키는 것: **꺼진 것·안 켜진 것·못 만든 것이 서로 다른 답으로 나간다.**
한 낱말로 뭉개면 화면이 "켜 주세요"와 "다시 눌러 보세요"를 구분할 수 없다 --
2026-08-20에 그림 생성에서 이 둘이 같은 문구로 보여 켜지지 않은 기능을 결함으로
보고할 뻔했다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.infographic_brief import INFOGRAPHIC_STYLES
from videobox_core_engine.infographic_service import (
    GeneratedInfographic,
    InfographicUnavailable,
)

BODY = {
    "topic": "스마트스토어 판매 수수료 구조",
    "facts": [
        {"label": "네이버 결제 수수료", "value": 3.4, "unit": "%"},
        {"label": "셀러에게 남는 몫", "value": 94.6, "unit": "%"},
    ],
    "style": "dark_glass",
}


class _Service:
    def __init__(self, made=None, raises: InfographicUnavailable | None = None) -> None:
        self.made = made
        self.raises = raises
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.made


def _made(**overrides) -> GeneratedInfographic:
    values = {
        "png_bytes": b"PNG",
        "html": "<!DOCTYPE html><html></html>",
        "style_key": "dark_glass",
        "title": "스마트스토어 판매 수수료 구조",
        "attempts": 1,
    }
    values.update(overrides)
    return GeneratedInfographic(**values)


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "data"))


def test_the_styles_come_from_one_place(client: TestClient) -> None:
    """화면이 결 이름을 손으로 베껴 적으면 둘이 어긋난다 -- 팔레트에서 이미
    겪은 일이다."""

    reply = client.get("/api/library/infographic-styles")
    assert reply.status_code == 200
    keys = [style["key"] for style in reply.json()["styles"]]
    assert keys == [style.key for style in INFOGRAPHIC_STYLES]
    assert reply.json()["styles"][0]["korean_name"]


def test_a_feature_that_is_not_on_says_so(client: TestClient) -> None:
    """꺼진 것과 고장 난 것은 다르다(`scene_images`와 같은 이유)."""

    client.app.state.infographic_service = None
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.status_code == 503
    assert reply.json()["detail"] == "infographic_generation_unavailable"


def test_a_made_picture_comes_back_with_where_it_went(client: TestClient) -> None:
    """만든 뒤 어디 갔는지 안 알려 주면 만든 적 없는 것과 같다."""

    service = _Service(_made(library_asset_id="user_abc"))
    client.app.state.infographic_service = service
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.status_code == 201
    body = reply.json()
    assert body["library_asset_id"] == "user_abc"
    assert body["style"] == "dark_glass"
    assert body["attempts"] == 1
    # 준 숫자가 그대로 서비스에 갔는지 -- 여기서 흘리면 그림이 엉뚱한 숫자로 나온다.
    facts = service.calls[0]["facts"]
    assert [(fact.label, fact.value, fact.unit) for fact in facts] == [
        ("네이버 결제 수수료", 3.4, "%"),
        ("셀러에게 남는 몫", 94.6, "%"),
    ]


def test_a_library_failure_still_returns_the_picture(client: TestClient) -> None:
    """그림은 만들어졌다. 500으로 내면 2분 걸려 만든 것을 창작자가 잃는다."""

    client.app.state.infographic_service = _Service(
        _made(library_asset_id=None, library_error="RuntimeError")
    )
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.status_code == 201
    assert reply.json()["library_error"] == "RuntimeError"
    assert reply.json()["library_asset_id"] is None


def test_what_is_still_wrong_is_not_hidden(client: TestClient) -> None:
    """시간이 모자라 더 못 고쳤을 때 채워져 온다. 숨기면 창작자가 다 된 줄 알고
    영상에 넣는다."""

    client.app.state.infographic_service = _Service(
        _made(library_asset_id="user_abc", attempts=1, remaining_problems=("아래가 잘린다",))
    )
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.json()["remaining_problems"] == ["아래가 잘린다"]


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("infographic_bridge_not_running", 503),
        ("infographic_took_too_long", 504),
        ("infographic_writer_unavailable", 502),
        ("infographic_did_not_pass_checks", 422),
    ],
)
def test_each_kind_of_failure_gets_its_own_answer(
    client: TestClient, reason: str, expected: int
) -> None:
    """**한 낱말로 뭉개지 않는다.** 화면이 "켜 주세요"와 "다시 눌러 보세요"를
    구분해서 말할 수 있어야 한다."""

    client.app.state.infographic_service = _Service(raises=InfographicUnavailable(reason))
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.status_code == expected
    assert reply.json()["detail"] == reason


def test_what_the_model_made_up_is_told_not_swallowed(client: TestClient) -> None:
    """**2026-09-07에 컨테이너에서 두 판 다 버려졌는데 로그에 이유가 없었다.**
    같은 요청을 손으로 다시 돌려서야 모델이 `316,000원`을 지어냈다는 것을 알았다.
    "다시 해 보세요"만 들으면 창작자는 같은 주제로 또 누른다."""

    client.app.state.infographic_service = _Service(
        raises=InfographicUnavailable(
            "infographic_did_not_pass_checks", "준 적 없는 숫자가 그림에 있다: 316000"
        )
    )
    reply = client.post("/api/library/infographics", json=BODY)
    assert reply.status_code == 422
    assert reply.json()["detail"]["reason"] == "infographic_did_not_pass_checks"
    assert "316000" in reply.json()["detail"]["problems"]


@pytest.mark.parametrize(
    "body",
    [
        {"topic": "", "facts": [{"label": "가", "value": 1}]},
        {"topic": "수수료", "facts": []},
        {"topic": "수수료", "facts": [{"label": "가", "value": n} for n in range(9)]},
    ],
)
def test_a_request_that_cannot_make_a_picture_is_refused_at_the_door(
    client: TestClient, body: dict
) -> None:
    """숫자 아홉 개는 1920x1080 안에 못 들어간다. 화면 가까운 쪽에서 막는 편이
    2분 기다린 뒤 실패하는 것보다 낫다."""

    service = _Service(_made())
    client.app.state.infographic_service = service
    assert client.post("/api/library/infographics", json=body).status_code == 422
    assert service.calls == [], "거절해야 할 요청이 서비스까지 갔다"
