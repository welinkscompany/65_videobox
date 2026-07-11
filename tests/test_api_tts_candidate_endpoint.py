from __future__ import annotations

from pathlib import Path
import wave

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.settings import TTSEngineConfig
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


class _DeterministicWaveTTSProvider:
    provider_name = "deterministic_wave"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        with wave.open(str(request.output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(1000)
            wav_file.writeframes(b"\x01\x00" * 3000)
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


def test_tts_candidate_endpoint_produces_a_real_synthesized_audio_asset_end_to_end(tmp_path: Path) -> None:
    voice_sample_path = tmp_path / "voice_sample.wav"
    voice_sample_path.write_bytes(b"fake voice sample bytes")

    app = create_app(
        projects_root=tmp_path,
        tts_engine_config=TTSEngineConfig(enabled=True, engine="gtts", language="en"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "TTS Candidate Draft"}).json()["project_id"]

    voice_sample_asset_id = client.post(
        f"/api/projects/{project_id}/assets/voice-sample",
        json={"source_path": str(voice_sample_path)},
    ).json()["asset_id"]

    candidate_response = client.post(
        f"/api/projects/{project_id}/tts-candidates",
        json={
            "segment_text": "Hello from VideoBox.",
            "voice_sample_asset_id": voice_sample_asset_id,
        },
    )

    assert candidate_response.status_code == 201
    body = candidate_response.json()
    assert body["asset_type"] == "generated_tts_audio"

    relative_output_path = Path(body["storage_uri"].removeprefix(f"local://projects/{project_id}/"))
    resolved_output_path = tmp_path / "projects" / project_id / relative_output_path
    assert resolved_output_path.exists()
    assert resolved_output_path.stat().st_size > 0


def test_tts_candidates_accumulate_per_segment_for_ab_comparison(tmp_path: Path) -> None:
    voice_sample_path = tmp_path / "voice_sample.wav"
    voice_sample_path.write_bytes(b"fake voice sample bytes")

    app = create_app(
        projects_root=tmp_path,
        tts_engine_config=TTSEngineConfig(enabled=True, engine="gtts", language="en"),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "TTS AB Draft"}).json()["project_id"]

    voice_sample_asset_id = client.post(
        f"/api/projects/{project_id}/assets/voice-sample",
        json={"source_path": str(voice_sample_path)},
    ).json()["asset_id"]

    empty_list = client.get(f"/api/projects/{project_id}/segments/seg_001/tts-candidates")
    assert empty_list.status_code == 200
    assert empty_list.json()["candidates"] == []

    first = client.post(
        f"/api/projects/{project_id}/tts-candidates",
        json={
            "segment_text": "Hello from VideoBox, take one.",
            "voice_sample_asset_id": voice_sample_asset_id,
            "segment_id": "seg_001",
        },
    )
    second = client.post(
        f"/api/projects/{project_id}/tts-candidates",
        json={
            "segment_text": "Hello from VideoBox, take two.",
            "voice_sample_asset_id": voice_sample_asset_id,
            "segment_id": "seg_001",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    listed = client.get(f"/api/projects/{project_id}/segments/seg_001/tts-candidates")
    assert listed.status_code == 200
    candidates = listed.json()["candidates"]
    assert len(candidates) == 2
    assert candidates[0]["asset_id"] == first.json()["asset_id"]
    assert candidates[1]["asset_id"] == second.json()["asset_id"]
    assert candidates[0]["source_text"] == "Hello from VideoBox, take one."
    assert candidates[1]["source_text"] == "Hello from VideoBox, take two."

    other_segment_list = client.get(f"/api/projects/{project_id}/segments/seg_002/tts-candidates")
    assert other_segment_list.json()["candidates"] == []

    content_response = client.get(
        f"/api/projects/{project_id}/assets/{first.json()['asset_id']}/content"
    )
    assert content_response.status_code == 200
    assert len(content_response.content) > 0


def test_tts_candidate_endpoint_serializes_pending_operator_review_with_fake_provider(tmp_path: Path) -> None:
    voice_sample_path = tmp_path / "voice_sample.wav"
    voice_sample_path.write_bytes(b"fake voice sample bytes")
    app = create_app(projects_root=tmp_path, tts_provider=_DeterministicWaveTTSProvider())
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "TTS Acceptance"}).json()["project_id"]
    voice_sample_asset_id = client.post(
        f"/api/projects/{project_id}/assets/voice-sample",
        json={"source_path": str(voice_sample_path)},
    ).json()["asset_id"]

    response = client.post(
        f"/api/projects/{project_id}/tts-candidates",
        json={
            "segment_text": "안녕하세요.",
            "voice_sample_asset_id": voice_sample_asset_id,
            "segment_id": "seg_001",
            "target_duration_sec": 3.0,
        },
    )

    assert response.status_code == 201
    assert response.json()["technical_status"] == "accepted"
    assert response.json()["operator_review_status"] == "pending"
