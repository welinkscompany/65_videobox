"""Measure what a music or effect file sounds like, locally.

The starter pack's 130 assets carry no describable metadata -- tags are the
literal word `music` or `sfx`, and names are slugs like `music-005`. With
nothing to tell one track from another, the music recommender could only ever
return a mood phrase and no track at all.

Rather than hand-labelling 130 files or asking an outside service, the
properties are measured from the audio with ffmpeg and numpy, both already in
the image. Three axes carry most of the useful judgement for a video bed:

  loudness   -- a quiet bed under narration vs something that carries a scene
  brightness -- dark and warm vs bright and sharp (spectral centroid)
  pace       -- how often the energy restarts, a robust stand-in for tempo
                that does not need beat tracking

Deliberately not measured: key, genre, instrument. Those need a trained model,
and guessing them from a filename would put invented facts on the owner's
screen.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Music beds are homogeneous; the opening minute characterises the whole
# track. Bounding the read keeps a 130-file pass off the owner's CPU budget.
_MAX_ANALYSIS_SECONDS = 60
# Enough bandwidth for brightness to mean something (Nyquist ~11 kHz) at a
# quarter of CD memory.
_SAMPLE_RATE = 22_050
_FRAME = 1024


@dataclass(slots=True, frozen=True)
class AudioDescriptor:
    duration_seconds: float
    #: Root-mean-square amplitude, 0.0-1.0.
    loudness_rms: float
    #: Spectral centroid in Hz -- where the energy sits, i.e. how bright.
    brightness_hz: float
    #: Energy restarts per second. A held note is near zero; a busy rhythm is
    #: several.
    onset_rate_per_second: float


def _decode_to_mono_pcm(path: Path) -> np.ndarray:
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-i", str(path),
            "-t", str(_MAX_ANALYSIS_SECONDS),
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", "1", "-ar", str(_SAMPLE_RATE),
            "-",
        ],
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0 or not result.stdout:
        raise ValueError(f"audio_unreadable: {path.name}")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _probe_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        # A stream without a declared duration still has samples; fall back to
        # what was actually decoded rather than failing the whole descriptor.
        return 0.0


def describe_audio_file(path: Path) -> AudioDescriptor:
    """Measure one file. Raises ValueError('audio_unreadable: ...') rather
    than returning zeros, so a broken file cannot masquerade as a silent one."""
    samples = _decode_to_mono_pcm(path)
    if samples.size == 0:
        raise ValueError(f"audio_unreadable: {path.name}")

    # Sound effects are routinely shorter than one frame -- the real pack has a
    # 43 ms pop. Pad it out so loudness and brightness still mean something;
    # rhythm is left at zero below rather than invented from a single frame.
    padded = samples
    if padded.size < _FRAME:
        padded = np.pad(padded, (0, _FRAME - padded.size))

    frame_count = padded.size // _FRAME
    frames = padded[: frame_count * _FRAME].reshape(frame_count, _FRAME)

    loudness_rms = float(np.sqrt(np.mean(np.square(samples))))

    window = np.hanning(_FRAME).astype(np.float32)
    spectra = np.abs(np.fft.rfft(frames * window, axis=1))
    frequencies = np.fft.rfftfreq(_FRAME, d=1.0 / _SAMPLE_RATE)
    magnitude_per_frame = spectra.sum(axis=1)
    # Silent frames would divide by zero and drag the mean toward 0 Hz, which
    # reads as "very dark" rather than "nothing there".
    voiced = magnitude_per_frame > 1e-6
    if voiced.any():
        centroids = (spectra[voiced] @ frequencies) / magnitude_per_frame[voiced]
        brightness_hz = float(np.mean(centroids))
    else:
        brightness_hz = 0.0

    # Spectral flux: how much the spectrum grows frame to frame. Counting the
    # peaks of that curve approximates "how often something new starts"
    # without needing a beat tracker.
    flux = np.maximum(np.diff(magnitude_per_frame), 0.0)
    analysed_seconds = samples.size / _SAMPLE_RATE
    if flux.size and analysed_seconds > 0 and samples.size >= _FRAME:
        threshold = float(np.mean(flux) + np.std(flux))
        above = flux > threshold
        # Count rising edges only, so one long swell is one onset.
        onsets = int(np.count_nonzero(above[1:] & ~above[:-1])) + int(above[0])
        onset_rate = onsets / analysed_seconds
    else:
        onset_rate = 0.0

    duration = _probe_duration_seconds(path) or analysed_seconds
    return AudioDescriptor(
        duration_seconds=round(duration, 3),
        loudness_rms=round(loudness_rms, 6),
        brightness_hz=round(brightness_hz, 1),
        onset_rate_per_second=round(onset_rate, 3),
    )


# Thresholds are read off the starter pack's own spread rather than an
# absolute standard: the point is to separate these 130 files from each other,
# not to agree with a mastering engineer.
def describe_in_creator_language(descriptor: AudioDescriptor) -> dict[str, str]:
    """Turn the measurements into the words a suggestion can actually say."""
    if descriptor.loudness_rms < 0.05:
        strength = "조용함"
    elif descriptor.loudness_rms < 0.18:
        strength = "보통"
    else:
        strength = "강함"

    if descriptor.brightness_hz < 1200:
        brightness = "어두움"
    elif descriptor.brightness_hz < 3000:
        brightness = "중간"
    else:
        brightness = "밝음"

    if descriptor.onset_rate_per_second < 1.0:
        pace = "느림"
    elif descriptor.onset_rate_per_second < 2.5:
        pace = "보통"
    else:
        pace = "빠름"

    return {"세기": strength, "밝기": brightness, "빠르기": pace}
