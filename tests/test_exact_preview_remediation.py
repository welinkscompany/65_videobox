from __future__ import annotations

import shutil
import subprocess
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.composition_plan import CompositionPlan, materialize_editing_session_timeline
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.exact_preview import ExactPreviewRequest
from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.assets import AssetType


def test_current_session_materializes_overrides_cut_and_source_bounds_once() -> None:
    """All render consumers must start from the operator's current session."""
    base = {
        "output": {"width": 320, "height": 240},
        "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "n", "segment_id": "s1", "asset_uri": "local://n", "start_sec": 0, "end_sec": 2}]},
            {"track_type": "broll", "clips": [{"clip_id": "old-b", "segment_id": "s1", "asset_id": "old", "asset_uri": "local://old", "start_sec": 0, "end_sec": 2}]},
            {"track_type": "bgm", "clips": [{"clip_id": "old-m", "segment_id": "s1", "asset_id": "old-m", "asset_uri": "local://old-m", "start_sec": 0, "end_sec": 2}]},
        ],
    }
    session = {
        "segments": [{
            "segment_id": "s1", "start_sec": 0, "end_sec": 2, "caption_text": "edited",
            "cut_action": "keep",
            "broll_override": {"asset_id": "new-b", "asset_uri": "local://new-b", "media_controls": {"trim_start_sec": 0.25, "in_sec": 0.5, "out_sec": 1.75, "loop": False, "pad": True}},
            "music_override": {"asset_id": "new-m", "asset_uri": "local://new-m", "media_controls": {"gain_db": -6}},
            "sfx_override": {"asset_id": "new-s", "asset_uri": "local://new-s", "media_controls": {"gain_db": 3}},
            "visual_overlays": [{"overlay_type": "image_card", "asset_id": "new-o", "asset_uri": "local://new-o"}],
        }],
    }

    materialized = materialize_editing_session_timeline(timeline=base, editing_session=session)
    plan = CompositionPlan.from_timeline(timeline=materialized, captions=session["segments"])

    assert [(item.track_type, item.asset_id) for item in plan.items] == [
        ("bgm", "new-m"), ("broll", "new-b"), ("narration", None), ("overlay", "new-o"), ("sfx", "new-s"),
    ]
    broll = next(item for item in plan.items if item.track_type == "broll")
    assert (broll.source_in_sec, broll.source_out_sec) == (0.75, 1.75)
    assert "old-b" not in [clip["clip_id"] for track in materialized["tracks"] for clip in track["clips"]]


def test_current_session_remove_cut_removes_all_segment_media_and_caption() -> None:
    base = {"tracks": [
        {"track_type": "narration", "clips": [{"clip_id": "n", "segment_id": "s1", "asset_uri": "local://n", "start_sec": 0, "end_sec": 1}]},
        {"track_type": "broll", "clips": [{"clip_id": "b", "segment_id": "s1", "asset_uri": "local://b", "start_sec": 0, "end_sec": 1}]},
    ]}
    session = {"segments": [{"segment_id": "s1", "start_sec": 0, "end_sec": 1, "caption_text": "removed", "cut_action": "remove", "visual_overlays": []}]}

    materialized = materialize_editing_session_timeline(timeline=base, editing_session=session)

    assert materialized["tracks"] == []


def test_current_session_bounds_shift_source_time_and_removed_export_overlay_is_absent() -> None:
    base = {
        "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b", "segment_id": "keep", "asset_uri": "local://b",
            "start_sec": 0, "end_sec": 4, "source_in_sec": 3, "source_out_sec": 7,
        }]}],
        "export_overlays": [
            {"segment_id": "remove", "title": "removed", "start_sec": 4, "end_sec": 5},
            {"segment_id": "keep", "title": "kept", "start_sec": 0, "end_sec": 4},
        ],
    }
    session = {"segments": [
        {"segment_id": "keep", "start_sec": 1, "end_sec": 3, "cut_action": "keep", "visual_overlays": []},
        {"segment_id": "remove", "start_sec": 4, "end_sec": 5, "cut_action": "remove", "visual_overlays": []},
    ]}

    plan = CompositionPlan.from_timeline(timeline=materialize_editing_session_timeline(timeline=base, editing_session=session))

    broll = plan.items[0]
    assert (broll.start_sec, broll.end_sec, broll.source_in_sec, broll.source_out_sec) == (1.0, 3.0, 4.0, 6.0)
    assert [overlay["title"] for overlay in plan.export_overlays] == ["kept"]


