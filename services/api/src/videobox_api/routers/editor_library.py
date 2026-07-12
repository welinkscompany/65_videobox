from __future__ import annotations

from fastapi import APIRouter, HTTPException

from videobox_api.models import EditorFavoriteRequest, EditorPresetRequest
from videobox_storage.user_library_store import UserLibraryStore


def build_editor_library_router(store: UserLibraryStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/editor-library/presets")
    def list_presets(project_id: str) -> list[dict[str, object]]:
        return store.list_caption_presets(project_id=project_id)

    @router.put("/api/projects/{project_id}/editor-library/presets/{preset_id:path}")
    def save_preset(project_id: str, preset_id: str, payload: EditorPresetRequest) -> dict[str, object]:
        try:
            return store.save_caption_preset(
                project_id=project_id,
                preset_id=preset_id,
                name=payload.name,
                style=payload.style,
                global_scope=payload.global_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/projects/{project_id}/editor-library/favorites")
    def list_favorites(project_id: str) -> list[dict[str, object]]:
        return store.list_favorites(project_id=project_id)

    @router.get("/api/projects/{project_id}/editor-library/recent-presets")
    def list_recent_presets(project_id: str) -> list[str]:
        return store.list_recent_preset_ids(project_id=project_id)

    @router.put("/api/projects/{project_id}/editor-library/recent-presets/{preset_id:path}")
    def mark_recent_preset(project_id: str, preset_id: str) -> list[str]:
        try:
            return store.mark_recent_preset(project_id=project_id, preset_id=preset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/api/projects/{project_id}/editor-library/favorites/{favorite_id:path}")
    def toggle_favorite(project_id: str, favorite_id: str, payload: EditorFavoriteRequest) -> dict[str, object]:
        try:
            return store.toggle_favorite(
                project_id=project_id,
                favorite_id=favorite_id,
                favorite_type=payload.favorite_type,
                enabled=payload.enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
