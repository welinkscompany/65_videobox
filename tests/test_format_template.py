from __future__ import annotations

import pytest

from videobox_core_engine.format_template import (
    FormatTemplateError,
    apply_format_template,
    format_template_from_session,
)


def _session(**overrides: object) -> dict:
    session = {
        "session_id": "session_a",
        "caption_style": {"font_family": "Pretendard", "font_size_px": 48, "text_color": "#FFFFFF"},
        "output": {"width": 1920, "height": 1080},
        "segments": [
            {"segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0, "music_asset_id": "asset_music"},
            {"segment_id": "s2", "start_sec": 5.0, "end_sec": 11.0, "music_asset_id": "asset_music"},
        ],
    }
    session.update(overrides)  # type: ignore[arg-type]
    return session


def test_a_template_captures_the_look_not_the_content() -> None:
    # 템플릿은 "어떻게 보이는가"를 옮기는 것이다. 이 영상의 장면이나 대본을
    # 함께 실어 나르면 다음 영상이 지난 영상의 내용을 물려받는다.
    template = format_template_from_session(name="내 기본 포맷", session=_session())

    assert template["name"] == "내 기본 포맷"
    assert template["caption_style"]["font_size_px"] == 48
    assert template["width"] == 1920
    assert template["height"] == 1080
    assert template["average_scene_sec"] == 5.5
    assert "segments" not in template
    assert "session_id" not in template


def test_a_template_remembers_the_music_it_used() -> None:
    # 음악은 포맷의 일부다. 같은 포맷인데 매번 다른 분위기가 깔리면 포맷이 아니다.
    template = format_template_from_session(name="브이로그", session=_session())

    assert template["music_asset_id"] == "asset_music"


def test_a_session_with_no_single_music_choice_carries_none() -> None:
    # 구간마다 음악이 다르면 하나로 못 줄인다. 아무거나 고르면 거짓말이 된다.
    session = _session(segments=[
        {"segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0, "music_asset_id": "asset_a"},
        {"segment_id": "s2", "start_sec": 5.0, "end_sec": 10.0, "music_asset_id": "asset_b"},
    ])

    assert format_template_from_session(name="혼합", session=session)["music_asset_id"] is None


def test_a_template_needs_a_name_a_person_can_recognize() -> None:
    with pytest.raises(FormatTemplateError):
        format_template_from_session(name="   ", session=_session())


def test_applying_a_template_changes_the_look_and_leaves_the_content_alone() -> None:
    template = format_template_from_session(name="포맷", session=_session())
    target = {
        "session_id": "session_b",
        "caption_style": {"font_family": "다른 글꼴", "font_size_px": 20},
        "output": {"width": 1080, "height": 1920},
        "segments": [{"segment_id": "t1", "start_sec": 0.0, "end_sec": 3.0}],
    }

    applied = apply_format_template(session=target, template=template)

    assert applied["caption_style"]["font_size_px"] == 48
    assert applied["output"] == {"width": 1920, "height": 1080}
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


def test_the_target_keeps_its_own_orientation_when_asked() -> None:
    # 가로 포맷을 세로 영상에 적용하고 싶을 때가 있다. 그때 크기까지 끌고 오면
    # 세로 영상이 조용히 가로가 된다.
    template = format_template_from_session(name="가로 포맷", session=_session())
    target = {"session_id": "b", "caption_style": {}, "output": {"width": 1080, "height": 1920}}

    applied = apply_format_template(session=target, template=template, keep_output_size=True)

    assert applied["output"] == {"width": 1080, "height": 1920}
    assert applied["caption_style"]["font_size_px"] == 48
