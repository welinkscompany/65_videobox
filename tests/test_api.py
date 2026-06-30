from __future__ import annotations

from dataclasses import dataclass, field
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.orchestration import LocalFirstRuntimeService
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.settings import AutoCutConfig, LocalOpenAICompatibleRuntimeConfig
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)
from videobox_provider_interfaces.stt import STTResult, STTSegment
from videobox_storage.local_project_store import LocalProjectStore


@dataclass
class FakeStructuredProvider:
    responses: list[StructuredLLMResponse] = field(default_factory=list)
    errors: list[Exception] = field(default_factory=list)
    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if self.errors:
            raise self.errors.pop(0)
        if self.responses:
            return self.responses.pop(0)
        raise AssertionError("No fake structured response configured.")


class FailingSegmentAnalyzer:
    def analyze(
        self,
        *,
        project_id: str,
        transcript_segments: list[dict[str, object]],
        script_text: str | None,
    ) -> list[dict[str, object]]:
        del project_id, transcript_segments, script_text
        raise LocalFirstStructuredGenerationError(
            message="segment provider failed",
            error_code="SEGMENT_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="local_qwen",
                fallback_reasons=["local_provider_error"],
            ),
        )


class FailingBrollRecommender:
    def recommend(self, request):  # noqa: ANN001
        del request
        raise LocalFirstStructuredGenerationError(
            message="broll Gemini fallback failed",
            error_code="BROLL_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        )


class FailingMusicRecommenderWithoutTrace:
    def recommend(self, request):  # noqa: ANN001
        del request
        raise RuntimeError("music provider exploded without trace")


class FailingOutputOperatorCopyBuilder:
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, object],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> dict[str, object]:
        del project_id, timeline, subtitle_file_uri
        raise LocalFirstStructuredGenerationError(
            message=f"{output_target} provider failed",
            error_code="OUTPUT_PROVIDER_FAILED",
            provider_name="local_first_router",
            provider_trace=build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        )


def _single_segment_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Office overview.",
                confidence=0.99,
            )
        ],
        provider_name="mock_stt",
    )


def _risky_multi_segment_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview. Team meeting restart.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Office overview.",
                confidence=0.99,
            ),
            STTSegment(
                start_sec=1.0,
                end_sec=2.0,
                text="Team meeting restart.",
                confidence=0.72,
            ),
        ],
        provider_name="mock_stt",
    )


def _split_script_line_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview intro. Team update starts.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=0.8,
                text="Office over",
                confidence=0.98,
            ),
            STTSegment(
                start_sec=0.8,
                end_sec=1.6,
                text="view intro",
                confidence=0.97,
            ),
            STTSegment(
                start_sec=1.6,
                end_sec=3.0,
                text="Team update starts.",
                confidence=0.96,
            ),
        ],
        provider_name="mock_stt",
    )


def _coarse_multi_sentence_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Office overview intro. Team update starts.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=3.0,
                text="Office overview intro. Team update starts.",
                confidence=0.98,
            ),
        ],
        provider_name="mock_stt",
    )


def _direction_mismatch_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Turn left now.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Turn left now.",
                confidence=0.99,
            ),
        ],
        provider_name="mock_stt",
    )


def _high_similarity_word_substitution_transcribe(self, request):  # noqa: ANN001
    return STTResult(
        text="Send the file today.",
        segments=[
            STTSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="Send the file today.",
                confidence=0.99,
            ),
        ],
        provider_name="mock_stt",
    )


def _create_segment_analysis_project(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    source_audio = tmp_path / "segment-runtime.wav"
    source_script = tmp_path / "segment-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")

    project_id = client.post("/api/projects", json={"name": "AI Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    return project_id, script_asset_id, transcription_job_id


def _local_first_service_factory(
    *,
    local_provider: FakeStructuredProvider,
    gemini_provider: FakeStructuredProvider,
    local_enabled: bool = True,
):
    def factory(store: LocalProjectStore) -> LocalFirstRuntimeService:
        return LocalFirstRuntimeService(
            store=store,
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_config=LLMProviderConfig(provider_name="local_qwen", enabled=local_enabled),
            gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
            local_runtime_config=LocalOpenAICompatibleRuntimeConfig(
                enabled=local_enabled,
                base_url="http://127.0.0.1:11434/v1",
                model_name="Qwen3-32B",
                timeout_seconds=42,
            ),
        )

    return factory


def _create_broll_recommendation_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "broll-runtime.wav"
    source_script = tmp_path / "broll-runtime.txt"
    broll_asset = tmp_path / "skyline.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")
    broll_asset.write_bytes(b"video bytes")

    project_id = client.post("/api/projects", json={"name": "AI Broll Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]
    return project_id, segment_job_id


def _create_music_recommendation_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "music-runtime.wav"
    source_script = tmp_path / "music-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")

    project_id = client.post("/api/projects", json={"name": "AI Music Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]
    return project_id, segment_job_id


def _create_timeline_review_project(
    client: TestClient,
    tmp_path: Path,
    *,
    gemini_key_payload: dict[str, str] | None = None,
) -> tuple[str, str]:
    source_audio = tmp_path / "review-runtime.wav"
    source_script = tmp_path / "review-runtime.txt"
    broll_asset = tmp_path / "review-runtime.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n", encoding="utf-8")
    broll_asset.write_bytes(b"video bytes")

    project_id = client.post("/api/projects", json={"name": "AI Review Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    if gemini_key_payload is not None:
        key_response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json=gemini_key_payload,
        )
        assert key_response.status_code == 201
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]
    return project_id, timeline_job_id


def test_health_endpoint_reports_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_app_exposes_local_runtime_builder_on_app_state(tmp_path: Path) -> None:
    config = LocalOpenAICompatibleRuntimeConfig(
        enabled=True,
        base_url="http://127.0.0.1:11434/v1/",
        model_name="Qwen3-32B",
        timeout_seconds=42,
    )

    app = create_app(projects_root=tmp_path, local_runtime_config=config)

    assert app.state.local_runtime_config.base_url == "http://127.0.0.1:11434/v1"
    assert app.state.local_runtime_config.model_name == "Qwen3-32B"
    assert callable(app.state.build_local_first_runtime_service)


def test_project_creation_endpoint_returns_local_storage_metadata(tmp_path) -> None:
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)

    response = client.post("/api/projects", json={"name": "Narration Draft"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Narration Draft"
    assert payload["root_storage_uri"].startswith("local://projects/")


def test_ingest_and_analysis_flow_persists_files_and_records(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Line one.\n\nLine two with restart.\n", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_response = client.post("/api/projects", json={"name": "Narration Draft"})
    project_id = project_response.json()["project_id"]

    narration_response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    )
    script_response = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    )

    assert narration_response.status_code == 201
    assert script_response.status_code == 201
    narration_asset_id = narration_response.json()["asset_id"]
    script_asset_id = script_response.json()["asset_id"]

    transcription_response = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    )
    assert transcription_response.status_code == 202
    transcription_job_id = transcription_response.json()["job_id"]

    transcription_result_response = client.get(
        f"/api/projects/{project_id}/jobs/transcription/{transcription_job_id}"
    )
    assert transcription_result_response.status_code == 200
    transcription_payload = transcription_result_response.json()
    assert transcription_payload["status"] == "succeeded"
    assert transcription_payload["transcript_uri"].startswith(
        f"local://projects/{project_id}/analysis/transcripts/"
    )

    segment_response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )
    assert segment_response.status_code == 202
    segment_job_id = segment_response.json()["job_id"]

    segment_result_response = client.get(
        f"/api/projects/{project_id}/jobs/segment-analysis/{segment_job_id}"
    )
    assert segment_result_response.status_code == 200
    segment_payload = segment_result_response.json()
    assert segment_payload["status"] == "succeeded"
    assert len(segment_payload["segments"]) >= 2
    assert any(segment["review_required"] for segment in segment_payload["segments"])

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "inputs" / "narration" / source_audio.name).read_bytes() == b"fake wav data"
    assert (
        project_root / "inputs" / "scripts" / source_script.name
    ).read_text(encoding="utf-8") == "Line one.\n\nLine two with restart.\n"

    transcript_files = list((project_root / "analysis" / "transcripts").glob("*.json"))
    assert transcript_files
    transcript_payload = json.loads(transcript_files[0].read_text(encoding="utf-8"))
    assert transcript_payload["source_asset_id"] == narration_asset_id

    segment_files = list((project_root / "analysis" / "segments").glob("*.json"))
    assert segment_files
    persisted_segments = json.loads(segment_files[0].read_text(encoding="utf-8"))
    assert persisted_segments["script_asset_id"] == script_asset_id


def test_segment_analysis_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 1
    assert gemini_provider.calls == []


def test_segment_analysis_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    key_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Fallback Gemini",
            "api_key": "AIza-segment-fallback",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert key_response.status_code == 201

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 1
    assert len(gemini_provider.calls) == 1


def test_segment_analysis_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    key_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Disabled Local Gemini",
            "api_key": "AIza-segment-disabled",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert key_response.status_code == 201

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is False
    assert segment["cleanup_decision"] == "keep"
    assert segment["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 1


def test_segment_analysis_endpoint_preserves_heuristic_fallback_when_local_disabled_without_gemini_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["review_required"] is False
    assert segment["cleanup_decision"] == "keep"


def test_segment_analysis_endpoint_marks_job_failed_on_unexpected_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(errors=[RuntimeError("segment analyzer exploded")])
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "segment analyzer exploded"
    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    assert jobs_response.status_code == 200
    segment_jobs = [
        job for job in jobs_response.json()["jobs"]
        if job["job_type"] == "segment_analysis"
    ]
    assert len(segment_jobs) == 1
    assert segment_jobs[0]["status"] == "failed"
    assert segment_jobs[0]["error_message"] == "segment analyzer exploded"
    assert len(local_provider.calls) == 1
    assert gemini_provider.calls == []


def test_segment_analysis_endpoint_uses_transcript_alignment_before_heuristic_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime.wav"
    source_script = tmp_path / "aligned-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro.\n\nTeam update starts.\n", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Aligned Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)
    assert all(segment["cleanup_decision"] == "keep" for segment in segments)


def test_segment_analysis_endpoint_flags_review_when_script_meaning_differs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _direction_mismatch_transcribe,
    )
    source_audio = tmp_path / "mismatch-runtime.wav"
    source_script = tmp_path / "mismatch-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Turn right now.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Mismatch Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["text"] == "Turn left now."
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"


