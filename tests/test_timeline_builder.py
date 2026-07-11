from __future__ import annotations

from videobox_core_engine.settings import DEFAULT_PROJECTS_ROOT
from videobox_core_engine.timeline_builder import TimelineBuilder
from videobox_domain_models.recommendations import (
    RecommendationRecord,
    RecommendationType,
)
from videobox_domain_models.segments import SegmentRecord


def test_timeline_builder_creates_review_focused_timeline() -> None:
    builder = TimelineBuilder()
    segment = SegmentRecord.create(
        project_id="proj_001",
        text="Narration line with a pronunciation issue",
        start_sec=0.0,
        end_sec=4.2,
        review_required=True,
    )
    recommendation = RecommendationRecord.create(
        project_id="proj_001",
        target_segment_id=segment.segment_id,
        recommendation_type=RecommendationType.TTS_REPLACEMENT,
        reason="Pronunciation cleanup candidate",
        score=0.88,
    )

    timeline = builder.build(
        project_id="proj_001",
        segments=[segment],
        recommendations=[recommendation],
    )

    assert timeline.output_mode == "review"
    assert len(timeline.tracks) == 1
    assert timeline.tracks[0].clips[0].segment_id == segment.segment_id
    assert len(timeline.review_flags) == 2


def test_timeline_builder_does_not_auto_apply_bgm_without_a_real_music_asset() -> None:
    builder = TimelineBuilder()
    segment = SegmentRecord.create(
        project_id="proj_001",
        text="Narration line",
        start_sec=0.0,
        end_sec=4.2,
    )
    recommendation = RecommendationRecord.create(
        project_id="proj_001",
        target_segment_id=segment.segment_id,
        recommendation_type=RecommendationType.BGM,
        reason="Recommended mood only; no local music asset is available.",
        score=0.88,
    )

    timeline = builder.build(
        project_id="proj_001",
        segments=[segment],
        recommendations=[recommendation],
    )

    assert not any(track.track_type == "bgm" for track in timeline.tracks)
    assert all("music/suggested" not in clip.asset_uri for track in timeline.tracks for clip in track.clips)


def test_default_projects_root_targets_project_workspace() -> None:
    assert str(DEFAULT_PROJECTS_ROOT).endswith("20_project\\65_videobox-project")
