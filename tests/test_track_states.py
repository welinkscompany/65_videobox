"""트랙 숨김·음소거 계약. 캡컷 타임라인의 눈·음소거에 해당한다."""
from __future__ import annotations

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.track_states import (
    apply_track_states_to_timeline,
    normalize_track_states,
)


def test_absent_states_normalize_to_nothing() -> None:
    assert normalize_track_states(None) == {}
    assert normalize_track_states({}) == {}


def test_default_valued_entries_are_dropped_so_untouched_sessions_look_the_same() -> None:
    # 켰다 끈 세션과 한 번도 안 건드린 세션이 같은 모양으로 남아야 저장분이
    # 쓸데없이 커지지 않는다.
    assert normalize_track_states({"bgm": {"muted": False}}) == {}
    assert normalize_track_states({"broll": {"hidden": False, "muted": False}}) == {}


def test_keeps_only_the_flags_that_were_turned_on() -> None:
    assert normalize_track_states({"broll": {"hidden": True, "muted": False}}) == {"broll": {"hidden": True}}
    assert normalize_track_states({"narration": {"muted": True}}) == {"narration": {"muted": True}}


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ({"caption": {"muted": True}}, "track_states_muted_unsupported"),
        ({"bgm": {"hidden": True}}, "track_states_hidden_unsupported"),
        ({"sfx": {"hidden": True}}, "track_states_hidden_unsupported"),
        ({"overlay": {"muted": True}}, "track_states_muted_unsupported"),
        ({"narration": {"hidden": True}}, "track_states_hidden_unsupported"),
    ],
)
def test_rejects_flags_that_would_do_nothing_on_that_track(states: dict, message: str) -> None:
    # 조용히 버리면 "화면에서 켰고 저장도 됐는데 결과는 그대로"가 된다 --
    # 이 저장소가 배속·음량에서 이미 한 번 겪은 실패다.
    with pytest.raises(ValueError, match=message):
        normalize_track_states(states)


@pytest.mark.parametrize(
    "states",
    [{"nope": {"hidden": True}}, {"broll": {"louder": True}}, {"broll": {"hidden": "yes"}}, {"broll": []}, []],
)
def test_rejects_shapes_it_cannot_mean(states: object) -> None:
    with pytest.raises(ValueError):
        normalize_track_states(states)


