"""Owner decision (2026-08-05, Task 21): place everything automatically and
review the actual result afterward, rather than gating approval on a
confidence heuristic before anything ever renders.

S-4 found that segment_review_required always blocked approve_timeline_review
once real STT confidence scores were in play. auto_approve_segment_review is
the runner-level switch for that gate. It defaults to False so every existing
test's blocking-behavior assertions keep meaning what they said; the owner's
real container turns it on explicitly via VIDEOBOX_AUTO_APPROVE_SEGMENT_REVIEW.

Turning it on does not delete review_required or review_reasons -- those stay
on the segment and in the timeline's review_flags for the owner to look at
later. It only stops that flag from blocking approval.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.settings import resolve_auto_approve_segment_review
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore


class _LowConfidenceSTTProvider:
    """Every segment comes back exactly at the boundary that used to block
    approval, so the test exercises the real HeuristicSegmentAnalyzer path
    rather than hand-building a blocked timeline."""

    provider_name = "test_low_confidence_stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        del request
        return STTResult(
            text="확신이 낮은 문장입니다.",
            segments=[STTSegment(start_sec=0.0, end_sec=2.0, text="확신이 낮은 문장입니다.", confidence=0.5)],
            provider_name=self.provider_name,
        )


def _write_narration(path: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(path)], check=True, capture_output=True)
    return path


def _write_broll(path: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15", "-an", str(path)], check=True, capture_output=True)
    return path


def _build_and_approve(tmp_path: Path, *, auto_approve_segment_review: bool) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    runner = LocalPipelineRunner(
        store=store,
        stt_provider=_LowConfidenceSTTProvider(),
        auto_approve_segment_review=auto_approve_segment_review,
    )
    project = store.bootstrap_project(name="policy-test")
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=_write_narration(tmp_path / "n.wav"))
    script_path = tmp_path / "script.txt"
    script_path.write_text("확신이 낮은 문장입니다.", encoding="utf-8")
    script = runner.register_script_asset(project_id=project.project_id, source_path=script_path)
    runner.register_broll_asset(project_id=project.project_id, source_path=_write_broll(tmp_path / "b.mp4"))

    transcription_job = runner.start_transcription(project_id=project.project_id, narration_asset_id=narration["asset_id"])
    analysis_job = runner.start_segment_analysis(project_id=project.project_id, transcription_job_id=transcription_job["job_id"], script_asset_id=script["asset_id"])
    recommendation_job = runner.start_broll_recommendation(project_id=project.project_id, segment_analysis_job_id=analysis_job["job_id"])
    timeline_job = runner.build_timeline(project_id=project.project_id, segment_analysis_job_id=analysis_job["job_id"], recommendation_job_ids=[recommendation_job["job_id"]])

    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    # Approval succeeding must not have erased the evidence -- the owner
    # reviews the actual result later, which requires the flag to still exist.
    timeline = runner.get_timeline_result(project_id=project.project_id, job_id=timeline_job["job_id"])["timeline"]
    flag_codes = [flag["code"] for flag in timeline.get("review_flags", [])]
    assert "segment_review_required" in flag_codes


def test_default_still_blocks_low_confidence_segments(tmp_path: Path) -> None:
    """Regression guard: existing behavior is unchanged unless the owner opts in."""
    with pytest.raises(ValueError, match="review blockers"):
        _build_and_approve(tmp_path, auto_approve_segment_review=False)


def test_auto_approve_places_low_confidence_segments_without_blocking(tmp_path: Path) -> None:
    _build_and_approve(tmp_path, auto_approve_segment_review=True)  # must not raise


def test_resolves_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIDEOBOX_AUTO_APPROVE_SEGMENT_REVIEW", raising=False)
    assert resolve_auto_approve_segment_review() is False

    monkeypatch.setenv("VIDEOBOX_AUTO_APPROVE_SEGMENT_REVIEW", "1")
    assert resolve_auto_approve_segment_review() is True
