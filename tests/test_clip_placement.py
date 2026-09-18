"""자유 멀티트랙 Phase 2 -- 놓인 클립을 세그먼트 정체성에서 떼어낸다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 2.

**아직 아무도 이 모델을 안 읽는다** -- Phase 1(`track_registry.py`)과 같은
덧붙이기 단계다. 렌더 경로(`composition_plan.py`)는 지금도 세그먼트의
`broll_override`/`music_override`/`sfx_override`를 그대로 읽는다.

여기서 지키는 것은 하나다: **이 새 모델이 지금 실제로 렌더되는 것과 같은
것을 말하는가.** 그럴듯해 보이는 평행우주를 만들어 놓고 Phase 4에서
렌더러를 갈아탈 때 어긋나는 것이 가장 비싼 실패다. 그래서 마지막 시험은
실제 `materialize_editing_session_timeline`과 결과를 맞대 본다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.clip_placement import (
    PlacedClip,
    VALID_CLIP_PLACEMENT_KINDS,
    ClipPlacementError,
    validate_placed_clips,
)
from videobox_core_engine.editing_session import FIXED_TIMELINE_TRACK_ROLES
from videobox_core_engine.track_registry import migrate_legacy_tracks_to_registry


def _legacy_tracks():
    return migrate_legacy_tracks_to_registry(FIXED_TIMELINE_TRACK_ROLES)


def _clip(clip_id: str, *, kind: str = "broll", track_id: str | None = None, start: float = 0.0, end: float = 4.0) -> PlacedClip:
    return PlacedClip(
        clip_id=clip_id, track_id=track_id or f"track-{kind}", kind=kind,
        asset_id=f"asset-{clip_id}", start_sec=start, end_sec=end,
    )


def test_a_placed_clip_knows_its_track_kind_and_absolute_window() -> None:
    clip = PlacedClip(
        clip_id="clip-1",
        track_id="track-broll",
        kind="broll",
        asset_id="asset-1",
        start_sec=0.0,
        end_sec=4.0,
    )

    assert clip.kind in VALID_CLIP_PLACEMENT_KINDS
    assert clip.end_sec > clip.start_sec


@pytest.mark.parametrize("kind", ["narration", "caption", "overlay", "", "video"])
def test_only_broll_bgm_sfx_can_be_placed_in_this_phase(kind: str) -> None:
    """내레이션·자막·오버레이는 Phase 3/7 몫이다. 지금 받아 주면 그 단계에서
    타이밍 기준 설계를 다시 열어야 한다."""
    with pytest.raises(ClipPlacementError):
        PlacedClip(clip_id="clip-1", track_id="track-x", kind=kind, asset_id="a", start_sec=0.0, end_sec=1.0)


@pytest.mark.parametrize(
    ("clip_id", "track_id", "asset_id"),
    [("", "track-broll", "a"), ("clip-1", "", "a"), ("clip-1", "track-broll", "")],
)
def test_a_clip_without_an_identity_is_refused(clip_id: str, track_id: str, asset_id: str) -> None:
    with pytest.raises(ClipPlacementError):
        PlacedClip(
            clip_id=clip_id, track_id=track_id, kind="broll", asset_id=asset_id,
            start_sec=0.0, end_sec=1.0,
        )


@pytest.mark.parametrize(("start_sec", "end_sec"), [(1.0, 1.0), (2.0, 1.0), (0.0, float("inf"))])
def test_a_window_that_is_not_a_real_span_is_refused(start_sec: float, end_sec: float) -> None:
    """길이가 없거나 뒤집힌 창은 렌더에서 조용히 사라진다 -- 여기서 막는다."""
    with pytest.raises(ClipPlacementError):
        PlacedClip(
            clip_id="clip-1", track_id="track-broll", kind="broll", asset_id="a",
            start_sec=start_sec, end_sec=end_sec,
        )


def test_clips_go_on_a_track_that_exists_and_matches_their_kind() -> None:
    """Phase 1의 트랙 목록과 짝이 맞아야 한다 -- 음악 클립이 효과음 줄에
    놓이면 렌더에서야 드러난다."""
    tracks = _legacy_tracks()

    validate_placed_clips([_clip("c1"), _clip("c2", kind="bgm"), _clip("c3", kind="sfx")], tracks=tracks)

    with pytest.raises(ClipPlacementError):
        validate_placed_clips([_clip("c1", track_id="track-does-not-exist")], tracks=tracks)
    with pytest.raises(ClipPlacementError):
        # 종류는 broll인데 놓인 줄은 음악 줄이다.
        validate_placed_clips([_clip("c1", track_id="track-bgm")], tracks=tracks)


def test_two_clips_cannot_share_one_identity() -> None:
    tracks = _legacy_tracks()

    with pytest.raises(ClipPlacementError):
        validate_placed_clips([_clip("same"), _clip("same", start=10.0, end=12.0)], tracks=tracks)


def test_one_track_can_hold_several_clips_as_long_as_they_do_not_overlap() -> None:
    """Phase 5(트랙 추가·삭제)가 기대는 성질이다. 고정 5트랙 시절에는 한 줄에
    여러 클립이 나란히 놓이는 것이 정상이었으므로 막으면 안 되고, 겹치는 것은
    렌더에서 어느 쪽이 이기는지 정해진 바가 없으므로 막아야 한다."""
    tracks = _legacy_tracks()

    validate_placed_clips([_clip("c1", start=0.0, end=4.0), _clip("c2", start=4.0, end=8.0)], tracks=tracks)

    with pytest.raises(ClipPlacementError):
        validate_placed_clips([_clip("c1", start=0.0, end=5.0), _clip("c2", start=4.0, end=8.0)], tracks=tracks)


def test_the_same_span_on_two_different_tracks_is_fine() -> None:
    """브롤이 도는 동안 음악이 같이 깔리는 것은 겹침이 아니라 정상이다."""
    tracks = _legacy_tracks()

    validate_placed_clips(
        [_clip("c1", kind="broll", start=0.0, end=4.0), _clip("c2", kind="bgm", start=0.0, end=4.0)],
        tracks=tracks,
    )


def _session(*, count: int = 2, seconds: float = 4.0) -> dict:
    """실제 `build_editing_session`이 만드는 세션. 손으로 지은 dict를 쓰면
    이 시험이 지키려는 대상(진짜 세션 모양)을 안 밟는다."""
    from videobox_core_engine.editing_session import build_editing_session

    segments = [
        {
            "segment_id": f"seg_{index + 1:03d}",
            "text": f"장면 {index + 1}",
            "start_sec": index * seconds,
            "end_sec": (index + 1) * seconds,
            "review_required": False,
            "cleanup_decision": "keep",
        }
        for index in range(count)
    ]
    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [{
            "track_id": "narration_primary",
            "track_type": "narration",
            "clips": [{
                "clip_id": f"clip_{segment['segment_id']}",
                "segment_id": segment["segment_id"],
                "asset_uri": f"local://projects/project_001/segments/{segment['segment_id']}",
                "start_sec": segment["start_sec"],
                "end_sec": segment["end_sec"],
                "clip_type": "narration",
            } for segment in segments],
        }],
        "review_flags": [],
        "pending_recommendations": [],
    }
    return build_editing_session(project_id="project_001", timeline=timeline, segments=segments)


def test_a_segment_with_one_broll_choice_becomes_one_placed_clip() -> None:
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.editing_session import update_segment_broll_override

    session = update_segment_broll_override(session=_session(), segment_id="seg_001", asset_id="broll-1")

    clips = migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks())

    assert len(clips) == 1
    clip = clips[0]
    assert (clip.kind, clip.asset_id, clip.track_id) == ("broll", "broll-1", "track-broll")
    # 절대 시각이다 -- 세그먼트를 다시 안 봐도 어디 놓였는지 알 수 있어야 한다.
    assert (clip.start_sec, clip.end_sec) == (0.0, 4.0)
    assert clip.source_segment_id == "seg_001"


def test_a_session_with_no_media_choices_places_nothing() -> None:
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips

    assert migrate_segment_media_to_placed_clips(segments=_session()["segments"], tracks=_legacy_tracks()) == []


def test_each_kind_resolves_on_its_own() -> None:
    """한 세그먼트에 브롤만 고르고 음악·효과음은 안 골랐다면 브롤 하나만
    나와야 한다 -- 셋이 한 창 구조를 같이 쓰는 탓에 유령 클립이 나기 쉽다."""
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.editing_session import update_segment_broll_override, update_segment_music_override

    session = update_segment_broll_override(session=_session(), segment_id="seg_001", asset_id="broll-1")
    session = update_segment_music_override(session=session, segment_id="seg_002", asset_id="music-1")

    clips = migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks())

    assert sorted((clip.kind, clip.source_segment_id) for clip in clips) == [
        ("bgm", "seg_002"), ("broll", "seg_001"),
    ]


def test_the_sfx_rejection_key_survives_the_move() -> None:
    """효과음만 `source_action_id`를 갖는다 -- owner가 거절한 그 삽입인지
    되짚는 열쇠라, 셋을 대칭으로 다루면 조용히 사라진다."""
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.editing_session import update_segment_sfx_override

    session = update_segment_sfx_override(session=_session(), segment_id="seg_001", asset_id="sfx-1")
    stamped = session["segments"][0]["sfx_override"]["source_action_id"]

    clips = migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks())

    assert stamped
    assert [clip.source_action_id for clip in clips] == [stamped]


def test_a_removed_segment_places_nothing() -> None:
    """잘라낸 장면의 브롤은 렌더에 안 나온다. 새 모델이 그것을 들고 있으면
    Phase 4에서 지운 장면이 되살아난다."""
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.editing_session import update_segment_broll_override

    session = update_segment_broll_override(session=_session(), segment_id="seg_001", asset_id="broll-1")
    session["segments"][0]["cut_action"] = "remove"

    assert migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks()) == []


def test_a_split_segment_keeps_each_window_where_it_was() -> None:
    """쪼갠 뒤에는 선택이 `media_windows`로 내려간다. 창의 시작 오프셋을
    무시하면 클립이 장면 앞머리로 밀린다."""
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.editing_session import split_segment, update_segment_broll_override

    session = update_segment_broll_override(session=_session(count=1, seconds=8.0), segment_id="seg_001", asset_id="broll-1")
    session = split_segment(session=session, segment_id="seg_001", split_sec=4.0)

    clips = migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks())

    spans = sorted((clip.start_sec, clip.end_sec) for clip in clips)
    assert spans == [(0.0, 4.0), (4.0, 8.0)]


def test_splitting_a_segment_with_an_overlay_does_not_duplicate_the_overlay_clip_id() -> None:
    """실사용 프로젝트 `0907-b26195af`에서 오버레이 클립 5개가 같은
    `placement_id`(`overlay:export-overlay-...`)를 공유해 프론트엔드
    `selectClip`이 `RangeError: Rect clipIds must be unique`로 죽었다
    (`docs/handoffs/2026-09-18-timeline-click-selection-was-silently-crashing.ko.md`).

    원인은 `composition_plan.py`의 `export_overlays` 재구성 루프가 분할로
    생긴 세그먼트(target)마다 도는데도, 만들어 내는 `clip_id`가 분할 조각을
    구분하지 못하고(`source_id`와 `overlay_index`만 씀) 매번 같은 값을
    낸다는 것이다 -- 세그먼트를 쪼개면 같은 원본을 가리키는 target이
    여럿 생기므로 overlay 클립이 그만큼 복제되면서 clip_id가 겹친다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import split_segment

    session = _session(count=1, seconds=8.0)
    session = split_segment(session=session, segment_id="seg_001", split_sec=4.0)

    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [{
            "track_id": "narration_primary",
            "track_type": "narration",
            "clips": [{
                "clip_id": "clip_seg_001",
                "segment_id": "seg_001",
                "asset_uri": "local://projects/project_001/segments/seg_001",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "clip_type": "narration",
            }],
        }],
        "export_overlays": [{
            "segment_id": "seg_001",
            "overlay_type": "image_overlay",
            "asset_id": "asset_overlay",
            "start_sec": 0.0,
            "end_sec": 8.0,
        }],
        "review_flags": [],
        "pending_recommendations": [],
    }

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=session, project_id="project_001",
    )

    overlay_clip_ids = [str(overlay.get("clip_id")) for overlay in materialized.get("export_overlays", [])]
    assert len(overlay_clip_ids) == 2, "쪼갠 세그먼트 둘 다 오버레이를 물려받아야 한다"
    assert len(set(overlay_clip_ids)) == len(overlay_clip_ids), (
        f"분할된 세그먼트가 만든 오버레이 clip_id가 겹친다: {overlay_clip_ids}"
    )


