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


def test_the_blank_timeline_stores_no_length_for_anyone_to_misread() -> None:
    """**빈 편집판은 타임라인 문서에 길이를 안 적는다.** 적어 두면 누군가 그걸 믿는다.

    적어 둔 5.0을 고쳐 주는 편집 문이 **하나도 없다** -- 장면을 넣고 쪼개고 경계를
    옮기는 일은 전부 세션에만 쌓인다. 그런데 그 값을 읽는 자리가 둘이나 생겨서
    두 번 연달아 같은 결함이 났다(2026-09-12):

    1. 눈금자가 120초 영상에서 5초만 그렸다.
    2. 조각을 옮길 때의 상한이 5초로 잠겨서 B-roll을 60초로 못 옮겼다.

    기획을 통과한 타임라인은 처음부터 이 칸을 안 적었다(`local_project_store`의
    `_ORIENTATION_OUTPUT_SIZES`는 가로·세로만 담는다). **빈 편집판만 적고 있었고,
    그래서 빈 편집판에서 시작한 프로젝트만 망가졌다.** 이제 길이는 한 자리에서
    조각을 보고 잰다(`materialized_timeline_duration_sec`). 이 칸을 되살리지 마라.
    """
    from videobox_core_engine.blank_editing_session import build_blank_timeline_payload

    payload = build_blank_timeline_payload()

    assert "duration_sec" not in payload["output"]
    assert payload["output"] == {"width": 1920, "height": 1080}


def test_a_freshly_opened_blank_board_still_measures_five_seconds() -> None:
    """길이를 안 적어도 **잃는 것이 없다.** 빈 장면이 그 5초를 들고 있다.

    저장된 숫자를 지우면 갓 연 편집판의 눈금자가 0이 될까 -- 아니다. 빈 편집판은
    0~5초 장면 하나로 열리고(`BLANK_SCENE_SECONDS`), 길이는 그 장면에서 재진다.
    다른 점은 하나다: 장면을 12초로 늘리면 이제 길이도 **같이 따라온다.**
    """
    from videobox_core_engine.blank_editing_session import (
        BLANK_SCENE_SECONDS,
        build_blank_editing_session,
        build_blank_timeline_payload,
    )
    from videobox_core_engine.composition_plan import (
        materialize_editing_session_timeline,
        materialized_timeline_duration_sec,
    )

    session = build_blank_editing_session(project_id="p1", timeline_id="timeline_001")
    timeline = {**build_blank_timeline_payload(), "project_id": "p1", "timeline_id": "timeline_001"}

    def measured(current_session: dict) -> float:
        return materialized_timeline_duration_sec(
            materialize_editing_session_timeline(
                timeline=timeline, editing_session=current_session, project_id="p1"
            )
        )

    assert measured(session) == BLANK_SCENE_SECONDS == 5.0

    session["segments"][0]["end_sec"] = 12.0
    assert measured(session) == 12.0
