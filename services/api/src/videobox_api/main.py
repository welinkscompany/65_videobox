from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from urllib.request import urlopen

from fastapi import FastAPI

from videobox_api.orchestration import (
    ApiOrchestrator,
    LocalFirstRuntimeService,
    LocalOnlyRuntimeService,
    build_local_only_runtime_service,
)
from videobox_api.provider_factories import _build_pycapcut_exporter, _build_stt_provider, _build_tts_provider
from videobox_api.response_normalizers import (
    _build_preflight_review_prediction,
    _build_targeted_segments,
    _normalize_recommendations_for_response,
    _normalize_review_flags_for_response,
)
from videobox_api.routers.assets import build_assets_router
from videobox_api.routers.creation_briefs import build_creation_briefs_router
from videobox_api.routers.draft_readiness import build_draft_readiness_router
from videobox_api.routers.atomic_draft_bundles import build_atomic_draft_bundles_router
from videobox_api.routers.editing_session import build_editing_session_router
from videobox_api.routers.director_proposals import build_director_proposals_router
from videobox_api.routers.editor_library import build_editor_library_router
from videobox_api.routers.jobs import build_jobs_router
from videobox_api.routers.media_library import build_media_library_router
from videobox_api.routers.media_analysis import build_media_analysis_router
from videobox_api.routers.outputs import build_outputs_router
from videobox_api.routers.projects import build_projects_router
from videobox_api.routers.review import build_review_router
from videobox_api.routers.timeline import build_timeline_router
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.creation_interview import CreationInterviewRuntime, DeterministicCreationInterviewRuntime
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.media_analysis import MediaAnalysisService
from videobox_core_engine.media_analysis import AnalysisProfile
from videobox_core_engine.media_probe import FFmpegMediaProbe
from videobox_provider_interfaces.lm_studio import LMStudioEmbeddingProvider, LMStudioHTTPTransport, LMStudioVisionProvider
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
    resolve_database_url,
    resolve_container_snapshot_root,
    resolve_projects_root,
    resolve_user_library_root,
)
from videobox_core_engine.container_snapshot import ContainerSnapshotError, verify_container_snapshot
from videobox_storage.local_project_store import LocalProjectStore, sha256_file
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_storage.postgres_project_store import PostgresProjectStore
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


async def _poll_media_analysis(app: FastAPI, *, recover_running: bool) -> None:
    store: LocalProjectStore = app.state.store
    dispatcher = app.state.media_analysis_dispatcher
    for project in store.list_projects():
        project_id = str(project["project_id"])
        recovered = store.recover_orphaned_media_analysis_jobs(project_id=project_id) if recover_running else []
        if dispatcher is None:
            continue
        pending_ids = {
            *recovered,
            *(str(item["analysis_id"]) for item in store.list_media_analysis(project_id=project_id) if item["status"] in {"queued", "failed"}),
        }
        for analysis_id in sorted(pending_ids):
            await asyncio.to_thread(dispatcher, project_id=project_id, analysis_id=analysis_id)


@asynccontextmanager
async def _media_analysis_lifespan(app: FastAPI):
    """Run recovery and durable retry polling outside request/startup hot paths."""
    stop_event = asyncio.Event()

    async def worker() -> None:
        first = True
        while not stop_event.is_set():
            await _poll_media_analysis(app, recover_running=first)
            first = False
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=app.state.media_analysis_poll_interval_seconds)
            except TimeoutError:
                pass

    task = asyncio.create_task(worker(), name="videobox-media-analysis-poller")
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class _UnavailableMediaAnalysisService:
    """Records a visible blocked capability state when no real local worker is configured."""
    def __init__(self, store: LocalProjectStore) -> None:
        self.store = store

    def enqueue_analysis(self, *, project_id: str, asset_id: str) -> dict:
        asset = self.store.get_asset(project_id=project_id, asset_id=asset_id)
        source = self.store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
        digest = sha256_file(source)
        key = f"queued:{digest}"
        self.store.record_media_analysis_cache(project_id=project_id, asset_id=asset_id, source_sha256=digest, cache_key=key)
        analysis = self.store.create_media_analysis(project_id=project_id, asset_id=asset_id, idempotency_key=f"{digest}:{key}", cache_key=key)
        if analysis["status"] == "queued":
            claimed = self.store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
            if claimed is not None:
                self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=int(claimed["attempt"]), error_code="MEDIA_ANALYSIS_WORKER_UNAVAILABLE", error_message="Configure a local media analysis worker or inject a vision provider.")
        return self.get_analysis(project_id, analysis["analysis_id"])

    def get_analysis(self, project_id: str, analysis_id: str) -> dict:
        return self.store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def cancel_analysis(self, *, project_id: str, analysis_id: str) -> dict | None:
        current = self.get_analysis(project_id, analysis_id)
        return self.store.request_media_analysis_cancel(project_id=project_id, analysis_id=analysis_id, expected_attempt=int(current["attempt"]))

    def retry_analysis(self, *, project_id: str, analysis_id: str) -> dict:
        self.store.retry_media_analysis(project_id=project_id, analysis_id=analysis_id)
        current = self.store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        claimed = self.store.claim_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if claimed is not None:
            self.store.mark_media_analysis_blocked(project_id=project_id, analysis_id=analysis_id, expected_attempt=int(claimed["attempt"]), error_code="MEDIA_ANALYSIS_WORKER_UNAVAILABLE", error_message="Configure a local media analysis worker or inject a vision provider.")
        return self.store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)


