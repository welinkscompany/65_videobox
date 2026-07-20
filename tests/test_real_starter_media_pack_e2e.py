from __future__ import annotations

"""Explicit release gate for the ignored, real Starter Media Pack output.

This intentionally remains opt-in: it installs and copies the 470MiB release
pack.  CI/unit runs must not silently pay that cost, while release closeout
must run this test with ``VIDEOBOX_RUN_REAL_STARTER_PACK_E2E=1``.
"""

import os
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_pack_release import ffprobe_media
from videobox_core_engine.media_pack_service import MediaPackService
from videobox_provider_interfaces.llm import LLMTaskType, StructuredLLMResponse
from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REAL_PACK_ROOT = REPOSITORY_ROOT / "dist" / "starter-media-pack"
RUN_REAL_PACK_E2E = os.environ.get("VIDEOBOX_RUN_REAL_STARTER_PACK_E2E") == "1"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class _DeterministicOfflineRuntime:
    external_provider_calls = 0

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
        output_data = {
            LLMTaskType.SCENE_PLANNING: {"review_required": False, "cleanup_decision": "keep"},
            LLMTaskType.KEYWORD_EXPANSION: {"keywords": ["starter", "pack"]},
            LLMTaskType.MUSIC_RECOMMENDATION: {"music_mood": "calm local bed", "score": 0.75},
            LLMTaskType.OPERATOR_COPY: {"summary": "Local starter-pack guidance.", "action_items": ["Continue local review."]},
        }[task_type]
        return StructuredLLMResponse(
            provider_name="deterministic_local_fixture",
            model_name="fixture",
            output_data=output_data,
            raw_text=json.dumps(output_data),
            metadata={"provider_trace": {"routing_mode": "local_only", "final_provider": "deterministic_local_fixture", "fallback_reasons": []}},
        )


