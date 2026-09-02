"""자막 번역 -- 원본 위에 덮어쓰지 않고 나란히 두고, 출력할 때 고른다.

이 저장소가 자막을 다루는 방식은 이미 하나 있다(`update_segment_caption`):
장면에 쓰고, 그 장면을 가리키는 content window에도 같이 쓴다. 번역도 **같은
자리·같은 규칙**으로 둔다. 두 벌로 나뉘면 한쪽만 갱신되는 상태가 생긴다.

가장 중요한 시험은 마지막 둘이다. 번역을 저장하는 것만으로는 완성본이 안 바뀐다 --
**출력에 실제로 실리는지**를 재야 한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from videobox_core_engine.caption_translation import (
    SUPPORTED_CAPTION_LANGUAGES,
    apply_caption_translations,
    caption_text_for_language,
)
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.editing_session import build_editing_session


def _session() -> dict[str, Any]:
    return build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {"segment_id": "segment_001", "text": "안녕하세요", "start_sec": 0.0, "end_sec": 2.0},
            {"segment_id": "segment_002", "text": "반갑습니다", "start_sec": 2.0, "end_sec": 4.0},
        ],
    )


def _caption_texts(session: dict[str, Any]) -> list[str]:
    materialized = materialize_editing_session_timeline(timeline={"tracks": []}, editing_session=session)
    return [str(caption["caption_text"]) for caption in materialized["session_captions"]]


def test_english_is_offered() -> None:
    assert "en" in SUPPORTED_CAPTION_LANGUAGES


def test_reader_falls_back_to_the_original_when_nothing_is_stored() -> None:
    assert caption_text_for_language({"caption_text": "안녕하세요"}, "en") == "안녕하세요"


def test_reader_falls_back_when_the_stored_translation_is_blank() -> None:
    """모델이 빈 문자열을 돌려줘도 **자막이 사라지면 안 된다.**

    번역이 비었다는 것은 "이 장면은 자막 없음"이 아니라 "아직 번역이 없음"이다.
    빈 값을 그대로 실으면 완성본에서 그 장면만 자막이 통째로 빠진다.
    """
    source = {"caption_text": "안녕하세요", "caption_translations": {"en": "   "}}
    assert caption_text_for_language(source, "en") == "안녕하세요"


def test_reader_returns_the_translation_when_it_is_there() -> None:
    source = {"caption_text": "안녕하세요", "caption_translations": {"en": "Hello"}}
    assert caption_text_for_language(source, "en") == "Hello"


def test_no_language_means_the_original() -> None:
    source = {"caption_text": "안녕하세요", "caption_translations": {"en": "Hello"}}
    assert caption_text_for_language(source, None) == "안녕하세요"


def test_the_original_survives_translation() -> None:
    """번역해도 한국어 원본은 그대로 남는다 -- 되돌릴 것이 없으면 안 된다."""
    updated = apply_caption_translations(
        session=_session(), language="en", texts_by_segment={"segment_001": "Hello"}
    )
    segment = next(item for item in updated["segments"] if item["segment_id"] == "segment_001")
    assert segment["caption_text"] == "안녕하세요"
    assert segment["caption_translations"]["en"] == "Hello"


def test_a_second_language_does_not_erase_the_first() -> None:
    once = apply_caption_translations(
        session=_session(), language="en", texts_by_segment={"segment_001": "Hello"}
    )
    twice = apply_caption_translations(
        session=once, language="ja", texts_by_segment={"segment_001": "こんにちは"}
    )
    segment = next(item for item in twice["segments"] if item["segment_id"] == "segment_001")
    assert segment["caption_translations"] == {"en": "Hello", "ja": "こんにちは"}


def test_unknown_language_is_refused() -> None:
    with pytest.raises(ValueError):
        apply_caption_translations(session=_session(), language="klingon", texts_by_segment={})


def test_export_carries_the_chosen_language() -> None:
    """**여기가 진짜 시험이다.** 저장만 되고 완성본이 안 바뀌면 아무 소용이 없다."""
    session = apply_caption_translations(
        session=_session(),
        language="en",
        texts_by_segment={"segment_001": "Hello", "segment_002": "Nice to meet you"},
    )
    session["caption_language"] = "en"
    assert _caption_texts(session) == ["Hello", "Nice to meet you"]


def test_export_falls_back_scene_by_scene() -> None:
    """한 장면만 번역돼 있으면 나머지는 **한국어 그대로** 나간다.

    번역이 반쯤 된 상태에서 내보내도 자막 없는 장면이 생기지 않아야 한다.
    """
    session = apply_caption_translations(
        session=_session(), language="en", texts_by_segment={"segment_001": "Hello"}
    )
    session["caption_language"] = "en"
    assert _caption_texts(session) == ["Hello", "반갑습니다"]


def test_export_without_a_choice_stays_korean() -> None:
    session = apply_caption_translations(
        session=_session(), language="en", texts_by_segment={"segment_001": "Hello"}
    )
    assert _caption_texts(session) == ["안녕하세요", "반갑습니다"]
