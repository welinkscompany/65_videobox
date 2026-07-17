from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave


TTS_DURATION_TOLERANCE_SEC = 0.5


@dataclass(frozen=True, slots=True)
class TtsAcceptance:
    technical_status: str
    operator_review_status: str
    target_duration_sec: float
    actual_duration_sec: float | None
    failure_code: str | None = None


def assess_tts_audio(*, path: Path, target_duration_sec: float) -> TtsAcceptance:
    if not path.exists() or path.stat().st_size == 0:
        return _rejected(target_duration_sec=target_duration_sec, failure_code="missing_audio")

    try:
        with wave.open(str(path), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            samples = wav_file.readframes(frame_count)
    except wave.Error:
        return _rejected(target_duration_sec=target_duration_sec, failure_code="unprobeable_audio")

    actual_duration_sec = frame_count / sample_rate if sample_rate else 0.0
    if not any(samples):
        return _rejected(
            target_duration_sec=target_duration_sec,
            actual_duration_sec=actual_duration_sec,
            failure_code="silent_audio",
        )
    if abs(actual_duration_sec - target_duration_sec) > TTS_DURATION_TOLERANCE_SEC:
        return _rejected(
            target_duration_sec=target_duration_sec,
            actual_duration_sec=actual_duration_sec,
            failure_code="duration_mismatch",
        )
    return TtsAcceptance(
        technical_status="accepted",
        operator_review_status="pending",
        target_duration_sec=target_duration_sec,
        actual_duration_sec=actual_duration_sec,
    )


def _rejected(
    *,
    target_duration_sec: float,
    failure_code: str,
    actual_duration_sec: float | None = None,
) -> TtsAcceptance:
    return TtsAcceptance(
        technical_status="rejected",
        operator_review_status="pending",
        target_duration_sec=target_duration_sec,
        actual_duration_sec=actual_duration_sec,
        failure_code=failure_code,
    )
