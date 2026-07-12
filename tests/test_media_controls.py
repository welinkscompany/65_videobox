from __future__ import annotations

import pytest


def test_normalized_media_controls_validate_audio_and_broll_contracts() -> None:
    from videobox_core_engine.media_controls import normalize_media_controls

    audio = normalize_media_controls(
        {"gain_db": -6, "fade_in_sec": 0.5, "fade_out_sec": 0.75, "ducking": True},
        media_kind="audio",
        duration_sec=4.0,
    )
    broll = normalize_media_controls(
        {"fit": "crop", "loop": True, "pad": False, "trim_start_sec": 0.25},
        media_kind="broll",
        duration_sec=4.0,
    )

    assert audio == {"gain_db": -6.0, "fade_in_sec": 0.5, "fade_out_sec": 0.75, "ducking": True}
    assert broll == {"fit": "crop", "loop": True, "pad": False, "trim_start_sec": 0.25}
    with pytest.raises(ValueError, match="fade"):
        normalize_media_controls({"fade_in_sec": 3.0, "fade_out_sec": 2.0}, media_kind="audio", duration_sec=4.0)
    with pytest.raises(ValueError, match="fit"):
        normalize_media_controls({"fit": "stretch"}, media_kind="broll", duration_sec=4.0)


def test_timeline_builder_carries_manual_media_controls_to_renderable_clips() -> None:
    from videobox_core_engine.timeline_builder import TimelineBuilder

    timeline = TimelineBuilder().build(
        project_id="project_001",
        segments=[{"segment_id": "seg_001", "text": "caption", "start_sec": 0.0, "end_sec": 4.0, "review_required": False}],
        recommendations=[
            {
                "recommendation_id": "manual_broll_seg_001",
                "target_segment_id": "seg_001",
                "recommendation_type": "broll",
                "selected_asset_id": "asset_broll_001",
                "score": 1.0,
                "reason": "manual",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"media_controls": {"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.5}},
            }
        ],
    )

    assert timeline.tracks[1].clips[0].media_controls == {"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.5}


def test_editing_session_media_override_persists_normalized_controls() -> None:
    from videobox_core_engine.editing_session import update_segment_broll_override, update_segment_music_override

    session = {"segments": [{"segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0}], "history": []}
    broll = update_segment_broll_override(
        session=session,
        segment_id="seg_001",
        asset_id="asset_broll_001",
        media_controls={"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.5},
    )
    music = update_segment_music_override(
        session=session,
        segment_id="seg_001",
        asset_id="asset_music_001",
        media_controls={"gain_db": -8, "fade_in_sec": 0.2, "fade_out_sec": 0.4, "ducking": True},
    )

    assert broll["segments"][0]["broll_override"]["media_controls"]["fit"] == "crop"
    assert music["segments"][0]["music_override"]["media_controls"]["gain_db"] == -8.0
