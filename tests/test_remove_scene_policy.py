"""빼기 정책 (2026-10-08 계획 H Task 12, 점검 §3-5). 기본은 구멍을 남기고 보여 준다.

두 길이 서버 한 곳에 있다: `leave_gap`(지금 출하 기본 = 오늘 동작 그대로)과
`ripple`(캡컷 주 트랙 자석처럼 뒤 장면을 당긴다). 화면(`PATCH …/cut-action`)과
유진(`SetCutActionOperation`)은 같은 `update_segment_cut_action`을 지나므로
정책은 상수 한 줄(`DEFAULT_REMOVE_MODE`)로 정해진다.
"""
from __future__ import annotations

import shutil
import subprocess
from copy import deepcopy

import pytest

from videobox_core_engine import editing_session as es
from videobox_core_engine.composition_plan import CompositionPlan, materialize_editing_session_timeline
from videobox_core_engine.editing_session import (
    DEFAULT_REMOVE_MODE,
    apply_yujin_editing_proposal,
    build_editing_session,
    redo,
    set_segment_bounds,
    undo,
    update_segment_cut_action,
)
from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest
from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal


def _session() -> dict:
    segments = [("s1", 0.0, 2.0), ("s2", 2.0, 3.7), ("s3", 3.7, 5.0)]
    return {"session_id": "e1", "project_id": "p", "timeline_id": "t", "session_revision": 1, "history": [],
            "segments": [{"segment_id": i, "caption_text": i, "start_sec": a, "end_sec": b, "cut_action": "keep"} for i, a, b in segments],
            "timeline_placement_overrides": {"broll:x": {"placement_id": "broll:x", "kind": "broll", "start_sec": 4.0, "end_sec": 4.5}}}


def _bounds(session: dict) -> list[tuple[str, float, float, str]]:
    return [(s["segment_id"], round(s["start_sec"], 6), round(s["end_sec"], 6), s["cut_action"]) for s in session["segments"]]


def _state(session: dict) -> dict:
    """되돌리기가 지키는 것 전부 (장면 + 배치)."""
    return {"segments": deepcopy(session["segments"]), "overrides": deepcopy(session.get("timeline_placement_overrides"))}


def _five() -> dict:
    segments = [("a", 0.0, 1.0), ("b", 1.0, 2.5), ("c", 2.5, 4.0), ("d", 4.0, 5.0), ("e", 5.0, 7.0)]
    return {"session_id": "e1", "project_id": "p", "timeline_id": "t", "session_revision": 1, "history": [],
            "segments": [{"segment_id": i, "caption_text": i, "start_sec": a, "end_sec": b, "cut_action": "keep"} for i, a, b in segments],
            "timeline_placement_overrides": {
                "before": {"placement_id": "before", "kind": "broll", "start_sec": 0.2, "end_sec": 0.8},
                "inside": {"placement_id": "inside", "kind": "broll", "start_sec": 1.2, "end_sec": 2.0},
                "straddle": {"placement_id": "straddle", "kind": "broll", "start_sec": 2.0, "end_sec": 3.0},
                "at_end": {"placement_id": "at_end", "kind": "sfx", "start_sec": 2.5, "end_sec": 2.7},
                "after": {"placement_id": "after", "kind": "broll", "start_sec": 5.5, "end_sec": 6.5},
            }}


# ---------------------------------------------------------------- 계약 (계획서 시험)

def test_the_shipped_default_is_leave_gap_until_the_owner_decides() -> None:
    assert DEFAULT_REMOVE_MODE == "leave_gap"


def test_leave_gap_keeps_later_scenes_in_place() -> None:
    updated = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="leave_gap")
    assert _bounds(updated) == [("s1", 0.0, 2.0, "keep"), ("s2", 2.0, 3.7, "remove"), ("s3", 3.7, 5.0, "keep")]


