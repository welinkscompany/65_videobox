from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from hashlib import sha256

from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_domain_models.assets import AssetType
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


def test_local_semantic_lookup_ranks_persisted_embeddings_after_store_restart(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    near_path, far_path = tmp_path / "near.mp4", tmp_path / "far.mp4"
    near_path.write_bytes(b"near")
    far_path.write_bytes(b"far")
    near_asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=near_path)
    far_asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=far_path)
    near = store.create_media_analysis(project_id=project_id, asset_id=near_asset.asset_id, idempotency_key=f"{sha256(near_path.read_bytes()).hexdigest()}:near", cache_key="cache-near")
    far = store.create_media_analysis(project_id=project_id, asset_id=far_asset.asset_id, idempotency_key=f"{sha256(far_path.read_bytes()).hexdigest()}:far", cache_key="cache-far")
    near_claim = store.claim_media_analysis(project_id=project_id, analysis_id=near["analysis_id"])
    far_claim = store.claim_media_analysis(project_id=project_id, analysis_id=far["analysis_id"])
    assert near_claim and far_claim
    store.record_media_embedding(
        project_id=project_id,
        analysis_id=near["analysis_id"],
        source_sha256="sha-near",
        profile_hash="cache-near",
        embedding=[1.0, 0.0],
    )
    store.record_media_embedding(
        project_id=project_id,
        analysis_id=far["analysis_id"],
        source_sha256="sha-far",
        profile_hash="cache-far",
        embedding=[0.0, 1.0],
    )
    assert store.complete_media_analysis(project_id=project_id, analysis_id=near["analysis_id"], expected_attempt=near_claim["attempt"], result={})
    assert store.complete_media_analysis(project_id=project_id, analysis_id=far["analysis_id"], expected_attempt=far_claim["attempt"], result={})

    restarted = LocalProjectStore(tmp_path)
    matches = restarted.find_local_media_embedding_matches(
        project_id=project_id,
        query_embedding=[0.9, 0.1],
        limit=2,
    )

    assert [item["analysis_id"] for item in matches] == [near["analysis_id"], far["analysis_id"]]
    assert matches[0]["asset_id"] == near_asset.asset_id
    assert matches[0]["score"] > matches[1]["score"]


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


def _exhaust_retry_budget(store: LocalProjectStore, project_id: str, analysis_id: str) -> None:
    """Burn the initial run plus both permitted retries, the way the worker does:
    the last failure carries no next_retry_at because the backoff table is spent."""
    for attempt in (1, 2, 3):
        claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis_id)
        assert claim is not None and claim["attempt"] == attempt
        store.fail_media_analysis(
            project_id=project_id,
            analysis_id=analysis_id,
            expected_attempt=attempt,
            error_code="MEDIA_ANALYSIS_FAILED",
            error_message="LM Studio timed out.",
            next_retry_at="2000-01-01T00:00:00+00:00" if attempt < 3 else None,
        )


def test_recovery_revives_an_analysis_the_retry_budget_abandoned(tmp_path: Path) -> None:
    """A spent budget leaves `failed` with no next_retry_at, which the claim query
    can never take again. Without this the run is frozen until the owner finds the
    manual retry, and the poller re-dispatches it forever with nothing happening."""
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset", idempotency_key="frozen", cache_key="cache")
    _exhaust_retry_budget(store, project_id, job["analysis_id"])
    frozen = store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert frozen["status"] == MediaAnalysisStatus.FAILED.value and frozen["next_retry_at"] is None
    assert store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is None

    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == [job["analysis_id"]]

    revived = store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert revived["status"] == MediaAnalysisStatus.QUEUED.value
    assert revived["error_code"] is None and revived["error_message"] is None
    claimed = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claimed is not None and claimed["attempt"] == 4


def test_recovery_grants_one_fresh_attempt_per_sweep_not_a_loop(tmp_path: Path) -> None:
    """The revival must not become its own retry loop: once requeued, a second
    sweep has nothing left to do until the run fails again."""
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset", idempotency_key="once", cache_key="cache")
    _exhaust_retry_budget(store, project_id, job["analysis_id"])

    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == [job["analysis_id"]]
    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == []


def test_recovery_leaves_a_failed_run_whose_retry_is_still_pending(tmp_path: Path) -> None:
    """A run with a due retry already belongs to the claim query. Requeuing it here
    would reset the backoff the worker deliberately booked."""
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset", idempotency_key="pending", cache_key="cache")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    store.fail_media_analysis(
        project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"],
        error_code="MEDIA_ANALYSIS_FAILED", error_message="Timed out.", next_retry_at="2999-01-01T00:00:00+00:00",
    )

    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == []

    still_failed = store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert still_failed["status"] == MediaAnalysisStatus.FAILED.value
    assert still_failed["next_retry_at"] == "2999-01-01T00:00:00+00:00"


