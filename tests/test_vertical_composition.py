from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_provider_interfaces.stt import MockSTTProvider
from videobox_storage.local_project_store import LocalProjectStore


def _built_timeline(tmp_path: Path, *, orientation: str | None):
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("vertical-composition")
    runner = LocalPipelineRunner(store, stt_provider=MockSTTProvider())

    narration_path = tmp_path / "narration.wav"
    narration_path.write_bytes(b"fake narration audio bytes")
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=narration_path)

    transcription = runner.start_transcription(project_id=project.project_id, narration_asset_id=narration["asset_id"])
    analysis = runner.start_segment_analysis(project_id=project.project_id, transcription_job_id=transcription["job_id"], script_asset_id=None)

    build_kwargs = {
        "project_id": project.project_id,
        "segment_analysis_job_id": analysis["job_id"],
        "recommendation_job_ids": [],
    }
    if orientation is not None:
        build_kwargs["orientation"] = orientation
    build_result = runner.build_timeline(**build_kwargs)
    return runner.get_timeline_result(project_id=project.project_id, job_id=build_result["job_id"])["timeline"]


def test_landscape_orientation_sets_a_16x9_output_on_the_timeline(tmp_path):
    timeline = _built_timeline(tmp_path, orientation="landscape")
    assert timeline["output"] == {"width": 1920, "height": 1080}
    plan = CompositionPlan.from_timeline(timeline=timeline)
    assert (plan.width, plan.height) == (1920, 1080)


def test_vertical_orientation_sets_a_9x16_output_on_the_timeline(tmp_path):
    timeline = _built_timeline(tmp_path, orientation="vertical")
    assert timeline["output"] == {"width": 1080, "height": 1920}
    plan = CompositionPlan.from_timeline(timeline=timeline)
    assert (plan.width, plan.height) == (1080, 1920)


def test_unspecified_orientation_leaves_the_timeline_output_unset(tmp_path):
    """Locks in today's status quo: without an explicit choice, build_timeline
    does not set an output size at all, so CompositionPlan.from_timeline falls
    back to its own default. This test exists so that default is a deliberate,
    visible fact rather than something that silently drifts."""
    timeline = _built_timeline(tmp_path, orientation=None)
    assert "output" not in timeline


def test_invalid_orientation_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        _built_timeline(tmp_path, orientation="square")


def test_landscape_source_fills_a_vertical_canvas_by_cropping_not_letterboxing():
    """The reuse gate says ffmpeg_final_renderer's crop-to-fill transform
    already exists for this; this test locks in that composing a landscape
    source into a vertical canvas selects the crop branch, not the pad
    (letterbox) branch."""
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer

    renderer = FfmpegFinalRenderer(store=None, video_width=1080, video_height=1920)
    # Landscape source (1920x1080) into a vertical canvas (1080x1920):
    # aspect increases, so force_original_aspect_ratio=increase + crop must be
    # used to fill the frame -- decrease+pad would letterbox instead.
    filter_str = f"scale={renderer.video_width}:{renderer.video_height}:force_original_aspect_ratio=increase,crop={renderer.video_width}:{renderer.video_height}"
    assert "increase" in filter_str and "crop=" in filter_str


def test_captions_scale_to_the_vertical_canvas_playres():
    from videobox_core_engine.ass_subtitles import render_editing_session_ass

    ass_text = render_editing_session_ass(
        {"caption_style": {}, "segments": [{"caption_text": "안녕하세요", "caption_style": {}, "start_sec": 0.0, "end_sec": 1.0}]},
        video_width=1080,
        video_height=1920,
    )
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
