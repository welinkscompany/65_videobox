"""목소리 더빙 -- 번역을 대본으로 쓰고, 장면 길이에 맞춘다.

가장 중요한 시험 둘:
- 번역이 없는 장면은 **한국어로 메우지 않고 건너뛴다**(영어 더빙 중간에 한국어가
  튀어나오면 안 된다)
- 자연스러운 범위를 넘으면 **억지로 맞추지 않는다**(우스운 소리는 없느니만 못하다)
"""

from __future__ import annotations

from typing import Any

import pytest

from videobox_core_engine.dubbing import (
    DUBBING_MAX_SPEED,
    DUBBING_MIN_FILL_RATIO,
    DubbingFit,
    apply_dubbing_fit,
    dubbing_lines,
    plan_dubbing_fit,
    unfitted_scene_message,
)


def _session(*segments: dict[str, Any]) -> dict[str, Any]:
    return {"segments": list(segments)}


def _segment(segment_id: str, start: float, end: float, **extra: Any) -> dict[str, Any]:
    return {"segment_id": segment_id, "start_sec": start, "end_sec": end, **extra}


def test_translated_scenes_become_the_dub_script() -> None:
    session = _session(
        _segment("s1", 0.0, 5.0, caption_text="안녕하세요", caption_translations={"en": "Hello"}),
    )

    lines = dubbing_lines(editing_session=session, language="en")

    assert len(lines) == 1
    assert lines[0].segment_id == "s1"
    assert lines[0].text == "Hello"
    assert lines[0].target_duration_sec == 5.0


def test_a_scene_without_a_translation_is_skipped_not_filled_with_korean() -> None:
    """**영어 더빙 중간에 한국어가 튀어나오면 안 된다.**

    번역이 반쯤 된 상태에서도 더빙을 눌러 볼 수 있어야 하고, 안 옮긴 장면은
    원래 목소리가 그대로 남는 것이 옳다.
    """
    session = _session(
        _segment("s1", 0.0, 5.0, caption_text="안녕하세요", caption_translations={"en": "Hello"}),
        _segment("s2", 5.0, 10.0, caption_text="반갑습니다"),
    )

    lines = dubbing_lines(editing_session=session, language="en")

    assert [line.segment_id for line in lines] == ["s1"]


def test_a_removed_scene_is_never_dubbed() -> None:
    session = _session(
        _segment("s1", 0.0, 5.0, cut_action="remove", caption_translations={"en": "Hello"}),
    )

    assert dubbing_lines(editing_session=session, language="en") == []


def test_another_language_is_not_mixed_in() -> None:
    session = _session(
        _segment("s1", 0.0, 5.0, caption_translations={"ja": "こんにちは"}),
    )

    assert dubbing_lines(editing_session=session, language="en") == []


def test_unknown_language_is_refused() -> None:
    with pytest.raises(ValueError):
        dubbing_lines(editing_session=_session(), language="klingon")


def test_a_slightly_long_take_is_just_trimmed() -> None:
    """조금 긴 것은 끝을 자른다 -- 속도를 건드리면 소리만 나빠진다."""
    fit = plan_dubbing_fit(actual_duration_sec=5.05, target_duration_sec=5.0)

    assert fit.fitted is True
    assert fit.speed == 1.0
    assert fit.pad_sec == 0.0


def test_even_a_barely_short_take_gets_padded() -> None:
    """`-t`는 자르기만 한다. 채우지 않으면 **그만큼 짧은 소리가 그대로 나간다**
    (코드리뷰 2026-09-02에서 나왔다)."""
    fit = plan_dubbing_fit(actual_duration_sec=4.90, target_duration_sec=5.0)

    assert fit.fitted is True
    assert fit.pad_sec == pytest.approx(0.10)


def test_a_slightly_long_take_is_sped_up_to_fit_exactly() -> None:
    fit = plan_dubbing_fit(actual_duration_sec=5.5, target_duration_sec=5.0)

    assert fit.fitted is True
    assert fit.speed == pytest.approx(1.1)


def test_a_short_take_is_padded_with_silence_not_slowed_down() -> None:
    """**말을 늘어뜨려 장면을 채우지 않는다.** 말이 끝나면 조용해지면 된다.

    2026-09-02에 실제로 돌려 보고 고친 설계다. 늘리려 했더니 다섯 장면 중 넷이
    거절됐다 -- 영어가 한국어 장면보다 짧은 것은 예외가 아니라 보통이다.
    """
    fit = plan_dubbing_fit(actual_duration_sec=3.58, target_duration_sec=5.0)

    assert fit.fitted is True
    assert fit.speed == 1.0
    assert fit.pad_sec == pytest.approx(1.42)


