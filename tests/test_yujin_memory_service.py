"""유진의 승인된 기억을 로컬에서만 저장·삭제한다 (2026-09-18, Mem0 제거).

옛 파일은 mem0 게이트웨이의 네트워크 실패 모양(event_pending/ambiguous/
reconcile)을 재는 시험으로 가득했다. 로컬 DB 쓰기는 성공 아니면 예외뿐이라
그 상태들은 이제 "게이트웨이가 뭐라고 답했는가"가 아니라 "로컬 쓰기 자체가
실패했는가"에서만 나온다 -- 그 경계를 다시 잰다. 승인 큐의 claim/finalize
동시성 계약은 그대로라 그 부분 시험은 옛 것과 같은 시나리오를 쓴다.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from videobox_api.yujin_memory_service import (
    MemoryStoreUnavailable,
    YujinMemoryService,
)
from videobox_storage.local_project_store import LocalProjectStore


def _approved_candidate(
    store: LocalProjectStore,
    *,
    project_id: str | None = None,
    category: str = "pacing",
    proposed_text: str = "빠른 컷을 선호합니다.",
    conversation_id: str = "conversation-memory",
    client_request_id: str = "request-memory",
) -> tuple[str, str]:
    if project_id is None:
        project_id = store.bootstrap_project("memory").project_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        client_message_id="memory-service-source-" + conversation_id,
        user_text="영상 템포를 조금 빠르게 해줘.",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="빠른 컷 편집 취향을 확인했습니다.",
        public_text="",
        retryable=False,
    )
    message = store.list_director_messages(
        project_id=project_id,
        conversation_id=conversation["conversation_id"],
    )[0]
    candidate = store.create_yujin_memory_candidate(
        project_id=project_id,
        conversation_id=conversation["conversation_id"],
        client_request_id=client_request_id,
        source_message_ids=(message["message_id"],),
        memory_scope="creator",
        category=category,
        proposed_text=proposed_text,
    )
    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )
    return project_id, candidate["candidate_id"]


def test_store_candidate_is_idempotent_and_carries_no_gateway(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)

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
    mapping = store.get_yujin_memory_private_mapping(
        project_id=project_id, candidate_id=candidate_id
    )
    assert mapping["memory_ref"].startswith("local-")


def test_duplicate_exact_text_reuses_the_same_memory_ref(
    tmp_path: Path,
) -> None:
    """mem0 시절 같은 문장이 9번 중복 저장되던 결함을 로컬로 고정 방지한다."""
    store = LocalProjectStore(tmp_path)
    project_id, first_candidate = _approved_candidate(
        store,
        conversation_id="conversation-a",
        client_request_id="request-a",
    )
    _, second_candidate = _approved_candidate(
        store,
        project_id=project_id,
        conversation_id="conversation-b",
        client_request_id="request-b",
    )
    service = YujinMemoryService(store=store)

    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=first_candidate,
            client_request_id="store-a",
        )
    )
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=second_candidate,
            client_request_id="store-b",
        )
    )

    first_mapping = store.get_yujin_memory_private_mapping(
        project_id=project_id, candidate_id=first_candidate
    )
    second_mapping = store.get_yujin_memory_private_mapping(
        project_id=project_id, candidate_id=second_candidate
    )
    assert first_mapping["memory_ref"] == second_mapping["memory_ref"]


def test_pending_candidate_cannot_store(tmp_path: Path) -> None:
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
    service = YujinMemoryService(store=store)

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


def test_stale_started_claim_recovers_on_retry(tmp_path: Path) -> None:
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
    service = YujinMemoryService(store=store)

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-recovery",
        )
    )

    assert settled["storage_status"] == "stored"


def test_local_write_failure_marks_ambiguous_and_retry_recovers(
    tmp_path: Path, monkeypatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)
    original = store.record_yujin_memory_provider_outcome
    failures = 0

    def fail_once(**kwargs):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("local write unavailable")
        return original(**kwargs)

    monkeypatch.setattr(store, "record_yujin_memory_provider_outcome", fail_once)
    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-request-1",
            )
        )
    except MemoryStoreUnavailable as error:
        assert str(error) == "memory_store_unavailable"
    else:
        raise AssertionError("first local write should fail")

    state = store.get_yujin_memory_store_state(
        project_id=project_id, candidate_id=candidate_id
    )
    assert state["storage_status"] == "ambiguous"
    assert state["retryable"] is True

    settled = asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
        )
    )
    assert settled["storage_status"] == "stored"


def test_second_caller_hits_in_progress_while_first_claim_is_open(
    tmp_path: Path,
) -> None:
    """저장소 계층의 claim 충돌 보장이 서비스 계층을 그대로 통과한다.

    로컬 쓰기는 네트워크 I/O가 없어 `asyncio.gather`로는 더 이상 진짜
    경합을 재현하지 못한다(옛 시험은 가짜 게이트웨이의 `asyncio.sleep`이
    만드는 양보 지점에 의존했다). 그래서 두 번째 요청이 claim을 이미
    쥔 상태에서 도착하는 상황을 직접 만든다.
    """
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate_id,
        client_request_id="store-concurrent-1",
        claim_token="claim-" + "b" * 64,
    )
    service = YujinMemoryService(store=store)

    try:
        asyncio.run(
            service.store_candidate(
                project_id=project_id,
                candidate_id=candidate_id,
                client_request_id="store-concurrent-2",
            )
        )
    except ValueError as error:
        assert str(error) == "memory_candidate_store_in_progress"
    else:
        raise AssertionError("open claim must block a second caller")


def test_operation_audit_records_local_write_and_stays_body_free(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)

    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    audit = store.list_yujin_memory_operation_audit(
        project_id=project_id, candidate_id=candidate_id
    )

    assert [item["event_order"] for item in audit] == list(
        range(1, len(audit) + 1)
    )
    assert [
        (item["action"], item["storage_status"]) for item in audit
    ] == [
        ("claim", "claimed"),
        ("call_started", "claimed"),
        ("outcome", "claimed"),
        ("finalize", "stored"),
    ]
    assert all(
        "빠른 컷" not in str(item) for item in audit
    )


def test_deleted_candidate_cannot_be_stored_again(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )
    asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id, candidate_id=candidate_id
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


def test_delete_candidate_memory_is_idempotent(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)
    asyncio.run(
        service.store_candidate(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-1",
        )
    )

    first = asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id, candidate_id=candidate_id
        )
    )
    second = asyncio.run(
        service.delete_candidate_memory(
            project_id=project_id, candidate_id=candidate_id
        )
    )

    assert first["storage_status"] == "deleted"
    assert second["storage_status"] == "deleted"


def test_delete_before_store_fails_not_stored(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, candidate_id = _approved_candidate(store)
    service = YujinMemoryService(store=store)

    try:
        asyncio.run(
            service.delete_candidate_memory(
                project_id=project_id, candidate_id=candidate_id
            )
        )
    except ValueError as error:
        assert str(error) == "memory_candidate_not_stored"
    else:
        raise AssertionError("delete before store must fail")
