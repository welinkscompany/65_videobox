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
    assert broll == {
        "fit": "crop",
        "loop": True,
        "pad": False,
        "trim_start_sec": 0.25,
        "preserve_source_audio": False,
    }
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

    assert timeline.tracks[1].clips[0].media_controls == {
        "fit": "crop",
        "loop": False,
        "pad": True,
        "trim_start_sec": 0.5,
        "preserve_source_audio": False,
    }


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


def test_manual_project_broll_persists_immutable_sha_and_revision_outside_playback_controls() -> None:
    from videobox_core_engine.editing_session import update_segment_broll_override

    updated = update_segment_broll_override(
        session={"segments": [{"segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0}], "history": []},
        segment_id="seg_001", asset_id="asset_broll_001",
        media_controls={"fit": "crop", "expected_content_sha256": "a" * 64, "media_revision": "2026-07-16T00:00:00Z"},
    )
    override = updated["segments"][0]["broll_override"]
    assert override["expected_content_sha256"] == "a" * 64
    assert override["media_revision"] == "2026-07-16T00:00:00Z"
    assert "expected_content_sha256" not in override["media_controls"]


def test_timeline_builder_carries_manual_broll_identity_to_the_output_source_verifier(tmp_path) -> None:
    """A manual local B-roll change after placement must block output verification."""
    from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
    from videobox_core_engine.timeline_builder import TimelineBuilder
    from videobox_domain_models.assets import AssetType
    from videobox_storage.local_project_store import LocalProjectStore

    source = tmp_path / "manual-broll.mp4"
    source.write_bytes(b"placed-broll")
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="manual provenance")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    expected_sha = __import__("hashlib").sha256(b"placed-broll").hexdigest()
    expected_revision = store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)["created_at"]
    timeline = TimelineBuilder().build(
        project_id=project.project_id,
        segments=[{"segment_id": "seg_001", "text": "caption", "start_sec": 0.0, "end_sec": 2.0}],
        recommendations=[{
            "recommendation_id": "manual_broll_seg_001",
            "target_segment_id": "seg_001",
            "recommendation_type": "broll",
            "selected_asset_id": asset.asset_id,
            "score": 1.0,
            "reason": "manual",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {
                "selected_asset_uri": asset.storage_uri,
                "expected_content_sha256": expected_sha,
                "media_revision": expected_revision,
            },
        }],
    )
    timeline_payload = __import__("dataclasses").asdict(timeline)
    clip = timeline_payload["tracks"][1]["clips"][0]

    assert clip["expected_content_sha256"] == expected_sha
    assert clip["media_revision"] == expected_revision
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).write_bytes(b"changed-after-placement")
    with pytest.raises(OutputSourceStaleError, match="SHA-256 changed"):
        verify_output_sources(store=store, project_id=project.project_id, timeline=timeline_payload)


def test_manual_music_asset_uses_resolvable_asset_uri_in_the_render_timeline() -> None:
    from videobox_core_engine.timeline_builder import TimelineBuilder

    asset_uri = "local://projects/project_001/assets/asset_bgm_001"
    timeline = TimelineBuilder().build(
        project_id="project_001",
        asset_uri_validator=lambda asset_id, media_type, candidate_uri: (
            asset_id == "asset_bgm_001"
            and media_type == "bgm"
            and candidate_uri == asset_uri
        ),
        segments=[{"segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0, "text": "music"}],
        recommendations=[
            {
                "recommendation_id": "manual_bgm_seg_001",
                "target_segment_id": "seg_001",
                "recommendation_type": "bgm",
                "selected_asset_id": "asset_bgm_001",
                "score": 1.0,
                "reason": "manual",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {
                    "selected_asset_uri": asset_uri,
                    "media_controls": {"gain_db": -6},
                },
            }
        ],
    )

    bgm_clip = next(clip for track in timeline.tracks if track.track_type == "bgm" for clip in track.clips)
    assert bgm_clip.asset_uri == "local://projects/project_001/assets/asset_bgm_001"
