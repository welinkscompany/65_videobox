from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.settings import TTSEngineConfig


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
