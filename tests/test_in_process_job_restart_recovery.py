"""A restart used to strand every in-process job as `running` forever.

The work for these job types runs on a daemon thread inside the API process
(routers/outputs.py, routers/jobs.py). When the container restarts the thread
dies, but the row keeps saying `running` -- the screen shows a spinner that
never stops, and `retry_job` refuses anything that is not `failed`, so there
is no way out. Media analysis and asset previews already recover at startup;
these job types did not.
"""

from __future__ import annotations

from pathlib import Path

from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> tuple[LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("복구 시험")
    return store, project.project_id


def test_restart_fails_stranded_in_process_jobs_so_the_owner_can_retry(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    stranded = store.create_job(project_id=project_id, job_type=JobType.TRANSCRIPTION, status=JobStatus.RUNNING)
    pending = store.create_job(project_id=project_id, job_type=JobType.FINAL_RENDER, status=JobStatus.PENDING)
    done = store.create_job(project_id=project_id, job_type=JobType.TIMELINE_BUILD, status=JobStatus.SUCCEEDED)

    recovered = store.recover_orphaned_in_process_jobs(project_id=project_id)

    assert sorted(recovered) == sorted([str(stranded["job_id"]), str(pending["job_id"])])
    for job_id in recovered:
        row = store.get_job(project_id=project_id, job_id=job_id)
        assert row["status"] == JobStatus.FAILED.value
        assert row["error_message"] == "WORKER_RESTARTED"
    assert store.get_job(project_id=project_id, job_id=str(done["job_id"]))["status"] == JobStatus.SUCCEEDED.value


def test_recovery_leaves_jobs_owned_by_their_own_recovery_path_alone(tmp_path: Path) -> None:
    # Media analysis and asset previews each have a recovery of their own that
    # knows how to requeue the work. Failing them here would take that away.
    store, project_id = _store(tmp_path)
    analysis = store.create_job(project_id=project_id, job_type=JobType.MEDIA_ANALYSIS, status=JobStatus.RUNNING)
    preview = store.create_job(project_id=project_id, job_type=JobType.ASSET_PREVIEW_PROXY, status=JobStatus.RUNNING)

    assert store.recover_orphaned_in_process_jobs(project_id=project_id) == []

    assert store.get_job(project_id=project_id, job_id=str(analysis["job_id"]))["status"] == JobStatus.RUNNING.value
    assert store.get_job(project_id=project_id, job_id=str(preview["job_id"]))["status"] == JobStatus.RUNNING.value


def test_a_recovered_job_can_actually_be_retried(tmp_path: Path) -> None:
    # The point of the change: `retry_job` rejects anything that is not
    # `failed`, so recovery is what makes the owner's retry button work.
    store, project_id = _store(tmp_path)
    stranded = store.create_job(project_id=project_id, job_type=JobType.TRANSCRIPTION, status=JobStatus.RUNNING)

    store.recover_orphaned_in_process_jobs(project_id=project_id)

    assert store.get_job(project_id=project_id, job_id=str(stranded["job_id"]))["status"] == JobStatus.FAILED.value
