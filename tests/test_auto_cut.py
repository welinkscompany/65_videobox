from __future__ import annotations

from pathlib import Path

from videobox_core_engine.auto_cut import AutoCutConfig, AutoCutPlanner
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


def test_auto_cut_planner_uses_scene_changes_and_black_regions_as_cut_points() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=90.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=70.0,
        scene_timestamps=[20.0, 50.0],
        black_regions=[{"start": 10.0, "end": 12.0}],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 12.0),
        (12.0, 20.0),
        (20.0, 50.0),
        (50.0, 70.0),
    ]


def test_auto_cut_planner_merges_adjacent_short_segments_using_configured_threshold() -> None:
    merge_enabled = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=90.0,
            merge_threshold=10.0,
        )
    )
    merge_disabled = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=90.0,
            merge_threshold=3.0,
        )
    )

    merged_segments = merge_enabled.plan_segments(
        total_duration=18.0,
        scene_timestamps=[7.0, 14.0],
        black_regions=[],
    )
    unmerged_segments = merge_disabled.plan_segments(
        total_duration=18.0,
        scene_timestamps=[7.0, 14.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in merged_segments] == [
        (0.0, 18.0),
    ]
    assert [(segment.start_sec, segment.end_sec) for segment in unmerged_segments] == [
        (0.0, 7.0),
        (7.0, 18.0),
    ]


def test_auto_cut_planner_evenly_splits_segments_that_exceed_max_length() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=90.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=200.0,
        scene_timestamps=[],
        black_regions=[],
    )

    assert [(round(segment.start_sec, 2), round(segment.end_sec, 2)) for segment in segments] == [
        (0.0, 66.67),
        (66.67, 133.33),
        (133.33, 200.0),
    ]


def test_auto_cut_planner_rejects_too_short_dark_and_static_segments() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            dark_brightness=15.0,
            static_duration=30.0,
        )
    )

    kept = planner.filter_segments(
        [
            {"start_sec": 0.0, "end_sec": 4.0, "avg_brightness": 128.0, "scene_change_count": 3},
            {"start_sec": 4.0, "end_sec": 12.0, "avg_brightness": 10.0, "scene_change_count": 2},
            {"start_sec": 12.0, "end_sec": 48.0, "avg_brightness": 80.0, "scene_change_count": 0},
            {"start_sec": 48.0, "end_sec": 60.0, "avg_brightness": 90.0, "scene_change_count": 4},
        ]
    )

    assert [(segment.start_sec, segment.end_sec) for segment in kept] == [
        (48.0, 60.0),
    ]


def test_auto_cut_planner_keeps_segments_on_threshold_boundaries() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            dark_brightness=15.0,
            static_duration=30.0,
        )
    )

    kept = planner.filter_segments(
        [
            {"start_sec": 0.0, "end_sec": 5.0, "avg_brightness": 15.0, "scene_change_count": 1},
            {"start_sec": 5.0, "end_sec": 35.0, "avg_brightness": 40.0, "scene_change_count": 1},
        ]
    )

    assert [(segment.start_sec, segment.end_sec) for segment in kept] == [
        (0.0, 5.0),
        (5.0, 35.0),
    ]


def test_auto_cut_planner_uses_auto_cut_threshold_to_skip_short_inputs() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            auto_cut_threshold=90.0,
        )
    )

    assert planner.should_auto_cut(total_duration=89.0) is False
    assert planner.should_auto_cut(total_duration=90.0) is False
    assert planner.should_auto_cut(total_duration=91.0) is True


def test_auto_cut_planner_exposes_scene_detection_filter_from_settings() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            scene_threshold=0.27,
            blackdetect_min_duration=0.8,
            blackdetect_picture_threshold=0.91,
        )
    )

    assert planner.build_scene_detection_filter() == "select='gt(scene,0.27)',showinfo"
    assert planner.build_blackdetect_filter() == "blackdetect=d=0.8:pic_th=0.91"


