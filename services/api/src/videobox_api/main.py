from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import base64
import binascii
import inspect
import logging
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
from videobox_api.provider_factories import _build_pycapcut_exporter, _build_scene_image_provider, _build_stt_provider, _build_tts_provider
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
from videobox_api.routers.caption_fonts import build_caption_fonts_router
from videobox_api.routers.jobs import build_jobs_router
from videobox_api.routers.live_smoke_attestation import build_live_smoke_attestation_router
from videobox_api.routers.media_inbox import build_media_inbox_router
from videobox_api.routers.media_library import build_media_library_router
from videobox_api.routers.format_templates import build_format_templates_router
from videobox_api.routers.library_assets import build_library_assets_router
from videobox_api.routers.media_analysis import build_media_analysis_router
from videobox_api.routers.outputs import build_outputs_router
from videobox_api.routers.hermes_conversation import build_hermes_conversation_router
from videobox_api.routers.hermes_operations import build_hermes_operations_router
from videobox_api.routers.projects import build_projects_router
from videobox_api.routers.review import build_review_router
from videobox_api.routers.scene_images import build_scene_images_router
from videobox_api.routers.script_drafts import build_script_drafts_router
from videobox_core_engine.scene_image_prompt import SceneImagePromptWriter
from videobox_core_engine.script_draft_writer import ScriptDraftWriter
from videobox_core_engine.scene_image_service import SceneImageService
from videobox_api.routers.timeline import build_timeline_router
from videobox_api.routers.yujin_memory import build_yujin_memory_router
from videobox_api.routers.footage_organizer import build_footage_organizer_router
from videobox_api.routers.output_variants import build_output_variants_router
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.asset_browser_preview import FFmpegBrowserPreviewRenderer, FFprobeBrowserPreviewProbe
from videobox_core_engine.creation_interview import CreationInterviewRuntime, DeterministicCreationInterviewRuntime
from videobox_core_engine.local_pipeline import (
    LocalPipelineRunner,
    broll_assets_needing_media_facts,
    record_broll_media_facts,
)
from videobox_core_engine.library_audio_indexer import index_pending_library_audio
from videobox_core_engine.library_footage_indexer import index_pending_library_footage
from videobox_core_engine.library_ingest import LibraryIngestService
from videobox_core_engine.library_media_facts import library_assets_needing_media_facts, record_library_media_facts
from videobox_core_engine.media_inbox import AUDIO_EXTENSIONS, MediaInboxConfig, run_inbox_watcher_loop
from videobox_core_engine.owner_audio_library import register_owner_audio_library
from videobox_core_engine.media_analysis import MediaAnalysisService, assets_needing_reanalysis
from videobox_core_engine.media_analysis import AnalysisProfile
from videobox_core_engine.media_probe import FFmpegMediaProbe
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_provider_interfaces.lm_studio import LMStudioEmbeddingProvider, LMStudioHTTPTransport, LMStudioVisionProvider
from videobox_core_engine.output_operator_copy import LocalFirstOutputOperatorCopyBuilder
from videobox_core_engine.recommenders import LocalOnlyKeywordBrollRecommender, LocalOnlyMusicRecommender
from videobox_core_engine.review_guidance import LocalFirstReviewGuidanceBuilder
from videobox_core_engine.script_scene_planner import LocalFirstSegmentAnalyzer
from videobox_core_engine.settings import (
    DEFAULT_PROJECTS_ROOT,
    AutoCutConfig,
    CapCutDraftExportConfig,
    ImageGenerationConfig,
    LocalOpenAICompatibleRuntimeConfig,
    TTSEngineConfig,
    WhisperSTTConfig,
    resolve_auto_approve_segment_review,
    resolve_capcut_draft_export_config,
    resolve_database_url,
    resolve_enable_local_media_analysis,
    resolve_image_generation_config,
    resolve_container_snapshot_root,
    resolve_local_runtime_config,
    resolve_media_inbox_library_root,
    resolve_media_inbox_watch_enabled,
    resolve_media_inbox_watch_interval_seconds,
    resolve_media_inbox_watch_path,
    resolve_owner_audio_library_root,
    resolve_owner_audio_watch_paths,
    resolve_projects_root,
    resolve_user_library_root,
    resolve_whisper_stt_config,
)
from videobox_core_engine.container_snapshot import ContainerSnapshotError, verify_container_snapshot
from videobox_storage.format_template_store import FormatTemplateStore
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