def test_segment_analysis_endpoint_flags_review_for_high_similarity_word_substitution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _high_similarity_word_substitution_transcribe,
    )
    source_audio = tmp_path / "near-match-runtime.wav"
    source_script = tmp_path / "near-match-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Send the final today.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Near Match Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segment = result.json()["segments"][0]
    assert segment["text"] == "Send the file today."
    assert segment["review_required"] is True
    assert segment["cleanup_decision"] == "review"


def test_segment_analysis_endpoint_aligns_single_line_multi_sentence_script_without_false_review_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-single-line.wav"
    source_script = tmp_path / "aligned-runtime-single-line.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro. Team update starts.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Aligned Single Line Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)
    assert all(segment["cleanup_decision"] == "keep" for segment in segments)


def test_segment_analysis_endpoint_preserves_transcript_when_script_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-no-script.wav"
    source_audio.write_bytes(b"fake wav data")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Missing Script Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": None,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office over",
        "view intro",
        "Team update starts.",
    ]


def test_segment_analysis_endpoint_keeps_spoken_words_when_script_is_only_partial_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _split_script_line_transcribe,
    )
    source_audio = tmp_path / "aligned-runtime-partial-script.wav"
    source_script = tmp_path / "aligned-runtime-partial-script.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Partial Script Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office over view intro",
        "Team update starts.",
    ]


def test_segment_analysis_endpoint_splits_coarse_transcript_segment_for_multi_sentence_script(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _coarse_multi_sentence_transcribe,
    )
    source_audio = tmp_path / "coarse-runtime.wav"
    source_script = tmp_path / "coarse-runtime.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro. Team update starts.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Coarse Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)


def test_segment_analysis_endpoint_splits_coarse_transcript_segment_when_script_is_partial(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _coarse_multi_sentence_transcribe,
    )
    source_audio = tmp_path / "coarse-runtime-partial.wav"
    source_script = tmp_path / "coarse-runtime-partial.txt"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview intro.", encoding="utf-8")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Coarse Partial Segment Draft"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert [segment["text"] for segment in segments] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert all(segment["review_required"] is False for segment in segments)


def test_segment_analysis_keeps_heuristic_review_flags_when_ai_downplays_risky_segment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _risky_multi_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/segment-analysis/{response.json()['job_id']}")
    assert result.status_code == 200
    segments = result.json()["segments"]
    assert segments[0]["review_required"] is False
    assert segments[0]["cleanup_decision"] == "keep"
    assert segments[1]["review_required"] is True
    assert segments[1]["cleanup_decision"] == "review"


def test_segment_analysis_local_first_path_preserves_downstream_timeline_review_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Review the flagged narration segment before export.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Review the flagged narration segment before export.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    broll_asset = tmp_path / "segment-downstream.mp4"
    broll_asset.write_bytes(b"video bytes")
    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    assert asset_response.status_code == 201

    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    assert any(flag["code"] == "segment_review_required" for flag in review_snapshot.json()["review_flags"])
    assert len(local_provider.calls) >= 2


def test_recommendation_flow_persists_broll_and_music_results(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    broll_team = tmp_path / "team-meeting.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")
    broll_team.write_bytes(b"video bytes 2")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Recommendation Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    city_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )
    team_asset = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_team),
            "title": "Team meeting",
            "tags": ["team", "meeting", "collaboration"],
        },
    )
    assert city_asset.status_code == 201
    assert team_asset.status_code == 201

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]

    broll_job = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    music_job = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )
    assert broll_job.status_code == 202
    assert music_job.status_code == 202

    broll_result = client.get(
        f"/api/projects/{project_id}/jobs/broll-recommendation/{broll_job.json()['job_id']}"
    )
    music_result = client.get(
        f"/api/projects/{project_id}/jobs/music-recommendation/{music_job.json()['job_id']}"
    )
    assert broll_result.status_code == 200
    assert music_result.status_code == 200

    broll_payload = broll_result.json()
    music_payload = music_result.json()
    assert broll_payload["status"] == "succeeded"
    assert music_payload["status"] == "succeeded"
    assert len(broll_payload["recommendations"]) >= 2
    assert len(music_payload["recommendations"]) >= 2
    assert all("score" in item for item in broll_payload["recommendations"])
    assert all("reason" in item for item in broll_payload["recommendations"])
    assert all(item["auto_apply_allowed"] is True for item in broll_payload["recommendations"])
    assert all(item["review_required"] is False for item in broll_payload["recommendations"])

    project_root = tmp_path / "projects" / project_id
    recommendation_files = list((project_root / "analysis" / "recommendations").glob("*.json"))
    assert len(recommendation_files) >= 2
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in recommendation_files
    ]
    recommendation_types = {payload["recommendation_type"] for payload in payloads}
    assert {"broll", "bgm"}.issubset(recommendation_types)


def test_music_recommendation_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "cinematic pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: cinematic pulse."
    assert recommendation["score"] == 0.91
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 2
    assert local_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION
    assert gemini_provider.calls == []


def test_music_recommendation_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "warm ambient", "score": 0.83},
                raw_text='{"music_mood":"warm ambient","score":0.83}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-music-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_music_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "warm ambient"
    assert recommendation["score"] == 0.83
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 2
    assert len(gemini_provider.calls) == 2
    assert gemini_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_music_recommendation_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Disabled Local Gemini",
        "api_key": "AIza-music-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_music_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "steady documentary"
    assert recommendation["score"] == 0.78
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 2
    assert gemini_provider.calls[1].task_type is LLMTaskType.MUSIC_RECOMMENDATION


def test_music_recommendation_endpoint_preserves_rule_based_fallback_when_local_disabled_without_gemini_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "clean documentary pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: clean documentary pulse."
    assert recommendation["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "rule_based_fallback",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }


def test_music_recommendation_endpoint_preserves_rule_based_path_after_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_music_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    recommendation = result.json()["recommendations"][0]
    assert recommendation["payload"]["music_mood"] == "clean documentary pulse"
    assert recommendation["reason"] == "Suggested music mood for this segment: clean documentary pulse."


def test_music_recommendation_local_first_path_preserves_downstream_timeline_behavior(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, script_asset_id, transcription_job_id = _create_segment_analysis_project(client, tmp_path)
    broll_asset = tmp_path / "music-downstream.mp4"
    broll_asset.write_bytes(b"video bytes")
    asset_response = client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_asset),
            "title": "Office Skyline",
            "tags": ["office", "skyline"],
        },
    )
    assert asset_response.status_code == 201

    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    music_result = client.get(f"/api/projects/{project_id}/jobs/music-recommendation/{music_job_id}")

    assert timeline_result.status_code == 200
    assert music_result.status_code == 200
    assert any(track["track_type"] == "bgm" for track in timeline_result.json()["timeline"]["tracks"])
    assert music_result.json()["recommendations"][0]["payload"]["music_mood"] == "cinematic pulse"
    assert len(local_provider.calls) == 3


def test_broll_recommendation_endpoint_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_broll_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    payload = result.json()
    assert payload["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert payload["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 2
    assert gemini_provider.calls == []


def test_broll_recommendation_endpoint_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-test-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_broll_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 2
    assert len(gemini_provider.calls) == 2


def test_broll_recommendation_endpoint_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            )
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-test-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, segment_job_id = _create_broll_recommendation_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 2


def test_broll_recommendation_endpoint_preserves_heuristic_path_after_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, segment_job_id = _create_broll_recommendation_project(client, tmp_path)

    response = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    )

    assert response.status_code == 202
    result = client.get(f"/api/projects/{project_id}/jobs/broll-recommendation/{response.json()['job_id']}")
    assert result.status_code == 200
    assert result.json()["recommendations"][0]["reason"].lower().startswith("matched keywords: office")
    assert result.json()["recommendations"][0]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }


def test_timeline_and_review_snapshot_flow(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Timeline Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    timeline_response = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    )
    assert timeline_response.status_code == 202
    timeline_job_id = timeline_response.json()["job_id"]

    timeline_result = client.get(
        f"/api/projects/{project_id}/timelines/{timeline_job_id}"
    )
    review_snapshot = client.get(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}"
    )
    assert timeline_result.status_code == 200
    assert review_snapshot.status_code == 200

    timeline_payload = timeline_result.json()
    review_payload = review_snapshot.json()
    assert timeline_payload["status"] == "succeeded"
    assert timeline_payload["job_id"].startswith("timeline_build_job_")
    assert timeline_payload["timeline"]["project_id"] == project_id
    assert len(timeline_payload["timeline"]["tracks"]) >= 1
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_payload["timeline"]["tracks"]}
    )
    assert len(review_payload["segments"]) >= 2
    assert len(review_payload["applied_recommendations"]) >= 2
    assert len(review_payload["pending_recommendations"]) == 0
    assert any(flag["code"] == "segment_review_required" for flag in review_payload["review_flags"])
    assert review_payload["timeline_id"] == timeline_payload["timeline"]["timeline_id"]

    project_root = tmp_path / "projects" / project_id
    timeline_files = list((project_root / "timelines").glob("timeline_*.json"))
    assert timeline_files
    timeline_json = json.loads(timeline_files[0].read_text(encoding="utf-8"))
    assert timeline_json["project_id"] == project_id
    assert {"narration", "broll", "bgm"}.issubset(
        {track["track_type"] for track in timeline_json["tracks"]}
    )


def test_review_snapshot_uses_local_first_runtime_before_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Review the flagged narration segment before export.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Review the flagged narration segment before export.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider()
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Review the flagged narration segment before export."
    assert payload["operator_guidance"]["action_items"] == ["Check seg_001 narration alignment"]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert len(local_provider.calls) == 4
    assert local_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls == []


def test_review_snapshot_persists_operator_guidance_for_repeated_reads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Persisted local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Persisted local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    second_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert first_review_snapshot.status_code == 200
    assert second_review_snapshot.status_code == 200
    first_payload = first_review_snapshot.json()
    second_payload = second_review_snapshot.json()
    assert first_payload["operator_guidance"]["summary"] == "Persisted local review summary."
    assert second_payload["operator_guidance"] == first_payload["operator_guidance"]
    assert len(local_provider.calls) == 4


