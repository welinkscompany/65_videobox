from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from videobox_api.errors import _http_error
from videobox_api.models import (
    AllJobsResponse,
    CreateProjectRequest,
    JobListResponse,
    JobRecordResponse,
    JobRecordWithProjectResponse,
    ProjectListResponse,
    ProjectResponse,
)
from videobox_storage.local_project_store import LocalProjectStore


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
