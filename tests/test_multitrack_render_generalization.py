"""자유 멀티트랙 Phase 4 -- 렌더 상류가 같은 종류 트랙 둘을 견디는가.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 4.

`materialize_editing_session_timeline`은 ffmpeg 렌더러와 CapCut 내보내기의
**공통 상류**다. 지금은 클립을 종류(kind)로 모아서 종류당 한 트랙으로 펴서
내보낸다 -- 그래서 같은 종류 트랙이 둘이면 뒤엣것이 앞엣것을 덮어썼다.

**오늘은 아무도 같은 종류 트랙을 둘 만들지 않는다**(`timeline_builder.py`가
종류당 하나만 낸다). 그러니 이건 지금 owner에게 보이는 결함이 아니라,
Phase 5(트랙 추가 문)가 생기는 순간 **영상 절반이 소리 없이 사라지는**
형태로 터질 잠복 결함이다. 스키마는 이미 여러 트랙을 허용한다.

z-order(어느 트랙이 위로 가는가)는 여기서 손대지 않는다 -- 지금 규칙은
"늦게 시작한 것이 위"이고 캡컷은 "위 트랙이 위"라, 바꾸면 **이미 있는
편집본의 결과 그림이 달라진다**. owner 결정 항목이다(§9.2).
"""

from __future__ import annotations

from videobox_core_engine.composition_plan import materialize_editing_session_timeline


def _timeline_with_two_broll_tracks() -> dict:
    """같은 종류 트랙 둘. 스키마가 허용하는 모양이고, Phase 5가 만들 모양이다."""
    return {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [
            {
                "track_id": "track_broll_a",
                "track_type": "broll",
                "clips": [{
                    "clip_id": "clip-a", "segment_id": "seg_001",
                    "asset_id": "asset-a", "asset_uri": "local://projects/project_001/assets/asset-a",
                    "start_sec": 0.0, "end_sec": 2.0,
                }],
            },
            {
                "track_id": "track_broll_b",
                "track_type": "broll",
                "clips": [{
                    "clip_id": "clip-b", "segment_id": "seg_001",
                    "asset_id": "asset-b", "asset_uri": "local://projects/project_001/assets/asset-b",
                    "start_sec": 4.0, "end_sec": 6.0,
                }],
            },
        ],
    }


def _session() -> dict:
    """**실제 세션을 넘겨야 한다.** `editing_session`이 dict가 아니면
    `materialize_editing_session_timeline`은 맨 앞에서 타임라인을 그대로
    돌려주고 끝난다(:171-172) -- 그러면 이 시험은 초록인 채로 아무것도
    안 밟는다(처음 썼을 때 실제로 그랬다)."""
    from videobox_core_engine.editing_session import build_editing_session

    return build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001", "project_id": "project_001", "tracks": [], "review_flags": [], "pending_recommendations": []},
        segments=[{
            "segment_id": "seg_001", "text": "한 장면", "start_sec": 0.0, "end_sec": 6.0,
            "review_required": False, "cleanup_decision": "keep",
        }],
    )


def _materialized_clip_ids(materialized: dict, kind: str = "broll") -> set[str]:
    return {
        str(clip.get("clip_id"))
        for track in materialized.get("tracks", [])
        if str(track.get("track_type")) == kind
        for clip in track.get("clips", [])
    }


def test_two_tracks_of_one_kind_do_not_eat_each_other() -> None:
    """뒤 트랙이 앞 트랙을 덮어쓰면 영상 절반이 **아무 오류 없이** 사라진다.

    잃어버리는 쪽이 조용하다는 것이 이 결함의 핵심이다 -- 예외도, 경고도,
    빈 자리도 없이 그냥 없어진다.
    """
    materialized = materialize_editing_session_timeline(
        timeline=_timeline_with_two_broll_tracks(), editing_session=_session(), project_id="project_001",
    )

    assert _materialized_clip_ids(materialized) == {"clip-a", "clip-b"}


def test_a_single_track_per_kind_timeline_is_untouched() -> None:
    """오늘 실제로 들어오는 모양(종류당 하나)에서는 아무것도 안 바뀌어야 한다.
    Phase 4의 모든 변경은 지금 입력에 대해 **무동작**이어야 안전하다."""
    timeline = _timeline_with_two_broll_tracks()
    timeline["tracks"] = timeline["tracks"][:1]

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=_session(), project_id="project_001",
    )

    assert _materialized_clip_ids(materialized) == {"clip-a"}
    assert [track["track_type"] for track in materialized["tracks"]] == ["broll"]
