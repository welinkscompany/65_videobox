from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from videobox_api.models import LibraryFavoriteRequest, MaterializeLibraryAssetRequest
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


def build_media_library_router(
    project_store: LocalProjectStore, library_store: MediaLibraryStore,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/media-library/install-state")
    def get_media_library_install_state() -> dict[str, object]:
        try:
            return library_store.install_state()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="library_unavailable") from exc

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
            media_type = str(asset["media_type"])
            if media_type == "music":
                asset_type = AssetType.BGM
            elif media_type == "sfx":
                asset_type = AssetType.SFX
            else:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported_media_type")

            source_pack_id = library_asset_id.split(":", 2)[1] if library_asset_id.startswith("pack:") else ""
            metadata = {
                "source_library_asset_id": library_asset_id,
                "source_pack_id": source_pack_id,
                "source_pack_version": str(asset["version"]),
                "license_snapshot": {
                    "official_url": str(asset["official_license_url"]),
                    "evidence_timestamp": str(asset["evidence_timestamp"]),
                    "evidence_sha256": str(asset["evidence_sha256"]),
                    "source": str(asset["source"]),
                    "creator": str(asset["creator"]),
                    "attribution_required": bool(asset["attribution_required"]),
                    "attribution_text": str(asset["attribution_text"]),
                },
            }
            registered = project_store.register_asset(
                project_id=payload.project_id,
                asset_type=asset_type,
                source_path=snapshot_path,
                source_kind="media_library",
                mime_type=_mime_type(snapshot_path),
                metadata=metadata,
            )
            result = project_store.get_asset(
                project_id=payload.project_id, asset_id=registered.asset_id,
            )
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="asset_missing") from exc
        finally:
            library_store.remove_verified_snapshot(snapshot_path)

        # Library usage is a postcondition: failed project registration must not
        # mutate the global library's recent/favorite state.
        library_store.mark_recent_usage(library_asset_id=library_asset_id)
        return result

    return router


def _mime_type(path: Path) -> str | None:
    return {".mp3": "audio/mpeg", ".wav": "audio/wav"}.get(path.suffix.lower())
