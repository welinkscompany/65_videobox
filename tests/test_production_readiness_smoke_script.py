from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
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
    def __init__(self, payload: dict[str, object], *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._payload


class _SequenceClient:
    def __init__(self, payloads: list[dict[str, object] | _SequenceResponse]) -> None:
        self._payloads = iter(payloads)
        self.paths: list[str] = []
        self.headers: list[dict[str, str] | None] = []

    def get(self, path: str, headers: dict[str, str] | None = None) -> _SequenceResponse:
        self.paths.append(path)
        self.headers.append(headers)
        payload = next(self._payloads)
        return payload if isinstance(payload, _SequenceResponse) else _SequenceResponse(payload)


def _exact_preview_payload(*, status: str) -> dict[str, object]:
    return {
        "status": status,
        "generation_id": "generation",
        "artifact_revision": 7,
        "timeline_start_sec": 0.0,
        "timeline_end_sec": 5.0,
        "content_url": "/api/projects/project/exact-previews/generation/content",
    }


def _poll_review_exact_preview(smoke, client, *, generation_id: str = "generation"):
    return smoke._poll_exact_preview(
        client,
        project_id="project",
        generation_id=generation_id,
        expected_revision=7,
        expected_start_sec=0.0,
        expected_end_sec=5.0,
        timeout_sec=1,
    )


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
        _exact_preview_payload(status="ready"),
        _SequenceResponse({}, status_code=206),
    ])

    result = _poll_review_exact_preview(smoke, client)

    assert result["status"] == "ready"
    assert result["range_status"] == 206
    assert result["content_url"] == "/api/projects/project/exact-previews/generation/content"
    assert client.paths == [
        "/api/projects/project/exact-previews/generation",
        "/api/projects/project/exact-previews/generation",
        "/api/projects/project/exact-previews/generation/content",
    ]
    assert client.headers == [None, None, {"Range": "bytes=0-0"}]


def test_smoke_exact_preview_poll_normalizes_public_succeeded_state_to_ready() -> None:
    smoke = _load_smoke_module()
    client = _SequenceClient([
        _exact_preview_payload(status="succeeded"),
        _SequenceResponse({}, status_code=206),
    ])

    result = _poll_review_exact_preview(smoke, client)

    assert result["status"] == "ready"
    assert result["generation_id"] == "generation"
    assert result["artifact_revision"] == 7
    assert result["range_status"] == 206


_MISSING = object()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_id", _MISSING),
        ("generation_id", "foreign-generation"),
        ("artifact_revision", _MISSING),
        ("artifact_revision", 8),
        ("timeline_start_sec", _MISSING),
        ("timeline_start_sec", 0.01),
        ("timeline_start_sec", float("nan")),
        ("timeline_end_sec", _MISSING),
        ("timeline_end_sec", 4.9),
        ("timeline_end_sec", float("inf")),
        ("content_url", _MISSING),
        ("content_url", "https://example.com/preview.mp4"),
        ("content_url", "C:/preview.mp4"),
        ("content_url", "/api/projects/project/exact-previews/foreign/content"),
        ("content_url", "/api/projects/foreign/exact-previews/generation/content"),
    ],
)
@pytest.mark.parametrize("status", ["succeeded", "ready"])
def test_smoke_exact_preview_poll_rejects_mismatched_success_identity(
    field: str,
    value: object,
    status: str,
) -> None:
    smoke = _load_smoke_module()
    payload = _exact_preview_payload(status=status)
    if value is _MISSING:
        payload.pop(field)
    else:
        payload[field] = value
    client = _SequenceClient([payload])

    with pytest.raises(RuntimeError, match="exact_preview_identity_mismatch") as raised:
        _poll_review_exact_preview(smoke, client)

    assert len(str(raised.value)) < 128
    assert client.paths == ["/api/projects/project/exact-previews/generation"]


def test_smoke_exact_preview_poll_accepts_only_bounded_range_equality() -> None:
    smoke = _load_smoke_module()
    payload = _exact_preview_payload(status="ready")
    payload["timeline_start_sec"] = 0.0000005
    payload["timeline_end_sec"] = 4.9999995
    client = _SequenceClient([payload, _SequenceResponse({}, status_code=206)])

    result = _poll_review_exact_preview(smoke, client)

    assert result["status"] == "ready"
    assert result["range_status"] == 206


