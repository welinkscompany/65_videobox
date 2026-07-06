from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


class _FakeAutoCutExecutor:
    def __init__(self, detection: dict[str, Any]) -> None:
        self.detection = detection
        self.received_paths: list[Path] = []

    def run_full_detection(self, video_path: Path) -> dict[str, Any]:
        self.received_paths.append(video_path)
        return self.detection


def test_run_auto_cut_detection_feeds_executor_output_into_plan_auto_cut_segments(tmp_path: Path) -> None:
    raw_video = tmp_path / "source-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Detection Project")

    fake_executor = _FakeAutoCutExecutor(
        detection={
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        }
    )
    runner = LocalPipelineRunner(store, auto_cut_executor=fake_executor)

    raw_asset = runner.register_raw_video_asset(project_id=project.project_id, source_path=raw_video)
    result = runner.run_auto_cut_detection(
        project_id=project.project_id,
        raw_video_asset_id=raw_asset["asset_id"],
    )

    assert fake_executor.received_paths == [
        store.resolve_storage_uri(project_id=project.project_id, storage_uri=raw_asset["storage_uri"])
    ]
    assert result["should_auto_cut"] is True
    assert result["planned_segments"] == [
        {"start_sec": 0.0, "end_sec": 30.0},
        {"start_sec": 30.0, "end_sec": 75.0},
        {"start_sec": 75.0, "end_sec": 120.0},
    ]
    assert [segment["avg_brightness"] for segment in result["kept_segments"]] == [90.0, 80.0, 85.0]


def test_run_auto_cut_detection_rejects_non_raw_video_asset(tmp_path: Path) -> None:
    script = tmp_path / "script.txt"
    script.write_text("hello", encoding="utf-8")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="AutoCut Detection Rejection Project")
    runner = LocalPipelineRunner(store, auto_cut_executor=_FakeAutoCutExecutor(detection={}))

    script_asset = runner.register_script_asset(project_id=project.project_id, source_path=script)

    try:
        runner.run_auto_cut_detection(
            project_id=project.project_id,
            raw_video_asset_id=script_asset["asset_id"],
        )
    except ValueError as exc:
        assert "raw_video asset" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non raw_video asset")
