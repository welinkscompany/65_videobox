"""Task 23: pick which part of a long clip to use as B-roll.

The owner films ten-minute walks and never uses all ten minutes.  Before this,
every candidate range was hardcoded to the first five seconds of the file --
which for handheld footage is usually the operator settling the camera, the
least usable part of the take.

Scene windows are already detected during media analysis and stored in
``media_scene_windows``; nothing read them back.  These tests fix the reading
end: given the windows, choose a window that actually fits the segment.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_storage.broll_source_window import choose_broll_source_window


def _window(start: float, end: float) -> dict[str, float]:
    return {"start_sec": start, "end_sec": end}


def test_falls_back_to_the_head_of_the_clip_when_no_scene_windows_exist() -> None:
    """Unanalyzed footage must keep working exactly as before."""
    chosen = choose_broll_source_window(duration_sec=600.0, needed_sec=5.0, scene_windows=[])

    assert chosen == {"start_sec": 0.0, "end_sec": 5.0}


def test_clamps_to_the_clip_when_the_segment_is_longer_than_the_footage() -> None:
    chosen = choose_broll_source_window(duration_sec=3.0, needed_sec=5.0, scene_windows=[])

    assert chosen == {"start_sec": 0.0, "end_sec": 3.0}


def test_skips_the_opening_window_and_uses_a_later_settled_scene() -> None:
    """The first window is where the camera is being set up, so a later window
    that fits is preferred."""
    chosen = choose_broll_source_window(
        duration_sec=600.0,
        needed_sec=5.0,
        scene_windows=[_window(0.0, 40.0), _window(40.0, 120.0), _window(120.0, 130.0)],
    )

    assert chosen["start_sec"] == 40.0
    assert chosen["end_sec"] == 45.0


def test_ignores_windows_that_are_shorter_than_the_segment() -> None:
    chosen = choose_broll_source_window(
        duration_sec=600.0,
        needed_sec=8.0,
        scene_windows=[_window(0.0, 30.0), _window(30.0, 33.0), _window(33.0, 90.0)],
    )

    assert chosen["start_sec"] == 33.0
    assert chosen["end_sec"] == 41.0


def test_uses_the_opening_window_when_it_is_the_only_one_that_fits() -> None:
    """Better the head of the clip than a window too short to fill the gap."""
    chosen = choose_broll_source_window(
        duration_sec=60.0,
        needed_sec=10.0,
        scene_windows=[_window(0.0, 30.0), _window(30.0, 32.0)],
    )

    assert chosen == {"start_sec": 0.0, "end_sec": 10.0}


def test_falls_back_when_every_window_is_too_short() -> None:
    """A clip chopped into very short scenes still has to produce a range."""
    chosen = choose_broll_source_window(
        duration_sec=20.0,
        needed_sec=5.0,
        scene_windows=[_window(0.0, 2.0), _window(2.0, 4.0)],
    )

    assert chosen == {"start_sec": 0.0, "end_sec": 5.0}


def test_prefers_the_longest_qualifying_window_so_the_take_is_settled() -> None:
    chosen = choose_broll_source_window(
        duration_sec=600.0,
        needed_sec=5.0,
        scene_windows=[_window(0.0, 10.0), _window(10.0, 20.0), _window(20.0, 200.0)],
    )

    assert chosen["start_sec"] == 20.0


def test_never_runs_past_the_end_of_the_clip() -> None:
    """A window whose end exceeds the real duration must not produce a range
    the renderer cannot read."""
    chosen = choose_broll_source_window(
        duration_sec=48.0,
        needed_sec=5.0,
        scene_windows=[_window(0.0, 20.0), _window(20.0, 60.0)],
    )

    assert chosen["end_sec"] <= 48.0
    assert chosen["end_sec"] - chosen["start_sec"] == pytest.approx(5.0)


@pytest.mark.parametrize("needed_sec", [0.0, -1.0])
def test_rejects_a_non_positive_segment_length(needed_sec: float) -> None:
    with pytest.raises(ValueError):
        choose_broll_source_window(duration_sec=60.0, needed_sec=needed_sec, scene_windows=[])


def _make_clip(path: Path, seconds: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True, timeout=60,
    )


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg/ffprobe to make and probe a real clip",
)
def test_draft_readiness_uses_a_scene_window_instead_of_the_head_of_a_long_clip(tmp_path: Path) -> None:
    """The wiring test: the pure chooser passing on its own proves nothing if
    the plan never calls it. This drives the real store end to end."""
    from videobox_core_engine.local_pipeline import LocalPipelineRunner
    from videobox_domain_models.media_analysis import MediaAnalysisStatus
    from videobox_storage.local_project_store import LocalProjectStore

    clip = tmp_path / "walk.mp4"
    _make_clip(clip, seconds=60)
    store = LocalProjectStore(tmp_path / "projects")
    pipeline = LocalPipelineRunner(store=store)
    project = store.bootstrap_project("scene window plan")
    asset = pipeline.register_broll_asset(project_id=project.project_id, source_path=clip, title="산책", tags=[])

    analysis = store.create_media_analysis(
        project_id=project.project_id, asset_id=asset["asset_id"],
        idempotency_key="sha:key", cache_key="key",
    )
    claimed = store.claim_media_analysis(project_id=project.project_id, analysis_id=analysis["analysis_id"])
    assert claimed is not None and claimed["status"] == MediaAnalysisStatus.RUNNING.value
    store.record_media_scene_windows(
        project_id=project.project_id, analysis_id=analysis["analysis_id"],
        source_sha256="sha", profile_hash="key",
        windows=[{"start_sec": 0.0, "end_sec": 8.0}, {"start_sec": 8.0, "end_sec": 55.0}],
    )

    plan = store._draft_readiness_plan(
        project_id=project.project_id,
        brief={"script_text": "산책 장면을 보여 줍니다."},
        narration={},
    )

    candidate = plan["broll_candidates"][0]
    # The long settled window starting at 8s wins over the opening window.
    assert candidate["target_range"] == {"start_sec": 8.0, "end_sec": 13.0}


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg/ffprobe to make and probe a real clip",
)
def test_draft_readiness_keeps_the_old_head_range_for_unanalyzed_footage(tmp_path: Path) -> None:
    """Footage that was never analyzed must behave exactly as before."""
    from videobox_core_engine.local_pipeline import LocalPipelineRunner
    from videobox_storage.local_project_store import LocalProjectStore

    clip = tmp_path / "walk.mp4"
    _make_clip(clip, seconds=30)
    store = LocalProjectStore(tmp_path / "projects")
    pipeline = LocalPipelineRunner(store=store)
    project = store.bootstrap_project("no scene windows")
    pipeline.register_broll_asset(project_id=project.project_id, source_path=clip, title="산책", tags=[])

    plan = store._draft_readiness_plan(
        project_id=project.project_id,
        brief={"script_text": "산책 장면을 보여 줍니다."},
        narration={},
    )

    assert plan["broll_candidates"][0]["target_range"] == {"start_sec": 0.0, "end_sec": 5.0}
