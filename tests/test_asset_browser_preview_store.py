from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> tuple[LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Browser preview")
    return store, project.project_id


def test_asset_preview_job_type_is_durable() -> None:
    assert JobType.ASSET_PREVIEW_PROXY.value == "asset_preview_proxy"


def test_preview_job_reuses_only_an_active_matching_source_identity(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)

    first, created = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")
    reused, reused_created = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")

    assert created is True
    assert reused_created is False
    assert reused["job_id"] == first["job_id"]
    assert first["job_type"] == JobType.ASSET_PREVIEW_PROXY.value
    assert first["status"] == JobStatus.RUNNING.value

    store.update_job(project_id=project_id, job_id=first["job_id"], status=JobStatus.FAILED, error_message="PREVIEW_RENDER_FAILED")
    retry, retry_created = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")
    assert retry_created is True
    assert retry["job_id"] != first["job_id"]


def test_preview_job_claim_is_atomic_for_concurrent_callers(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)

    def claim(_index: int):
        return store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(claim, range(16)))

    assert len({claim[0]["job_id"] for claim in claims}) == 1
    assert sum(1 for _job, created in claims if created) == 1


def test_latest_preview_job_and_orphan_recovery_are_scoped(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    old, _ = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")
    store.update_job(project_id=project_id, job_id=old["job_id"], status=JobStatus.SUCCEEDED, output_ref="project://preview.mp4")
    latest, _ = store.create_or_reuse_active_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")
    unrelated = store.create_job(project_id=project_id, job_type=JobType.MEDIA_ANALYSIS, status=JobStatus.RUNNING)

    assert store.get_latest_asset_preview_job(project_id=project_id, input_ref="asset-1:fingerprint-a")["job_id"] == latest["job_id"]
    assert store.get_latest_asset_preview_job(project_id=project_id, input_ref="missing") is None

    assert store.recover_orphaned_asset_preview_jobs(project_id=project_id) == 1
    recovered = store.get_job(project_id=project_id, job_id=latest["job_id"])
    assert recovered["status"] == JobStatus.FAILED.value
    assert recovered["error_message"] == "PREVIEW_WORKER_RESTARTED"
    assert store.get_job(project_id=project_id, job_id=old["job_id"])["status"] == JobStatus.SUCCEEDED.value
    assert store.get_job(project_id=project_id, job_id=unrelated["job_id"])["status"] == JobStatus.RUNNING.value
