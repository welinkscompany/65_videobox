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

**job 상태는 메모리에만 있지 않다(2026-08-30, 뒤로 미뤘던 항목을 마저 처리).**
`_jobs`는 여전히 살아 있는 취소 이벤트·진행 중 prompt_id를 들고 있으려고
남긴다(`threading.Event`는 애초에 직렬화할 수 없다) -- 하지만 상태·결과의
정본은 `LocalProjectStore`의 기존 `jobs` 테이블이다. 이 테이블과
`recover_orphaned_in_process_jobs`(재시작 시 멈춰 있던 job을 실패로 정리하는
기존 장치, `main.py`의 `_recover_in_process_jobs`가 시작할 때마다 모든
프로젝트에 이미 돌리고 있다)는 `final_render`·`capcut_draft_export` 같은
다른 job 종류가 이미 쓰고 있었다 -- 새 스키마를 만드는 대신 `JobType`에
`SCENE_VIDEO_GENERATION` 한 줄만 더해 그 재사용 게이트를 그대로 탄다. 완성된
결과는 자산 메타데이터에 이미 다 있으므로(`_as_result`) `output_ref`에는
`scene_asset_id`만 적어 두고, 다시 조회할 때 그 자산에서 결과를 되짚는다 --
같은 내용을 두 곳에 중복 저장하지 않는다."""
from __future__ import annotations

import threading
from typing import Any

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
from videobox_domain_models.jobs import JobStatus, JobType
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
        # 재시작 뒤에도 조회·복구가 가능하려면 job_id가 DB 행을 가리켜야 한다
        # -- `uuid4().hex`(메모리 dict 키로만 썼던 예전 방식)가 아니라
        # `create_job`이 만든 값을 그대로 쓴다.
        job_row = store.create_job(
            project_id=project_id, job_type=JobType.SCENE_VIDEO_GENERATION,
            input_ref=payload.segment_id, status=JobStatus.RUNNING,
        )
        job_id = str(job_row["job_id"])
        cancel_event = threading.Event()
        with _jobs_lock:
            _jobs[job_id] = {
                "project_id": project_id, "status": "processing", "result": None, "error_detail": None,
                "prompt_id": None, "cancel_event": cancel_event,
            }
        background_tasks.add_task(_run_job, service, store, project_id, job_id, payload, cancel_event)
        return SceneVideoStartResponse(job_id=job_id, status="processing")

    @router.get("/api/projects/{project_id}/scene-videos/{job_id}")
    def get_scene_video_job(project_id: str, job_id: str) -> SceneVideoStatusResponse:
        snapshot = _snapshot_job(store, project_id, job_id)
        result = SceneVideoResult(**snapshot["result"]) if snapshot["result"] is not None else None
        return SceneVideoStatusResponse(
            job_id=job_id, status=snapshot["status"], result=result, error_detail=snapshot["error_detail"],
        )

    @router.post("/api/projects/{project_id}/scene-videos/{job_id}/cancel")
    def cancel_scene_video(project_id: str, job_id: str) -> SceneVideoStatusResponse:
        """지금 돌고 있는 작업만 멈춘다 -- 끝난 작업을 다시 취소하지 않는다.

        **실제로 멈추는 일은 여기서 하지 않는다.** 이벤트만 켜고 바로 돌아온다
        -- ComfyUI에 무엇을 멈추라고 말할지는 그 작업을 실제로 돌리고 있는
        스레드가(이 요청이 처리될 즈음엔 이미 최대 20분째 그 자리에 있다)
        `/queue`로 자기 작업이 맞는지 직접 확인한 뒤 결정한다.

        코드리뷰(2026-08-30)로 잡힌 결함 -- 상태 확인과 이벤트를 켜는 동작이
        예전엔 잠금 밖에서 따로 일어나서, `_run_job`이 그 사이에 끝내 버리면
        이미 끝난 작업에 조용히 이벤트만 켜고(아무도 안 보는) 409도 안 뜨는
        경합이 있었다. 이제 확인·이벤트 켜기·읽기를 한 번의 잠금 안에서 한다.

        **이 프로세스가 그 job을 기억하고 있을 때만 취소할 수 있다.** 재시작
        때문에 메모리에서 사라진 job은 취소할 실제 스레드가 이미 없다 --
        `recover_orphaned_in_process_jobs`가 시작할 때 이미 실패로 정리했을
        것이므로, DB에는 있지만 메모리에는 없는 job은 그냥 취소 불가(409)로
        본다(진행 중이 아니므로 이 응답이 맞다).
        """
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None and job["project_id"] == project_id:
                if job["status"] != "processing":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT, detail="scene_video_job_not_cancellable",
                    )
                job["cancel_event"].set()
                snapshot = dict(job)
                result = SceneVideoResult(**snapshot["result"]) if snapshot["result"] is not None else None
                return SceneVideoStatusResponse(
                    job_id=job_id, status=snapshot["status"], result=result, error_detail=snapshot["error_detail"],
                )
        try:
            store.get_job(project_id=project_id, job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scene_video_job_not_found") from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="scene_video_job_not_cancellable")

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


def _snapshot_job(store: LocalProjectStore, project_id: str, job_id: str) -> dict[str, Any]:
    """잠금 안에서 한 번에 복사해 돌려준다 -- 코드리뷰(2026-08-30)로 잡힌
    결함: 예전엔 잠금 밖에서 같은 dict 참조를 그대로 돌려주고 호출부가
    `status`/`result`/`error_detail`을 각각 따로 읽었다. 그 사이에
    `_run_job`이 `job.update(...)`을 끝내면 "성공했는데 result는 없음" 같은
    앞뒤가 안 맞는 조합을 돌려줄 수 있었다.

    **이 프로세스 메모리에 없으면 DB로 넘어간다(2026-08-30).** 이 프로세스가
    시작된 뒤로 한 번도 이 job을 다룬 적이 없는 경우(다른 프로세스가 만든
    job을 재시작 뒤 이 프로세스가 이어받은 경우)다. `store.get_job`이
    `KeyError`를 던지면 정말 없는 job이므로 그대로 404다."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None and job["project_id"] == project_id:
            return dict(job)
    try:
        row = store.get_job(project_id=project_id, job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scene_video_job_not_found") from exc
    return _snapshot_from_job_row(store, project_id, row)


def _snapshot_from_job_row(store: LocalProjectStore, project_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """DB에 남은 job 행 하나를 화면이 기대하는 모양으로 바꾼다.

    결과 자체는 두 번 저장하지 않는다 -- 완성된 영상은 이미 scene 자산
    메타데이터에 다 있으므로(`scene_video_service.py`), `output_ref`가
    가리키는 자산을 다시 읽어 `_as_result`로 되짚는다. 자산이 이미 지워졌으면
    (드문 경우) 조용히 실패로 답한다 -- 있지도 않은 결과를 지어내지 않는다."""
    status_value = str(row["status"])
    if status_value == JobStatus.SUCCEEDED.value:
        try:
            asset = store.get_asset(project_id=project_id, asset_id=str(row["output_ref"]))
        except KeyError:
            return {"status": "failed", "result": None, "error_detail": "scene_video_result_asset_missing"}
        return {"status": "succeeded", "result": _as_result(asset), "error_detail": None}
    if status_value == JobStatus.FAILED.value:
        return {"status": "failed", "result": None, "error_detail": row.get("error_message")}
    return {"status": "processing", "result": None, "error_detail": None}


def _record_prompt_id(job_id: str, prompt_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["prompt_id"] = prompt_id


def _run_job(
    service: Any, store: LocalProjectStore, project_id: str, job_id: str,
    payload: SceneVideoCreateRequest, cancel_event: threading.Event,
) -> None:
    """`BackgroundTasks`가 응답을 보낸 뒤 부른다.

    메모리(`_jobs`)와 DB(`store`의 `jobs` 테이블) 둘 다 갱신한다 -- 메모리는
    이 프로세스가 살아 있는 동안 폴링에 빠르게 답하려는 것이고, DB는 이
    프로세스가 재시작되거나 다른 프로세스가 이어받았을 때도 상태가 남아
    있게 하려는 것이다(2026-08-30)."""
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
        _update_job_row(store, project_id, job_id, JobStatus.SUCCEEDED, output_ref=result["scene_asset_id"])
    except SceneVideoGenerationError as exc:
        detail = _detail(exc)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "failed", "result": None, "error_detail": detail})
        _update_job_row(store, project_id, job_id, JobStatus.FAILED, error_message=detail)
    except Exception as exc:  # noqa: BLE001 -- 백그라운드 작업이라 여기서 반드시 잡아야 폴링이 영원히 "처리 중"으로 남지 않는다
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "failed", "result": None, "error_detail": str(exc)})
        _update_job_row(store, project_id, job_id, JobStatus.FAILED, error_message=str(exc))


