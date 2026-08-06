"""Task 18's library -> project step: list what the watcher has already
verified and moved into the local media-inbox library, and copy one of
those files into a specific project as a raw video asset."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from videobox_api.models import MediaInboxImportRequest
from videobox_core_engine.media_inbox import import_media_inbox_asset_to_project
from videobox_storage.local_project_store import LocalProjectStore


def build_media_inbox_router(store: LocalProjectStore, library_root: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/api/media-inbox/assets")
    def list_media_inbox_assets() -> dict[str, object]:
        if not library_root.is_dir():
            return {"assets": []}
        return {
            "assets": [
                {"filename": path.name, "size_bytes": path.stat().st_size}
                for path in sorted(library_root.iterdir())
                if path.is_file()
            ]
        }

    @router.post(
        "/api/projects/{project_id}/media-inbox/import",
        status_code=status.HTTP_201_CREATED,
    )
    def import_media_inbox_asset(project_id: str, body: MediaInboxImportRequest) -> dict[str, object]:
        try:
            asset = import_media_inbox_asset_to_project(
                store, project_id=project_id, library_root=library_root, filename=body.filename,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="media_inbox_asset_missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project_missing") from exc
        return {
            "asset_id": asset.asset_id,
            "project_id": asset.project_id,
            "asset_type": asset.asset_type.value,
            "storage_uri": asset.storage_uri,
        }

    return router


__all__ = ["build_media_inbox_router"]
