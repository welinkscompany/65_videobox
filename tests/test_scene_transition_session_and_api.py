"""전환이 편집 세션에 저장되고, 저장한 것이 렌더 계획까지 도착하는가.

**부품을 만드는 것과 제품을 만드는 것은 다르다**(`CLAUDE.md` §4). 렌더러가
전환을 그릴 수 있다는 것만으로는 owner가 쓸 수 없다. 고른 값이 세션에 남고,
그 세션이 타임라인으로 펼쳐질 때 클립에 실려야 실제로 보인다.
"""

from __future__ import annotations

from typing import Any

import pytest

from videobox_core_engine.composition_plan import (
    CompositionPlan,
    materialize_editing_session_timeline,
)
from videobox_core_engine.editing_session import update_segment_transition


def _session() -> dict[str, Any]:
    return {
        "project_id": "p1",
        "timeline_id": "t1",
        "session_revision": 1,
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "segments": [
            {
                "segment_id": "seg-1", "caption_text": "첫 장면",
                "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep",
                "source_slices": [{"segment_id": "seg-1", "source_offset_sec": 0.0, "duration_sec": 4.0}],
                "broll_override": {"asset_id": "asset-a", "asset_uri": "local://a"},
            },
            {
                "segment_id": "seg-2", "caption_text": "둘째 장면",
                "start_sec": 4.0, "end_sec": 8.0, "cut_action": "keep",
                "source_slices": [{"segment_id": "seg-2", "source_offset_sec": 0.0, "duration_sec": 4.0}],
                "broll_override": {"asset_id": "asset-b", "asset_uri": "local://b"},
            },
        ],
    }


def _timeline() -> dict[str, Any]:
    return {
        "project_id": "p1", "timeline_id": "t1",
        "output": {"width": 1280, "height": 720},
        "tracks": [
            {"track_type": "narration", "clips": [
                {"segment_id": "seg-1", "asset_uri": "local://n1", "start_sec": 0.0, "end_sec": 4.0},
                {"segment_id": "seg-2", "asset_uri": "local://n2", "start_sec": 4.0, "end_sec": 8.0},
            ]},
        ],
    }


def test_choosing_a_transition_is_saved_on_the_scene_it_opens() -> None:
    updated = update_segment_transition(
        session=_session(), segment_id="seg-2",
        transition={"type": "wipeleft", "duration_sec": 0.8},
    )

    assert updated["segments"][1]["transition_in"] == {
        "type": "wipeleft", "duration_sec": 0.8, "chosen_by": "owner",
    }
    # 앞 장면은 건드리지 않는다. 경계 하나에 값이 두 벌이면 반드시 어긋난다.
    assert "transition_in" not in updated["segments"][0]


def test_turning_a_transition_back_off_removes_it() -> None:
    chosen = update_segment_transition(
        session=_session(), segment_id="seg-2", transition={"type": "fade"})
    cleared = update_segment_transition(
        session=chosen, segment_id="seg-2", transition=None)

    assert "transition_in" not in cleared["segments"][1]


def test_the_choice_can_be_undone() -> None:
    """편집기의 되돌리기가 전환에도 그대로 듣는다."""
    from videobox_core_engine.editing_session import undo

    chosen = update_segment_transition(
        session=_session(), segment_id="seg-2", transition={"type": "fade"})
    assert undo(session=chosen)["segments"][1].get("transition_in") is None


def test_an_unknown_transition_is_refused_before_it_is_stored() -> None:
    with pytest.raises(ValueError):
        update_segment_transition(
            session=_session(), segment_id="seg-2", transition={"type": "hologram_swirl"})


def test_the_saved_choice_reaches_the_broll_clip_that_opens_the_scene() -> None:
    """세션에 남긴 값이 **렌더가 읽는 클립**까지 간다. 여기가 끊기면 안 보인다."""
    session = update_segment_transition(
        session=_session(), segment_id="seg-2",
        transition={"type": "circleopen", "duration_sec": 0.6, "chosen_by": "yujin"},
    )
    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="p1")

    broll = next(t for t in materialized["tracks"] if t["track_type"] == "broll")
    opening = next(c for c in broll["clips"] if c["segment_id"] == "seg-2")
    assert opening["transition"]["type"] == "circleopen"
    # 누가 골랐는지가 끝까지 살아 있어야 유진 추천을 되돌릴 수 있다.
    assert opening["transition"]["chosen_by"] == "yujin"

    plan = CompositionPlan.from_timeline(timeline=materialized)
    item = next(i for i in plan.items if i.track_type == "broll" and i.clip_id == opening["clip_id"])
    assert item.transition == {"type": "circleopen", "duration_sec": 0.6, "chosen_by": "yujin"}


def test_a_removed_scene_carries_no_transition() -> None:
    """지운 장면의 전환이 남아 다른 경계에 붙으면 안 된다."""
    session = update_segment_transition(
        session=_session(), segment_id="seg-2", transition={"type": "fade"})
    session["segments"][1]["cut_action"] = "remove"
    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="p1")

    broll = next((t for t in materialized["tracks"] if t["track_type"] == "broll"), {"clips": []})
    assert all("transition" not in clip for clip in broll["clips"])


def test_a_range_preview_drops_a_transition_whose_boundary_is_cut_away() -> None:
    """구간 미리보기의 첫 프레임이 난데없이 전환으로 시작하면 안 된다."""
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720},
        "tracks": [{"track_type": "broll", "clips": [
            {"clip_id": "a", "asset_uri": "local://a", "start_sec": 0.0, "end_sec": 4.0},
            {"clip_id": "b", "asset_uri": "local://b", "start_sec": 4.0, "end_sec": 8.0,
             "transition": {"type": "fade"}},
        ]}],
    })

    # 경계(4.0)를 그대로 품은 구간 -- 전환은 살아 있다.
    kept = plan.for_range(start_sec=2.0, end_sec=6.0)
    assert next(i for i in kept.items if i.clip_id == "b").transition is not None
    # 경계를 잘라 낸 구간 -- 넘어올 앞 장면이 없으므로 전환도 없다.
    cut = plan.for_range(start_sec=5.0, end_sec=7.0)
    assert next(i for i in cut.items if i.clip_id == "b").transition is None