def test_offline_runtime_returns_local_structured_responses_without_external_calls() -> None:
    _DeterministicOfflineRuntime.external_provider_calls = 0
    runtime = _DeterministicOfflineRuntime()

    outputs = {
        task_type: runtime.generate_structured(
            project_id="starter-pack-fixture",
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

    assert outputs[LLMTaskType.SCENE_PLANNING]["review_required"] is False
    assert outputs[LLMTaskType.KEYWORD_EXPANSION]["keywords"] == ["starter", "pack"]
    assert outputs[LLMTaskType.MUSIC_RECOMMENDATION]["music_mood"] == "calm local bed"
    assert outputs[LLMTaskType.OPERATOR_COPY]["summary"] == "Local starter-pack guidance."
    assert _DeterministicOfflineRuntime.external_provider_calls == 0


class _DeterministicSTT:
    provider_name = "deterministic_real_pack_e2e_stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        del request
        return STTResult(
            text="실물 스타터 미디어팩 최종 출력 검증입니다.",
            segments=[
                STTSegment(
                    start_sec=0.0,
                    end_sec=3.0,
                    text="실물 스타터 미디어팩 최종 출력 검증입니다.",
                    confidence=0.99,
                )
            ],
            provider_name=self.provider_name,
        )


class _RecordingRenderer(FfmpegFinalRenderer):
    """Keeps the real renderer while exposing the exact FFmpeg input contract."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.commands: list[list[str]] = []

    def _run(self, command: list[str]):  # noqa: ANN201
        self.commands.append(list(command))
        return super()._run(command)


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return float(result.stdout.strip())


def _probe_audio_stream_count(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return sum(1 for stream in json.loads(result.stdout)["streams"] if stream["codec_type"] == "audio")


def _poll(get_result, *, timeout_seconds: float = 60.0):  # noqa: ANN001
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = get_result()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for real Starter Media Pack E2E output.")


@pytest.mark.skipif(not RUN_REAL_PACK_E2E, reason="explicit release gate; set VIDEOBOX_RUN_REAL_STARTER_PACK_E2E=1")
@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_real_starter_media_pack_flows_to_final_mp4_and_real_capcut_draft(tmp_path: Path) -> None:
    _DeterministicOfflineRuntime.external_provider_calls = 0
    """Use real release bytes end-to-end; source archives must never become media."""
    assert REAL_PACK_ROOT.is_dir(), f"Build the real pack first: {REAL_PACK_ROOT}"
    library = MediaLibraryStore(tmp_path / "library")
    install = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=library,
        duration_probe=_probe_duration,
        media_probe=lambda path: ffprobe_media(path, ffprobe_binary="ffprobe"),
    ).install(REAL_PACK_ROOT)
    assert install.status == "installed"

    listed = library.inspect_active_assets()
    assert len(listed) == 130
    assert {asset["media_type"] for asset in listed} == {"music", "sfx"}
    assert all("source-archive" not in str(asset["path"]).replace("\\", "/") for asset in listed)
    music = next(asset for asset in listed if asset["media_type"] == "music")
    sfx = next(asset for asset in listed if asset["media_type"] == "sfx")

    narration = tmp_path / "narration.wav"
    broll = tmp_path / "broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(narration)])
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=12", str(broll),
    ])
    script = tmp_path / "script.txt"
    script.write_text("실물 스타터 미디어팩 최종 출력 검증입니다.", encoding="utf-8")

    projects_root = tmp_path / "projects"
    store = LocalProjectStore(projects_root)
    renderer = _RecordingRenderer(
        store=store, video_width=320, video_height=180, video_fps=12, render_timeout_seconds=120,
    )
    app = create_app(
        projects_root=projects_root,
        media_library_store=library,
        local_only_runtime_service_factory=lambda _: _DeterministicOfflineRuntime(),
        stt_provider=_DeterministicSTT(),
        final_renderer=renderer,
        pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=12),
    )
    with TestClient(app) as client:
        listed_response = client.get("/api/media-library/assets")
        assert listed_response.status_code == 200
        assert music["library_asset_id"] in {item["library_asset_id"] for item in listed_response.json()["assets"]}
        assert client.put(f"/api/media-library/assets/{music['library_asset_id']}/favorite", json={"enabled": True}).status_code == 200
        assert client.get("/api/media-library/favorites").json()["asset_ids"] == [music["library_asset_id"]]

        project_id = client.post("/api/projects", json={"name": "Real Starter Media Pack E2E"}).json()["project_id"]
        narration_asset = client.post(
            f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)}
        ).json()
        script_asset = client.post(
            f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script)}
        ).json()
        assert client.post(
            f"/api/projects/{project_id}/assets/broll-video",
            json={"source_path": str(broll), "title": "real pack broll", "tags": ["검증"]},
        ).status_code == 201
        materialized_music = client.post(
            f"/api/media-library/assets/{music['library_asset_id']}/materialize", json={"project_id": project_id}
        ).json()
        materialized_sfx = client.post(
            f"/api/media-library/assets/{sfx['library_asset_id']}/materialize", json={"project_id": project_id}
        ).json()
        assert music["asset_id"] in materialized_music["storage_uri"]
        assert sfx["asset_id"] in materialized_sfx["storage_uri"]
        assert "source-archive" not in materialized_music["storage_uri"]
        assert "source-archive" not in materialized_sfx["storage_uri"]

        transcription = client.post(
            f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": narration_asset["asset_id"]}
        ).json()
        analysis = client.post(
            f"/api/projects/{project_id}/jobs/segment-analysis",
            json={"transcription_job_id": transcription["job_id"], "script_asset_id": script_asset["asset_id"]},
        ).json()
        broll_recommendation = client.post(
            f"/api/projects/{project_id}/jobs/broll-recommendation", json={"segment_analysis_job_id": analysis["job_id"]}
        ).json()
        timeline_job_id = client.post(
            f"/api/projects/{project_id}/jobs/build-timeline",
            json={"segment_analysis_job_id": analysis["job_id"], "recommendation_job_ids": [broll_recommendation["job_id"]]},
        ).json()["job_id"]
        session = client.post(
            f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job_id}
        ).json()
        session_id = session["session_id"]
        # Give the real, project-local media-pack copy the director metadata
        # required by the proposal picker.  This makes the release gate cover
        # the immutable materialize -> apply path, not merely the legacy
        # manual music selector.
        store.update_asset_metadata(
            project_id=project_id,
            asset_id=materialized_music["asset_id"],
            metadata_patch={
                "canonical_metadata_indexed": True,
                "mood": "calm",
                "energy": "low",
                "genre": "ambient",
                "recommended_use": "bed",
                "license": "valid",
                "review_status": "approved",
            },
        )
        proposal_response = client.post(
            f"/api/projects/{project_id}/director/proposals", json={"session_id": session_id}
        )
        assert proposal_response.status_code == 201, proposal_response.text
        proposal = proposal_response.json()
        candidate = next(
            item
            for item in proposal["candidates"]
            if item["media_type"] == "bgm" and item["asset_id"] == materialized_music["asset_id"]
        )
        applied_materialized = client.post(
            f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize"
        )
        assert applied_materialized.status_code == 201, applied_materialized.text
        apply_response = client.post(
            f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply",
            json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]},
        )
        assert apply_response.status_code == 200, apply_response.text
        session = apply_response.json()
        applied_music = session["segments"][0]["music_override"]
        assert applied_music["asset_id"] == applied_materialized.json()["asset_id"]
        assert applied_music["media_controls"] == candidate["controls"]
        assert applied_music["expected_content_sha256"] == candidate["expected_content_sha256"]
        session = client.patch(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/sfx",
            json={"asset_id": materialized_sfx["asset_id"], "expected_revision": session["session_revision"]},
        ).json()
        partial_job_id = client.post(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
            json={"segment_ids": ["seg_001"], "fields": ["music", "sfx"], "expected_revision": session["session_revision"]},
        ).json()["job_id"]
        review = client.get(f"/api/projects/{project_id}/review-snapshots/{partial_job_id}").json()
        sfx_recommendation = next(
            item["recommendation_id"] for item in review["pending_recommendations"] if item["recommendation_type"] == "sfx"
        )
        assert client.post(
            f"/api/projects/{project_id}/review-snapshots/{partial_job_id}/recommendations/{sfx_recommendation}/approve"
        ).status_code == 200
        assert client.post(f"/api/projects/{project_id}/review-approvals/{partial_job_id}/approve").status_code == 202
        timeline = client.get(f"/api/projects/{project_id}/timelines/{partial_job_id}").json()["timeline"]
        timeline_text = str(timeline)
        assert applied_materialized.json()["storage_uri"] in timeline_text
        assert materialized_sfx["storage_uri"] in timeline_text
        assert "source-archive" not in timeline_text

        subtitle_job_id = client.post(
            f"/api/projects/{project_id}/jobs/subtitle-render", json={"timeline_job_id": partial_job_id}
        ).json()["job_id"]
        subtitle = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job_id}").json()
        assert subtitle["subtitle"]["file_uri"].endswith(".srt")
        subtitle_path = store.resolve_storage_uri(project_id=project_id, storage_uri=subtitle["subtitle"]["file_uri"])
        assert subtitle_path.is_file()
        assert "실물 스타터 미디어팩 최종 출력 검증입니다." in subtitle_path.read_text(encoding="utf-8")
        final_job_id = client.post(
            f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": partial_job_id}
        ).json()["job_id"]
        final = _poll(lambda: client.get(f"/api/projects/{project_id}/final-renders/{final_job_id}").json())
        assert final["status"] == "succeeded", (final, store.get_job(project_id=project_id, job_id=final_job_id))
        final_path = store.resolve_storage_uri(project_id=project_id, storage_uri=final["render"]["file_uri"])
        assert final_path.is_file() and final_path.stat().st_size > 0
        assert _probe_duration(final_path) >= 2.5
        assert _probe_audio_stream_count(final_path) == 1
        materialized_music_path = str(
            store.resolve_storage_uri(project_id=project_id, storage_uri=applied_materialized.json()["storage_uri"])
        )
        materialized_sfx_path = str(
            store.resolve_storage_uri(project_id=project_id, storage_uri=materialized_sfx["storage_uri"])
        )
        assert any(materialized_music_path in command for command in renderer.commands)
        assert any(materialized_sfx_path in command for command in renderer.commands)
        assert any(
            f"volume={candidate['controls']['gain_db']}dB" in " ".join(command)
            for command in renderer.commands
        )
        capcut_job_id = client.post(
            f"/api/projects/{project_id}/jobs/capcut-draft-export", json={"timeline_job_id": partial_job_id}
        ).json()["job_id"]
        capcut = _poll(lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{capcut_job_id}").json())
        assert capcut["status"] == "succeeded", capcut
        draft_root = store.resolve_storage_uri(project_id=project_id, storage_uri=capcut["export"]["file_uri"])
        draft_content = (draft_root / "draft_content.json").read_text(encoding="utf-8")
        draft_json = json.loads(draft_content)
        draft_tracks = {track["name"]: track["segments"] for track in draft_json["tracks"]}
        assert Path(applied_materialized.json()["storage_uri"]).name in draft_content
        assert Path(materialized_sfx["storage_uri"]).name in draft_content
        assert draft_tracks["bgm"][0]["volume"] == pytest.approx(
            0.25 * 10 ** (float(candidate["controls"]["gain_db"]) / 20)
        )
        assert "source-archive" not in draft_content
        # Mutating the exact project-local applied file must fail closed before
        # either output entrypoint writes a new artifact.  Recovery must not
        # repair those bytes in place: it has to rematerialize from the still
        # verified library copy, apply a new proposal revision, then rebuild
        # the affected review/subtitle outputs before export is current again.
        applied_music_path = store.resolve_storage_uri(
            project_id=project_id, storage_uri=applied_materialized.json()["storage_uri"]
        )
        original_music_bytes = applied_music_path.read_bytes()
        applied_music_path.write_bytes(original_music_bytes + b"real-pack-stale-mutation")
        final_before = len(list((store.project_root(project_id) / "exports" / "final_render").glob("*")))
        capcut_before = len(list((store.project_root(project_id) / "exports" / "capcut_draft").glob("*")))
        failed_final_job = client.post(
            f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": partial_job_id}
        ).json()["job_id"]
        failed_final = _poll(lambda: client.get(f"/api/projects/{project_id}/final-renders/{failed_final_job}").json())
        assert failed_final["status"] == "failed"
        assert "stale_output_asset" in str(store.get_job(project_id=project_id, job_id=failed_final_job)["error_message"])
        failed_capcut_job = client.post(
            f"/api/projects/{project_id}/jobs/capcut-draft-export", json={"timeline_job_id": partial_job_id}
        ).json()["job_id"]
        failed_capcut = _poll(lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{failed_capcut_job}").json())
        assert failed_capcut["status"] == "failed"
        assert "stale_output_asset" in str(failed_capcut["error_message"])
        assert len(list((store.project_root(project_id) / "exports" / "final_render").glob("*"))) == final_before
        assert len(list((store.project_root(project_id) / "exports" / "capcut_draft").glob("*"))) == capcut_before

        recovery_proposal_response = client.post(
            f"/api/projects/{project_id}/director/proposals", json={"session_id": session_id}
        )
        assert recovery_proposal_response.status_code == 201, recovery_proposal_response.text
        recovery_proposal = recovery_proposal_response.json()
        recovery_candidate = next(
            item
            for item in recovery_proposal["candidates"]
            if item["media_type"] == "bgm" and item["asset_id"] == materialized_music["asset_id"]
        )
        recovery_materialized_response = client.post(
            f"/api/projects/{project_id}/director/proposals/{recovery_proposal['proposal_id']}"
            f"/candidates/{recovery_candidate['candidate_id']}/materialize"
        )
        assert recovery_materialized_response.status_code == 201, recovery_materialized_response.text
        recovery_materialized = recovery_materialized_response.json()
        assert recovery_materialized["asset_id"] != applied_materialized.json()["asset_id"]
        assert recovery_materialized["metadata"]["director_materialized_asset_index_revision"] == store.get_asset_index_revision(project_id)
        recovery_apply_response = client.post(
            f"/api/projects/{project_id}/director/proposals/{recovery_proposal['proposal_id']}/apply",
            json={"candidate_ids": [recovery_candidate["candidate_id"]], "expected_revision": recovery_proposal["base_session_revision"]},
        )
        assert recovery_apply_response.status_code == 200, recovery_apply_response.text
        recovered_session = recovery_apply_response.json()
        recovered_music = recovered_session["segments"][0]["music_override"]
        assert recovered_music["asset_id"] == recovery_materialized["asset_id"]
        assert recovered_music["media_controls"] == recovery_candidate["controls"]
        assert recovered_music["expected_content_sha256"] == recovery_candidate["expected_content_sha256"]

        recovery_partial_job_id = client.post(
            f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
            json={
                "segment_ids": ["seg_001"],
                "fields": ["music"],
                "expected_revision": recovered_session["session_revision"],
            },
        ).json()["job_id"]
        recovery_review = client.get(f"/api/projects/{project_id}/review-snapshots/{recovery_partial_job_id}").json()
        for recommendation in recovery_review["pending_recommendations"]:
            response = client.post(
                f"/api/projects/{project_id}/review-snapshots/{recovery_partial_job_id}"
                f"/recommendations/{recommendation['recommendation_id']}/approve"
            )
            assert response.status_code == 200, response.text
        assert client.post(f"/api/projects/{project_id}/review-approvals/{recovery_partial_job_id}/approve").status_code == 202
        recovery_subtitle_job_id = client.post(
            f"/api/projects/{project_id}/jobs/subtitle-render", json={"timeline_job_id": recovery_partial_job_id}
        ).json()["job_id"]
        recovery_subtitle = client.get(f"/api/projects/{project_id}/subtitles/{recovery_subtitle_job_id}").json()
        assert recovery_subtitle["subtitle"]["is_current"] is True
        recovered_final_job = client.post(
            f"/api/projects/{project_id}/jobs/final-render", json={"timeline_job_id": recovery_partial_job_id}
        ).json()["job_id"]
        recovered_final = _poll(lambda: client.get(f"/api/projects/{project_id}/final-renders/{recovered_final_job}").json())
        assert recovered_final["status"] == "succeeded"
        assert recovered_final["render"]["is_current"] is True
        recovered_capcut_job = client.post(
            f"/api/projects/{project_id}/jobs/capcut-draft-export", json={"timeline_job_id": recovery_partial_job_id}
        ).json()["job_id"]
        recovered_capcut = _poll(lambda: client.get(f"/api/projects/{project_id}/capcut-draft-exports/{recovered_capcut_job}").json())
        assert recovered_capcut["status"] == "succeeded"
        assert recovered_capcut["export"]["is_current"] is True
        recovered_draft_root = store.resolve_storage_uri(project_id=project_id, storage_uri=recovered_capcut["export"]["file_uri"])
        recovered_draft_content = (recovered_draft_root / "draft_content.json").read_text(encoding="utf-8")
        recovered_draft_json = json.loads(recovered_draft_content)
        recovered_draft_tracks = {track["name"]: track["segments"] for track in recovered_draft_json["tracks"]}
        assert Path(recovery_materialized["storage_uri"]).name in recovered_draft_content
        assert recovered_draft_tracks["bgm"][0]["volume"] == pytest.approx(
            0.25 * 10 ** (float(recovery_candidate["controls"]["gain_db"]) / 20)
        )
        # This release gate is offline by construction. Any provider invocation
        # would be both a policy violation and a deterministic test failure.
        assert _DeterministicOfflineRuntime.external_provider_calls == 0