def test_review_snapshot_invalidates_persisted_guidance_when_review_status_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Draft review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Draft review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    second_review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert first_review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert second_review_snapshot.status_code == 200
    assert first_review_snapshot.json()["operator_guidance"]["summary"] == "Draft review summary."
    assert second_review_snapshot.json()["review_status"] == "approved"
    assert second_review_snapshot.json()["operator_guidance"]["summary"] == (
        "Timeline review is approved and outputs can be generated."
    )
    assert second_review_snapshot.json()["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_review_snapshot_falls_back_to_gemini_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini fallback review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Gemini fallback review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Fallback Gemini",
        "api_key": "AIza-review-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Gemini fallback review summary."
    assert payload["operator_guidance"]["action_items"] == ["Resolve flagged review items"]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 4
    assert len(gemini_provider.calls) == 4
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_review_snapshot_skips_local_when_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider()
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Disabled local review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Disabled Local Gemini",
        "api_key": "AIza-review-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"] == "Disabled local review summary."
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert local_provider.calls == []
    assert len(gemini_provider.calls) == 4
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY


def test_review_snapshot_preserves_blocking_behavior_when_ai_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    ),
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["review_status"] == "draft"
    assert payload["operator_guidance"]["summary"].lower().startswith("timeline is ready for approval")
    assert preview_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()


def test_review_snapshot_falls_back_to_heuristic_guidance_on_unexpected_runtime_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")

    assert review_snapshot.status_code == 200
    payload = review_snapshot.json()
    assert payload["operator_guidance"]["summary"].lower().startswith("review is blocked")
    assert payload["operator_guidance"]["action_items"] == ["Segment requires operator review before export."]
    assert payload["operator_guidance"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_preview_and_export_use_operator_copy_runtime_in_production_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Preview operator copy from local runtime.",
                    "action_items": ["Check caption timing in the playable preview."],
                },
                raw_text='{"summary":"Preview operator copy from local runtime.","action_items":["Check caption timing in the playable preview."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Export operator copy from local runtime.",
                    "action_items": ["Open the CapCut payload and confirm subtitle attachment."],
                },
                raw_text='{"summary":"Export operator copy from local runtime.","action_items":["Open the CapCut payload and confirm subtitle attachment."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202
    assert len(local_provider.calls) == 5
    assert local_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert local_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY
    assert "preview" in local_provider.calls[3].prompt.lower()
    assert "capcut" in local_provider.calls[4].prompt.lower()


def test_preview_and_export_return_ai_backed_operator_copy_on_local_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Preview operator copy from local runtime.",
                    "action_items": ["Check caption timing in the playable preview."],
                },
                raw_text='{"summary":"Preview operator copy from local runtime.","action_items":["Check caption timing in the playable preview."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Export operator copy from local runtime.",
                    "action_items": ["Open the CapCut payload and confirm subtitle attachment."],
                },
                raw_text='{"summary":"Export operator copy from local runtime.","action_items":["Open the CapCut payload and confirm subtitle attachment."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"] == [
        "Preview operator copy from local runtime.",
        "Check caption timing in the playable preview.",
    ]
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }
    assert export_result.json()["export"]["notes"] == [
        "Export operator copy from local runtime.",
        "Open the CapCut payload and confirm subtitle attachment.",
        "CapCut remains an export target, not the internal source of truth.",
    ]
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }


def test_preview_and_export_fall_back_to_gemini_operator_copy_when_local_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="preview/export local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Review the playable preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Review the playable preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the CapCut export package before delivery."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the CapCut export package before delivery."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Output Fallback Gemini",
        "api_key": "AIza-output-fallback",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"] == [
        "Gemini preview operator copy.",
        "Review the playable preview before handoff.",
    ]
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert export_result.json()["export"]["notes"] == [
        "Gemini export operator copy.",
        "Validate the CapCut export package before delivery.",
        "CapCut remains an export target, not the internal source of truth.",
    ]
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }
    assert len(local_provider.calls) == 5
    assert len(gemini_provider.calls) == 5
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY
    keys_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert keys_response.status_code == 200
    key_state = keys_response.json()["keys"][0]
    assert key_state["consecutive_failures"] == 0
    assert key_state["last_error"] is None
    assert key_state["last_used_at"] is not None


def test_preview_and_export_skip_local_operator_copy_when_local_runtime_is_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local preview operator copy.",
                    "action_items": ["Review the preview in Gemini fallback mode."],
                },
                raw_text='{"summary":"Disabled local preview operator copy.","action_items":["Review the preview in Gemini fallback mode."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Disabled local export operator copy.",
                    "action_items": ["Review the export in Gemini fallback mode."],
                },
                raw_text='{"summary":"Disabled local export operator copy.","action_items":["Review the export in Gemini fallback mode."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(),
            gemini_provider=gemini_provider,
            local_enabled=False,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Output Disabled Gemini",
        "api_key": "AIza-output-disabled",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    assert client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve").status_code == 202
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200
    assert preview_result.json()["preview"]["notes"][0] == "Disabled local preview operator copy."
    assert export_result.json()["export"]["notes"][0] == "Disabled local export operator copy."
    assert export_result.json()["export"]["notes"][-1] == "CapCut remains an export target, not the internal source of truth."
    assert preview_result.json()["preview"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert export_result.json()["export"]["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_disabled"],
    }
    assert len(gemini_provider.calls) == 5
    assert gemini_provider.calls[3].task_type is LLMTaskType.OPERATOR_COPY
    assert gemini_provider.calls[4].task_type is LLMTaskType.OPERATOR_COPY


def test_preview_and_export_gating_blocks_before_operator_copy_runtime_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "focused", "score": 0.88},
                raw_text='{"music_mood":"focused","score":0.88}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert len(local_provider.calls) == 3


