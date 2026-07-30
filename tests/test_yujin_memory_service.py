from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from videobox_agent_gateway.memory_gateway import MemoryWriteOutcome
from videobox_api.yujin_memory_service import (
    MemoryStoreUnavailable,
    YujinMemoryService,
)
from videobox_storage.local_project_store import LocalProjectStore


def _approved_candidate(store: LocalProjectStore) -> tuple[str, str]:
    project = store.bootstrap_project("memory")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id="conversation-memory",
    )
    message = store.append_director_message(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="user",
        text="영상 템포를 조금 빠르게 해줘.",
    )
    candidate = store.create_yujin_memory_candidate(
        project_id=project.project_id,
        conversation_id=conversation["conversation_id"],
        client_request_id="request-memory",
        source_message_ids=(message["message_id"],),
        memory_scope="creator",
        category="pacing",
        proposed_text="빠른 컷을 선호합니다.",
    )
    store.transition_yujin_memory_candidate(
        project_id=project.project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )
    return project.project_id, candidate["candidate_id"]


class _Gateway:
    def __init__(self, outcomes: list[MemoryWriteOutcome]) -> None:
        self.outcomes = outcomes
        self.add_calls = []
        self.reconcile_calls = []
        self.delete_calls = []

    async def add_approved_memory(self, request):
        self.add_calls.append(request)
        return self.outcomes.pop(0)

    async def reconcile_memory(self, request):
        self.reconcile_calls.append(request)
        return self.outcomes.pop(0)

    async def delete_memory(self, request):
        self.delete_calls.append(request)
        return {"deleted": True}


def test_explicit_store_calls_add_once_and_replay_is_local(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    first = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    repeated = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )

    assert first == repeated
    assert first == {
        "candidate_id": candidate_id,
        "status": "approved",
        "storage_status": "stored",
        "retryable": False,
    }
    assert "memory_ref" not in first
    assert len(gateway.add_calls) == 1
    assert gateway.reconcile_calls == []
    request = gateway.add_calls[0]
    assert request.text == "빠른 컷을 선호합니다."
    assert request.external_ref.startswith("ext-")
    assert request.operation_id.startswith("op-")
    assert not hasattr(request, "project_id")


def test_event_replay_reconciles_without_second_add(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [
            MemoryWriteOutcome(
                status="event_pending",
                event_ref="event-private",
            ),
            MemoryWriteOutcome(
                status="stored",
                memory_ref="memory-private",
            ),
        ]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    pending = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )

    assert pending["storage_status"] == "event_pending"
    assert pending["status"] == "approved"
    assert settled["storage_status"] == "stored"
    assert settled["status"] == "approved"
    assert len(gateway.add_calls) == 1
    assert len(gateway.reconcile_calls) == 1
    assert not hasattr(gateway.reconcile_calls[0], "project_id")


def test_pending_candidate_cannot_store_and_gateway_call_is_zero(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    connection = store._connection(project_id)
    try:
        connection.execute(
            "UPDATE yujin_memory_candidates SET status = 'pending' "
            "WHERE project_id = ? AND candidate_id = ?",
            (project_id, candidate_id),
        )
        connection.commit()
    finally:
        connection.close()
    gateway = _Gateway([])
    service = YujinMemoryService(store=store, gateway=gateway)

    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-request-1",
            )
        )
    except ValueError as error:
        assert str(error) == "memory_candidate_not_approved"
    else:
        raise AssertionError("pending candidate store must fail")

    assert gateway.add_calls == []
    assert gateway.reconcile_calls == []


def test_stale_started_claim_reconciles_without_blind_add(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 7, 30, 8, tzinfo=UTC)]
    store = LocalProjectStore(tmp_path, now=lambda: now[0])
    project_id, candidate_id = _approved_candidate(store)
    store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate_id,
        client_request_id="store-crashed",
        claim_token="claim-" + "a" * 64,
    )
    store.mark_yujin_memory_store_call_started(
        project_id=project_id,
        candidate_id=candidate_id,
        claim_token="claim-" + "a" * 64,
    )
    now[0] += timedelta(seconds=61)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-recovery",
        )
    )

    assert settled["storage_status"] == "stored"
    assert gateway.add_calls == []
    assert len(gateway.reconcile_calls) == 1
    assert gateway.reconcile_calls[0].event_ref is None


def test_provider_success_then_local_finalize_failure_replays_without_add(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    original = store.finalize_yujin_memory_store
    failures = 0

    def fail_once(**kwargs):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("local settle unavailable")
        return original(**kwargs)

    monkeypatch.setattr(store, "finalize_yujin_memory_store", fail_once)
    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-request-1",
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("first local finalize should fail")

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )
    assert settled["storage_status"] == "stored"
    assert len(gateway.add_calls) == 1
    assert gateway.reconcile_calls == []


