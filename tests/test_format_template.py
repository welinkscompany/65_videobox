from __future__ import annotations

import pytest

from videobox_core_engine.format_template import (
    FormatTemplateError,
    apply_format_template,
    format_template_from_session,
)


def _session(**overrides: object) -> dict:
    """실제 편집본의 모양을 그대로 쓴다.

    음악은 `music_override.asset_id`에 있고, 화면 크기는 편집본이 아니라 타임라인에
    있다. 2026-08-16에 이걸 짐작으로 썼다가 아무것도 안 담긴 포맷이 저장됐다.
    """
    session = {
        "session_id": "session_a",
        "caption_style": {"font_family": "Pretendard", "font_size_px": 48, "text_color": "#FFFFFF"},
        "segments": [
            {"segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0, "music_override": {"asset_id": "asset_music"}},
            {"segment_id": "s2", "start_sec": 5.0, "end_sec": 11.0, "music_override": {"asset_id": "asset_music"}},
        ],
    }
    session.update(overrides)  # type: ignore[arg-type]
    return session


def test_a_template_captures_the_look_not_the_content() -> None:
    # 템플릿은 "어떻게 보이는가"를 옮기는 것이다. 이 영상의 장면이나 대본을
    # 함께 실어 나르면 다음 영상이 지난 영상의 내용을 물려받는다.
    template = format_template_from_session(
        name="내 기본 포맷", session=_session(), timeline={"output": {"width": 1920, "height": 1080}},
    )

    assert template["name"] == "내 기본 포맷"
    assert template["caption_style"]["font_size_px"] == 48
    assert template["width"] == 1920
    assert template["height"] == 1080
    assert template["average_scene_sec"] == 5.5
    assert "segments" not in template
    assert "session_id" not in template


def test_a_caption_style_a_segment_carries_is_used_when_the_session_has_none() -> None:
    # 실제 편집본은 세션 수준 `caption_style`이 비어 있고 장면마다 들고 있을 수 있다.
    # 세션만 보면 빈 포맷이 저장된다 — 2026-08-16에 실제로 그렇게 나왔다.
    session = _session(caption_style=None, segments=[
        {"segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0, "caption_style": {"font_size_px": 64}},
    ])

    assert format_template_from_session(name="장면 스타일", session=session)["caption_style"]["font_size_px"] == 64


def test_a_template_remembers_the_music_it_used() -> None:
    # 음악은 포맷의 일부다. 같은 포맷인데 매번 다른 분위기가 깔리면 포맷이 아니다.
    template = format_template_from_session(name="브이로그", session=_session())

    assert template["music_asset_id"] == "asset_music"


def test_a_session_with_no_single_music_choice_carries_none() -> None:
    # 구간마다 음악이 다르면 하나로 못 줄인다. 아무거나 고르면 거짓말이 된다.
    session = _session(segments=[
        {"segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0, "music_override": {"asset_id": "asset_a"}},
        {"segment_id": "s2", "start_sec": 5.0, "end_sec": 10.0, "music_override": {"asset_id": "asset_b"}},
    ])

    assert format_template_from_session(name="혼합", session=session)["music_asset_id"] is None


def test_a_template_needs_a_name_a_person_can_recognize() -> None:
    with pytest.raises(FormatTemplateError):
        format_template_from_session(name="   ", session=_session())


def test_applying_a_template_changes_the_captions_and_leaves_everything_else_alone() -> None:
    # 적용은 자막 모양만 바꾼다. 화면 크기는 영상을 만들 때 정한 그대로다 —
    # 크기를 실제로 바꾸는 검증된 경로가 없는데 세션에만 써 두면, 화면은
    # 바뀌었다고 말하고 완성본은 원래 크기로 나오는 거짓말이 된다.
    template = format_template_from_session(
        name="포맷", session=_session(), timeline={"output": {"width": 1920, "height": 1080}},
    )
    target = {
        "session_id": "session_b",
        "caption_style": {"font_family": "다른 글꼴", "font_size_px": 20},
        "output": {"width": 1080, "height": 1920},
        "segments": [{"segment_id": "t1", "start_sec": 0.0, "end_sec": 3.0}],
    }

    applied = apply_format_template(session=target, template=template)

    assert applied["caption_style"]["font_size_px"] == 48
    # 세로 영상은 세로 그대로다. 가로 포맷을 눌렀다고 조용히 가로가 되지 않는다.
    assert applied["output"] == {"width": 1080, "height": 1920}
    # 내용은 그대로다.
    assert applied["segments"] == target["segments"]
    assert applied["session_id"] == "session_b"


def test_applying_a_template_does_not_mutate_what_it_was_given() -> None:
    # 적용을 되돌릴 수 있어야 한다. 원본을 그 자리에서 고치면 되돌릴 것이 없다.
    template = format_template_from_session(name="포맷", session=_session())
    target = {"session_id": "session_b", "caption_style": {"font_size_px": 20}, "output": {"width": 1080, "height": 1920}}

    apply_format_template(session=target, template=template)

    assert target["caption_style"]["font_size_px"] == 20
    assert target["output"]["width"] == 1080


def test_the_size_a_template_remembers_is_a_record_not_a_command() -> None:
    # 크기는 포맷 카드가 "이건 가로에서 떠낸 포맷"이라고 알려 주는 기록이다.
    # 저장은 계속 담되, 적용이 그 크기를 세션에 쓰지 않는다.
    template = format_template_from_session(
        name="가로 포맷", session=_session(), timeline={"output": {"width": 1920, "height": 1080}},
    )
    assert template["width"] == 1920
    assert template["height"] == 1080

    applied = apply_format_template(
        session={"session_id": "b", "caption_style": {}, "segments": []}, template=template
    )

    # 크기가 없던 편집본에 크기를 심지도 않는다.
    assert "output" not in applied
    assert applied["caption_style"]["font_size_px"] == 48