def test_ripple_pulls_later_scenes_and_placements_in_one_undo_step() -> None:
    updated = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    assert _bounds(updated) == [("s1", 0.0, 2.0, "keep"), ("s2", 2.0, 3.7, "remove"), ("s3", 2.0, 3.3, "keep")]
    assert updated["timeline_placement_overrides"]["broll:x"]["start_sec"] == pytest.approx(2.3)
    assert len(updated["history"]) == 1


def test_restoring_a_ripple_removed_scene_pushes_later_scenes_back() -> None:
    removed = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    restored = update_segment_cut_action(session=removed, segment_id="s2", cut_action="keep")
    assert _bounds(restored) == _bounds(_session())
    assert restored["timeline_placement_overrides"]["broll:x"]["start_sec"] == pytest.approx(4.0)
    assert "ripple_removed_sec" not in restored["segments"][1]


# ---------------------------------------------------------------- 기본값은 오늘 동작 그대로

def test_no_mode_given_behaves_exactly_like_the_shipped_default() -> None:
    plain = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove")
    explicit = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="leave_gap")
    assert _state(plain) == _state(explicit)
    assert "ripple_removed_sec" not in plain["segments"][1]
    assert plain["timeline_placement_overrides"] == _session()["timeline_placement_overrides"]


def test_unknown_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="remove_mode"):
        update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="shrink")  # type: ignore[arg-type]


def test_the_default_constant_is_the_one_place_that_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "DEFAULT_REMOVE_MODE", "ripple")
    updated = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove")
    assert _bounds(updated)[2] == ("s3", 2.0, 3.3, "keep")


def test_yujin_exclude_goes_through_the_same_function_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    def propose(action: str):
        return YujinEditingProposal.model_validate({
            "proposal_id": "p1", "base_session_revision": 1,
            "operations": [{"intent": "set_cut_action", "segment_id": "s2", "action": action}],
        })

    by_yujin = apply_yujin_editing_proposal(session=_session(), proposal=propose("exclude"))
    by_screen = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove")
    assert _state(by_yujin) == _state(by_screen)
    assert _bounds(by_yujin)[2] == ("s3", 3.7, 5.0, "keep")  # 기본 leave_gap

    # 상수를 ripple로 바꾸면 유진도 화면도 같이 당긴다 -- 유진 쪽에 정책 복사본이 없다.
    monkeypatch.setattr(es, "DEFAULT_REMOVE_MODE", "ripple")
    by_yujin = apply_yujin_editing_proposal(session=_session(), proposal=propose("exclude"))
    by_screen = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove")
    assert _state(by_yujin) == _state(by_screen)
    assert _bounds(by_yujin)[2] == ("s3", 2.0, 3.3, "keep")
    restored = apply_yujin_editing_proposal(session=by_yujin, proposal=propose("restore"))
    assert _bounds(restored) == _bounds(_session())


# ---------------------------------------------------------------- 되돌리기 = 한 칸, 정확히 원래대로

@pytest.mark.parametrize("mode", ["leave_gap", "ripple"])
def test_undo_restores_the_exact_prior_state_in_one_step(mode: str) -> None:
    before = _five()
    removed = update_segment_cut_action(session=before, segment_id="b", cut_action="remove", remove_mode=mode)
    assert len(removed["undo_stack"]) == 1
    assert removed["undo_stack"][-1]["remove_mode"] == mode
    restored = undo(session=removed)
    assert _state(restored) == _state(before)
    assert restored["undo_stack"] == []
    assert len(restored["redo_stack"]) == 1


@pytest.mark.parametrize("mode", ["leave_gap", "ripple"])
def test_repeated_remove_undo_redo_never_drifts(mode: str) -> None:
    before = _five()
    session = before
    after_remove = None
    for _ in range(4):
        session = update_segment_cut_action(session=session, segment_id="c", cut_action="remove", remove_mode=mode)
        after_remove = after_remove or _state(session)
        assert _state(session) == after_remove
        session = undo(session=session)
        assert _state(session) == _state(before)
        session = redo(session=session)
        assert _state(session) == after_remove
        session = undo(session=session)
        assert _state(session) == _state(before)
    assert session["undo_stack"] == []


