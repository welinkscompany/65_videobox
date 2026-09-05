"""유진이 글꼴을 고를 수 있다 — owner 지시 2026-09-05.

> "유진이가 폰트, 음악, 효과들 이런 모든것들을 전부 추천해서 자동으로 편집
> 추천을 할수 있게 해줘"

세어 보니 **음악·효과음·B-roll·색감·속도·자르기·전환은 이미 됐고 글꼴만
빈칸이었다**(`apply_media`, `set_scene_look`, `set_scene_speed`…).
그래서 여기만 채운다.

**장면별이 아니라 편집본 전체다.** 자막 모양은 원래 그렇게 걸린다
(`update_caption_style`의 `whole_project`). 장면마다 글꼴이 달라지면
한 영상 안에서 자막이 춤춘다 -- 창작자가 그걸 원하면 화면에서 직접 고른다.

**지어낸 글꼴 이름은 막는다.** 없는 글꼴은 완성본에서 조용히 다른 글꼴로
떨어진다(`caption_fonts.py`가 처음부터 그 사고를 막으려고 만들어졌다).
그래서 이 기계에 실제로 있는 것만 통과시킨다.
"""

from __future__ import annotations

from videobox_core_engine.editing_session import (
    _apply_yujin_editing_operations,
    build_editing_session,
    update_caption_style,
)
from videobox_core_engine.yujin_editing_proposal_service import YujinEditingContext, interpret_yujin_editing_request
from videobox_domain_models.caption_fonts import caption_font_catalog


def _context() -> YujinEditingContext:
    return YujinEditingContext(
        session_id="session-1",
        session_revision=3,
        segment_ids=("seg-1", "seg-2"),
        segment_ids_with_broll=("seg-1",),
    )


def _response(family: str) -> dict[str, object]:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "자막 글꼴을 바꾸는 편집안을 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{"intent": "set_caption_font", "family": family}],
        },
    }


def test_yujin_can_choose_a_font_that_is_actually_installed() -> None:
    installed = caption_font_catalog()
    assert installed, "이 기계에 글꼴이 하나도 없으면 이 시험은 아무것도 못 지킨다"
    family = str(installed[0]["family"])

    accepted = interpret_yujin_editing_request(_response(family), _context())

    assert accepted.status == "candidate_only"
    assert accepted.proposal is not None
    assert accepted.proposal.operations[0].family == family


def test_a_font_nobody_installed_is_refused_before_it_reaches_the_render() -> None:
    refused = interpret_yujin_editing_request(_response("Comic Sans Nope"), _context())

    # 사유를 구체적으로 준다 -- "잘못된 응답"이라고만 하면 유진이 무엇을 고쳐야
    # 할지 모른다.
    assert refused.reason == "caption_font_not_available"


def test_applying_the_font_changes_the_whole_project_not_one_scene() -> None:
    session = build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[{"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": "첫 장면"}],
    )
    family = str(caption_font_catalog()[0]["family"])
    proposal = interpret_yujin_editing_request(_response(family), _context()).proposal
    assert proposal is not None

    # **창작자가 이미 맞춰 둔 크기**를 걸어 두고 시작한다. 글꼴만 바꿔 달라고
    # 했는데 크기가 기본값으로 돌아가면 그게 사고다.
    session = update_caption_style(
        session=session, style={"font_size_px": 41}, scope="whole_project", segment_ids=[],
    )
    assert session["caption_style"]["font_size_px"] == 41

    applied = _apply_yujin_editing_operations(session=session, operations=tuple(proposal.operations))

    assert applied["caption_style"]["font_family"] == family
    assert applied["caption_style"]["font_size_px"] == 41


def _size_response(size_px: int) -> dict[str, object]:
    """**글꼴 이름 없이 크기만** 싣는다 -- "더 큰 걸로"가 딱 이 모양이다."""
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "자막을 더 크게 만드는 편집안을 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{"intent": "set_caption_font", "size_px": size_px}],
        },
    }


def test_yujin_can_change_only_the_size(tmp_path=None) -> None:
    """자막 **크기**를 말로 못 바꿨다 (2026-09-06).

    "자막 글꼴 좀 더 큰 걸로 바꿔줘"라고 하니 유진이 되물었다. 화면에는
    `font_size_px`가 있는데 `set_caption_font`는 `family`만 받았기 때문이다 --
    창작자가 당연히 할 말인데 말로는 되는 길이 없었다.
    """
    accepted = interpret_yujin_editing_request(_size_response(72), _context())

    assert accepted.status == "candidate_only"
    assert accepted.proposal is not None
    operation = accepted.proposal.operations[0]
    assert operation.size_px == 72
    # **이름은 비운다.** 채우면 창작자가 맞춰 둔 글꼴이 조용히 바뀐다.
    assert operation.family is None


def test_changing_only_the_size_keeps_the_font_the_creator_chose() -> None:
    session = build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[{"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": "첫 장면"}],
    )
    chosen = str(caption_font_catalog()[0]["family"])
    session = update_caption_style(
        session=session, style={"font_family": chosen, "font_size_px": 41},
        scope="whole_project", segment_ids=[],
    )
    proposal = interpret_yujin_editing_request(_size_response(72), _context()).proposal
    assert proposal is not None

    applied = _apply_yujin_editing_operations(session=session, operations=tuple(proposal.operations))

    assert applied["caption_style"]["font_size_px"] == 72
    assert applied["caption_style"]["font_family"] == chosen


def test_an_empty_font_change_is_refused() -> None:
    """이름도 크기도 없으면 아무것도 안 바뀐다 -- 성공한 척하지 않는다."""
    empty = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "바꿨어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{"intent": "set_caption_font"}],
        },
    }

    assert interpret_yujin_editing_request(empty, _context()).reason == "invalid_editing_response"


def test_a_size_outside_the_screen_range_is_refused() -> None:
    """화면이 받는 범위와 같아야 한다 -- 넓히면 렌더에서 터진다."""
    assert interpret_yujin_editing_request(_size_response(400), _context()).reason == "invalid_editing_response"
    assert interpret_yujin_editing_request(_size_response(4), _context()).reason == "invalid_editing_response"
