"""Task 18's library -> project step: list what the watcher has already
verified and moved into the local media-inbox library, and copy one of
those files into a specific project as B-roll.

Task 22 (owner decision, 2026-08-07) corrected the asset type: collected
footage is B-roll, so it registers through the same path an upload takes and
queues analysis the same way, which is what makes it show up in the asset
list and become recommendable."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from videobox_api.models import MediaInboxImportRequest
from videobox_core_engine.media_inbox import import_media_inbox_asset_to_project


def build_media_inbox_router(orchestrator: object, library_root: Path) -> APIRouter:
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
    def import_media_inbox_asset(
        project_id: str,
        body: MediaInboxImportRequest,
        background_tasks: BackgroundTasks,
    ) -> dict[str, object]:
        try:
            asset = import_media_inbox_asset_to_project(
                orchestrator.pipeline,  # type: ignore[attr-defined]
                project_id=project_id,
                library_root=library_root,
                filename=body.filename,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="media_inbox_asset_missing") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="project_missing") from exc
        return {**asset, "analysis": _start_analysis(project_id, str(asset["asset_id"]), background_tasks)}

    def _start_analysis(
        project_id: str, asset_id: str, background_tasks: BackgroundTasks
    ) -> dict[str, object] | None:
        """Mirror the b-roll batch endpoint: queue analysis so imported footage
        gets tagged, but never let a failure there undo a durable import."""
        service = getattr(orchestrator, "media_analysis_service", None)
        if service is None:
            return None
        try:
            analysis = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
            dispatcher = getattr(orchestrator, "media_analysis_dispatcher", None)
            if dispatcher is not None:
                background_tasks.add_task(
                    dispatcher, project_id=project_id, analysis_id=analysis["analysis_id"]
                )
            return service.get_analysis(project_id, analysis["analysis_id"])
        except Exception:
            return None

    return router


__all__ = ["build_media_inbox_router"]
