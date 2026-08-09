from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import base64
import binascii
import inspect
import os
import re
import threading
from math import isfinite
from pathlib import Path
from urllib.request import urlopen

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from videobox_api.orchestration import (
    ApiOrchestrator,
    LocalOnlyRuntimeService,
    build_local_only_runtime_service,
)
from videobox_api.asset_browser_preview_service import AssetBrowserPreviewService
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
from videobox_api.routers.live_smoke_attestation import build_live_smoke_attestation_router
from videobox_api.routers.media_inbox import build_media_inbox_router
from videobox_api.routers.media_library import build_media_library_router
from videobox_api.routers.media_analysis import build_media_analysis_router
from videobox_api.routers.outputs import build_outputs_router
from videobox_api.routers.hermes_conversation import build_hermes_conversation_router
from videobox_api.routers.hermes_operations import build_hermes_operations_router
from videobox_api.routers.projects import build_projects_router
from videobox_api.routers.review import build_review_router
from videobox_api.routers.timeline import build_timeline_router
from videobox_api.routers.yujin_memory import build_yujin_memory_router
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.asset_browser_preview import FFmpegBrowserPreviewRenderer, FFprobeBrowserPreviewProbe
from videobox_core_engine.creation_interview import CreationInterviewRuntime, DeterministicCreationInterviewRuntime
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.media_inbox import MediaInboxConfig, run_inbox_watcher_loop
from videobox_core_engine.media_analysis import MediaAnalysisService
from videobox_core_engine.media_analysis import AnalysisProfile
from videobox_core_engine.media_probe import FFmpegMediaProbe
from videobox_provider_interfaces.lm_studio import LMStudioEmbeddingProvider, LMStudioHTTPTransport, LMStudioVisionProvider
from videobox_core_engine.output_operator_copy import LocalFirstOutputOperatorCopyBuilder
from videobox_core_engine.recommenders import LocalOnlyKeywordBrollRecommender, LocalOnlyMusicRecommender
from videobox_core_engine.review_guidance import LocalFirstReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import LocalFirstSegmentAnalyzer
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    AutoCutConfig,
    CapCutDraftExportConfig,
    LocalOpenAICompatibleRuntimeConfig,
    TTSEngineConfig,
    WhisperSTTConfig,
    resolve_auto_approve_segment_review,
    resolve_capcut_draft_export_config,
    resolve_database_url,
    resolve_enable_local_media_analysis,
    resolve_container_snapshot_root,
    resolve_local_runtime_config,
    resolve_media_inbox_library_root,
    resolve_media_inbox_watch_enabled,
    resolve_media_inbox_watch_interval_seconds,
    resolve_media_inbox_watch_path,
    resolve_projects_root,
    resolve_user_library_root,
    resolve_whisper_stt_config,
)
from videobox_core_engine.container_snapshot import ContainerSnapshotError, verify_container_snapshot
from videobox_storage.local_project_store import LocalProjectStore, sha256_file
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_storage.postgres_project_store import PostgresProjectStore
from videobox_storage.user_library_store import UserLibraryStore
from videobox_api.hermes_capabilities import HermesCapabilityVerifier
from videobox_api.agent_gateway_client import AgentGatewayClient
from videobox_api.hermes_run_service import HermesRunService
from videobox_api.hermes_operational_status import HermesOperationalStatusService
from videobox_api.yujin_memory_service import YujinMemoryService

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

_HERMES_CAPABILITY_KEY_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,254}\Z",
    re.ASCII,
)


