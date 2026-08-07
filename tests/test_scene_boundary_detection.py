"""Task 27: detect real scene boundaries instead of the whole-clip placeholder.

`media_probe._probe` used to set `boundaries = (0.0, duration)`, so every clip
looked like a single scene and Task 23's window chooser had nothing to choose
between. These tests drive real detection with clips built by ffmpeg.

Detection runs only on the analysis path (`probe`). Asset registration uses
`probe_metadata`, which must stay a single cheap ffprobe call.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.media_probe import FFmpegMediaProbe

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg/ffprobe to build and probe real clips",
)


def _solid_clip(path: Path, colour: str, seconds: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=320x240:d={seconds}",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True, timeout=60,
    )


def _clip_with_cuts(path: Path, tmp_path: Path) -> None:
    """Three hard cuts: black -> white -> black, 4s each."""
    parts = []
    for index, colour in enumerate(("black", "white", "black")):
        part = tmp_path / f"part{index}.mp4"
        _solid_clip(part, colour, 4)
        parts.append(part)
    listing = tmp_path / "parts.txt"
    listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(path)],
        capture_output=True, check=True, timeout=60,
    )


@requires_ffmpeg
def test_detects_the_cuts_in_a_clip_that_has_them(tmp_path: Path) -> None:
    clip = tmp_path / "cuts.mp4"
    _clip_with_cuts(clip, tmp_path)

    result = FFmpegMediaProbe().probe(clip)

    # Starts at 0, ends at the duration, and finds the two colour changes in
    # between rather than reporting one whole-clip scene.
    assert result.scene_boundaries[0] == 0.0
    assert result.scene_boundaries[-1] == pytest.approx(result.duration_sec, abs=0.5)
    interior = [value for value in result.scene_boundaries if 0.0 < value < result.duration_sec]
    assert len(interior) >= 2, result.scene_boundaries


@requires_ffmpeg
def test_reports_a_single_take_as_one_window(tmp_path: Path) -> None:
    """A continuous phone clip genuinely has no cuts -- it must not invent any."""
    clip = tmp_path / "single.mp4"
    _solid_clip(clip, "blue", 10)

    result = FFmpegMediaProbe().probe(clip)

    assert result.scene_boundaries == (0.0, pytest.approx(result.duration_sec, abs=0.5))


@requires_ffmpeg
def test_boundaries_are_sorted_and_unique(tmp_path: Path) -> None:
    clip = tmp_path / "cuts.mp4"
    _clip_with_cuts(clip, tmp_path)

    boundaries = FFmpegMediaProbe().probe(clip).scene_boundaries

    assert list(boundaries) == sorted(boundaries)
    assert len(set(boundaries)) == len(boundaries)


@requires_ffmpeg
def test_metadata_probe_stays_cheap_and_does_not_detect_scenes(tmp_path: Path) -> None:
    """Asset registration must not pay for a full decode of every upload."""
    clip = tmp_path / "cuts.mp4"
    _clip_with_cuts(clip, tmp_path)

    result = FFmpegMediaProbe().probe_metadata(clip)

    assert result.scene_boundaries == (0.0, pytest.approx(result.duration_sec, abs=0.5))
    assert result.frames == ()