def test_session_source_offsets_distinguish_trim_from_reorder_and_migrate_legacy_sessions() -> None:
    """A relayout moves placement only; a bounds edit deliberately trims source."""
    from videobox_core_engine.editing_session import reorder_segments, set_segment_bounds

    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "red", "segment_id": "red", "asset_uri": "local://red", "start_sec": 0, "end_sec": 2, "source_in_sec": 0, "source_out_sec": 2},
        {"clip_id": "blue", "segment_id": "blue", "asset_uri": "local://blue", "start_sec": 2, "end_sec": 4, "source_in_sec": 0, "source_out_sec": 2},
    ]}]}
    # Old persisted sessions have no source_offset_sec.  Their mutation
    # history must distinguish a timeline-only reorder from a trim.
    legacy = {"segments": [
        {"segment_id": "red", "start_sec": 0, "end_sec": 2, "cut_action": "keep", "visual_overlays": []},
        {"segment_id": "blue", "start_sec": 2, "end_sec": 4, "cut_action": "keep", "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    reordered = reorder_segments(
        session=legacy, segment_ids=["blue", "red"],
        bounds_by_id={"blue": {"start_sec": 0, "end_sec": 2}, "red": {"start_sec": 2, "end_sec": 4}},
    )
    reordered_plan = CompositionPlan.from_timeline(timeline=materialize_editing_session_timeline(timeline=timeline, editing_session=reordered))
    assert [(item.clip_id, item.start_sec, item.source_in_sec, item.source_out_sec) for item in reordered_plan.items] == [
        ("blue", 0.0, 0.0, 2.0), ("red", 2.0, 0.0, 2.0),
    ]

    current = {**legacy, "segments": [{**segment, "source_offset_sec": 0.0} for segment in legacy["segments"]]}
    trimmed = set_segment_bounds(session=current, segment_id="red", start_sec=1, end_sec=2)
    assert trimmed["segments"][0]["source_offset_sec"] == 1.0
    expanded = set_segment_bounds(session=trimmed, segment_id="red", start_sec=0, end_sec=2)
    assert expanded["segments"][0]["source_slices"] == [{"segment_id": "red", "source_offset_sec": 0.0, "duration_sec": 2.0}]
    combined = reorder_segments(
        session=trimmed, segment_ids=["blue", "red"],
        bounds_by_id={"blue": {"start_sec": 0, "end_sec": 2}, "red": {"start_sec": 2, "end_sec": 3}},
    )
    combined_plan = CompositionPlan.from_timeline(timeline=materialize_editing_session_timeline(timeline=timeline, editing_session=combined))
    red = next(item for item in combined_plan.items if item.clip_id == "red")
    assert (red.start_sec, red.end_sec, red.source_in_sec, red.source_out_sec) == (2.0, 3.0, 1.0, 2.0)

    # A session saved before this migration may carry an earlier bounds event
    # but not the new durable field yet.  Its next trim must continue from
    # the historical source position instead of resetting to zero.
    old_trimmed = set_segment_bounds(session=legacy, segment_id="red", start_sec=1, end_sec=2)
    del old_trimmed["segments"][0]["source_offset_sec"]
    continued = set_segment_bounds(session=old_trimmed, segment_id="red", start_sec=1.5, end_sec=2)
    assert continued["segments"][0]["source_offset_sec"] == 1.5


def test_session_split_and_merge_materialize_source_slices_without_losing_media() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments, split_segment
    from videobox_core_engine.exact_preview import fingerprint_exact_preview

    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "source", "segment_id": "source", "asset_uri": "local://source", "start_sec": 0, "end_sec": 4, "source_in_sec": 3, "source_out_sec": 7},
    ]}]}
    session = {"segments": [{"segment_id": "source", "start_sec": 0, "end_sec": 4, "source_offset_sec": 0, "source_slices": [{"segment_id": "source", "source_offset_sec": 0, "duration_sec": 4}], "caption_text": "", "cut_action": "keep", "visual_overlays": []}], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}

    split = split_segment(session=session, segment_id="source", split_sec=2)
    split_plan = CompositionPlan.from_timeline(timeline=materialize_editing_session_timeline(timeline=timeline, editing_session=split))
    assert [(item.start_sec, item.end_sec, item.source_in_sec, item.source_out_sec) for item in split_plan.items] == [
        (0.0, 2.0, 3.0, 5.0), (2.0, 4.0, 5.0, 7.0),
    ]
    base_plan = CompositionPlan.from_timeline(timeline=timeline)
    assert fingerprint_exact_preview(plan=split_plan, session_captions=(), used_asset_sha256={}) != fingerprint_exact_preview(plan=base_plan, session_captions=(), used_asset_sha256={})

    merged = merge_adjacent_segments(session=split, left_segment_id="source", right_segment_id="source__split_2")
    merged_plan = CompositionPlan.from_timeline(timeline=materialize_editing_session_timeline(timeline=timeline, editing_session=merged))
    assert [(item.start_sec, item.end_sec, item.source_in_sec, item.source_out_sec) for item in merged_plan.items] == [
        (0.0, 2.0, 3.0, 5.0), (2.0, 4.0, 5.0, 7.0),
    ]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_split_merge_and_reorder_render_all_source_slices_for_proxy_and_final(tmp_path: Path) -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments, reorder_segments, split_segment

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="split merge exact source")
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": "source", "segment_id": "source", "asset_id": asset.asset_id, "asset_uri": uri, "start_sec": 0, "end_sec": 4, "source_in_sec": 0, "source_out_sec": 4}]}]}
    session = {"segments": [{"segment_id": "source", "start_sec": 0, "end_sec": 4, "source_offset_sec": 0, "source_slices": [{"segment_id": "source", "source_offset_sec": 0, "duration_sec": 4}], "caption_text": "", "cut_action": "keep", "visual_overlays": []}], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)

    def render_pair(label: str, editing_session: dict[str, object]) -> tuple[Path, Path]:
        materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=editing_session, project_id=project.project_id)
        plan = CompositionPlan.from_timeline(timeline=materialized)
        proxy, final = tmp_path / f"{label}-proxy.mp4", tmp_path / f"{label}-final.mp4"
        renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=materialized, output_path=proxy, subtitle_ass_path=None)
        renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, composition_plan=plan, output_path=final)
        return proxy, final

    def pixel(path: Path, second: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(second), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    split = split_segment(session=session, segment_id="source", split_sec=2)
    for output in render_pair("split", split):
        assert pixel(output, 0.5)[0] > 200
        assert pixel(output, 2.5)[2] > 200

    reordered = reorder_segments(session=split, segment_ids=["source__split_2", "source"], bounds_by_id={"source__split_2": {"start_sec": 0, "end_sec": 2}, "source": {"start_sec": 2, "end_sec": 4}})
    for output in render_pair("reordered", reordered):
        assert pixel(output, 0.5)[2] > 200
        assert pixel(output, 2.5)[0] > 200

    merged = merge_adjacent_segments(session=split, left_segment_id="source", right_segment_id="source__split_2")
    for output in render_pair("merged", merged):
        assert pixel(output, 0.5)[0] > 200
        assert pixel(output, 2.5)[2] > 200


def test_broll_controls_fail_before_render_when_window_is_invalid_or_insufficient_without_pad_or_loop() -> None:
    invalid = {"tracks": [{"track_type": "broll", "clips": [{
        "asset_uri": "local://b", "start_sec": 0, "end_sec": 1,
        "media_controls": {"trim_start_sec": 1, "in_sec": 1, "out_sec": 1.5},
    }]}]}
    short_without_fallback = {"tracks": [{"track_type": "broll", "clips": [{
        "asset_uri": "local://b", "start_sec": 0, "end_sec": 1,
        "media_controls": {"in_sec": 0, "out_sec": 0.25, "loop": False, "pad": False},
    }]}]}

    with pytest.raises(ValueError, match="composition_plan_invalid_source_bounds"):
        CompositionPlan.from_timeline(timeline=invalid)
    with pytest.raises(ValueError, match="composition_plan_insufficient_broll_source"):
        CompositionPlan.from_timeline(timeline=short_without_fallback)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_session_bounds_and_removed_overlay_render_correct_source_for_exact_and_final_full_and_range(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="session bounds exact final")
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": "b", "segment_id": "s", "asset_id": asset.asset_id, "asset_uri": uri, "start_sec": 0, "end_sec": 3, "source_in_sec": 0, "source_out_sec": 3}]}], "export_overlays": [{"segment_id": "removed", "title": "do not render", "start_sec": 3, "end_sec": 4}]}
    session = {"segments": [
        {"segment_id": "s", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "visual_overlays": []},
        {"segment_id": "removed", "start_sec": 3, "end_sec": 4, "cut_action": "remove", "visual_overlays": []},
    ]}
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=session, project_id=project.project_id)
    plan = CompositionPlan.from_timeline(timeline=materialized)
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)
    full_proxy, full_final, range_proxy, range_final = (tmp_path / name for name in ("full-proxy.mp4", "full-final.mp4", "range-proxy.mp4", "range-final.mp4"))
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=materialized, output_path=full_proxy, subtitle_ass_path=None)
    renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, composition_plan=plan, output_path=full_final)
    ranged = plan.for_range(start_sec=1, end_sec=2)
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=ranged, timeline_context=materialized, output_path=range_proxy, subtitle_ass_path=None)
    renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, composition_plan=ranged, output_path=range_final)

    def pixel(path: Path, seconds: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    for output in (full_proxy, full_final):
        assert pixel(output, 0.5) == (0, 0, 0)
        assert pixel(output, 1.5)[2] > 200 and pixel(output, 1.5)[0] < 30
    for output in (range_proxy, range_final):
        assert pixel(output, 0.5)[2] > 200 and pixel(output, 0.5)[0] < 30


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_short_broll_source_window_loops_or_black_pads_only_when_its_control_allows_it(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="short broll control behavior")
    source = tmp_path / "blue.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)

    def render(name: str, controls: dict[str, object]) -> Path:
        timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": name, "asset_id": asset.asset_id, "asset_uri": uri, "start_sec": 0, "end_sec": 1, "media_controls": controls}]}]}
        output = tmp_path / f"{name}.mp4"
        renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=CompositionPlan.from_timeline(timeline=timeline), timeline_context=timeline, output_path=output, subtitle_ass_path=None)
        return output

    looped = render("looped", {"in_sec": 0, "out_sec": 0.25, "loop": True, "pad": False})
    padded = render("padded", {"in_sec": 0, "out_sec": 0.25, "loop": False, "pad": True})

    def pixel(path: Path) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.75", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    assert pixel(looped)[2] > 200
    assert pixel(padded) == (0, 0, 0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_reorder_and_trim_keep_source_content_for_proxy_and_final(tmp_path: Path) -> None:
    """The same segment keeps its source through relayout; only trim advances it."""
    from videobox_core_engine.editing_session import reorder_segments, set_segment_bounds

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="reorder source contract")
    red_green, blue = tmp_path / "red-green.mp4", tmp_path / "blue.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(red_green)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2", "-pix_fmt", "yuv420p", str(blue)], check=True, capture_output=True)
    red_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=red_green)
    blue_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=blue)
    uri = lambda asset: f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "red", "segment_id": "red", "asset_id": red_asset.asset_id, "asset_uri": uri(red_asset), "start_sec": 0, "end_sec": 2, "source_in_sec": 0, "source_out_sec": 2},
        {"clip_id": "blue", "segment_id": "blue", "asset_id": blue_asset.asset_id, "asset_uri": uri(blue_asset), "start_sec": 2, "end_sec": 4, "source_in_sec": 0, "source_out_sec": 2},
    ]}]}
    session = {"segments": [
        {"segment_id": "red", "start_sec": 0, "end_sec": 2, "source_offset_sec": 0, "cut_action": "keep", "visual_overlays": []},
        {"segment_id": "blue", "start_sec": 2, "end_sec": 4, "source_offset_sec": 0, "cut_action": "keep", "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)

    def render_pair(prefix: str, editing_session: dict[str, object]) -> tuple[Path, Path]:
        materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=editing_session, project_id=project.project_id)
        plan = CompositionPlan.from_timeline(timeline=materialized)
        proxy, final = tmp_path / f"{prefix}-proxy.mp4", tmp_path / f"{prefix}-final.mp4"
        renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=materialized, output_path=proxy, subtitle_ass_path=None)
        renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, composition_plan=plan, output_path=final)
        return proxy, final

    def pixel(path: Path, second: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(second), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    reordered = reorder_segments(session=session, segment_ids=["blue", "red"], bounds_by_id={"blue": {"start_sec": 0, "end_sec": 2}, "red": {"start_sec": 2, "end_sec": 4}})
    for output in render_pair("reorder", reordered):
        assert pixel(output, 0.5)[2] > 200
        assert pixel(output, 2.5)[0] > 200

    trimmed = set_segment_bounds(session=session, segment_id="red", start_sec=1, end_sec=2)
    combined = reorder_segments(session=trimmed, segment_ids=["blue", "red"], bounds_by_id={"blue": {"start_sec": 0, "end_sec": 2}, "red": {"start_sec": 2, "end_sec": 3}})
    for output in render_pair("combined", combined):
        assert pixel(output, 0.5)[2] > 200
        assert pixel(output, 2.5)[1] > 100 and pixel(output, 2.5)[0] < 30


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_looping_broll_preserves_source_audio_for_the_full_timeline_window(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="looped broll source audio")
    source = tmp_path / "tone.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1", "-shortest", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": "loop", "asset_id": asset.asset_id, "asset_uri": uri, "start_sec": 0, "end_sec": 2, "source_in_sec": 0, "source_out_sec": 1, "media_controls": {"loop": True, "pad": False, "preserve_source_audio": True}}]}]}
    plan = CompositionPlan.from_timeline(timeline=timeline)
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)
    proxy, final = tmp_path / "loop-proxy.mp4", tmp_path / "loop-final.mp4"
    for output, method in ((proxy, renderer.render_exact_preview_to_mp4), (final, renderer.render_timeline_to_mp4)):
        kwargs = {"project_id": project.project_id, "composition_plan": plan, "timeline_context": timeline, "output_path": output}
        if method == renderer.render_exact_preview_to_mp4:
            method(**kwargs, subtitle_ass_path=None)
        else:
            method(project_id=project.project_id, timeline=timeline, composition_plan=plan, output_path=output)
        samples = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.5", "-t", "0.1", "-i", str(output), "-f", "s16le", "-ac", "1", "-ar", "48000", "pipe:1"], check=True, capture_output=True).stdout
        assert max(abs(sample[0]) for sample in struct.iter_unpack("<h", samples)) > 500