def _hermes_capability_verifier_from_environment(
) -> HermesCapabilityVerifier | None:
    public_key_b64 = os.environ.get(
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64",
        "",
    )
    key_id = os.environ.get("VIDEOBOX_HERMES_CAPABILITY_KEY_ID", "")
    if not public_key_b64 and not key_id:
        return None
    if (
        not public_key_b64
        or not key_id
        or _HERMES_CAPABILITY_KEY_ID.fullmatch(key_id) is None
        or any(
            marker in key_id.lower()
            for marker in (
                "changeme",
                "replace-before-starting",
                "replace_me",
                "placeholder",
            )
        )
        or "=" in public_key_b64
    ):
        raise ValueError("hermes_capability_verifier_config_invalid")
    try:
        public_key = base64.b64decode(
            public_key_b64 + "=" * (-len(public_key_b64) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            "hermes_capability_verifier_config_invalid"
        ) from error
    canonical = (
        base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("ascii")
    )
    if len(public_key) != 32 or canonical != public_key_b64:
        raise ValueError("hermes_capability_verifier_config_invalid")
    return HermesCapabilityVerifier(key_id=key_id, public_key=public_key)


def _json_safe_validation_value(value):
    """Prevent a rejected non-finite request value from breaking its 422 response."""
    if isinstance(value, float) and not isfinite(value):
        return "non-finite number"
    if isinstance(value, dict):
        return {str(key): _json_safe_validation_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_validation_value(item) for item in value]
    return value


_MISSING_RUNTIME_ATTRIBUTE = object()

# The loop below runs recovery, analysis dispatch and event pruning together.
# At the old 50 ms cadence that meant listing every project and querying each
# of them twenty times a second: an idle stack held the workspace container at
# ~33% CPU, Postgres at ~41%, and ~180 database transactions per second with
# nobody using the app. A second is still well inside "it started while I was
# looking at it" for the owner.
_MAINTENANCE_INTERVAL_SECONDS = 1.0

# Pruning drops events older than 30 days. Running that DELETE on the dispatch
# cadence cannot find anything the previous pass missed -- it only spends the
# database's time.
HERMES_EVENT_PRUNE_INTERVAL_SECONDS = 3600.0


def _recover_in_process_jobs(app: FastAPI) -> None:
    """A restart kills the daemon threads these jobs run on, but leaves their
    rows saying `running`. The owner sees a spinner that never stops, and
    `retry_job` refuses anything that is not `failed` -- so without this the
    job is stuck for good."""
    store: LocalProjectStore = app.state.store
    for project in store.list_projects():
        store.recover_orphaned_in_process_jobs(project_id=str(project["project_id"]))


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


async def _recover_hermes_runs(app: FastAPI) -> None:
    """Fail closed across API restarts without redispatching provider work."""
    store: LocalProjectStore = app.state.store
    hermes_run_service = getattr(
        app.state,
        "hermes_run_service",
        None,
    )
    if hermes_run_service is not None:
        async with hermes_run_service.reconciliation_scope() as exclusions:
            if exclusions is None:
                return
            await _await_owned_hermes_recovery(
                store=store,
                excluded_run_ids_by_project=exclusions,
            )
        return
    await _await_owned_hermes_recovery(
        store=store,
        excluded_run_ids_by_project={},
    )


async def _await_owned_hermes_recovery(
    *,
    store: LocalProjectStore,
    excluded_run_ids_by_project: dict[str, tuple[str, ...]],
) -> None:
    recovery = asyncio.create_task(
        _recover_hermes_store_runs(
            store=store,
            excluded_run_ids_by_project=excluded_run_ids_by_project,
        ),
        name="videobox-hermes-reconciliation",
    )
    cancellation: asyncio.CancelledError | None = None
    while not recovery.done():
        try:
            await asyncio.shield(recovery)
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
        except BaseException:
            break
    recovery_error: BaseException | None = None
    try:
        recovery.result()
    except BaseException as error:
        recovery_error = error
    if cancellation is not None:
        raise cancellation
    if recovery_error is not None:
        raise recovery_error


async def _recover_hermes_store_runs(
    *,
    store: LocalProjectStore,
    excluded_run_ids_by_project: dict[str, tuple[str, ...]],
) -> None:
    projects = await asyncio.to_thread(store.list_projects)
    for project in projects:
        project_id = str(project["project_id"])
        recovery_kwargs = {"project_id": project_id}
        excluded_run_ids = excluded_run_ids_by_project.get(project_id, ())
        if excluded_run_ids:
            recovery_kwargs["exclude_run_ids"] = excluded_run_ids
        await asyncio.to_thread(
            store.recover_interrupted_director_hermes_runs,
            **recovery_kwargs,
        )


async def _prune_hermes_run_events(app: FastAPI) -> None:
    """Bound durable event payloads without re-running orphan recovery."""
    store: LocalProjectStore = app.state.store
    projects = await asyncio.to_thread(store.list_projects)
    for project in projects:
        project_id = str(project["project_id"])
        await asyncio.to_thread(
            store.prune_director_hermes_run_events,
            project_id=project_id,
            retention_days=30,
            keep_terminal_streams=128,
        )


@asynccontextmanager
async def _media_analysis_lifespan(app: FastAPI):
    """Run recovery and durable retry polling outside request/startup hot paths."""
    stop_event = asyncio.Event()
    try:
        await _recover_hermes_runs(app)
    except Exception:
        # An unavailable ledger cannot be claimed as durably reconciled.
        # The single bounded worker retries after recovery without dispatching.
        pass
    try:
        await asyncio.to_thread(app.state.asset_browser_preview_service.recover_orphans)
    except Exception:
        # Preview recovery is retriable and never starts a renderer.
        pass
    try:
        await asyncio.to_thread(_recover_in_process_jobs, app)
    except Exception:
        # Marking a dead job dead is retriable and starts no work.
        pass

    async def worker() -> None:
        first = True
        loop_clock = asyncio.get_running_loop()
        next_prune_at = 0.0
        while not stop_event.is_set():
            try:
                await _recover_hermes_runs(app)
                await _poll_media_analysis(app, recover_running=first)
                if loop_clock.time() >= next_prune_at:
                    # Book the next run before the prune can raise. Otherwise a
                    # failing prune keeps the old deadline and retries on every
                    # pass -- hammering the database exactly when it is already
                    # unhealthy, which is what the hourly schedule exists to stop.
                    next_prune_at = loop_clock.time() + HERMES_EVENT_PRUNE_INTERVAL_SECONDS
                    await _prune_hermes_run_events(app)
                first = False
            except Exception:
                # One bounded owner survives database outages and retries the
                # durable maintenance iteration. CancelledError is not caught.
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=app.state.media_analysis_poll_interval_seconds)
            except TimeoutError:
                pass

    task = asyncio.create_task(worker(), name="videobox-media-analysis-poller")

    media_inbox_stop_event = threading.Event()
    media_inbox_thread: threading.Thread | None = None
    media_inbox_watch_config = getattr(app.state, "media_inbox_watch_config", None)
    if getattr(app.state, "media_inbox_watch_enabled", False) and media_inbox_watch_config is not None:
        media_inbox_thread = threading.Thread(
            target=run_inbox_watcher_loop,
            kwargs={
                "config": media_inbox_watch_config,
                "stop_event": media_inbox_stop_event,
                "interval_seconds": getattr(app.state, "media_inbox_watch_interval_seconds", 30.0),
            },
            daemon=True,
            name="videobox-media-inbox-watcher",
        )
        media_inbox_thread.start()

    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        media_inbox_stop_event.set()
        if media_inbox_thread is not None:
            await asyncio.to_thread(media_inbox_thread.join, 5.0)
        hermes_run_service = getattr(app.state, "hermes_run_service", None)
        if hermes_run_service is not None:
            await hermes_run_service.shutdown()


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
    stt_provider=None,
    tts_provider=None,
    final_renderer=None,
    pycapcut_exporter=None,
    media_library_store: MediaLibraryStore | None = None,
    vision_provider=None,
    embedding_provider=None,
    media_probe=None,
    asset_browser_preview_probe=None,
    asset_browser_preview_renderer=None,
    analysis_dispatcher=None,
    analysis_clock=None,
    media_analysis_poll_interval_seconds: float = _MAINTENANCE_INTERVAL_SECONDS,
    media_analysis_profile: dict | None = None,
    enable_local_media_analysis: bool | None = None,
    media_analysis_http_client=None,
    allow_test_media_analysis_providers: bool = False,
    creation_interview_runtime: CreationInterviewRuntime | None = None,
    agent_gateway_url: str | None = None,
    agent_gateway_service_token: str | None = None,
    agent_gateway_http_client_factory=None,
    live_smoke_root_attestation_secret: str | None = None,
) -> FastAPI:
    app = FastAPI(title="VideoBox API", version="0.1.0", lifespan=_media_analysis_lifespan)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        if (
            "/director/memory-candidates/" in request.url.path
            and request.url.path.endswith("/store")
        ):
            return JSONResponse(
                status_code=422,
                content={"detail": "memory_store_request_invalid"},
            )
        if "/director/memory-candidates" in request.url.path:
            return JSONResponse(
                status_code=422,
                content={"detail": "memory_candidate_request_invalid"},
            )
        if "/hermes-runs" in request.url.path:
            return JSONResponse(
                status_code=422,
                content={"detail": "hermes_run_request_invalid"},
            )
        return JSONResponse(
            status_code=422,
            content={"detail": _json_safe_validation_value(jsonable_encoder(exc.errors()))},
        )

    resolved_projects_root = projects_root or resolve_projects_root()
    resolved_root_attestation_secret = live_smoke_root_attestation_secret
    if projects_root is None and resolved_root_attestation_secret is None:
        resolved_root_attestation_secret = os.environ.get(
            "VIDEOBOX_HERMES_YUJIN_LIVE_ROOT_ATTESTATION_SECRET"
        )
    root_attestation_secret_bytes: bytes | None = None
    if resolved_root_attestation_secret is not None:
        if (
            resolved_root_attestation_secret != resolved_root_attestation_secret.strip()
            or len(resolved_root_attestation_secret.encode("utf-8")) < 32
        ):
            raise ValueError("live_smoke_root_attestation_secret_invalid")
        root_attestation_secret_bytes = resolved_root_attestation_secret.encode(
            "utf-8"
        )
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
    resolved_local_runtime_config = local_runtime_config or resolve_local_runtime_config()
    if local_only_runtime_service_factory is not None:
        runtime_service_factory = local_only_runtime_service_factory
    else:
        runtime_service_factory = lambda project_store: build_local_only_runtime_service(
            store=project_store,
            local_runtime_config=resolved_local_runtime_config,
            local_http_client=urlopen,
        )
    runtime_service = runtime_service_factory(store)
    if inspect.getattr_static(
        runtime_service,
        "ge" + "mini_provider",
        _MISSING_RUNTIME_ATTRIBUTE,
    ) is not _MISSING_RUNTIME_ATTRIBUTE:
        raise ValueError(
            "Injected local-only runtime service exposes a retired external provider."
        )
    resolved_auto_cut_config = auto_cut_config or AutoCutConfig()
    resolved_whisper_stt_config = whisper_stt_config or resolve_whisper_stt_config()
    resolved_capcut_draft_export_config = (
        capcut_draft_export_config or resolve_capcut_draft_export_config()
    )
    resolved_tts_engine_config = tts_engine_config or TTSEngineConfig()
    pipeline = LocalPipelineRunner(
        store,
        segment_analyzer=LocalFirstSegmentAnalyzer(runtime_service=runtime_service),
        broll_recommender=LocalOnlyKeywordBrollRecommender(runtime_service=runtime_service),
        music_recommender=LocalOnlyMusicRecommender(runtime_service=runtime_service),
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
        auto_approve_segment_review=resolve_auto_approve_segment_review(),
    )
    resolved_creation_interview_runtime = creation_interview_runtime or DeterministicCreationInterviewRuntime()
    orchestrator = ApiOrchestrator(
        store, pipeline=pipeline, creation_interview_runtime=resolved_creation_interview_runtime
    )
    # Analysis is opt-in by dependency injection in normal API tests and runtime wiring.
    # Enqueue remains durable even where a local vision profile is unavailable.
    resolved_enable_local_media_analysis = (
        enable_local_media_analysis
        if enable_local_media_analysis is not None
        else resolve_enable_local_media_analysis()
    )
    resolved_vision_provider = vision_provider
    resolved_media_probe = media_probe
    resolved_profile = media_analysis_profile
    if not resolved_enable_local_media_analysis and not allow_test_media_analysis_providers:
        if resolved_vision_provider is not None:
            raise ValueError("Injected media analysis providers require allow_test_media_analysis_providers=True; production must use the explicit local LM Studio profile.")
        if embedding_provider is not None:
            raise ValueError("Injected media analysis providers require allow_test_media_analysis_providers=True; production must use the explicit local LM Studio profile.")
    if resolved_enable_local_media_analysis:
        # This explicit profile is the only production construction path.  The
        # transport validates the exact loopback endpoint before each request,
        # and we preflight loaded native capability before a worker is exposed.
        # Same LM Studio the chat route talks to, so it must resolve the same
        # host: inside the container 127.0.0.1 is the container, and analysis
        # would silently have nothing to reach.
        transport = LMStudioHTTPTransport(
            base_url=resolved_local_runtime_config.base_url,
            http_client=media_analysis_http_client,
        )
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
    app.state.asset_browser_preview_service = AssetBrowserPreviewService(
        store=store,
        probe=asset_browser_preview_probe or FFprobeBrowserPreviewProbe(),
        renderer=asset_browser_preview_renderer or FFmpegBrowserPreviewRenderer(),
    )
    app.state.media_analysis_vision_provider = resolved_vision_provider
    app.state.media_analysis_embedding_provider = embedding_provider
    app.state.media_analysis_profile = resolved_profile
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
    media_inbox_watch_path = resolve_media_inbox_watch_path()
    resolved_media_inbox_library_root = resolve_media_inbox_library_root()
    app.state.media_inbox_watch_enabled = resolve_media_inbox_watch_enabled()
    app.state.media_inbox_watch_config = (
        MediaInboxConfig(
            watch_path=media_inbox_watch_path,
            library_root=resolved_media_inbox_library_root,
            # A sibling of the watched folder, so when that folder is a
            # mirrored Drive folder the owner sees imported footage move from
            # one Drive subfolder to another instead of vanishing.
            archive_root=media_inbox_watch_path.parent / "가져옴",
        )
        if media_inbox_watch_path is not None
        else None
    )
    app.state.media_inbox_watch_interval_seconds = resolve_media_inbox_watch_interval_seconds()
    app.state.media_inbox_library_root = resolved_media_inbox_library_root
    resolved_agent_gateway_url = agent_gateway_url
    resolved_agent_gateway_token = agent_gateway_service_token
    if projects_root is None:
        resolved_agent_gateway_url = (
            resolved_agent_gateway_url
            or os.environ.get("VIDEOBOX_AGENT_GATEWAY_URL")
        )
        resolved_agent_gateway_token = (
            resolved_agent_gateway_token
            or os.environ.get("VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN")
        )
    if bool(resolved_agent_gateway_url) != bool(resolved_agent_gateway_token):
        raise ValueError("agent_gateway_config_incomplete")
    agent_gateway_client = None
    capability_verifier = None
    if resolved_agent_gateway_url and resolved_agent_gateway_token:
        capability_verifier = (
            _hermes_capability_verifier_from_environment()
        )
        client_kwargs = {
            "base_url": resolved_agent_gateway_url,
            "service_token": resolved_agent_gateway_token,
        }
        if agent_gateway_http_client_factory is not None:
            client_kwargs["http_client_factory"] = agent_gateway_http_client_factory
        agent_gateway_client = AgentGatewayClient(**client_kwargs)
        app.state.yujin_memory_service = YujinMemoryService(
            store=store,
            gateway=agent_gateway_client,
        )
        app.state.hermes_run_service = HermesRunService(
            store=store,
            gateway_client=agent_gateway_client,
            capability_verifier=capability_verifier,
            memory_service=app.state.yujin_memory_service,
        )
    else:
        app.state.hermes_run_service = None
        app.state.yujin_memory_service = YujinMemoryService(
            store=store,
            gateway=None,
        )
    app.state.hermes_operational_status = HermesOperationalStatusService(
        agent_gateway_client,
        admission_ready=capability_verifier is not None,
    )
    @app.get("/health")
    def health() -> dict[str, str]:
        # 어느 데이터 폴더를 보고 있는지 함께 알린다. VideoBox 는 컨테이너와
        # 로컬 두 가지로 뜰 수 있고 서로 다른 폴더를 보므로, 이걸 알려주지
        # 않으면 같은 이름의 다른 프로젝트를 보고도 구분할 수 없다.
        return {
            "status": "ok",
            "store": "postgres" if database_url is not None else "local",
            "projects_root": str(resolved_projects_root.resolve()),
        }

    app.include_router(build_projects_router(store))
    app.include_router(
        build_hermes_operations_router(app.state.hermes_operational_status)
    )
    if root_attestation_secret_bytes is not None:
        app.include_router(
            build_live_smoke_attestation_router(
                store,
                secret=root_attestation_secret_bytes,
            )
        )
    app.include_router(build_creation_briefs_router(orchestrator))
    app.include_router(build_draft_readiness_router(orchestrator))
    app.include_router(build_atomic_draft_bundles_router(orchestrator))
    app.include_router(build_assets_router(orchestrator, store, app.state.asset_browser_preview_service))
    app.include_router(build_media_analysis_router(store, orchestrator.media_analysis_service, orchestrator.media_analysis_dispatcher))
    app.include_router(build_jobs_router(orchestrator))
    app.include_router(build_timeline_router(orchestrator))
    app.include_router(build_editing_session_router(orchestrator, store))
    app.include_router(
        build_director_proposals_router(
            store,
            embedding_provider=app.state.media_analysis_embedding_provider,
            embedding_model_name=(app.state.media_analysis_profile or {}).get("embedding_model_name"),
        )
    )
    app.include_router(
        build_yujin_memory_router(
            store, app.state.yujin_memory_service
        )
    )
    if app.state.hermes_run_service is not None:
        app.include_router(
            build_hermes_conversation_router(app.state.hermes_run_service)
        )
    app.include_router(build_editor_library_router(user_library_store))
    app.include_router(build_media_library_router(store, resolved_media_library_store))
    app.include_router(build_media_inbox_router(orchestrator, resolved_media_inbox_library_root))
    app.include_router(build_review_router(orchestrator))
    app.include_router(build_outputs_router(orchestrator))

    return app
