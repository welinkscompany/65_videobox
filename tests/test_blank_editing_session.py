"""빈 편집판으로 편집기를 여는 길.

캡컷은 새 프로젝트를 열면 빈 편집판이 뜨고 거기에 재료를 끌어다 놓는다. 우리는
편집 세션을 만드는 길이 둘뿐이었고 **둘 다 기획을 통과해야 했다** -- 기획 산출물
(`timeline_job_id`)이나 대본(`script_asset_id`). 그래서 owner가 편집기를 열면
`먼저 영상 초안을 만들어 주세요`라는 잠긴 문을 만났다(2026-08-17 owner 지시로 착수).

**빈 편집판은 내보낼 수 있는 물건이 아니다.** 아직 아무것도 안 들어 있으므로
`review_required`로 표시해 두어, 채우기 전에 완성본으로 나가지 않게 한다.
"""

import pytest

from videobox_core_engine.blank_editing_session import build_blank_editing_session


def test_a_blank_session_opens_with_one_scene_you_can_edit() -> None:
    session = build_blank_editing_session(project_id="p1")

    segments = session["segments"]
    assert len(segments) == 1, "편집판이 완전히 비어 있으면 고를 것도, 나눌 것도 없다"
    scene = segments[0]
    assert scene["start_sec"] == 0
    assert scene["end_sec"] > 0, "길이가 0이면 타임라인에 그려지지 않는다"
    assert scene["cut_action"] == "keep"
    assert scene["broll_override"] is None
    assert scene["caption_text"] == ""


def test_a_blank_session_says_it_is_not_ready_to_go_out() -> None:
    # 안전장치. 아무것도 안 들어 있는 것을 조용히 완성본으로 내보내면 안 된다.
    session = build_blank_editing_session(project_id="p1")

    assert session["segments"][0]["review_required"] is True


def test_two_blank_sessions_do_not_collide() -> None:
    # timeline_id가 같으면 두 번째가 첫 번째를 덮어쓴다.
    first = build_blank_editing_session(project_id="p1")
    second = build_blank_editing_session(project_id="p1")

    assert first["timeline_id"] != second["timeline_id"]
    assert first["timeline_id"].startswith("blank:")


def test_a_blank_session_carries_the_same_shape_the_editor_already_reads() -> None:
    session = build_blank_editing_session(project_id="p1")

    for key in ("project_id", "timeline_id", "segments", "history", "undo_stack", "redo_stack", "session_revision"):
        assert key in session, key
    assert session["project_id"] == "p1"
    assert session["session_revision"] == 1
    assert session["history"] == []


def test_a_blank_session_needs_a_project() -> None:
    with pytest.raises(ValueError):
        build_blank_editing_session(project_id="  ")
