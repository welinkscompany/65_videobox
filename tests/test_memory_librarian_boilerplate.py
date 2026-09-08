"""기억 사서의 정형구 필터. `docs/handoffs/...`에 적은 owner 스펙과 정확히 맞춘다:

긴 문단(40자 이상)은 2회, 짧은 문단은 3회 이상 반복돼야 정형구다. 90일 창.
고정 이름 목록이 아니라 반복 빈도로만 판정한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC

from videobox_core_engine.memory_librarian_boilerplate import (
    TimestampedParagraph,
    find_boilerplate,
    is_injected_paragraph,
    strip_boilerplate,
)

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


def _at(days_ago: float, text: str) -> TimestampedParagraph:
    return TimestampedParagraph(text=text, occurred_at=NOW - timedelta(days=days_ago))


def test_a_long_paragraph_needs_only_two_repeats_to_count_as_boilerplate() -> None:
    long_text = "이 요청은 유진이 직접 할 수 없어요. 데이터·파일·자격정보 조작이나 썸네일·추천 영상 생성은 유진의 대화 범위 밖이에요."
    assert len(long_text) >= 40
    paragraphs = [_at(1, long_text), _at(2, long_text), _at(10, "빠른 컷을 좋아합니다.")]

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert long_text in boilerplate


def test_a_short_paragraph_needs_three_repeats_not_two() -> None:
    short_text = "참조를 확인했습니다."
    assert len(short_text) < 40
    paragraphs = [_at(1, short_text), _at(2, short_text)]  # 2번뿐

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert short_text not in boilerplate  # 짧은 건 3번은 돼야 한다


def test_a_short_paragraph_with_three_repeats_does_count() -> None:
    short_text = "참조를 확인했습니다."
    paragraphs = [_at(1, short_text), _at(2, short_text), _at(3, short_text)]

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert short_text in boilerplate


def test_a_paragraph_outside_the_lookback_window_is_not_counted() -> None:
    text = "참조를 확인했습니다."
    paragraphs = [
        _at(1, text), _at(2, text),
        _at(200, text),  # 90일 창 밖 -- 세지 않는다
    ]

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert text not in boilerplate  # 창 안에는 2번뿐이라 짧은 기준(3)을 못 채운다


def test_near_duplicate_text_is_not_treated_as_the_same_paragraph() -> None:
    """의미가 비슷해도 문자열이 다르면 다른 문단이다 -- 정확히 일치하는 것만 센다."""
    paragraphs = [
        _at(1, "빠른 컷을 좋아합니다."),
        _at(2, "빠른 컷 편집을 선호합니다."),
        _at(3, "빠른 컷이 좋아요."),
    ]

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert boilerplate == frozenset()


def test_a_real_user_preference_repeated_by_coincidence_is_not_swallowed_below_threshold() -> None:
    """짧은 문장이 딱 2번만 나오면(3번 미만) 아직 정형구가 아니다 -- 사람 말이 지워지면 안 된다."""
    paragraphs = [_at(1, "짧게 부탁해요."), _at(5, "짧게 부탁해요.")]

    boilerplate = find_boilerplate(paragraphs, as_of=NOW)

    assert boilerplate == frozenset()


def test_is_injected_paragraph_detects_bracket_prefixed_text() -> None:
    assert is_injected_paragraph("[system] route guard active")
    assert not is_injected_paragraph("사용자가 대괄호를 쓴 게 아니라 그냥 말한 것")


def test_strip_boilerplate_removes_repeats_and_bracketed_and_oversized_paragraphs() -> None:
    repeated = "참조를 확인했습니다."
    paragraphs = [
        _at(1, repeated), _at(2, repeated), _at(3, repeated),
        _at(1, "[system] internal note"),
        _at(1, "가" * 900),  # 지나치게 긴 사용자 문단
        _at(1, "빠른 컷을 좋아합니다."),  # 진짜 사람 말, 남아야 한다
    ]

    kept = strip_boilerplate(paragraphs, as_of=NOW, max_user_paragraph_chars=800)

    assert [p.text for p in kept] == ["빠른 컷을 좋아합니다."]


def test_strip_boilerplate_without_a_length_cap_keeps_long_non_repeated_text() -> None:
    paragraphs = [_at(1, "가" * 900)]

    kept = strip_boilerplate(paragraphs, as_of=NOW)

    assert len(kept) == 1


def test_blank_paragraphs_are_dropped() -> None:
    paragraphs = [_at(1, "   "), _at(1, "")]

    assert find_boilerplate(paragraphs, as_of=NOW) == frozenset()
    assert strip_boilerplate(paragraphs, as_of=NOW) == []
