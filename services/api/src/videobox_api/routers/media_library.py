from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from videobox_api.models import (
    LibraryAudioSearchRequest,
    LibraryFavoriteRequest,
    MaterializeLibraryAssetRequest,
)
from videobox_provider_interfaces.embeddings import EmbeddingRequest
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer

_LOGGER = logging.getLogger(__name__)

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
