"""대본의 한 장면에 얹을 그림을 만드는 문. owner 승인 2026-08-20 (§10.14 조항 2-C).

**한 번에 끝나는 요청이다.** 실측으로 1280x720이 22초, 1920x1080이 24초라
(2026-08-21, LM Studio를 켜 둔 채) 사람이 버튼을 누르고 기다릴 수 있는 시간이다.
job으로 쪼개면 화면이 폴링을 한 겹 더 들고 다녀야 하고, 그만큼 얻는 것이 없다.

**대신 이음매를 하나 못박았다.** nginx는 기본 60초에서 잘라 버리고, 그러면 화면은
504 HTML을 받고 제품이 고장 난 것처럼 보인다. 이 저장소의 테스트는 프록시를 한
번도 안 지나므로(2026-08-20 업로드 1MB 벽이 그렇게 숨어 있었다) 두 값이 어긋나지
않게 `tests/test_compose_contract.py`가 지킨다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status

from videobox_api.errors import _http_error
from videobox_api.models import SceneImageCreateRequest, SceneImageListResponse, SceneImageResponse
from videobox_core_engine.scene_image_service import SceneImageGenerationError
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore
from fastapi import HTTPException


#: `invalid`는 우리가 GPU를 깨우기 전에 막은 것, 나머지 셋은 provider가 분류한 것이다.
#: 한 낱말로 뭉개면 화면이 "켜야 한다"와 "다시 걸면 된다"를 구분할 수 없다.
_STATUS_BY_CODE = {
    "invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "blocked": status.HTTP_503_SERVICE_UNAVAILABLE,
    "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
    "failed": status.HTTP_502_BAD_GATEWAY,
}


def build_scene_images_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/scene-images", status_code=status.HTTP_201_CREATED)
    def create_scene_image(
        project_id: str, payload: SceneImageCreateRequest, request: Request
    ) -> SceneImageResponse:
        service = getattr(request.app.state, "scene_image_service", None)
        if service is None:
            # 꺼진 것과 고장 난 것은 다르다. 2026-08-20에 이 둘이 같은 문구로 보여
            # 켜지지 않은 기능을 결함으로 보고할 뻔했다.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="scene_image_generation_unavailable",
            )
        try:
            return SceneImageResponse(**service.generate_scene_image(
                project_id=project_id,
                prompt=payload.prompt,
                segment_id=payload.segment_id,
                vertical=payload.vertical,
                duration_sec=payload.duration_sec,
                gap_slot_id=payload.gap_slot_id,
            ))
        except SceneImageGenerationError as exc:
            raise HTTPException(
                status_code=_STATUS_BY_CODE.get(exc.code, status.HTTP_502_BAD_GATEWAY),
                detail=_detail(exc),
            ) from exc
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}/scene-images")
    def list_scene_images(project_id: str) -> SceneImageListResponse:
        """만든 것을 다시 볼 수 있어야 한다. 넣는 길만 있고 보는 길이 없으면
        잘못 만든 것을 영영 모른다(내레이션에서 같은 교훈을 얻었다)."""
        try:
            images = store.list_assets(project_id=project_id, asset_type=AssetType.IMAGE)
            clips = store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        except Exception as exc:
            raise _http_error(exc) from exc
        # 짝은 클립 쪽이 들고 있다 -- 그림이 먼저 등록되므로 그림에 클립 id를 적을
        # 수가 없다. 여기서 되짚는 편이 자산을 두 번 쓰는 것보다 낫다.
        clip_by_image = {
            str((clip.get("metadata") or {}).get("source_image_asset_id")): str(clip["asset_id"])
            for clip in clips
            if (clip.get("metadata") or {}).get("source_image_asset_id")
        }
        return SceneImageListResponse(images=[
            _as_scene_image(asset, clip_by_image.get(str(asset["asset_id"]), ""))
            for asset in images
            if _is_generated(asset)
        ])

    return router


def _is_generated(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") or {}
    return bool(metadata.get("generated_by")) and bool(metadata.get("scene_segment_id"))


def _as_scene_image(asset: dict[str, Any], scene_asset_id: str) -> SceneImageResponse:
    metadata = asset.get("metadata") or {}
    return SceneImageResponse(
        image_asset_id=str(asset["asset_id"]),
        scene_asset_id=scene_asset_id,
        segment_id=str(metadata.get("scene_segment_id") or ""),
        image_prompt=str(metadata.get("image_prompt") or metadata.get("prompt") or ""),
        title=str(metadata.get("title") or "장면 그림"),
        prompt=str(metadata.get("prompt") or ""),
        seed=int(metadata.get("seed") or 0),
        elapsed_sec=metadata.get("elapsed_sec"),
        commercial_use_is_unrestricted=metadata.get("commercial_use_is_unrestricted"),
    )


def _detail(exc: SceneImageGenerationError) -> str:
    """화면에 코드로 건넨다. 영어 문장은 creator 문구로 옮길 방법이 없어서
    2026-08-20에 게이트 하나를 이미 코드로 바꿨다(§10.13)."""
    message = str(exc)
    if message.startswith("scene_image_"):
        return message.split(":", 1)[0]
    return f"scene_image_generation_{exc.code}"


__all__ = ["build_scene_images_router"]