# 호출부에 로거를 다는 것만으로는 부족하다. 설정이 없으면 파이썬의 최후 수단
# 핸들러가 메시지만 찍어서, 어느 모듈에서 언제 났는지가 사라진다. 컨테이너에서
# 확인한 실제 상태가 그랬다 -- `root handlers: []`.
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_LOGGER = logging.getLogger(__name__)


def _redact_database_url(database_url: str) -> str:
    """비밀번호를 빼고 어디에 붙었는지만 남긴다. 로그는 컨테이너 밖으로 나간다."""
    without_scheme = database_url.split("://", 1)[-1]
    return without_scheme.split("@", 1)[-1] if "@" in without_scheme else without_scheme


def configure_logging() -> None:
    """VideoBox 로그가 컨테이너 출력에 추적 가능한 형태로 나가게 한다.

    uvicorn은 자기 로거만 설정하고 루트는 건드리지 않는다. 이미 핸들러가
    붙어 있으면 그대로 둔다 -- 테스트나 상위 프로세스가 정해 둔 것을 빼앗지
    않는다.
    """
    root = logging.getLogger()
    if root.handlers:
        # 누군가 이미 정해 뒀다 -- pytest, 상위 프로세스, 배포 설정. 형식도
        # 수준도 빼앗지 않는다. 수준을 덮어쓰면 DEBUG를 보려던 쪽이 조용히
        # 아무것도 못 보게 된다.
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(handler)
    # `getattr(logging, name)`은 `FileHandler` 같은 것도 돌려준다. 그것을
    # setLevel에 넘기면 오타 하나로 앱이 안 뜬다.
    level_name = os.environ.get("VIDEOBOX_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    root.setLevel(level)


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

# The owner adds music and effects over time, and each new file has to become
# searchable without them running anything. A bounded pass keeps a first
# install of 130 files -- or a big drop of new ones -- from turning startup
# into a long analysis run; what is left is picked up next minute.
LIBRARY_AUDIO_INDEX_INTERVAL_SECONDS = 60.0
LIBRARY_AUDIO_INDEX_BATCH = 8

# 낡은 분석을 한꺼번에 다 걸면 로컬 모델이 동시에 받고 전부 타임아웃한다.
REANALYSIS_BATCH = 1

# ffprobe가 실패해 길이·크기·오디오 없이 등록된 b-roll을 다시 잰다. 화면 분석과
# 달리 ffprobe 한 번은 싸지만, 촬영본이 쌓인 프로젝트에서 한 패스가 길어지지
# 않게 색인·재분석과 같은 방식으로 끊는다.
BROLL_MEDIA_FACTS_BACKFILL_BATCH = 4

# 같은 이유로 개인 라이브러리 broll도 다시 잰다. library_ingest.py의 probe_metadata는
# ingest 시점 1회뿐이라 실패하면 영구히 정보 없이 남는다(위 broll 백필과 달리 이
# 대응물이 없었다 -- wave2-* 4개가 이 gap으로 계속 "길이 정보 없음"이었다).
LIBRARY_MEDIA_FACTS_BACKFILL_BATCH = 4


def _build_music_library_hooks(
    *, library_store: MediaLibraryStore, project_store: LocalProjectStore, app: FastAPI
):
    """음악 추천이 실제 곡을 고를 수 있게 해 주는 두 갈고리.

    추천기는 저장소도 임베딩 공급자도 모르게 두고 호출 가능한 것만 넘긴다.
    모델이 없으면 검색이 None을 돌려주고, 추천은 예전처럼 분위기만 말한다 --
    라이브러리에서 아무거나 집어 주는 것보다 낫다.
    """

    def search(query: str, limit: int) -> list[dict[str, object]]:
        provider = getattr(app.state, "media_analysis_embedding_provider", None)
        model_name = (getattr(app.state, "media_analysis_profile", None) or {}).get(
            "embedding_model_name"
        )
        if provider is None or not model_name:
            return []
        response = provider.embed(EmbeddingRequest(model_name=model_name, inputs=(query,)))
        return library_store.find_audio_matches(
            query_embedding=[float(value) for value in response.vectors[0]],
            media_type="music",
            limit=limit,
        )

    # 실패 사유가 같으면 다시 찍지 않는다. 추천 한 번에 장면 수만큼 불리는
    # 갈고리라, 사유마다 한 줄이 아니면 로그가 못 쓰게 된다. 한 번 성공하면
    # 잊어서, 나중에 다시 고장 나면 다시 남긴다.
    reported_resolve_faults: set[str] = set()

    def resolve(project_id: str, library_asset_id: str) -> str | None:
        # 이미 가져온 곡이면 화면이 바로 적용할 수 있다. materializer가 남기는
        # `source_library_asset_id`가 그 표식이다.
        try:
            resolved: str | None = None
            for asset in project_store.list_assets(project_id=project_id):
                metadata = dict(asset.get("metadata") or {})
                if metadata.get("source_library_asset_id") == library_asset_id:
                    resolved = str(asset["asset_id"])
                    break
        except Exception as exc:  # noqa: BLE001 - 추천은 계속 나가야 한다
            # 여기서 None을 돌려주면 추천기는 "아직 안 가져온 곡"으로 읽고
            # 이미 갖고 있는 곡을 다시 가져오라고 안내한다. 안내가 정상으로
            # 보이기 때문에 이유를 남기지 않으면 아무도 알아채지 못한다.
            fault = f"{project_id}|{type(exc).__name__}|{exc}"
            if fault not in reported_resolve_faults:
                reported_resolve_faults.add(fault)
                _LOGGER.warning(
                    "프로젝트 자산을 읽지 못해 이미 가져온 곡을 못 알아봅니다. "
                    "가져오기부터 하라고 안내될 수 있습니다 (project=%s).",
                    project_id,
                    exc_info=True,
                )
            return None
        reported_resolve_faults.clear()
        return resolved

    return search, resolve


def _index_library_footage(app: FastAPI) -> None:
    """드롭 폴더에 쌓인 촬영본을 찾을 수 있는 자산으로 만든다.

    b-roll 분석은 프로젝트에 묶여 있어서, 라이브러리에 있는 영상은 가져오기
    전까지 유진에게 보이지 않았다. 화면 분석은 무거우므로 한 번에 몇 개만
    처리하고 나머지는 다음 차례로 둔다.
    """
    store = getattr(app.state, "media_library_store", None)
    library_root = getattr(app.state, "media_inbox_library_root", None)
    if store is None or library_root is None or not Path(library_root).is_dir():
        return
    profile = getattr(app.state, "media_analysis_profile", None) or {}
    report = index_pending_library_footage(
        store=store,
        paths=[path for path in Path(library_root).iterdir() if path.is_file()],
        media_probe=getattr(app.state, "media_analysis_probe", None),
        vision_provider=getattr(app.state, "media_analysis_vision_provider", None),
        vision_model_name=profile.get("vision_model_name"),
        embedding_provider=getattr(app.state, "media_analysis_embedding_provider", None),
        embedding_model_name=profile.get("embedding_model_name"),
    )
    # 색인기는 실패한 파일을 성실히 모아 돌려주는데 부르는 쪽이 그 보고서를
    # 버리고 있었다. 색인되지 못한 촬영본은 검색에서 그냥 없는 것이 된다.
    if report.failed:
        _LOGGER.warning(
            "촬영본 %d개를 색인하지 못했습니다. 검색에 나오지 않습니다: %s",
            len(report.failed),
            ", ".join(report.failed[:10]),
        )


def _register_owner_audio(app: FastAPI) -> None:
    """owner가 직접 넣은 음악·효과음을 라이브러리 자산으로 올린다.

    감시가 파일을 옮겨 놓는 것만으로는 검색에 절대 나오지 않는다. 바로 아래
    `_index_library_audio`가 부르는 색인기는 폴더가 아니라 라이브러리 DB를
    읽고, 그 질의는 활성·검증된 팩에 속한 자산만 돌려주기 때문이다. 그래서
    이 한 걸음이 없으면 owner에게는 "넣었는데 아무 일도 안 일어난다"가 된다.

    반드시 색인보다 **먼저** 돈다. 그래야 이번 한 바퀴에 등록과 색인이 같이
    끝나고, owner가 다음 바퀴를 기다리지 않는다.
    """
    store = getattr(app.state, "media_library_store", None)
    roots = getattr(app.state, "owner_audio_library_roots", None)
    install_path = getattr(app.state, "owner_audio_library_root", None)
    if store is None or not roots or install_path is None:
        return
    report = register_owner_audio_library(
        store=store, roots=roots, install_path=Path(install_path)
    )
    if report.failed:
        _LOGGER.warning(
            "직접 넣은 소리 %d개를 라이브러리에 넣지 못했습니다. 검색에 나오지 않습니다: %s",
            len(report.failed),
            ", ".join(report.failed[:10]),
        )


def _index_library_audio(app: FastAPI) -> None:
    store = getattr(app.state, "media_library_store", None)
    if store is None:
        return
    report = index_pending_library_audio(
        store=store,
        embedding_provider=getattr(app.state, "media_analysis_embedding_provider", None),
        embedding_model_name=(getattr(app.state, "media_analysis_profile", None) or {}).get(
            "embedding_model_name"
        ),
        max_assets=LIBRARY_AUDIO_INDEX_BATCH,
    )
    # 촬영본 쪽과 같다. 옮겨졌거나 읽지 못한 음원은 보고서에만 남고
    # 어디에도 나타나지 않았다.
    if report.failed:
        _LOGGER.warning(
            "음원 %d개를 색인하지 못했습니다. 검색에 나오지 않습니다: %s",
            len(report.failed),
            ", ".join(report.failed[:10]),
        )


def _backfill_broll_media_facts(app: FastAPI) -> None:
    """등록 때 ffprobe가 실패한 b-roll의 길이·크기·오디오를 나중에 채운다.

    등록 시점 1회 호출뿐이라, 한 번 실패하면 그 자산은 영구히 "길이 정보 없음"
    으로 남고 편집기 세로/가로 필터에서 빠졌다. owner는 폰으로 찍어 롱폼과
    숏폼을 같이 만들기 때문에 그 필터에서 빠지는 것이 실제 손실이다.

    라이브러리 색인과 같은 자리에서 같은 방식으로 돈다.
    """
    store: LocalProjectStore = app.state.store
    for project in store.list_projects():
        project_id = str(project["project_id"])
        try:
            recovered = [
                pending["asset_id"]
                for pending in broll_assets_needing_media_facts(
                    store=store, project_id=project_id, limit=BROLL_MEDIA_FACTS_BACKFILL_BATCH
                )
                if record_broll_media_facts(store=store, project_id=project_id, **pending)
            ]
        except Exception:
            _LOGGER.warning(
                "빠진 영상 정보를 다시 채우지 못했습니다 (project=%s). 해당 자산은 "
                "세로/가로 필터에서 계속 빠집니다.",
                project_id,
                exc_info=True,
            )
            continue
        if recovered:
            _LOGGER.info(
                "빠져 있던 영상 정보 %d건을 채웠습니다 (project=%s).", len(recovered), project_id
            )


def _backfill_library_media_facts(app: FastAPI) -> None:
    """등록 때 ffprobe가 실패한 개인 라이브러리 broll의 길이·크기·오디오를 나중에 채운다.

    `_backfill_broll_media_facts`의 라이브러리 버전이다. 라이브러리는 프로젝트에
    묶이지 않으므로(전역 1개) project 순회가 없다.
    """
    media_library_store = getattr(app.state, "media_library_store", None)
    probe = getattr(app.state, "media_analysis_probe", None)
    roots = getattr(app.state, "library_asset_managed_roots", None)
    if media_library_store is None or probe is None or not roots:
        return
    user_asset_store = media_library_store.user_asset_store
    try:
        recovered = [
            pending["library_asset_id"]
            for pending in library_assets_needing_media_facts(
                store=user_asset_store, limit=LIBRARY_MEDIA_FACTS_BACKFILL_BATCH
            )
            if record_library_media_facts(store=user_asset_store, roots=roots, probe=probe, **pending)
        ]
    except Exception:
        _LOGGER.warning(
            "빠진 라이브러리 영상 정보를 다시 채우지 못했습니다.",
            exc_info=True,
        )
        return
    if recovered:
        _LOGGER.info("빠져 있던 라이브러리 영상 정보 %d건을 채웠습니다.", len(recovered))


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
        if recovered:
            # 굳은 분석은 여기서만 풀린다. 몇 건을 다시 걸었는지 남기지 않으면
            # 되살아난 것과 처음부터 없던 것을 구분할 수 없다.
            _LOGGER.info("멈춰 있던 분석 %d건을 다시 걸었습니다 (project=%s).", len(recovered), project_id)
        if dispatcher is None:
            continue
        # 분석 문구가 바뀌면 저장된 결과는 낡은 언어로 남는다. 라이브러리
        # 색인과 같은 방식으로 저절로 다시 걸어 준다.
        service = getattr(app.state, "media_analysis_service", None)
        stale: list[str] = []
        if service is not None and recover_running:
            try:
                current_keys = {}
                for asset in store.list_assets(project_id=project_id):
                    asset_id = str(asset["asset_id"])
                    try:
                        current_keys[asset_id] = service.cache_key(
                            source_sha256=sha256_file(
                                store.resolve_storage_uri(
                                    project_id=project_id, storage_uri=str(asset["storage_uri"])
                                )
                            ),
                            profile=service.profile,
                        )
                    except Exception:
                        _LOGGER.warning(
                            "자산의 현재 캐시 열쇠를 계산하지 못했습니다 (project=%s, asset=%s). "
                            "이번 회차에는 낡음 여부를 판단할 수 없어 다시 걸리지 않습니다.",
                            project_id,
                            asset_id,
                            exc_info=True,
                        )
                        continue
                stale = assets_needing_reanalysis(
                    store=store,
                    project_id=project_id,
                    current_cache_keys=current_keys,
                    limit=REANALYSIS_BATCH,
                )
                for asset_id in stale:
                    service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
            except Exception:
                _LOGGER.warning(
                    "낡은 분석을 다시 걸지 못했습니다 (project=%s). 태그가 옛 언어로 남습니다.",
                    project_id,
                    exc_info=True,
                )
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
    """오래된 기록을 쳐낸다. 재시도나 재실행은 하지 않는다."""
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
        # 이 정리는 정의와 테스트만 있고 부르는 곳이 없었다. 그래서
        # `media_analysis_cache`와 `media_embeddings`가 계속 늘기만 했다 --
        # 아무도 돌리지 않는 보관 정책은 정책이 아니다.
        await asyncio.to_thread(
            store.prune_stale_media_analysis_cache,
            project_id=project_id,
            retention_days=30,
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
        _LOGGER.warning(
            "기동 복구에서 유진 실행 기록을 정리하지 못했습니다. 아래 작업자가 다시 시도합니다.",
            exc_info=True,
        )
    try:
        await asyncio.to_thread(app.state.asset_browser_preview_service.recover_orphans)
    except Exception:
        # Preview recovery is retriable and never starts a renderer.
        _LOGGER.warning(
            "기동 복구에서 미리보기를 정리하지 못했습니다. 만들다 만 미리보기가 남아 있을 수 있습니다.",
            exc_info=True,
        )
    try:
        await asyncio.to_thread(_recover_in_process_jobs, app)
    except Exception:
        # Marking a dead job dead is retriable and starts no work.
        _LOGGER.warning(
            "기동 복구에서 끊긴 작업을 정리하지 못했습니다. 화면에 멈춘 진행 표시가 남을 수 있습니다.",
            exc_info=True,
        )

    async def worker() -> None:
        first = True
        loop_clock = asyncio.get_running_loop()
        next_prune_at = 0.0
        next_index_at = 0.0
        while not stop_event.is_set():
            try:
                await _recover_hermes_runs(app)
                await _poll_media_analysis(app, recover_running=first)
                if loop_clock.time() >= next_index_at:
                    # Booked before the call, same as the prune below: a
                    # failing pass must not turn into a per-second retry.
                    next_index_at = loop_clock.time() + LIBRARY_AUDIO_INDEX_INTERVAL_SECONDS
                    # 등록이 먼저다. 그래야 방금 들어온 음악이 같은 바퀴에서
                    # 색인까지 끝난다.
                    await asyncio.to_thread(_register_owner_audio, app)
                    await asyncio.to_thread(_index_library_audio, app)
                    await asyncio.to_thread(_index_library_footage, app)
                    await asyncio.to_thread(_backfill_broll_media_facts, app)
                    await asyncio.to_thread(_backfill_library_media_facts, app)
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
                #
                # 살아남는 것과 침묵하는 것은 다르다. 여기 한 바퀴에는 분석
                # 폴링과 배차, 라이브러리 색인, 유진 실행 복구, 이벤트 정리가
                # 전부 들어 있다. 이유를 남기지 않으면 무엇이 계속 터져도
                # 화면은 정상으로 보이고 owner는 물어볼 근거조차 없다.
                _LOGGER.warning(
                    "뒤에서 도는 정비 한 바퀴가 실패했습니다. 다음 차례에 다시 시도합니다.",
                    exc_info=True,
                )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=app.state.media_analysis_poll_interval_seconds)
            except TimeoutError:
                pass

    task = asyncio.create_task(worker(), name="videobox-media-analysis-poller")

    media_inbox_stop_event = threading.Event()
    media_inbox_threads: list[threading.Thread] = []
    media_inbox_watch_configs = getattr(app.state, "media_inbox_watch_configs", []) or []
    if getattr(app.state, "media_inbox_watch_enabled", False):
        for watch_config in media_inbox_watch_configs:
            # 폴더가 없으면 감시는 조용히 아무것도 하지 않는다
            # (`scan_inbox_candidates`가 빈 목록을 돌려준다). owner가 이름을
            # 정확히 맞춰 폴더를 만들어야만 동작한다는 뜻이라, 여기서 만들어
            # 둔다. 이미 있으면 아무 일도 하지 않는다.
            try:
                watch_config.watch_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                _LOGGER.warning(
                    "넣는 폴더를 만들지 못했습니다: %s. 직접 만들어 주셔야 합니다.",
                    watch_config.watch_path,
                    exc_info=True,
                )
            thread = threading.Thread(
                target=run_inbox_watcher_loop,
                kwargs={
                    "config": watch_config,
                    "stop_event": media_inbox_stop_event,
                    "interval_seconds": getattr(app.state, "media_inbox_watch_interval_seconds", 30.0),
                },
                daemon=True,
                name=f"videobox-media-inbox-watcher-{watch_config.watch_path.name}",
            )
            thread.start()
            media_inbox_threads.append(thread)

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
        for thread in media_inbox_threads:
            await asyncio.to_thread(thread.join, 5.0)
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
    image_generation_config: ImageGenerationConfig | None = None,
    scene_image_provider=None,
    scene_image_prompt_writer=None,
    script_draft_writer=None,
    capcut_handoff_service=None,
    local_only_runtime_service_factory=None,
    stt_provider=None,
    tts_provider=None,
    final_renderer=None,
    pycapcut_exporter=None,
    media_library_store: MediaLibraryStore | None = None,
    footage_detector=None,
    footage_derivative_renderer=None,
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
    configure_logging()
    # 설정이 살아 있다는 것을 로그만 보고 알 수 있게 한다. 실패 경로를
    # 일부러 터뜨리지 않고도 형식과 핸들러가 붙었는지 확인된다.
    _LOGGER.info("VideoBox 시작 -- 기록 설정 완료")
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
    if snapshot_root is not None and database_url is None:
        # 이 프로젝트는 데이터베이스로만 돈다(owner 지시). 컨테이너 모드에서
        # 주소가 빠지면 예전에는 조용히 빈 파일 저장소를 열었고, 화면에서는
        # 그것이 "프로젝트가 전부 사라짐"과 구분되지 않았다. 뜨지 않는 편이
        # 낫다. 손으로 돌리는 개발 실행은 `VIDEOBOX_SNAPSHOT_ROOT`가 없으므로
        # 여기 걸리지 않고 계속 파일 저장소를 쓴다.
        #
        # 스냅샷 검증보다 먼저 본다. 뒤에 두면 스냅샷 오류가 이 오류를 가려서
        # 정작 빠진 변수 이름이 로그에 뜨지 않는다.
        raise ValueError(
            "container mode requires VIDEOBOX_DATABASE_URL; refusing to fall back to the local file store"
        )
    if snapshot_root is not None:
        try:
            verify_container_snapshot(snapshot_root)
        except ContainerSnapshotError as error:
            raise ValueError(f"container mode requires a verified container snapshot: {error}") from error
    # 저장소는 실행할 때 갈린다. 주소 한 줄이 빠져도 실패하지 않고 조용히 다른
    # 서랍을 여는데, 화면에서는 그것이 "프로젝트가 전부 사라짐"으로 보인다.
    # 어느 쪽을 열었는지 남겨야 그 물음에 로그로 답할 수 있다.
    if database_url is not None:
        _LOGGER.info("데이터베이스 저장소를 씁니다 (%s).", _redact_database_url(database_url))
    else:
        _LOGGER.info("파일 저장소를 씁니다 (%s). 데이터베이스 주소가 설정되지 않았습니다.", resolved_projects_root)
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
    resolved_image_generation_config = image_generation_config or resolve_image_generation_config()
    resolved_scene_image_provider = scene_image_provider or _build_scene_image_provider(
        resolved_image_generation_config
    )
    _music_library_search, _music_project_asset = _build_music_library_hooks(
        library_store=resolved_media_library_store, project_store=store, app=app
    )
    pipeline = LocalPipelineRunner(
        store,
        segment_analyzer=LocalFirstSegmentAnalyzer(runtime_service=runtime_service),
        broll_recommender=LocalOnlyKeywordBrollRecommender(runtime_service=runtime_service),
        music_recommender=LocalOnlyMusicRecommender(
            runtime_service=runtime_service,
            library_search=_music_library_search,
            resolve_project_asset=_music_project_asset,
        ),
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
    app.state.media_analysis_probe = resolved_media_probe
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
    app.state.image_generation_config = resolved_image_generation_config
    # 켜지 않았으면 `None`이다. 라우터가 그것을 "꺼져 있다"로 답하고, 화면은
    # 꺼진 것과 고장 난 것을 구분할 수 있다 (§10.14 2-C).
    app.state.scene_image_service = (
        SceneImageService(
            store=store,
            provider=resolved_scene_image_provider,
            # 유진이 대본 한 줄을 영어 묘사로 다시 쓴다. 없으면 한국어 요청을
            # 거절한다 -- 그대로 넣으면 24초 뒤에 엉뚱한 그림이 나온다.
            prompt_writer=scene_image_prompt_writer
            or SceneImagePromptWriter(runtime_service=runtime_service),
        )
        if resolved_scene_image_provider is not None
        else None
    )
    # 유진이 주제 한 줄에서 대본 초안을 쓴다. 첫 화면의 네 번째 길이 이것을 부른다.
    # `SceneImageService`와 달리 켜고 끄는 설정이 없다 -- 부르는 곳이 유진의 두뇌
    # 하나뿐이고, 그 두뇌는 이미 대화·추천·장면 계획이 모두 쓰고 있다.
    app.state.script_draft_writer = script_draft_writer or ScriptDraftWriter(
        runtime_service=runtime_service
    )
    app.state.build_local_only_runtime_service = build_local_only_runtime_service
    app.state.local_only_runtime_service_factory = runtime_service_factory
    app.state.local_http_client = urlopen
    app.state.stt_provider = pipeline.stt_provider
    app.state.tts_provider = pipeline.tts_provider
    app.state.final_renderer = pipeline.final_renderer
    app.state.user_library_store = user_library_store
    app.state.media_library_store = resolved_media_library_store
    # User media is copied into the global library root and gets one durable
    # ingest/idempotency authority shared by PC and Drive mirror imports.
    app.state.library_ingest_service = LibraryIngestService(
        store=resolved_media_library_store.user_asset_store,
        managed_root=user_library_root,
        probe_metadata=FFmpegMediaProbe().probe_metadata,
    )
    media_inbox_watch_path = resolve_media_inbox_watch_path()
    resolved_media_inbox_library_root = resolve_media_inbox_library_root()
    resolved_owner_audio_library_root = resolve_owner_audio_library_root()
    app.state.media_inbox_watch_enabled = resolve_media_inbox_watch_enabled()
    # A sibling of the watched folder, so when that folder is a mirrored Drive
    # folder the owner sees imported footage move from one Drive subfolder to
    # another instead of vanishing.  All three watched folders share it,
    # because all three are siblings.
    media_inbox_archive_root = (
        media_inbox_watch_path.parent / "자산화_완료"
        if media_inbox_watch_path is not None
        else None
    )
    app.state.media_inbox_watch_config = (
        MediaInboxConfig(
            watch_path=media_inbox_watch_path,
            library_root=resolved_media_inbox_library_root,
            archive_root=media_inbox_archive_root,
            copy_only=True,
            ingest_store=resolved_media_library_store.user_asset_store,
            media_type="broll",
        )
        if media_inbox_watch_path is not None
        else None
    )
    # 음악과 효과음은 각자의 폴더로 들어오고, 어느 폴더였는지가 곧 종류다
    # (owner 결정 2026-08-10). 라이브러리 자리도 촬영본과 나눠 둔다 -- 한군데
    # 섞이면 촬영본 색인이 음원을 영상으로 알고 화면 분석을 시도한다.
    app.state.owner_audio_library_root = resolved_owner_audio_library_root
    app.state.owner_audio_library_roots = {
        media_type: resolved_owner_audio_library_root / media_type
        for media_type in resolve_owner_audio_watch_paths(media_inbox_watch_path)
    }
    app.state.owner_audio_watch_configs = [
        MediaInboxConfig(
            watch_path=watch_path,
            library_root=resolved_owner_audio_library_root / media_type,
            archive_root=media_inbox_archive_root,
            accepted_extensions=AUDIO_EXTENSIONS,
            copy_only=True,
            ingest_store=resolved_media_library_store.user_asset_store,
            media_type=media_type,
        )
        for media_type, watch_path in sorted(
            resolve_owner_audio_watch_paths(media_inbox_watch_path).items()
        )
    ]
    app.state.media_inbox_watch_configs = [
        config
        for config in [app.state.media_inbox_watch_config, *app.state.owner_audio_watch_configs]
        if config is not None
    ]
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
            orchestrator=orchestrator,
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
    app.include_router(build_caption_fonts_router(user_library_store))
    def _schedule_scene_analysis(project_id: str, asset_id: str) -> None:
        """자산이 프로젝트에 들어온 순간 장면 분석을 건다. 이 함수가 없으면
        라이브러리에서 넣은 촬영본은 아무도 분석을 걸지 않아 유진의 추천이
        영원히 409로 막힌다 -- 뒤에서 도는 재분석 작업자는 **한 번도 분석하지
        않은 자산은 일부러 건너뛴다.**
        """
        service = getattr(orchestrator, "media_analysis_service", None)
        if service is None:
            return
        analysis = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
        dispatcher = getattr(orchestrator, "media_analysis_dispatcher", None)
        if dispatcher is not None:
            dispatcher(project_id=project_id, analysis_id=analysis["analysis_id"])

    app.include_router(build_media_library_router(store, resolved_media_library_store, schedule_scene_analysis=_schedule_scene_analysis))
    app.include_router(
        build_footage_organizer_router(
            media_library_store=resolved_media_library_store,
            detector=footage_detector,
            derivative_renderer=footage_derivative_renderer,
            yujin_runtime_service=runtime_service,
        )
    )
    resolved_library_asset_managed_roots = tuple(dict.fromkeys((user_library_root, resolved_media_inbox_library_root, resolved_owner_audio_library_root, *(resolved_owner_audio_library_root / media_type for media_type in resolve_owner_audio_watch_paths(media_inbox_watch_path)))))
    app.state.library_asset_managed_roots = resolved_library_asset_managed_roots
    app.include_router(
        build_library_assets_router(
            project_store=store,
            media_library_store=resolved_media_library_store,
            user_asset_store=resolved_media_library_store.user_asset_store,
            ingest_service=app.state.library_ingest_service,
            managed_root=user_library_root,
            managed_roots=resolved_library_asset_managed_roots,
            schedule_scene_analysis=_schedule_scene_analysis,
        )
    )
    # 포맷은 프로젝트가 아니라 사용자에게 붙는다 — 다음 영상은 보통 새 프로젝트다.
    app.state.format_template_store = FormatTemplateStore(user_library_root)
    app.include_router(
        build_format_templates_router(
            orchestrator=orchestrator, template_store=app.state.format_template_store
        )
    )
    app.include_router(build_media_inbox_router(orchestrator, resolved_media_inbox_library_root))
    app.include_router(build_scene_images_router(store))
    app.include_router(build_script_drafts_router())
    app.include_router(build_review_router(orchestrator))
    app.include_router(build_outputs_router(orchestrator))
    app.include_router(build_output_variants_router(store))

    return app
