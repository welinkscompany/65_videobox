from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import inspect
import sqlite3
from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.postgres_schema import POSTGRES_SCHEMA_STATEMENTS


def _seed(store: LocalProjectStore, *, name: str = "memory"):
    project = store.bootstrap_project(name)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=f"conversation-{project.project_id}",
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        client_message_id=f"memory-seed-{project.project_id}",
        user_text="영상 템포를 조금 빠르게 해줘.",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert run["dispatch"] is True
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="빠른 컷과 짧은 호흡을 제안합니다.",
        public_text="",
        retryable=False,
    )
    first, second = store.list_director_messages(
        project_id=project.project_id,
        conversation_id=conversation["conversation_id"],
    )
    return project.project_id, session, conversation["conversation_id"], first, second


def _create(store: LocalProjectStore, project_id: str, conversation_id: str, *message_ids: str):
    return store.create_yujin_memory_candidate(
        project_id=project_id,
        conversation_id=conversation_id,
        client_request_id="request-1",
        source_message_ids=message_ids,
        memory_scope="creator",
        category="pacing",
        proposed_text="빠른 컷과 짧은 호흡을 선호합니다.",
    )


def _append_run_messages(
    store: LocalProjectStore,
    *,
    project_id: str,
    session_id: str,
    conversation_id: str,
    status: str,
    suffix: str,
) -> tuple[list[dict], dict]:
    before = {
        message["message_id"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    }
    run = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session_id,
        conversation_id=conversation_id,
        client_message_id=f"authority-{status}-{suffix}",
        user_text=f"{status} source",
        expected_session_revision=1,
        expected_asset_index_revision=0,
    )
    if status == "streaming":
        assert store.append_director_hermes_draft(
            project_id=project_id,
            run_id=run["run_id"],
            owner_token=run["owner_token"],
            assistant_draft_text="진행 중",
        )
    elif status in {"completed", "blocked", "interrupted"}:
        assert store.complete_director_hermes_run(
            project_id=project_id,
            run_id=run["run_id"],
            owner_token=run["owner_token"],
            status=status,
            assistant_text=f"{status} assistant",
            public_text="",
            retryable=status != "completed",
        )
    return [
        message
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
        if message["message_id"] not in before
    ], run


def test_candidate_sources_must_belong_to_completed_hermes_run_before_audit(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, session, conversation_id, completed_user, completed_assistant = _seed(
        store
    )
    completed_candidates = []
    for suffix, source in (
        ("user", completed_user),
        ("assistant", completed_assistant),
    ):
        completed_candidates.append(
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"completed-subset-{suffix}",
                source_message_ids=(source["message_id"],),
                memory_scope="creator",
                category="pacing",
                proposed_text="빠른 컷 편집을 선호합니다.",
            )
        )
    assert [candidate["source_message_ids"] for candidate in completed_candidates] == [
        (completed_user["message_id"],),
        (completed_assistant["message_id"],),
    ]

    for status in ("pending", "streaming", "blocked", "interrupted"):
        invalid_messages, run = _append_run_messages(
            store,
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            status=status,
            suffix="invalid",
        )
        for source in invalid_messages:
            with pytest.raises(
                KeyError,
                match="yujin_memory_source_missing",
            ):
                store.create_yujin_memory_candidate(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    client_request_id=(
                        f"invalid-{status}-{source['message_id']}"
                    ),
                    source_message_ids=(source["message_id"],),
                    memory_scope="creator",
                    category="pacing",
                    proposed_text="빠른 컷 편집을 선호합니다.",
                )
        if status in {"pending", "streaming"}:
            assert store.complete_director_hermes_run(
                project_id=project_id,
                run_id=run["run_id"],
                owner_token=run["owner_token"],
                status="interrupted",
                assistant_text=(
                    "진행 중 테스트 run 정리"
                    if status == "streaming"
                    else "테스트 run 정리"
                ),
                public_text="진행 중" if status == "streaming" else "",
                retryable=True,
            )
    legacy_user = store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        role="user",
        text="연결되지 않은 사용자 메시지",
    )
    legacy_assistant = store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        role="assistant",
        text="연결되지 않은 응답 메시지",
    )

    for source in (legacy_user, legacy_assistant):
        with pytest.raises(KeyError, match="yujin_memory_source_missing"):
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"invalid-{source['message_id']}",
                source_message_ids=(source["message_id"],),
                memory_scope="creator",
                category="pacing",
                proposed_text="빠른 컷 편집을 선호합니다.",
            )

    listed_candidates = store.list_yujin_memory_candidates(
        project_id=project_id
    )
    assert {
        candidate["candidate_id"]
        for candidate in listed_candidates
    } == {
        candidate["candidate_id"]
        for candidate in completed_candidates
    }
    assert len(listed_candidates) == 2


