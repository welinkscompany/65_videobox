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


def test_muted_track_renders_at_zero_volume_rather_than_disappearing() -> None:
    # 음소거는 소리만 끄는 것이다. 클립이 사라지면 그림도 같이 사라진다.
    timeline = apply_track_states_to_timeline(timeline=_timeline(), states={"broll": {"muted": True}})

    plan = CompositionPlan.from_timeline(timeline=timeline)

    broll = next(item for item in plan.items if item.track_type == "broll")
    assert broll.media_controls["volume"] == 0.0


def test_muting_narration_keeps_its_clip_and_zeroes_the_volume() -> None:
    timeline = apply_track_states_to_timeline(timeline=_timeline(), states={"narration": {"muted": True}})

    plan = CompositionPlan.from_timeline(timeline=timeline)

    narration = next(item for item in plan.items if item.track_type == "narration")
    assert narration.media_controls.get("volume") == 0.0


def test_hiding_captions_actually_drops_them_from_the_render() -> None:
    # 자막은 트랙이 아니라 **따로 들어온다**(`from_timeline(captions=...)`).
    # 처음엔 트랙 순회만 고쳐서, 자막 숨김이 저장은 되는데 결과물은 그대로인
    # 단추가 됐다 -- 실제 화면에서 눌러 보고 찾았다(2026-08-23).
    timeline = _timeline()
    timeline["tracks"].append({"track_id": "t-caption", "track_type": "caption", "clips": []})
    cues = [{"start_sec": 0.0, "end_sec": 2.0, "text": "첫 자막"}]

    shown = CompositionPlan.from_timeline(timeline=timeline, captions=cues)
    hidden = CompositionPlan.from_timeline(
        timeline=apply_track_states_to_timeline(timeline=timeline, states={"caption": {"hidden": True}}),
        captions=cues,
    )

    assert len(shown.captions) == 1
    assert hidden.captions == ()


def test_untouched_tracks_are_left_exactly_as_they_were() -> None:
    plain = CompositionPlan.from_timeline(timeline=_timeline())
    stated = CompositionPlan.from_timeline(
        timeline=apply_track_states_to_timeline(timeline=_timeline(), states={})
    )

    assert plain.canonical_dict() == stated.canonical_dict()
