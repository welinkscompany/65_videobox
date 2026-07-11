from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-production-readiness-smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("production_readiness_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_harness_exposes_a_600_second_korean_stt_contract(tmp_path: Path) -> None:
    smoke = _load_smoke_module()

    result = smoke.DeterministicKoreanSTTProvider().transcribe(
        smoke.STTRequest(source_path=tmp_path / "narration.wav", language="ko")
    )

    assert result.provider_name == "deterministic_korean_smoke_stt"
    assert result.segments[0].start_sec == 0.0
    assert result.segments[-1].end_sec == pytest.approx(600.0)
    assert all(segment.text.endswith("니다.") for segment in result.segments)


def test_smoke_harness_rejects_narration_that_is_not_ten_minutes() -> None:
    smoke = _load_smoke_module()

    with pytest.raises(ValueError, match="600"):
        smoke.require_duration(duration_sec=599.4, expected_sec=600.0, tolerance_sec=0.1)

    smoke.require_duration(duration_sec=600.0, expected_sec=600.0, tolerance_sec=0.1)


def test_smoke_source_script_matches_deterministic_stt_before_the_caption_edit() -> None:
    smoke = _load_smoke_module()

    source_segments = smoke.DeterministicKoreanSTTProvider().transcribe(
        smoke.STTRequest(source_path=Path("narration.wav"), language="ko")
    ).segments

    assert smoke.SOURCE_CAPTIONS == [segment.text for segment in source_segments]


def test_smoke_source_segments_do_not_trigger_heuristic_retake_review() -> None:
    smoke = _load_smoke_module()
    from videobox_core_engine.script_scene_planner import HeuristicSegmentAnalyzer

    segments = smoke.DeterministicKoreanSTTProvider().transcribe(
        smoke.STTRequest(source_path=Path("narration.wav"), language="ko")
    ).segments
    analyzed = HeuristicSegmentAnalyzer().analyze(
        project_id="smoke",
        transcript_segments=[
            {"start_sec": segment.start_sec, "end_sec": segment.end_sec, "text": segment.text, "confidence": segment.confidence}
            for segment in segments
        ],
        script_text="\n".join(smoke.SOURCE_CAPTIONS),
    )

    assert not any(segment["review_required"] for segment in analyzed)


def test_korean_sample_generator_forbids_repetition_or_silence_padding() -> None:
    generator = REPO_ROOT / "scripts" / "New-ProductionReadinessKoreanSample.ps1"

    source = generator.read_text(encoding="utf-8")

    assert "Microsoft Heami Desktop" in source
    assert "Add-Type -AssemblyName System.Speech" in source
    assert "Get-FileHash" not in source
    assert "Security.Cryptography.SHA256" in source
    assert source.count("Remove-Item -LiteralPath $rawPath") >= 2
    assert "raw narration" in source.lower()
    assert "600" in source
    assert "silence" in source.lower()
    assert "repeat" in source.lower()


def test_smoke_harness_observes_broll_loop_and_muxed_subtitle_instead_of_marking_them_true() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'checks["short_broll_loops"] = True' not in source
    assert "_extract_subtitle_stream" in source
    assert 'checks["revised_caption_in_final_mp4"]' in source


def test_smoke_harness_requires_listening_approved_personal_voice_tts_for_final_and_capcut_outputs() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'checks["tts_candidate_pending_operator_review"]' in source
    assert 'checks["tts_candidate_listening_approved"]' in source
    assert 'checks["approved_tts_in_final_and_capcut"]' in source
    assert '"tts_replacement"' in source
    assert '"target_duration_sec"' in source
    assert 'assets/voice-sample/upload' in source
    assert 'checks["voice_sample_uploaded"]' in source


def test_smoke_harness_decodes_ffmpeg_subtitles_as_utf8_on_windows() -> None:
    smoke = _load_smoke_module()

    assert smoke._decode_ffmpeg_utf8("수정된 최종 자막".encode("utf-8")) == "수정된 최종 자막"


def test_smoke_harness_recreates_only_its_projects_subdirectory_for_a_repeat_run(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    (projects_root / "stale.sqlite").write_text("old run", encoding="utf-8")

    recreated = smoke._prepare_projects_root(tmp_path)

    assert recreated == projects_root
    assert recreated.is_dir()
    assert list(recreated.iterdir()) == []