def test_recent_running_claim_from_a_dead_process_is_reclaimed_without_late_publish(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="recent restart recovery")
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"duration_sec": 1}, "tracks": []})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    old = LocalPipelineRunner(store).start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=old["generation_id"], owner_token="dead-process-worker")

    # A new store instance models a fresh API process while the old claim is
    # still recent, so timestamp-only recovery must not leave it coalesced.
    restarted_store = LocalProjectStore(tmp_path)
    restarted = LocalPipelineRunner(restarted_store).start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)
    worker_output = tmp_path / "late.mp4"; worker_output.write_bytes(b"late")

    assert restarted["generation_id"] != old["generation_id"]
    assert restarted_store.get_exact_preview(project_id=project.project_id, generation_id=old["generation_id"])["state"] == "failed"
    assert not restarted_store.finish_exact_preview(project_id=project.project_id, generation_id=old["generation_id"], fingerprint=old["fingerprint"], artifact_path=worker_output, owner_token="dead-process-worker")


def test_source_mutation_between_render_and_publish_is_never_succeeded(tmp_path: Path) -> None:
    class MutatingRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs):  # type: ignore[no-untyped-def]
            output_path.write_bytes(b"rendered-before-source-mutation")
            self.mutate_path.write_bytes(b"mutated-after-render")
            return output_path

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="publish source fence")
    source = tmp_path / "source.mp4"; source.write_bytes(b"before")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"duration_sec": 1}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": "b", "asset_id": asset.asset_id, "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}", "start_sec": 0, "end_sec": 1}]}]})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    renderer = MutatingRenderer(store=store)
    renderer.mutate_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri)
    pipeline = LocalPipelineRunner(store, final_renderer=renderer)
    record = pipeline.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=1)

    pipeline.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])

    assert store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])["state"] == "obsolete"


