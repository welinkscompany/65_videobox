"""모션 한 편 -- 고르고·검사하고·다리에 맡기고·자료실에 넣는다."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from videobox_core_engine.motion_host_bridge import (
    MotionClip,
    MotionHostBridgeRefused,
    MotionHostBridgeTimedOut,
    MotionHostBridgeUnavailable,
)
from videobox_core_engine.motion_service import MotionService, MotionUnavailable
from videobox_domain_models.library_assets import LibraryMediaType

BAR = {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]}


class _Bridge:
    def __init__(self, clip: MotionClip | None = None, error: BaseException | None = None) -> None:
        self.clip = clip or MotionClip(video_bytes=b"MP4-1", format="mp4", elapsed_sec=12.5)
        self.error = error
        self.calls: list[dict] = []

    def render(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.clip


class _Library:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.calls: list[dict] = []

    def ingest(self, *, media_type, source, filename, idempotency_key, provenance):
        if self.fails:
            raise RuntimeError("자리 없음")
        self.calls.append({"media_type": media_type, "bytes": Path(source).read_bytes(), "filename": filename, "key": idempotency_key, "provenance": provenance})
        return {"library_asset_id": "user_motion1"}


@contextlib.contextmanager
def _scratch(prefix: str, tmp_path: Path):
    del prefix
    yield tmp_path


def _service(bridge, library=None, *, tmp_path: Path) -> MotionService:
    return MotionService(bridge=bridge, library_ingest=library, _scratch_factory=lambda prefix: _scratch(prefix, tmp_path))


def test_a_made_motion_goes_into_the_library_as_a_video(tmp_path: Path) -> None:
    bridge, library = _Bridge(), _Library()
    made = _service(bridge, library, tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert bridge.calls == [{"template": "bar_compare", "variables": {"title": "월 수익 비교", "subtitle": "", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280.0}, {"label": "자사몰", "value": 430.0}]}, "duration_sec": 6.0, "layout": "full"}]
    call = library.calls[0]
    assert call["media_type"] == LibraryMediaType.BROLL
    assert call["bytes"] == b"MP4-1"
    assert call["filename"] == "월-수익-비교.mp4"
    assert call["key"].startswith("motion:")
    assert call["provenance"]["source_kind"] == "generated_motion"
    assert call["provenance"]["template"] == "bar_compare"
    assert (made.library_asset_id, made.title, made.format, made.elapsed_sec) == ("user_motion1", "월 수익 비교", "mp4", 12.5)


def test_a_library_failure_keeps_the_motion_and_says_why(tmp_path: Path) -> None:
    made = _service(_Bridge(), _Library(fails=True), tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert (made.library_asset_id, made.library_error, made.video_bytes) == (None, "RuntimeError", b"MP4-1")


def test_bad_variables_never_reach_the_bridge(tmp_path: Path) -> None:
    bridge = _Bridge()
    with pytest.raises(MotionUnavailable) as caught:
        _service(bridge, tmp_path=tmp_path).make(template_key="bar_compare", variables={"title": "<b>x</b>", "bars": []}, duration_sec=6.0)
    assert caught.value.reason == "motion_variables_invalid"
    assert caught.value.problems
    assert bridge.calls == []


@pytest.mark.parametrize(("duration", "layout"), [(2.0, "full"), (31.0, "full"), (6.0, "mov")])
def test_length_and_look_are_checked_here_too(tmp_path: Path, duration: float, layout: str) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(), tmp_path=tmp_path).make(template_key="step_list", variables={"title": "t", "steps": ["a", "b"]}, duration_sec=duration, layout=layout)
    assert caught.value.reason == "motion_variables_invalid"


def test_an_unknown_template_is_its_own_reason(tmp_path: Path) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(), tmp_path=tmp_path).make(template_key="free_form", variables={}, duration_sec=6.0)
    assert caught.value.reason == "motion_template_unknown"


def test_no_bridge_says_so(tmp_path: Path) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        MotionService(bridge=None).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert caught.value.reason == "motion_bridge_not_configured"


@pytest.mark.parametrize(("error", "reason"), [
    (MotionHostBridgeUnavailable("off"), "motion_bridge_not_running"),
    (MotionHostBridgeTimedOut("slow"), "motion_took_too_long"),
    (MotionHostBridgeRefused(409, "motion_render_busy"), "motion_busy"),
    (MotionHostBridgeRefused(503, "motion_engine_not_prepared"), "motion_engine_not_prepared"),
    (MotionHostBridgeRefused(504, "render_timed_out"), "motion_took_too_long"),
    (MotionHostBridgeRefused(500, "render_failed", "engine_failed: boom"), "motion_render_failed"),
])
def test_each_bridge_failure_gets_its_own_reason(tmp_path: Path, error: BaseException, reason: str) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(error=error), tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert caught.value.reason == reason
