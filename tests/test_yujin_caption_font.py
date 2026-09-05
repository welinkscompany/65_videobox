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