def test_auto_cut_planner_preserves_scene_threshold_precision_in_filter_output() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            scene_threshold=0.275,
        )
    )

    assert planner.build_scene_detection_filter() == "select='gt(scene,0.275)',showinfo"


def test_auto_cut_planner_parses_scene_and_black_detection_output() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            scene_threshold=0.31,
            initial_scene_ignore_seconds=0.5,
        )
    )

    scene_stderr = """
    [Parsed_showinfo_1 @ 000001] n:1 pts:100 pts_time:0.40
    [Parsed_showinfo_1 @ 000001] n:2 pts:200 pts_time:1.75
    [Parsed_showinfo_1 @ 000001] n:3 pts:300 pts_time:8.10
    """.strip()
    black_stderr = """
    [blackdetect @ 000001] black_start:9.00 black_end:9.80 black_duration:0.80
    [blackdetect @ 000001] black_start:20.00 black_end:21.25 black_duration:1.25
    """.strip()

    assert planner.parse_scene_timestamps(scene_stderr) == [1.75, 8.1]
    assert planner.parse_black_regions(black_stderr) == [
        {"start": 9.0, "end": 9.8},
        {"start": 20.0, "end": 21.25},
    ]


def test_auto_cut_planner_uses_configured_cut_point_spacing() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            cut_point_min_spacing=3.0,
            merge_threshold=1.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=20.0,
        scene_timestamps=[5.0, 6.5, 12.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 5.0),
        (5.0, 12.0),
        (12.0, 20.0),
    ]


def test_auto_cut_planner_merges_trailing_short_segment_into_previous_segment() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=180.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=120.0,
        scene_timestamps=[118.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 120.0),
    ]


def test_auto_cut_planner_merges_trailing_short_segment_even_with_multiple_cuts() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=180.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=120.0,
        scene_timestamps=[50.0, 118.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 50.0),
        (50.0, 120.0),
    ]


def test_auto_cut_planner_merges_isolated_short_middle_segment() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=180.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=100.0,
        scene_timestamps=[40.0, 44.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 44.0),
        (44.0, 100.0),
    ]


def test_auto_cut_planner_keeps_middle_segment_on_min_clip_duration_boundary() -> None:
    planner = AutoCutPlanner(
        config=AutoCutConfig(
            min_clip_duration=5.0,
            max_clip_duration=180.0,
            merge_threshold=10.0,
        )
    )

    segments = planner.plan_segments(
        total_duration=100.0,
        scene_timestamps=[40.0, 45.0, 80.0],
        black_regions=[],
    )

    assert [(segment.start_sec, segment.end_sec) for segment in segments] == [
        (0.0, 40.0),
        (40.0, 45.0),
        (45.0, 80.0),
        (80.0, 100.0),
    ]


