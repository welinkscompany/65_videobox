from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen

from videobox_core_engine.gemini_runtime import GeminiStructuredRuntime
from videobox_core_engine.local_first_runtime import LocalFirstStructuredRuntime
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.local_qwen import LocalQwenHTTPTransport, LocalQwenStructuredProvider
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMResponse,
)
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


@dataclass(slots=True, frozen=True)
class RegisteredAsset:
    asset_id: str
    asset_type: str
    storage_uri: str


@dataclass(slots=True)
class GeminiRuntimeService:
    store: LocalProjectStore
    provider: StructuredLLMProvider
    provider_config: LLMProviderConfig
    cooldown_seconds: int = 180

    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        runtime = GeminiStructuredRuntime(
            store=self.store,
            provider=self.provider,
            provider_config=self.provider_config,
            cooldown_seconds=self.cooldown_seconds,
        )
        return runtime.generate(
            project_id=project_id,
            task_type=task_type,
            prompt=prompt,
            response_schema=response_schema,
            now=now,
        )


@dataclass(slots=True)
class LocalFirstRuntimeService:
    store: LocalProjectStore
    local_provider: StructuredLLMProvider
    gemini_provider: StructuredLLMProvider
    local_config: LLMProviderConfig
    gemini_config: LLMProviderConfig
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig = field(
        default_factory=LocalOpenAICompatibleRuntimeConfig
    )
    cooldown_seconds: int = 180

    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        runtime = LocalFirstStructuredRuntime(
            store=self.store,
            local_provider=self.local_provider,
            gemini_provider=self.gemini_provider,
            local_config=self.local_config,
            gemini_config=self.gemini_config,
            local_runtime_config=self.local_runtime_config,
            cooldown_seconds=self.cooldown_seconds,
        )
        return runtime.generate(
            project_id=project_id,
            task_type=task_type,
            prompt=prompt,
            response_schema=response_schema,
            now=now,
        )


def build_local_qwen_structured_provider(
    *,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig,
    local_http_client: Callable[..., Any],
) -> LocalQwenStructuredProvider:
    transport = LocalQwenHTTPTransport(
        base_url=local_runtime_config.base_url,
        timeout_seconds=local_runtime_config.timeout_seconds,
        http_client=local_http_client,
    )
    return LocalQwenStructuredProvider(transport=transport)


def build_local_first_runtime_service(
    *,
    store: LocalProjectStore,
    gemini_provider: StructuredLLMProvider,
    gemini_config: LLMProviderConfig,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig,
    local_http_client: Callable[..., Any] = urlopen,
    local_config: LLMProviderConfig | None = None,
    cooldown_seconds: int = 180,
) -> LocalFirstRuntimeService:
    resolved_local_config = local_config or LLMProviderConfig(
        provider_name="local_qwen",
        enabled=local_runtime_config.enabled,
        timeout_seconds=local_runtime_config.timeout_seconds,
    )
    if resolved_local_config.enabled != local_runtime_config.enabled:
        raise ValueError("local_config.enabled must match local_runtime_config.enabled.")
    if resolved_local_config.timeout_seconds != local_runtime_config.timeout_seconds:
        raise ValueError("local_config.timeout_seconds must match local_runtime_config.timeout_seconds.")
    return LocalFirstRuntimeService(
        store=store,
        local_provider=build_local_qwen_structured_provider(
            local_runtime_config=local_runtime_config,
            local_http_client=local_http_client,
        ),
        gemini_provider=gemini_provider,
        local_config=resolved_local_config,
        gemini_config=gemini_config,
        local_runtime_config=local_runtime_config,
        cooldown_seconds=cooldown_seconds,
    )