def test_undoing_a_ripple_restore_brings_the_pulled_layout_back() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    restored = update_segment_cut_action(session=removed, segment_id="b", cut_action="keep")
    assert _state(undo(session=restored)) == _state(removed)


# ---------------------------------------------------------------- 첫·가운데·마지막 장면

def test_ripple_removing_the_first_scene_pulls_everything_to_zero() -> None:
    updated = update_segment_cut_action(session=_five(), segment_id="a", cut_action="remove", remove_mode="ripple")
    assert _bounds(updated) == [("a", 0.0, 1.0, "remove"), ("b", 0.0, 1.5, "keep"), ("c", 1.5, 3.0, "keep"), ("d", 3.0, 4.0, "keep"), ("e", 4.0, 6.0, "keep")]


def test_ripple_removing_the_middle_scene_leaves_earlier_scenes_alone() -> None:
    updated = update_segment_cut_action(session=_five(), segment_id="c", cut_action="remove", remove_mode="ripple")
    assert _bounds(updated) == [("a", 0.0, 1.0, "keep"), ("b", 1.0, 2.5, "keep"), ("c", 2.5, 4.0, "remove"), ("d", 2.5, 3.5, "keep"), ("e", 3.5, 5.5, "keep")]
    assert updated["segments"][2]["ripple_removed_sec"] == pytest.approx(1.5)


def test_ripple_removing_the_last_scene_changes_nothing_else() -> None:
    updated = update_segment_cut_action(session=_five(), segment_id="e", cut_action="remove", remove_mode="ripple")
    assert _bounds(updated)[:4] == _bounds(_five())[:4]
    assert _bounds(updated)[4] == ("e", 5.0, 7.0, "remove")


# ---------------------------------------------------------------- 배치(override)가 뒤에 있을 때 / 겹칠 때

def test_ripple_moves_only_placements_at_or_after_the_removed_end_and_leaves_overlapping_ones() -> None:
    # 뺀 장면 b = 1.0~2.5, D = 1.5
    updated = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    placed = {k: (round(v["start_sec"], 6), round(v["end_sec"], 6)) for k, v in updated["timeline_placement_overrides"].items()}
    assert placed == {
        "before": (0.2, 0.8),        # 앞: 그대로
        "inside": (1.2, 2.0),        # 뺀 자리 안에 통째로 들어간 것: 그대로 (보고 대상)
        "straddle": (2.0, 3.0),      # 걸친 것: 그대로 (보고 대상)
        "at_end": (1.0, 1.2),        # 시작이 뺀 장면 끝과 같으면 뒤로 본다 -> 당김
        "after": (4.0, 5.0),         # 뒤: 당김
    }


def test_restore_moves_back_exactly_the_placements_the_removal_moved() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    restored = update_segment_cut_action(session=removed, segment_id="b", cut_action="keep")
    # 뺄 때 안 건드린 겹친 배치(inside/straddle)는 되살릴 때도 안 건드린다.
    assert restored["timeline_placement_overrides"] == _five()["timeline_placement_overrides"]
    assert _bounds(restored) == _bounds(_five())


def test_restore_without_the_remembered_ids_falls_back_to_the_start_threshold() -> None:
    removed = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    removed["segments"][1].pop("ripple_shifted_placement_ids", None)
    restored = update_segment_cut_action(session=removed, segment_id="s2", cut_action="keep")
    assert restored["timeline_placement_overrides"]["broll:x"]["start_sec"] == pytest.approx(4.0)


def test_session_without_any_placements_ripples_fine() -> None:
    session = _five()
    session.pop("timeline_placement_overrides")
    updated = update_segment_cut_action(session=session, segment_id="b", cut_action="remove", remove_mode="ripple")
    assert "timeline_placement_overrides" not in updated
    assert undo(session=updated).get("timeline_placement_overrides") is None


# ---------------------------------------------------------------- 여러 장면을 잇달아

