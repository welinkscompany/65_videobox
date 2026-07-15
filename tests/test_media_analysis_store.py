from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_storage.local_project_store import LocalProjectStore


def _store(tmp_path: Path) -> tuple[LocalProjectStore, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Media analysis")
    return store, project.project_id


def test_media_analysis_persists_retry_and_recovers_orphan(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )

    claimed = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])

    assert claimed["status"] == MediaAnalysisStatus.RUNNING.value
    recovered = store.recover_orphaned_media_analysis_jobs(project_id=project_id)
    assert recovered == [job["analysis_id"]]
    assert store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == MediaAnalysisStatus.QUEUED.value


def test_media_analysis_recovery_returns_only_runs_it_requeued(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    queued = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:queued",
        cache_key="cache-v1",
    )
    orphan = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_002",
        idempotency_key="sha:orphan",
        cache_key="cache-v1",
    )
    assert store.claim_media_analysis(project_id=project_id, analysis_id=orphan["analysis_id"])

    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == [orphan["analysis_id"]]
    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == []
    assert store.get_media_analysis(project_id=project_id, analysis_id=queued["analysis_id"])["status"] == MediaAnalysisStatus.QUEUED.value


def test_orphan_recovery_does_not_requeue_exhausted_attempt(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset", idempotency_key="exhausted", cache_key="cache")
    for _ in range(3):
        claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]); assert claim
        if claim["attempt"] < 3:
            store.fail_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], error_code="retry", error_message="retry", next_retry_at="2000-01-01T00:00:00+00:00")
    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == []
    assert store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == MediaAnalysisStatus.FAILED.value


def test_media_analysis_claim_is_atomic_and_reports_the_loser(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )

    winner = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    loser = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])

    assert winner is not None
    assert winner["status"] == MediaAnalysisStatus.RUNNING.value
    assert loser is None
    assert winner["attempt"] == 1


def test_media_analysis_concurrent_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    barrier = Barrier(2)

    def claim() -> dict[str, object] | None:
        barrier.wait()
        return store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim(), range(2)))

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0]["attempt"] == 1


def test_media_analysis_reclaims_a_due_failed_run_and_increments_attempt(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    store.fail_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=claim["attempt"],
        error_code="VLM_TIMEOUT",
        error_message="Timed out.",
        next_retry_at="2000-01-01T00:00:00+00:00",
    )

    retry = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])

    assert retry is not None
    assert retry["status"] == MediaAnalysisStatus.RUNNING.value
    assert retry["attempt"] == 2
    assert retry["next_retry_at"] is None


def test_media_analysis_rejects_stale_worker_attempt_after_retry_claim(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    first_claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert first_claim is not None
    assert store.fail_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=first_claim["attempt"],
        error_code="VLM_TIMEOUT",
        error_message="Timed out.",
        next_retry_at="2000-01-01T00:00:00+00:00",
    )
    retry_claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert retry_claim is not None

    stale_result = store.complete_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=first_claim["attempt"],
        result={"summary": "stale worker"},
    )

    assert stale_result is None
    assert store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == MediaAnalysisStatus.RUNNING.value


def test_media_analysis_only_allows_running_job_to_transition(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )

    assert store.complete_media_analysis(
        project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=0, result={"summary": "ignored"}
    ) is None
    cancelled = store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=0)
    assert cancelled is not None
    assert store.fail_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=0,
        error_code="ignored",
        error_message="ignored",
    ) is None
    assert store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == MediaAnalysisStatus.CANCELLED.value


def test_media_analysis_returns_existing_run_for_same_idempotency_key(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)

    first = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    second = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )

    assert second == first


def test_get_media_analysis_tolerates_queue_snapshot_race(tmp_path: Path, monkeypatch) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset_001", idempotency_key="race", cache_key="cache")
    monkeypatch.setattr(store, "list_media_analysis", lambda *, project_id: [])
    assert store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["queue_position"] is None


def test_media_analysis_ignores_late_completion_after_cancellation(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None

    cancelled = store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"])
    late = store.complete_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"summary": "late"},
    )

    assert cancelled["status"] == MediaAnalysisStatus.CANCELLED.value
    assert late is None


def test_media_analysis_cancellation_keeps_late_error_from_overwriting_terminal_state(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    cancelled = store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"])

    late_error = store.fail_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=claim["attempt"],
        error_code="VLM_TIMEOUT",
        error_message="Late worker failure.",
    )

    assert cancelled is not None
    assert late_error is None
    persisted = store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert persisted["status"] == MediaAnalysisStatus.CANCELLED.value
    assert persisted["error_code"] is None


def test_media_analysis_can_complete_running_run_as_needs_review(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None

    completed = store.complete_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"summary": "operator review required"},
        status=MediaAnalysisStatus.NEEDS_REVIEW,
    )

    assert completed is not None
    assert completed["status"] == MediaAnalysisStatus.NEEDS_REVIEW.value


def test_media_analysis_transitions_to_blocked_and_retriable_failure(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    blocked_job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_001",
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    blocked_claim = store.claim_media_analysis(project_id=project_id, analysis_id=blocked_job["analysis_id"])
    assert blocked_claim is not None

    blocked = store.mark_media_analysis_blocked(
        project_id=project_id,
        analysis_id=blocked_job["analysis_id"],
        expected_attempt=blocked_claim["attempt"],
        error_code="MODEL_UNAVAILABLE",
        error_message="Local vision model is unavailable.",
    )
    failed_job = store.create_media_analysis(
        project_id=project_id,
        asset_id="asset_002",
        idempotency_key="sha:profile:failure",
        cache_key="cache-v1",
    )
    failed_claim = store.claim_media_analysis(project_id=project_id, analysis_id=failed_job["analysis_id"])
    assert failed_claim is not None
    failed = store.fail_media_analysis(
        project_id=project_id,
        analysis_id=failed_job["analysis_id"],
        expected_attempt=failed_claim["attempt"],
        error_code="VLM_TIMEOUT",
        error_message="Timed out.",
        next_retry_at="2026-07-14T00:00:05+00:00",
    )

    assert blocked["status"] == MediaAnalysisStatus.BLOCKED.value
    assert failed["status"] == MediaAnalysisStatus.FAILED.value
    assert failed["next_retry_at"] == "2026-07-14T00:00:05+00:00"
