from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    AllJobsResponse,
    CreateProjectRequest,
    HomeSummaryResponse,
    JobListResponse,
    JobRecordResponse,
    JobRecordWithProjectResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectWorkspaceSummaryResponse,
    WorkspaceNextActionResponse,
)
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore

_LOGGER = logging.getLogger(__name__)


def build_projects_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: CreateProjectRequest) -> ProjectResponse:
        project = store.bootstrap_project(name=payload.name)
        return ProjectResponse(
            project_id=project.project_id,
            name=project.name,
            status=project.status.value,
            root_storage_uri=project.root_storage_uri,
        )

    @router.get("/api/projects")
    def list_projects(include_archived: bool = False) -> ProjectListResponse:
        projects = store.list_projects(include_archived=include_archived)
        return ProjectListResponse(
            projects=[
                ProjectResponse(
                    project_id=project["project_id"],
                    name=project["name"],
                    status=project["status"],
                    root_storage_uri=project["root_storage_uri"],
                )
                for project in projects
            ]
        )

    @router.post("/api/projects/{project_id}/archive")
    def archive_project(project_id: str) -> ProjectResponse:
        try:
            project = store.archive_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProjectResponse(
            project_id=project["project_id"],
            name=project["name"],
            status=project["status"],
            root_storage_uri=project["root_storage_uri"],
        )

    @router.post("/api/projects/{project_id}/restore")
    def restore_project(project_id: str) -> ProjectResponse:
        try:
            project = store.restore_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProjectResponse(
            project_id=project["project_id"],
            name=project["name"],
            status=project["status"],
            root_storage_uri=project["root_storage_uri"],
        )

    @router.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def delete_project_permanently(project_id: str, confirm: bool = False) -> None:
        # Confirmation is enforced here, not just in the UI's two-step
        # dialog -- a client bug or a replayed request must not be able to
        # delete a project without ever passing this gate.
        if not confirm:
            raise HTTPException(status_code=400, detail="permanent_delete_requires_confirm")
        try:
            store.delete_project_permanently(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> ProjectResponse:
        try:
            project = store.get_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProjectResponse(
            project_id=project["project_id"],
            name=project["name"],
            status=project["status"],
            root_storage_uri=project["root_storage_uri"],
        )

    @router.get("/api/projects/{project_id}/home-summary")
    def get_home_summary(project_id: str) -> HomeSummaryResponse:
        """Everything the three home cards claim, in one request.

        The cards used to state all three unconditionally, so each one could be
        false -- "no finished videos" stayed on screen after a render finished.
        Home must not poll the job list (ProductShell pins that the list is
        fetched only when the owner opens the job dialog), so the counting
        happens here and the screen makes exactly one call.
        """
        try:
            jobs = store.list_jobs(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        finished = sum(
            1
            for job in jobs
            if str(job.get("job_type")) == JobType.FINAL_RENDER
            and str(job.get("status")) == JobStatus.SUCCEEDED
        )
        try:
            session = store.get_latest_editing_session(project_id=project_id)
        except KeyError:
            # No draft yet is an ordinary state, not an error.
            session = None
        except Exception:
            # 여기까지 오면 초안이 없는 게 아니라 못 읽은 것이다. 카드는
            # 둘을 구분하지 않고 "아직 시작한 작업이 없어요"라고 말하므로,
            # 기록이 없으면 owner는 초안이 사라졌다고 믿게 된다.
            # 홈이 계속 열리는 동작은 그대로 둔다.
            _LOGGER.warning(
                "작업 중인 초안을 읽지 못해 없는 것으로 표시합니다 (project=%s).",
                project_id,
                exc_info=True,
            )
            session = None
        gaps = session.get("gap_slots") if isinstance(session, dict) else None
        return HomeSummaryResponse(
            finished_video_count=finished,
            has_draft=session is not None,
            asset_gap_count=len(gaps) if isinstance(gaps, list) else 0,
        )

    @router.get("/api/projects/{project_id}/workspace-summary")
    def get_workspace_summary(project_id: str) -> ProjectWorkspaceSummaryResponse:
        """Return the project card's single, store-backed source of truth.

        A missing latest session is an ordinary first-visit state.  Any other
        read failure is deliberately surfaced instead of becoming an empty
        project that sends the creator back to project creation.
        """
        try:
            project = store.get_project(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        try:
            jobs = store.list_jobs(project_id=project_id)
            try:
                session = store.get_latest_editing_session(project_id=project_id)
            except KeyError:
                session = None
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="workspace_summary_unavailable",
                ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace_summary_unavailable",
            ) from exc

        finished = sum(
            1
            for job in jobs
            if str(job.get("job_type")) == JobType.FINAL_RENDER
            and str(job.get("status")) == JobStatus.SUCCEEDED
        )
        final_jobs = [job for job in jobs if str(job.get("job_type")) == JobType.FINAL_RENDER]
        latest_final = final_jobs[-1] if final_jobs else None
        gaps = session.get("gap_slots") if isinstance(session, dict) else None
        timeline_review_status: str | None = None
        if isinstance(session, dict) and session.get("timeline_id"):
            try:
                review = store.get_review_state(
                    project_id=project_id,
                    timeline_id=str(session["timeline_id"]),
                )
            except KeyError:
                review = None
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="workspace_summary_unavailable",
                ) from exc
            if isinstance(review, dict):
                timeline_review_status = str(review.get("status") or "").strip().lower() or None

        if session is None:
            current_stage = "plan"
            state = "ready"
            action_label = "새 영상 시작"
        elif isinstance(gaps, list) and gaps:
            current_stage = "assets"
            state = "attention"
            action_label = "자산 준비"
        elif timeline_review_status == "blocked":
            current_stage = "review"
            state = "blocked"
            action_label = "검토 문제 해결"
        elif timeline_review_status in {"draft", "pending", "review"}:
            current_stage = "review"
            state = "ready"
            action_label = "검토하기"
        elif timeline_review_status in {"approved", "succeeded"}:
            current_stage = "output"
            state = "ready"
            action_label = "완성본 만들기"
        elif latest_final is not None and str(latest_final.get("status")) == JobStatus.SUCCEEDED:
            current_stage = "output"
            state = "ready"
            action_label = "완성본 보기"
        elif latest_final is not None and str(latest_final.get("status")) == JobStatus.FAILED:
            current_stage = "output"
            state = "attention"
            action_label = "출력 다시 시도"
        elif latest_final is not None and str(latest_final.get("status")) in {"pending", "running"}:
            current_stage = "output"
            state = "attention"
            action_label = "출력 상태 보기"
        else:
            current_stage = "edit"
            state = "ready"
            action_label = "계속 편집"

        thumbnail_url: str | None = None
        try:
            assets = store.list_assets(project_id=project_id)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="workspace_summary_unavailable",
            ) from exc
        for asset in assets:
            metadata = asset.get("metadata") if isinstance(asset, dict) else None
            if not isinstance(metadata, dict):
                continue
            if metadata.get("thumbnail_uri") or metadata.get("thumbnail_url"):
                thumbnail_url = (
                    f"/api/projects/{project_id}/assets/{asset['asset_id']}/thumbnail"
                )
                break

        timestamps = [str(project.get("updated_at") or "")]
        if isinstance(session, dict) and session.get("updated_at"):
            timestamps.append(str(session["updated_at"]))
        if latest_final and latest_final.get("finished_at"):
            timestamps.append(str(latest_final["finished_at"]))
        updated_at = max(timestamps)
        return ProjectWorkspaceSummaryResponse(
            project_id=project_id,
            display_name=str(project["name"]),
            updated_at=updated_at,
            current_stage=current_stage,
            state=state,
            thumbnail_url=thumbnail_url,
            finished_video_count=finished,
            next_action=WorkspaceNextActionResponse(
                label=action_label,
                href=f"/projects/{project_id}/{current_stage}",
            ),
        )

    @router.get("/api/projects/{project_id}/jobs")
    def list_project_jobs(project_id: str) -> JobListResponse:
        try:
            jobs = store.list_jobs(project_id=project_id)
        except Exception as exc:
            raise _http_error(exc) from exc
        return JobListResponse(jobs=[JobRecordResponse(**job) for job in jobs])

    @router.get("/api/jobs")
    def list_all_jobs() -> AllJobsResponse:
        jobs = store.list_all_jobs()
        return AllJobsResponse(jobs=[JobRecordWithProjectResponse(**job) for job in jobs])

    return router
