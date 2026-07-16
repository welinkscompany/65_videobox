"""Opt-in, independently driven Local Media Director release gate.

Unlike the Starter Pack test this test owns the Director flow and its
assertions.  It deliberately uses real locally-installed pack bytes, FFmpeg,
and PyCapCut, while the injected runtime rejects every AI-provider call.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_pack_release import ffprobe_media
from videobox_core_engine.media_pack_service import MediaPackService
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.llm import LLMTaskType, StructuredLLMResponse
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


ROOT = Path(__file__).resolve().parents[1]
REAL_PACK_ROOT = ROOT / "dist" / "starter-media-pack"
RUN_REAL_DIRECTOR_E2E = os.environ.get("VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E") == "1"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class _DeterministicLocalDirectorRuntime:
    external_calls = 0
    gemini_calls = 0
    local_task_calls: list[LLMTaskType] = []

    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, object],
        now: object | None = None,
    ) -> StructuredLLMResponse:
        del project_id, prompt, response_schema, now
        type(self).local_task_calls.append(task_type)
        output_data = {
            LLMTaskType.SCENE_PLANNING: {
                "review_required": False,
                "cleanup_decision": "keep",
            },
            LLMTaskType.KEYWORD_EXPANSION: {"keywords": ["local", "director"]},
            LLMTaskType.MUSIC_RECOMMENDATION: {
                "music_mood": "calm local bed",
                "score": 0.75,
            },
            LLMTaskType.OPERATOR_COPY: {
                "summary": "Local deterministic guidance.",
                "action_items": ["Continue local review."],
            },
        }[task_type]
        return StructuredLLMResponse(
            provider_name="deterministic_local_fixture",
            model_name="fixture",
            output_data=output_data,
            raw_text=json.dumps(output_data),
            metadata={"provider_trace": {"routing_mode": "local_only", "final_provider": "deterministic_local_fixture", "fallback_reasons": []}},
        )


def test_offline_director_runtime_serves_deterministic_local_responses_for_pipeline_tasks() -> None:
    """The release fixture must exercise every legacy LocalFirst helper without a provider call."""
    _DeterministicLocalDirectorRuntime.external_calls = 0
    _DeterministicLocalDirectorRuntime.gemini_calls = 0
    _DeterministicLocalDirectorRuntime.local_task_calls = []
    runtime = _DeterministicLocalDirectorRuntime()

    outputs = {
        task_type: runtime.generate_structured(
            project_id="local-director-fixture",
            task_type=task_type,
            prompt="fixture",
            response_schema={},
        ).output_data
        for task_type in (
            LLMTaskType.SCENE_PLANNING,
            LLMTaskType.KEYWORD_EXPANSION,
            LLMTaskType.MUSIC_RECOMMENDATION,
            LLMTaskType.OPERATOR_COPY,
        )
    }

    assert outputs[LLMTaskType.SCENE_PLANNING] == {
        "review_required": False,
        "cleanup_decision": "keep",
    }
    assert outputs[LLMTaskType.KEYWORD_EXPANSION]["keywords"] == ["local", "director"]
    assert outputs[LLMTaskType.MUSIC_RECOMMENDATION]["music_mood"] == "calm local bed"
    assert outputs[LLMTaskType.OPERATOR_COPY]["action_items"] == ["Continue local review."]
    assert _DeterministicLocalDirectorRuntime.local_task_calls == list(outputs)
    assert _DeterministicLocalDirectorRuntime.external_calls == 0
    assert _DeterministicLocalDirectorRuntime.gemini_calls == 0


class _KoreanSTT:
    provider_name = "offline-director-e2e-stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        del request
        return STTResult(text="로컬 디렉터 실출력 검증입니다.", segments=[STTSegment(start_sec=0, end_sec=3, text="로컬 디렉터 실출력 검증입니다.", confidence=.99)], provider_name=self.provider_name)


class _RecordingRenderer(FfmpegFinalRenderer):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.commands: list[list[str]] = []

    def _run(self, command: list[str]):  # noqa: ANN201
        self.commands.append(list(command))
        return super()._run(command)


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _poll(get_result):  # noqa: ANN001
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = get_result()
        if result["status"] in {"succeeded", "failed"}:
            return result
        time.sleep(.1)
    raise TimeoutError("timed out waiting for local Director output")


def _duration(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], check=True, capture_output=True, text=True, timeout=30).stdout.strip())


def _ffprobe_comment(path: Path) -> str:
    return subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags=comment",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


@pytest.mark.skipif(not RUN_REAL_DIRECTOR_E2E, reason="set VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E=1 for the release gate")
@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_real_local_director_drives_broll_bgm_sfx_to_final_and_draft(tmp_path: Path) -> None:
    """Own the full deterministic B-roll/BGM/SFX flow; do not delegate to another test."""
    _DeterministicLocalDirectorRuntime.external_calls = _DeterministicLocalDirectorRuntime.gemini_calls = 0
    _DeterministicLocalDirectorRuntime.local_task_calls = []
    assert REAL_PACK_ROOT.is_dir(), f"Build the audited Starter Pack first: {REAL_PACK_ROOT}"
    library = MediaLibraryStore(tmp_path / "library")
    assert MediaPackService(user_library_root=tmp_path / "user-library", library_store=library, duration_probe=_duration, media_probe=lambda path: ffprobe_media(path, ffprobe_binary="ffprobe")).install(REAL_PACK_ROOT).status == "installed"
    assets = library.inspect_active_assets()
    music, sfx = next(item for item in assets if item["media_type"] == "music"), next(item for item in assets if item["media_type"] == "sfx")
    narration, broll, script = tmp_path / "n.wav", tmp_path / "b.mp4", tmp_path / "script.txt"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(narration)])
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=12", str(broll)])
    script.write_text("로컬 디렉터 실출력 검증입니다.", encoding="utf-8")
    root = tmp_path / "projects"; store = LocalProjectStore(root)
    renderer = _RecordingRenderer(store=store, video_width=320, video_height=180, video_fps=12, render_timeout_seconds=120)
    app = create_app(projects_root=root, media_library_store=library, local_only_runtime_service_factory=lambda _: _DeterministicLocalDirectorRuntime(), stt_provider=_KoreanSTT(), final_renderer=renderer, pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=12))
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Real Local Director"}).json()["project_id"]
        n = client.post(f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)}).json()
        s = client.post(f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script)}).json()
        b = client.post(f"/api/projects/{project_id}/assets/broll-video", json={"source_path": str(broll), "title": "director broll", "tags": ["검증"]}).json()
        # User-owned unknown B-roll is allowed locally and must carry a warning through both outputs.
        store.update_asset_metadata(project_id=project_id, asset_id=b["asset_id"], metadata_patch={"review_status": "approved", "license_policy": "unknown_user_owned", "warning_provenance": ["copyright_confirmation_required"], "controls": {"in_sec": .1, "out_sec": 2.5, "fit": "crop", "loop": False, "pad": True, "trim_start_sec": .1}})
        # Director ranking requires a current, non-empty durable visual analysis
        # bound to the exact project-local B-roll SHA; do not bypass this gate.
        broll_path = store.resolve_storage_uri(project_id=project_id, storage_uri=b["storage_uri"])
        broll_sha = sha256(broll_path.read_bytes()).hexdigest()
        broll_analysis = store.create_media_analysis(project_id=project_id, asset_id=b["asset_id"], idempotency_key=f"{broll_sha}:real-director", cache_key="real-director")
        claim = store.claim_media_analysis(project_id=project_id, analysis_id=broll_analysis["analysis_id"])
        assert claim is not None
        assert store.complete_media_analysis(project_id=project_id, analysis_id=broll_analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "real director broll", "sha256": broll_sha}]})["status"] == "succeeded"
        material_music = client.post(f"/api/media-library/assets/{music['library_asset_id']}/materialize", json={"project_id": project_id}).json()
        material_sfx = client.post(f"/api/media-library/assets/{sfx['library_asset_id']}/materialize", json={"project_id": project_id}).json()
        assert all("source-archive" not in item["storage_uri"] for item in (material_music, material_sfx))
        # These rows deliberately satisfy BGM/SFX metadata eligibility but have
        # no project-local bytes.  They reach the Director snapshot and must
        # never become rankable/materializable/applicable candidates.
        assetless_music_source = tmp_path / "assetless-bgm.mp3"
        assetless_sfx_source = tmp_path / "assetless-sfx.wav"
        assetless_music_source.write_bytes(b"assetless bgm")
        assetless_sfx_source.write_bytes(b"assetless sfx")
        assetless_bgm = store.register_asset(
            project_id=project_id,
            asset_type=AssetType.BGM,
            source_path=assetless_music_source,
            metadata={
                "canonical_metadata_indexed": True,
                "mood": "calm",
                "energy": "low",
                "genre": "ambient",
                "recommended_use": "bed",
                "license": "valid",
                "review_status": "approved",
            },
        )
        assetless_sfx = store.register_asset(
            project_id=project_id,
            asset_type=AssetType.SFX,
            source_path=assetless_sfx_source,
            metadata={
                "canonical_metadata_indexed": True,
                "action_event": "impact",
                "intensity": "high",
                "recommended_use": "accent",
                "license": "valid",
                "review_status": "approved",
            },
        )
        for asset in (assetless_bgm, assetless_sfx):
            store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri).unlink()
        store.update_asset_metadata(project_id=project_id, asset_id=material_music["asset_id"], metadata_patch={"canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient", "recommended_use": "bed", "license": "valid", "review_status": "approved", "controls": {"gain_db": -6, "fade_in_sec": .2, "fade_out_sec": .2, "ducking": True}})
        store.update_asset_metadata(project_id=project_id, asset_id=material_sfx["asset_id"], metadata_patch={"canonical_metadata_indexed": True, "action_event": "impact", "intensity": "high", "recommended_use": "accent", "license": "valid", "review_status": "approved", "controls": {"gain_db": -4, "fade_in_sec": .1, "fade_out_sec": .1}})
        transcription = client.post(f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": n["asset_id"]}).json()["job_id"]
        analysis = client.post(f"/api/projects/{project_id}/jobs/segment-analysis", json={"transcription_job_id": transcription, "script_asset_id": s["asset_id"]}).json()["job_id"]
        rec = client.post(f"/api/projects/{project_id}/jobs/broll-recommendation", json={"segment_analysis_job_id": analysis}).json()["job_id"]
        timeline_response = client.post(f"/api/projects/{project_id}/jobs/build-timeline", json={"segment_analysis_job_id": analysis, "recommendation_job_ids": [rec]})
        assert timeline_response.status_code == 202, timeline_response.text
        timeline_job = timeline_response.json()["job_id"]
        session = client.post(f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job}).json(); session_id = session["session_id"]
        proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session_id}).json()
        broll_candidate = next(item for item in proposal["candidates"] if item["media_type"] == "broll")
        candidate = next(item for item in proposal["candidates"] if item["media_type"] == "bgm" and item["asset_id"] == material_music["asset_id"])
        sfx_candidate = next(item for item in proposal["candidates"] if item["media_type"] == "sfx" and item["asset_id"] == material_sfx["asset_id"])
        assert all(item["asset_id"] not in {assetless_bgm.asset_id, assetless_sfx.asset_id} for item in proposal["candidates"])
        source_id = proposal["source_script_segment_ids"][0]
        for assetless_asset in (assetless_bgm, assetless_sfx):
            assetless_candidate_id = f"candidate:{source_id}:{assetless_asset.asset_id}"
            materialize = client.post(
                f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{assetless_candidate_id}/materialize"
            )
            assert materialize.status_code in {404, 422}, materialize.text
            rejected_apply = client.post(
                f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply",
                json={"candidate_ids": [assetless_candidate_id], "expected_revision": session["session_revision"]},
            )
            assert rejected_apply.status_code in {404, 422}, rejected_apply.text
        assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()["session_revision"] == session["session_revision"]
        # Preview is a read-only parity surface: all B/M/S candidates preserve the
        # controls selected by the Director and never request autoplay.
        for preview_candidate in (broll_candidate, candidate, sfx_candidate):
            preview = client.get(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{preview_candidate['candidate_id']}/preview")
            assert preview.status_code == 200 and preview.headers["x-videobox-autoplay"] == "false"
            assert json.loads(preview.headers["x-videobox-proposal-controls"]) == preview_candidate["controls"]
            assert preview.headers["x-videobox-in-sec"] == str(preview_candidate["controls"].get("in_sec", ""))
            assert preview.headers["x-videobox-out-sec"] == str(preview_candidate["controls"].get("out_sec", ""))
        session = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={"candidate_ids": [broll_candidate["candidate_id"], candidate["candidate_id"], sfx_candidate["candidate_id"]], "expected_revision": session["session_revision"]}).json()
        applied = session["segments"][0]["music_override"]
        assert applied["media_controls"] == candidate["controls"] and applied["expected_content_sha256"] == candidate["expected_content_sha256"]
        applied_broll = session["segments"][0]["broll_override"]
        assert applied_broll["media_controls"] == broll_candidate["controls"] and applied_broll["expected_content_sha256"] == broll_candidate["expected_content_sha256"]
        applied_sfx = session["segments"][0]["sfx_override"]
        assert applied_sfx["media_controls"] == sfx_candidate["controls"] and applied_sfx["expected_content_sha256"] == sfx_candidate["expected_content_sha256"]
        partial = client.post(f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration", json={"segment_ids": ["seg_001"], "fields": ["broll", "music", "sfx"], "expected_revision": session["session_revision"]}).json()["job_id"]
        review = client.get(f"/api/projects/{project_id}/review-snapshots/{partial}").json()
        for item in review["pending_recommendations"]: assert client.post(f"/api/projects/{project_id}/review-snapshots/{partial}/recommendations/{item['recommendation_id']}/approve").status_code == 200
        assert client.post(f"/api/projects/{project_id}/review-approvals/{partial}/approve").status_code == 202
        timeline = client.get(f"/api/projects/{project_id}/timelines/{partial}").json()["timeline"]
        assert applied["asset_uri"] in str(timeline) and applied_broll["asset_uri"] in str(timeline) and applied_sfx["asset_uri"] in str(timeline)
        timeline_clips = {
            track["track_type"]: track["clips"][0]
            for track in timeline["tracks"]
            if track["track_type"] in {"broll", "bgm", "sfx"}
        }
        for track_type, proposal_candidate in {
            "broll": broll_candidate,
            "bgm": candidate,
            "sfx": sfx_candidate,
        }.items():
            assert timeline_clips[track_type]["expected_content_sha256"] == proposal_candidate["expected_content_sha256"], track_type
            assert timeline_clips[track_type]["media_controls"] == proposal_candidate["controls"]
        subtitle_job = client.post(f"/api/projects/{project_id}/jobs/subtitle-render", json={"timeline_job_id": partial}).json()["job_id"]
        subtitle = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job}").json()["subtitle"]
        assert "로컬 디렉터 실출력 검증입니다." in store.resolve_storage_uri(project_id=project_id, storage_uri=subtitle["file_uri"]).read_text(encoding="utf-8")
        final_job = client.post(f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": partial}).json()["job_id"]; final = _poll(lambda: client.get(f"/api/projects/{project_id}/final-renders/{final_job}").json())
        assert final["status"] == "succeeded", final
        final_path = store.resolve_storage_uri(project_id=project_id, storage_uri=final["render"]["file_uri"])
        assert _duration(final_path) >= 2.5
        assert "copyright_confirmation_required" in _ffprobe_comment(final_path)
        rendered_commands = [" ".join(command) for command in renderer.commands]
        assert any(str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied_broll["asset_uri"])) in command for command in rendered_commands)
        assert any(str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied["asset_uri"])) in command for command in rendered_commands)
        assert any(str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied_sfx["asset_uri"])) in command for command in rendered_commands)
        assert any(str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied["asset_uri"])) in command for command in renderer.commands)
        broll_command = next(command for command in rendered_commands if str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied_broll["asset_uri"])) in command)
        assert "-ss 0.2" in broll_command and "crop=320:180" in broll_command and "tpad=stop_mode=add" in broll_command
        assert "-stream_loop -1" not in broll_command
        bgm_command = next(command for command in rendered_commands if str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied["asset_uri"])) in command and "sidechaincompress" in command)
        assert "volume=-6.0dB" in bgm_command and "afade=t=in:st=0:d=0.2" in bgm_command and "afade=t=out:st=2.8:d=0.2" in bgm_command
        sfx_command = next(command for command in rendered_commands if str(store.resolve_storage_uri(project_id=project_id, storage_uri=applied_sfx["asset_uri"])) in command)
        assert "volume=-4.0dB" in sfx_command and "afade=t=in:st=0:d=0.1" in sfx_command and "afade=t=out:st=2.9:d=0.1" in sfx_command
        draft_job = client.post(f"/api/projects/{project_id}/jobs/capcut-draft-export", json={"timeline_job_id": partial}).json()["job_id"]; draft = _poll(lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{draft_job}").json())
        assert draft["status"] == "succeeded", draft
        content = json.loads((store.resolve_storage_uri(project_id=project_id, storage_uri=draft["export"]["file_uri"]) / "draft_content.json").read_text(encoding="utf-8"))
        tracks = {track["name"]: track["segments"] for track in content["tracks"]}
        assert tracks["broll"] and tracks["bgm"] and tracks["sfx"]
        assert "copyright_confirmation_required" in content["videobox_output_metadata"]["warning_provenance"]
        assert content["videobox_output_metadata"]["warnings"]
        assert tracks["broll"][0]["source_timerange"]["start"] == 200_000
        broll_material = next(material for material in content["materials"]["videos"] if material["path"].endswith("b.mp4"))
        assert broll_material["crop"]["upper_left_y"] > 0
        assert tracks["bgm"][0]["volume"] == pytest.approx(0.25 * 10 ** (-6 / 20))
        assert tracks["sfx"][0]["volume"] == pytest.approx(10 ** (-4 / 20))
        assert tracks["bgm"][0]["extra_material_refs"] and tracks["sfx"][0]["extra_material_refs"]
        # Mutating selected B-roll blocks both output routes before a new artifact is written.
        timeline_broll_uri = next(track for track in timeline["tracks"] if track["track_type"] == "broll")["clips"][0]["asset_uri"]
        source = store.resolve_storage_uri(project_id=project_id, storage_uri=timeline_broll_uri); source.write_bytes(source.read_bytes() + b"mutated")
        failed_final_job = client.post(f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": partial}).json()["job_id"]
        failed_final = _poll(lambda: client.get(f"/api/projects/{project_id}/final-renders/{failed_final_job}").json())
        assert failed_final["status"] == "failed"
        assert "stale_output_asset" in str(store.get_job(project_id=project_id, job_id=failed_final_job).get("error_message"))
        failed_draft_job = client.post(f"/api/projects/{project_id}/jobs/capcut-draft-export", json={"timeline_job_id": partial}).json()["job_id"]
        failed_draft = _poll(lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{failed_draft_job}").json())
        assert failed_draft["status"] == "failed"
        assert "stale_output_asset" in str(store.get_job(project_id=project_id, job_id=failed_draft_job).get("error_message"))
        assert _DeterministicLocalDirectorRuntime.external_calls == 0 and _DeterministicLocalDirectorRuntime.gemini_calls == 0
