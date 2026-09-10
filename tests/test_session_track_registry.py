"""자유 멀티트랙 Phase 5 -- 트랙을 실제로 추가·삭제·순서 변경한다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 5.

Phase 1(`track_registry.py`)·Phase 2(`clip_placement.py`)는 **읽기만** 하는
모델이라 아무것도 안 깨뜨리고 덧붙일 수 있었다. Phase 5는 **처음으로 쓰는
문**이라 지켜야 할 것이 다르다:

- **되돌리기가 같이 돌아야 한다.** `editing_transactions._snapshot()`은 담을
  최상위 열쇠를 **이름으로 적어** 두므로, 새 열쇠를 넣으면 그 자리도 같이
  넓혀야 트랙 추가가 되돌려진다(`timeline_placement_overrides`를 넣을 때
  이미 한 번 했던 일이다).
- **옛 세션이 안 깨져야 한다.** 트랙 목록이 없는 세션은 지금까지처럼
  고정 다섯 역할로 읽힌다.

이번 조각은 **브롤·음악·효과음만** 다룬다. 내레이션·자막은 타이밍 기준
설계(Phase 3)가 걸려 있어 열지 않는다 -- 열면 "기준 트랙을 지우면?"이라는
결정을 몰래 전제하게 된다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.editing_session import build_editing_session
from videobox_core_engine.session_tracks import (
    MAX_TRACKS_PER_KIND,
    SessionTrackError,
    add_session_track,
    remove_session_track,
    reorder_session_tracks,
    session_tracks,
)


def _session() -> dict:
    return build_editing_session(
        project_id="p",
        timeline={"timeline_id": "t", "project_id": "p", "tracks": [], "review_flags": [], "pending_recommendations": []},
        segments=[{
            "segment_id": "seg_001", "text": "한 장면", "start_sec": 0.0, "end_sec": 6.0,
            "review_required": False, "cleanup_decision": "keep",
        }],
    )


def test_an_old_session_still_reads_as_the_five_fixed_roles() -> None:
    """트랙 목록을 저장한 적 없는 세션(지금 있는 편집본 전부)은 지금까지처럼
    보여야 한다 -- 여기서 모양이 달라지면 옛 프로젝트가 통째로 흔들린다."""
    tracks = session_tracks(_session())

    assert [track.kind for track in tracks] == ["narration", "broll", "bgm", "sfx", "overlay"]
    assert [track.track_id for track in tracks] == [
        "track-narration", "track-broll", "track-bgm", "track-sfx", "track-overlay",
    ]


def test_adding_a_second_broll_track_keeps_the_first_one() -> None:
    updated = add_session_track(session=_session(), kind="broll", label="브롤 2")

    tracks = session_tracks(updated)
    broll = [track for track in tracks if track.kind == "broll"]
    assert len(broll) == 2
    assert broll[0].track_id == "track-broll"
    assert broll[1].label == "브롤 2"
    # 새 트랙은 같은 종류의 **맨 위**에 얹힌다(나중 = 위, Phase 4에서 정한 규칙).
    assert broll[1].order > broll[0].order


def test_narration_and_caption_stay_shut_until_the_timing_anchor_is_designed() -> None:
    """내레이션 트랙을 늘리면 "무엇이 세그먼트 시간을 정하는가"가 흔들린다.
    Phase 3 결정 전에는 아예 안 받는다 -- 조용히 받아 두면 그 결정을 몰래
    전제하게 된다."""
    for kind in ("narration", "caption"):
        with pytest.raises(SessionTrackError):
            add_session_track(session=_session(), kind=kind, label="x")


def test_there_is_a_ceiling_so_the_screen_cannot_be_buried() -> None:
    """화면 세로 공간은 유한하다. 상한은 나중에 넓히기 쉽고 좁히기 어렵다."""
    session = _session()
    for index in range(MAX_TRACKS_PER_KIND - 1):
        session = add_session_track(session=session, kind="broll", label=f"브롤 {index + 2}")

    assert len([t for t in session_tracks(session) if t.kind == "broll"]) == MAX_TRACKS_PER_KIND
    with pytest.raises(SessionTrackError):
        add_session_track(session=session, kind="broll", label="하나 더")


def test_removing_a_track_leaves_the_others_alone() -> None:
    session = add_session_track(session=_session(), kind="broll", label="브롤 2")
    added = [t for t in session_tracks(session) if t.kind == "broll"][1]

    session = remove_session_track(session=session, track_id=added.track_id)

    assert [t.track_id for t in session_tracks(session) if t.kind == "broll"] == ["track-broll"]


def test_the_last_track_of_a_kind_cannot_be_removed() -> None:
    """마지막 브롤 줄까지 지우면 브롤을 놓을 자리가 사라진다 -- 되돌리기로만
    복구되는 상태를 조용히 만들지 않는다."""
    with pytest.raises(SessionTrackError):
        remove_session_track(session=_session(), track_id="track-broll")


def test_reordering_changes_which_track_sits_on_top() -> None:
    session = add_session_track(session=_session(), kind="broll", label="브롤 2")
    broll_ids = [t.track_id for t in session_tracks(session) if t.kind == "broll"]

    session = reorder_session_tracks(session=session, kind="broll", track_ids=list(reversed(broll_ids)))

    reordered = [t.track_id for t in session_tracks(session) if t.kind == "broll"]
    assert reordered == list(reversed(broll_ids))


def test_reordering_refuses_a_list_that_is_not_the_same_tracks() -> None:
    """빠뜨리거나 없는 것을 넣은 목록을 받아 주면 트랙이 조용히 사라진다."""
    session = add_session_track(session=_session(), kind="broll", label="브롤 2")

    with pytest.raises(SessionTrackError):
        reorder_session_tracks(session=session, kind="broll", track_ids=["track-broll"])
    with pytest.raises(SessionTrackError):
        reorder_session_tracks(session=session, kind="broll", track_ids=["track-broll", "없는-트랙"])


def test_adding_a_track_can_be_undone() -> None:
    """**Phase 5가 처음으로 쓰는 문이라 여기서 처음 문제가 된다.**
    `_snapshot()`이 담을 열쇠를 이름으로 적어 두므로, 새 열쇠를 넣고 그 자리를
    안 넓히면 되돌리기가 트랙 추가를 못 되돌린다 -- 조용히."""
    from videobox_core_engine.editing_session import undo

    session = add_session_track(session=_session(), kind="broll", label="브롤 2")
    assert len([t for t in session_tracks(session) if t.kind == "broll"]) == 2

    session = undo(session=session)

    assert len([t for t in session_tracks(session) if t.kind == "broll"]) == 1