def test_two_ripple_removals_in_sequence_then_restoring_in_either_order_returns_to_start() -> None:
    first = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    second = update_segment_cut_action(session=first, segment_id="d", cut_action="remove", remove_mode="ripple")
    kept = [(s["segment_id"], round(s["start_sec"], 6), round(s["end_sec"], 6)) for s in second["segments"] if s["cut_action"] == "keep"]
    # 남은 장면 a, c, e가 틈 없이 이어진다: 1.0 + 1.5 + 2.0 = 4.5초
    assert kept == [("a", 0.0, 1.0), ("c", 1.0, 2.5), ("e", 2.5, 4.5)]
    for order in (("b", "d"), ("d", "b")):
        session = second
        for segment_id in order:
            session = update_segment_cut_action(session=session, segment_id=segment_id, cut_action="keep")
        assert _bounds(session) == _bounds(_five()), order
        assert session["timeline_placement_overrides"] == _five()["timeline_placement_overrides"], order
        assert all("ripple_removed_sec" not in s for s in session["segments"])


def test_removing_an_already_removed_scene_again_does_not_pull_twice() -> None:
    once = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    twice = update_segment_cut_action(session=once, segment_id="b", cut_action="remove", remove_mode="ripple")
    assert _bounds(twice) == _bounds(once)
    assert twice["segments"][1]["ripple_removed_sec"] == pytest.approx(1.5)


def test_restoring_a_scene_removed_in_leave_gap_mode_moves_nothing() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="leave_gap")
    restored = update_segment_cut_action(session=removed, segment_id="b", cut_action="keep", remove_mode="ripple")
    assert _state(restored) == _state(_five())


def test_restore_follows_how_the_scene_was_removed_not_the_current_default() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    # 지금 기본이 leave_gap이어도 당겨서 뺀 장면은 다시 밀어 넣는다 -- 안 그러면 겹친다.
    restored = update_segment_cut_action(session=removed, segment_id="b", cut_action="keep", remove_mode="leave_gap")
    assert _bounds(restored) == _bounds(_five())


def test_trim_instead_of_keep_also_reopens_the_space() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="b", cut_action="remove", remove_mode="ripple")
    reopened = update_segment_cut_action(session=removed, segment_id="b", cut_action="trim")
    assert [s[1:3] for s in _bounds(reopened)] == [s[1:3] for s in _bounds(_five())]


# ---------------------------------------------------------------- 최소 길이 · 경계 검사

def test_validate_bounds_ignores_removed_scenes_for_overlap_but_not_for_duration() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="c", cut_action="remove", remove_mode="leave_gap")
    # 이웃 b를 뺀 장면 c 자리(2.5~4.0) 안으로 늘려도 거절하지 않는다.
    widened = set_segment_bounds(session=removed, segment_id="b", start_sec=1.0, end_sec=3.0)
    assert widened["segments"][1]["end_sec"] == pytest.approx(3.0)
    # 켜 있는 장면끼리는 여전히 겹치면 거절한다.
    with pytest.raises(ValueError, match="overlap"):
        set_segment_bounds(session=removed, segment_id="b", start_sec=1.0, end_sec=4.5)
    # 최소 길이는 뺀 장면에도 그대로 지킨다.
    broken = deepcopy(removed)
    broken["segments"][2]["end_sec"] = broken["segments"][2]["start_sec"] + 0.1
    with pytest.raises(ValueError, match="at least"):
        set_segment_bounds(session=broken, segment_id="a", start_sec=0.0, end_sec=1.0)