def test_proven_failed_write_allows_one_explicit_new_add(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [
            MemoryWriteOutcome(status="failed_retryable"),
            MemoryWriteOutcome(
                status="stored", memory_ref="memory-private"
            ),
        ]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    failed = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )

    assert failed["storage_status"] == "failed_retryable"
    assert failed["retryable"] is True
    assert settled["storage_status"] == "stored"
    assert len(gateway.add_calls) == 2
    assert gateway.reconcile_calls == []


def test_ambiguous_write_reconciles_and_never_blind_adds(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [
            MemoryWriteOutcome(status="ambiguous"),
            MemoryWriteOutcome(status="ambiguous"),
        ]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    first = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    second = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )

    assert first["storage_status"] == "ambiguous"
    assert second["storage_status"] == "ambiguous"
    assert len(gateway.add_calls) == 1
    assert len(gateway.reconcile_calls) == 1


def test_two_concurrent_store_requests_keep_add_count_one(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)

    class SlowGateway(_Gateway):
        async def add_approved_memory(self, request):
            self.add_calls.append(request)
            await asyncio.sleep(0.05)
            return self.outcomes.pop(0)

    gateway = SlowGateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    async def run_both():
        return await asyncio.gather(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-concurrent-1",
            ),
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-concurrent-2",
            ),
            return_exceptions=True,
        )

    results = asyncio.run(run_both())

    assert len(gateway.add_calls) == 1
    assert any(
        isinstance(result, dict)
        and result["storage_status"] == "stored"
        for result in results
    )
    assert any(
        isinstance(result, ValueError)
        and str(result) == "memory_candidate_store_in_progress"
        for result in results
    )


def test_provider_success_then_private_record_failure_reconciles_without_add(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [
            MemoryWriteOutcome(
                status="stored", memory_ref="memory-private"
            ),
            MemoryWriteOutcome(
                status="stored", memory_ref="memory-private"
            ),
        ]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    original = store.record_yujin_memory_provider_outcome
    failures = 0

    def fail_once(**kwargs):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("private record unavailable")
        return original(**kwargs)

    monkeypatch.setattr(
        store, "record_yujin_memory_provider_outcome", fail_once
    )
    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-request-1",
            )
        )
    except Exception:
        pass
    else:
        raise AssertionError("first local record should fail")

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )

    assert settled["storage_status"] == "stored"
    assert len(gateway.add_calls) == 1
    assert len(gateway.reconcile_calls) == 1


def test_operation_audit_is_monotonic_and_body_free(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [
            MemoryWriteOutcome(
                status="event_pending", event_ref="event-private"
            ),
            MemoryWriteOutcome(
                status="stored", memory_ref="memory-private"
            ),
        ]
    )
    service = YujinMemoryService(store=store, gateway=gateway)

    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )
    audit = store.list_yujin_memory_operation_audit(
        project_id=project_id,
        candidate_id=candidate_id,
    )

    assert [item["event_order"] for item in audit] == list(
        range(1, len(audit) + 1)
    )
    assert [
        (item["action"], item["storage_status"]) for item in audit
    ] == [
        ("claim", "claimed"),
        ("call_started", "claimed"),
        ("outcome", "event_pending"),
        ("claim", "claimed"),
        ("call_started", "claimed"),
        ("outcome", "claimed"),
        ("finalize", "stored"),
    ]
    assert all(
        set(item)
        == {
            "operation_audit_id",
            "candidate_id",
            "project_id",
            "event_order",
            "action",
            "storage_status",
            "occurred_at",
        }
        for item in audit
    )
    assert all(
        "빠른 컷" not in str(item)
        and "event-private" not in str(item)
        and "memory-private" not in str(item)
        for item in audit
    )


def test_same_store_request_replays_local_state_without_gateway_call(
    tmp_path: Path,
) -> None:
    for outcome in (
        MemoryWriteOutcome(
            status="event_pending", event_ref="event-private"
        ),
        MemoryWriteOutcome(status="ambiguous"),
        MemoryWriteOutcome(status="failed_retryable"),
    ):
        store = LocalProjectStore(tmp_path / outcome.status)
        project_id, candidate_id = _approved_candidate(store)
        gateway = _Gateway([outcome])
        service = YujinMemoryService(store=store, gateway=gateway)
        first = asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="same-store-request",
            )
        )
        repeated = asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="same-store-request",
            )
        )

        assert repeated == first
        assert len(gateway.add_calls) == 1
        assert gateway.reconcile_calls == []


def test_stored_same_request_finalizes_locally_after_crash(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    original = store.finalize_yujin_memory_store
    monkeypatch.setattr(
        store,
        "finalize_yujin_memory_store",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("crash before finalize")
        ),
    )
    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="same-store-request",
            )
        )
    except RuntimeError:
        pass
    monkeypatch.setattr(store, "finalize_yujin_memory_store", original)

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="same-store-request",
        )
    )

    assert settled["storage_status"] == "stored"
    assert len(gateway.add_calls) == 1