def test_candidate_and_redacted_audit_are_durable(tmp_path: Path) -> None:
    clock = lambda: datetime(2026, 7, 30, 5, tzinfo=UTC)
    store = LocalProjectStore(tmp_path, now=clock)
    project_id, _, conversation_id, first, second = _seed(store)

    created = _create(
        store,
        project_id,
        conversation_id,
        first["message_id"],
        second["message_id"],
    )
    reopened = LocalProjectStore(tmp_path, now=clock)

    assert created["candidate_id"].startswith("memory-candidate-")
    assert created["memory_scope"] == "creator"
    assert created["status"] == "pending"
    assert reopened.list_yujin_memory_candidates(project_id=project_id) == [created]
    audit = reopened.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=created["candidate_id"],
    )
    assert audit == [
        {
            "audit_event_id": audit[0]["audit_event_id"],
            "candidate_id": created["candidate_id"],
            "project_id": project_id,
            "event_order": 1,
            "action": "create",
            "status": "pending",
            "occurred_at": created["created_at"],
        }
    ]
    assert "proposed_text" not in audit[0]
    assert "source_message_ids" not in audit[0]
    assert "provider" not in audit[0]


def test_source_ids_are_canonicalized_by_conversation_order(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, second = _seed(store)

    reversed_candidate = _create(
        store,
        project_id,
        conversation_id,
        second["message_id"],
        first["message_id"],
    )
    repeated = _create(
        store,
        project_id,
        conversation_id,
        first["message_id"],
        second["message_id"],
    )

    assert reversed_candidate["source_message_ids"] == (
        first["message_id"],
        second["message_id"],
    )
    assert repeated == reversed_candidate


def test_candidate_scope_requires_current_project_conversation_and_every_message(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_a, _, conversation_a, first_a, _ = _seed(store, name="a")
    project_b, _, conversation_b, first_b, _ = _seed(store, name="b")

    invalid_requests = (
        (project_a, "missing", (first_a["message_id"],)),
        (project_a, conversation_a, ("missing",)),
        (project_a, conversation_a, (first_a["message_id"], first_b["message_id"])),
        (project_b, conversation_a, (first_a["message_id"],)),
        (project_b, conversation_b, (first_a["message_id"],)),
    )
    for project_id, conversation_id, source_ids in invalid_requests:
        with pytest.raises(KeyError, match="yujin_memory_source_missing"):
            _create(store, project_id, conversation_id, *source_ids)

    assert store.list_yujin_memory_candidates(project_id=project_a) == []
    assert store.list_yujin_memory_candidates(project_id=project_b) == []


@pytest.mark.parametrize(
    "proposed_text",
    [
        "API_KEY=private",
        "비밀번호는 private 입니다",
        "인증 토큰은 private 입니다",
        "계좌 번호는 123-45-67890 입니다",
        "연락처는 +44 20 7946 0958 입니다",
        "Call +44 20 7946 0958",
        "phone 212-555-1212",
        "전화 212-555-1212",
        "소스는 /workspace/private/video.mp4",
        "소스는 /clip.mp4",
        "소스는 ~/clip.mp4",
        "소스는 ./clip.mp4",
        "소스는 ../private/video.mp4",
        r"소스는 C:relative\file.txt",
        "소스는 s3://bucket/private.mp4",
        "미디어는 https://example.invalid/private/video.mp4",
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "-----BEGIN PRIVATE KEY----- ABCDEF",
        "https://media.example/video.mp4?X-Amz-Signature=deadbeef",
        "\ufdfa" * 280,
        "safe\u0000text",
        "영상 템포를 조금 빠르게 해줘.",
    ],
)
def test_store_is_final_policy_guard_and_rolls_back_invalid_text(
    tmp_path: Path,
    proposed_text: str,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)

    with pytest.raises(ValueError):
        store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id="request-guard",
            source_message_ids=(first["message_id"],),
            memory_scope="creator",
            category="pacing",
            proposed_text=proposed_text,
        )

    assert store.list_yujin_memory_candidates(project_id=project_id) == []
    connection = store._connection(project_id)
    try:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM yujin_memory_candidate_audit"
        ).fetchone()["count"] == 0
    finally:
        connection.close()


