"""자유 멀티트랙 -- 클립이 "어느 트랙 소속"인지 들고 다니는가.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3.

Phase 5로 트랙을 **추가하는 문**은 열렸는데, 거기 올릴 수 있는 것이 없다.
촬영본/음악/효과음 클립은 전부 장면에 달린 필드(`broll_override` 등)에서
나오고 `composition_plan.py:612`가 그것을 종류(kind)별 바구니 하나에
그대로 쏟아 넣는다 -- 클립이 자기 트랙을 말할 자리가 없다.

그래서 Phase 7(타임라인 UI)을 먼저 만들면 **아무것도 못 올리는 빈 줄**이
생긴다. 이 파일은 그 앞 단계를 지킨다: 장면 override가 `track_id`를 달면
그 클립이 **그 트랙으로** 간다.

## 이름표 두 세계가 만난다

트랙 목록(`session["tracks"]`)의 이름은 `track-broll`(하이픈,
`track_registry.migrate_legacy_tracks_to_registry`)이고, 완성된 타임라인의
트랙 이름은 `track_broll`(밑줄, `timeline["tracks"]`에서 온다). 서로 다른
세계다 -- 그래서 "그 종류의 첫 트랙"은 **옛 이름 그대로** 두고, 추가된
트랙만 목록 쪽 이름으로 나온다. 그래야 지금 있는 편집본의 결과가 한 글자도
안 바뀐다(바뀌면 캐시된 미리보기가 전부 무효다).
"""

from __future__ import annotations

from videobox_core_engine.composition_plan import materialize_editing_session_timeline


def _timeline() -> dict:
    return {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [
            {"track_id": "track_broll", "track_type": "broll", "clips": []},
        ],
        "review_flags": [],
        "pending_recommendations": [],
    }


def _base_session() -> dict:
    from videobox_core_engine.editing_session import build_editing_session

    return build_editing_session(
        project_id="project_001",
        timeline=_timeline(),
        segments=[{
            "segment_id": "seg_001", "text": "한 장면", "start_sec": 0.0, "end_sec": 6.0,
            "review_required": False, "cleanup_decision": "keep",
        }],
    )


def _with_second_broll_track(session: dict) -> dict:
    """Phase 5의 트랙 추가가 실제로 남기는 모양."""
    from videobox_core_engine.session_tracks import add_session_track

    return add_session_track(session=session, kind="broll", label="촬영본 2")


def _broll(override: dict) -> dict:
    return {
        "asset_id": override["asset_id"],
        "asset_uri": f"local://projects/project_001/assets/{override['asset_id']}",
        **({"track_id": override["track_id"]} if override.get("track_id") else {}),
    }


def _broll_tracks(materialized: dict) -> list[tuple[str, list[str]]]:
    return [
        (str(track.get("track_id")), [str(clip.get("clip_id")) for clip in track.get("clips", [])])
        for track in materialized.get("tracks", [])
        if str(track.get("track_type")) == "broll"
    ]


def _second_broll_track_id(session: dict) -> str:
    added = [track for track in session["tracks"] if track["kind"] == "broll"]
    assert len(added) == 2, "트랙 추가가 실제로 남지 않았다"
    return str(added[-1]["track_id"])


def test_an_override_that_names_an_added_track_lands_on_that_track() -> None:
    """Phase 5로 추가한 트랙에 촬영본을 올릴 수 있어야 한다.

    이게 없으면 트랙 추가 API는 **올릴 데가 없는 빈 트랙**만 만든다.
    """
    session = _with_second_broll_track(_base_session())
    session["segments"][0]["broll_override"] = _broll(
        {"asset_id": "asset-b", "track_id": _second_broll_track_id(session)},
    )

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    assert _broll_tracks(materialized) == [
        (_second_broll_track_id(session), ["session-broll-seg_001-0"]),
    ], "이름표를 단 클립은 그 트랙으로 가야 한다 -- 지금은 종류 바구니 하나에 다 쏟는다"


def test_two_overrides_on_different_tracks_both_survive_the_same_span() -> None:
    """서로 다른 트랙에 올린 촬영본 둘이 같은 구간을 덮어도 둘 다 남아야 한다.

    한 트랙 안에서 같은 구간을 덮으면 하나가 다른 하나를 가린다 -- 트랙을
    나누는 이유가 바로 이것이다.
    """
    session = _with_second_broll_track(_base_session())
    upper = _second_broll_track_id(session)
    session["segments"][0]["media_windows"] = [
        {"start_offset_sec": 0.0, "duration_sec": 6.0, "broll_override": _broll({"asset_id": "asset-lower"})},
        {"start_offset_sec": 0.0, "duration_sec": 6.0, "broll_override": _broll({"asset_id": "asset-upper", "track_id": upper})},
    ]

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    tracks = dict(_broll_tracks(materialized))
    assert set(tracks) == {"track_broll", upper}, f"트랙 둘이 나와야 한다 -- 실제: {sorted(tracks)}"
    assert sum(len(clips) for clips in tracks.values()) == 2


def test_an_override_without_a_track_id_is_byte_identical_to_before() -> None:
    """지금 있는 편집본은 override에 `track_id`가 없다. 그 경우 결과가
    달라지면 **캐시된 미리보기가 전부 무효**가 된다."""
    session = _base_session()
    session["segments"][0]["broll_override"] = _broll({"asset_id": "asset-b"})

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    assert _broll_tracks(materialized) == [("track_broll", ["session-broll-seg_001-0"])]


def test_an_override_naming_the_first_track_of_its_kind_keeps_the_old_name() -> None:
    """목록 쪽 이름(`track-broll`)으로 그 종류의 **첫 트랙**을 가리켜도
    결과 트랙 이름은 옛 이름(`track_broll`) 그대로여야 한다 -- 두 이름 세계가
    만나는 자리이고, 여기서 이름이 바뀌면 지문이 깨진다."""
    session = _base_session()
    session["segments"][0]["broll_override"] = _broll(
        {"asset_id": "asset-b", "track_id": "track-broll"},
    )

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    assert _broll_tracks(materialized) == [("track_broll", ["session-broll-seg_001-0"])]


def test_an_override_naming_an_unknown_track_still_shows_its_clip() -> None:
    """지운 트랙(또는 옛 세션의 흔적) 이름표가 남아 있어도 촬영본이 **소리
    없이 사라지면** 안 된다. 재료는 여전히 장면에 붙어 있다 -- 이름표만
    못 알아보는 것이므로 그 종류의 첫 트랙으로 내린다."""
    session = _base_session()
    session["segments"][0]["broll_override"] = _broll(
        {"asset_id": "asset-b", "track_id": "track-broll-지워짐"},
    )

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    assert _broll_tracks(materialized) == [("track_broll", ["session-broll-seg_001-0"])]


def test_an_override_naming_a_track_of_another_kind_falls_back() -> None:
    """촬영본에 음악 트랙 이름표가 붙으면 그리로 보내면 안 된다 -- 렌더러가
    영상 클립을 소리 트랙에서 찾게 된다."""
    session = _with_second_broll_track(_base_session())
    bgm_track_id = next(track["track_id"] for track in session["tracks"] if track["kind"] == "bgm")
    session["segments"][0]["broll_override"] = _broll({"asset_id": "asset-b", "track_id": bgm_track_id})

    materialized = materialize_editing_session_timeline(
        timeline=_timeline(), editing_session=session, project_id="project_001",
    )

    assert _broll_tracks(materialized) == [("track_broll", ["session-broll-seg_001-0"])]