def test_after_ripple_the_pulled_scene_can_be_trimmed_even_though_it_sits_on_the_removed_span() -> None:
    removed = update_segment_cut_action(session=_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    trimmed = set_segment_bounds(session=removed, segment_id="s3", start_sec=2.0, end_sec=3.0)
    assert (trimmed["segments"][2]["start_sec"], trimmed["segments"][2]["end_sec"]) == (2.0, 3.0)


def test_restore_that_would_overlap_a_scene_stretched_into_the_hole_is_refused() -> None:
    removed = update_segment_cut_action(session=_five(), segment_id="c", cut_action="remove", remove_mode="leave_gap")
    widened = set_segment_bounds(session=removed, segment_id="b", start_sec=1.0, end_sec=3.0)
    with pytest.raises(ValueError, match="overlap"):
        update_segment_cut_action(session=widened, segment_id="c", cut_action="keep")


# ---------------------------------------------------------------- 매니페스트: 빈 구간 수

def _timeline() -> dict:
    clips = lambda prefix: [  # noqa: E731
        {"clip_id": f"{prefix}-1", "segment_id": "s1", "asset_uri": f"local://{prefix}-1", "start_sec": 0.0, "end_sec": 2.0},
        {"clip_id": f"{prefix}-2", "segment_id": "s2", "asset_uri": f"local://{prefix}-2", "start_sec": 2.0, "end_sec": 3.7},
        {"clip_id": f"{prefix}-3", "segment_id": "s3", "asset_uri": f"local://{prefix}-3", "start_sec": 3.7, "end_sec": 5.0},
    ]
    return {"project_id": "p", "timeline_id": "t", "version": "v001", "output": {"width": 1280, "height": 720, "duration_sec": 5.0},
            "tracks": [{"track_type": "narration", "clips": clips("narration")}, {"track_type": "broll", "clips": clips("broll")}]}


def _real_session(timeline: dict | None = None) -> dict:
    return _with_ids(build_editing_session(
        project_id="p", timeline=timeline or _timeline(),
        segments=[
            {"segment_id": "s1", "text": "하나", "start_sec": 0.0, "end_sec": 2.0},
            {"segment_id": "s2", "text": "둘", "start_sec": 2.0, "end_sec": 3.7},
            {"segment_id": "s3", "text": "셋", "start_sec": 3.7, "end_sec": 5.0},
        ],
    ))


def _with_ids(session: dict) -> dict:
    return {**session, "session_id": "e1", "timeline_id": "t"}


def _manifest(session: dict, timeline: dict | None = None) -> dict:
    return build_editor_playback_manifest(
        project_id="p", session=session, timeline=timeline or _timeline(), asset_content_url_prefix="/api/projects/p/assets",
    )


def _removed_gaps(manifest: dict) -> list[dict]:
    return [g for g in manifest["gap_slots"] if str(g["gap_id"]).startswith("removed:")]


def test_manifest_counts_the_hole_a_leave_gap_removal_leaves() -> None:
    session = update_segment_cut_action(session=_real_session(), segment_id="s2", cut_action="remove", remove_mode="leave_gap")
    gaps = _removed_gaps(_manifest(session))
    assert gaps == [{"gap_id": "removed:s2", "segment_id": "s2", "start_sec": 2.0, "end_sec": 3.7, "reason": "removed_scene"}]


def test_manifest_has_no_removed_scene_gap_after_a_ripple_removal() -> None:
    session = update_segment_cut_action(session=_real_session(), segment_id="s2", cut_action="remove", remove_mode="ripple")
    assert _removed_gaps(_manifest(session)) == []


def test_manifest_has_no_removed_scene_gap_when_nothing_was_removed() -> None:
    assert _removed_gaps(_manifest(_real_session())) == []


def test_manifest_cuts_the_hole_that_lies_beyond_the_output_end() -> None:
    session = update_segment_cut_action(session=_real_session(), segment_id="s3", cut_action="remove", remove_mode="leave_gap")
    # 마지막 장면을 빼면 출력이 s2에서 끝나므로 그 뒤는 구멍이 아니다.
    assert _removed_gaps(_manifest(session)) == []


def test_manifest_counts_a_removed_first_scene_and_two_separate_holes() -> None:
    session = update_segment_cut_action(session=_real_session(), segment_id="s1", cut_action="remove", remove_mode="leave_gap")
    assert [(g["gap_id"], g["start_sec"], g["end_sec"]) for g in _removed_gaps(_manifest(session))] == [("removed:s1", 0.0, 2.0)]


def test_manifest_hole_shrinks_to_what_a_neighbour_does_not_cover() -> None:
    session = update_segment_cut_action(session=_real_session(), segment_id="s2", cut_action="remove", remove_mode="leave_gap")
    session = set_segment_bounds(session=session, segment_id="s1", start_sec=0.0, end_sec=2.5)
    gaps = _removed_gaps(_manifest(session))
    assert [(g["start_sec"], g["end_sec"]) for g in gaps] == [(2.5, 3.7)]


# ---------------------------------------------------------------- 소비자: 당긴 시각을 같이 읽는가 (내레이션·자막 포함)

def _clip(materialized: dict, track_type: str, clip_id: str) -> dict:
    return next(c for t in materialized["tracks"] if t["track_type"] == track_type for c in t["clips"] if c["clip_id"] == clip_id)


def test_ripple_moves_the_narration_audio_captions_and_broll_of_later_scenes_together() -> None:
    timeline = _timeline()
    base = materialize_editing_session_timeline(timeline=timeline, editing_session=_real_session(timeline), project_id="p")
    ripple = materialize_editing_session_timeline(
        timeline=timeline, project_id="p",
        editing_session=update_segment_cut_action(session=_real_session(timeline), segment_id="s2", cut_action="remove", remove_mode="ripple"),
    )
    gap = materialize_editing_session_timeline(
        timeline=timeline, project_id="p",
        editing_session=update_segment_cut_action(session=_real_session(timeline), segment_id="s2", cut_action="remove", remove_mode="leave_gap"),
    )
    for track_type in ("narration", "broll"):
        # 뺀 장면의 소리와 그림은 둘 다 없다.
        for materialized in (ripple, gap):
            ids = {c["clip_id"] for t in materialized["tracks"] if t["track_type"] == track_type for c in t["clips"]}
            assert f"{track_type}-2" not in ids
        s3_before, s3_ripple, s3_gap = (_clip(m, track_type, f"{track_type}-3") for m in (base, ripple, gap))
        # leave_gap: 오늘과 같다 (3.7~5.0).
        assert (s3_gap["start_sec"], s3_gap["end_sec"]) == (3.7, 5.0)
        # ripple: 그림도 소리도 같은 만큼(1.7초) 당겨진다. 원본에서 읽는 구간(source_in/out)은 그대로다.
        assert (s3_ripple["start_sec"], s3_ripple["end_sec"]) == (pytest.approx(2.0), pytest.approx(3.3))
        assert s3_ripple["source_in_sec"] == pytest.approx(s3_before["source_in_sec"])
        assert s3_ripple["source_out_sec"] == pytest.approx(s3_before["source_out_sec"])
        assert s3_ripple["source_in_sec"] == pytest.approx(s3_gap["source_in_sec"])
        # 앞 장면은 안 움직인다.
        assert _clip(ripple, track_type, f"{track_type}-1")["end_sec"] == 2.0
    cue = next(c for c in ripple["session_captions"] if c["segment_id"] == "s3")
    assert (cue["start_sec"], cue["end_sec"]) == (pytest.approx(2.0), pytest.approx(3.3))
    assert not any(c["segment_id"] == "s2" for c in ripple["session_captions"])
    # 영상 길이는 뺀 만큼 짧아진다. leave_gap은 그대로다.
    from videobox_core_engine.composition_plan import materialized_timeline_duration_sec
    assert materialized_timeline_duration_sec(ripple) == pytest.approx(3.3)
    assert materialized_timeline_duration_sec(gap) == pytest.approx(5.0)


def test_ripple_narration_stays_attached_to_its_scene_when_the_scene_was_trimmed_before() -> None:
    timeline = _timeline()
    session = set_segment_bounds(session=_real_session(timeline), segment_id="s3", start_sec=4.0, end_sec=5.0)
    gap = materialize_editing_session_timeline(
        timeline=timeline, project_id="p",
        editing_session=update_segment_cut_action(session=session, segment_id="s2", cut_action="remove", remove_mode="leave_gap"),
    )
    ripple = materialize_editing_session_timeline(
        timeline=timeline, project_id="p",
        editing_session=update_segment_cut_action(session=session, segment_id="s2", cut_action="remove", remove_mode="ripple"),
    )
    left, right = _clip(gap, "narration", "narration-3"), _clip(ripple, "narration", "narration-3")
    assert right["source_in_sec"] == pytest.approx(left["source_in_sec"]) and right["source_in_sec"] == pytest.approx(0.3)
    assert right["end_sec"] - right["start_sec"] == pytest.approx(left["end_sec"] - left["start_sec"])


def test_ripple_composition_plan_and_render_graph_read_the_pulled_times() -> None:
    timeline = _timeline()
    session = update_segment_cut_action(session=_real_session(timeline), segment_id="s2", cut_action="remove", remove_mode="ripple")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=session, project_id="p")
    plan = CompositionPlan.from_timeline(timeline=materialized, captions=materialized["session_captions"])
    assert plan.duration_sec == pytest.approx(3.3)
    narration = {item.clip_id: item for item in plan.items if item.track_type == "narration"}
    assert set(narration) == {"narration-1", "narration-3"}
    assert (narration["narration-3"].start_sec, narration["narration-3"].end_sec) == (pytest.approx(2.0), pytest.approx(3.3))
    assert [(c.start_sec, c.end_sec) for c in plan.captions] == [(pytest.approx(0.0), pytest.approx(2.0)), (pytest.approx(2.0), pytest.approx(3.3))]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required to make local export sources")
