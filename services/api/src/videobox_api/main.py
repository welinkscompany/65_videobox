from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

from fastapi import FastAPI

from videobox_api.orchestration import ApiOrchestrator, build_local_first_runtime_service
from videobox_api.provider_factories import _build_pycapcut_exporter, _build_stt_provider, _build_tts_provider
from videobox_api.response_normalizers import (
    _build_preflight_review_prediction,
    _build_targeted_segments,
    _normalize_recommendations_for_response,
    _normalize_review_flags_for_response,
)
from videobox_api.routers.assets import build_assets_router
from videobox_api.routers.editing_session import build_editing_session_router
from videobox_api.routers.editor_library import build_editor_library_router
from videobox_api.routers.gemini_keys import build_gemini_keys_router
from videobox_api.routers.jobs import build_jobs_router
from videobox_api.routers.outputs import build_outputs_router
from videobox_api.routers.projects import build_projects_router
from videobox_api.routers.review import build_review_router
from videobox_api.routers.timeline import build_timeline_router
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_operator_copy import LocalFirstOutputOperatorCopyBuilder
from videobox_core_engine.recommenders import LocalFirstKeywordBrollRecommender, LocalFirstMusicRecommender
from videobox_core_engine.review_guidance import LocalFirstReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import LocalFirstSegmentAnalyzer
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    AutoCutConfig,
    CapCutDraftExportConfig,
    LocalOpenAICompatibleRuntimeConfig,
    TTSEngineConfig,
    WhisperSTTConfig,
)
from videobox_provider_interfaces.gemini import GeminiHTTPTransport, GeminiRESTStructuredProvider
from videobox_provider_interfaces.llm import LLMProviderConfig
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.user_library_store import UserLibraryStore

# Re-exported for backward compatibility: tests/test_api.py and a few other
# test modules import these names directly from videobox_api.main rather
# than from the modules they now live in (response_normalizers.py,
# provider_factories.py).
__all__ = [
    "create_app",
    "_build_preflight_review_prediction",
    "_normalize_review_flags_for_response",
    "_normalize_recommendations_for_response",
    "_build_targeted_segments",
    "_build_stt_provider",
]


def create_app(
    *,
    projects_root: Path | None = None,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig | None = None,
    auto_cut_config: AutoCutConfig | None = None,
    whisper_stt_config: WhisperSTTConfig | None = None,
    capcut_draft_export_config: CapCutDraftExportConfig | None = None,
    tts_engine_config: TTSEngineConfig | None = None,
    local_first_runtime_service_factory=None,
    stt_provider=None,
    tts_provider=None,
    final_renderer=None,
    pycapcut_exporter=None,
) -> FastAPI:
    app = FastAPI(title="VideoBox API", version="0.1.0")
    store = LocalProjectStore(projects_root or DEFAULT_PROJECTS_ROOT)
    user_library_store = UserLibraryStore(store.projects_root.parent / "videobox-user-library")
    resolved_local_runtime_config = local_runtime_config or LocalOpenAICompatibleRuntimeConfig()
    runtime_service_factory = local_first_runtime_service_factory or (
        lambda project_store: build_local_first_runtime_service(
            store=project_store,
            gemini_provider=GeminiRESTStructuredProvider(
                transport=GeminiHTTPTransport(http_client=urlopen)
            ),
            gemini_config=LLMProviderConfig(provider_name="gemini", enabled=True),
            local_runtime_config=resolved_local_runtime_config,
            local_http_client=urlopen,
        )
    )
    runtime_service = runtime_service_factory(store)
    resolved_auto_cut_config = auto_cut_config or AutoCutConfig()
    resolved_whisper_stt_config = whisper_stt_config or WhisperSTTConfig()
    resolved_capcut_draft_export_config = capcut_draft_export_config or CapCutDraftExportConfig()
    resolved_tts_engine_config = tts_engine_config or TTSEngineConfig()
    pipeline = LocalPipelineRunner(
        store,
        segment_analyzer=LocalFirstSegmentAnalyzer(runtime_service=runtime_service),
        broll_recommender=LocalFirstKeywordBrollRecommender(runtime_service=runtime_service),
        music_recommender=LocalFirstMusicRecommender(runtime_service=runtime_service),
        review_guidance_builder=LocalFirstReviewGuidanceBuilder(runtime_service=runtime_service),
        output_operator_copy_builder=LocalFirstOutputOperatorCopyBuilder(runtime_service=runtime_service),
        auto_cut_planner=AutoCutPlanner(config=resolved_auto_cut_config),
        stt_provider=stt_provider or _build_stt_provider(resolved_whisper_stt_config),
        pycapcut_exporter=pycapcut_exporter or _build_pycapcut_exporter(
            resolved_capcut_draft_export_config, store=store
        ),
        tts_provider=tts_provider or _build_tts_provider(resolved_tts_engine_config),
        final_renderer=final_renderer,
    )
    orchestrator = ApiOrchestrator(store, pipeline=pipeline)
    app.state.local_runtime_config = resolved_local_runtime_config
    app.state.auto_cut_config = resolved_auto_cut_config
    app.state.whisper_stt_config = resolved_whisper_stt_config
    app.state.capcut_draft_export_config = resolved_capcut_draft_export_config
    app.state.tts_engine_config = resolved_tts_engine_config
    app.state.build_local_first_runtime_service = build_local_first_runtime_service
    app.state.local_first_runtime_service_factory = runtime_service_factory
    app.state.local_http_client = urlopen
    app.state.stt_provider = pipeline.stt_provider
    app.state.tts_provider = pipeline.tts_provider
    app.state.final_renderer = pipeline.final_renderer

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(build_projects_router(store))
    app.include_router(build_assets_router(orchestrator, store))
    app.include_router(build_jobs_router(orchestrator))
    app.include_router(build_timeline_router(orchestrator))
    app.include_router(build_editing_session_router(orchestrator, store))
    app.include_router(build_editor_library_router(user_library_store))
    app.include_router(build_review_router(orchestrator))
    app.include_router(build_outputs_router(orchestrator))
    app.include_router(build_gemini_keys_router(orchestrator))

    return app
