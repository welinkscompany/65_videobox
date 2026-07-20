from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_provider_interfaces.llm import LLMProviderError
from videobox_storage.local_project_store import LocalProjectStore


class FailingBrollRecommender:
    def recommend(self, request):  # noqa: ANN001
        del request
        raise LLMProviderError(
            message="broll provider failed",
            error_code="BROLL_PROVIDER_FAILED",
            provider_name="local_qwen",
            retryable=False,
        )


def test_retry_job_reruns_a_failed_broll_recommendation(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Retry Broll Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
                "provider_trace": build_provider_trace(final_provider="local_qwen"),
            }
        ],
    )
    segment_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.SEGMENT_ANALYSIS,
        input_ref="transcription_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=segment_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref="segment_analysis_001",
    )
    failing_runner = LocalPipelineRunner(store, broll_recommender=FailingBrollRecommender())
    with pytest.raises(LLMProviderError):
        failing_runner.start_broll_recommendation(
            project_id=project.project_id,
            segment_analysis_job_id=segment_job["job_id"],
        )

    client = TestClient(create_app(projects_root=tmp_path))
    jobs_before = client.get(f"/api/projects/{project.project_id}/jobs").json()["jobs"]
    failed_job = next(job for job in jobs_before if job["job_type"] == "broll_recommendation")
    assert failed_job["status"] == "failed"

    retry_response = client.post(f"/api/projects/{project.project_id}/jobs/{failed_job['job_id']}/retry")

    assert retry_response.status_code == 202
    new_job_id = retry_response.json()["job_id"]
    assert new_job_id != failed_job["job_id"]
    assert retry_response.json()["status"] == "succeeded"

    result = client.get(f"/api/projects/{project.project_id}/jobs/broll-recommendation/{new_job_id}")
    assert result.status_code == 200


def test_retry_job_rejects_a_job_that_is_not_failed(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Retry Rejects Succeeded Project")
    job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TRANSCRIPTION,
        input_ref="narration_asset_001",
        status=JobStatus.SUCCEEDED,
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.post(f"/api/projects/{project.project_id}/jobs/{job['job_id']}/retry")

    assert response.status_code == 400
    assert "not in a failed state" in response.json()["detail"]


def test_retry_job_rejects_a_non_retryable_job_type(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Retry Rejects Partial Regen Project")
    job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.PARTIAL_REGENERATION,
        input_ref="session_001",
        status=JobStatus.FAILED,
    )

    client = TestClient(create_app(projects_root=tmp_path))
    response = client.post(f"/api/projects/{project.project_id}/jobs/{job['job_id']}/retry")

    assert response.status_code == 400
    assert "cannot be retried automatically" in response.json()["detail"]