def test_capcut_export_places_the_pulled_scene_right_after_the_previous_one(tmp_path) -> None:
    import json
    from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
    from videobox_domain_models.assets import AssetType
    from videobox_storage.local_project_store import LocalProjectStore

    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="Remove ripple CapCut")
    narration_path, broll_path = tmp_path / "narration.wav", tmp_path / "broll.mp4"
    for command in (
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(narration_path)],
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=240x320:rate=15", str(broll_path)],
    ):
        subprocess.run(command, check=True, capture_output=True, text=True)
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_path)
    source = {
        "project_id": project.project_id, "timeline_id": "timeline-remove-capcut", "narration_source_uri": narration.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [
                {"clip_id": f"voice-{i}", "segment_id": f"sc{i}", "asset_uri": f"local://projects/{project.project_id}/segments/sc{i}", "start_sec": 2.0 * (i - 1), "end_sec": 2.0 * i}
                for i in (1, 2, 3)]},
            {"track_type": "broll", "clips": [
                {"clip_id": f"video-{i}", "segment_id": f"sc{i}", "asset_uri": broll.storage_uri, "start_sec": 2.0 * (i - 1), "end_sec": 2.0 * i}
                for i in (1, 2, 3)]},
        ],
    }
    session = build_editing_session(
        project_id=project.project_id, timeline=source,
        segments=[{"segment_id": f"sc{i}", "text": f"장면{i}", "start_sec": 2.0 * (i - 1), "end_sec": 2.0 * i} for i in (1, 2, 3)],
    )
    session = update_segment_cut_action(session=session, segment_id="sc2", cut_action="remove", remove_mode="ripple")
    materialized = materialize_editing_session_timeline(timeline=source, editing_session=session, project_id=project.project_id)
    result = PyCapCutRealExportAdapter(store=store, video_width=320, video_height=240).export_timeline(
        project_id=project.project_id, timeline=materialized, drafts_root=tmp_path / "drafts",
        draft_name="remove-ripple", editing_session=session,
    )
    content = json.loads((result.draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}
    for name in ("voiceover", "broll"):
        starts = [(seg["target_timerange"]["start"], seg["target_timerange"]["duration"]) for seg in tracks[name]]
        assert starts == [(0, 2_000_000), (2_000_000, 2_000_000)], name
