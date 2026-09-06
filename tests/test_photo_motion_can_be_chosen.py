"""사진이 **어떻게** 움직일지 고를 수 없었다 — 갭검증 2026-09-06.

> owner: "사진 움직이는 효과도 다양한 형태로 움직이게 하고"

여섯 가지를 만들어 두고 `clip_id` 해시로 **자동 배정**하고 있었다. 다양하긴
한데 창작자가 고르지도, 끄지도 못한다 -- 이 저장소가 되풀이한 "부품은 있는데
부르는 자리가 없다"의 축소판이다.

색감(`filter`)이 지나간 길을 그대로 쓴다: 클립 조정값에 얹고, **안 고른 클립에는
칸 자체를 안 넣는다.** 넣으면 옛 저장분과 모양이 달라져 아무것도 안 바꾼
편집본이 바뀐 것처럼 보인다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_controls import normalize_media_controls


def _controls(**payload: object) -> dict:
    return normalize_media_controls(payload, media_kind="broll", duration_sec=4.0)


def test_not_choosing_leaves_the_field_out() -> None:
    assert "photo_motion" not in _controls()


def test_a_chosen_motion_is_kept() -> None:
    assert _controls(photo_motion="pan_left")["photo_motion"] == "pan_left"


def test_holding_still_is_a_choice_too() -> None:
    """움직임을 끄는 것도 고르는 것이다. 안 고른 것과 구별해야 끌 수 있다."""
    assert _controls(photo_motion="still")["photo_motion"] == "still"


def test_a_made_up_motion_is_refused() -> None:
    with pytest.raises(ValueError):
        _controls(photo_motion="spin")


def test_the_renderer_uses_the_chosen_motion() -> None:
    renderer = FfmpegFinalRenderer(store=None)

    chain = renderer._photo_motion_chain("clip_a", 4.0, chosen="pan_up")
    other = renderer._photo_motion_chain("clip_a", 4.0, chosen="pan_down")

    assert "zoompan" in chain
    assert chain != other, "고른 값이 달라도 같은 사슬이 나왔다"


def test_holding_still_adds_no_filter() -> None:
    """끄면 필터를 안 더한다 -- 안 쓰는 기능에 화질과 시간을 들이지 않는다."""
    assert FfmpegFinalRenderer(store=None)._photo_motion_chain("clip_a", 4.0, chosen="still") == ""


def test_without_a_choice_the_motion_is_still_decided_by_the_clip() -> None:
    """안 고르면 예전 그대로 -- 클립마다 다르되 같은 편집본에서는 늘 같다."""
    renderer = FfmpegFinalRenderer(store=None)

    assert renderer._photo_motion_chain("clip_a", 4.0) == renderer._photo_motion_chain("clip_a", 4.0)
    assert renderer._photo_motion_chain("clip_a", 4.0) != renderer._photo_motion_chain("clip_b", 4.0)


def test_the_two_motion_lists_have_not_drifted() -> None:
    """AI 장면 그림 쪽과 이름이 어긋나면 같은 것을 두 이름으로 부르게 된다.

    거기서 import하지 않는 것은 그 모듈이 제공자 인터페이스까지 끌고 오기
    때문이다 -- 조정값 파일은 렌더·API·화면이 다 부르는 잎이다. 그래서 사람
    기억 대신 여기서 맞대어 본다(전환 목록이 쓰는 방식과 같다).
    """
    from videobox_core_engine.media_controls import PHOTO_MOTIONS
    from videobox_core_engine.scene_image_service import SCENE_MOTIONS

    assert PHOTO_MOTIONS == SCENE_MOTIONS
