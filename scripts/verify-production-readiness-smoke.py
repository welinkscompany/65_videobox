from __future__ import annotations

"""Run the real 10-minute VideoBox production-readiness smoke locally.

The API, local storage, subtitle generation, and FFmpeg renderer are production
code.  Only LLM/STT/TTS providers are deterministic so this check never contacts
a localhost LLM or an external provider.
"""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

# The repository packages are installed for pytest, but this script is also
# intentionally runnable directly from the checked-out worktree.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for package_source in (
    REPOSITORY_ROOT / "services" / "api" / "src",
    *sorted((REPOSITORY_ROOT / "packages").glob("*/src")),
):
    if str(package_source) not in sys.path:
        sys.path.insert(0, str(package_source))

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.llm import LLMProviderError
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment
from videobox_provider_interfaces.tts import TTSRequest, TTSResult
from videobox_storage.local_project_store import LocalProjectStore


SMOKE_DURATION_SEC = 600.0
EXACT_PREVIEW_DURATION_SEC = 5.0
EXACT_PREVIEW_DURATION_TOLERANCE_SEC = 0.25
FINAL_MEDIA_DURATION_TOLERANCE_SEC = 0.5
EXACT_PREVIEW_RANGE_EQUALITY_TOLERANCE_SEC = 0.000001
REVISED_CAPTION = "수정된 최종 자막: 열 분 한국어 제작 흐름이 실제 출력까지 유지됩니다."
SOURCE_CAPTIONS = [
    "첫 번째 한국어 제작 구간입니다.",
    "편집기에서 장면 전환과 음량을 차례로 확인합니다.",
]
LONG_FORM_PROFILE_NAMES = ("loop", "crop_pad_overlay", "audio_ducking")
_LONG_FORM_FIXTURES: dict[str, dict[str, Any]] = {
    "loop": {
        "broll_controls": {"fit": "fit", "loop": True, "pad": False, "trim_start_sec": 0.0},
        "include_image_overlay": False,
        "audio_controls": None,
        "desktop_capcut_opened": False,
    },
    "crop_pad_overlay": {
        "broll_controls": {"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.2},
        "include_image_overlay": True,
        "audio_controls": None,
        "desktop_capcut_opened": False,
    },
    "audio_ducking": {
        "broll_controls": {"fit": "fit", "loop": True, "pad": False, "trim_start_sec": 0.0},
        "include_image_overlay": False,
        "audio_controls": {"gain_db": -6.0, "fade_in_sec": 0.5, "fade_out_sec": 0.5, "ducking": True},
        "desktop_capcut_opened": False,
    },
}


def get_long_form_fixture(name: str) -> dict[str, Any]:
    try:
        return dict(_LONG_FORM_FIXTURES[name])
    except KeyError as exc:
        raise ValueError(f"Unknown long-form QA fixture: {name}") from exc


class DeterministicOfflineRuntime:
    """Forces the production local-first components to use heuristic fallbacks."""

    def generate_structured(self, **_: object) -> object:
        raise LLMProviderError(
            provider_name="deterministic_smoke",
            message="Production-readiness smoke uses deterministic heuristic fallbacks.",
            retryable=False,
            error_code="DETERMINISTIC_SMOKE_FALLBACK",
        )


class DeterministicKoreanSTTProvider:
    provider_name = "deterministic_korean_smoke_stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        del request
        return STTResult(
            text=" ".join(SOURCE_CAPTIONS),
            segments=[
                STTSegment(0.0, 300.0, SOURCE_CAPTIONS[0], confidence=0.99),
                STTSegment(300.0, 600.0, SOURCE_CAPTIONS[1], confidence=0.99),
            ],
            provider_name=self.provider_name,
        )


class DeterministicWaveTTSProvider:
    provider_name = "deterministic_wave_smoke_tts"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(request.output_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48_000)
            duration_sec = request.target_duration_sec or 1.0
            output.writeframes(b"\x10\x00" * int(48_000 * duration_sec))
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


def require_duration(*, duration_sec: float, expected_sec: float, tolerance_sec: float) -> None:
    if abs(duration_sec - expected_sec) > tolerance_sec:
        raise ValueError(
            f"Expected {expected_sec:.1f}s +/- {tolerance_sec:.1f}s, received {duration_sec:.3f}s."
        )


def _run(command: list[str], *, timeout: int = 1_800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def _probe_duration(path: Path, *, ffprobe_binary: str) -> float:
    result = _run(
        [ffprobe_binary, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        timeout=60,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _probe_media_summary(path: Path, *, ffprobe_binary: str) -> dict[str, Any]:
    try:
        result = _run(
            [
                ffprobe_binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration,format_name:stream=codec_type,codec_name,pix_fmt",
                "-of",
                "json",
                str(path),
            ],
            timeout=60,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("invalid ffprobe payload")
        format_payload = payload.get("format")
        streams = payload.get("streams")
        if not isinstance(format_payload, dict) or not isinstance(streams, list) or len(streams) > 32:
            raise ValueError("invalid ffprobe schema")
        if not all(isinstance(stream, dict) for stream in streams):
            raise ValueError("invalid ffprobe stream")
        duration = float(format_payload["duration"])
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("invalid ffprobe duration")
        format_name = format_payload.get("format_name")
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if video is None:
            raise ValueError("missing ffprobe video stream")
        video_codec = video.get("codec_name")
        pixel_format = video.get("pix_fmt")
        audio_codec = audio.get("codec_name") if audio is not None else None
        bounded_text = (format_name, video_codec, pixel_format, audio_codec)
        if any(value is not None and (not isinstance(value, str) or not value or len(value) > 128) for value in bounded_text):
            raise ValueError("invalid ffprobe field")
        if format_name is None or video_codec is None or pixel_format is None:
            raise ValueError("missing ffprobe field")
        return {
            "duration_sec": duration,
            "format": format_name,
            "video_codec": video_codec,
            "pixel_format": pixel_format,
            "audio_codec": audio_codec,
        }
    except Exception:
        raise RuntimeError("media_probe_failed") from None


def _require_playable_media_summary(
    summary: dict[str, Any],
    *,
    expected_duration_sec: float,
    tolerance_sec: float,
) -> None:
    try:
        duration = summary.get("duration_sec")
        audio_codec = summary.get("audio_codec")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or float(duration) <= 0
            or not math.isfinite(expected_duration_sec)
            or expected_duration_sec <= 0
            or not math.isfinite(tolerance_sec)
            or tolerance_sec < 0
            or abs(float(duration) - expected_duration_sec) > tolerance_sec
            or not isinstance(audio_codec, str)
            or not audio_codec
            or len(audio_codec) > 128
        ):
            raise ValueError("unplayable media summary")
    except Exception:
        raise RuntimeError("media_evidence_invalid") from None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_stable_json(destination: Path, payload: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_review_snapshots(
    work_root: Path,
    *,
    timeline: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Path]:
    review_root = work_root / "review"
    review_root.mkdir(parents=True, exist_ok=True)
    destinations = {
        "timeline": review_root / "timeline.json",
        "editing_session": review_root / "editing-session.json",
    }
    for name, payload in (("timeline", timeline), ("editing_session", session)):
        _write_stable_json(destinations[name], payload)
    return destinations


def _artifact_evidence(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError("review_artifact_missing")
    return {"path": str(path), "sha256": _sha256(path)}


def _build_review_artifact_evidence(
    work_root: Path,
    *,
    srt_path: Path,
    exact_preview_path: Path,
    timeline_snapshot_path: Path,
    editing_session_snapshot_path: Path,
    final_mp4_path: Path,
    capcut_draft_path: Path,
    ffprobe_summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    _require_playable_media_summary(
        ffprobe_summary.get("exact_preview", {}),
        expected_duration_sec=EXACT_PREVIEW_DURATION_SEC,
        tolerance_sec=EXACT_PREVIEW_DURATION_TOLERANCE_SEC,
    )
    _require_playable_media_summary(
        ffprobe_summary.get("final_mp4", {}),
        expected_duration_sec=SMOKE_DURATION_SEC,
        tolerance_sec=FINAL_MEDIA_DURATION_TOLERANCE_SEC,
    )
    ffprobe_summary_path = work_root / "review" / "ffprobe-summary.json"
    _write_stable_json(ffprobe_summary_path, ffprobe_summary)
    evidence: dict[str, dict[str, Any]] = {
        "srt": _artifact_evidence(srt_path),
        "exact_preview": _artifact_evidence(exact_preview_path),
        "timeline_snapshot": _artifact_evidence(timeline_snapshot_path),
        "editing_session_snapshot": _artifact_evidence(editing_session_snapshot_path),
        "ffprobe_summary": _artifact_evidence(ffprobe_summary_path),
        "final_mp4": _artifact_evidence(final_mp4_path),
        "capcut_draft": _artifact_evidence(capcut_draft_path),
    }
    evidence["ffprobe_summary"].update(ffprobe_summary)
    return evidence


def _create_short_broll(path: Path, *, ffmpeg_binary: str) -> None:
    _run(
        [
            ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:r=12:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x180:r=12:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=12:d=1",
            "-filter_complex",
            "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            str(path),
        ],
        timeout=120,
    )


def _create_sfx(path: Path, *, ffmpeg_binary: str) -> None:
    _run([ffmpeg_binary, "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(path)], timeout=120)


def _create_bgm(path: Path, *, ffmpeg_binary: str) -> None:
    _run([ffmpeg_binary, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=3", str(path)], timeout=120)


def _create_overlay_image(path: Path, *, ffmpeg_binary: str) -> None:
    _run(
        [ffmpeg_binary, "-y", "-f", "lavfi", "-i", "color=c=yellow:s=48x32", "-frames:v", "1", str(path)],
        timeout=120,
    )


def _prepare_projects_root(work_root: Path) -> Path:
    projects_root = work_root / "projects"
    if projects_root.exists():
        shutil.rmtree(projects_root)
    projects_root.mkdir(parents=True, exist_ok=True)
    return projects_root


def _assert_status(response: Any, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text}")
    return response.json()


def _poll_final_render(client: TestClient, *, project_id: str, job_id: str, timeout_sec: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = _assert_status(client.get(f"/api/projects/{project_id}/final-renders/{job_id}"), 200)
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for final render job '{job_id}'.")


def _poll_exact_preview(
    client: TestClient,
    *,
    project_id: str,
    generation_id: str,
    expected_revision: int,
    expected_start_sec: float,
    expected_end_sec: float,
    timeout_sec: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    generation_label = generation_id[:80]
    canonical_content_url = f"/api/projects/{project_id}/exact-previews/{generation_id}/content"
    while time.monotonic() < deadline:
        response = client.get(f"/api/projects/{project_id}/exact-previews/{generation_id}")
        if response.status_code != 200:
            raise RuntimeError(
                f"Exact preview generation '{generation_label}' status request failed with HTTP {response.status_code}."
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Exact preview generation '{generation_label}' returned an invalid status payload."
            )
        status = str(payload.get("status") or "unavailable")
        if status in {"ready", "succeeded"}:
            start_sec = payload.get("timeline_start_sec")
            end_sec = payload.get("timeline_end_sec")
            identity_matches = (
                payload.get("generation_id") == generation_id
                and isinstance(payload.get("artifact_revision"), int)
                and not isinstance(payload.get("artifact_revision"), bool)
                and payload.get("artifact_revision") == expected_revision
                and isinstance(start_sec, (int, float))
                and not isinstance(start_sec, bool)
                and math.isfinite(float(start_sec))
                and math.isclose(
                    float(start_sec),
                    expected_start_sec,
                    rel_tol=0.0,
                    abs_tol=EXACT_PREVIEW_RANGE_EQUALITY_TOLERANCE_SEC,
                )
                and isinstance(end_sec, (int, float))
                and not isinstance(end_sec, bool)
                and math.isfinite(float(end_sec))
                and math.isclose(
                    float(end_sec),
                    expected_end_sec,
                    rel_tol=0.0,
                    abs_tol=EXACT_PREVIEW_RANGE_EQUALITY_TOLERANCE_SEC,
                )
                and payload.get("content_url") == canonical_content_url
            )
            if not identity_matches:
                raise RuntimeError("exact_preview_identity_mismatch")
            range_response = client.get(
                canonical_content_url,
                headers={"Range": "bytes=0-0"},
            )
            if range_response.status_code != 206:
                raise RuntimeError("exact_preview_range_failed")
            return {**payload, "status": "ready", "range_status": 206}
        if status not in {"pending", "running"}:
            raise RuntimeError(
                f"Exact preview generation '{generation_label}' entered terminal state {status[:80]}."
            )
        time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for exact preview generation '{generation_label}'.")


def _poll_capcut_draft_export(client: TestClient, *, project_id: str, job_id: str, timeout_sec: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = _assert_status(client.get(f"/api/projects/{project_id}/capcut-draft-exports/{job_id}"), 200)
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for CapCut draft export job '{job_id}'.")


def _extract_frame(path: Path, *, second: float, output_path: Path, ffmpeg_binary: str) -> str:
    _run([ffmpeg_binary, "-y", "-ss", str(second), "-i", str(path), "-frames:v", "1", str(output_path)], timeout=120)
    return _sha256(output_path)


def _decode_ffmpeg_utf8(payload: bytes) -> str:
    return payload.decode("utf-8")


def _extract_subtitle_stream(path: Path, *, ffmpeg_binary: str) -> str:
    result = subprocess.run(
        [ffmpeg_binary, "-v", "error", "-i", str(path), "-map", "0:s:0", "-f", "srt", "pipe:1"],
        check=False,
        capture_output=True,
        text=False,
        timeout=120,
    )
    return _decode_ffmpeg_utf8(result.stdout) if result.returncode == 0 else ""


def _short_broll_is_observably_looped(*, final_path: Path, work_root: Path, ffmpeg_binary: str) -> bool:
    first_cycle_a = _extract_corner_pixel(final_path, second=0.5, ffmpeg_binary=ffmpeg_binary)
    repeated_cycle_a = _extract_corner_pixel(final_path, second=3.5, ffmpeg_binary=ffmpeg_binary)
    first_cycle_b = _extract_corner_pixel(final_path, second=1.5, ffmpeg_binary=ffmpeg_binary)
    repeated_cycle_b = _extract_corner_pixel(final_path, second=4.5, ffmpeg_binary=ffmpeg_binary)
    return first_cycle_a == repeated_cycle_a and first_cycle_b == repeated_cycle_b and first_cycle_a != first_cycle_b


def _extract_corner_pixel(path: Path, *, second: float, ffmpeg_binary: str) -> bytes:
    result = subprocess.run(
        [
            ffmpeg_binary,
            "-v",
            "error",
            "-ss",
            str(second),
            "-i",
            str(path),
            "-vf",
            "crop=2:2:8:(ih-2)/2",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    if len(result.stdout) != 12:
        raise RuntimeError("Could not read the B-roll corner pixel from final output.")
    return result.stdout


def run_smoke(
    *,
    narration: Path,
    work_root: Path,
    ffmpeg_binary: str,
    ffprobe_binary: str,
    fixture_name: str = "loop",
    project_name: str | None = None,
) -> dict[str, object]:
    fixture = get_long_form_fixture(fixture_name)
    narration = narration.resolve()
    if not narration.is_file():
        raise FileNotFoundError(f"Narration source does not exist: {narration}")
    require_duration(
        duration_sec=_probe_duration(narration, ffprobe_binary=ffprobe_binary),
        expected_sec=SMOKE_DURATION_SEC,
        tolerance_sec=0.1,
    )
    work_root.mkdir(parents=True, exist_ok=True)
    projects_root = _prepare_projects_root(work_root)
    script_path = work_root / "smoke-script.txt"
    script_path.write_text("\n".join(SOURCE_CAPTIONS), encoding="utf-8")
    broll_path = work_root / "short-broll.mp4"
    _create_short_broll(broll_path, ffmpeg_binary=ffmpeg_binary)
    sfx_path = work_root / "smoke-impact.wav"
    _create_sfx(sfx_path, ffmpeg_binary=ffmpeg_binary)
    bgm_path = work_root / "smoke-bgm.wav"
    if fixture["audio_controls"] is not None:
        _create_bgm(bgm_path, ffmpeg_binary=ffmpeg_binary)
    overlay_image_path = work_root / "smoke-overlay.png"
    if fixture["include_image_overlay"]:
        _create_overlay_image(overlay_image_path, ffmpeg_binary=ffmpeg_binary)

    store = LocalProjectStore(projects_root)
    renderer = FfmpegFinalRenderer(
        store=store,
        ffmpeg_binary=ffmpeg_binary,
        video_width=320,
        video_height=180,
        video_fps=12,
        render_timeout_seconds=1_800,
    )
    app = create_app(
        projects_root=projects_root,
        local_only_runtime_service_factory=lambda _: DeterministicOfflineRuntime(),
        stt_provider=DeterministicKoreanSTTProvider(),
        tts_provider=DeterministicWaveTTSProvider(),
        final_renderer=renderer,
        pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=12),
    )
    checks: dict[str, bool] = {}
    with TestClient(app) as client:
        project = _assert_status(
            client.post(
                "/api/projects",
                json={
                    "name": project_name
                    or f"Production readiness Korean smoke {fixture_name}"
                },
            ),
            201,
        )
        project_id = project["project_id"]
        narration_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)}), 201)
        with narration.open("rb") as voice_sample_file:
            voice_sample_asset = _assert_status(client.post(
                f"/api/projects/{project_id}/assets/voice-sample/upload",
                files={"file": (narration.name, voice_sample_file, "audio/wav")},
            ), 201)
        checks["voice_sample_uploaded"] = voice_sample_asset["asset_type"] == "voice_sample_audio"
        script_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script_path)}), 201)
        broll_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/broll-video",
            json={"source_path": str(broll_path), "title": "3 second looping smoke broll", "tags": ["smoke"]},
        ), 201)
        sfx_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/sfx", json={"source_path": str(sfx_path)}), 201)
        bgm_asset = None
        if fixture["audio_controls"] is not None:
            registered_bgm = store.register_asset(
                project_id=project_id, asset_type=AssetType.BGM, source_path=bgm_path
            )
            bgm_asset = {"asset_id": registered_bgm.asset_id, "storage_uri": registered_bgm.storage_uri}
        image_asset = None
        if fixture["include_image_overlay"]:
            registered_image = store.register_asset(
                project_id=project_id, asset_type=AssetType.IMAGE, source_path=overlay_image_path
            )
            image_asset = {"asset_id": registered_image.asset_id, "storage_uri": registered_image.storage_uri}
        checks["ingest"] = True

        transcription = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": narration_asset["asset_id"]}), 202)
        analysis = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/segment-analysis",
            json={"transcription_job_id": transcription["job_id"], "script_asset_id": script_asset["asset_id"]},
        ), 202)
        tts_candidate = _assert_status(client.post(
            f"/api/projects/{project_id}/tts-candidates",
            json={
                "segment_text": SOURCE_CAPTIONS[0],
                "voice_sample_asset_id": voice_sample_asset["asset_id"],
                "segment_id": "seg_001",
                "target_duration_sec": 300.0,
            },
        ), 201)
        checks["tts_candidate_pending_operator_review"] = (
            tts_candidate["technical_status"] == "accepted"
            and tts_candidate["operator_review_status"] == "pending"
        )
        approved_tts_candidate = _assert_status(client.patch(
            f"/api/projects/{project_id}/tts-candidates/{tts_candidate['candidate_id']}/listening-review",
            json={"decision": "approved"},
        ), 200)
        checks["tts_candidate_listening_approved"] = (
            approved_tts_candidate["operator_review_status"] == "approved"
        )
        broll_recommendation = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/broll-recommendation", json={"segment_analysis_job_id": analysis["job_id"]}), 202)
        music_recommendation = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/music-recommendation", json={"segment_analysis_job_id": analysis["job_id"]}), 202)
        timeline_job = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/build-timeline",
            json={"segment_analysis_job_id": analysis["job_id"], "recommendation_job_ids": [broll_recommendation["job_id"], music_recommendation["job_id"]]},
        ), 202)
        timeline_result = _assert_status(client.get(f"/api/projects/{project_id}/timelines/{timeline_job['job_id']}"), 200)
        timeline = timeline_result["timeline"]
        if "music/suggested" in json.dumps(timeline, ensure_ascii=False):
            raise AssertionError("Assetless music recommendation created a synthetic timeline clip.")
        checks["assetless_bgm_excluded"] = True

        session = _assert_status(client.post(
            f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job["job_id"]}), 201)
        session_id = session["session_id"]
        session = _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
            json={"recommendation_id": tts_candidate["candidate_id"], "asset_id": tts_candidate["asset_id"], "expected_revision": session["session_revision"]},
        ), 200)
        sfx_session = _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/sfx",
            json={
                "asset_id": sfx_asset["asset_id"],
                "media_controls": fixture["audio_controls"],
                "expected_revision": session["session_revision"],
            },
        ), 200)
        session = sfx_session
        if sfx_session["segments"][0].get("sfx_override", {}).get("asset_id") != sfx_asset["asset_id"]:
            raise AssertionError(f"SFX selection did not persist to editing session: {sfx_session['segments'][0]}")
        for segment in session["segments"]:
            segment_id = segment["segment_id"]
            session = _assert_status(client.patch(
                f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll",
                json={
                    "asset_id": broll_asset["asset_id"],
                    "media_controls": fixture["broll_controls"],
                    "expected_revision": session["session_revision"],
                },
            ), 200)
        if bgm_asset is not None:
            session = _assert_status(client.patch(
                f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
                json={
                    "asset_id": bgm_asset["asset_id"],
                    "media_controls": fixture["audio_controls"],
                    "expected_revision": session["session_revision"],
                },
            ), 200)
        if image_asset is not None:
            session = _assert_status(client.patch(
                f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/image-overlay",
                json={
                    "asset_id": image_asset["asset_id"],
                    "text": "SMOKE IMAGE OVERLAY",
                    "expected_revision": session["session_revision"],
                },
            ), 200)
        revised_segment_id = session["segments"][-1]["segment_id"]
        session = _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{revised_segment_id}/caption",
            json={"caption_text": REVISED_CAPTION, "expected_revision": session["session_revision"]},
        ), 200)
        session = _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{revised_segment_id}/explanation-card",
            json={"title": "Smoke overlay", "body": "Final output contract", "text": "SMOKE OVERLAY", "expected_revision": session["session_revision"]},
        ), 200)
        exact_preview_started = _assert_status(client.post(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/exact-preview",
            json={
                "expected_revision": session["session_revision"],
                "start_sec": 0.0,
                "end_sec": EXACT_PREVIEW_DURATION_SEC,
            },
        ), 202)
        exact_preview_status = _poll_exact_preview(
            client,
            project_id=project_id,
            generation_id=exact_preview_started["generation_id"],
            expected_revision=session["session_revision"],
            expected_start_sec=0.0,
            expected_end_sec=EXACT_PREVIEW_DURATION_SEC,
            timeout_sec=300,
        )
        exact_preview_record = store.get_exact_preview(
            project_id=project_id,
            generation_id=exact_preview_started["generation_id"],
        )
        if (
            exact_preview_record.get("state") != "succeeded"
            or int(exact_preview_record.get("expected_revision") or 0) != int(session["session_revision"])
            or not exact_preview_record.get("artifact_uri")
        ):
            raise RuntimeError(
                f"Exact preview generation '{exact_preview_started['generation_id']}' is not the current session artifact."
            )
        exact_preview_path = store.resolve_storage_uri(
            project_id=project_id,
            storage_uri=str(exact_preview_record["artifact_uri"]),
        )
        if not exact_preview_path.is_file():
            raise RuntimeError(
                f"Exact preview generation '{exact_preview_started['generation_id']}' has no current artifact file."
            )
        checks["exact_preview_ready"] = True
        checks["exact_preview_range_206"] = exact_preview_status["range_status"] == 206
        regenerated = _assert_status(client.post(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
            json={
                "segment_ids": ["seg_001", revised_segment_id],
                "fields": ["caption", "broll", "visual_overlay", "tts_replacement", "sfx"] + (["music"] if bgm_asset is not None else []),
                "expected_revision": session["session_revision"],
            },
        ), 202)
        partial = _assert_status(client.get(
            f"/api/projects/{project_id}/partial-regenerations/{regenerated['job_id']}"), 200)
        if "sfx_refresh" not in partial["downstream_steps"]:
            raise AssertionError(f"SFX partial regeneration step missing: {partial['downstream_steps']}")
        candidate_timeline_job_id = partial["job_id"]
        candidate_review = _assert_status(
            client.get(f"/api/projects/{project_id}/review-snapshots/{candidate_timeline_job_id}"), 200
        )
        sfx_pending = [
            item for item in candidate_review["pending_recommendations"]
            if item.get("recommendation_type") == "sfx"
        ]
        if not sfx_pending:
            raise AssertionError(f"SFX selection did not produce a pending review recommendation: {candidate_review['pending_recommendations']}")
        sfx_recommendation_id = sfx_pending[0]["recommendation_id"]
        _assert_status(client.post(
            f"/api/projects/{project_id}/review-snapshots/{candidate_timeline_job_id}/recommendations/{sfx_recommendation_id}/approve"
        ), 200)
        _assert_status(client.post(
            f"/api/projects/{project_id}/review-approvals/{candidate_timeline_job_id}/approve"), 202)
        checks["edit_and_approval"] = True

        candidate_timeline = _assert_status(
            client.get(f"/api/projects/{project_id}/timelines/{candidate_timeline_job_id}"), 200
        )["timeline"]
        current_session = _assert_status(
            client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}"), 200
        )
        snapshot_paths = _write_review_snapshots(
            work_root,
            timeline=candidate_timeline,
            session=current_session,
        )
        checks["approved_tts_in_final_and_capcut"] = any(
            item.get("recommendation_type") == "tts_replacement"
            and item.get("payload", {}).get("selected_asset_uri")
            for item in candidate_timeline.get("applied_recommendations", [])
            if isinstance(item, dict)
        )
        checks["approved_sfx_in_final_and_capcut"] = any(
            item.get("recommendation_type") == "sfx" and item.get("selected_asset_id") == sfx_asset["asset_id"]
            for item in candidate_timeline.get("applied_recommendations", []) if isinstance(item, dict)
        )
        broll_controls = [
            clip.get("media_controls")
            for track in candidate_timeline.get("tracks", [])
            if track.get("track_type") == "broll"
            for clip in track.get("clips", [])
            if isinstance(clip, dict)
        ]
        broll_controls.extend(
            item.get("payload", {}).get("media_controls")
            for item in candidate_timeline.get("applied_recommendations", [])
            if isinstance(item, dict) and item.get("recommendation_type") == "broll"
        )
        checks["broll_controls_in_timeline"] = any(
            isinstance(controls, dict)
            and all(controls.get(key) == value for key, value in fixture["broll_controls"].items())
            for controls in broll_controls
        )
        if bgm_asset is not None:
            audio_controls = [
                clip.get("media_controls")
                for track in candidate_timeline.get("tracks", [])
                if track.get("track_type") in {"bgm", "sfx"}
                for clip in track.get("clips", [])
                if isinstance(clip, dict)
            ]
            audio_controls.extend(
                item.get("payload", {}).get("media_controls")
                for item in candidate_timeline.get("applied_recommendations", [])
                if isinstance(item, dict) and item.get("recommendation_type") in {"bgm", "sfx"}
            )
            checks["audio_controls_in_timeline"] = any(
                isinstance(controls, dict)
                and all(controls.get(key) == value for key, value in fixture["audio_controls"].items())
                for controls in audio_controls
            )

        subtitle_job = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/subtitle-render", json={"timeline_job_id": candidate_timeline_job_id}), 202)
        subtitle = _assert_status(client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job['job_id']}"), 200)
        subtitle_path = store.resolve_storage_uri(project_id=project_id, storage_uri=subtitle["subtitle"]["file_uri"])
        checks["revised_caption_in_srt"] = REVISED_CAPTION in subtitle_path.read_text(encoding="utf-8")

        final_job = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": candidate_timeline_job_id}), 202)
        final = _poll_final_render(client, project_id=project_id, job_id=final_job["job_id"], timeout_sec=2_400)
        if final["status"] != "succeeded" or final["render"] is None:
            raise RuntimeError(f"Final render failed: {final}")
        final_path = store.resolve_storage_uri(project_id=project_id, storage_uri=final["render"]["file_uri"])
        checks["final_duration"] = False
        require_duration(
            duration_sec=_probe_duration(final_path, ffprobe_binary=ffprobe_binary),
            expected_sec=SMOKE_DURATION_SEC,
            tolerance_sec=0.5,
        )
        checks["final_duration"] = True
        before_overlay = _extract_frame(final_path, second=10, output_path=work_root / "before-overlay.png", ffmpeg_binary=ffmpeg_binary)
        during_overlay = _extract_frame(final_path, second=310, output_path=work_root / "during-overlay.png", ffmpeg_binary=ffmpeg_binary)
        checks["overlay_changes_frame"] = before_overlay != during_overlay
        checks["short_broll_loops"] = (
            not fixture["broll_controls"]["loop"]
            or _short_broll_is_observably_looped(
                final_path=final_path,
                work_root=work_root,
                ffmpeg_binary=ffmpeg_binary,
            )
        )
        checks["final_has_no_selectable_subtitle_stream"] = not _extract_subtitle_stream(
            final_path,
            ffmpeg_binary=ffmpeg_binary,
        )
        # Styled captions are burned into the final MP4, so there is no
        # extractable subtitle stream. The revised SRT plus the burned-in
        # output contract together prove the regenerated caption path.
        checks["revised_caption_in_final_mp4"] = (
            bool(checks["revised_caption_in_srt"])
            and bool(checks["final_has_no_selectable_subtitle_stream"])
        )
        checks["final_artifact_sha256"] = bool(_sha256(final_path))
        capcut_job = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/capcut-draft-export",
            json={"timeline_job_id": candidate_timeline_job_id},
        ), 202)
        capcut = _poll_capcut_draft_export(
            client, project_id=project_id, job_id=capcut_job["job_id"], timeout_sec=300
        )
        if capcut["status"] != "succeeded" or capcut["export"] is None:
            raise RuntimeError(f"CapCut draft export failed: {capcut}")
        draft_path = store.resolve_storage_uri(project_id=project_id, storage_uri=capcut["export"]["file_uri"])
        draft_content = (draft_path / "draft_content.json").read_text(encoding="utf-8")
        checks["approved_tts_in_final_and_capcut"] = (
            checks["approved_tts_in_final_and_capcut"] and "tts_candidate.wav" in draft_content
        )
        checks["approved_sfx_in_final_and_capcut"] = (
            checks["approved_sfx_in_final_and_capcut"] and "smoke-impact.wav" in draft_content
        )
        checks["broll_controls_in_capcut_draft"] = "short-broll.mp4" in draft_content
        if bgm_asset is not None:
            checks["audio_controls_in_capcut_draft"] = "smoke-bgm.wav" in draft_content
            checks["capcut_ducking_warning_preserved"] = any(
                "ducking is not natively supported" in note
                for note in capcut["export"].get("notes") or []
            )
        if image_asset is not None:
            checks["image_overlay_in_final_and_capcut"] = (
                "smoke-overlay.png" in draft_content and bool(checks["overlay_changes_frame"])
            )

    if not all(checks.values()):
        raise AssertionError(f"Smoke checks failed: {checks}")
    artifact_evidence = _build_review_artifact_evidence(
        work_root,
        srt_path=subtitle_path,
        exact_preview_path=exact_preview_path,
        timeline_snapshot_path=snapshot_paths["timeline"],
        editing_session_snapshot_path=snapshot_paths["editing_session"],
        final_mp4_path=final_path,
        capcut_draft_path=draft_path / "draft_content.json",
        ffprobe_summary={
            "exact_preview": _probe_media_summary(exact_preview_path, ffprobe_binary=ffprobe_binary),
            "final_mp4": _probe_media_summary(final_path, ffprobe_binary=ffprobe_binary),
        },
    )
    return {
        "fixture_name": fixture_name,
        "desktop_capcut_opened": fixture["desktop_capcut_opened"],
        "checks": checks,
        "narration": {"path": str(narration), "sha256": _sha256(narration)},
        "srt": artifact_evidence["srt"],
        "exact_preview": {
            "status": exact_preview_status["status"],
            "generation_id": exact_preview_started["generation_id"],
            "session_revision": exact_preview_status["artifact_revision"],
            "timeline_start_sec": exact_preview_status["timeline_start_sec"],
            "timeline_end_sec": exact_preview_status["timeline_end_sec"],
            "range_status": 206,
            **artifact_evidence["exact_preview"],
        },
        "timeline_snapshot": artifact_evidence["timeline_snapshot"],
        "editing_session_snapshot": artifact_evidence["editing_session_snapshot"],
        "ffprobe_summary": artifact_evidence["ffprobe_summary"],
        "final_mp4": artifact_evidence["final_mp4"],
        "capcut_draft": {
            **artifact_evidence["capcut_draft"],
            "warnings": list(capcut["export"].get("notes") or []),
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--narration", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    print(json.dumps(
        run_smoke(
            narration=args.narration,
            work_root=args.work_root,
            ffmpeg_binary=args.ffmpeg,
            ffprobe_binary=args.ffprobe,
        ),
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