def test_a_far_too_long_take_is_refused_rather_than_made_silly() -> None:
    """1.25배를 넘으면 소리가 우스워진다. 그때는 넣지 않는다."""
    fit = plan_dubbing_fit(actual_duration_sec=9.0, target_duration_sec=5.0)

    assert fit.fitted is False
    assert fit.reason == "too_long_to_fit"


def test_a_take_that_barely_says_anything_is_refused() -> None:
    """장면의 절반도 못 채우면 번역이 내용을 흘린 것이다 -- 맞추기 전에 볼 것이 있다."""
    fit = plan_dubbing_fit(actual_duration_sec=2.0, target_duration_sec=5.0)

    assert fit.fitted is False
    assert fit.reason == "too_short_to_fill"


def test_silence_is_never_accepted() -> None:
    fit = plan_dubbing_fit(actual_duration_sec=0.0, target_duration_sec=5.0)

    assert fit.fitted is False
    assert fit.reason == "silent_audio"


def test_the_speed_bound_stays_inside_what_one_atempo_can_do() -> None:
    """`atempo` 한 번은 0.5~2.0만 낸다. 범위를 넓히면 필터를 이어 붙여야 한다."""
    assert 1.0 < DUBBING_MAX_SPEED <= 2.0
    assert 0.0 < DUBBING_MIN_FILL_RATIO < 1.0


def test_the_message_calls_out_engine_failures_separately() -> None:
    """목소리를 못 만든 것은 길이 문제가 아니다 -- 창작자가 할 일도 다르다."""
    message = unfitted_scene_message([
        ("s1", DubbingFit(False, 5.0, 0.0, 1.0, reason="engine_failed")),
    ])

    assert message is not None
    assert "목소리를 만들지 못했어요" in message


def test_the_message_separates_too_long_from_too_short() -> None:
    """창작자가 할 일이 다르다 -- 앞은 번역을 줄이는 것, 뒤는 늘리는 것."""
    message = unfitted_scene_message([
        ("s1", DubbingFit(False, 5.0, 9.0, 1.8, reason="too_long_to_fit")),
        ("s2", DubbingFit(False, 5.0, 2.0, 1.0, reason="too_short_to_fill")),
        ("s3", DubbingFit(True, 5.0, 5.0, 1.0)),
    ])

    assert message is not None
    assert "1개 장면은 옮긴 말이 길어서" in message
    assert "1개 장면은 옮긴 말이 짧아서" in message
    # 못 맞춘 장면이 어떻게 되는지 반드시 말해 준다.
    assert "원래 목소리가 그대로" in message


def test_no_message_when_everything_fits() -> None:
    assert unfitted_scene_message([("s1", DubbingFit(True, 5.0, 5.0, 1.0))]) is None


def test_speed_change_keeps_the_pitch(tmp_path) -> None:
    """**실제로 ffmpeg를 돌려서** 길이가 맞는지 잰다.

    `atempo`는 음높이를 지키고 `asetrate`는 안 지킨다. 잘못 쓰면 목소리가
    다람쥐가 되는데, 그건 코드만 봐서는 안 보인다.
    """
    import subprocess

    source = tmp_path / "source.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=5.5", str(source)],
        check=True, capture_output=True, timeout=120,
    )

    destination = tmp_path / "fitted.wav"
    apply_dubbing_fit(
        source=source, destination=destination,
        fit=plan_dubbing_fit(actual_duration_sec=5.5, target_duration_sec=5.0),
    )

    from videobox_core_engine.audio_descriptors import probe_duration_seconds

    assert probe_duration_seconds(destination) == pytest.approx(5.0, abs=0.1)


def test_padding_actually_reaches_the_scene_length(tmp_path) -> None:
    """짧은 말도 **실제로** 장면 길이만큼 나와야 한다.

    `apad`는 끝을 말해 주지 않으면 무한히 채운다 -- `-t`를 빼먹으면 렌더가 안 끝난다.
    """
    import subprocess

    source = tmp_path / "short.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=3.58", str(source)],
        check=True, capture_output=True, timeout=120,
    )

    destination = tmp_path / "padded.wav"
    apply_dubbing_fit(
        source=source, destination=destination,
        fit=plan_dubbing_fit(actual_duration_sec=3.58, target_duration_sec=5.0),
    )

    from videobox_core_engine.audio_descriptors import probe_duration_seconds

    assert probe_duration_seconds(destination) == pytest.approx(5.0, abs=0.1)
