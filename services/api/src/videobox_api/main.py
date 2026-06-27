from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, status
from pydantic import BaseModel, Field

from videobox_core_engine.settings import DEFAULT_PROJECTS_ROOT
from videobox_storage.local_project_store import LocalProjectStore


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    status: str
    root_storage_uri: str


def create_app(*, projects_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="VideoBox API", version="0.1.0")
    store = LocalProjectStore(projects_root or DEFAULT_PROJECTS_ROOT)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(payload: CreateProjectRequest) -> ProjectResponse:
        project = store.bootstrap_project(name=payload.name)
        return ProjectResponse(
            project_id=project.project_id,
            name=project.name,
            status=project.status.value,
            root_storage_uri=project.root_storage_uri,
        )

    return app
