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


def test_a_scene_with_no_recording_does_not_reach_the_render_as_a_sound_source() -> None:
    """녹음이 없는 장면 막대는 **소리가 아니라 자리**다.

    빈 편집판에서 시작하면 목소리가 없다. 그래도 타임라인에는 장면마다 가상
    내레이션 클립이 생긴다(편집기가 그리는 그 막대). 그 막대가 완성본 만드는
    쪽까지 `읽을 오디오`로 넘어가면 열 수 없는 파일을 찾다가 렌더가 통째로
    멈춘다. 화면에는 남기고, 완성본 계획에서만 뺀다.
    """
    from videobox_core_engine.composition_plan import CompositionPlan

    timeline = {
        "output": {"width": 1920, "height": 1080, "duration_sec": 5.0},
        "tracks": [
            {"track_type": "narration", "track_id": "narration_primary", "clips": [{
                "clip_id": "clip_narration_001", "segment_id": "timeline_001:001",
                "asset_uri": "local://projects/p1/segments/timeline_001:001",
                "start_sec": 0.0, "end_sec": 5.0,
            }]},
            {"track_type": "broll", "track_id": "broll_overlay", "clips": [{
                "clip_id": "clip_broll_001", "segment_id": "timeline_001:001",
                "asset_id": "asset_scene", "asset_uri": "local://projects/p1/assets/asset_scene",
                "start_sec": 0.0, "end_sec": 5.0,
            }]},
        ],
    }

    plan = CompositionPlan.from_timeline(timeline=timeline)

    assert [item.track_type for item in plan.items] == ["broll"]


def test_a_scene_whose_recording_exists_still_reaches_the_render() -> None:
    """녹음이 있으면 그 막대는 여전히 소리다. 위 규칙이 목소리를 지우면 안 된다."""
    from videobox_core_engine.composition_plan import CompositionPlan

    timeline = {
        "narration_source_uri": "local://projects/p1/assets/asset_narration",
        "output": {"width": 1920, "height": 1080, "duration_sec": 5.0},
        "tracks": [
            {"track_type": "narration", "track_id": "narration_primary", "clips": [{
                "clip_id": "clip_narration_001", "segment_id": "timeline_001:001",
                "asset_uri": "local://projects/p1/segments/timeline_001:001",
                "start_sec": 0.0, "end_sec": 5.0,
            }]},
        ],
    }

    plan = CompositionPlan.from_timeline(timeline=timeline)

    assert [item.track_type for item in plan.items] == ["narration"]
