"""자유 멀티트랙 Phase 4 -- 렌더 상류가 같은 종류 트랙 둘을 견디는가.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 4.

`materialize_editing_session_timeline`은 ffmpeg 렌더러와 CapCut 내보내기의
**공통 상류**다. 지금은 클립을 종류(kind)로 모아서 종류당 한 트랙으로 펴서
내보낸다 -- 그래서 같은 종류 트랙이 둘이면 뒤엣것이 앞엣것을 덮어썼다.

**오늘은 아무도 같은 종류 트랙을 둘 만들지 않는다**(`timeline_builder.py`가
종류당 하나만 낸다). 그러니 이건 지금 owner에게 보이는 결함이 아니라,
Phase 5(트랙 추가 문)가 생기는 순간 **영상 절반이 소리 없이 사라지는**
형태로 터질 잠복 결함이다. 스키마는 이미 여러 트랙을 허용한다.

z-order(어느 트랙이 위로 가는가)는 **owner가 정했다**(2026-09-10): 캡컷처럼
위 트랙이 위. 옛 규칙은 "늦게 시작한 것이 위"였다. 트랙이 종류당 하나뿐인
지금 편집본은 클립들의 트랙 순서값이 전부 같아서 **결과가 예전과 완전히
같다** -- 옛 규칙은 같은 트랙 안에서 그대로 남는다.
"""

from __future__ import annotations

from pathlib import Path

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


def _two_broll_tracks_overlapping() -> dict:
    """**규칙: 트랙 목록에서 나중에 오는 트랙이 위다**(아래→위 순서로 나열).

    렌더러가 순서대로 얹으므로 "나중 = 위"가 합성 모델과 그대로 맞고,
    `track_registry.Track.order`가 커지는 방향과도 같다.

    아래 트랙(목록의 첫 번째) 클립이 **늦게** 시작하도록 일부러 꼬아 둔다.
    옛 규칙("늦게 시작한 것이 위")과 새 규칙("위 트랙이 위")이 서로 반대
    답을 내야 시험이 규칙 변경을 실제로 지킨다 -- 안 그러면 초록인 채로
    아무것도 안 지킨다.
    """
    return {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "output": {"width": 1080, "height": 1920},
        "tracks": [
            {
                # 목록의 첫 번째 = 아래 트랙. 그런데 **늦게** 시작한다.
                "track_id": "track_broll_lower", "track_type": "broll",
                "clips": [{
                    "clip_id": "lower", "segment_id": "seg_001", "asset_id": "asset-l",
                    "asset_uri": "local://projects/project_001/assets/asset-l",
                    "start_sec": 3.0, "end_sec": 6.0,
                }],
            },
            {
                # 목록의 두 번째 = 위 트랙. 먼저 시작한다.
                "track_id": "track_broll_upper", "track_type": "broll",
                "clips": [{
                    "clip_id": "upper", "segment_id": "seg_001", "asset_id": "asset-u",
                    "asset_uri": "local://projects/project_001/assets/asset-u",
                    "start_sec": 0.0, "end_sec": 6.0,
                }],
            },
        ],
    }


def test_the_upper_track_sits_on_top_even_when_it_started_earlier() -> None:
    """owner 결정(2026-09-10): 캡컷처럼 **위 트랙이 위**로 간다.

    옛 규칙은 "늦게 시작한 것이 위"였다. 이 타임라인은 늦게 시작한 쪽이
    아래 트랙이라 두 규칙이 반대 답을 낸다 -- 옛 규칙이면 `lower`가 위로
    간다.
    """
    from videobox_core_engine.composition_plan import CompositionPlan

    plan = CompositionPlan.from_timeline(timeline=_two_broll_tracks_overlapping())
    order = {item.clip_id: item.track_order for item in plan.items if item.track_type == "broll"}

    assert order["upper"] > order["lower"], "위 트랙이 더 큰 순서값을 가져야 나중에 얹혀 위로 간다"


