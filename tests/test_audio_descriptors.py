"""Measure what a music or effect file actually sounds like.

The starter pack ships 130 assets whose only metadata is the word `music` or
`sfx` and a slug filename. Nothing in it can answer "does this suit a calm
scene?", so the music recommender never had anything to choose between --
it returns a mood phrase and `selected_asset_id: None`, confirmed against the
running container.

These descriptors come from the audio itself with ffmpeg and numpy, both
already in the image. Nothing leaves the machine and no one has to label 130
files by hand.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.audio_descriptors import (
    AudioDescriptor,
    describe_audio_file,
    describe_in_creator_language,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _tone(path: Path, *, frequency: int, volume: float, duration: int = 3) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
            "-filter:a", f"volume={volume}",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_a_loud_bright_tone_measures_louder_and_brighter_than_a_quiet_low_one(tmp_path: Path) -> None:
    quiet_low = describe_audio_file(_tone(tmp_path / "quiet_low.wav", frequency=120, volume=0.05))
    loud_high = describe_audio_file(_tone(tmp_path / "loud_high.wav", frequency=4000, volume=0.9))

    assert loud_high.loudness_rms > quiet_low.loudness_rms
    assert loud_high.brightness_hz > quiet_low.brightness_hz
    assert quiet_low.duration_seconds == pytest.approx(3.0, abs=0.3)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_a_busy_file_measures_a_faster_pace_than_a_held_note(tmp_path: Path) -> None:
    held = _tone(tmp_path / "held.wav", frequency=440, volume=0.5, duration=4)
    busy = tmp_path / "busy.wav"
    # A tone switched on and off repeatedly: many onsets in the same seconds.
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-filter:a", "tremolo=f=8:d=0.9",
            str(busy),
        ],
        check=True,
        timeout=60,
    )

    assert describe_audio_file(busy).onset_rate_per_second > describe_audio_file(held).onset_rate_per_second


def test_measurements_become_words_the_owner_can_read() -> None:
    # The owner picks music, not decibels. The numbers stay for matching; the
    # words are what a screen or a suggestion can say.
    calm = AudioDescriptor(
        duration_seconds=90.0, loudness_rms=0.02, brightness_hz=700.0, onset_rate_per_second=0.4
    )
    driving = AudioDescriptor(
        duration_seconds=90.0, loudness_rms=0.30, brightness_hz=4200.0, onset_rate_per_second=3.5
    )

    assert describe_in_creator_language(calm) == {"세기": "조용함", "밝기": "어두움", "빠르기": "느림"}
    assert describe_in_creator_language(driving) == {"세기": "강함", "밝기": "밝음", "빠르기": "빠름"}


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_an_unreadable_file_says_so_instead_of_crashing_the_caller(tmp_path: Path) -> None:
    broken = tmp_path / "not-audio.wav"
    broken.write_bytes(b"this is not audio")

    with pytest.raises(ValueError, match="audio_unreadable"):
        describe_audio_file(broken)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not installed on this machine")
def test_a_very_short_effect_is_measured_not_rejected(tmp_path: Path) -> None:
    """Running this over the real pack rejected `sfx-pop10.wav`, which turned
    out to be a perfectly good 43 ms pop -- shorter than one analysis frame.
    Sound effects are routinely that short, so refusing them would leave a
    chunk of the library undescribed."""
    pop = tmp_path / "pop.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=900:duration=0.04",
            str(pop),
        ],
        check=True,
        timeout=60,
    )

    descriptor = describe_audio_file(pop)

    assert descriptor.duration_seconds == pytest.approx(0.04, abs=0.02)
    assert descriptor.loudness_rms > 0.0
    assert descriptor.brightness_hz > 0.0
    # Too little signal to claim a rhythm, and saying "fast" would be invented.
    assert descriptor.onset_rate_per_second == 0.0