def test_splitting_an_already_regenerated_segment_further_does_not_overlap_its_own_children() -> None:
    """실사용 프로젝트 `0907-b26195af`에서 드래그 트림 커밋이 매번
    `RangeError: Narration segments must not overlap`로 거부됐다
    (`docs/handoffs/2026-09-18-timeline-click-selection-was-silently-crashing.ko.md`
    다음 세션 백로그 `task_ecf8eb71`). 실제 postgres 데이터를 직접 대조해
    보니 `clip_narration_002`(세그먼트 `timeline_001:001__split_2`)가
    `[4.0, 8.0]`을 그대로 물고 있었는데, 그 세그먼트는 이미 세션에서
    `[4.0, 5.7)`로 다시 쪼개진 뒤였다(나머지는 `__split_2__split_3`,
    `__split_2__split_2`가 가져갔다) -- **겹침은 검증 로직 오탐이 아니라
    실제 데이터 흠이다.**

    원인: `timeline_002`처럼 **다시 지은 편집판**은 두 세그먼트("A"=
    `timeline_001:001`, "B"=`timeline_001:001__split_2`)가 각자 자기
    raw narration 클립을 갖고 있으면서도, `source_slices`는 **둘 다 같은
    진짜 원본("A")을 가리킨다**(`session_bound_clip_ids_by_track`가 이
    모양을 이미 알고 다룬다, 2026-09-07 주석). 그 중 "B"가 세션에서
    **또 쪼개지면**, `materialize_editing_session_timeline`의 fallback
    경로(`elif targets is None and source_id in segments`)가 **지금
    세그먼트의 길이가 아니라 raw 클립이 최초에 물고 있던 낡은 길이**로
    클립을 만든다 -- 그래서 세그먼트는 `[4.0, 5.7)`로 줄었는데 클립은 옛
    `[4.0, 8.0)`대로 남아 자기 자식과 겹친다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import split_segment

    # `build_editing_session`으로 새로 지으면 "B"가 자기 자신을 원본으로
    # 삼는다(자기 뿌리) -- 그러면 이 결함이 재현되지 않는다(실제로 확인함).
    # 재현하려면 **regenerate가 만드는 실제 모양**대로, "B"의 `source_slices`가
    # 자기 자신이 아니라 "A"(진짜 원본)를 가리키도록 손으로 지어야 한다.
    session = {
        "project_id": "project_001", "timeline_id": "timeline_001",
        "session_revision": 1, "history": [{"mutation_type": "segment_split"}],
        "undo_stack": [], "redo_stack": [],
        "segments": [
            {
                "segment_id": "A", "caption_text": "", "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep",
                "source_slices": [{"segment_id": "A", "source_offset_sec": 0.0, "duration_sec": 4.0}],
                "lineage": {"root_segment_id": "A", "parent_segment_id": "A", "source_segment_ids": ["A"]},
            },
            {
                "segment_id": "B", "caption_text": "", "start_sec": 4.0, "end_sec": 8.0, "cut_action": "keep",
                "source_slices": [{"segment_id": "A", "source_offset_sec": 4.0, "duration_sec": 4.0}],
                "lineage": {"root_segment_id": "A", "parent_segment_id": "B", "source_segment_ids": ["A"]},
            },
        ],
    }
    session = split_segment(session=session, segment_id="B", split_sec=5.7)

    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [{
            "track_id": "narration_primary",
            "track_type": "narration",
            "clips": [{
                "clip_id": f"clip_narration_{index + 1:03d}",
                "segment_id": segment_id,
                "asset_uri": f"local://projects/project_001/segments/{segment_id}",
                "start_sec": start,
                "end_sec": end,
                "clip_type": "narration",
            } for index, (segment_id, start, end) in enumerate((("A", 0.0, 4.0), ("B", 4.0, 8.0)))],
        }],
        "review_flags": [],
        "pending_recommendations": [],
    }

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=session, project_id="project_001",
    )
    narration_clips = sorted(
        (
            clip
            for track in materialized.get("tracks", [])
            if track.get("track_type") == "narration"
            for clip in track.get("clips", [])
        ),
        key=lambda clip: float(clip.get("start_sec")),
    )

    spans = [(round(float(clip["start_sec"]), 4), round(float(clip["end_sec"]), 4)) for clip in narration_clips]
    assert spans == [(0.0, 4.0), (4.0, 5.7), (5.7, 8.0)], (
        f"쪼갠 뒤 낡은 raw 클립 길이가 되살아나면 안 된다: {spans}"
    )
    for previous, current in zip(narration_clips, narration_clips[1:]):
        assert float(previous["end_sec"]) <= float(current["start_sec"]), (
            f"내레이션 클립이 겹친다: {previous.get('clip_id')} -> {current.get('clip_id')}"
        )


def test_the_new_model_says_the_same_thing_the_real_renderer_does() -> None:
    """**이 파일에서 가장 중요한 시험이다.**

    새 모델이 그럴듯해 보이는 평행우주가 되는 것이 이 단계의 가장 비싼
    실패다 -- Phase 4에서 렌더러를 갈아탄 뒤에야 드러나기 때문이다. 그래서
    같은 세션을 두 길로 통과시켜(실제 `materialize_editing_session_timeline`
    대 새 `migrate_segment_media_to_placed_clips`) 나온 것을 맞대 본다.

    기대값을 이 실행이 방금 만든 값과 비교하지 않는다 -- 두 **독립적인**
    구현이 같은 답을 내는지를 본다.
    """
    from videobox_core_engine.clip_placement import migrate_segment_media_to_placed_clips
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import (
        merge_adjacent_segments,
        split_segment,
        update_segment_broll_override,
        update_segment_music_override,
        update_segment_sfx_override,
    )

    session = _session(count=2, seconds=8.0)
    # **쪼갠 뒤 다시 합친다.** 쪼개기만 하면 창의 `start_offset_sec`가 늘 0이라
    # 그 차원을 아무것도 안 지킨다(이 시험을 처음 썼을 때 실제로 그랬다 --
    # 오프셋을 통째로 무시하게 고쳐도 초록이었다). 합치기가 두 번째 창에
    # 0이 아닌 오프셋을 만든다.
    session = split_segment(session=session, segment_id="seg_001", split_sec=4.0)
    left_id, right_id = [segment["segment_id"] for segment in session["segments"]][:2]
    session = update_segment_broll_override(session=session, segment_id=left_id, asset_id="broll-1")
    session = update_segment_broll_override(session=session, segment_id=right_id, asset_id="broll-2")
    session = merge_adjacent_segments(session=session, left_segment_id=left_id, right_segment_id=right_id)
    session = update_segment_music_override(session=session, segment_id="seg_002", asset_id="music-1")
    session = update_segment_sfx_override(session=session, segment_id="seg_002", asset_id="sfx-1")

    offsets = [
        float(window.get("start_offset_sec") or 0.0)
        for segment in session["segments"]
        for window in (segment.get("media_windows") or [])
    ]
    assert any(offset > 0 for offset in offsets), "0이 아닌 창 오프셋을 안 만들었다 -- 시험이 그 차원을 못 지킨다"

    materialized = materialize_editing_session_timeline(
        timeline={"timeline_id": "timeline_001", "project_id": "project_001", "tracks": []},
        editing_session=session,
        project_id="project_001",
    )
    rendered = {
        (str(track.get("track_type")), str(clip.get("clip_id")), round(float(clip["start_sec"]), 4), round(float(clip["end_sec"]), 4))
        for track in materialized.get("tracks", [])
        if str(track.get("track_type")) in {"broll", "bgm", "sfx"}
        for clip in track.get("clips", [])
    }
    placed = {
        (clip.kind, clip.clip_id, round(clip.start_sec, 4), round(clip.end_sec, 4))
        for clip in migrate_segment_media_to_placed_clips(segments=session["segments"], tracks=_legacy_tracks())
    }

    assert rendered, "실제 렌더 경로가 아무 클립도 안 냈다 -- 시험 자체가 아무것도 안 지키고 있다"
    assert placed == rendered


def test_one_call_gives_a_track_list_and_its_clips_that_agree_with_each_other() -> None:
    """Phase 4·5·6·7이 실제로 부를 자리. 트랙과 클립을 따로 만들어 놓고
    서로 안 맞으면 그 단계에서야 드러난다 -- 한 번에 만들고 그 자리에서
    맞는지 본다."""
    from videobox_core_engine.clip_placement import build_track_registry_snapshot, validate_placed_clips
    from videobox_core_engine.editing_session import update_segment_broll_override, update_segment_music_override
    from videobox_core_engine.track_registry import validate_tracks

    session = update_segment_broll_override(session=_session(), segment_id="seg_001", asset_id="broll-1")
    session = update_segment_music_override(session=session, segment_id="seg_002", asset_id="music-1")

    tracks, clips = build_track_registry_snapshot(session)

    validate_tracks(tracks)
    validate_placed_clips(clips, tracks=tracks)
    assert [track.track_id for track in tracks] == [
        "track-narration", "track-broll", "track-bgm", "track-sfx", "track-overlay",
    ]
    assert sorted(clip.kind for clip in clips) == ["bgm", "broll"]
    # 옛 고정 구조에서 왔으므로 타이밍 기준은 내레이션 하나다(Phase 3에서 일반화).
    assert [track.track_id for track in tracks if track.is_timing_anchor] == ["track-narration"]


def test_the_snapshot_of_an_untouched_session_is_still_valid_and_empty() -> None:
    from videobox_core_engine.clip_placement import build_track_registry_snapshot, validate_placed_clips
    from videobox_core_engine.track_registry import validate_tracks

    tracks, clips = build_track_registry_snapshot(_session())

    validate_tracks(tracks)
    validate_placed_clips(clips, tracks=tracks)
    assert clips == []