def test_selected_exact_preview_range_is_validated_against_full_session_and_keeps_range_metadata(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="absolute selected preview range")
    timeline = store.save_timeline_run(
        project_id=project.project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 20}, "tracks": [
            {"track_type": "broll", "clips": [{"clip_id": "b", "segment_id": "s", "asset_uri": "", "start_sec": 0, "end_sec": 20}]}
        ]},
    )
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id=timeline["timeline_id"],
        session_payload={"segments": [{"segment_id": "s", "start_sec": 0, "end_sec": 20, "cut_action": "keep"}]},
    )

    record = LocalPipelineRunner(store).start_exact_preview(
        project_id=project.project_id, session_id=session["session_id"], expected_revision=1, start_sec=2, end_sec=12,
    )

    assert record["start_sec"] == 2
    assert record["end_sec"] == 12
    assert record["duration_sec"] == 10


def test_bounds_can_shrink_then_expand_back_to_immutable_source_basis() -> None:
    from videobox_core_engine.editing_session import set_segment_bounds

    session = {"segments": [{
        "segment_id": "s", "start_sec": 0, "end_sec": 4, "source_offset_sec": 0,
        "source_slices": [{"segment_id": "s", "source_offset_sec": 0, "duration_sec": 4}],
    }], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}

    shrunk = set_segment_bounds(session=session, segment_id="s", start_sec=1, end_sec=3)
    expanded = set_segment_bounds(session=shrunk, segment_id="s", start_sec=0, end_sec=4)

    segment = expanded["segments"][0]
    assert segment["source_slices"] == [{"segment_id": "s", "source_offset_sec": 0.0, "duration_sec": 4.0}]


