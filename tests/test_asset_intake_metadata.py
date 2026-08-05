"""B-roll intake discarded everything ffprobe already knows.

Registration stored only title and tags, so the picker had no length, no
dimensions, and no audio flag to show -- which is why asset cards read
"길이 정보 없음" and "오디오 정보 확인 중".  Orientation was never derived at all,
so vertical footage could not be told apart from landscape.
"""

import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


def _write_video(path: Path, *, size: str, with_audio: bool, duration: int = 2) -> Path:
    command = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=15"]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac", "-shortest"]
    else:
        command += ["-an"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True, capture_output=True)
    return path


@pytest.fixture()
def runner(tmp_path: Path) -> LocalPipelineRunner:
    store = LocalProjectStore(tmp_path / "projects")
    return LocalPipelineRunner(store=store)


def _stored_metadata(runner: LocalPipelineRunner, project_id: str, asset_id: str) -> dict:
    """Registration returns an identity payload; metadata lives in the store,
    which is what the asset list endpoint reads."""
    return runner.store.get_asset(project_id=project_id, asset_id=asset_id)["metadata"]


def _register(runner: LocalPipelineRunner, tmp_path: Path, **video) -> dict:
    project = runner.store.bootstrap_project(name="Intake")
    source = _write_video(tmp_path / f"{video['size']}.mp4", **video)
    asset = runner.register_broll_asset(project_id=project.project_id, source_path=source)
    return _stored_metadata(runner, project.project_id, asset["asset_id"])


def test_landscape_intake_records_size_length_and_audio(runner, tmp_path: Path) -> None:
    metadata = _register(runner, tmp_path, size="320x180", with_audio=True)

    assert metadata["width"] == 320
    assert metadata["height"] == 180
    assert metadata["orientation"] == "가로"
    assert metadata["has_audio"] is True
    assert metadata["duration_sec"] == pytest.approx(2.0, abs=0.3)


def test_portrait_intake_is_marked_vertical(runner, tmp_path: Path) -> None:
    """Shortform work needs vertical footage to be distinguishable at intake."""
    metadata = _register(runner, tmp_path, size="180x320", with_audio=False)

    assert metadata["orientation"] == "세로"
    assert metadata["has_audio"] is False


def test_square_intake_is_marked_square(runner, tmp_path: Path) -> None:
    metadata = _register(runner, tmp_path, size="240x240", with_audio=False)

    assert metadata["orientation"] == "정사각"


def test_intake_keeps_tags_for_the_owner(runner, tmp_path: Path) -> None:
    """Derived facts must not be written into the owner's own tag list."""
    project = runner.store.bootstrap_project(name="Tags")
    source = _write_video(tmp_path / "tagged.mp4", size="320x180", with_audio=False)

    asset = runner.register_broll_asset(
        project_id=project.project_id, source_path=source, tags=["카페"]
    )

    metadata = _stored_metadata(runner, project.project_id, asset["asset_id"])

    assert metadata["tags"] == ["카페"]
    for derived in ("orientation", "duration_sec", "width", "height", "has_audio"):
        assert derived not in metadata["tags"]


def test_unreadable_media_still_registers(runner, tmp_path: Path) -> None:
    """A probe failure must not block intake, matching the thumbnail fallback."""
    project = runner.store.bootstrap_project(name="Broken")
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")

    asset = runner.register_broll_asset(project_id=project.project_id, source_path=broken)
    metadata = _stored_metadata(runner, project.project_id, asset["asset_id"])

    assert asset["asset_id"]
    assert metadata.get("orientation") is None