def test_store_canonicalizes_text_before_fingerprint_and_persistence(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    kwargs = {
        "project_id": project_id,
        "conversation_id": conversation_id,
        "client_request_id": "request-canonical",
        "source_message_ids": (first["message_id"],),
        "memory_scope": "creator",
        "category": "caption",
    }

    created = store.create_yujin_memory_candidate(
        **kwargs,
        proposed_text="  Ａ형\t자막을  선호합니다.  ",
    )
    repeated = store.create_yujin_memory_candidate(
        **kwargs,
        proposed_text="A형 자막을 선호합니다.",
    )

    assert created["proposed_text"] == "A형 자막을 선호합니다."
    assert repeated == created


def test_same_transition_is_idempotent_and_opposite_transition_conflicts(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(store, project_id, conversation_id, first["message_id"])

    approved = store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )
    repeated = store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )

    assert approved == repeated
    with pytest.raises(ValueError, match="memory_candidate_terminal_conflict"):
        store.transition_yujin_memory_candidate(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            action="reject",
        )
    audit = store.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
    )
    assert [(item["action"], item["status"]) for item in audit] == [
        ("create", "pending"),
        ("approve", "approved"),
    ]
    assert [item["event_order"] for item in audit] == [1, 2]


def test_audit_order_is_monotonic_when_lifecycle_timestamps_match(
    tmp_path: Path,
) -> None:
    fixed_clock = lambda: datetime(2026, 7, 30, 5, tzinfo=UTC)
    store = LocalProjectStore(tmp_path, now=fixed_clock)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(
        store,
        project_id,
        conversation_id,
        first["message_id"],
    )

    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )

    audit = store.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
    )
    assert [item["occurred_at"] for item in audit] == [
        candidate["created_at"],
        candidate["created_at"],
    ]
    assert [
        (item["event_order"], item["action"], item["status"])
        for item in audit
    ] == [
        (1, "create", "pending"),
        (2, "approve", "approved"),
    ]


def test_expired_memory_claims_are_listed_retryable_and_reclaim_on_click(
    tmp_path: Path,
) -> None:
    current = datetime(2026, 7, 30, 5, tzinfo=UTC)
    store = LocalProjectStore(tmp_path, now=lambda: current)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(
        store,
        project_id,
        conversation_id,
        first["message_id"],
    )
    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )
    store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        client_request_id="store-request-1",
        claim_token="claim-" + "a" * 64,
    )
    started = store.create_yujin_memory_candidate(
        project_id=project_id,
        conversation_id=conversation_id,
        client_request_id="request-2",
        source_message_ids=(first["message_id"],),
        memory_scope="creator",
        category="workflow",
        proposed_text="명시적으로 확인한 뒤 저장합니다.",
    )
    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=started["candidate_id"],
        action="approve",
    )
    store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=started["candidate_id"],
        client_request_id="store-started-1",
        claim_token="claim-" + "c" * 64,
    )
    store.mark_yujin_memory_store_call_started(
        project_id=project_id,
        candidate_id=started["candidate_id"],
        claim_token="claim-" + "c" * 64,
    )

    live = {
        item["candidate_id"]: item
        for item in store.list_yujin_memory_candidates(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    }
    current = datetime(2026, 7, 30, 5, 1, 1, tzinfo=UTC)
    expired = {
        item["candidate_id"]: item
        for item in store.list_yujin_memory_candidates(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    }
    reclaimed = store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        client_request_id="store-request-2",
        claim_token="claim-" + "b" * 64,
    )
    reconciled = store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=started["candidate_id"],
        client_request_id="store-started-2",
        claim_token="claim-" + "d" * 64,
    )

    assert live[candidate["candidate_id"]]["storage_status"] == "claimed"
    assert live[candidate["candidate_id"]]["retryable"] is False
    assert live[started["candidate_id"]]["retryable"] is False
    assert expired[candidate["candidate_id"]]["storage_status"] == "claimed"
    assert expired[candidate["candidate_id"]]["retryable"] is True
    assert expired[started["candidate_id"]]["retryable"] is True
    assert not {
        "write_claimed_at",
        "provider_call_started_at",
        "provider_memory_ref",
    } & set(expired[candidate["candidate_id"]])
    assert reclaimed["action"] == "add"
    assert reclaimed["candidate"]["retryable"] is False
    assert reconciled["action"] == "reconcile"
    assert reconciled["candidate"]["retryable"] is False


def test_create_is_idempotent_by_canonical_request_and_conflicts_on_reuse(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)

    created = _create(store, project_id, conversation_id, first["message_id"])
    repeated = _create(store, project_id, conversation_id, first["message_id"])

    assert repeated == created
    with pytest.raises(ValueError, match="memory_candidate_request_conflict"):
        store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id="request-1",
            source_message_ids=(first["message_id"],),
            memory_scope="creator",
            category="tone",
            proposed_text="차분한 도입을 선호합니다.",
        )
    assert len(store.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=created["candidate_id"],
    )) == 1