def test_legacy_bounds_history_recovers_oldest_source_basis_for_expand() -> None:
    """Pre-basis sessions may expand through their retained bounds snapshots."""
    from videobox_core_engine.editing_session import set_segment_bounds

    def snapshot(start_sec: float, end_sec: float, *, source_offset_sec: float | None = None) -> dict[str, object]:
        segment: dict[str, object] = {"segment_id": "s", "start_sec": start_sec, "end_sec": end_sec}
        if source_offset_sec is not None:
            segment["source_slices"] = [{"segment_id": "s", "source_offset_sec": source_offset_sec, "duration_sec": end_sec - start_sec}]
        return {"segments": [segment]}

    # These were saved before source_slice_basis/source_slice_window_start_sec
    # existed.  The current slice still proves that the source begins at +2.
    session = {
        "segments": [{
            "segment_id": "s", "start_sec": 2, "end_sec": 4,
            "source_slices": [{"segment_id": "s", "source_offset_sec": 2, "duration_sec": 2}],
        }],
        "history": [
            {"mutation_type": "segment_bounds_update", "inverse_payload": snapshot(0, 4), "forward_payload": snapshot(1, 4)},
            {"mutation_type": "segment_bounds_update", "inverse_payload": snapshot(1, 4), "forward_payload": snapshot(2, 4)},
        ],
        "undo_stack": [], "redo_stack": [], "session_revision": 3,
    }

    expanded = set_segment_bounds(session=session, segment_id="s", start_sec=0, end_sec=4)

    assert expanded["segments"][0]["source_slices"] == [
        {"segment_id": "s", "source_offset_sec": 0.0, "duration_sec": 4.0},
    ]


def test_incomplete_legacy_bounds_history_refuses_unproven_right_expansion() -> None:
    """A broken pre-basis history cannot authorize synthesized source tail."""
    from videobox_core_engine.editing_session import set_segment_bounds

    def snapshot(start_sec: float, end_sec: float) -> dict[str, object]:
        return {"segments": [{"segment_id": "s", "start_sec": start_sec, "end_sec": end_sec}]}

    session = {
        "segments": [{
            "segment_id": "s", "start_sec": 2, "end_sec": 4,
            "source_slices": [{"segment_id": "s", "source_offset_sec": 2, "duration_sec": 2}],
        }],
        # Both snapshots are legacy but do not form a contiguous chain to the
        # current window, so no immutable source basis can be recovered.
        "history": [
            {"mutation_type": "segment_bounds_update", "inverse_payload": snapshot(0, 4), "forward_payload": snapshot(1, 4)},
            {"mutation_type": "segment_bounds_update", "inverse_payload": snapshot(3, 4), "forward_payload": snapshot(4, 4)},
        ],
        "undo_stack": [], "redo_stack": [], "session_revision": 3,
    }

    with pytest.raises(ValueError, match="segment_source_expansion_outside_slice"):
        set_segment_bounds(session=session, segment_id="s", start_sec=2, end_sec=7)