def test_the_renderer_lays_the_upper_track_down_last() -> None:
    """계획에 순서값만 실리고 렌더러가 안 쓰면 아무 의미가 없다 -- 실제로
    만들어지는 필터 그래프에서 위 트랙이 **나중에** 얹히는지 본다."""
    from videobox_core_engine.composition_plan import CompositionPlan
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
    from videobox_storage.local_project_store import LocalProjectStore
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        renderer = FfmpegFinalRenderer(store=LocalProjectStore(Path(tmp)), video_width=1080, video_height=1920)
        graph = renderer.build_plan_filter_graph(
            composition_plan=CompositionPlan.from_timeline(timeline=_two_broll_tracks_overlapping()),
            source_indices={"lower": 0, "upper": 1},
        )

    assert graph.index("v_upper") > graph.index("v_lower"), "위 트랙이 나중에 얹혀야 한다"


def test_one_track_per_kind_keeps_the_exact_preview_fingerprint_byte_identical() -> None:
    """`canonical_dict()`는 미리보기 캐시 지문(`fingerprint_exact_preview`)이
    먹는다. 필드를 늘리면서 기본값까지 실어 보내면 **캐시된 미리보기가 전부
    무효**가 된다 -- 지금 있는 편집본은 트랙이 종류당 하나뿐이므로 지문이
    한 바이트도 바뀌면 안 된다."""
    from videobox_core_engine.composition_plan import CompositionPlan

    timeline = _two_broll_tracks_overlapping()
    timeline["tracks"] = timeline["tracks"][:1]

    plan = CompositionPlan.from_timeline(timeline=timeline)
    item = plan.canonical_dict()["items"][0]

    assert "track_order" not in item, "트랙이 하나뿐일 때는 지문에 새 필드가 실리면 안 된다"


def test_two_tracks_that_reuse_one_clip_id_do_not_shadow_each_other() -> None:
    """갭2: 렌더러는 **클립 이름으로** 입력을 찾는다
    (`ffmpeg_final_renderer.py`의 `source_indices[item.clip_id]`). 두 트랙이
    같은 이름을 쓰면 하나가 다른 하나를 가려서, 엉뚱한 영상이 깔리거나
    한 쪽이 사라진다.

    이름을 **항상** 바꾸면 안 된다 -- 지금 편집본(트랙 하나)의 이름이 바뀌면
    미리보기 캐시가 깨진다. 겹칠 때만 구분해야 한다.
    """
    timeline = _timeline_with_two_broll_tracks()
    for track in timeline["tracks"]:
        track["clips"][0]["clip_id"] = "same-name"

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=_session(), project_id="project_001",
    )
    clip_ids = [
        str(clip.get("clip_id"))
        for track in materialized.get("tracks", [])
        if str(track.get("track_type")) == "broll"
        for clip in track.get("clips", [])
    ]

    assert len(clip_ids) == 2, "두 클립 다 남아야 한다"
    assert len(set(clip_ids)) == 2, f"이름이 겹치면 렌더러가 하나를 가린다: {clip_ids}"


def test_a_single_track_keeps_its_clip_ids_exactly() -> None:
    """트랙이 하나뿐이면 이름을 **한 글자도** 바꾸면 안 된다 -- 미리보기 캐시
    지문이 클립 이름을 먹는다."""
    timeline = _timeline_with_two_broll_tracks()
    timeline["tracks"] = timeline["tracks"][:1]

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=_session(), project_id="project_001",
    )

    assert _materialized_clip_ids(materialized) == {"clip-a"}


def test_rehydrating_a_plan_keeps_the_two_tracks_apart() -> None:
    """갭3: 계획에서 타임라인을 되돌릴 때 다시 종류로 접으면 트랙 정체성이
    또 사라진다 -- Phase 4가 상류에서 지킨 것을 하류가 도로 뭉갠다."""
    from videobox_core_engine.composition_plan import CompositionPlan
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer

    plan = CompositionPlan.from_timeline(timeline=_two_broll_tracks_overlapping())
    rehydrated = FfmpegFinalRenderer._timeline_from_plan(
        composition_plan=plan, timeline_context={},
    )

    broll_tracks = [t for t in rehydrated.get("tracks", []) if str(t.get("track_type")) == "broll"]
    assert len(broll_tracks) == 2, f"트랙 둘이 하나로 접혔다: {len(broll_tracks)}"
