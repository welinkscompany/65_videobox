"""배속은 절대값이다 -- 두 번 걸어도 곱해지지 않는다.

실기 검증에서 잡았다(2026-09-05). 화면에서 `속도`를 1.5배로 넣고 이어서 2배로
넣었더니 5초 장면이 2.5초가 아니라 1.67초가 됐다. 두 번째 계산이 **이미 줄어든
길이**를 원본으로 착각한 것이다.

원인은 `_source_slices`의 폴백이다. 세그먼트에 `source_slices`가 없으면 현재
`end_sec - start_sec`을 원본 길이로 돌려주는데, 그 값에는 앞서 건 배속이 이미
반영돼 있다. 실제 세션 데이터에는 `source_slices`가 없는 세그먼트가 흔하다.

캡컷의 `속도`는 절대값이다 -- 2배로 두었다가 1.5배로 바꾸면 원본의 1.5배지
3배가 아니다. 단추 셋(`기본`·`1.5배`·`2배`)뿐이던 시절에도 같은 결함이었지만,
쓸 수 있는 값이 셋뿐이라 눈에 덜 띄었다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.editing_session import set_segment_ripple_playback_rate


def _session() -> dict:
    """`source_slices`가 없는 세션 -- 실제 데이터에서 흔한 모양이다."""
    return {
        "session_id": "s1",
        "segments": [
            {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0},
            {"segment_id": "seg-2", "start_sec": 5.0, "end_sec": 9.0},
        ],
    }


def _duration(session: dict, segment_id: str) -> float:
    segment = next(item for item in session["segments"] if item["segment_id"] == segment_id)
    return float(segment["end_sec"]) - float(segment["start_sec"])


@pytest.mark.parametrize("first, second", [(1.5, 2.0), (2.0, 1.5), (0.5, 4.0), (4.0, 0.25)])
def test_second_speed_replaces_the_first_instead_of_multiplying(first: float, second: float) -> None:
    once = set_segment_ripple_playback_rate(session=_session(), segment_id="seg-1", rate=first)
    twice = set_segment_ripple_playback_rate(session=once, segment_id="seg-1", rate=second)

    assert _duration(twice, "seg-1") == pytest.approx(5.0 / second)


def test_returning_to_one_restores_the_original_length() -> None:
    session = set_segment_ripple_playback_rate(session=_session(), segment_id="seg-1", rate=2.0)
    session = set_segment_ripple_playback_rate(session=session, segment_id="seg-1", rate=1.0)

    assert _duration(session, "seg-1") == pytest.approx(5.0)
    # 뒤 장면도 제자리로 돌아온다 -- 델타가 어긋나면 여기서 드러난다.
    assert _duration(session, "seg-2") == pytest.approx(4.0)
    segment = session["segments"][0]
    assert "ripple_playback_rate" not in segment


def test_explicit_source_slices_stay_the_measuring_stick() -> None:
    """원본 좌표를 들고 있는 세그먼트는 폴백을 타지 않는다 -- 회귀 방지."""
    session = {
        "session_id": "s1",
        "segments": [
            {
                "segment_id": "seg-1",
                "start_sec": 0.0,
                "end_sec": 5.0,
                "source_slices": [{"segment_id": "seg-1", "source_offset_sec": 0.0, "duration_sec": 5.0}],
            },
        ],
    }

    once = set_segment_ripple_playback_rate(session=session, segment_id="seg-1", rate=1.25)
    twice = set_segment_ripple_playback_rate(session=once, segment_id="seg-1", rate=2.5)

    assert _duration(twice, "seg-1") == pytest.approx(2.0)
