from __future__ import annotations

import wave
from pathlib import Path

from videobox_core_engine.tts_acceptance import assess_tts_audio
from videobox_storage.local_project_store import LocalProjectStore


def _write_mono_wav(path: Path, *, samples: list[int], sample_rate: int = 1000) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


def test_tts_acceptance_rejects_silent_wav(tmp_path: Path) -> None:
    wav_path = tmp_path / "silent.wav"
    _write_mono_wav(wav_path, samples=[0] * 3000)

    result = assess_tts_audio(path=wav_path, target_duration_sec=3.0)

    assert result.technical_status == "rejected"
    assert result.failure_code == "silent_audio"
    assert result.operator_review_status == "pending"


def test_tts_acceptance_accepts_audible_wav_inside_duration_tolerance(tmp_path: Path) -> None:
    wav_path = tmp_path / "audible.wav"
    _write_mono_wav(wav_path, samples=[1000, -1000] * 1500)

    result = assess_tts_audio(path=wav_path, target_duration_sec=3.2)

    assert result.technical_status == "accepted"
    assert result.failure_code is None
    assert result.operator_review_status == "pending"
    assert result.actual_duration_sec == 3.0


def test_tts_candidate_store_round_trips_pending_operator_review(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="TTS Acceptance")
    acceptance = assess_tts_audio(
        path=_write_accepted_wav(tmp_path / "accepted.wav"),
        target_duration_sec=3.0,
    )

    store.save_tts_candidate(
        project_id=project.project_id,
        segment_id="seg_001",
        asset_id="asset_001",
        source_text="안녕하세요.",
        acceptance=acceptance,
    )

    candidate = store.list_tts_candidates(project_id=project.project_id, segment_id="seg_001")[0]
    assert candidate["technical_status"] == "accepted"
    assert candidate["operator_review_status"] == "pending"
    assert candidate["target_duration_sec"] == 3.0


def _write_accepted_wav(path: Path) -> Path:
    _write_mono_wav(path, samples=[1000, -1000] * 1500)
    return path