def test_recovery_leaves_blocked_and_cancelled_runs_alone(tmp_path: Path) -> None:
    """Blocked means a human has to change something -- a missing source or an
    unconfigured worker. Reviving those would just burn the provider on every restart."""
    store, project_id = _store(tmp_path)
    blocked = store.create_media_analysis(project_id=project_id, asset_id="asset_a", idempotency_key="blocked", cache_key="cache")
    cancelled = store.create_media_analysis(project_id=project_id, asset_id="asset_b", idempotency_key="cancelled", cache_key="cache")
    blocked_claim = store.claim_media_analysis(project_id=project_id, analysis_id=blocked["analysis_id"])
    cancelled_claim = store.claim_media_analysis(project_id=project_id, analysis_id=cancelled["analysis_id"])
    assert blocked_claim is not None and cancelled_claim is not None
    store.mark_media_analysis_blocked(
        project_id=project_id, analysis_id=blocked["analysis_id"], expected_attempt=blocked_claim["attempt"],
        error_code="SOURCE_MISSING", error_message="gone",
    )
    store.request_media_analysis_cancel(
        project_id=project_id, analysis_id=cancelled["analysis_id"], expected_attempt=cancelled_claim["attempt"],
    )

    assert store.recover_orphaned_media_analysis_jobs(project_id=project_id) == []

    assert store.get_media_analysis(project_id=project_id, analysis_id=blocked["analysis_id"])["status"] == MediaAnalysisStatus.BLOCKED.value
    assert store.get_media_analysis(project_id=project_id, analysis_id=cancelled["analysis_id"])["status"] == MediaAnalysisStatus.CANCELLED.value


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


def test_cancelled_analysis_rejects_late_derived_records_and_semantic_query(tmp_path: Path) -> None:
    """Cancellation is terminal: a late worker cannot repopulate searchable data."""
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset_001", idempotency_key="sha:profile", cache_key="cache-v1")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    assert store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"])

    store.record_media_scene_windows(project_id=project_id, analysis_id=job["analysis_id"], source_sha256="sha", profile_hash="cache-v1", windows=[{"start_sec": 0, "end_sec": 1}])
    store.record_media_embedding(project_id=project_id, analysis_id=job["analysis_id"], source_sha256="sha", profile_hash="cache-v1", embedding=[1.0, 0.0])

    assert store.list_media_scene_windows(project_id=project_id, analysis_id=job["analysis_id"]) == []
    assert store.list_media_embeddings(project_id=project_id, analysis_id=job["analysis_id"]) == []
    assert store.find_local_media_embedding_matches(project_id=project_id, query_embedding=[1.0, 0.0]) == []


def test_analysis_state_transitions_bump_asset_index_revision(tmp_path: Path) -> None:
    """Every ranking-visible analysis lifecycle transition invalidates proposals."""
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset_001", idempotency_key="sha:profile", cache_key="cache-v1")
    initial = store.get_asset_index_revision(project_id)
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    assert store.complete_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], result={})
    assert store.get_asset_index_revision(project_id) > initial


def test_every_ranking_visible_analysis_transition_is_revisioned_and_rejected_late_write_is_not(tmp_path: Path) -> None:
    """Proposal freshness advances for every visible lifecycle transition, atomically."""
    store, project_id = _store(tmp_path)
    source = tmp_path / "indexed.mp4"
    source.write_bytes(b"indexed")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    digest = sha256(source.read_bytes()).hexdigest()

    def claimed(label: str) -> tuple[dict, dict]:
        job = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:{label}", cache_key=label)
        claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
        assert claim is not None
        return job, claim

    revision = store.get_asset_index_revision(project_id)
    needs_review, claim = claimed("review")
    assert store.complete_media_analysis(project_id=project_id, analysis_id=needs_review["analysis_id"], expected_attempt=claim["attempt"], status=MediaAnalysisStatus.NEEDS_REVIEW, result={"tags": {"layers": {"subjects": []}}})
    assert store.get_asset_index_revision(project_id) > revision
    revision = store.get_asset_index_revision(project_id)
    assert store.review_media_analysis(project_id=project_id, analysis_id=needs_review["analysis_id"], tags={"subjects": ["office"]})
    assert store.get_asset_index_revision(project_id) > revision

    for label, transition in (("failed", "failed"), ("blocked", "blocked"), ("cancelled", "cancelled")):
        job, claim = claimed(label)
        revision = store.get_asset_index_revision(project_id)
        if transition == "failed":
            changed = store.fail_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], error_code="FAIL", error_message="failed")
        elif transition == "blocked":
            changed = store.mark_media_analysis_blocked(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], error_code="BLOCKED", error_message="blocked")
        else:
            changed = store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"])
        assert changed is not None
        assert store.get_asset_index_revision(project_id) > revision
        revision = store.get_asset_index_revision(project_id)
        assert store.complete_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], result={}) is None
        assert store.get_asset_index_revision(project_id) == revision


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


def test_analysis_idempotency_is_scoped_to_asset_ownership(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    first = store.create_media_analysis(project_id=project_id, asset_id="asset-a", idempotency_key="same-sha", cache_key="cache")
    second = store.create_media_analysis(project_id=project_id, asset_id="asset-b", idempotency_key="same-sha", cache_key="cache")
    assert first["analysis_id"] != second["analysis_id"]
    assert second["asset_id"] == "asset-b"


def test_cancel_removes_query_visible_derived_analysis_records(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    job = store.create_media_analysis(project_id=project_id, asset_id="asset", idempotency_key="owned", cache_key="cache")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    store.record_media_scene_windows(project_id=project_id, analysis_id=job["analysis_id"], source_sha256="sha", profile_hash="profile", windows=[{"start_sec": 0, "end_sec": 1}])
    store.record_media_embedding(project_id=project_id, analysis_id=job["analysis_id"], source_sha256="sha", profile_hash="profile", embedding=[1.0, 0.0])
    assert store.request_media_analysis_cancel(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"])
    assert store.list_media_scene_windows(project_id=project_id, analysis_id=job["analysis_id"]) == []
    assert store.list_media_embeddings(project_id=project_id, analysis_id=job["analysis_id"]) == []