def test_merge_keeps_right_semantics_windowed_and_reanchors_legacy_export_overlay() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "caption_text": "left", "caption_style": {"color": "white"}, "review_required": False, "visual_overlays": [], "tts_replacement": None},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "caption_text": "right", "caption_style": {"color": "yellow"}, "review_required": True, "visual_overlays": [{"overlay_type": "text_card", "text": "right overlay"}], "tts_replacement": {"asset_id": "tts-right", "recommendation_id": "rec-right"}},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "left-media", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "right-media", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}], "export_overlays": [{"segment_id": "right", "title": "legacy right", "start_sec": 1.25, "end_sec": 1.75}]}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=merged)

    window = merged["segments"][0]["content_windows"][1]
    assert window["caption_text"] == "right" and window["caption_style"] == {"color": "yellow"}
    assert window["review_required"] is True and window["tts_replacement"]["asset_id"] == "tts-right"
    assert [(item["segment_id"], item["caption_text"], item["caption_style"], item["start_sec"], item["end_sec"]) for item in materialized["session_captions"]] == [
        ("left", "left", {"color": "white"}, 0.0, 1.0),
        ("right", "right", {"color": "yellow"}, 1.0, 2.0),
    ]
    plan = CompositionPlan.from_timeline(timeline=materialized, captions=materialized["session_captions"])
    assert [(cue.text, cue.style, cue.start_sec, cue.end_sec) for cue in plan.captions] == [
        ("left", {"color": "white"}, 0.0, 1.0),
        ("right", {"color": "yellow"}, 1.0, 2.0),
    ]
    ranged = plan.for_range(start_sec=1.0, end_sec=2.0)
    assert [(cue.text, cue.style, cue.start_sec, cue.end_sec) for cue in ranged.captions] == [
        ("right", {"color": "yellow"}, 0.0, 1.0),
    ]
    assert any(item.get("text") == "right overlay" and item["start_sec"] == 1.0 and item["end_sec"] == 2.0 for item in materialized["export_overlays"])
    legacy = next(item for item in materialized["export_overlays"] if item.get("title") == "legacy right")
    assert (legacy["start_sec"], legacy["end_sec"]) == (1.25, 1.75)


def test_legacy_export_overlay_reanchors_for_reorder_and_source_trim() -> None:
    from videobox_core_engine.editing_session import reorder_segments, set_segment_bounds

    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 2},
        {"clip_id": "right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 2, "end_sec": 4},
    ]}], "export_overlays": [{"segment_id": "right", "title": "legacy", "start_sec": 2.5, "end_sec": 3.5}]}
    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 2, "cut_action": "keep", "source_slices": [{"segment_id": "left", "source_offset_sec": 0, "duration_sec": 2}]},
        {"segment_id": "right", "start_sec": 2, "end_sec": 4, "cut_action": "keep", "source_slices": [{"segment_id": "right", "source_offset_sec": 0, "duration_sec": 2}]},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}

    reordered = reorder_segments(session=session, segment_ids=["right", "left"], bounds_by_id={"right": {"start_sec": 0, "end_sec": 2}, "left": {"start_sec": 2, "end_sec": 4}})
    reordered_overlay = materialize_editing_session_timeline(timeline=timeline, editing_session=reordered)["export_overlays"][0]
    assert (reordered_overlay["start_sec"], reordered_overlay["end_sec"]) == (0.5, 1.5)

    trimmed = set_segment_bounds(session=session, segment_id="right", start_sec=2.75, end_sec=4)
    trimmed_overlay = materialize_editing_session_timeline(timeline=timeline, editing_session=trimmed)["export_overlays"][0]
    assert (trimmed_overlay["start_sec"], trimmed_overlay["end_sec"]) == (2.75, 3.5)


@pytest.mark.parametrize("operation", ["set", "reorder", "split"])
def test_editing_session_operations_reject_nonfinite_segment_bounds(operation: str) -> None:
    from videobox_core_engine.editing_session import reorder_segments, set_segment_bounds, split_segment

    session = {"segments": [{"segment_id": "s", "start_sec": 0, "end_sec": 2}], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    with pytest.raises(ValueError):
        if operation == "set":
            set_segment_bounds(session=session, segment_id="s", start_sec=float("nan"), end_sec=1)
        elif operation == "reorder":
            reorder_segments(session=session, segment_ids=["s"], bounds_by_id={"s": {"start_sec": 0, "end_sec": float("inf")}})
        else:
            split_segment(session=session, segment_id="s", split_sec=float("nan"))


def test_segment_order_api_schema_rejects_nonfinite_nested_bounds() -> None:
    from pydantic import ValidationError
    from videobox_api.models import SegmentOrderRequest

    with pytest.raises(ValidationError):
        SegmentOrderRequest(expected_revision=1, segment_ids=["s"], bounds_by_id={"s": {"start_sec": 0, "end_sec": float("nan")}})


@pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
def test_segment_order_api_refuses_nonfinite_nested_bounds_before_mutating_session(tmp_path: Path, nonfinite: str) -> None:
    """JSON callers must not bypass the core finite-bounds fail-closed rule."""
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "finite segment order"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 2}, "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project_id, timeline_id=timeline["timeline_id"],
        session_payload={"segments": [{"segment_id": "s", "start_sec": 0, "end_sec": 2, "cut_action": "keep"}]},
    )

    response = client.put(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/segment-order",
        content=(
            '{"expected_revision":1,"segment_ids":["s"],"bounds_by_id":'
            '{"s":{"start_sec":0,"end_sec":' + nonfinite + '}}}'
        ),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"])["session_revision"] == 1


def test_merge_preserves_distinct_media_overrides_in_their_original_windows() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "broll_override": {"asset_id": "broll-left"}, "music_override": {"asset_id": "bgm-left"}, "sfx_override": {"asset_id": "sfx-left"}, "visual_overlays": []},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "broll_override": {"asset_id": "broll-right"}, "music_override": {"asset_id": "bgm-right"}, "sfx_override": {"asset_id": "sfx-right"}, "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "base-left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "base-right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}]}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=merged, project_id="p")
    by_track = {track["track_type"]: track["clips"] for track in materialized["tracks"]}

    for track_type, expected in (("broll", ["broll-left", "broll-right"]), ("bgm", ["bgm-left", "bgm-right"]), ("sfx", ["sfx-left", "sfx-right"])):
        clips = [clip for clip in by_track[track_type] if clip.get("asset_id") in expected]
        assert [(clip["asset_id"], clip["start_sec"], clip["end_sec"]) for clip in clips] == [(expected[0], 0, 1), (expected[1], 1, 2)]
    # Windowed overrides replace the inherited B-roll in both source slices;
    # otherwise a merge visibly composites the old base media over the choice.
    assert not [clip for clip in by_track["broll"] if clip["clip_id"].startswith("base-")]