def test_competing_terminal_transitions_are_serialized(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(store, project_id, conversation_id, first["message_id"])

    def decide(action: str):
        try:
            return store.transition_yujin_memory_candidate(
                project_id=project_id,
                candidate_id=candidate["candidate_id"],
                action=action,
            )["status"]
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(decide, ("approve", "reject")))

    assert sorted(results).count("memory_candidate_terminal_conflict") == 1
    assert len(set(results) & {"approved", "rejected"}) == 1
    audit = store.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
    )
    assert len(audit) == 2


def test_audit_failure_rolls_back_create_and_approve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    original = store._append_yujin_memory_audit

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(store, "_append_yujin_memory_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        _create(store, project_id, conversation_id, first["message_id"])
    assert store.list_yujin_memory_candidates(project_id=project_id) == []

    monkeypatch.setattr(store, "_append_yujin_memory_audit", original)
    candidate = _create(store, project_id, conversation_id, first["message_id"])
    monkeypatch.setattr(store, "_append_yujin_memory_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        store.transition_yujin_memory_candidate(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            action="approve",
        )
    current = store.list_yujin_memory_candidates(project_id=project_id)
    assert current[0]["status"] == "pending"
    audit = store.list_yujin_memory_candidate_audit(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
    )
    assert [(row["action"], row["status"]) for row in audit] == [
        ("create", "pending")
    ]


def test_candidate_list_is_bounded_to_deterministic_latest_100(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    for index in range(101):
        store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id=f"request-{index:03d}",
            source_message_ids=(first["message_id"],),
            memory_scope="creator",
            category="pacing",
            proposed_text=f"빠른 컷 선호 {index:03d}",
        )

    candidates = store.list_yujin_memory_candidates(project_id=project_id)

    assert len(candidates) == 100
    assert candidates == sorted(
        candidates,
        key=lambda item: (item["created_at"], item["candidate_id"]),
        reverse=True,
    )


def test_postgres_schema_is_derived_and_transition_uses_row_lock() -> None:
    schema = "\n".join(POSTGRES_SCHEMA_STATEMENTS)
    lock_source = inspect.getsource(
        LocalProjectStore._lock_yujin_memory_candidate
    )
    transition_source = inspect.getsource(
        LocalProjectStore.transition_yujin_memory_candidate
    )

    assert "CREATE TABLE IF NOT EXISTS yujin_memory_candidates" in schema
    assert "CREATE TABLE IF NOT EXISTS yujin_memory_candidate_audit" in schema
    assert "UNIQUE(project_id, conversation_id, client_request_id)" in schema
    assert "UNIQUE(project_id, candidate_id, event_order)" in schema
    assert "CHECK(memory_scope = 'creator')" in schema
    assert "CHECK(category IN (" in schema
    assert "CHECK(status IN (" in schema
    for status in (
        "pending",
        "approved",
        "rejected",
    ):
        assert f"'{status}'" in schema
    assert "if isinstance(connection, sqlite3.Connection)" in lock_source
    assert "FOR UPDATE" in lock_source
    assert "_lock_yujin_memory_candidate" in transition_source
    assert "AND status = 'pending'" in transition_source
    for column in (
        "external_ref",
        "operation_id",
        "provider_event_ref",
        "provider_memory_ref",
        "store_client_request_id",
        "write_claim_token",
        "write_claimed_at",
        "provider_call_started_at",
        "attempt_count",
        "storage_status",
    ):
        assert column in schema


def test_old_sqlite_candidate_table_gets_private_operation_columns() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            """
            CREATE TABLE yujin_memory_candidates (
                candidate_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL
            )
            """
        )
        LocalProjectStore._ensure_yujin_memory_operation_columns(
            connection
        )
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(yujin_memory_candidates)"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "external_ref",
        "operation_id",
        "provider_event_ref",
        "provider_memory_ref",
        "store_client_request_id",
        "write_claim_token",
        "write_claimed_at",
        "provider_call_started_at",
        "attempt_count",
        "storage_status",
    } <= columns


def test_operation_audit_failure_rolls_back_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(
        store, project_id, conversation_id, first["message_id"]
    )
    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
        action="approve",
    )

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("operation audit unavailable")

    monkeypatch.setattr(
        store, "_append_yujin_memory_operation_audit", fail_audit
    )
    with pytest.raises(RuntimeError, match="operation audit unavailable"):
        store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            client_request_id="store-request-1",
            claim_token="claim-" + "a" * 64,
        )

    assert store.get_yujin_memory_store_state(
        project_id=project_id,
        candidate_id=candidate["candidate_id"],
    ) == {
        "candidate_id": candidate["candidate_id"],
        "status": "approved",
        "storage_status": "not_requested",
        "retryable": False,
    }