class ApiOrchestrator:
    def __init__(self, store: LocalProjectStore, *, pipeline: LocalPipelineRunner | None = None) -> None:
        self.store = store
        self.pipeline = pipeline or LocalPipelineRunner(store)

    def register_narration_audio(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_narration_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_script_document(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_script_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_broll_asset(
        self,
        *,
        project_id: str,
        source_path: Path,
        title: str | None,
        tags: list[str],
    ) -> RegisteredAsset:
        asset = self.pipeline.register_broll_asset(
            project_id=project_id,
            source_path=source_path,
            title=title,
            tags=tags,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def start_transcription(self, *, project_id: str, narration_asset_id: str) -> dict[str, Any]:
        result = self.pipeline.start_transcription(
            project_id=project_id,
            narration_asset_id=narration_asset_id,
        )
        transcription = self.pipeline.get_transcription_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": transcription["transcript_uri"],
        }

    def get_transcription_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_transcription_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "transcript_uri": result["transcript_uri"],
        }

    def start_segment_analysis(
        self,
        *,
        project_id: str,
        transcription_job_id: str,
        script_asset_id: str | None,
    ) -> dict[str, Any]:
        result = self.pipeline.start_segment_analysis(
            project_id=project_id,
            transcription_job_id=transcription_job_id,
            script_asset_id=script_asset_id,
        )
        analysis = self.pipeline.get_segment_analysis_result(
            project_id=project_id,
            job_id=result["job_id"],
        )
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments_uri": analysis["file_uri"],
        }

    def get_segment_analysis_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_segment_analysis_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "segments": result["segments"],
        }

    def start_broll_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_broll_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_broll_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_broll_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "broll",
            "recommendations": result["recommendations"],
        }

    def start_music_recommendation(self, *, project_id: str, segment_analysis_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_music_recommendation(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
        )

    def get_music_recommendation_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        result = self.pipeline.get_music_recommendation_result(project_id=project_id, job_id=job_id)
        return {
            "job_id": result["job_id"],
            "status": result["status"],
            "recommendation_type": "bgm",
            "recommendations": result["recommendations"],
        }

    def build_timeline(
        self,
        *,
        project_id: str,
        segment_analysis_job_id: str,
        recommendation_job_ids: list[str],
    ) -> dict[str, Any]:
        return self.pipeline.build_timeline(
            project_id=project_id,
            segment_analysis_job_id=segment_analysis_job_id,
            recommendation_job_ids=recommendation_job_ids,
        )

    def get_timeline_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_timeline_result(project_id=project_id, job_id=job_id)

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_review_snapshot(project_id=project_id, job_id=job_id)

    def approve_timeline_review(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.approve_timeline_review(project_id=project_id, timeline_job_id=job_id)

    def reopen_timeline_review(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.reopen_timeline_review(project_id=project_id, timeline_job_id=job_id)

    def start_subtitle_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_subtitle_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_subtitle_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_subtitle_result(project_id=project_id, job_id=job_id)

    def start_preview_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_preview_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_preview_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_preview_result(project_id=project_id, job_id=job_id)

    def start_capcut_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_export(project_id=project_id, timeline_job_id=timeline_job_id)

    def get_capcut_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_capcut_export_result(project_id=project_id, job_id=job_id)

    def get_provider_trace_audit(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.store.get_provider_trace_audit(
            project_id=project_id,
            timeline_id=timeline_id,
            include_upstream=include_upstream,
            job_type=job_type,
            artifact_type=artifact_type,
            final_provider=final_provider,
            fallback_reason=fallback_reason,
        )

    def list_gemini_provider_keys(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.pipeline.store.list_gemini_provider_keys(project_id=project_id)

    def save_gemini_provider_key(
        self,
        *,
        project_id: str,
        label: str,
        api_key_secret: str,
        primary_model: str,
        cheap_model: str,
        high_quality_model: str,
    ) -> dict[str, Any]:
        return self.pipeline.store.save_gemini_provider_key(
            project_id=project_id,
            label=label,
            api_key_secret=api_key_secret,
            primary_model=primary_model,
            cheap_model=cheap_model,
            high_quality_model=high_quality_model,
        )

    def update_gemini_provider_key(
        self,
        *,
        project_id: str,
        key_id: str,
        label: str | None = None,
        primary_model: str | None = None,
        cheap_model: str | None = None,
        high_quality_model: str | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.store.update_gemini_provider_key(
            project_id=project_id,
            key_id=key_id,
            label=label,
            primary_model=primary_model,
            cheap_model=cheap_model,
            high_quality_model=high_quality_model,
        )

    def set_gemini_provider_key_status(
        self,
        *,
        project_id: str,
        key_id: str,
        status: str,
    ) -> dict[str, Any]:
        return self.pipeline.store.set_gemini_provider_key_status(
            project_id=project_id,
            key_id=key_id,
            status=status,
        )
