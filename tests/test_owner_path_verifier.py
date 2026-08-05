"""verify_owner_path.py exists to answer one question honestly: with the
providers Task 1 turned on, does ingest -> STT -> segments -> recommend ->
timeline -> preview -> captions -> export actually work end to end, or does it
only look like it works because a stub sits somewhere in the chain?

The two contracts under test are the ones the plan calls out explicitly:
1. no stub provider is ever accepted as evidence a stage passed.
2. a failing stage does not stop the run; every remaining stage is still
   attempted and recorded, so one break does not hide the rest.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.verify_owner_path import STUB_PROVIDER_NAMES, run_owner_path
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment


class _FakeRealSTTProvider:
    """Stands in for a real transcriber without downloading model weights.

    Its name is deliberately not in STUB_PROVIDER_NAMES, and it actually reads
    the audio path it is given rather than ignoring it, unlike the mocks.
    """

    provider_name = "test_fake_real_stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        assert request.source_path.exists()
        return STTResult(
            text="합격한 스타트업 대표님의 실제 목소리입니다.",
            segments=[STTSegment(start_sec=0.0, end_sec=2.0, text="합격한 스타트업 대표님의 실제 목소리입니다.", confidence=0.9)],
            provider_name=self.provider_name,
        )


def _write_narration(path: Path, duration: int = 2) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", str(path)],
        check=True, capture_output=True,
    )
    return path


def _write_broll(path: Path, duration: int = 2) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=15", "-an", str(path)],
        check=True, capture_output=True,
    )
    return path


@pytest.fixture()
def work_root(tmp_path: Path) -> Path:
    return tmp_path / "verify-owner-path"


def test_rejects_a_stub_provider_instead_of_reporting_a_false_pass(work_root: Path, tmp_path: Path) -> None:
    """The exact failure mode this script exists to prevent: a mock silently
    standing in for STT and the run being reported green anyway."""
    from videobox_provider_interfaces.stt import MockSTTProvider

    narration = _write_narration(tmp_path / "narration.wav")
    broll = _write_broll(tmp_path / "broll.mp4")

    report = run_owner_path(
        narration_path=narration,
        script_text="합격한 스타트업 대표님의 실제 목소리입니다.",
        broll_paths=[broll],
        work_root=work_root,
        stt_provider=MockSTTProvider(),
    )

    stt_stage = next(stage for stage in report["stages"] if stage["name"] == "transcription")
    assert stt_stage["status"] == "failed"
    assert "mock_stt" in stt_stage["detail"]


def test_accepts_a_provider_that_is_not_on_the_stub_list(work_root: Path, tmp_path: Path) -> None:
    narration = _write_narration(tmp_path / "narration.wav")
    broll = _write_broll(tmp_path / "broll.mp4")

    report = run_owner_path(
        narration_path=narration,
        script_text="합격한 스타트업 대표님의 실제 목소리입니다.",
        broll_paths=[broll],
        work_root=work_root,
        stt_provider=_FakeRealSTTProvider(),
    )

    stt_stage = next(stage for stage in report["stages"] if stage["name"] == "transcription")
    assert stt_stage["status"] == "passed"
    assert stt_stage["evidence"]["provider_name"] == "test_fake_real_stt"
    assert "합격" in stt_stage["evidence"]["transcript_text"]


def test_a_failing_stage_does_not_stop_the_remaining_stages(work_root: Path, tmp_path: Path) -> None:
    """narration.wav does not exist, so transcription fails at the first
    step. Every later stage must still appear in the report -- attempted and
    recorded as failed or skipped, not silently dropped."""
    missing_narration = tmp_path / "does-not-exist.wav"
    broll = _write_broll(tmp_path / "broll.mp4")

    report = run_owner_path(
        narration_path=missing_narration,
        script_text="아무 대본",
        broll_paths=[broll],
        work_root=work_root,
        stt_provider=_FakeRealSTTProvider(),
    )

    stage_names = [stage["name"] for stage in report["stages"]]
    assert stage_names == [
        "ingest",
        "transcription",
        "segment_analysis",
        "broll_recommendation",
        "timeline_build",
        "preview_render",
        "subtitle_render",
        "final_render",
        "capcut_draft_export",
    ]
    assert report["stages"][0]["status"] == "failed"
    for stage in report["stages"][1:]:
        assert stage["status"] in {"failed", "skipped"}


def test_known_stub_names_include_both_transcribers_this_project_has_shipped() -> None:
    # F-0's finding: two independent stub STT paths existed (the container's
    # mock default and the smoke-test's deterministic stub). Both must be
    # recognized so re-registering either under a plausible name still trips
    # the guard.
    assert "mock_stt" in STUB_PROVIDER_NAMES
    assert "deterministic_korean_smoke_stt" in STUB_PROVIDER_NAMES