def _update_job_row(
    store: LocalProjectStore, project_id: str, job_id: str, status_value: JobStatus,
    *, output_ref: str | None = None, error_message: str | None = None,
) -> None:
    """DB 쪽 갱신 실패가 방금 만든(또는 실패로 확정된) 결과 자체를 지우면 안
    된다 -- 메모리 쪽은 이미 갱신됐으니 이 프로세스가 살아 있는 한 폴링은
    정확하게 답한다. DB는 재시작 대비용 이중화이지 유일한 정본이 아니다."""
    try:
        store.update_job(
            project_id=project_id, job_id=job_id, status=status_value,
            output_ref=output_ref, error_message=error_message,
        )
    except Exception:  # noqa: BLE001 -- 위 설명 참고
        pass


def _is_generated_video(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") or {}
    return bool(metadata.get("generated_by")) and bool(metadata.get("scene_segment_id"))


def _as_result(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = asset.get("metadata") or {}
    return {
        "scene_asset_id": str(asset["asset_id"]),
        # 만드는 순간에 `scene_video_service.py`가 이 값들을 scene 자산 메타데이터에도
        # 같이 적어 둔다 -- 그래서 목록 조회(새로고침 뒤)에서도 그대로 보인다.
        "gif_asset_id": metadata.get("gif_asset_id"),
        "library_asset_id": metadata.get("library_asset_id"),
        "gif_library_asset_id": metadata.get("gif_library_asset_id"),
        "library_ingest_error": metadata.get("library_ingest_error"),
        "gif_library_ingest_error": metadata.get("gif_library_ingest_error"),
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
