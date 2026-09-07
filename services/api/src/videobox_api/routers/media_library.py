from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from videobox_api.models import (
    LibraryAudioSearchRequest,
    LibraryFavoriteRequest,
    MaterializeLibraryAssetRequest,
    MediaPackInstallRequest,
)
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_core_engine.media_pack_release import ffprobe_media
from videobox_core_engine.media_pack_service import MediaPackService
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer

_LOGGER = logging.getLogger(__name__)

def _probe_duration(path: Path) -> float:
    """오디오 길이(초)만 잰다."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())



# 장면 분석을 거는 자산 종류. 음악·효과음은 볼 장면이 없다.
_SCENE_ANALYSED_ASSET_TYPES = frozenset({"broll_video", "raw_video"})


def build_media_library_router(
    project_store: LocalProjectStore, library_store: MediaLibraryStore,
    # 사용자 라이브러리 쪽과 **같이** 걸어야 한다. 이 저장소는 렌더 경로가 둘인
    # 것을 두 번 잊었고, 자산이 들어오는 문도 마찬가지로 둘이다.
    schedule_scene_analysis: Callable[[str, str], None] | None = None,
) -> APIRouter:
    router = APIRouter()
    materializer = ProjectAssetMaterializer(project_store)

    @router.get("/api/media-library/install-state")
    def get_media_library_install_state() -> dict[str, object]:
        try:
            return library_store.install_state()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc

    @router.post("/api/media-library/install")
    def install_media_pack(payload: MediaPackInstallRequest) -> dict[str, object]:
        """데이터 폴더에 놓아 둔 미디어 팩을 설치한다.

        **이 자리가 없어서 팩을 갱신할 방법이 아예 없었다**(2026-09-05, owner가
        음악을 바꿔 달라고 해서 드러났다). 설치기는 처음부터 있었지만 부르는
        곳이 어디에도 없었고, 최초 설치는 사람이 손으로 한 것이었다.

        **API가 설치해야 하는 이유**: 자산 색인이 SQLite에 있고 그 파일은 이
        프로세스가 열고 있다. 밖에서 손대면 `readonly database`로 막히고,
        9p 마운트에서는 더 잘 난다.

        같은 버전이 이미 건강하게 깔려 있으면 설치기가 `already_installed`로
        답한다 -- **곡을 바꿨다면 버전을 올려야 한다.**
        """
        name = payload.directory_name.strip()
        # 이름 한 조각만 받는다. 경로 구분자나 상위 이동이 섞이면 데이터 폴더
        # 밖으로 나갈 수 있다.
        if name in {"", ".", ".."} or "/" in name or "\\" in name or Path(name).name != name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pack_directory_invalid")
        source = (library_store.root.parent / name).resolve()
        try:
            source.relative_to(library_store.root.parent.resolve())
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pack_directory_invalid") from None
        if not (source / "manifest.json").is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pack_not_found")
        service = MediaPackService(
            user_library_root=library_store.root,
            library_store=library_store,
            # 길이는 `ffprobe_media`가 주지 않는다 -- 그건 코덱·비트레이트만 본다.
            # 따로 재야 한다(`scripts/verify-starter-media-pack.py`와 같은 방식).
            duration_probe=_probe_duration,
            media_probe=ffprobe_media,
        )
        result = service.install(source)
        if result.status == "failed":
            # **이유를 로그에 남긴다.** 응답에는 코드만 나가는데(창작자에게 내부
            # 메시지를 보이지 않는다), 그것만으로는 무엇이 틀렸는지 아무도 모른다.
            _LOGGER.warning(
                "media pack install failed: name=%s code=%s message=%s",
                name, result.error_code, result.message,
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result.error_code or "install_failed")
        return {
            "status": result.status,
            "pack_id": result.pack_id,
            "version": result.version,
            "install_state": library_store.install_state(),
        }

    @router.post("/api/media-library/search")
    def search_library_assets(payload: LibraryAudioSearchRequest, request: Request) -> dict[str, object]:
        """Find assets that suit a scene, by meaning rather than by filename.

        The library's own descriptions are written in creator language, so a
        query like "차분한 배경 음악" lands near the right tracks. Without the
        local model there is no query vector, and answering with an arbitrary
        list would be worse than saying so.
        """
        query = payload.query.strip()
        if not query:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query_required")
        provider = getattr(request.app.state, "media_analysis_embedding_provider", None)
        model_name = (getattr(request.app.state, "media_analysis_profile", None) or {}).get(
            "embedding_model_name"
        )
        if provider is None or not model_name:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_search_unavailable"
            )
        try:
            response = provider.embed(EmbeddingRequest(model_name=model_name, inputs=(query,)))
            vector = [float(value) for value in response.vectors[0]]
            if payload.media_type == "broll":
                matches = library_store.find_footage_matches(
                    query_embedding=vector, orientation=payload.orientation, limit=payload.limit
                )
            else:
                matches = library_store.find_audio_matches(
                    query_embedding=vector, media_type=payload.media_type, limit=payload.limit
                )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_search_unavailable"
            ) from exc
        return {"matches": matches}

    @router.get("/api/media-library/assets")
    def list_library_assets() -> dict[str, object]:
        try:
            assets = library_store.inspect_active_assets()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc
        return {"assets": [{
            "library_asset_id": item["library_asset_id"],
            "asset_id": item["asset_id"],
            "media_type": item["media_type"],
            "duration_seconds": item["duration_seconds"],
            "version": item["version"],
            "verified": item["verified"],
            "available": item["available"],
            "source": item["source"],
            "creator": item["creator"],
            "official_license_url": item["official_license_url"],
            "evidence_timestamp": item["evidence_timestamp"],
            "tags": item["tags"],
            "attribution_required": item["attribution_required"],
            "attribution_text": item["attribution_text"],
        } for item in assets]}

    @router.get("/api/media-library/favorites")
    def list_library_favorites() -> dict[str, object]:
        try:
            return {"asset_ids": library_store.list_favorites()}
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc

    @router.get("/api/media-library/recent")
    def list_recent_library_usage() -> dict[str, object]:
        try:
            return {"asset_ids": library_store.list_recent_usage()}
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc

    @router.get("/api/projects/{project_id}/media-library/favorites")
    def list_project_library_favorites(project_id: str) -> dict[str, object]:
        _require_project(project_store, project_id)
        return {"asset_ids": project_store.get_project_media_library_preferences(project_id)["favorite_asset_ids"]}

    @router.get("/api/projects/{project_id}/media-library/recent")
    def list_project_recent_library_usage(project_id: str) -> dict[str, object]:
        _require_project(project_store, project_id)
        return {"asset_ids": project_store.get_project_media_library_preferences(project_id)["recent_asset_ids"]}

    @router.put("/api/projects/{project_id}/media-library/assets/{library_asset_id:path}/favorite")
    def set_project_library_favorite(
        project_id: str, library_asset_id: str, payload: LibraryFavoriteRequest,
    ) -> dict[str, object]:
        _require_project(project_store, project_id)
        try:
            if payload.enabled and library_store.get_verified_asset(library_asset_id=library_asset_id) is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc
        preferences = project_store.set_project_media_library_favorite(
            project_id=project_id, library_asset_id=library_asset_id, enabled=payload.enabled,
        )
        return {"asset_ids": preferences["favorite_asset_ids"]}

    @router.put("/api/media-library/assets/{library_asset_id:path}/favorite")
    def set_library_favorite(library_asset_id: str, payload: LibraryFavoriteRequest) -> dict[str, object]:
        try:
            if payload.enabled and library_store.get_verified_asset(library_asset_id=library_asset_id) is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")
            library_store.set_favorite(library_asset_id=library_asset_id, enabled=payload.enabled)
            return {"asset_ids": library_store.list_favorites()}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc

    @router.get("/api/media-library/assets/{library_asset_id:path}/preview")
    def preview_library_asset(library_asset_id: str):
        try:
            snapshot = library_store.snapshot_verified_asset(library_asset_id=library_asset_id)
        except (FileNotFoundError, OSError, ValueError):
            snapshot = None
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")
        _, snapshot_path = snapshot
        return FileResponse(
            snapshot_path,
            media_type=_mime_type(snapshot_path),
            background=BackgroundTask(library_store.remove_verified_snapshot, snapshot_path),
        )

    @router.post(
        "/api/media-library/assets/{library_asset_id:path}/materialize",
        status_code=status.HTTP_201_CREATED,
    )
    def materialize_library_asset(
        library_asset_id: str, payload: MaterializeLibraryAssetRequest,
    ) -> dict[str, object]:
        try:
            snapshot = library_store.snapshot_verified_asset(library_asset_id=library_asset_id)
        except (FileNotFoundError, OSError, ValueError):
            snapshot = None
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing")

        asset, snapshot_path = snapshot
        try:
            result = materializer.materialize_verified_library_snapshot(
                project_id=payload.project_id, library_asset_id=library_asset_id,
                library_asset=asset, snapshot_path=snapshot_path, mime_type=_mime_type(snapshot_path),
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing") from exc
        finally:
            library_store.remove_verified_snapshot(snapshot_path)

        # Library usage is a postcondition: failed project registration must not
        # mutate the global library's recent/favorite state.
        library_store.mark_recent_usage(library_asset_id=library_asset_id)
        project_store.mark_project_media_library_recent(
            project_id=payload.project_id, library_asset_id=library_asset_id,
        )
        if schedule_scene_analysis is not None and str(result.get("asset_type") or "") in _SCENE_ANALYSED_ASSET_TYPES:
            try:
                schedule_scene_analysis(payload.project_id, str(result["asset_id"]))
            except Exception:
                _LOGGER.warning(
                    "팩에서 넣은 촬영본의 장면 분석을 걸지 못했습니다 (project=%s, 자산=%s). "
                    "태그가 붙지 않아 유진의 추천이 막힙니다.",
                    payload.project_id, result.get("asset_id"), exc_info=True,
                )
        return result

    return router


def _mime_type(path: Path) -> str | None:
    # 팩은 mp3와 wav뿐이지만, owner가 직접 넣는 파일은 폰과 녹음기가 뱉는
    # 무엇이든 될 수 있다. 여기 없으면 브라우저가 미리 듣기를 재생하지 못한다.
    return {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
    }.get(path.suffix.lower())


def _require_project(project_store: LocalProjectStore, project_id: str) -> None:
    try:
        project_store.get_project(project_id=project_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_missing") from exc
