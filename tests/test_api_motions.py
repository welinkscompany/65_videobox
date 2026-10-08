"""설명 모션을 만드는 문(HTTP). 꺼진 것·준비 중·바쁨·못 만든 것이 서로 다른 답으로 나간다."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.motion_service import MadeMotion, MotionService, MotionUnavailable
from videobox_core_engine.motion_templates import MOTION_TEMPLATES

BODY = {
    "template": "bar_compare",
    "variables": {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]},
    "duration_sec": 6,
    "layout": "full",
}


class _Service:
    def __init__(self, made=None, raises: MotionUnavailable | None = None) -> None:
        self.made, self.raises, self.calls = made, raises, []

    def make(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.made


def _made(**overrides) -> MadeMotion:
    values = {"video_bytes": b"MP4", "template_key": "bar_compare", "title": "월 수익 비교", "duration_sec": 6.0, "layout": "full", "format": "mp4", "elapsed_sec": 13.1, "library_asset_id": "user_m1"}
    values.update(overrides)
    return MadeMotion(**values)


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "data"))


def test_the_templates_come_from_one_place(client: TestClient) -> None:
    reply = client.get("/api/library/motion-templates")
    assert reply.status_code == 200
    templates = reply.json()["templates"]
    assert [t["key"] for t in templates] == [t.key for t in MOTION_TEMPLATES]
    assert templates[0]["korean_name"] == "막대 비교"
    assert (templates[0]["min_duration_sec"], templates[0]["max_duration_sec"]) == (3.0, 30.0)
    assert templates[0]["limits"]["title"] == 24


def test_the_app_builds_a_motion_service_wired_to_the_library(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_MOTION_BRIDGE_URL", "http://host.docker.internal:8202")
    app = create_app(projects_root=tmp_path / "data")
    assert isinstance(app.state.motion_service, MotionService)
    assert app.state.motion_service.library_ingest is app.state.library_ingest_service
    assert app.state.motion_service.bridge.base_url == "http://host.docker.internal:8202"


def test_a_feature_that_is_not_on_says_so(client: TestClient) -> None:
    client.app.state.motion_service = None
    reply = client.post("/api/library/motions", json=BODY)
    assert (reply.status_code, reply.json()["detail"]) == (503, "motion_generation_unavailable")


def test_a_made_motion_comes_back_with_where_it_went(client: TestClient) -> None:
    service = _Service(_made())
    client.app.state.motion_service = service
    reply = client.post("/api/library/motions", json=BODY)
    assert reply.status_code == 201
    assert reply.json() == {"library_asset_id": "user_m1", "template": "bar_compare", "title": "월 수익 비교", "duration_sec": 6.0, "layout": "full", "format": "mp4", "byte_size": 3, "elapsed_sec": 13.1, "library_error": None}
    assert service.calls == [{"template_key": "bar_compare", "variables": BODY["variables"], "duration_sec": 6.0, "layout": "full", "title": None}]


def test_a_small_transparent_window_reaches_the_service_as_overlay(client: TestClient) -> None:
    service = _Service(_made())
    client.app.state.motion_service = service
    reply = client.post("/api/library/motions", json={**BODY, "layout": "overlay"})
    assert reply.status_code == 201
    assert service.calls[0]["layout"] == "overlay"


def test_whole_numbers_reach_the_service_as_whole_numbers(client: TestClient) -> None:
    """Task 3은 정수 칸에 1280.0을 거절한다 -- 문이 숫자를 소수로 바꾸면 안 된다."""
    service = _Service(_made())
    client.app.state.motion_service = service
    client.post("/api/library/motions", json=BODY)
    value = service.calls[0]["variables"]["bars"][0]["value"]
    assert value == 1280 and isinstance(value, int)


@pytest.mark.parametrize(("reason", "status"), [
    ("motion_template_unknown", 422), ("motion_bridge_not_configured", 503), ("motion_bridge_not_running", 503),
    ("motion_engine_not_prepared", 503), ("motion_busy", 409), ("motion_took_too_long", 504), ("motion_render_failed", 502),
])
def test_each_kind_of_failure_gets_its_own_answer(client: TestClient, reason: str, status: int) -> None:
    client.app.state.motion_service = _Service(raises=MotionUnavailable(reason))
    reply = client.post("/api/library/motions", json=BODY)
    assert (reply.status_code, reply.json()["detail"]) == (status, reason)


def test_what_was_wrong_with_the_text_is_told_not_swallowed(client: TestClient) -> None:
    client.app.state.motion_service = _Service(raises=MotionUnavailable("motion_variables_invalid", problems=("제목: 24자까지 써요",)))
    reply = client.post("/api/library/motions", json=BODY)
    assert reply.status_code == 422
    assert reply.json()["detail"] == {"reason": "motion_variables_invalid", "problems": ["제목: 24자까지 써요"]}


@pytest.mark.parametrize("patch", [
    {"duration_sec": 2}, {"duration_sec": 31}, {"layout": "mov"}, {"title": "<b>x</b>"}, {"title": "x" * 61}, {"extra": 1},
])
def test_a_request_that_cannot_be_a_motion_is_refused_at_the_door(client: TestClient, patch: dict) -> None:
    service = _Service(_made())
    client.app.state.motion_service = service
    reply = client.post("/api/library/motions", json={**BODY, **patch})
    assert reply.status_code == 422
    assert service.calls == []
