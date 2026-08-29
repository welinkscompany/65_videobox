"""대본의 한 장면에 짧은 **진짜 동영상**을 만드는 문. owner 결정 2026-08-29(2회차).

**`scene_images.py`와 별개다.** owner가 명시적으로 "원래 만든거외에 별도로
만들자"고 했다 -- 정지 이미지+zoompan 경로는 그대로 두고, 이 파일이 진짜
동영상 생성을 맡는다.

**비동기다.** `scene_images.py`는 한 번에 끝나는 요청으로 설계됐다(22~24초,
nginx 60초 안). 실측(2026-08-29, owner 기계 RTX 5090)으로 이 경로는 다르다 --
1920x1080·81프레임·20스텝이 5분을 넘긴다. 유튜브 학습을 비동기로 바꾼 것과
같은 패턴(`BackgroundTasks` + `job_id` 폴링)을 그대로 재사용한다.

**취소도 된다(owner 요청 2026-08-29 3회차).** 작업마다 `threading.Event`를
들고 있다가, 취소 요청이 오면 그 이벤트만 켠다 -- 실제로 ComfyUI에 무엇을
멈추라고 말할지는 그 작업을 실제로 돌리고 있는 백그라운드 스레드(provider의
폴링 루프)가 직접 판단한다. 그래야 상태를 쓰는 주체가 하나로 유지되고,
"이미 끝난 작업을 뒤늦게 취소로 덮어쓰는" 경합이 생기지 않는다.
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    SceneVideoCreateRequest,
    SceneVideoResult,
    SceneVideoStartResponse,
    SceneVideoStatusResponse,
)
from videobox_core_engine.scene_video_service import SceneVideoGenerationError
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def build_scene_videos_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/scene-videos", status_code=status.HTTP_202_ACCEPTED)
    def start_scene_video(
        project_id: str, payload: SceneVideoCreateRequest, request: Request, background_tasks: BackgroundTasks,
    ) -> SceneVideoStartResponse:
        service = getattr(request.app.state, "scene_video_service", None)
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="scene_video_generation_unavailable",
            )
        job_id = uuid4().hex
        cancel_event = threading.Event()
        with _jobs_lock:
            _jobs[job_id] = {
                "project_id": project_id, "status": "processing", "result": None, "error_detail": None,
                "prompt_id": None, "cancel_event": cancel_event,
            }
        background_tasks.add_task(_run_job, service, project_id, job_id, payload, cancel_event)
        return SceneVideoStartResponse(job_id=job_id, status="processing")

    @router.get("/api/projects/{project_id}/scene-videos/{job_id}")
    def get_scene_video_job(project_id: str, job_id: str) -> SceneVideoStatusResponse:
        job = _get_job_or_404(project_id, job_id)
        result = SceneVideoResult(**job["result"]) if job["result"] is not None else None
        return SceneVideoStatusResponse(
            job_id=job_id, status=job["status"], result=result, error_detail=job["error_detail"],
        )

    @router.post("/api/projects/{project_id}/scene-videos/{job_id}/cancel")
    def cancel_scene_video(project_id: str, job_id: str) -> SceneVideoStatusResponse:
        """지금 돌고 있는 작업만 멈춘다 -- 끝난 작업을 다시 취소하지 않는다.

        **실제로 멈추는 일은 여기서 하지 않는다.** 이벤트만 켜고 바로 돌아온다
        -- ComfyUI에 무엇을 멈추라고 말할지는 그 작업을 실제로 돌리고 있는
        스레드가(이 요청이 처리될 즈음엔 이미 최대 20분째 그 자리에 있다)
        `/queue`로 자기 작업이 맞는지 직접 확인한 뒤 결정한다.
        """
        job = _get_job_or_404(project_id, job_id)
        if job["status"] != "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="scene_video_job_not_cancellable",
            )
        job["cancel_event"].set()
        result = SceneVideoResult(**job["result"]) if job["result"] is not None else None
        return SceneVideoStatusResponse(
            job_id=job_id, status=job["status"], result=result, error_detail=job["error_detail"],
        )

    @router.get("/api/projects/{project_id}/scene-videos")
    def list_scene_videos(project_id: str) -> dict[str, Any]:
        """만든 것을 다시 볼 수 있어야 한다 -- `scene_images.py`와 같은 이유."""
        try:
            clips = store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO)
        except Exception as exc:
            raise _http_error(exc) from exc
        videos = [asset for asset in clips if _is_generated_video(asset)]
        return {"videos": [_as_result(asset) for asset in videos]}

    return router


def _get_job_or_404(project_id: str, job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job["project_id"] != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scene_video_job_not_found")
    return job


def _record_prompt_id(job_id: str, prompt_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["prompt_id"] = prompt_id


def _run_job(
    service: Any, project_id: str, job_id: str, payload: SceneVideoCreateRequest, cancel_event: threading.Event,
) -> None:
    """`BackgroundTasks`가 응답을 보낸 뒤 부른다."""
    try:
        result = service.generate_scene_video(
            project_id=project_id,
            prompt=payload.prompt,
            segment_id=payload.segment_id,
            vertical=payload.vertical,
            gap_slot_id=payload.gap_slot_id,
            make_gif=payload.make_gif,
            quality=payload.quality,
            on_prompt_submitted=lambda prompt_id: _record_prompt_id(job_id, prompt_id),
            cancel_event=cancel_event,
        )
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "succeeded", "result": result, "error_detail": None})
    except SceneVideoGenerationError as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "failed", "result": None, "error_detail": _detail(exc)})
    except Exception as exc:  # noqa: BLE001 -- 백그라운드 작업이라 여기서 반드시 잡아야 폴링이 영원히 "처리 중"으로 남지 않는다
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "failed", "result": None, "error_detail": str(exc)})


def _is_generated_video(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") or {}
    return bool(metadata.get("generated_by")) and bool(metadata.get("scene_segment_id"))


def _as_result(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = asset.get("metadata") or {}
    return {
        "scene_asset_id": str(asset["asset_id"]),
        # `gif_asset_id`와 같은 이유로 목록 조회에서는 짝을 다시 찾지 않는다 --
        # 만드는 순간의 응답에서만 값이 있다. `library_asset_id`도 같다.
        "gif_asset_id": None,
        "library_asset_id": None,
        "gif_library_asset_id": None,
        "segment_id": str(metadata.get("scene_segment_id") or ""),
        "title": str(metadata.get("title") or "장면 영상"),
        "prompt": str(metadata.get("prompt") or ""),
        "video_prompt": str(metadata.get("video_prompt") or ""),
        "quality": str(metadata.get("quality") or "full"),
        "seed": int(metadata.get("seed") or 0),
        "elapsed_sec": metadata.get("elapsed_sec"),
    }


def _detail(exc: SceneVideoGenerationError) -> str:
    message = str(exc)
    if message.startswith("scene_video_"):
        return message.split(":", 1)[0]
    return f"scene_video_generation_{exc.code}"


__all__ = ["build_scene_videos_router"]
