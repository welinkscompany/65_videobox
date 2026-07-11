from __future__ import annotations

"""Run the real 10-minute VideoBox production-readiness smoke locally.

The API, local storage, subtitle generation, and FFmpeg renderer are production
code.  Only LLM/STT/TTS providers are deterministic so this check never contacts
a localhost LLM or an external provider.
"""

import argparse
import hashlib
import json
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
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_provider_interfaces.llm import LLMProviderError
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment
from videobox_provider_interfaces.tts import TTSRequest, TTSResult
from videobox_storage.local_project_store import LocalProjectStore


SMOKE_DURATION_SEC = 600.0
REVISED_CAPTION = "수정된 최종 자막: 열 분 한국어 제작 흐름이 실제 출력까지 유지됩니다."
SOURCE_CAPTIONS = [
    "첫 번째 한국어 제작 구간입니다.",
    "편집기에서 장면 전환과 음량을 차례로 확인합니다.",
]


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
            output.writeframes(b"\x00\x00" * 48_000)
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _extract_frame(path: Path, *, second: float, output_path: Path, ffmpeg_binary: str) -> str:
    _run([ffmpeg_binary, "-y", "-ss", str(second), "-i", str(path), "-frames:v", "1", str(output_path)], timeout=120)
    return _sha256(output_path)


def _decode_ffmpeg_utf8(payload: bytes) -> str:
    return payload.decode("utf-8")


def _extract_subtitle_stream(path: Path, *, ffmpeg_binary: str) -> str:
    result = subprocess.run(
        [ffmpeg_binary, "-v", "error", "-i", str(path), "-map", "0:s:0", "-f", "srt", "pipe:1"],
        check=True,
        capture_output=True,
        text=False,
        timeout=120,
    )
    return _decode_ffmpeg_utf8(result.stdout)


def _short_broll_is_observably_looped(*, final_path: Path, work_root: Path, ffmpeg_binary: str) -> bool:
    first_cycle_a = _extract_frame(final_path, second=0.5, output_path=work_root / "broll-cycle-a.png", ffmpeg_binary=ffmpeg_binary)
    repeated_cycle_a = _extract_frame(final_path, second=3.5, output_path=work_root / "broll-cycle-a-repeat.png", ffmpeg_binary=ffmpeg_binary)
    first_cycle_b = _extract_frame(final_path, second=1.5, output_path=work_root / "broll-cycle-b.png", ffmpeg_binary=ffmpeg_binary)
    repeated_cycle_b = _extract_frame(final_path, second=4.5, output_path=work_root / "broll-cycle-b-repeat.png", ffmpeg_binary=ffmpeg_binary)
    return first_cycle_a == repeated_cycle_a and first_cycle_b == repeated_cycle_b and first_cycle_a != first_cycle_b


def run_smoke(*, narration: Path, work_root: Path, ffmpeg_binary: str, ffprobe_binary: str) -> dict[str, object]:
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
        local_first_runtime_service_factory=lambda _: DeterministicOfflineRuntime(),
        stt_provider=DeterministicKoreanSTTProvider(),
        tts_provider=DeterministicWaveTTSProvider(),
        final_renderer=renderer,
    )
    checks: dict[str, bool] = {}
    with TestClient(app) as client:
        project = _assert_status(client.post("/api/projects", json={"name": "Production readiness Korean smoke"}), 201)
        project_id = project["project_id"]
        narration_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)}), 201)
        script_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script_path)}), 201)
        broll_asset = _assert_status(client.post(
            f"/api/projects/{project_id}/assets/broll-video",
            json={"source_path": str(broll_path), "title": "3 second looping smoke broll", "tags": ["smoke"]},
        ), 201)
        checks["ingest"] = True

        transcription = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": narration_asset["asset_id"]}), 202)
        analysis = _assert_status(client.post(
            f"/api/projects/{project_id}/jobs/segment-analysis",
            json={"transcription_job_id": transcription["job_id"], "script_asset_id": script_asset["asset_id"]},
        ), 202)
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
        for segment in session["segments"]:
            segment_id = segment["segment_id"]
            _assert_status(client.patch(
                f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/broll",
                json={"asset_id": broll_asset["asset_id"]},
            ), 200)
        revised_segment_id = session["segments"][-1]["segment_id"]
        _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{revised_segment_id}/caption",
            json={"caption_text": REVISED_CAPTION},
        ), 200)
        _assert_status(client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{revised_segment_id}/explanation-card",
            json={"title": "Smoke overlay", "body": "Final output contract", "text": "SMOKE OVERLAY"},
        ), 200)
        regenerated = _assert_status(client.post(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
            json={"segment_ids": [revised_segment_id], "fields": ["caption", "broll", "visual_overlay"]},
        ), 202)
        partial = _assert_status(client.get(
            f"/api/projects/{project_id}/partial-regenerations/{regenerated['job_id']}"), 200)
        candidate_timeline_job_id = partial["job_id"]
        _assert_status(client.post(
            f"/api/projects/{project_id}/review-approvals/{candidate_timeline_job_id}/approve"), 202)
        checks["edit_and_approval"] = True

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
        checks["short_broll_loops"] = _short_broll_is_observably_looped(
            final_path=final_path,
            work_root=work_root,
            ffmpeg_binary=ffmpeg_binary,
        )
        checks["revised_caption_in_final_mp4"] = REVISED_CAPTION in _extract_subtitle_stream(
            final_path,
            ffmpeg_binary=ffmpeg_binary,
        )
        checks["final_artifact_sha256"] = bool(_sha256(final_path))

    if not all(checks.values()):
        raise AssertionError(f"Smoke checks failed: {checks}")
    return {
        "checks": checks,
        "narration": {"path": str(narration), "sha256": _sha256(narration)},
        "final_mp4": {"path": str(final_path), "sha256": _sha256(final_path)},
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