def test_stored_replay_works_without_gateway_and_pending_fails_consent_first(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    asyncio.run(
        YujinMemoryService(store=store, gateway=gateway).store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    without_gateway = YujinMemoryService(store=store, gateway=None)
    replay = asyncio.run(
        without_gateway.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    assert replay["storage_status"] == "stored"

    pending_store = LocalProjectStore(tmp_path / "pending")
    pending_project, pending_candidate = _approved_candidate(pending_store)
    connection = pending_store._connection(pending_project)
    try:
        connection.execute(
            "UPDATE yujin_memory_candidates SET status = 'pending' "
            "WHERE project_id = ? AND candidate_id = ?",
            (pending_project, pending_candidate),
        )
        connection.commit()
    finally:
        connection.close()
    try:
        asyncio.run(
            YujinMemoryService(
                store=pending_store, gateway=None
            ).store_candidate(
                project_id=pending_project,
                candidate_id=pending_candidate,
                client_request_id="store-request-1",
            )
        )
    except ValueError as error:
        assert str(error) == "memory_candidate_not_approved"
    else:
        raise AssertionError("pending consent must fail before gateway")


def test_server_owned_delete_resolves_private_mapping_and_preserves_on_failure(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    deleted = asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id,
            candidate_id=candidate_id,
        )
    )

    assert deleted["storage_status"] == "deleted"
    assert len(gateway.delete_calls) == 1
    assert gateway.delete_calls[0].memory_ref == "memory-private"
    assert gateway.delete_calls[0].allow_absent is False
    assert not hasattr(gateway.delete_calls[0], "project_id")

    failed_store = LocalProjectStore(tmp_path / "failed-delete")
    failed_project_id, failed_candidate_id = _approved_candidate(failed_store)
    failed_gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="keep-private")]
    )
    failed_service = YujinMemoryService(
        store=failed_store, gateway=failed_gateway
    )
    asyncio.run(
        failed_service.store_candidate(
            project_id=failed_project_id,
            candidate_id=failed_candidate_id,
            client_request_id="store-request-1",
        )
    )

    async def fail_delete(_request):
        raise RuntimeError("private provider failure")

    failed_gateway.delete_memory = fail_delete
    try:
        asyncio.run(
            failed_service.delete_candidate_memory(
                project_id=failed_project_id,
                candidate_id=failed_candidate_id,
            )
        )
    except MemoryStoreUnavailable as error:
        assert str(error) == "memory_delete_unavailable"
    else:
        raise AssertionError("failed provider delete must fail closed")

    mapping = failed_store.get_yujin_memory_private_mapping(
        project_id=failed_project_id,
        candidate_id=failed_candidate_id,
    )
    assert mapping["memory_ref"] == "keep-private"
    assert failed_store.get_yujin_memory_store_state(
        project_id=failed_project_id,
        candidate_id=failed_candidate_id,
    )["storage_status"] == "stored"


def test_delete_retries_after_provider_success_and_local_finalize_crash(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)

    class Gateway(_Gateway):
        async def delete_memory(self, request):
            self.delete_calls.append(request)
            return {"deleted": True}

    gateway = Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    original = store.mark_yujin_memory_deleted
    monkeypatch.setattr(
        store,
        "mark_yujin_memory_deleted",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("crash after provider delete")
        ),
    )
    try:
        asyncio.run(
            service.delete_candidate_memory(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        )
    except MemoryStoreUnavailable as error:
        assert str(error) == "memory_delete_unavailable"
    else:
        raise AssertionError("local finalize crash must be normalized")
    monkeypatch.setattr(store, "mark_yujin_memory_deleted", original)

    retried = asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id,
            candidate_id=candidate_id,
        )
    )
    repeated = asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id,
            candidate_id=candidate_id,
        )
    )

    assert retried == repeated
    assert retried["storage_status"] == "deleted"
    assert len(gateway.delete_calls) == 2
    assert [call.allow_absent for call in gateway.delete_calls] == [
        False,
        True,
    ]


def test_delete_without_gateway_adds_no_durable_call_marker(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    asyncio.run(
        YujinMemoryService(store=store, gateway=gateway).store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    before = store.list_yujin_memory_operation_audit(
        project_id=project_id,
        candidate_id=candidate_id,
    )

    try:
        asyncio.run(
            YujinMemoryService(
                store=store, gateway=None
            ).delete_candidate_memory(
                project_id=project_id,
                candidate_id=candidate_id,
            )
        )
    except MemoryStoreUnavailable as error:
        assert str(error) == "memory_delete_unavailable"
    else:
        raise AssertionError("missing gateway must fail closed")

    assert store.list_yujin_memory_operation_audit(
        project_id=project_id,
        candidate_id=candidate_id,
    ) == before


def test_deleted_candidate_cannot_be_stored_again(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    gateway = _Gateway(
        [MemoryWriteOutcome(status="stored", memory_ref="memory-private")]
    )
    service = YujinMemoryService(store=store, gateway=gateway)
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id,
            candidate_id=candidate_id,
        )
    )

    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-request-2",
            )
        )
    except ValueError as error:
        assert str(error) == "memory_candidate_deleted"
    else:
        raise AssertionError("deleted candidate must be terminal")
    assert len(gateway.add_calls) == 1
