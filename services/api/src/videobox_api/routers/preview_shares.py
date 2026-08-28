from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from videobox_api.content_delivery import deliver_file
from videobox_api.errors import _http_error
from videobox_api.models import (
    PreviewShareCreateResponse,
    PreviewShareStatusResponse,
    PreviewShareSummaryResponse,
)
from videobox_api.orchestration import ApiOrchestrator


def build_preview_shares_router(orchestrator: ApiOrchestrator) -> APIRouter:
    router = APIRouter()

    # owner 요청(2026-08-28): 프리뷰 공유 링크 -- 토큰 링크 방식 승인. 이 앱은
    # 지금까지 인증이 전혀 없었다는 점을 밝혀 둔다. 아래 두 개는
    # `/api/projects/{project_id}/...` 밖에 있다 -- 토큰 자체가 인증이라
    # project_id를 URL에 실을 필요도, 실어서도 안 된다.

    @router.post(
        "/api/projects/{project_id}/final-renders/{job_id}/share",
        status_code=status.HTTP_201_CREATED,
    )
    def create_preview_share(project_id: str, job_id: str) -> PreviewShareCreateResponse:
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            render = result.get("render")
            if not render or str(result.get("status")) != "succeeded":
                raise KeyError("final_render_not_ready")
            share = orchestrator.create_preview_share(
                project_id=project_id, export_id=str(render["export_id"])
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return PreviewShareCreateResponse(
            share_id=share["share_id"],
            token=share["token"],
            url=f"/preview/{share['token']}",
        )

    @router.get("/api/preview-shares/{token}")
    def get_preview_share(token: str) -> PreviewShareStatusResponse:
        share = orchestrator.get_preview_share(token=token)
        if share is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="preview_share_not_found")
        return PreviewShareStatusResponse(status="active")

    @router.get("/api/preview-shares/{token}/content")
    def get_preview_share_content(token: str, request: Request):
        try:
            share = orchestrator.get_preview_share(token=token)
            if share is None:
                raise KeyError("preview_share_not_found")
            export = orchestrator.store.get_final_render_export(
                project_id=share["project_id"], export_id=share["export_id"]
            )
            path = orchestrator.store.resolve_storage_uri(
                project_id=share["project_id"], storage_uri=str(export["file_uri"])
            )
            if not path.is_file():
                raise KeyError("preview_share_content_missing")
            return deliver_file(request=request, path=path, media_type="video/mp4")
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.post("/api/projects/{project_id}/preview-shares/{share_id}/revoke")
    def revoke_preview_share(project_id: str, share_id: str) -> dict[str, bool]:
        try:
            orchestrator.revoke_preview_share(project_id=project_id, share_id=share_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return {"revoked": True}

    @router.get("/api/projects/{project_id}/final-renders/{job_id}/shares")
    def list_preview_shares(project_id: str, job_id: str) -> dict[str, list[PreviewShareSummaryResponse]]:
        try:
            result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
            render = result.get("render")
            export_id = str(render["export_id"]) if render else None
            shares = orchestrator.list_preview_shares_for_render(
                project_id=project_id, export_id=export_id
            )
        except Exception as exc:
            raise _http_error(exc) from exc
        return {"shares": [PreviewShareSummaryResponse(**share) for share in shares]}

    return router
