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


# --- 엔진 위 층: 화면과 유진 ------------------------------------------------
#
# 엔진이 값을 받는 것은 절반이다. 이 저장소가 되풀이한 사고 그대로 -- 조정 칸
# 하나를 더하면 손댈 자리가 일곱이고, 그중 둘은 전체 pytest에서만 걸린다.


def test_the_editor_screen_can_read_a_clip_that_chose_a_motion() -> None:
    """**응답 모델이 `extra="forbid"`다.** 여기 칸이 없으면 한 번 고른 클립의
    편집기 화면이 통째로 안 열린다 -- 조용히 빠지는 게 아니라 응답이 터진다
    (2026-09-01에 손떨림 보정으로 실제로 겪었다).
    """
    from videobox_api.models import EditorMediaControlsResponse

    assert EditorMediaControlsResponse(photo_motion="pan_left").photo_motion == "pan_left"


def test_the_save_request_carries_the_chosen_motion() -> None:
    """화면이 보낸 값이 저장까지 간다. 명령 포트에서 빠뜨리면 "저장했어요"까지
    떠 놓고 값만 사라진다(색감이 2026-08-23에 그랬다).
    """
    from videobox_core_engine.editing_session import update_segment_broll_override

    session = {
        "session_revision": 1,
        "segments": [{
            "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0,
            "broll_override": {"asset_id": "broll_001"},
        }],
    }

    saved = update_segment_broll_override(
        session=session, segment_id="seg_001", asset_id="broll_001",
        media_controls={"photo_motion": "zoom_out"},
    )

    controls = saved["segments"][0]["broll_override"]["media_controls"]
    assert controls["photo_motion"] == "zoom_out"


def _yujin_payload(motion: str, segment_id: str = "seg_001") -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "사진 움직임을 바꿔 볼게요.",
        "proposal": {
            "proposal_id": "motion",
            "base_session_revision": 1,
            "operations": [{"intent": "set_photo_motion", "segment_id": segment_id, "motion": motion}],
        },
    }


def _yujin_context():
    from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext

    return YujinEditingContext(
        session_id="s", session_revision=1, segment_ids=("seg_001",),
        segment_ids_with_broll=("seg_001",),
    )


def test_yujin_can_ask_for_a_motion() -> None:
    from videobox_core_engine.yujin_editing_proposal_adapter import interpret_yujin_editing_request

    result = interpret_yujin_editing_request(_yujin_payload("pan_right"), _yujin_context())

    assert result.status == "candidate_only"
    assert result.proposal is not None
    assert result.proposal.operations[0].motion == "pan_right"


def test_yujin_cannot_make_up_a_motion() -> None:
    """지어낸 이름은 검증기가 막는다 -- 색감·전환과 같은 자리다."""
    from videobox_core_engine.yujin_editing_proposal_adapter import interpret_yujin_editing_request

    result = interpret_yujin_editing_request(_yujin_payload("spin"), _yujin_context())

    assert result.status == "rejected"
    assert result.reason == "photo_motion_not_available"


def test_yujin_cannot_move_a_photo_that_is_not_there() -> None:
    """화면이 안 깔린 장면에는 걸 수 없다 -- 색감과 같은 이유다."""
    from videobox_core_engine.yujin_editing_proposal_adapter import (
        YujinEditingContext,
        interpret_yujin_editing_request,
    )

    empty = YujinEditingContext(session_id="s", session_revision=1, segment_ids=("seg_001",))
    result = interpret_yujin_editing_request(_yujin_payload("pan_right"), empty)

    assert result.status == "rejected"
    assert result.reason == "scene_look_needs_broll"


def test_the_prompt_gives_both_the_list_and_what_is_already_on() -> None:
    """**목록과 지금 걸린 값은 한 쌍이다.** 목록만 주면 "원래대로 돌려줘"에
    "걸린 게 없습니다"라고 답한다 -- 전환·색감 둘 다 그랬다(2026-09-06 실측).
    """
    from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
    from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext

    prompt = _editing_prompt(
        instruction="사진 천천히 확대해줘",
        context=YujinEditingContext(
            session_id="s", session_revision=1, segment_ids=("seg_001",),
            segment_ids_with_broll=("seg_001",),
            photo_motions_by_segment=(("seg_001", "zoom_in"),),
        ),
    )

    assert "set_photo_motion" in prompt
    assert "천천히 다가가기" in prompt, "코드만 주면 '천천히 확대'를 못 옮긴다"
    assert "지금 움직임이 걸린 장면: seg_001(zoom_in)" in prompt
