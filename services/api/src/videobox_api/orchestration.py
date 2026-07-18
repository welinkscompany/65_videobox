from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen

from videobox_core_engine.gemini_runtime import GeminiStructuredRuntime
from videobox_core_engine.local_first_runtime import LocalFirstStructuredRuntime
from videobox_core_engine.local_only_runtime import (
    LocalOnlyStructuredGenerationError,
    LocalOnlyStructuredRuntime,
)
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.local_qwen import LocalQwenHTTPTransport, LocalQwenStructuredProvider
from videobox_provider_interfaces.llm import (
    LLMProviderConfig,
    LLMProviderError,
    LLMTaskType,
    StructuredLLMProvider,
    StructuredLLMResponse,
)
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.creation_interview import CreationInterviewRuntime, DeterministicCreationInterviewRuntime
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

BROLL_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


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


@dataclass(slots=True)
class LocalOnlyRuntimeService:
    local_provider: StructuredLLMProvider
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig = field(
        default_factory=LocalOpenAICompatibleRuntimeConfig
    )

    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: datetime | None = None,
    ) -> StructuredLLMResponse:
        del now
        try:
            return LocalOnlyStructuredRuntime(
                local_provider=self.local_provider,
                local_runtime_config=self.local_runtime_config,
            ).generate(
                project_id=project_id,
                task_type=task_type,
                prompt=prompt,
                response_schema=response_schema,
            )
        except LocalOnlyStructuredGenerationError as exc:
            raise LocalOnlyRuntimeProviderError(
                provider_name=exc.provider_name,
                message=exc.message,
                retryable=False,
                error_code=exc.error_code,
                provider_trace=exc.provider_trace,
            ) from exc


@dataclass(slots=True, frozen=True)
class LocalOnlyRuntimeProviderError(LLMProviderError):
    provider_trace: dict[str, Any] = field(default_factory=dict)


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


def build_local_only_runtime_service(
    *,
    store: LocalProjectStore,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig,
    local_http_client: Callable[..., Any] = urlopen,
) -> LocalOnlyRuntimeService:
    del store
    return LocalOnlyRuntimeService(
        local_provider=build_local_qwen_structured_provider(
            local_runtime_config=local_runtime_config,
            local_http_client=local_http_client,
        ),
        local_runtime_config=local_runtime_config,
    )


