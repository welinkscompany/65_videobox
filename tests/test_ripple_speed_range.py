"""리플 배속 허용 범위. owner 지시(2026-09-04): "속도는 캡컷이랑 동일하게 맞춰."

캡컷 `속도` 속성은 숫자칸이라 임의 배속을 받는다. 우리는 `{1.0, 1.5, 2.0}` 셋만
받았다 -- 창작자가 1.25배를 쓰고 싶어도 방법이 없었다.

**넓혀도 되는 근거는 이미 코드에 있다**: 렌더의 `_atempo_chain`이 "허용
범위(0.25~4)"를 명시하고 그 범위를 단계로 쪼개 처리한다
(`ffmpeg_final_renderer.py:92`). 너무 짧아지는 장면은 `MIN_SEGMENT_DURATION_SEC`이
따로 막는다. 즉 엔진은 처음부터 이 범위를 감당하게 만들어져 있었고, 화면과
검증만 셋으로 좁혀 놨던 것이다.

**유진의 스키마는 그대로 둔다.** `set_scene_speed`는 `enum: [1, 1.5, 2]`로
좁게 유지한다 -- 사람이 고르는 것과 AI가 제안하는 것의 범위가 같을 이유가 없고,
좁은 쪽이 안전하다.

**값이 두 파일에 따로 있던 것도 없앤다.** `editing_session.py`와
`composition_plan.py`가 각자 `frozenset`을 갖고 있어서, 한쪽만 고치면 저장은
되는데 렌더가 거부하는 상태가 된다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.editing_session import (
    MAX_RIPPLE_PLAYBACK_RATE,
    MIN_RIPPLE_PLAYBACK_RATE,
    build_editing_session,
    set_segment_ripple_playback_rate,
)


def _session() -> dict:
    return build_editing_session(
        project_id="project_rate",
        timeline={"timeline_id": "timeline_rate", "tracks": []},
        segments=[{"segment_id": "scene-1", "text": "장면", "start_sec": 0.0, "end_sec": 8.0}],
    )


@pytest.mark.parametrize("rate", [0.25, 0.5, 1.25, 1.75, 3.0, 4.0])
def test_accepts_any_rate_the_renderer_can_actually_play(rate: float) -> None:
    updated = set_segment_ripple_playback_rate(session=_session(), segment_id="scene-1", rate=rate)
    segment = updated["segments"][0]
    # 길이는 엔진 식 그대로 -- 원본 8초를 배속으로 나눈다.
    assert segment["end_sec"] == pytest.approx(8.0 / rate)


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf"), 0.1, 5.0])
def test_still_refuses_what_the_renderer_cannot_play(rate: float) -> None:
    session = _session()
    with pytest.raises(ValueError, match="segment_ripple_playback_rate_invalid"):
        set_segment_ripple_playback_rate(session=session, segment_id="scene-1", rate=rate)
    assert session["segments"][0].get("ripple_playback_rate") is None


def test_range_matches_the_renderer_chain() -> None:
    """`_atempo_chain` 주석이 말하는 범위와 같아야 한다.

    다르면 저장은 되는데 렌더가 실패하는 조합이 생긴다.
    """
    assert (MIN_RIPPLE_PLAYBACK_RATE, MAX_RIPPLE_PLAYBACK_RATE) == (0.25, 4.0)


def test_both_modules_read_the_same_range() -> None:
    """값이 두 파일에 따로 있으면 한쪽만 고쳐지는 날이 온다."""
    from videobox_core_engine import composition_plan

    assert composition_plan.MIN_RIPPLE_PLAYBACK_RATE is MIN_RIPPLE_PLAYBACK_RATE
    assert composition_plan.MAX_RIPPLE_PLAYBACK_RATE is MAX_RIPPLE_PLAYBACK_RATE
