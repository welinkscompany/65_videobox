from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from videobox_api.errors import _http_error
from videobox_api.models import MediaAnalysisReviewRequest
from videobox_storage.local_project_store import LocalProjectStore


def build_media_analysis_router(store: LocalProjectStore, service, dispatcher=None) -> APIRouter:
    router = APIRouter()

    def dispatch(project_id: str, analysis_id: str) -> None:
        if dispatcher is not None:
            dispatcher(project_id=project_id, analysis_id=analysis_id)

    @router.post("/api/projects/{project_id}/media-analysis")
    def create(project_id: str, payload: dict, background_tasks: BackgroundTasks) -> dict:
        try:
            item = service.enqueue_analysis(project_id=project_id, asset_id=str(payload["asset_id"]))
            if dispatcher is not None:
                background_tasks.add_task(dispatcher, project_id=project_id, analysis_id=item["analysis_id"])
            return service.get_analysis(project_id, item["analysis_id"])
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/media-analysis")
    def list_items(project_id: str) -> dict:
        try:
            return {"items": store.list_media_analysis(project_id=project_id)}
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/media-analysis/{analysis_id}")
    def get_item(project_id: str, analysis_id: str) -> dict:
        try:
            return store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/media-analysis/{analysis_id}/provenance")
    def provenance(project_id: str, analysis_id: str) -> dict:
        try:
            profile = store.get_media_analysis_profile(project_id=project_id, analysis_id=analysis_id)
            windows = store.list_media_scene_windows(project_id=project_id, analysis_id=analysis_id)
            embeddings = store.list_media_embeddings(project_id=project_id, analysis_id=analysis_id)
            return {
                "profile": profile,
                "scene_windows": [{"start_sec": window["start_sec"], "end_sec": window["end_sec"]} for window in windows],
                # Vectors are retained locally for future retrieval but are not
                # sent to the browser; dimensions provide auditable provenance.
                "embedding_dimensions": [len(item["embedding"]) for item in embeddings],
            }
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/media-analysis/{analysis_id}/cancel")
    def cancel(project_id: str, analysis_id: str) -> dict:
        try:
            item = service.cancel_analysis(project_id=project_id, analysis_id=analysis_id)
            if item is None: raise ValueError("Media analysis cannot be cancelled.")
            return item
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/media-analysis/{analysis_id}/retry")
    def retry(project_id: str, analysis_id: str, background_tasks: BackgroundTasks) -> dict:
        try:
            retry_service = getattr(service, "retry_analysis", None)
            item = retry_service(project_id=project_id, analysis_id=analysis_id) if retry_service is not None else store.retry_media_analysis(project_id=project_id, analysis_id=analysis_id)
            if dispatcher is not None:
                background_tasks.add_task(dispatcher, project_id=project_id, analysis_id=analysis_id)
            return store.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.patch("/api/projects/{project_id}/media-analysis/{analysis_id}/review")
    def review(project_id: str, analysis_id: str, payload: MediaAnalysisReviewRequest) -> dict:
        try:
            return store.review_media_analysis(project_id=project_id, analysis_id=analysis_id, tags=payload.tags)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/assets/{asset_id}/analysis-preview")
    def preview(project_id: str, asset_id: str) -> dict:
        try:
            items = [item for item in store.list_media_analysis(project_id=project_id) if item["asset_id"] == asset_id]
            if not items: raise KeyError(f"No media analysis for asset: {asset_id}")
            latest = items[-1]
            preview_data = (latest.get("result") or {}).get("probe")
            if latest["status"] not in {"succeeded", "needs_review"} or preview_data is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="analysis_preview_unavailable")
            return {"analysis_id": latest["analysis_id"], "preview": preview_data}
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_error(exc) from exc
    return router