class ApiOrchestrator:
    def __init__(
        self, store: LocalProjectStore, *, pipeline: LocalPipelineRunner | None = None,
        creation_interview_runtime: CreationInterviewRuntime | None = None,
    ) -> None:
        self.store = store
        self.pipeline = pipeline or LocalPipelineRunner(store)
        # This is intentionally a provider-neutral local planning seam. No
        # LLM/provider transport is constructed for an interview.
        self.creation_interview_runtime = creation_interview_runtime or DeterministicCreationInterviewRuntime()

    def create_creation_brief(self, **kwargs: Any) -> dict[str, Any]:
        return self.pipeline.create_creation_brief(runtime=self.creation_interview_runtime, **kwargs)

    def start_draft_readiness(self, **kwargs: Any) -> dict[str, Any]:
        # Readiness is deterministic local storage planning only; it never
        # constructs a provider transport or editing-session mutation path.
        return self.store.start_draft_readiness(**kwargs)

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

    def list_broll_assets(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)

    def list_voice_sample_assets(self, *, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_assets(project_id=project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO)

    def register_sfx_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_sfx_asset(project_id=project_id, source_path=source_path)
        return RegisteredAsset(asset_id=asset["asset_id"], asset_type=asset["asset_type"], storage_uri=asset["storage_uri"])

    def register_broll_assets_batch(
        self,
        *,
        project_id: str,
        source_paths: list[Path],
        source_directory: Path | None,
        tags: list[str],
        title_by_source_path: dict[str, str],
        recursive: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        paths, failures = self._resolve_broll_batch_paths(
            source_paths=source_paths,
            source_directory=source_directory, recursive=recursive,
        )
        registered_asset_ids: list[str] = []
        source_by_asset_id: dict[str, str] = {}
        for source_path in paths:
            try:
                asset = self.pipeline.register_broll_asset(
                    project_id=project_id,
                    source_path=source_path,
                    title=title_by_source_path.get(str(source_path)) or source_path.stem,
                    tags=tags,
                )
            except Exception as exc:
                # A bad file must not roll back assets already accepted in this batch.
                failures.append({"source_path": str(source_path.resolve()), "reason": str(exc)})
                continue
            registered_asset_ids.append(asset["asset_id"])
            source_by_asset_id[asset["asset_id"]] = str(source_path.resolve())
        assets_by_id = {
            asset["asset_id"]: asset
            for asset in self.store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        }
        return {"assets": [{**assets_by_id[asset_id], "source_path": source_by_asset_id.get(asset_id)} for asset_id in registered_asset_ids if asset_id in assets_by_id], "failures": failures}

    def _resolve_broll_batch_paths(
        self,
        *,
        source_paths: list[Path],
        source_directory: Path | None, recursive: bool = False,
    ) -> tuple[list[Path], list[dict[str, str]]]:
        paths: list[Path] = []
        if source_directory is not None:
            if not source_directory.exists():
                raise ValueError(f"B-roll source directory does not exist: {source_directory}")
            if not source_directory.is_dir():
                raise ValueError(f"B-roll source directory is not a directory: {source_directory}")
            iterator = source_directory.rglob("*") if recursive else source_directory.iterdir()
            paths.extend(sorted((candidate for candidate in iterator if candidate.is_file() and candidate.suffix.lower() in BROLL_VIDEO_EXTENSIONS), key=lambda path: str(path.resolve()).lower()))
        paths.extend(source_paths)
        if not paths:
            raise ValueError("No B-roll video files found for batch import.")
        unique_paths: list[Path] = []
        failures: list[dict[str, str]] = []
        seen: set[Path] = set()
        seen_content: set[str] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            from videobox_storage.local_project_store import sha256_file
            if not resolved.exists() or not resolved.is_file():
                failures.append({"source_path": str(resolved), "reason": "source file does not exist"})
                continue
            if resolved.suffix.lower() not in BROLL_VIDEO_EXTENSIONS:
                failures.append({"source_path": str(resolved), "reason": "unsupported video extension"})
                continue
            if resolved.exists() and resolved.is_file():
                digest = sha256_file(resolved)
                if digest in seen_content:
                    continue
                seen_content.add(digest)
            unique_paths.append(resolved)
        if not unique_paths and not failures:
            raise ValueError("No B-roll video files found for batch import.")
        return unique_paths, failures

    def register_raw_video_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_raw_video_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def register_voice_sample_asset(self, *, project_id: str, source_path: Path) -> RegisteredAsset:
        asset = self.pipeline.register_voice_sample_asset(
            project_id=project_id,
            source_path=source_path,
        )
        return RegisteredAsset(
            asset_id=asset["asset_id"],
            asset_type=asset["asset_type"],
            storage_uri=asset["storage_uri"],
        )

    def generate_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        segment_text: str,
        voice_sample_asset_id: str,
        segment_id: str | None = None,
        target_duration_sec: float | None = None,
    ) -> dict[str, Any]:
        return self.pipeline.generate_tts_replacement_candidate(
            project_id=project_id,
            segment_text=segment_text,
            voice_sample_asset_id=voice_sample_asset_id,
            segment_id=segment_id,
            target_duration_sec=target_duration_sec,
        )

    def list_tts_replacement_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        return self.pipeline.list_tts_replacement_candidates(project_id=project_id, segment_id=segment_id)

    def review_tts_replacement_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        return self.pipeline.review_tts_replacement_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            decision=decision,
        )

    def plan_auto_cut_segments(
        self,
        *,
        project_id: str,
        raw_video_asset_id: str,
        total_duration: float,
        scene_timestamps: list[float],
        black_regions: list[dict[str, float]],
        segment_samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.pipeline.plan_auto_cut_segments(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
            total_duration=total_duration,
            scene_timestamps=scene_timestamps,
            black_regions=black_regions,
            segment_samples=segment_samples,
        )

    def run_auto_cut_detection(self, *, project_id: str, raw_video_asset_id: str) -> dict[str, Any]:
        return self.pipeline.run_auto_cut_detection(
            project_id=project_id,
            raw_video_asset_id=raw_video_asset_id,
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

    def create_editing_session(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.create_editing_session(project_id=project_id, timeline_job_id=timeline_job_id)

    def create_script_draft_editing_session(self, *, project_id: str, script_asset_id: str) -> dict[str, Any]:
        return self.pipeline.create_script_draft_editing_session(project_id=project_id, script_asset_id=script_asset_id)

    def apply_script_draft_narration_alignment(self, *, project_id: str, session_id: str, aligned_segments: list[dict[str, Any]], expected_revision: int) -> dict[str, Any]:
        return self.pipeline.apply_script_draft_narration_alignment(project_id=project_id, session_id=session_id, aligned_segments=aligned_segments, expected_revision=expected_revision)

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.pipeline.get_editing_session(project_id=project_id, session_id=session_id)

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        return self.pipeline.get_latest_editing_session(project_id=project_id)

    def get_editing_session_fixed_timeline(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        return self.pipeline.get_editing_session_fixed_timeline(project_id=project_id, session_id=session_id)

    def preview_editing_session_selected_range(self, *, project_id: str, session_id: str, start_sec: float, end_sec: float) -> dict[str, Any]:
        return self.pipeline.preview_editing_session_selected_range(project_id=project_id, session_id=session_id, start_sec=start_sec, end_sec=end_sec)

    def split_editing_session_segment(self, *, project_id: str, session_id: str, segment_id: str, split_sec: float, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.split_editing_session_segment(project_id=project_id, session_id=session_id, segment_id=segment_id, split_sec=split_sec, expected_revision=expected_revision)

    def merge_editing_session_segments(self, *, project_id: str, session_id: str, left_segment_id: str, right_segment_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.merge_editing_session_segments(project_id=project_id, session_id=session_id, left_segment_id=left_segment_id, right_segment_id=right_segment_id, expected_revision=expected_revision)

    def set_editing_session_segment_bounds(self, *, project_id: str, session_id: str, segment_id: str, start_sec: float, end_sec: float, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.set_editing_session_segment_bounds(project_id=project_id, session_id=session_id, segment_id=segment_id, start_sec=start_sec, end_sec=end_sec, expected_revision=expected_revision)

    def reorder_editing_session_segments(self, *, project_id: str, session_id: str, segment_ids: list[str], bounds_by_id: dict[str, dict[str, float]] | None, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.reorder_editing_session_segments(project_id=project_id, session_id=session_id, segment_ids=segment_ids, bounds_by_id=bounds_by_id, expected_revision=expected_revision)

    def undo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.undo_editing_session(project_id=project_id, session_id=session_id, expected_revision=expected_revision)

    def redo_editing_session(self, *, project_id: str, session_id: str, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.redo_editing_session(project_id=project_id, session_id=session_id, expected_revision=expected_revision)

    def preview_caption_style_scope(self, *, project_id: str, session_id: str, scope: str, segment_ids: list[str]) -> dict[str, Any]:
        return self.pipeline.preview_editing_session_caption_style_scope(project_id=project_id, session_id=session_id, scope=scope, segment_ids=segment_ids)

    def update_caption_style(self, *, project_id: str, session_id: str, style: dict[str, Any], scope: str, segment_ids: list[str], expected_revision: int) -> dict[str, Any]:
        return self.pipeline.update_editing_session_caption_style(project_id=project_id, session_id=session_id, style=style, scope=scope, segment_ids=segment_ids, expected_revision=expected_revision)

    def update_segment_caption(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        caption_text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_caption(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            caption_text=caption_text,
            expected_revision=expected_revision,
        )

    def update_segment_cut_action(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        cut_action: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_cut_action(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            cut_action=cut_action,
            expected_revision=expected_revision,
        )

    def update_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_broll_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            media_controls=media_controls,
            expected_revision=expected_revision,
        )

    def update_segment_sfx_override(self, *, project_id: str, session_id: str, segment_id: str, asset_id: str, media_controls: dict[str, Any] | None = None, expected_revision: int) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_sfx_override(project_id=project_id, session_id=session_id, segment_id=segment_id, asset_id=asset_id, media_controls=media_controls, expected_revision=expected_revision)

    def clear_segment_sfx_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_sfx_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def clear_segment_broll_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_broll_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def build_editing_session_partial_regeneration_request(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
    ) -> dict[str, Any]:
        return self.pipeline.build_editing_session_partial_regeneration_request(
            project_id=project_id,
            session_id=session_id,
            segment_ids=segment_ids,
            fields=fields,
        )

    def start_editing_session_partial_regeneration(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_ids: list[str],
        fields: list[str],
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.start_editing_session_partial_regeneration(
            project_id=project_id,
            session_id=session_id,
            segment_ids=segment_ids,
            fields=fields,
            expected_revision=expected_revision,
        )

    def get_partial_regeneration_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_partial_regeneration_result(project_id=project_id, job_id=job_id)

    def update_segment_visual_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        overlay_type: str,
        asset_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_visual_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            overlay_type=overlay_type,
            asset_id=asset_id,
            expected_revision=expected_revision,
        )

    def clear_segment_visual_overlays(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_visual_overlays(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        title: str,
        body: str,
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_explanation_card(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            title=title,
            body=body,
            text=text,
            expected_revision=expected_revision,
        )

    def remove_segment_explanation_card(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_explanation_card(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_image_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            text=text,
            expected_revision=expected_revision,
        )

    def update_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        columns: list[str],
        rows: list[list[str]],
        text: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_table_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            columns=columns,
            rows=rows,
            text=text,
            expected_revision=expected_revision,
        )

    def remove_segment_image_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_image_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def remove_segment_table_overlay(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.remove_editing_session_segment_table_overlay(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def update_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        asset_id: str,
        media_controls: dict[str, Any] | None = None,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.update_editing_session_segment_music_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            asset_id=asset_id,
            media_controls=media_controls,
            expected_revision=expected_revision,
        )

    def clear_segment_music_override(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_music_override(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def select_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        recommendation_id: str,
        asset_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.select_editing_session_segment_tts_replacement(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            recommendation_id=recommendation_id,
            asset_id=asset_id,
            expected_revision=expected_revision,
        )

    def clear_segment_tts_replacement(
        self,
        *,
        project_id: str,
        session_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        return self.pipeline.clear_editing_session_segment_tts_replacement(
            project_id=project_id,
            session_id=session_id,
            segment_id=segment_id,
            expected_revision=expected_revision,
        )

    def get_review_snapshot(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_review_snapshot(project_id=project_id, job_id=job_id)

    def approve_pending_recommendation(
        self,
        *,
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        return self.pipeline.approve_pending_recommendation(
            project_id=project_id,
            timeline_job_id=job_id,
            recommendation_id=recommendation_id,
        )

    def reject_pending_recommendation(
        self,
        *,
        project_id: str,
        job_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        return self.pipeline.reject_pending_recommendation(
            project_id=project_id,
            timeline_job_id=job_id,
            recommendation_id=recommendation_id,
        )

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

    def start_final_render(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_final_render(project_id=project_id, timeline_job_id=timeline_job_id)

    def start_final_render_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id)

    def run_final_render_job(self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]) -> None:
        self.pipeline.run_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id, job=job)

    def get_final_render_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_final_render_result(project_id=project_id, job_id=job_id)

    def start_capcut_draft_export(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_draft_export(project_id=project_id, timeline_job_id=timeline_job_id)

    def start_capcut_draft_export_job(self, *, project_id: str, timeline_job_id: str) -> dict[str, Any]:
        return self.pipeline.start_capcut_draft_export_job(project_id=project_id, timeline_job_id=timeline_job_id)

    def run_capcut_draft_export_job(
        self, *, project_id: str, timeline_job_id: str, job: dict[str, Any]
    ) -> None:
        self.pipeline.run_capcut_draft_export_job(
            project_id=project_id, timeline_job_id=timeline_job_id, job=job
        )

    def get_capcut_draft_export_result(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.get_capcut_draft_export_result(project_id=project_id, job_id=job_id)

    def register_capcut_draft_handoff(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        return self.pipeline.register_capcut_draft_handoff(project_id=project_id, job_id=job_id)

    def get_capcut_handoff_diagnostics(self) -> dict[str, Any]:
        return self.pipeline.get_capcut_handoff_diagnostics()

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

    # Job types whose start_* call takes exactly one input_ref-shaped kwarg,
    # so a failed run can be retried generically from the stored job record
    # alone. TIMELINE_BUILD (needs recommendation_job_ids too), SEGMENT_ANALYSIS
    # (needs an optional script_asset_id), and PARTIAL_REGENERATION (needs
    # session_id/segment_ids/fields) carry extra parameters that aren't
    # recoverable from input_ref alone, so they're intentionally excluded —
    # those must be re-triggered manually with their full original request.
    _RETRYABLE_JOB_DISPATCH: dict[str, tuple[str, str]] = {
        "transcription": ("start_transcription", "narration_asset_id"),
        "broll_recommendation": ("start_broll_recommendation", "segment_analysis_job_id"),
        "music_recommendation": ("start_music_recommendation", "segment_analysis_job_id"),
        "subtitle_render": ("start_subtitle_render", "timeline_job_id"),
        "preview_render": ("start_preview_render", "timeline_job_id"),
        "capcut_export": ("start_capcut_export", "timeline_job_id"),
        "final_render": ("start_final_render_job", "timeline_job_id"),
        "capcut_draft_export": ("start_capcut_draft_export_job", "timeline_job_id"),
    }

    def retry_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(project_id=project_id, job_id=job_id)
        if job["status"] != "failed":
            raise ValueError(f"Job '{job_id}' is not in a failed state and cannot be retried.")
        job_type = str(job["job_type"])
        dispatch = self._RETRYABLE_JOB_DISPATCH.get(job_type)
        if dispatch is None:
            raise ValueError(
                f"Job type '{job_type}' cannot be retried automatically; "
                "restart it with its original request instead."
            )
        method_name, input_kwarg = dispatch
        if not job["input_ref"]:
            raise ValueError(f"Job '{job_id}' has no input_ref recorded and cannot be retried.")
        method = getattr(self, method_name)
        result = method(project_id=project_id, **{input_kwarg: job["input_ref"]})
        return {"job_type": job_type, "input_ref": job["input_ref"], **result}