def test_bounds_after_merge_trim_and_expand_keep_media_windows_on_their_original_moments() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments, set_segment_bounds

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "broll_override": {"asset_id": "broll-left"}, "music_override": {"asset_id": "bgm-left"}, "sfx_override": {"asset_id": "sfx-left"}, "visual_overlays": []},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "broll_override": {"asset_id": "broll-right"}, "music_override": {"asset_id": "bgm-right"}, "sfx_override": {"asset_id": "sfx-right"}, "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    trimmed = set_segment_bounds(session=merged, segment_id="left", start_sec=0.5, end_sec=2)

    def media_window_summary(value: dict[str, object]) -> list[tuple[float, float, str, str, str]]:
        return [
            (float(window["start_offset_sec"]), float(window["duration_sec"]),
             str(window.get("broll_override", {}).get("asset_id")),
             str(window.get("music_override", {}).get("asset_id")),
             str(window.get("sfx_override", {}).get("asset_id")))
            for window in value["segments"][0]["media_windows"]
        ]

    assert media_window_summary(trimmed) == [
        (0.0, 0.5, "broll-left", "bgm-left", "sfx-left"),
        (0.5, 1.0, "broll-right", "bgm-right", "sfx-right"),
    ]
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "base-left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "base-right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}]}
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=trimmed, project_id="p")
    by_track = {track["track_type"]: track["clips"] for track in materialized["tracks"]}
    for track_type, expected in (("broll", ["broll-left", "broll-right"]), ("bgm", ["bgm-left", "bgm-right"]), ("sfx", ["sfx-left", "sfx-right"])):
        assert [(clip["asset_id"], clip["start_sec"], clip["end_sec"]) for clip in by_track[track_type]] == [
            (expected[0], 0.5, 1.0), (expected[1], 1.0, 2.0),
        ]
    expanded = set_segment_bounds(session=trimmed, segment_id="left", start_sec=0, end_sec=2)
    assert media_window_summary(expanded) == [
        (0.0, 1.0, "broll-left", "bgm-left", "sfx-left"),
        (1.0, 1.0, "broll-right", "bgm-right", "sfx-right"),
    ]


def test_split_after_merge_rebases_distinct_media_windows_to_each_new_segment() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments, split_segment

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "broll_override": {"asset_id": "broll-left"}, "visual_overlays": []},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "broll_override": {"asset_id": "broll-right"}, "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "base-left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "base-right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}]}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    split = split_segment(session=merged, segment_id="left", split_sec=1)
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=split, project_id="p")
    broll = next(track["clips"] for track in materialized["tracks"] if track["track_type"] == "broll")

    assert [(clip["asset_id"], clip["start_sec"], clip["end_sec"]) for clip in broll] == [
        ("broll-left", 0, 1), ("broll-right", 1, 2),
    ]


def test_broll_update_after_merge_replaces_the_prior_windowed_choices() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments, update_segment_broll_override

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "broll_override": {"asset_id": "broll-left"}, "visual_overlays": []},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "broll_override": {"asset_id": "broll-right"}, "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "base-left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "base-right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}]}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    updated = update_segment_broll_override(session=merged, segment_id="left", asset_id="broll-new")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=updated, project_id="p")
    broll = next(track["clips"] for track in materialized["tracks"] if track["track_type"] == "broll")

    assert [(clip["asset_id"], clip["start_sec"], clip["end_sec"]) for clip in broll] == [("broll-new", 0, 2)]


