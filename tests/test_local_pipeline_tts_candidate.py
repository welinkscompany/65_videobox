from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_provider_interfaces.tts import TTSRequest, TTSResult
from videobox_storage.local_project_store import LocalProjectStore


class _FakeTTSProvider:
    provider_name = "fake_tts"

    def __init__(self) -> None:
        self.received_requests: list[TTSRequest] = []

    def synthesize(self, request: TTSRequest) -> TTSResult:
        self.received_requests.append(request)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(b"fake synthesized audio")
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


def test_generate_tts_replacement_candidate_registers_a_generated_tts_asset(tmp_path: Path) -> None:
    voice_sample_path = tmp_path / "voice_sample.wav"
    voice_sample_path.write_bytes(b"fake voice sample bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="TTS Candidate Project")
    fake_provider = _FakeTTSProvider()
    runner = LocalPipelineRunner(store, tts_provider=fake_provider)

    voice_sample_asset = runner.register_voice_sample_asset(
        project_id=project.project_id, source_path=voice_sample_path
    )

    result = runner.generate_tts_replacement_candidate(
        project_id=project.project_id,
        segment_text="Hello there.",
        voice_sample_asset_id=voice_sample_asset["asset_id"],
    )

    assert result["asset_type"] == "generated_tts_audio"
    assert len(fake_provider.received_requests) == 1
    request = fake_provider.received_requests[0]
    assert request.text == "Hello there."
    assert request.voice_sample_uri.endswith("voice_sample.wav")

    resolved_output_path = store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=result["storage_uri"]
    )
    assert resolved_output_path.read_bytes() == b"fake synthesized audio"


def test_generate_tts_replacement_candidate_raises_clear_error_when_not_configured(tmp_path: Path) -> None:
    voice_sample_path = tmp_path / "voice_sample.wav"
    voice_sample_path.write_bytes(b"fake voice sample bytes")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="TTS Candidate Unconfigured Project")
    runner = LocalPipelineRunner(store)
    voice_sample_asset = runner.register_voice_sample_asset(
        project_id=project.project_id, source_path=voice_sample_path
    )

    with pytest.raises(RuntimeError, match="not configured"):
        runner.generate_tts_replacement_candidate(
            project_id=project.project_id,
            segment_text="Hello there.",
            voice_sample_asset_id=voice_sample_asset["asset_id"],
        )


def test_generate_tts_replacement_candidate_rejects_non_voice_sample_asset(tmp_path: Path) -> None:
    script_path = tmp_path / "script.txt"
    script_path.write_text("hello", encoding="utf-8")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="TTS Candidate Rejection Project")
    runner = LocalPipelineRunner(store, tts_provider=_FakeTTSProvider())
    script_asset = runner.register_script_asset(project_id=project.project_id, source_path=script_path)

    with pytest.raises(ValueError, match="voice_sample_audio"):
        runner.generate_tts_replacement_candidate(
            project_id=project.project_id,
            segment_text="Hello there.",
            voice_sample_asset_id=script_asset["asset_id"],
        )
