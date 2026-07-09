from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def test_list_all_jobs_merges_jobs_across_every_project(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_a = store.bootstrap_project(name="Project A")
    project_b = store.bootstrap_project(name="Project B")
    store.create_job(
        project_id=project_a.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="asset_001",
        status=JobStatus.SUCCEEDED,
    )
    store.create_job(
        project_id=project_b.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.FAILED,
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get("/api/jobs")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    project_names = {job["project_name"] for job in jobs}
    assert project_names == {"Project A", "Project B"}
    job_types = {job["job_type"] for job in jobs}
    assert job_types == {"transcription", "segment_analysis"}


def test_list_all_jobs_returns_empty_list_when_no_projects_exist(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert response.json()["jobs"] == []