def test_broll_clear_after_merge_removes_the_prior_windowed_choices() -> None:
    from videobox_core_engine.editing_session import clear_segment_broll_override, merge_adjacent_segments

    session = {"segments": [
        {"segment_id": "left", "start_sec": 0, "end_sec": 1, "cut_action": "keep", "broll_override": {"asset_id": "broll-left"}, "visual_overlays": []},
        {"segment_id": "right", "start_sec": 1, "end_sec": 2, "cut_action": "keep", "broll_override": {"asset_id": "broll-right"}, "visual_overlays": []},
    ], "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1}
    timeline = {"tracks": [{"track_type": "broll", "clips": [
        {"clip_id": "base-left", "segment_id": "left", "asset_uri": "local://left", "start_sec": 0, "end_sec": 1},
        {"clip_id": "base-right", "segment_id": "right", "asset_uri": "local://right", "start_sec": 1, "end_sec": 2},
    ]}]}

    merged = merge_adjacent_segments(session=session, left_segment_id="left", right_segment_id="right")
    cleared = clear_segment_broll_override(session=merged, segment_id="left")
    materialized = materialize_editing_session_timeline(timeline=timeline, editing_session=cleared, project_id="p")
    broll = next(track["clips"] for track in materialized["tracks"] if track["track_type"] == "broll")

    assert [(clip["clip_id"], clip["start_sec"], clip["end_sec"]) for clip in broll] == [
        ("base-left", 0, 1), ("base-right", 1, 2),
    ]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_current_session_media_overrides_cut_and_overlay_render_identically_for_proxy_and_final(tmp_path: Path) -> None:
    """Real media proves the materialized plan is shared, not just fingerprinted."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="session materialized exact and final")
    old, replacement, overlay = tmp_path / "old.mp4", tmp_path / "replacement.mp4", tmp_path / "overlay.png"
    bgm, sfx = tmp_path / "bgm.wav", tmp_path / "sfx.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:d=4", "-pix_fmt", "yuv420p", str(old)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(replacement)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1", "-frames:v", "1", str(overlay)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=1", str(bgm)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=1", str(sfx)], check=True, capture_output=True)
    old_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=old)
    replacement_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=replacement)
    overlay_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=overlay)
    bgm_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=bgm)
    sfx_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.SFX, source_path=sfx)
    uri = lambda asset: f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": f"base-{index}", "segment_id": f"s{index}", "asset_id": old_asset.asset_id, "asset_uri": uri(old_asset), "start_sec": index - 1, "end_sec": index} for index in range(1, 5)]}]})
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": [
        {"segment_id": "s1", "start_sec": 0, "end_sec": 1, "caption_text": "", "cut_action": "keep", "broll_override": {"asset_id": replacement_asset.asset_id, "media_controls": {"in_sec": 1, "out_sec": 2, "loop": False, "pad": True}}, "visual_overlays": []},
        {"segment_id": "s2", "start_sec": 1, "end_sec": 2, "caption_text": "", "cut_action": "keep", "music_override": {"asset_id": bgm_asset.asset_id, "asset_uri": uri(bgm_asset), "media_controls": {"gain_db": 0}}, "sfx_override": {"asset_id": sfx_asset.asset_id, "asset_uri": uri(sfx_asset), "media_controls": {"gain_db": 0}}, "visual_overlays": []},
        {"segment_id": "s3", "start_sec": 2, "end_sec": 3, "caption_text": "", "cut_action": "keep", "visual_overlays": [{"overlay_type": "image_card", "asset_id": overlay_asset.asset_id}]},
        {"segment_id": "s4", "start_sec": 3, "end_sec": 4, "caption_text": "removed", "cut_action": "remove", "visual_overlays": []},
    ]})
    pipeline = LocalPipelineRunner(store)
    _session, materialized, plan, _fingerprint = pipeline._exact_preview_inputs(project_id=project.project_id, session_id=session["session_id"])
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)
    proxy, final = tmp_path / "proxy.mp4", tmp_path / "final.mp4"
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=materialized, output_path=proxy, subtitle_ass_path=None)
    renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=materialized, output_path=final, composition_plan=plan)

    def pixel(path: Path, second: float) -> tuple[int, int, int]:
        frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(second), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
        return tuple(frame[:3])

    for output in (proxy, final):
        assert pixel(output, 0.5)[2] > 200  # B-roll override + in_sec selects blue half.
        assert pixel(output, 2.5)[0] > 200  # Session visual overlay is composited.
        streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(output)], check=True, capture_output=True, text=True).stdout
        assert "video" in streams and "audio" in streams
        raw_audio = subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.25", "-t", "0.1", "-i", str(output), "-f", "s16le", "-ac", "1", "-ar", "48000", "pipe:1"], check=True, capture_output=True).stdout
        assert max(abs(sample[0]) for sample in struct.iter_unpack("<h", raw_audio)) > 500  # session BGM/SFX are actually mixed.
        duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output)], check=True, capture_output=True, text=True).stdout)
        assert duration < 3.2  # Session cut removed the fourth segment.
    assert [item.asset_id for item in plan.items if item.track_type in {"bgm", "sfx"}] == [bgm_asset.asset_id, sfx_asset.asset_id]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg fixture required")
def test_narration_only_exact_proxy_uses_reviewable_black_canvas_with_audio(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="narration-only exact preview")
    narration = tmp_path / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1", str(narration)], check=True, capture_output=True)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration)
    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {"output": {"width": 320, "height": 240}, "tracks": [{"track_type": "narration", "clips": [{"clip_id": "n", "asset_id": asset.asset_id, "asset_uri": uri, "start_sec": 0, "end_sec": 1}]}]}
    output = tmp_path / "narration-only.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240).render_exact_preview_to_mp4(
        project_id=project.project_id, composition_plan=CompositionPlan.from_timeline(timeline=timeline),
        timeline_context=timeline, output_path=output, subtitle_ass_path=None,
    )

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(output)], check=True, capture_output=True, text=True).stdout
    pixel = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
    assert "video" in probe and "audio" in probe
    assert tuple(pixel[:3]) == (0, 0, 0)