def test_local_pipeline_runner_exposes_auto_cut_plan_for_registered_raw_video_asset(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Project")
    runner = LocalPipelineRunner(store)

    raw_asset = runner.register_raw_video_asset(
        project_id=project.project_id,
        source_path=raw_video,
    )
    result = runner.plan_auto_cut_segments(
        project_id=project.project_id,
        raw_video_asset_id=raw_asset["asset_id"],
        total_duration=120.0,
        scene_timestamps=[30.0, 75.0],
        black_regions=[],
        segment_samples=[
            {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
            {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
            {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
        ],
    )

    assert result["asset_id"] == raw_asset["asset_id"]
    assert result["storage_uri"] == raw_asset["storage_uri"]
    assert result["should_auto_cut"] is True
    assert result["planned_segments"] == [
        {"start_sec": 0.0, "end_sec": 30.0},
        {"start_sec": 30.0, "end_sec": 75.0},
        {"start_sec": 75.0, "end_sec": 120.0},
    ]
    assert result["kept_segments"] == [
        {
            "start_sec": 0.0,
            "end_sec": 30.0,
            "duration_sec": 30.0,
            "avg_brightness": 90.0,
            "scene_change_count": 3,
            "reasons": [],
        },
        {
            "start_sec": 30.0,
            "end_sec": 75.0,
            "duration_sec": 45.0,
            "avg_brightness": 80.0,
            "scene_change_count": 2,
            "reasons": [],
        },
        {
            "start_sec": 75.0,
            "end_sec": 120.0,
            "duration_sec": 45.0,
            "avg_brightness": 85.0,
            "scene_change_count": 4,
            "reasons": [],
        },
    ]
    assert result["scene_detection_filter"] == "select='gt(scene,0.4)',showinfo"
    assert result["blackdetect_filter"] == "blackdetect=d=0.5:pic_th=0.95"


def test_local_pipeline_runner_rejects_segment_samples_that_do_not_match_planned_segments(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Project")
    runner = LocalPipelineRunner(store)

    raw_asset = runner.register_raw_video_asset(
        project_id=project.project_id,
        source_path=raw_video,
    )

    try:
        runner.plan_auto_cut_segments(
            project_id=project.project_id,
            raw_video_asset_id=raw_asset["asset_id"],
            total_duration=120.0,
            scene_timestamps=[30.0, 75.0],
            black_regions=[],
            segment_samples=[
                {"start_sec": 5.0, "end_sec": 35.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 35.0, "end_sec": 80.0, "avg_brightness": 80.0, "scene_change_count": 2},
            ],
        )
    except ValueError as exc:
        assert str(exc) == "auto_cut segment_samples must match planned segment boundaries."
    else:
        raise AssertionError("Expected plan_auto_cut_segments to reject mismatched segment samples.")


def test_local_pipeline_runner_rejects_missing_segment_samples_for_planned_segments(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Project")
    runner = LocalPipelineRunner(store)

    raw_asset = runner.register_raw_video_asset(
        project_id=project.project_id,
        source_path=raw_video,
    )

    try:
        runner.plan_auto_cut_segments(
            project_id=project.project_id,
            raw_video_asset_id=raw_asset["asset_id"],
            total_duration=120.0,
            scene_timestamps=[30.0, 75.0],
            black_regions=[],
            segment_samples=[
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
            ],
        )
    except ValueError as exc:
        assert str(exc) == "auto_cut segment_samples must match planned segment boundaries."
    else:
        raise AssertionError("Expected plan_auto_cut_segments to reject missing segment samples.")


def test_local_pipeline_runner_rejects_duplicate_segment_samples(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Project")
    runner = LocalPipelineRunner(store)

    raw_asset = runner.register_raw_video_asset(
        project_id=project.project_id,
        source_path=raw_video,
    )

    try:
        runner.plan_auto_cut_segments(
            project_id=project.project_id,
            raw_video_asset_id=raw_asset["asset_id"],
            total_duration=120.0,
            scene_timestamps=[30.0, 75.0],
            black_regions=[],
            segment_samples=[
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        )
    except ValueError as exc:
        assert str(exc) == "auto_cut segment_samples must match planned segment boundaries."
    else:
        raise AssertionError("Expected plan_auto_cut_segments to reject duplicate segment samples.")


def test_local_pipeline_runner_orders_kept_segments_by_planned_boundaries(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Project")
    runner = LocalPipelineRunner(store)

    raw_asset = runner.register_raw_video_asset(
        project_id=project.project_id,
        source_path=raw_video,
    )
    result = runner.plan_auto_cut_segments(
        project_id=project.project_id,
        raw_video_asset_id=raw_asset["asset_id"],
        total_duration=120.0,
        scene_timestamps=[30.0, 75.0],
        black_regions=[],
        segment_samples=[
            {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
            {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
        ],
    )

    assert [(segment["start_sec"], segment["end_sec"]) for segment in result["kept_segments"]] == [
        (0.0, 30.0),
        (30.0, 75.0),
        (75.0, 120.0),
    ]