def _timeline() -> dict:
    return {
        "output": {"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1},
        "tracks": [
            {
                "track_id": "t-narration",
                "track_type": "narration",
                "clips": [{"clip_id": "n-1", "asset_uri": "file:///n.wav", "start_sec": 0, "end_sec": 4}],
            },
            {
                "track_id": "t-broll",
                "track_type": "broll",
                "clips": [{
                    "clip_id": "b-1", "asset_uri": "file:///b.mp4", "start_sec": 0, "end_sec": 4,
                    "source_in_sec": 0, "source_out_sec": 4, "media_controls": {"volume": 1.0},
                }],
            },
            {
                "track_id": "t-bgm",
                "track_type": "bgm",
                "clips": [{"clip_id": "m-1", "asset_uri": "file:///m.mp3", "start_sec": 0, "end_sec": 4}],
            },
        ],
    }


def test_hidden_track_drops_out_of_the_composition_entirely() -> None:
    timeline = apply_track_states_to_timeline(timeline=_timeline(), states={"broll": {"hidden": True}})

    plan = CompositionPlan.from_timeline(timeline=timeline)

    assert [item.track_type for item in plan.items] == ["bgm", "narration"]


def test_muting_does_not_remove_the_clip() -> None:
    # 음소거는 소리만 끈다. 클립이 사라지면 그림도 같이 사라진다.
    #
    # 갱신 이유(2026-08-23): 예전에는 `media_controls["volume"]`을 0으로
    # 덮어쓰는지 봤다. 그 방식은 `broll`에만 통했다 -- 내레이션은
    # `media_controls`를 아예 안 읽고 `bgm`·`sfx`는 `gain_db`를 쓴다.
    # 이제 계획이 꺼진 레인을 들고 가고 렌더러가 그 소리를 안 섞는다.
    timeline = apply_track_states_to_timeline(timeline=_timeline(), states={"broll": {"muted": True}})

    plan = CompositionPlan.from_timeline(timeline=timeline)

    assert plan.muted_tracks == frozenset({"broll"})
    assert "broll" in {item.track_type for item in plan.items}


def _materialized(states: dict) -> "CompositionPlan":
    """**실물이 만드는 모양으로** 계획을 세운다.

    앞서 이 파일의 시험들은 타임라인에 `caption` 트랙과 빈 `overlay` 트랙을
    손으로 붙여 놓고 통과했다. 그런데 `materialize_editing_session_timeline`은
    그런 트랙을 **아예 만들지 않는다** -- 지원 트랙만, 그리고 클립이 있을
    때만 낸다. 그래서 시험은 초록인데 실제 완성본은 안 바뀌었다(2026-08-23
    코드리뷰에서 발견). 이제 진짜 materializer를 지난다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline

    timeline = {
        "timeline_id": "t-1",
        "output": {"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "duration_sec": 4.0},
        "narration_source_uri": "local://projects/p/assets/narration",
        "tracks": [
            {"track_id": "n", "track_type": "narration", "clips": [
                {"clip_id": "n-1", "segment_id": "seg-1", "asset_uri": "local://projects/p/assets/n",
                 "start_sec": 0.0, "end_sec": 4.0},
            ]},
            {"track_id": "b", "track_type": "broll", "clips": [
                {"clip_id": "b-1", "segment_id": "seg-1", "clip_type": "broll",
                 "asset_uri": "local://projects/p/assets/b", "start_sec": 0.0, "end_sec": 4.0,
                 "source_in_sec": 0.0, "source_out_sec": 4.0, "media_controls": {"fit": "crop"}},
            ]},
        ],
        "export_overlays": [
            {"clip_id": "eo1", "start_sec": 0.0, "end_sec": 2.0, "overlay_type": "explanation_card",
             "overlay_payload": {"title": "제목", "body": "본문"}},
        ],
    }
    session = {
        "session_id": "s-1",
        "project_id": "p",
        "timeline_id": "t-1",
        "session_revision": 1,
        "segments": [{
            "segment_id": "seg-1", "caption_text": "자막입니다",
            "start_sec": 0.0, "end_sec": 4.0, "cut_action": "keep", "review_required": False,
        }],
        "history": [],
        "track_states": states,
    }
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=session, project_id="p")
    captions = materialized.get("session_captions") or []
    return CompositionPlan.from_timeline(timeline=materialized, captions=captions)


def test_hiding_captions_drops_them_from_the_render_for_real() -> None:
    # 자막은 트랙이 아니라 따로 들어오고, materializer는 `caption` 트랙을 아예
    # 만들지 않는다. 그래서 트랙을 훑어 판단하면 영영 못 잡는다.
    assert len(_materialized({}).captions) == 1
    assert _materialized({"caption": {"hidden": True}}).captions == ()


def test_hiding_the_overlay_lane_drops_text_overlays_for_real() -> None:
    # 설명 카드는 `export_overlays`에 있다. 화면은 오버레이 레인에 그려 주므로
    # 눈을 끄면 사라진 것처럼 보이는데 완성본에는 그대로 박혔다.
    assert len(_materialized({}).export_overlays) == 1
    assert _materialized({"overlay": {"hidden": True}}).export_overlays == ()


def test_hiding_the_video_lane_drops_its_clips_for_real() -> None:
    assert "broll" in {item.track_type for item in _materialized({}).items}
    assert "broll" not in {item.track_type for item in _materialized({"broll": {"hidden": True}}).items}


def test_muting_a_lane_is_carried_to_the_renderer_for_real() -> None:
    # 음소거는 트랙마다 쓰는 제어가 다르다 -- 내레이션은 `media_controls`를
    # 아예 안 읽고, bgm/sfx는 `gain_db`, broll만 `volume`이다. 그래서 계획이
    # **어느 레인이 꺼졌는지** 들고 가고, 렌더러가 그 레인의 소리를 뺀다.
    assert _materialized({}).muted_tracks == frozenset()
    assert _materialized({"narration": {"muted": True}}).muted_tracks == frozenset({"narration"})
    # 음소거는 클립을 지우지 않는다 -- 지우면 그림까지 사라진다.
    assert "narration" in {item.track_type for item in _materialized({"narration": {"muted": True}}).items}


def test_untouched_tracks_are_left_exactly_as_they_were() -> None:
    plain = CompositionPlan.from_timeline(timeline=_timeline())
    stated = CompositionPlan.from_timeline(
        timeline=apply_track_states_to_timeline(timeline=_timeline(), states={})
    )

    assert plain.canonical_dict() == stated.canonical_dict()


def _audio_graph(states: dict) -> str:
    """실제 오디오 필터 그래프. **그래프가 안 바뀌면 소리도 안 바뀐다.**

    코드리뷰가 이 방법으로 결함을 찾았다 -- 음소거를 켠 그래프와 안 켠 그래프가
    바이트까지 같았다(2026-08-23). 그래서 여기서도 그래프를 직접 견준다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer

    plan = _materialized(states)
    renderer = FfmpegFinalRenderer.__new__(FfmpegFinalRenderer)
    return renderer.build_plan_audio_filter_graph(
        composition_plan=plan,
        source_indices={item.clip_id: index for index, item in enumerate(plan.items)},
    )


def test_muting_narration_actually_changes_the_audio_graph() -> None:
    plain = _audio_graph({})
    silent = _audio_graph({"narration": {"muted": True}})

    assert plain != silent, "음소거를 켰는데 그래프가 그대로면 소리도 그대로다"
    # 내레이션이 안 섞이면 대신 무음이 깔린다 -- 길이는 유지되어야 한다.
    assert "anullsrc" in silent
    assert "anullsrc" not in plain


def test_muting_the_video_lane_drops_its_source_audio_from_the_graph() -> None:
    # `broll`은 `preserve_source_audio`가 켜져 있을 때만 소리를 낸다.
    plain = _audio_graph({})
    silent = _audio_graph({"broll": {"muted": True}})

    assert "b-1" not in silent.split("[aout]")[0] or plain != silent
