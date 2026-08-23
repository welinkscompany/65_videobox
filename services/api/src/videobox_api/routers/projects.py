from __future__ import annotations

import logging
from datetime import UTC, datetime

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
    RenameProjectRequest,
    WorkspaceNextActionResponse,
)
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore

_LOGGER = logging.getLogger(__name__)


def build_projects_router(store: LocalProjectStore) -> APIRouter:
    router = APIRouter()

    def _job_temporal_key(job: dict[str, object]) -> tuple[float, str]:
        """Order output jobs by recorded timestamps, never list position."""
        for field in ("updated_at", "finished_at", "started_at", "created_at"):
            value = job.get(field)
            if value is None:
                continue
            try:
                parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return (parsed.timestamp(), str(job.get("job_id") or ""))
            except (TypeError, ValueError, OverflowError):
                continue
        return (float("-inf"), str(job.get("job_id") or ""))

    def _latest_final_job(jobs: list[dict[str, object]]) -> dict[str, object] | None:
        final_jobs = [job for job in jobs if str(job.get("job_type")) == JobType.FINAL_RENDER]
        if not final_jobs:
            return None
        # A retry can be claimed before the worker has populated timestamps.
        # Its active lifecycle state is stronger evidence than an older
        # terminal result, so keep the card on the retry/status action.
        untimestamped_active = [
            job
            for job in final_jobs
            if str(job.get("status")) in {JobStatus.PENDING, JobStatus.RUNNING}
            and _job_temporal_key(job)[0] == float("-inf")
        ]
        if untimestamped_active:
            return max(untimestamped_active, key=lambda job: str(job.get("job_id") or ""))
        return max(final_jobs, key=_job_temporal_key)

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

    @router.patch("/api/projects/{project_id}")
    def rename_project(project_id: str, payload: RenameProjectRequest) -> ProjectResponse:
        """Rename the project. No `expected_revision` here on purpose.

        Every endpoint in this repo that carries one guards a row that
        actually has a `revision` column (creation briefs, draft readiness,
        editing sessions). The `projects` table has no such column, and its
        two existing mutations -- archive and restore -- guard nothing
        either. Inventing a counter for this one field would mean a schema
        migration on both SQLite and Postgres to protect a single-user,
        local-first tool from a lost update it cannot really have. Left out
        deliberately; add it with the rest of the table if projects ever gain
        concurrent writers.
        """
        try:
            project = store.rename_project(project_id=project_id, name=payload.name)
        except Exception as exc:
            raise _http_error(exc) from exc
        return ProjectResponse(
            project_id=project["project_id"],
            name=project["name"],
            status=project["status"],
            root_storage_uri=project["root_storage_uri"],
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
        latest_final = _latest_final_job(jobs)
        gaps = session.get("gap_slots") if isinstance(session, dict) else None
        timeline_review_status: str | None = None
        if isinstance(session, dict) and session.get("timeline_id"):
            timeline_id = str(session["timeline_id"])
            # 아직 첫 초안을 만들지 않은 세션(빈 편집판 `blank:...`, 붙여넣은
            # 대본으로 여는 `script_draft:...`)은 `timelines` 행이 아예 없다 --
            # 검토를 받을 대상이 아직 없는 정상 상태다. 실제 타임라인을 만드는
            # 경로(`save_timeline_run`, atomic draft bundle)는 전부 검토 행도
            # 같은 호출에서 함께 만든다 -- 타임라인은 있는데 검토 행이 없으면
            # 그건 진짜 자료 문제(예: 두 기록 사이 비정상 종료)다. 한 번의
            # LEFT JOIN 조회로 세 경우(없음/있고 검토도 있음/있는데 검토만
            # 없음)를 한 번에 가른다 -- 카탈로그 카드마다 부르는 자리라 조회를
            # 두 번으로 나누지 않는다.
            try:
                review = store.get_review_state_if_timeline_started(
                    project_id=project_id,
                    timeline_id=timeline_id,
                )
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
            action_label = "계속 만들기"
        elif timeline_review_status == "blocked":
            current_stage = "review"
            state = "blocked"
            action_label = "검토 문제 해결"
        elif latest_final is not None and str(latest_final.get("status")) == JobStatus.FAILED:
            current_stage = "output"
            state = "attention"
            action_label = "출력 다시 시도"
        elif latest_final is not None and str(latest_final.get("status")) in {"pending", "running"}:
            current_stage = "output"
            state = "attention"
            action_label = "출력 상태 보기"
        elif latest_final is not None and str(latest_final.get("status")) == JobStatus.SUCCEEDED:
            current_stage = "output"
            state = "ready"
            action_label = "완성본 보기"
        elif isinstance(gaps, list) and gaps:
            current_stage = "assets"
            state = "attention"
            action_label = "자산 준비"
        elif timeline_review_status in {"draft", "pending", "review"}:
            current_stage = "review"
            state = "ready"
            action_label = "검토하기"
        elif timeline_review_status in {"approved", "succeeded"}:
            current_stage = "output"
            state = "ready"
            action_label = "완성본 만들기"
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