def test_smoke_exact_preview_poll_rejects_non_206_canonical_range_with_bounded_error() -> None:
    smoke = _load_smoke_module()
    client = _SequenceClient([
        _exact_preview_payload(status="succeeded"),
        _SequenceResponse({}, status_code=200),
    ])

    with pytest.raises(RuntimeError, match="exact_preview_range_failed") as raised:
        _poll_review_exact_preview(smoke, client)

    assert len(str(raised.value)) < 128
    assert client.paths[-1] == "/api/projects/project/exact-previews/generation/content"
    assert client.headers[-1] == {"Range": "bytes=0-0"}


@pytest.mark.parametrize("status", ["failed", "stale", "obsolete", "unavailable", "unexpected"])
def test_smoke_exact_preview_poll_rejects_terminal_non_ready_states(status: str) -> None:
    smoke = _load_smoke_module()
    client = _SequenceClient([{"status": status, "error_message": "x" * 4_096}])

    with pytest.raises(RuntimeError, match=rf"Exact preview .* {status}") as raised:
        _poll_review_exact_preview(smoke, client)

    assert len(str(raised.value)) < 256


def test_smoke_exact_preview_poll_rejects_timeout_without_unbounded_payload() -> None:
    smoke = _load_smoke_module()

    with pytest.raises(TimeoutError, match="generation") as raised:
        smoke._poll_exact_preview(
            _SequenceClient([]),
            project_id="project",
            generation_id="generation",
            expected_revision=7,
            expected_start_sec=0.0,
            expected_end_sec=5.0,
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
            expected_revision=7,
            expected_start_sec=0.0,
            expected_end_sec=5.0,
            timeout_sec=0,
        )

    class _HttpErrorClient:
        @staticmethod
        def get(path: str, headers: dict[str, str] | None = None) -> SimpleNamespace:
            return SimpleNamespace(status_code=503, text="x" * 4_096)

    with pytest.raises(RuntimeError, match="HTTP 503") as http_error:
        smoke._poll_exact_preview(
            _HttpErrorClient(),
            project_id="project",
            generation_id=oversized_generation_id,
            expected_revision=7,
            expected_start_sec=0.0,
            expected_end_sec=5.0,
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


def test_smoke_probe_media_summary_bounds_subprocess_failure_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke = _load_smoke_module()
    oversized_path = Path("x" * 4_096)

    def fail_probe(command: list[str], *, timeout: int) -> SimpleNamespace:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            stderr="private ffprobe detail " * 1_024,
        )

    monkeypatch.setattr(smoke, "_run", fail_probe)

    with pytest.raises(RuntimeError, match="media_probe_failed") as raised:
        smoke._probe_media_summary(oversized_path, ffprobe_binary="ffprobe")

    message = str(raised.value)
    assert len(message) < 128
    assert str(oversized_path) not in message
    assert "private ffprobe detail" not in message


@pytest.mark.parametrize(
    "stdout",
    [
        "not-json",
        "[]",
        json.dumps({"format": {"duration": "not-duration", "format_name": "mp4"}, "streams": []}),
        json.dumps({"format": {"duration": "1", "format_name": "mp4"}, "streams": "not-a-list"}),
    ],
)
def test_smoke_probe_media_summary_rejects_malformed_output_with_bounded_domain_error(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
) -> None:
    smoke = _load_smoke_module()
    monkeypatch.setattr(
        smoke,
        "_run",
        lambda command, timeout: SimpleNamespace(stdout=stdout),
    )

    with pytest.raises(RuntimeError, match="media_probe_failed") as raised:
        smoke._probe_media_summary(Path("preview.mp4"), ffprobe_binary="ffprobe")

    assert len(str(raised.value)) < 128


def _playable_summary(duration_sec: object, *, audio_codec: object = "aac") -> dict[str, object]:
    return {
        "duration_sec": duration_sec,
        "format": "mov,mp4",
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "audio_codec": audio_codec,
    }


@pytest.mark.parametrize("duration_sec", [4.75, 5.0, 5.25])
def test_smoke_playable_media_gate_accepts_exact_preview_tolerance_edges(duration_sec: float) -> None:
    smoke = _load_smoke_module()

    smoke._require_playable_media_summary(
        _playable_summary(duration_sec),
        expected_duration_sec=5.0,
        tolerance_sec=0.25,
    )