def create_app(
    *,
    projects_root: Path | None = None,
    local_runtime_config: LocalOpenAICompatibleRuntimeConfig | None = None,
    auto_cut_config: AutoCutConfig | None = None,
    whisper_stt_config: WhisperSTTConfig | None = None,
    capcut_draft_export_config: CapCutDraftExportConfig | None = None,
    tts_engine_config: TTSEngineConfig | None = None,
    capcut_handoff_service=None,
    local_only_runtime_service_factory=None,
    local_first_runtime_service_factory=None,
    stt_provider=None,
    tts_provider=None,
    final_renderer=None,
    pycapcut_exporter=None,
    media_library_store: MediaLibraryStore | None = None,
    vision_provider=None,
    embedding_provider=None,
    media_probe=None,
    analysis_dispatcher=None,
    analysis_clock=None,
    media_analysis_poll_interval_seconds: float = 0.05,
    media_analysis_profile: dict | None = None,
    enable_local_media_analysis: bool = False,
    media_analysis_http_client=None,
    allow_test_media_analysis_providers: bool = False,
    creation_interview_runtime: CreationInterviewRuntime | None = None,
) -> FastAPI:
    app = FastAPI(title="VideoBox API", version="0.1.0", lifespan=_media_analysis_lifespan)
    resolved_projects_root = projects_root or resolve_projects_root()
    database_url = resolve_database_url()
    snapshot_root = resolve_container_snapshot_root()
    if snapshot_root is not None:
        try:
            verify_container_snapshot(snapshot_root)
        except ContainerSnapshotError as error:
            raise ValueError(f"container mode requires a verified container snapshot: {error}") from error
    store = (
        PostgresProjectStore(resolved_projects_root, database_url=database_url, now=analysis_clock)
        if database_url is not None
        else LocalProjectStore(resolved_projects_root, now=analysis_clock)
    )
    user_library_root = (
        resolve_user_library_root()
        if projects_root is None
        else store.projects_root.parent / "videobox-user-library"
    )
    user_library_store = UserLibraryStore(user_library_root)
    resolved_media_library_store = media_library_store or MediaLibraryStore(
        user_library_root
    )
    resolved_local_runtime_config = local_runtime_config or LocalOpenAICompatibleRuntimeConfig()
    if local_only_runtime_service_factory is not None:
        runtime_service_factory = local_only_runtime_service_factory
    elif local_first_runtime_service_factory is not None:
        # A LocalFirst instance carries a fallback-capable provider graph and
        # cannot be safely reduced by duck typing. Callers must migrate to the
        # explicitly named local_only factory (or deterministic test runtime).
        raise ValueError("local_first_runtime_service_factory is no longer supported; use local_only_runtime_service_factory.")
    else:
        runtime_service_factory = lambda project_store: build_local_only_runtime_service(
            store=project_store,
            local_runtime_config=resolved_local_runtime_config,
            local_http_client=urlopen,
        )
    runtime_service = runtime_service_factory(store)
    if isinstance(runtime_service, LocalFirstRuntimeService) or hasattr(runtime_service, "gemini_provider"):
        raise ValueError("local_only_runtime_service_factory must not return a fallback-capable runtime")
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
        capcut_handoff_service=capcut_handoff_service,
        tts_provider=tts_provider or _build_tts_provider(resolved_tts_engine_config),
        final_renderer=final_renderer,
    )
    resolved_creation_interview_runtime = creation_interview_runtime or DeterministicCreationInterviewRuntime()
    orchestrator = ApiOrchestrator(
        store, pipeline=pipeline, creation_interview_runtime=resolved_creation_interview_runtime
    )
    # Analysis is opt-in by dependency injection in normal API tests and runtime wiring.
    # Enqueue remains durable even where a local vision profile is unavailable.
    resolved_vision_provider = vision_provider
    resolved_media_probe = media_probe
    resolved_profile = media_analysis_profile
    if not enable_local_media_analysis and not allow_test_media_analysis_providers:
        if resolved_vision_provider is not None:
            raise ValueError("Injected media analysis providers require allow_test_media_analysis_providers=True; production must use the explicit local LM Studio profile.")
        if embedding_provider is not None:
            raise ValueError("Injected media analysis providers require allow_test_media_analysis_providers=True; production must use the explicit local LM Studio profile.")
    if enable_local_media_analysis:
        # This explicit profile is the only production construction path.  The
        # transport validates the exact loopback endpoint before each request,
        # and we preflight loaded native capability before a worker is exposed.
        transport = LMStudioHTTPTransport(http_client=media_analysis_http_client)
        capability = transport.capability_profile()
        if capability.vision_model_name is None:
            raise ValueError("A loaded LM Studio vision + structured_json model is required.")
        transport.preflight(model_name=capability.vision_model_name, capability="vision")
        resolved_vision_provider = LMStudioVisionProvider(transport=transport)
        if capability.embedding_model_name is not None:
            transport.preflight(model_name=capability.embedding_model_name, capability="embedding")
            embedding_provider = LMStudioEmbeddingProvider(transport=transport)
        resolved_media_probe = resolved_media_probe or FFmpegMediaProbe()
        resolved_profile = {
            "vision_model_name": capability.vision_model_name,
            "embedding_model_name": capability.embedding_model_name,
        }
    if resolved_vision_provider is not None:
        if resolved_media_probe is None:
            raise ValueError("media_probe is required when vision_provider is injected.")
        analysis_service = MediaAnalysisService(
            store=store, media_probe=resolved_media_probe, vision_provider=resolved_vision_provider, embedding_provider=embedding_provider,
            profile=AnalysisProfile(**(resolved_profile or {})), clock=analysis_clock,
        )
        orchestrator.media_analysis_service = analysis_service
        orchestrator.media_analysis_dispatcher = analysis_dispatcher or analysis_service.dispatch_once
    else:
        analysis_service = _UnavailableMediaAnalysisService(store)
        orchestrator.media_analysis_service = analysis_service
        orchestrator.media_analysis_dispatcher = None
    app.state.local_runtime_config = resolved_local_runtime_config
    app.state.store = store
    app.state.media_analysis_vision_provider = resolved_vision_provider
    app.state.media_analysis_embedding_provider = embedding_provider
    app.state.media_analysis_service = orchestrator.media_analysis_service
    app.state.media_analysis_dispatcher = orchestrator.media_analysis_dispatcher
    app.state.media_analysis_poll_interval_seconds = media_analysis_poll_interval_seconds
    app.state.auto_cut_config = resolved_auto_cut_config
    app.state.whisper_stt_config = resolved_whisper_stt_config
    app.state.capcut_draft_export_config = resolved_capcut_draft_export_config
    app.state.tts_engine_config = resolved_tts_engine_config
    app.state.build_local_only_runtime_service = build_local_only_runtime_service
    app.state.local_only_runtime_service_factory = runtime_service_factory
    app.state.local_http_client = urlopen
    app.state.stt_provider = pipeline.stt_provider
    app.state.tts_provider = pipeline.tts_provider
    app.state.final_renderer = pipeline.final_renderer
    app.state.user_library_store = user_library_store
    app.state.media_library_store = resolved_media_library_store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(build_projects_router(store))
    app.include_router(build_creation_briefs_router(orchestrator))
    app.include_router(build_draft_readiness_router(orchestrator))
    app.include_router(build_atomic_draft_bundles_router(orchestrator))
    app.include_router(build_assets_router(orchestrator, store))
    app.include_router(build_media_analysis_router(store, orchestrator.media_analysis_service, orchestrator.media_analysis_dispatcher))
    app.include_router(build_jobs_router(orchestrator))
    app.include_router(build_timeline_router(orchestrator))
    app.include_router(build_editing_session_router(orchestrator, store))
    app.include_router(build_director_proposals_router(store))
    app.include_router(build_editor_library_router(user_library_store))
    app.include_router(build_media_library_router(store, resolved_media_library_store))
    app.include_router(build_review_router(orchestrator))
    app.include_router(build_outputs_router(orchestrator))

    return app