def test_deleted_storage_state_rejects_new_claim_without_audit(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project_id, _, conversation_id, first, _ = _seed(store)
    candidate = _create(
        store, project_id, conversation_id, first["message_id"]
    )
    candidate_id = candidate["candidate_id"]
    store.transition_yujin_memory_candidate(
        project_id=project_id,
        candidate_id=candidate_id,
        action="approve",
    )
    claim_token = "claim-" + "a" * 64
    store.claim_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate_id,
        client_request_id="store-request-1",
        claim_token=claim_token,
    )
    store.mark_yujin_memory_store_call_started(
        project_id=project_id,
        candidate_id=candidate_id,
        claim_token=claim_token,
    )
    store.record_yujin_memory_provider_outcome(
        project_id=project_id,
        candidate_id=candidate_id,
        claim_token=claim_token,
        status="stored",
        memory_ref="memory-private",
        event_ref=None,
    )
    store.finalize_yujin_memory_store(
        project_id=project_id,
        candidate_id=candidate_id,
    )
    first_delete_call = store.mark_yujin_memory_delete_call_started(
        project_id=project_id,
        candidate_id=candidate_id,
    )
    retried_delete_call = store.mark_yujin_memory_delete_call_started(
        project_id=project_id,
        candidate_id=candidate_id,
    )
    assert first_delete_call["allow_absent"] is False
    assert retried_delete_call["allow_absent"] is True
    assert first_delete_call["memory_ref"] == "memory-private"
    delete_call_audit = [
        row
        for row in store.list_yujin_memory_operation_audit(
            project_id=project_id,
            candidate_id=candidate_id,
        )
        if row["action"] == "call_started"
        and row["storage_status"] == "stored"
    ]
    assert len(delete_call_audit) == 1
    assert "memory_ref" not in delete_call_audit[0]
    assert "external_ref" not in delete_call_audit[0]
    store.mark_yujin_memory_deleted(
        project_id=project_id,
        candidate_id=candidate_id,
    )
    before_audit = store.list_yujin_memory_operation_audit(
        project_id=project_id,
        candidate_id=candidate_id,
    )

    with pytest.raises(ValueError, match="memory_candidate_deleted"):
        store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate_id,
            client_request_id="store-request-2",
            claim_token="claim-" + "b" * 64,
        )

    assert store.list_yujin_memory_operation_audit(
        project_id=project_id,
        candidate_id=candidate_id,
    ) == before_audit
    assert store.get_yujin_memory_store_state(
        project_id=project_id,
        candidate_id=candidate_id,
    )["storage_status"] == "deleted"


def test_local_first_exchange_is_a_valid_memory_source(tmp_path: Path) -> None:
    """The editor screen chats through the local route, which has no run object.

    Requiring a completed Hermes run meant the owner could never save a memory
    from a conversation they actually had on screen.
    """
    store = LocalProjectStore(tmp_path)
    project_id, session, conversation_id, _user, _assistant = _seed(store)

    exchange = store.append_director_exchange(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="local-turn-1",
        user_text="자막은 어떻게 두는 게 좋을까?",
        assistant_text="두 줄 이내를 권합니다.",
    )

    for source in (exchange["user_message"], exchange["assistant_message"]):
        created = store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id=f"local-source-{source['message_id']}",
            source_message_ids=(source["message_id"],),
            memory_scope="creator",
            category="caption",
            proposed_text="자막은 두 줄 이내를 선호합니다.",
        )
        assert created["source_message_ids"] == (source["message_id"],)


def test_a_blocked_local_exchange_is_not_a_memory_source(tmp_path: Path) -> None:
    """A reply that failed is not a turn the owner had; it must not seed memory."""
    store = LocalProjectStore(tmp_path)
    project_id, session, conversation_id, _user, _assistant = _seed(store)

    exchange = store.append_director_exchange(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="local-blocked-1",
        user_text="자막은 어떻게 두는 게 좋을까?",
        assistant_text="local_only_blocked: local model unavailable",
        assistant_metadata={"status": "blocked", "error_code": "LOCAL_UNAVAILABLE"},
    )

    for source in (exchange["user_message"], exchange["assistant_message"]):
        with pytest.raises(KeyError, match="yujin_memory_source_missing"):
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"blocked-source-{source['message_id']}",
                source_message_ids=(source["message_id"],),
                memory_scope="creator",
                category="caption",
                proposed_text="자막은 두 줄 이내를 선호합니다.",
            )
