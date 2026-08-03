from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


class _SequenceResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _SequenceClient:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self._payloads = iter(payloads)
        self.paths: list[str] = []

    def get(self, path: str) -> _SequenceResponse:
        self.paths.append(path)
        return _SequenceResponse(next(self._payloads))


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
    assert '"crop=2:2:8:(ih-2)/2"' in source
    assert "_extract_subtitle_stream" in source
    assert 'checks["revised_caption_in_final_mp4"]' in source


def test_smoke_harness_uses_the_supported_local_only_runtime_factory() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "local_only_runtime_service_factory=lambda _: DeterministicOfflineRuntime()" in source
    assert "local_first_runtime_service_factory" not in source


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


def test_long_form_fixture_profiles_define_real_media_controls_and_desktop_scope() -> None:
    smoke = _load_smoke_module()

    assert tuple(smoke.LONG_FORM_PROFILE_NAMES) == ("loop", "crop_pad_overlay", "audio_ducking")
    assert smoke.get_long_form_fixture("loop")["broll_controls"]["loop"] is True
    crop_pad = smoke.get_long_form_fixture("crop_pad_overlay")
    assert crop_pad["broll_controls"] == {"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.2}
    assert crop_pad["include_image_overlay"] is True
    audio = smoke.get_long_form_fixture("audio_ducking")
    assert audio["audio_controls"] == {"gain_db": -6.0, "fade_in_sec": 0.5, "fade_out_sec": 0.5, "ducking": True}
    assert audio["desktop_capcut_opened"] is False


def test_smoke_exact_preview_poll_requires_ready_state(monkeypatch: pytest.MonkeyPatch) -> None:
    smoke = _load_smoke_module()
    monkeypatch.setattr(smoke.time, "sleep", lambda _: None)
    client = _SequenceClient([
        {"status": "running"},
        {"status": "ready", "content_url": "/content"},
    ])

    result = smoke._poll_exact_preview(
        client,
        project_id="project",
        generation_id="generation",
        timeout_sec=1,
    )

    assert result["status"] == "ready"
    assert result["content_url"] == "/content"
    assert client.paths == [
        "/api/projects/project/exact-previews/generation",
        "/api/projects/project/exact-previews/generation",
    ]


def test_smoke_exact_preview_poll_normalizes_public_succeeded_state_to_ready() -> None:
    smoke = _load_smoke_module()
    client = _SequenceClient([{"status": "succeeded", "content_url": "/content"}])

    result = smoke._poll_exact_preview(
        client,
        project_id="project",
        generation_id="generation",
        timeout_sec=1,
    )

    assert result == {"status": "ready", "content_url": "/content"}


@pytest.mark.parametrize("status", ["failed", "stale", "obsolete", "unavailable", "unexpected"])
def test_smoke_exact_preview_poll_rejects_terminal_non_ready_states(status: str) -> None:
    smoke = _load_smoke_module()
    client = _SequenceClient([{"status": status, "error_message": "x" * 4_096}])

    with pytest.raises(RuntimeError, match=rf"Exact preview .* {status}") as raised:
        smoke._poll_exact_preview(
            client,
            project_id="project",
            generation_id="generation",
            timeout_sec=1,
        )

    assert len(str(raised.value)) < 256


def test_smoke_exact_preview_poll_rejects_timeout_without_unbounded_payload() -> None:
    smoke = _load_smoke_module()

    with pytest.raises(TimeoutError, match="generation") as raised:
        smoke._poll_exact_preview(
            _SequenceClient([]),
            project_id="project",
            generation_id="generation",
            timeout_sec=0,
        )

    assert len(str(raised.value)) < 256


def test_smoke_exact_preview_poll_bounds_identifier_and_http_error_details() -> None:
    smoke = _load_smoke_module()
    oversized_generation_id = "generation-" + ("x" * 4_096)

    with pytest.raises(TimeoutError) as timeout:
        smoke._poll_exact_preview(
            _SequenceClient([]),
            project_id="project",
            generation_id=oversized_generation_id,
            timeout_sec=0,
        )

    class _HttpErrorClient:
        @staticmethod
        def get(path: str) -> SimpleNamespace:
            return SimpleNamespace(status_code=503, text="x" * 4_096)

    with pytest.raises(RuntimeError, match="HTTP 503") as http_error:
        smoke._poll_exact_preview(
            _HttpErrorClient(),
            project_id="project",
            generation_id=oversized_generation_id,
            timeout_sec=1,
        )

    assert len(str(timeout.value)) < 256
    assert len(str(http_error.value)) < 256


def test_smoke_writes_timeline_and_session_snapshots_atomically_with_stable_utf8_json(
    tmp_path: Path,
) -> None:
    smoke = _load_smoke_module()
    timeline = {"z_key": 2, "a_key": "검토 타임라인"}
    session = {"session_id": "session", "segments": [{"caption_text": "수정 자막"}]}

    paths = smoke._write_review_snapshots(
        tmp_path,
        timeline=timeline,
        session=session,
    )

    assert paths == {
        "timeline": tmp_path / "review" / "timeline.json",
        "editing_session": tmp_path / "review" / "editing-session.json",
    }
    assert json.loads(paths["timeline"].read_text(encoding="utf-8")) == timeline
    assert json.loads(paths["editing_session"].read_text(encoding="utf-8")) == session
    assert paths["timeline"].read_text(encoding="utf-8").index('"a_key"') < paths["timeline"].read_text(encoding="utf-8").index('"z_key"')
    assert "검토 타임라인" in paths["timeline"].read_text(encoding="utf-8")
    assert str(tmp_path.resolve()) not in paths["timeline"].read_text(encoding="utf-8")
    assert list((tmp_path / "review").glob("*.tmp")) == []


def test_smoke_probe_media_summary_returns_only_bounded_review_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke = _load_smoke_module()
    probe_payload = {
        "format": {"duration": "5.125000", "format_name": "mov,mp4", "tags": {"secret": "ignored"}},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "extradata": "ignored"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ],
    }
    monkeypatch.setattr(
        smoke,
        "_run",
        lambda command, timeout: SimpleNamespace(stdout=json.dumps(probe_payload)),
    )

    summary = smoke._probe_media_summary(tmp_path / "preview.mp4", ffprobe_binary="ffprobe")

    assert summary == {
        "duration_sec": 5.125,
        "format": "mov,mp4",
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "audio_codec": "aac",
    }


def test_smoke_run_wires_exact_preview_before_regeneration_and_returns_review_evidence() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    exact_preview_start = source.index('/exact-preview"')
    partial_regeneration_start = source.index('/partial-regeneration"')

    assert exact_preview_start < partial_regeneration_start
    assert '"start_sec": 0.0' in source
    assert '"end_sec": 5.0' in source
    assert 'headers={"Range": "bytes=0-0"}' in source
    assert "store.get_exact_preview(" in source
    assert "_write_review_snapshots(" in source
    assert '"exact_preview"' in source
    assert '"timeline_snapshot"' in source
    assert '"editing_session_snapshot"' in source
    assert '"ffprobe_summary"' in source