@pytest.mark.parametrize(
    "summary",
    [
        _playable_summary(0.0),
        _playable_summary(5.251),
        _playable_summary("5.0"),
        _playable_summary(5.0, audio_codec=None),
        _playable_summary(5.0, audio_codec=""),
    ],
)
def test_smoke_playable_media_gate_rejects_zero_wrong_duration_or_missing_audio(
    summary: dict[str, object],
) -> None:
    smoke = _load_smoke_module()

    with pytest.raises(RuntimeError, match="media_evidence_invalid") as raised:
        smoke._require_playable_media_summary(
            summary,
            expected_duration_sec=5.0,
            tolerance_sec=0.25,
        )

    assert len(str(raised.value)) < 128


def test_smoke_builds_hash_linked_review_artifact_evidence(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    snapshot_paths = smoke._write_review_snapshots(
        tmp_path,
        timeline={"timeline_id": "timeline"},
        session={"session_id": "session"},
    )
    artifact_paths = {
        "srt": tmp_path / "captions.srt",
        "exact_preview": tmp_path / "exact-preview.mp4",
        "final_mp4": tmp_path / "final.mp4",
        "capcut_draft": tmp_path / "draft_content.json",
    }
    for name, path in artifact_paths.items():
        path.write_bytes(f"artifact:{name}".encode("utf-8"))
    media_summary = {
        "exact_preview": _playable_summary(5.25),
        "final_mp4": _playable_summary(599.5),
    }

    evidence = smoke._build_review_artifact_evidence(
        tmp_path,
        srt_path=artifact_paths["srt"],
        exact_preview_path=artifact_paths["exact_preview"],
        timeline_snapshot_path=snapshot_paths["timeline"],
        editing_session_snapshot_path=snapshot_paths["editing_session"],
        final_mp4_path=artifact_paths["final_mp4"],
        capcut_draft_path=artifact_paths["capcut_draft"],
        ffprobe_summary=media_summary,
    )

    assert set(evidence) == {
        "srt",
        "exact_preview",
        "timeline_snapshot",
        "editing_session_snapshot",
        "ffprobe_summary",
        "final_mp4",
        "capcut_draft",
    }
    for row in evidence.values():
        artifact_path = Path(row["path"])
        assert artifact_path.is_file()
        assert row["sha256"] == smoke._sha256(artifact_path)
    ffprobe_path = tmp_path / "review" / "ffprobe-summary.json"
    assert Path(evidence["ffprobe_summary"]["path"]) == ffprobe_path
    assert json.loads(ffprobe_path.read_text(encoding="utf-8")) == media_summary
    assert evidence["ffprobe_summary"]["exact_preview"] == media_summary["exact_preview"]
    assert evidence["ffprobe_summary"]["final_mp4"] == media_summary["final_mp4"]
    assert "media" not in evidence["ffprobe_summary"]
    assert list((tmp_path / "review").glob("*.tmp")) == []


def test_smoke_review_evidence_rejects_unplayable_summary_before_json_publish(tmp_path: Path) -> None:
    smoke = _load_smoke_module()
    snapshot_paths = smoke._write_review_snapshots(
        tmp_path,
        timeline={"timeline_id": "timeline"},
        session={"session_id": "session"},
    )
    artifact_paths = {
        "srt": tmp_path / "captions.srt",
        "exact_preview": tmp_path / "exact-preview.mp4",
        "final_mp4": tmp_path / "final.mp4",
        "capcut_draft": tmp_path / "draft_content.json",
    }
    for path in artifact_paths.values():
        path.write_bytes(b"artifact")

    with pytest.raises(RuntimeError, match="media_evidence_invalid"):
        smoke._build_review_artifact_evidence(
            tmp_path,
            srt_path=artifact_paths["srt"],
            exact_preview_path=artifact_paths["exact_preview"],
            timeline_snapshot_path=snapshot_paths["timeline"],
            editing_session_snapshot_path=snapshot_paths["editing_session"],
            final_mp4_path=artifact_paths["final_mp4"],
            capcut_draft_path=artifact_paths["capcut_draft"],
            ffprobe_summary={
                "exact_preview": _playable_summary(0.0),
                "final_mp4": _playable_summary(600.0),
            },
        )

    assert not (tmp_path / "review" / "ffprobe-summary.json").exists()