def test_project_listing_and_job_feed_support_dashboard(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Dashboard Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    projects_response = client.get("/api/projects")
    project_response = client.get(f"/api/projects/{project_id}")
    jobs_response = client.get(f"/api/projects/{project_id}/jobs")

    assert projects_response.status_code == 200
    assert project_response.status_code == 200
    assert jobs_response.status_code == 200

    projects_payload = projects_response.json()
    project_payload = project_response.json()
    jobs_payload = jobs_response.json()

    assert any(project["project_id"] == project_id for project in projects_payload["projects"])
    assert project_payload["project_id"] == project_id
    assert project_payload["name"] == "Dashboard Draft"
    assert any(job["job_id"] == timeline_job_id for job in jobs_payload["jobs"])
    assert any(job["job_type"] == "timeline_build" for job in jobs_payload["jobs"])


def test_preview_and_capcut_export_flow_persist_outputs_and_statuses(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Output Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]
    approve_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    assert approve_response.status_code == 202

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_job_id = preview_response.json()["job_id"]
    export_job_id = export_response.json()["job_id"]

    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert preview_result.status_code == 200
    assert export_result.status_code == 200

    preview_payload = preview_result.json()
    export_payload = export_result.json()
    assert preview_payload["status"] == "succeeded"
    assert preview_payload["preview"]["timeline_id"] == "timeline_001"
    assert preview_payload["preview"]["artifact_kind"] == "playable_html_preview"
    assert preview_payload["preview"]["player_uri"].endswith(".html")
    assert export_payload["status"] == "succeeded"
    assert export_payload["export"]["timeline_id"] == "timeline_001"
    assert export_payload["export"]["export_type"] == "capcut"
    assert export_payload["export"]["adapter"] == "capcut_v1_port"
    assert export_payload["export"]["notes"][0].lower().startswith("capcut export manifest")
    assert export_payload["export"]["capcut_tracks"][0]["segments"][0]["source_uri"].endswith("/inputs/narration/source-narration.wav")

    project_root = tmp_path / "projects" / project_id
    assert (project_root / "previews" / "preview_001.json").exists()
    assert (
        project_root / "exports" / "capcut" / "export_001" / "capcut_payload.json"
    ).exists()


def test_preview_and_capcut_export_require_review_clearance(tmp_path: Path) -> None:
    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting restart.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Review Gate Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert "review" in preview_response.json()["detail"].lower()
    assert "review" in export_response.json()["detail"].lower()

    jobs_response = client.get(f"/api/projects/{project_id}/jobs")
    jobs_payload = jobs_response.json()["jobs"]
    preview_job = next(job for job in jobs_payload if job["job_type"] == "preview_render")
    export_job = next(job for job in jobs_payload if job["job_type"] == "capcut_export")
    assert preview_job["status"] == "failed"
    assert export_job["status"] == "failed"

    project_root = tmp_path / "projects" / project_id
    assert not list((project_root / "previews").glob("preview_*.json"))
    assert not list((project_root / "exports" / "capcut").glob("export_*"))


def test_preview_and_export_surface_pending_tts_replacement_blocker_before_approval(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Pending TTS Blocker Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [
                {
                    "code": "tts_replacement_review_required",
                    "segment_id": "seg_001",
                    "message": "Approved TTS replacement is still required before output.",
                }
            ],
            "applied_recommendations": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Manual TTS replacement selection from editing session.",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert "tts_replacement" in preview_response.json()["detail"]
    assert "rec_tts_seg_001" in preview_response.json()["detail"]
    assert "tts_replacement" in export_response.json()["detail"]
    assert "rec_tts_seg_001" in export_response.json()["detail"]


def test_preview_export_and_subtitles_require_explicit_approval_even_without_blockers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Approval Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    assert review_snapshot.status_code == 200
    assert review_snapshot.json()["pending_recommendations"] == []
    assert review_snapshot.json()["review_flags"] == []

    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )

    assert preview_response.status_code == 400
    assert export_response.status_code == 400
    assert subtitle_response.status_code == 400
    assert "approval" in preview_response.json()["detail"].lower()


def test_review_snapshot_api_can_approve_pending_recommendation(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    approved_candidate = {
        "recommendation_id": "rec_broll_review_002",
        "target_segment_id": "seg_002",
        "recommendation_type": "broll",
        "selected_asset_id": "asset_broll_review_002",
        "score": 0.88,
        "reason": "Operator approved the suggested B-roll pick.",
        "auto_apply_allowed": False,
        "review_required": True,
        "payload": {"tags": ["team", "meeting"]},
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    persisted_timeline["applied_recommendations"] = []
    persisted_timeline["pending_recommendations"] = [approved_candidate]
    persisted_timeline["review_flags"] = [
        {
            "code": "broll_review_required",
            "segment_id": "seg_002",
            "message": "Operator must confirm the B-roll pick before approval.",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    database_path = tmp_path / "projects" / project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM recommendations")
        connection.execute(
            """
            INSERT INTO recommendations (
                recommendation_id,
                project_id,
                target_segment_id,
                recommendation_type,
                selected_asset_id,
                score,
                reason,
                auto_apply_allowed,
                review_required,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approved_candidate["recommendation_id"],
                project_id,
                approved_candidate["target_segment_id"],
                approved_candidate["recommendation_type"],
                approved_candidate["selected_asset_id"],
                approved_candidate["score"],
                approved_candidate["reason"],
                0,
                1,
                json.dumps(approved_candidate["payload"], ensure_ascii=True),
                approved_candidate["created_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/recommendations/"
        "rec_broll_review_002/approve"
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["review_status"] == "draft"
    assert payload["pending_recommendations"] == []
    assert payload["review_flags"] == []
    assert payload["applied_recommendations"][0]["recommendation_id"] == "rec_broll_review_002"

    refreshed_timeline = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    assert refreshed_timeline.status_code == 200
    refreshed_timeline_payload = refreshed_timeline.json()["timeline"]
    assert refreshed_timeline_payload["pending_recommendations"] == []
    assert refreshed_timeline_payload["review_flags"] == []
    assert refreshed_timeline_payload["applied_recommendations"][0]["recommendation_id"] == (
        "rec_broll_review_002"
    )


def test_approved_tts_replacement_flows_through_preview_and_export_outputs(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved TTS Output Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "narration_source_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": (
                                f"local://projects/{project.project_id}/assets/generated/"
                                "asset_tts_approved_001.wav"
                            ),
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_approved_001",
                    "score": 1.0,
                    "reason": "Approved narration replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": f"local://projects/{project.project_id}/assets/generated/asset_tts_approved_001.wav"
                    },
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )

    client = TestClient(create_app(projects_root=tmp_path))
    preview_response = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_response = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )

    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    preview_payload = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_response.json()['job_id']}"
    ).json()
    export_payload = client.get(
        f"/api/projects/{project.project_id}/exports/{export_response.json()['job_id']}"
    ).json()

    preview_html_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=preview_payload["preview"]["player_uri"],
    )
    assert "asset_tts_approved_001" in preview_html_path.read_text(encoding="utf-8")
    voiceover_track = next(
        track for track in export_payload["export"]["capcut_tracks"] if track["track_name"] == "voiceover"
    )
    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        f"local://projects/{project.project_id}/assets/generated/asset_tts_approved_001.wav",
        f"local://projects/{project.project_id}/inputs/narration/source.wav",
    ]


def test_editing_session_api_can_create_and_patch_caption_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )

    assert create_response.status_code == 201
    session_id = create_response.json()["session_id"]

    patch_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "Manual caption fix"},
    )

    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["session_id"] == session_id
    assert payload["segments"][0]["caption_text"] == "Manual caption fix"
    assert payload["history"][-1]["mutation_type"] == "caption_update"


def test_editing_session_api_rejects_blank_caption_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    patch_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "   "},
    )

    assert patch_response.status_code == 422


def test_editing_session_api_can_fetch_cut_and_broll_updates(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    cut_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/cut-action",
        json={"cut_action": "remove"},
    )
    broll_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    get_response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}",
    )

    assert cut_response.status_code == 200
    assert broll_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["cut_action"] == "remove"
    assert payload["segments"][0]["broll_override"] == {"asset_id": "asset_manual_001"}
    assert payload["history"][-2]["mutation_type"] == "cut_action_update"
    assert payload["history"][-1]["mutation_type"] == "broll_override_update"


def test_editing_session_api_can_clear_broll_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["broll_override"] is None
    assert payload["history"][-1]["mutation_type"] == "broll_override_clear"


def test_editing_session_api_can_fetch_latest_session_by_updated_at(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_session = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    ).json()
    second_session = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    ).json()

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{first_session['session_id']}/segments/seg_001/caption",
        json={"caption_text": "Older session touched first"},
    )
    latest_update_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{second_session['session_id']}/segments/seg_001/caption",
        json={"caption_text": "Latest session should win"},
    )

    response = client.get(f"/api/projects/{project_id}/editing-sessions/latest")

    assert latest_update_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == second_session["session_id"]
    assert payload["segments"][0]["caption_text"] == "Latest session should win"
    assert payload["updated_at"] == latest_update_response.json()["updated_at"]


def test_editing_session_api_can_start_partial_regeneration_job(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll", "visual_overlay"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"].startswith("partial_regeneration_job_")
    assert payload["status"] == "succeeded"
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["fields"] == ["broll", "visual_overlay"]
    assert payload["downstream_steps"] == [
        "broll_refresh",
        "overlay_refresh",
        "timeline_build",
    ]


def test_editing_session_api_can_preview_partial_regeneration_scope_without_creating_job(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/caption",
        json={"caption_text": "Team meeting overview with corrected label"},
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/broll",
        json={"asset_id": "asset_manual_002"},
    )

    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002"],
            "fields": ["caption", "broll", "visual_overlay"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert "job_id" not in payload
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_002"]
    assert payload["fields"] == ["caption", "broll", "visual_overlay"]
    assert payload["downstream_steps"] == [
        "segment_refresh",
        "broll_refresh",
        "overlay_refresh",
        "timeline_build",
    ]
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Team meeting overview with corrected label",
            "cut_action": "keep",
            "review_required": True,
            "broll_override": {"asset_id": "asset_manual_002"},
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": None,
        }
    ]
    assert payload["affected_output_areas"] == [
        "segment copy",
        "b-roll track",
        "visual overlays",
        "timeline preview",
        "subtitle render",
        "capcut export",
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_blocked_for_manual_tts_rerun_scope_on_review_required_segment(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_002/tts-replacement",
        json={
            "recommendation_id": "rec_tts_review_002",
            "asset_id": "asset_tts_review_002",
        },
    )
    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_002"],
            "fields": ["tts_replacement"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]
    assert payload["targeted_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Line two with restart from review runtime.",
            "cut_action": "keep",
            "review_required": True,
            "broll_override": None,
            "visual_overlays": [],
            "music_override": None,
            "tts_replacement": {
                "recommendation_id": "rec_tts_review_002",
                "asset_id": "asset_tts_review_002",
            },
        }
    ]
    assert before_jobs == after_jobs


def test_editing_session_api_marks_preflight_as_draft_for_clean_rerun_scope(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Clean Preflight Draft Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Clean caption",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)

    response = client.post(
        f"/api/projects/{project.project_id}/editing-sessions/{session['session_id']}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "draft"
    assert payload["prediction_reasons"] == []


def test_editing_session_api_marks_preflight_blocked_when_source_timeline_still_has_review_blockers(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    timeline_payload = timeline_result.json()["timeline"]
    timeline_path = (
        tmp_path
        / "projects"
        / project_id
        / "timelines"
        / f'{timeline_payload["timeline_id"]}.json'
    )
    persisted_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_timeline["review_flags"] = [
        {
            "code": "tts_replacement_review_required",
            "segment_id": "seg_002",
            "message": "Operator review still required.",
        }
    ]
    persisted_timeline["pending_recommendations"] = [
        {
            "recommendation_id": "rec_tts_review_002",
            "target_segment_id": "seg_002",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": "asset_tts_review_002",
            "score": 0.93,
            "reason": "Awaiting operator approval.",
            "auto_apply_allowed": False,
            "review_required": True,
            "payload": {},
            "created_at": "2026-06-29T00:00:00+00:00",
        }
    ]
    timeline_path.write_text(json.dumps(persisted_timeline, indent=2), encoding="utf-8")

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration/preflight",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["caption"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["predicted_review_status_after_rerun"] == "blocked"
    assert payload["prediction_reasons"] == [
        "source timeline already has unresolved review blockers that rerun will preserve",
        "selected segments already require operator review, so rerun output stays blocked",
    ]


def test_editing_session_api_can_fetch_partial_regeneration_result(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": "asset_manual_001"},
    )
    start_response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )
    job_id = start_response.json()["job_id"]

    result_response = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{job_id}",
    )

    assert result_response.status_code == 200
    payload = result_response.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "succeeded"
    assert payload["session_id"] == session_id
    assert payload["segment_ids"] == ["seg_001"]
    assert payload["fields"] == ["broll"]
    assert payload["downstream_steps"] == ["broll_refresh", "timeline_build"]
    assert payload["session_updated_at"]
    assert payload["timeline"]["timeline_id"].startswith("timeline_")
    latest_session = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    assert payload["session_updated_at"] == latest_session["updated_at"]


def test_editing_session_api_rejects_invalid_partial_regeneration_request(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["does_not_exist"],
            "fields": ["not_a_real_field"],
        },
    )

    assert response.status_code == 400


def test_editing_session_api_rejects_partial_regeneration_when_scope_normalizes_empty(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    before_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["   "],
            "fields": ["broll"],
        },
    )
    after_jobs = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]

    assert response.status_code == 400
    assert before_jobs == after_jobs


def test_editing_session_api_can_fetch_visual_overlay_and_music_updates(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    visual_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/visual-overlay",
        json={"overlay_type": "image_card", "asset_id": "asset_image_001"},
    )
    music_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )
    get_response = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}",
    )

    assert visual_response.status_code == 200
    assert music_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {"overlay_type": "image_card", "asset_id": "asset_image_001"}
    ]
    assert payload["segments"][0]["music_override"] == {"asset_id": "music_manual_001"}
    assert payload["history"][-2]["mutation_type"] == "visual_overlay_update"
    assert payload["history"][-1]["mutation_type"] == "music_override_update"


def test_editing_session_api_can_clear_music_override(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music_manual_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["music_override"] is None
    assert payload["history"][-1]["mutation_type"] == "music_override_clear"


def test_editing_session_api_can_patch_explanation_and_tts_mutations(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    explanation_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    tts_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": "asset_tts_001"},
    )
    get_response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}")

    assert explanation_response.status_code == 200
    assert tts_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        }
    ]
    assert payload["segments"][0]["tts_replacement"] == {
        "recommendation_id": "rec_tts_seg_001",
        "asset_id": "asset_tts_001",
    }
    assert payload["history"][-2]["mutation_type"] == "explanation_card_update"
    assert payload["history"][-1]["mutation_type"] == "tts_replacement_select"


def test_editing_session_api_can_clear_explanation_card(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["visual_overlays"] == []
    assert payload["history"][-1]["mutation_type"] == "explanation_card_remove"


def test_editing_session_api_can_clear_tts_replacement(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": "asset_tts_001"},
    )
    clear_response = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["segments"][0]["tts_replacement"] is None
    assert payload["history"][-1]["mutation_type"] == "tts_replacement_clear"


def test_editing_session_api_can_clear_image_and_table_overlays(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/image-overlay",
        json={"asset_id": "asset_image_001", "text": "Exterior reference image"},
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/table-overlay",
        json={
            "columns": ["Metric", "Value"],
            "rows": [["CTR", "4.2%"]],
            "text": "Metric | Value\nCTR | 4.2%",
        },
    )

    clear_image = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/image-overlay",
    )
    clear_table = client.delete(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/table-overlay",
    )

    assert clear_image.status_code == 200
    assert clear_table.status_code == 200
    payload = clear_table.json()
    assert payload["segments"][0]["visual_overlays"] == []
    assert payload["history"][-2]["mutation_type"] == "image_overlay_remove"
    assert payload["history"][-1]["mutation_type"] == "table_overlay_remove"


def test_editing_session_api_visual_overlay_patch_preserves_existing_explanation_overlay(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/visual-overlay",
        json={"overlay_type": "image_card", "asset_id": "asset_image_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
        {
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
        },
    ]


def test_editing_session_api_can_start_partial_regeneration_for_explanation_and_tts(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    tts_audio = tmp_path / "editing-session-tts.wav"
    tts_audio.write_bytes(b"tts wav data")
    tts_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(tts_audio)},
    ).json()["asset_id"]

    create_response = client.post(
        f"/api/projects/{project_id}/editing-sessions",
        json={"timeline_job_id": timeline_job_id},
    )
    session_id = create_response.json()["session_id"]

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/explanation-card",
        json={
            "title": "Key takeaway",
            "body": "Explain the result clearly.",
            "text": "Key takeaway: Explain the result clearly.",
        },
    )
    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/tts-replacement",
        json={"recommendation_id": "rec_tts_seg_001", "asset_id": tts_asset_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={
            "segment_ids": ["seg_001"],
            "fields": ["explanation_card", "tts_replacement"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["fields"] == ["explanation_card", "tts_replacement"]
    assert payload["downstream_steps"] == [
        "overlay_refresh",
        "tts_refresh",
        "timeline_build",
    ]

def test_approved_timeline_can_generate_subtitles_preview_and_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Approved Output Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    approve_response = client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    )
    subtitle_response = client.post(
        f"/api/projects/{project_id}/jobs/subtitle-render",
        json={"timeline_job_id": timeline_job_id},
    )
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert approve_response.status_code == 202
    assert subtitle_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    subtitle_job_id = subtitle_response.json()["job_id"]
    preview_job_id = preview_response.json()["job_id"]
    export_job_id = export_response.json()["job_id"]

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    subtitle_result = client.get(f"/api/projects/{project_id}/subtitles/{subtitle_job_id}")
    preview_result = client.get(f"/api/projects/{project_id}/previews/{preview_job_id}")
    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert review_snapshot.status_code == 200
    assert review_snapshot.json()["review_status"] == "approved"
    assert subtitle_result.status_code == 200
    assert subtitle_result.json()["subtitle"]["format"] == "srt"
    assert subtitle_result.json()["subtitle"]["file_uri"].endswith(".srt")
    assert preview_result.status_code == 200
    assert preview_result.json()["preview"]["player_uri"].endswith(".html")
    assert preview_result.json()["preview"]["artifact_kind"] == "playable_html_preview"
    assert export_result.status_code == 200
    assert export_result.json()["export"]["subtitle_file_uri"].endswith(".srt")
    assert export_result.json()["export"]["adapter"] == "capcut_v1_port"
    assert [track["track_name"] for track in export_result.json()["export"]["capcut_tracks"]] == [
        "voiceover",
        "broll",
        "subtitle",
        "bgm",
    ]


def test_auto_cut_module_introduction_does_not_break_approved_output_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def clean_transcribe(self, request):  # noqa: ANN001
        return STTResult(
            text="Office overview. Team meeting overview.",
            segments=[
                STTSegment(start_sec=0.0, end_sec=1.0, text="Office overview.", confidence=0.99),
                STTSegment(
                    start_sec=1.0,
                    end_sec=2.2,
                    text="Team meeting overview.",
                    confidence=0.98,
                ),
            ],
            provider_name="mock_stt",
        )

    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        clean_transcribe,
    )

    source_audio = tmp_path / "source-narration.wav"
    source_script = tmp_path / "source-script.txt"
    broll_city = tmp_path / "city-office.mp4"
    source_audio.write_bytes(b"fake wav data")
    source_script.write_text("Office overview.\n\nTeam meeting overview.\n", encoding="utf-8")
    broll_city.write_bytes(b"video bytes 1")

    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=FakeStructuredProvider(
                errors=[
                    LLMProviderError(
                        provider_name="local_qwen",
                        message="offline test local unavailable",
                        retryable=True,
                        error_code="LOCAL_UNAVAILABLE",
                    )
                    for _ in range(8)
                ]
            ),
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Regression Draft"}).json()["project_id"]

    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(source_audio)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document",
        json={"source_path": str(source_script)},
    ).json()["asset_id"]
    client.post(
        f"/api/projects/{project_id}/assets/broll-video",
        json={
            "source_path": str(broll_city),
            "title": "Office skyline",
            "tags": ["office", "city", "overview"],
        },
    )

    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={
            "transcription_job_id": transcription_job_id,
            "script_asset_id": script_asset_id,
        },
    ).json()["job_id"]
    broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    music_job_id = client.post(
        f"/api/projects/{project_id}/jobs/music-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={
            "segment_analysis_job_id": segment_job_id,
            "recommendation_job_ids": [broll_job_id, music_job_id],
        },
    ).json()["job_id"]

    assert client.post(
        f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve"
    ).status_code == 202
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    export_result = client.get(f"/api/projects/{project_id}/exports/{export_job_id}")

    assert export_result.status_code == 200
    assert export_result.json()["status"] == "succeeded"
    assert export_result.json()["export"]["export_type"] == "capcut"


def test_auto_cut_api_registers_raw_video_and_returns_planning_payload(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(
        projects_root=tmp_path,
        auto_cut_config=AutoCutConfig(
            scene_threshold=0.275,
            blackdetect_min_duration=0.8,
            blackdetect_picture_threshold=0.91,
        ),
    )
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut API Draft"}).json()["project_id"]

    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    assert raw_asset_response.status_code == 201
    assert raw_asset_response.json()["asset_type"] == "raw_video"

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 200
    assert plan_response.json() == {
        "asset_id": raw_asset_response.json()["asset_id"],
        "storage_uri": raw_asset_response.json()["storage_uri"],
        "should_auto_cut": True,
        "scene_detection_filter": "select='gt(scene,0.275)',showinfo",
        "blackdetect_filter": "blackdetect=d=0.8:pic_th=0.91",
        "planned_segments": [
            {"start_sec": 0.0, "end_sec": 30.0},
            {"start_sec": 30.0, "end_sec": 75.0},
            {"start_sec": 75.0, "end_sec": 120.0},
        ],
        "kept_segments": [
            {
                "start_sec": 0.0,
                "end_sec": 30.0,
                "duration_sec": 30.0,
                "avg_brightness": 90.0,
                "scene_change_count": 3,
                "reasons": [],
            },
            {
                "start_sec": 30.0,
                "end_sec": 75.0,
                "duration_sec": 45.0,
                "avg_brightness": 80.0,
                "scene_change_count": 2,
                "reasons": [],
            },
            {
                "start_sec": 75.0,
                "end_sec": 120.0,
                "duration_sec": 45.0,
                "avg_brightness": 85.0,
                "scene_change_count": 4,
                "reasons": [],
            },
        ],
    }


def test_auto_cut_api_rejects_non_raw_video_assets(tmp_path: Path) -> None:
    narration_audio = tmp_path / "narration.wav"
    narration_audio.write_bytes(b"audio bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Invalid Asset Draft"}).json()["project_id"]
    narration_asset_response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(narration_audio)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": narration_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 400
    assert plan_response.json()["detail"] == "auto_cut planning requires a raw_video asset."


def test_auto_cut_api_rejects_segment_sample_boundary_mismatches(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Boundary Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 5.0, "end_sec": 35.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 35.0, "end_sec": 80.0, "avg_brightness": 80.0, "scene_change_count": 2},
            ],
        },
    )

    assert plan_response.status_code == 400
    assert plan_response.json()["detail"] == "auto_cut segment_samples must match planned segment boundaries."


def test_auto_cut_api_skips_planning_for_short_inputs(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Short Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 60.0,
            "scene_timestamps": [30.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 60.0, "avg_brightness": 90.0, "scene_change_count": 3},
            ],
        },
    )

    assert plan_response.status_code == 200
    assert plan_response.json()["should_auto_cut"] is False
    assert plan_response.json()["planned_segments"] == []
    assert plan_response.json()["kept_segments"] == []


def test_auto_cut_api_rejects_malformed_black_regions(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Black Region Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [{"start": 40.0, "end": 5.0}],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": 90.0, "scene_change_count": 3},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 422


def test_auto_cut_api_rejects_invalid_segment_sample_metrics(tmp_path: Path) -> None:
    raw_video = tmp_path / "raw-footage.mp4"
    raw_video.write_bytes(b"video bytes")

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "AutoCut Invalid Metrics Draft"}).json()["project_id"]
    raw_asset_response = client.post(
        f"/api/projects/{project_id}/assets/raw-video",
        json={"source_path": str(raw_video)},
    )

    plan_response = client.post(
        f"/api/projects/{project_id}/jobs/auto-cut-plan",
        json={
            "raw_video_asset_id": raw_asset_response.json()["asset_id"],
            "total_duration": 120.0,
            "scene_timestamps": [30.0, 75.0],
            "black_regions": [],
            "segment_samples": [
                {"start_sec": 0.0, "end_sec": 30.0, "avg_brightness": -1.0, "scene_change_count": -1},
                {"start_sec": 30.0, "end_sec": 75.0, "avg_brightness": 80.0, "scene_change_count": 2},
                {"start_sec": 75.0, "end_sec": 120.0, "avg_brightness": 85.0, "scene_change_count": 4},
            ],
        },
    )

    assert plan_response.status_code == 422


def test_gemini_key_management_api_masks_secrets_and_supports_state_changes(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Gemini API Project"}).json()["project_id"]

    create_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Primary Gemini",
            "api_key": "AIza-sample-secret-1234",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["label"] == "Primary Gemini"
    assert created["status"] == "active"
    assert created["masked_api_key"].startswith("AIza")
    assert "secret" not in json.dumps(created).lower()

    list_response = client.get(f"/api/projects/{project_id}/providers/gemini/keys")
    assert list_response.status_code == 200
    listed = list_response.json()["keys"]
    assert len(listed) == 1
    assert listed[0]["key_id"] == created["key_id"]
    assert "api_key" not in listed[0]
    assert "api_key_secret" not in listed[0]

    update_response = client.patch(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}",
        json={
            "label": "Primary Gemini Updated",
            "cheap_model": "gemini-2.5-flash",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Primary Gemini Updated"
    assert update_response.json()["cheap_model"] == "gemini-2.5-flash"

    disable_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}/disable"
    )
    enable_response = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys/{created['key_id']}/enable"
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"
    assert enable_response.status_code == 200
    assert enable_response.json()["status"] == "active"


def test_gemini_key_api_enforces_max_ten_keys(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Gemini Limit Project"}).json()["project_id"]

    for index in range(10):
        response = client.post(
            f"/api/projects/{project_id}/providers/gemini/keys",
            json={
                "label": f"Gemini {index}",
                "api_key": f"AIza-sample-secret-{index}",
                "primary_model": "gemini-2.5-flash",
                "cheap_model": "gemini-2.5-flash-lite",
                "high_quality_model": "gemini-2.5-pro",
            },
        )
        assert response.status_code == 201

    overflow = client.post(
        f"/api/projects/{project_id}/providers/gemini/keys",
        json={
            "label": "Gemini overflow",
            "api_key": "AIza-over-limit",
            "primary_model": "gemini-2.5-flash",
            "cheap_model": "gemini-2.5-flash-lite",
            "high_quality_model": "gemini-2.5-pro",
        },
    )
    assert overflow.status_code == 400
    assert "10" in overflow.json()["detail"]


def test_provider_trace_audit_endpoint_summarizes_project_fallback_usage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
            for _ in range(6)
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Gemini review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Trace Audit Gemini",
        "api_key": "AIza-trace-audit",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert payload["summary"]["total_entries"] == 6
    assert payload["summary"]["provider_counts"]["gemini"] == 6
    assert payload["summary"]["fallback_entry_count"] == 6
    assert payload["summary"]["fallback_reason_counts"]["local_provider_error"] == 6
    assert payload["summary"]["artifact_type_counts"] == {
        "segment_analysis": 1,
        "broll_recommendation": 1,
        "music_recommendation": 1,
        "review_guidance": 1,
        "preview_render": 1,
        "capcut_export": 1,
    }


def test_provider_trace_audit_endpoint_exposes_artifact_level_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202

    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert [entry["artifact_type"] for entry in entries] == [
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
        "review_guidance",
        "preview_render",
        "capcut_export",
    ]
    review_entry = next(entry for entry in entries if entry["artifact_type"] == "review_guidance")
    preview_entry = next(entry for entry in entries if entry["artifact_type"] == "preview_render")
    export_entry = next(entry for entry in entries if entry["artifact_type"] == "capcut_export")
    assert review_entry["timeline_id"].startswith("timeline_")
    assert review_entry["job_id"] == timeline_job_id
    assert review_entry["status"] == "available"
    assert review_entry["provider_trace"]["final_provider"] == "local_qwen"
    assert preview_entry["job_id"] == preview_job_id
    assert preview_entry["artifact_id"].startswith("preview_")
    assert preview_entry["status"] == "succeeded"
    assert preview_entry["source_job_id"] == timeline_job_id
    assert preview_entry["provider_trace"]["final_provider"] == "local_qwen"
    assert export_entry["job_id"] == export_job_id
    assert export_entry["artifact_id"].startswith("export_")
    assert export_entry["status"] == "succeeded"
    assert export_entry["source_job_id"] == timeline_job_id
    assert export_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_supports_timeline_job_and_artifact_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_job_id = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]
    export_job_id = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    ).json()["job_id"]

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202

    unfiltered = client.get(f"/api/projects/{project_id}/provider-traces")
    timeline_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"]},
    )
    blank_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": "   ", "final_provider": ""},
    )
    job_type_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"job_type": "preview_render"},
    )
    artifact_type_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"artifact_type": "review_guidance"},
    )

    assert unfiltered.status_code == 200
    assert timeline_filtered.status_code == 200
    assert blank_filtered.status_code == 200
    assert job_type_filtered.status_code == 200
    assert artifact_type_filtered.status_code == 200
    assert len(unfiltered.json()["entries"]) == 6
    assert unfiltered.json()["direct_entries"] == unfiltered.json()["entries"]
    assert unfiltered.json()["upstream_entries"] == []
    assert len(blank_filtered.json()["entries"]) == len(unfiltered.json()["entries"])
    assert blank_filtered.json()["direct_entries"] == blank_filtered.json()["entries"]
    assert blank_filtered.json()["upstream_entries"] == []
    assert {entry["artifact_type"] for entry in timeline_filtered.json()["entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert [entry["job_id"] for entry in job_type_filtered.json()["entries"]] == [preview_job_id]
    assert [entry["artifact_type"] for entry in artifact_type_filtered.json()["entries"]] == ["review_guidance"]
    assert export_job_id not in [entry["job_id"] for entry in job_type_filtered.json()["entries"]]


def test_provider_trace_audit_endpoint_supports_provider_and_fallback_reason_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            )
            for _ in range(6)
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "steady documentary", "score": 0.78},
                raw_text='{"music_mood":"steady documentary","score":0.78}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Gemini review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Gemini preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Gemini export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Gemini export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Trace Audit Gemini",
        "api_key": "AIza-trace-audit",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    provider_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"final_provider": "gemini"},
    )
    provider_excluded = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"final_provider": "local_qwen"},
    )
    fallback_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"fallback_reason": "local_provider_error"},
    )
    fallback_excluded = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"fallback_reason": "unexpected_runtime_failure"},
    )

    assert provider_filtered.status_code == 200
    assert provider_excluded.status_code == 200
    assert fallback_filtered.status_code == 200
    assert fallback_excluded.status_code == 200
    assert len(provider_filtered.json()["entries"]) == 6
    assert provider_excluded.json()["entries"] == []
    assert len(fallback_filtered.json()["entries"]) == 6
    assert fallback_excluded.json()["entries"] == []
    assert {entry["provider_trace"]["final_provider"] for entry in provider_filtered.json()["entries"]} == {"gemini"}
    assert all(
        "local_provider_error" in entry["provider_trace"]["fallback_reasons"]
        for entry in fallback_filtered.json()["entries"]
    )


def test_provider_trace_audit_timeline_filter_includes_failed_preview_render_for_the_same_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Filtered Failed Preview Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="preview_render provider failed"):
        runner.start_preview_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )

    assert filtered_response.status_code == 200
    filtered_entries = filtered_response.json()["entries"]
    failed_entry = next(
        entry
        for entry in filtered_entries
        if entry["status"] == "failed" and entry["job_type"] == "preview_render"
    )
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["timeline_id"] == timeline["timeline_id"]


def test_provider_trace_audit_timeline_filter_includes_failed_capcut_export_for_the_same_timeline(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Filtered Failed Export Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="capcut_export provider failed"):
        runner.start_capcut_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )

    assert filtered_response.status_code == 200
    filtered_entries = filtered_response.json()["entries"]
    failed_entry = next(
        entry
        for entry in filtered_entries
        if entry["status"] == "failed" and entry["job_type"] == "capcut_export"
    )
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["timeline_id"] == timeline["timeline_id"]


def test_provider_trace_audit_timeline_filter_include_upstream_adds_segment_broll_and_music_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local preview operator copy.",
                    "action_items": ["Check the preview before handoff."],
                },
                raw_text='{"summary":"Local preview operator copy.","action_items":["Check the preview before handoff."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local export operator copy.",
                    "action_items": ["Validate the export package."],
                },
                raw_text='{"summary":"Local export operator copy.","action_items":["Validate the export package."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_result = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}")
    approve_response = client.post(f"/api/projects/{project_id}/review-approvals/{timeline_job_id}/approve")
    preview_response = client.post(
        f"/api/projects/{project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job_id},
    )
    export_response = client.post(
        f"/api/projects/{project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job_id},
    )

    assert review_snapshot.status_code == 200
    assert approve_response.status_code == 202
    assert preview_response.status_code == 202
    assert export_response.status_code == 202

    direct_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_result.json()["timeline"]["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert {entry["artifact_type"] for entry in direct_filtered.json()["entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in direct_filtered.json()["direct_entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert direct_filtered.json()["upstream_entries"] == []
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["entries"]} == {
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["direct_entries"]} == {
        "review_guidance",
        "preview_render",
        "capcut_export",
    }
    assert {entry["artifact_type"] for entry in upstream_filtered.json()["upstream_entries"]} == {
        "segment_analysis",
        "broll_recommendation",
        "music_recommendation",
    }
    assert len(upstream_filtered.json()["entries"]) == (
        len(upstream_filtered.json()["direct_entries"]) + len(upstream_filtered.json()["upstream_entries"])
    )
    assert next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "preview_render"
    )["status"] == "succeeded"
    assert next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "capcut_export"
    )["status"] == "succeeded"


def test_provider_trace_audit_timeline_filter_include_upstream_includes_failed_upstream_job(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Upstream Provenance Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    failed_broll_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.RUNNING,
    )
    failed_broll_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_broll_job["job_id"],
        status=JobStatus.FAILED,
        error_message="broll provider failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project.project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_broll_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_broll_job["job_id"],
            "source_job_id": segment_job["job_id"],
            "status": "failed",
            "finished_at": failed_broll_job["finished_at"],
            "error_message": "broll provider failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error"],
            ),
        },
    )
    music_run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BGM,
        source_job_id=segment_job["job_id"],
        recommendations=[
            {
                "recommendation_id": "bgm_rec_001",
                "target_segment_id": "seg_001",
                "selected_asset_id": None,
                "score": 0.8,
                "reason": "steady mood",
                "auto_apply_allowed": False,
                "review_required": False,
                "payload": {"provider_trace": build_provider_trace(final_provider="local_qwen")},
            }
        ],
    )
    music_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.MUSIC_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=music_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=music_run["recommendation_run_id"],
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    direct_filtered = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert direct_filtered.json()["entries"] == []
    failed_upstream = next(
        entry
        for entry in upstream_filtered.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "broll_recommendation"
    )
    assert failed_upstream["source_job_id"] == segment_job["job_id"]
    assert failed_upstream["provider_trace"]["final_provider"] == "gemini"


def test_timeline_build_persists_exact_recommendation_job_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    music_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "music_recommendation")

    timeline_path = tmp_path / "projects" / project_id / "timelines" / f'{timeline_payload["timeline_id"]}.json'
    persisted_payload = json.loads(timeline_path.read_text(encoding="utf-8"))

    assert persisted_payload["lineage"] == {
        "segment_analysis_job_id": segment_job_id,
        "recommendation_job_ids": [broll_job_id, music_job_id],
    }


def test_provider_trace_audit_include_upstream_uses_exact_persisted_recommendation_lineage_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    original_broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    sibling_broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    assert sibling_broll_job_id != original_broll_job_id

    direct_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"]},
    )
    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert direct_filtered.status_code == 200
    assert upstream_filtered.status_code == 200
    assert {entry["job_id"] for entry in direct_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == set()
    assert {entry["job_id"] for entry in upstream_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["upstream_entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["direct_entries"] if entry["artifact_type"] == "broll_recommendation"} == set()


def test_provider_trace_audit_include_upstream_falls_back_to_shared_segment_for_legacy_timelines_without_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office", "desk"]},
                raw_text='{"keywords":["office","desk"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]

    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")
    original_broll_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "broll_recommendation")
    sibling_broll_job_id = client.post(
        f"/api/projects/{project_id}/jobs/broll-recommendation",
        json={"segment_analysis_job_id": segment_job_id},
    ).json()["job_id"]

    timeline_path = tmp_path / "projects" / project_id / "timelines" / f'{timeline_payload["timeline_id"]}.json'
    persisted_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    persisted_payload.pop("lineage", None)
    timeline_path.write_text(json.dumps(persisted_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert upstream_filtered.status_code == 200
    assert {entry["job_id"] for entry in upstream_filtered.json()["entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
        sibling_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["upstream_entries"] if entry["artifact_type"] == "broll_recommendation"} == {
        original_broll_job_id,
        sibling_broll_job_id,
    }
    assert {entry["job_id"] for entry in upstream_filtered.json()["direct_entries"] if entry["artifact_type"] == "broll_recommendation"} == set()


def test_provider_trace_audit_include_upstream_excludes_failed_recommendation_not_in_exact_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": False, "cleanup_decision": "keep"},
                raw_text='{"review_required":false,"cleanup_decision":"keep"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Local review summary.",
                    "action_items": ["Approve the timeline now."],
                },
                raw_text='{"summary":"Local review summary.","action_items":["Approve the timeline now."]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    jobs_payload = client.get(f"/api/projects/{project_id}/jobs").json()["jobs"]
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]
    segment_job_id = next(job["job_id"] for job in jobs_payload if job["job_type"] == "segment_analysis")

    store = LocalProjectStore(tmp_path)
    failed_broll_job = store.create_job(
        project_id=project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job_id,
        status=JobStatus.RUNNING,
    )
    failed_broll_job = store.update_job(
        project_id=project_id,
        job_id=failed_broll_job["job_id"],
        status=JobStatus.FAILED,
        error_message="sibling broll failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_broll_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_broll_job["job_id"],
            "source_job_id": segment_job_id,
            "status": "failed",
            "finished_at": failed_broll_job["finished_at"],
            "error_message": "sibling broll failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error"],
            ),
        },
    )

    upstream_filtered = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "include_upstream": "true"},
    )

    assert upstream_filtered.status_code == 200
    assert failed_broll_job["job_id"] not in {
        entry["job_id"]
        for entry in upstream_filtered.json()["entries"]
        if entry["artifact_type"] == "broll_recommendation"
    }


def test_provider_trace_audit_timeline_filter_keeps_review_guidance_attempt_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Audit local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Audit local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()["timeline"]
    filtered_response = client.get(
        f"/api/projects/{project_id}/provider-traces",
        params={"timeline_id": timeline_payload["timeline_id"], "artifact_type": "review_guidance_attempt"},
    )

    assert review_snapshot.status_code == 500
    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance_attempt"]
    assert filtered_response.json()["entries"][0]["timeline_id"] == timeline_payload["timeline_id"]


def test_provider_trace_audit_timeline_filter_keeps_legacy_review_guidance_entry(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Filtered Guidance Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "operator_guidance_history": [
                {
                    "artifact_id": "timeline_001:review_guidance:001",
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "provider_trace": build_provider_trace(final_provider="local_qwen"),
                }
            ],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )

    client = TestClient(create_app(projects_root=tmp_path))
    filtered_response = client.get(
        f"/api/projects/{project.project_id}/provider-traces",
        params={"timeline_id": timeline["timeline_id"], "artifact_type": "review_guidance"},
    )

    assert filtered_response.status_code == 200
    assert [entry["artifact_type"] for entry in filtered_response.json()["entries"]] == ["review_guidance"]
    assert filtered_response.json()["entries"][0]["timeline_id"] == timeline["timeline_id"]
    assert filtered_response.json()["entries"][0]["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_backfills_legacy_records_without_complete_trace_data(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Trace Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id=segment_job["job_id"],
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.8,
                "reason": "Matched keywords: office",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"matched_tags": ["office"]},
            }
        ],
    )
    recommendation_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=recommendation_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="broll_001",
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_path = tmp_path / "projects" / project.project_id / "timelines" / "timeline_001.json"
    timeline_payload = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline_payload["operator_guidance"] = {
        "summary": "Legacy review guidance.",
        "action_items": ["Approve the timeline now."],
        "provider_trace": {
            "routing_mode": "local_first",
            "final_provider": "heuristic_fallback",
            "fallback_reasons": [],
        },
    }
    timeline_payload["operator_guidance_history"] = [
        {
            "artifact_id": "timeline_001:review_guidance:001",
            "created_at": timeline_payload["created_at"],
            "provider_trace": {
                "routing_mode": "local_first",
                "final_provider": "heuristic_fallback",
                "fallback_reasons": [],
            },
        }
    ]
    timeline_path.write_text(json.dumps(timeline_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    preview = store.save_preview_run(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        preview_payload={
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [],
            "notes": ["Legacy preview."],
        },
    )
    preview_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PREVIEW_RENDER,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=preview_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=preview["preview_id"],
    )
    export = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        export_payload={
            "timeline_id": timeline["timeline_id"],
            "adapter": "capcut_v1",
            "tracks": [],
            "notes": ["Legacy export."],
        },
    )
    export_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.CAPCUT_EXPORT,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=export_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=export["export_id"],
    )
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE segments SET metadata_json = '[]'")
        connection.execute("UPDATE recommendations SET payload_json = 'null'")
        connection.commit()
    finally:
        connection.close()
    preview_path = tmp_path / "projects" / project.project_id / "previews" / "preview_001.json"
    preview_payload = json.loads(preview_path.read_text(encoding="utf-8"))
    preview_payload.pop("provider_trace", None)
    preview_path.write_text(json.dumps(preview_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    export_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "exports"
        / "capcut"
        / "export_001"
        / "capcut_payload.json"
    )
    export_payload = json.loads(export_path.read_text(encoding="utf-8"))
    export_payload.pop("provider_trace", None)
    export_path.write_text(json.dumps(export_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = {entry["artifact_type"]: entry for entry in audit_response.json()["entries"]}
    assert entries["segment_analysis"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["broll_recommendation"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["review_guidance"]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert entries["preview_render"]["provider_trace"]["final_provider"] == "static_fallback"
    assert entries["capcut_export"]["provider_trace"]["final_provider"] == "static_fallback"


def test_provider_trace_audit_endpoint_tolerates_partial_artifact_and_log_corruption(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Corrupt Trace Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": {
                    "routing_mode": "local_first",
                    "final_provider": "local_qwen",
                    "fallback_reasons": [],
                },
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    preview = store.save_preview_run(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        preview_payload={
            "timeline_id": timeline["timeline_id"],
            "artifact_kind": "playable_html_preview",
            "clips": [],
            "notes": ["Corrupt preview."],
            "provider_trace": {
                "routing_mode": "local_first",
                "final_provider": "gemini",
                "fallback_reasons": ["local_provider_error"],
            },
        },
    )
    preview_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PREVIEW_RENDER,
        input_ref="timeline_build_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=preview_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=preview["preview_id"],
    )
    preview_path = tmp_path / "projects" / project.project_id / "previews" / "preview_001.json"
    preview_path.unlink()
    audit_log_path = tmp_path / "projects" / project.project_id / "logs" / "provider_trace_audit.jsonl"
    audit_log_path.write_text("{bad json}\n", encoding="utf-8")

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["artifact_type"] == "segment_analysis"
    assert entries[0]["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_includes_failed_segment_analysis_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Segment Audit Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["job_id"].startswith("segment_analysis_job_")
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["error_message"] == "local_first_router: segment provider failed"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": ["local_provider_error"],
    }


def test_provider_trace_audit_endpoint_includes_failed_gemini_fallback_recommendation_run(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Broll Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    runner = LocalPipelineRunner(store, broll_recommender=FailingBrollRecommender())

    with pytest.raises(LocalFirstStructuredGenerationError, match="broll Gemini fallback failed"):
        runner.start_broll_recommendation(
            project_id=project.project_id,
            segment_analysis_job_id=segment_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "broll_recommendation"
    )
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error", "gemini_unavailable"],
    }
    assert failed_entry["source_job_id"] == segment_job["job_id"]
    assert failed_entry["artifact_id"] == failed_entry["job_id"]


def test_provider_trace_audit_endpoint_uses_default_trace_for_failed_provider_job_without_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Music Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    runner = LocalPipelineRunner(store, music_recommender=FailingMusicRecommenderWithoutTrace())

    with pytest.raises(RuntimeError, match="music provider exploded without trace"):
        runner.start_music_recommendation(
            project_id=project.project_id,
            segment_analysis_job_id=segment_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "music_recommendation"
    )
    success_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "succeeded" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "unknown_failure",
        "fallback_reasons": ["missing_provider_trace"],
    }
    assert failed_entry["error_message"] == "music provider exploded without trace"
    assert success_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_endpoint_includes_failed_preview_render_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Preview Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="preview_render provider failed"):
        runner.start_preview_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "preview_render"
    )
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["provider_trace"]["final_provider"] == "gemini"


def test_provider_trace_audit_endpoint_includes_failed_capcut_export_without_output_ref(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Export Audit Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=FailingOutputOperatorCopyBuilder(),
    )

    with pytest.raises(LocalFirstStructuredGenerationError, match="capcut_export provider failed"):
        runner.start_capcut_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "capcut_export"
    )
    assert failed_entry["artifact_id"] == failed_entry["job_id"]
    assert failed_entry["source_job_id"] == timeline_job["job_id"]
    assert failed_entry["provider_trace"]["final_provider"] == "gemini"


def test_start_segment_analysis_marks_job_failed_without_provider_trace_for_missing_source_job(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Missing Source Segment Project")
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(KeyError, match="missing_transcription_job"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id="missing_transcription_job",
            script_asset_id=None,
        )

    jobs = store.list_jobs(project_id=project.project_id)
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "segment_analysis"
    assert jobs[0]["status"] == "failed"

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    assert not [
        entry
        for entry in audit_response.json()["entries"]
        if entry["job_type"] == "segment_analysis" and entry["status"] == "failed"
    ]


def test_provider_trace_audit_endpoint_uses_authoritative_failed_run_when_audit_log_append_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed Log Append Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )

    def fail_append(*, project_id: str, event: dict[str, object]) -> None:
        del project_id, event
        raise OSError("provider trace audit log offline")

    monkeypatch.setattr(store, "_append_provider_trace_audit_event", fail_append)
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["error_message"] == "local_first_router: segment provider failed"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": ["local_provider_error"],
    }


def test_provider_trace_audit_endpoint_backfills_partial_authoritative_failed_run_without_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Failed Persistence Project")
    failed_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.MUSIC_RECOMMENDATION,
        input_ref="segment_analysis_job_001",
        status=JobStatus.RUNNING,
    )
    failed_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_job["job_id"],
        status=JobStatus.FAILED,
        error_message="music provider exploded without trace",
    )

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_trace_failed_runs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                source_job_id TEXT,
                artifact_id TEXT,
                timeline_id TEXT,
                error_message TEXT,
                provider_trace_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_trace_failed_runs (
                job_id,
                project_id,
                job_type,
                source_job_id,
                artifact_id,
                timeline_id,
                error_message,
                provider_trace_json,
                created_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                failed_job["job_id"],
                project.project_id,
                "music_recommendation",
                "segment_analysis_job_001",
                failed_job["job_id"],
                None,
                "music provider exploded without trace",
                None,
                "2026-06-29T00:00:00+00:00",
                failed_job["finished_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "music_recommendation"
    )
    assert failed_entry["artifact_id"] == failed_job["job_id"]
    assert failed_entry["error_message"] == "music provider exploded without trace"
    assert failed_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "unknown_failure",
        "fallback_reasons": ["missing_provider_trace"],
    }


def test_provider_trace_audit_endpoint_deduplicates_failed_run_between_authoritative_store_and_log(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Deduplicated Failed Run Project")
    failed_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.BROLL_RECOMMENDATION,
        input_ref="segment_analysis_job_001",
        status=JobStatus.RUNNING,
    )
    failed_job = store.update_job(
        project_id=project.project_id,
        job_id=failed_job["job_id"],
        status=JobStatus.FAILED,
        error_message="local_first_router: broll Gemini fallback failed",
    )
    store.save_provider_trace_audit_event(
        project_id=project.project_id,
        event={
            "artifact_type": "broll_recommendation",
            "artifact_id": failed_job["job_id"],
            "job_type": "broll_recommendation",
            "job_id": failed_job["job_id"],
            "source_job_id": "segment_analysis_job_001",
            "status": "failed",
            "finished_at": failed_job["finished_at"],
            "error_message": "local_first_router: broll Gemini fallback failed",
            "provider_trace": build_provider_trace(
                final_provider="gemini",
                fallback_reasons=["local_provider_error", "gemini_unavailable"],
            ),
        },
    )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entries = [
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_id"] == failed_job["job_id"]
    ]
    assert len(failed_entries) == 1
    assert failed_entries[0]["provider_trace"]["final_provider"] == "gemini"


def test_provider_trace_audit_endpoint_falls_back_to_log_when_authoritative_failed_run_persist_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Failed SQLite Persist Project")
    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id="asset_001",
        transcript_text="Office overview.",
        segments=[
            {
                "start_sec": 0.0,
                "end_sec": 1.0,
                "text": "Office overview.",
                "confidence": 0.99,
            }
        ],
    )
    transcription_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=transcription_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=transcript["transcript_id"],
    )

    def fail_authoritative_persist(*, project_id: str, event: dict[str, object]) -> None:
        del project_id, event
        raise sqlite3.OperationalError("failed runs table locked")

    monkeypatch.setattr(store, "_save_failed_provider_trace_run", fail_authoritative_persist)
    runner = LocalPipelineRunner(store, segment_analyzer=FailingSegmentAnalyzer())

    with pytest.raises(LocalFirstStructuredGenerationError, match="segment provider failed"):
        runner.start_segment_analysis(
            project_id=project.project_id,
            transcription_job_id=transcription_job["job_id"],
            script_asset_id=None,
        )

    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    failed_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["status"] == "failed" and entry["job_type"] == "segment_analysis"
    )
    assert failed_entry["provider_trace"]["final_provider"] == "local_qwen"


def test_provider_trace_audit_read_path_does_not_require_failed_run_schema_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Read Only Audit Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )

    def fail_schema_mutation(self, *, project_id: str) -> None:  # noqa: ANN001
        del self, project_id
        raise AssertionError("read path must not mutate failed-run schema")

    monkeypatch.setattr(LocalProjectStore, "_ensure_provider_trace_failed_runs_table", fail_schema_mutation)
    client = TestClient(create_app(projects_root=tmp_path))
    audit_response = client.get(f"/api/projects/{project.project_id}/provider-traces")

    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["artifact_type"] == "segment_analysis"


def test_provider_trace_audit_endpoint_includes_review_guidance_attempt_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Audit local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Audit local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["job_id"] == timeline_job_id
    assert attempt_entry["source_job_id"] == timeline_job_id
    assert attempt_entry["timeline_id"]
    assert attempt_entry["status"] == "unpersisted"
    assert attempt_entry["error_message"] == "review guidance persistence offline"
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "local_qwen",
        "fallback_reasons": [],
    }


def test_provider_trace_audit_endpoint_reflects_heuristic_review_guidance_fallback_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )
    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "heuristic_fallback",
        "fallback_reasons": ["unexpected_runtime_failure"],
    }


def test_provider_trace_audit_endpoint_keeps_gemini_review_guidance_attempt_when_guidance_is_not_persisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        errors=[
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
            LLMProviderError(
                provider_name="local_qwen",
                message="local unavailable",
                retryable=True,
                error_code="LOCAL_UNAVAILABLE",
            ),
        ]
    )
    gemini_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash-lite",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="gemini",
                model_name="gemini-2.5-flash",
                output_data={
                    "summary": "Unpersisted Gemini review summary.",
                    "action_items": ["Resolve flagged review items"],
                },
                raw_text='{"summary":"Unpersisted Gemini review summary.","action_items":["Resolve flagged review items"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=gemini_provider,
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    gemini_key_payload = {
        "label": "Unpersisted Review Gemini",
        "api_key": "AIza-unpersisted-review",
        "primary_model": "gemini-2.5-flash",
        "cheap_model": "gemini-2.5-flash-lite",
        "high_quality_model": "gemini-2.5-pro",
    }
    project_id, timeline_job_id = _create_timeline_review_project(
        client,
        tmp_path,
        gemini_key_payload=gemini_key_payload,
    )

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entry = next(
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    )
    assert attempt_entry["job_id"] == timeline_job_id
    assert attempt_entry["provider_trace"] == {
        "routing_mode": "local_first",
        "final_provider": "gemini",
        "fallback_reasons": ["local_provider_error"],
    }


def test_review_snapshot_tolerates_review_guidance_audit_append_failure_without_unpersisted_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_append(self, *, project_id: str, event: dict[str, object]) -> None:  # noqa: ANN001
        del self, project_id
        if str(event.get("artifact_type") or "") == "review_guidance":
            raise OSError("review guidance audit log offline")

    monkeypatch.setattr(LocalProjectStore, "_append_provider_trace_audit_event", fail_append)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Append failure local review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Append failure local review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    review_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert review_snapshot.status_code == 200
    assert audit_response.status_code == 200
    artifact_types = [entry["artifact_type"] for entry in audit_response.json()["entries"]]
    assert "review_guidance" in artifact_types
    assert "review_guidance_attempt" not in artifact_types


def test_provider_trace_audit_endpoint_deduplicates_repeated_unpersisted_review_guidance_attempts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.stt.MockSTTProvider.transcribe",
        _single_segment_transcribe,
    )

    def fail_save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, object],
    ) -> dict[str, object]:
        del self, project_id, timeline_id, operator_guidance
        raise OSError("review guidance persistence offline")

    monkeypatch.setattr(LocalProjectStore, "save_operator_guidance", fail_save_operator_guidance)
    local_provider = FakeStructuredProvider(
        responses=[
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"review_required": True, "cleanup_decision": "review"},
                raw_text='{"review_required":true,"cleanup_decision":"review"}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"keywords": ["office"]},
                raw_text='{"keywords":["office"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={"music_mood": "cinematic pulse", "score": 0.91},
                raw_text='{"music_mood":"cinematic pulse","score":0.91}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Retry one review summary.",
                    "action_items": ["Check seg_001 narration alignment"],
                },
                raw_text='{"summary":"Retry one review summary.","action_items":["Check seg_001 narration alignment"]}',
                metadata={},
            ),
            StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="Qwen3-32B",
                output_data={
                    "summary": "Retry two review summary.",
                    "action_items": ["Check seg_001 narration alignment again"],
                },
                raw_text='{"summary":"Retry two review summary.","action_items":["Check seg_001 narration alignment again"]}',
                metadata={},
            ),
        ]
    )
    app = create_app(
        projects_root=tmp_path,
        local_first_runtime_service_factory=_local_first_service_factory(
            local_provider=local_provider,
            gemini_provider=FakeStructuredProvider(),
            local_enabled=True,
        ),
    )
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)

    first_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    second_snapshot = client.get(f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}")
    audit_response = client.get(f"/api/projects/{project_id}/provider-traces")

    assert first_snapshot.status_code == 500
    assert second_snapshot.status_code == 500
    assert audit_response.status_code == 200
    attempt_entries = [
        entry
        for entry in audit_response.json()["entries"]
        if entry["artifact_type"] == "review_guidance_attempt"
    ]
    assert len(attempt_entries) == 1
