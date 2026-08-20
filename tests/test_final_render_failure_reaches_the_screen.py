from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore

APPROVAL_REQUIRED = "final_output_requires_review_approval"


def test_a_failed_render_tells_the_screen_why(tmp_path) -> None:
    """Rendering a real draft failed and the API answered `{"render": null}`
    with no reason, so the screen could only say `완성본을 만들지 못했어요` --
    while the job row held the actual cause: the timeline was never approved
    in 검토. That is one click away, and the owner had no way to know.

    The web type has declared `error_message` all along; the API just never
    filled it in. Both sides believed the other one carried the reason.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "실패 이유"}).json()["project_id"]

    store = LocalProjectStore(tmp_path)
    job = store.create_job(project_id=project_id, job_type=JobType.FINAL_RENDER, status=JobStatus.RUNNING)
    store.update_job(
        project_id=project_id,
        job_id=job["job_id"],
        status=JobStatus.FAILED,
        error_message=APPROVAL_REQUIRED,
    )

    body = client.get(f"/api/projects/{project_id}/final-renders/{job['job_id']}").json()
    assert body["status"] == "failed"
    assert body["render"] is None
    assert body["error_message"] == APPROVAL_REQUIRED


def test_the_approval_gate_names_itself_with_a_code(tmp_path) -> None:
    """The gate used to raise an English sentence while every other blocker in
    this file raises a snake_case code. A sentence cannot be mapped to creator
    language on the screen without matching prose, so it would have arrived as
    either raw English or nothing at all.
    """
    import inspect

    from videobox_core_engine import _pipeline_private_helpers

    source = inspect.getsource(_pipeline_private_helpers)
    assert APPROVAL_REQUIRED in source
    assert "Timeline requires explicit approval" not in source
