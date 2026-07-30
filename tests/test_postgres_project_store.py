from __future__ import annotations

from copy import deepcopy
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from threading import Barrier, Event, get_ident
from unittest.mock import patch
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_core_engine.editing_session import select_segment_tts_replacement
from videobox_storage.postgres_project_store import PostgresProjectStore, _PostgresConnection
from videobox_storage.postgres_compat import translate_sql
from videobox_storage.local_project_store import EditingSessionRevisionConflict, LocalProjectStore


def _approve_postgres_brief(store: PostgresProjectStore, project_id: str) -> dict:
    source = store.project_root(project_id) / "brief-source.txt"
    source.write_text("동시 요청을 검증하는 짧은 대본입니다.", encoding="utf-8")
    script_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.SCRIPT_DOCUMENT,
        source_path=source,
    )
    brief = store.create_creation_brief(
        project_id=project_id,
        script_filename="script.txt",
        script_text="동시 요청을 검증하는 짧은 대본입니다.",
        idempotency_key="brief",
        capability_profile={},
        script_asset_id=script_asset.asset_id,
        runtime=type("NoQuestions", (), {"plan_questions": lambda *_args, **_kwargs: []})(),
    )
    brief = store.bypass_creation_interview(
        project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"]
    )
    brief = store.update_creation_brief_summary(
        project_id=project_id, brief_id=brief["brief_id"], summary="동시성 확인", expected_revision=brief["revision"]
    )
    return store.approve_creation_brief(
        project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"]
    )


def _run_two_requests_at_same_insert(*, statement_marker: str, request) -> list[dict]:
    """Make both real PostgreSQL transactions observe the pre-insert state."""
    barrier = Barrier(2)
    original_execute = _PostgresConnection.execute

    def gate_insert(self, statement: str, parameters=None):
        if statement_marker in statement:
            barrier.wait(timeout=10)
        return original_execute(self, statement, parameters)

    with patch.object(_PostgresConnection, "execute", gate_insert):
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: request(), range(2)))


def _cleanup_postgres_hermes_project(
    store: PostgresProjectStore,
    project_id: str,
) -> None:
    connection = store._connection(project_id)
    try:
        for table in (
            "yujin_memory_operation_audit",
            "yujin_memory_candidate_audit",
            "yujin_memory_candidates",
            "hermes_capability_audit",
            "hermes_capability_ledger",
            "director_hermes_run_events",
            "director_hermes_runs",
            "director_messages",
            "director_conversations",
            "editing_sessions",
            "director_asset_index_revisions",
            "projects",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE project_id = ?",
                (project_id,),
            )
        connection.commit()
    finally:
        connection.close()


def _append_completed_yujin_source_messages(
    store: LocalProjectStore,
    *,
    project_id: str,
    session: dict,
    conversation_id: str,
    user_text: str,
    assistant_text: str = "확인한 편집 취향입니다.",
) -> tuple[dict, dict]:
    before = {
        message["message_id"]
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
    }
    run = store.begin_director_hermes_run(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"memory-source-{uuid4().hex}",
        user_text=user_text,
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert run["dispatch"] is True
    assert store.complete_director_hermes_run(
        project_id=project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text=assistant_text,
        public_text="",
        retryable=False,
    )
    created = [
        message
        for message in store.list_director_messages(
            project_id=project_id,
            conversation_id=conversation_id,
        )
        if message["message_id"] not in before
    ]
    assert len(created) == 2
    return created[0], created[1]


def test_postgres_yujin_memory_candidate_workflow_is_atomic_and_serialized(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin memory {uuid4().hex}"
    )
    project_id = project.project_id
    try:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=f"timeline-{uuid4().hex}",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = f"conversation-{uuid4().hex}"
        store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        first, second = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=conversation_id,
            user_text="영상 호흡을 조금 빠르게 해줘.",
            assistant_text="짧은 컷 중심의 편집을 제안합니다.",
        )
        request = {
            "project_id": project_id,
            "conversation_id": conversation_id,
            "client_request_id": "postgres-request-1",
            "source_message_ids": (
                second["message_id"],
                first["message_id"],
            ),
            "memory_scope": "creator",
            "category": "pacing",
            "proposed_text": "짧은 컷 중심의 빠른 호흡을 선호합니다.",
        }

        created = store.create_yujin_memory_candidate(**request)
        replayed = store.create_yujin_memory_candidate(**request)

        assert replayed == created
        assert created["source_message_ids"] == (
            first["message_id"],
            second["message_id"],
        )

        def decide(action: str) -> str:
            try:
                return str(
                    store.transition_yujin_memory_candidate(
                        project_id=project_id,
                        candidate_id=created["candidate_id"],
                        action=action,
                    )["status"]
                )
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(decide, ("approve", "reject")))

        assert results.count("memory_candidate_terminal_conflict") == 1
        assert len(set(results) & {"approved", "rejected"}) == 1
        audit = store.list_yujin_memory_candidate_audit(
            project_id=project_id,
            candidate_id=created["candidate_id"],
        )
        assert [(row["action"], row["status"]) for row in audit] in (
            [("create", "pending"), ("approve", "approved")],
            [("create", "pending"), ("reject", "rejected")],
        )
        assert [row["event_order"] for row in audit] == [1, 2]
    finally:
        _cleanup_postgres_hermes_project(store, project_id)


def test_postgres_yujin_memory_sources_require_completed_run_authority(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory-source-authority",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin source authority {uuid4().hex}"
    )
    project_id = project.project_id
    try:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=f"timeline-{uuid4().hex}",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = f"conversation-{uuid4().hex}"
        store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        completed_user, completed_assistant = (
            _append_completed_yujin_source_messages(
                store,
                project_id=project_id,
                session=session,
                conversation_id=conversation_id,
                user_text="빠른 컷 편집을 기억해 주세요.",
            )
        )
        completed_candidates = [
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"completed-{role}",
                source_message_ids=(message["message_id"],),
                memory_scope="creator",
                category="pacing",
                proposed_text=f"완료된 {role} 근거만 기억합니다.",
            )
            for role, message in (
                ("user", completed_user),
                ("assistant", completed_assistant),
            )
        ]

        for status in ("pending", "streaming", "blocked", "interrupted"):
            before = {
                message["message_id"]
                for message in store.list_director_messages(
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
            }
            run = store.begin_director_hermes_run(
                project_id=project_id,
                session_id=session["session_id"],
                conversation_id=conversation_id,
                client_message_id=f"invalid-{status}-{uuid4().hex}",
                user_text=f"{status} source",
                expected_session_revision=session["session_revision"],
                expected_asset_index_revision=0,
            )
            if status == "streaming":
                assert store.append_director_hermes_draft(
                    project_id=project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    assistant_draft_text="진행 중",
                )
            elif status in {"blocked", "interrupted"}:
                assert store.complete_director_hermes_run(
                    project_id=project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    status=status,
                    assistant_text=f"{status} assistant",
                    public_text="",
                    retryable=True,
                )
            invalid_messages = [
                message
                for message in store.list_director_messages(
                    project_id=project_id,
                    conversation_id=conversation_id,
                )
                if message["message_id"] not in before
            ]
            for index, message in enumerate(invalid_messages):
                with pytest.raises(
                    KeyError,
                    match="yujin_memory_source_missing",
                ):
                    store.create_yujin_memory_candidate(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        client_request_id=(
                            f"invalid-{status}-source-{index}"
                        ),
                        source_message_ids=(message["message_id"],),
                        memory_scope="creator",
                        category="pacing",
                        proposed_text="검증되지 않은 근거입니다.",
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
                    public_text=(
                        "진행 중" if status == "streaming" else ""
                    ),
                    retryable=True,
                )
        legacy = store.append_director_message(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            role="user",
            text="run에 연결되지 않은 legacy source",
        )
        with pytest.raises(
            KeyError,
            match="yujin_memory_source_missing",
        ):
            store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id="invalid-legacy-source",
                source_message_ids=(legacy["message_id"],),
                memory_scope="creator",
                category="pacing",
                proposed_text="검증되지 않은 근거입니다.",
            )

        connection = store._connection(project_id)
        try:
            assert connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM yujin_memory_candidates
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()["count"] == len(completed_candidates)
            assert connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM yujin_memory_candidate_audit
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()["count"] == len(completed_candidates)
        finally:
            connection.close()
    finally:
        _cleanup_postgres_hermes_project(store, project_id)


def test_postgres_yujin_memory_store_state_and_audit_match_local_contract(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory-d2",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin memory D2 {uuid4().hex}"
    )
    project_id = project.project_id
    try:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=f"timeline-{uuid4().hex}",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = f"conversation-{uuid4().hex}"
        store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        message, _ = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=conversation_id,
            user_text="영상 초반은 짧은 장면을 이어서 템포를 올려 주세요.",
        )
        candidate = store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id="postgres-d2-candidate",
            source_message_ids=(message["message_id"],),
            memory_scope="creator",
            category="pacing",
            proposed_text="빠른 컷 편집을 선호합니다.",
        )
        store.transition_yujin_memory_candidate(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            action="approve",
        )
        claim = store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            client_request_id="postgres-d2-store",
            claim_token="claim-" + "a" * 64,
        )
        store.mark_yujin_memory_store_call_started(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            claim_token="claim-" + "a" * 64,
        )
        store.record_yujin_memory_provider_outcome(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
            claim_token="claim-" + "a" * 64,
            status="stored",
            memory_ref="provider-private",
            event_ref=None,
        )
        store.finalize_yujin_memory_store(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
        )
        first_delete_call = (
            store.mark_yujin_memory_delete_call_started(
                project_id=project_id,
                candidate_id=candidate["candidate_id"],
            )
        )
        retried_delete_call = (
            store.mark_yujin_memory_delete_call_started(
                project_id=project_id,
                candidate_id=candidate["candidate_id"],
            )
        )

        assert claim["action"] == "add"
        assert first_delete_call["allow_absent"] is False
        assert retried_delete_call["allow_absent"] is True
        assert first_delete_call["memory_ref"] == "provider-private"
        assert store.get_yujin_memory_store_state(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
        ) == {
            "candidate_id": candidate["candidate_id"],
            "status": "approved",
            "storage_status": "stored",
            "retryable": False,
        }
        audit = store.list_yujin_memory_operation_audit(
            project_id=project_id,
            candidate_id=candidate["candidate_id"],
        )
        assert [
            (item["action"], item["storage_status"]) for item in audit
        ] == [
            ("claim", "claimed"),
            ("call_started", "claimed"),
            ("outcome", "claimed"),
            ("finalize", "stored"),
            ("call_started", "stored"),
        ]
    finally:
        _cleanup_postgres_hermes_project(store, project_id)


def test_postgres_yujin_memory_list_filters_conversation_before_limit(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory-d3",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin memory D3 {uuid4().hex}"
    )
    project_id = project.project_id
    try:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=f"timeline-{uuid4().hex}",
            session_payload={"segments": [], "history": []},
        )
        current_conversation_id = f"conversation-current-{uuid4().hex}"
        other_conversation_id = f"conversation-other-{uuid4().hex}"
        for conversation_id in (
            current_conversation_id,
            other_conversation_id,
        ):
            store.create_director_conversation(
                project_id=project_id,
                session_id=session["session_id"],
                conversation_id=conversation_id,
            )
        current_message, _ = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=current_conversation_id,
            user_text="빠른 템포를 기억해 주세요.",
        )
        other_message, _ = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=other_conversation_id,
            user_text="다른 대화입니다.",
        )
        current = store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=current_conversation_id,
            client_request_id="postgres-d3-current",
            source_message_ids=(current_message["message_id"],),
            memory_scope="creator",
            category="pacing",
            proposed_text="빠른 컷 편집을 선호합니다.",
        )
        store.transition_yujin_memory_candidate(
            project_id=project_id,
            candidate_id=current["candidate_id"],
            action="approve",
        )
        store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=current["candidate_id"],
            client_request_id="postgres-d3-store",
            claim_token="claim-" + "d" * 64,
        )
        connection = store._connection(project_id)
        try:
            for index in range(101):
                connection.execute(
                    """
                    INSERT INTO yujin_memory_candidates (
                        candidate_id, project_id, conversation_id,
                        client_request_id, request_fingerprint,
                        source_message_ids_json, memory_scope, category,
                        proposed_text, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'creator', 'workflow',
                        ?, 'pending', ?, ?)
                    """,
                    (
                        f"memory-candidate-other-{index:03d}",
                        project_id,
                        other_conversation_id,
                        f"postgres-d3-other-{index}",
                        f"fingerprint-{index}",
                        json.dumps([other_message["message_id"]]),
                        f"다른 대화 후보 {index}",
                        "9999-01-01T00:00:00+00:00",
                        "9999-01-01T00:00:00+00:00",
                    ),
                )
            connection.commit()
        finally:
            connection.close()

        listed = store.list_yujin_memory_candidates(
            project_id=project_id,
            conversation_id=current_conversation_id,
        )

        assert [item["candidate_id"] for item in listed] == [
            current["candidate_id"]
        ]
        assert listed[0]["storage_status"] == "claimed"
        assert listed[0]["retryable"] is False
    finally:
        _cleanup_postgres_hermes_project(store, project_id)


def _seed_yujin_memory_retrieval_parity(
    store: LocalProjectStore,
    *,
    name: str,
) -> tuple[str, str, list[str]]:
    project = store.bootstrap_project(name)
    project_id = project.project_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    current_conversation_id = f"conversation-current-{uuid4().hex}"
    other_conversation_id = f"conversation-other-{uuid4().hex}"
    sources: dict[str, str] = {}
    for conversation_id in (
        current_conversation_id,
        other_conversation_id,
    ):
        store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        message, _ = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=conversation_id,
            user_text="현재 대화의 편집 취향입니다.",
        )
        sources[conversation_id] = message["message_id"]

    definitions = (
        (
            current_conversation_id,
            "caption",
            "자막은 두 줄 이내를 선호합니다.",
            "approved",
            "stored",
            "memory-caption",
            "ext-" + "a" * 64,
        ),
        (
            current_conversation_id,
            "pacing",
            "빠른 컷 편집을 선호합니다.",
            "approved",
            "stored",
            "memory-pacing",
            "ext-" + "b" * 64,
        ),
        (
            current_conversation_id,
            "workflow",
            "대기 중인 취향입니다.",
            "pending",
            "not_requested",
            None,
            None,
        ),
        (
            current_conversation_id,
            "tone",
            "거절된 취향입니다.",
            "rejected",
            "not_requested",
            None,
            None,
        ),
        (
            current_conversation_id,
            "audio",
            "저장 실패한 취향입니다.",
            "approved",
            "failed_retryable",
            "memory-failed",
            "ext-" + "c" * 64,
        ),
        (
            current_conversation_id,
            "audio",
            "삭제된 취향입니다.",
            "approved",
            "deleted",
            "memory-deleted",
            "ext-" + "d" * 64,
        ),
        (
            current_conversation_id,
            "workflow",
            "private mapping이 없는 취향입니다.",
            "approved",
            "stored",
            None,
            None,
        ),
        (
            other_conversation_id,
            "pacing",
            "다른 대화의 취향입니다.",
            "approved",
            "stored",
            "memory-other-conversation",
            "ext-" + "e" * 64,
        ),
    )
    candidate_ids: list[str] = []
    for index, (
        conversation_id,
        category,
        text,
        status,
        storage_status,
        memory_ref,
        external_ref,
    ) in enumerate(definitions):
        candidate = store.create_yujin_memory_candidate(
            project_id=project_id,
            conversation_id=conversation_id,
            client_request_id=f"retrieval-parity-{index}",
            source_message_ids=(sources[conversation_id],),
            memory_scope="creator",
            category=category,
            proposed_text=text,
        )
        candidate_ids.append(candidate["candidate_id"])
        connection = store._connection(project_id)
        try:
            connection.execute(
                """
                UPDATE yujin_memory_candidates
                SET status = ?, storage_status = ?,
                    provider_memory_ref = ?, external_ref = ?
                WHERE project_id = ? AND candidate_id = ?
                """,
                (
                    status,
                    storage_status,
                    memory_ref,
                    external_ref,
                    project_id,
                    candidate["candidate_id"],
                ),
            )
            connection.commit()
        finally:
            connection.close()

    unrelated = store.bootstrap_project(f"{name} unrelated")
    unrelated_session = store.save_editing_session(
        project_id=unrelated.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    unrelated_conversation = f"conversation-unrelated-{uuid4().hex}"
    store.create_director_conversation(
        project_id=unrelated.project_id,
        session_id=unrelated_session["session_id"],
        conversation_id=unrelated_conversation,
    )
    unrelated_message, _ = _append_completed_yujin_source_messages(
        store,
        project_id=unrelated.project_id,
        session=unrelated_session,
        conversation_id=unrelated_conversation,
        user_text="다른 프로젝트의 취향입니다.",
    )
    unrelated_candidate = store.create_yujin_memory_candidate(
        project_id=unrelated.project_id,
        conversation_id=unrelated_conversation,
        client_request_id="retrieval-parity-unrelated",
        source_message_ids=(unrelated_message["message_id"],),
        memory_scope="creator",
        category="pacing",
        proposed_text="다른 프로젝트의 빠른 편집 취향입니다.",
    )
    connection = store._connection(unrelated.project_id)
    try:
        connection.execute(
            """
            UPDATE yujin_memory_candidates
            SET status = 'approved', storage_status = 'stored',
                provider_memory_ref = ?, external_ref = ?
            WHERE project_id = ? AND candidate_id = ?
            """,
            (
                "memory-unrelated-project",
                "ext-" + "f" * 64,
                unrelated.project_id,
                unrelated_candidate["candidate_id"],
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return (
        project_id,
        current_conversation_id,
        [project_id, unrelated.project_id],
    )


def test_postgres_yujin_memory_retrieval_rows_match_sqlite_exactly(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    postgres = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory-d4-retrieval",
        database_url=postgres_url,
    )
    local = LocalProjectStore(tmp_path / "sqlite-yujin-memory-d4-retrieval")
    postgres_project_id = ""
    postgres_project_ids: list[str] = []
    try:
        (
            postgres_project_id,
            postgres_conversation_id,
            postgres_project_ids,
        ) = _seed_yujin_memory_retrieval_parity(
            postgres,
            name=f"PostgreSQL Yujin memory D4 {uuid4().hex}",
        )
        local_project_id, local_conversation_id, _ = (
            _seed_yujin_memory_retrieval_parity(
                local,
                name=f"SQLite Yujin memory D4 {uuid4().hex}",
            )
        )

        postgres_rows = postgres.list_yujin_memory_retrieval_rows(
            project_id=postgres_project_id,
            conversation_id=postgres_conversation_id,
        )
        local_rows = local.list_yujin_memory_retrieval_rows(
            project_id=local_project_id,
            conversation_id=local_conversation_id,
        )

        def projection(rows: list[dict]) -> list[dict]:
            return [
                {
                    "status": row["status"],
                    "storage_status": row["storage_status"],
                    "memory_ref": row["memory_ref"],
                    "external_ref": row["external_ref"],
                    "text": row["text"],
                    "category": row["category"],
                }
                for row in rows
            ]

        assert projection(postgres_rows) == projection(local_rows) == [
            {
                "status": "approved",
                "storage_status": "stored",
                "memory_ref": "memory-caption",
                "external_ref": "ext-" + "a" * 64,
                "text": "자막은 두 줄 이내를 선호합니다.",
                "category": "caption",
            },
            {
                "status": "approved",
                "storage_status": "stored",
                "memory_ref": "memory-pacing",
                "external_ref": "ext-" + "b" * 64,
                "text": "빠른 컷 편집을 선호합니다.",
                "category": "pacing",
            },
        ]
        assert {
            row["project_id"] for row in postgres_rows
        } == {postgres_project_id}
        assert {
            row["conversation_id"] for row in postgres_rows
        } == {postgres_conversation_id}
        assert postgres.list_yujin_memory_retrieval_rows(
            project_id=postgres_project_id,
            conversation_id="missing",
        ) == []
    finally:
        for project_id in reversed(postgres_project_ids):
            _cleanup_postgres_hermes_project(postgres, project_id)


def test_postgres_expired_yujin_memory_claims_match_local_retry_paths(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    current = datetime(2026, 7, 30, 5, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-memory-d3-expired",
        database_url=postgres_url,
        now=lambda: current,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin memory D3 expired {uuid4().hex}"
    )
    project_id = project.project_id
    try:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=f"timeline-{uuid4().hex}",
            session_payload={"segments": [], "history": []},
        )
        conversation_id = f"conversation-{uuid4().hex}"
        store.create_director_conversation(
            project_id=project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
        )
        message, _ = _append_completed_yujin_source_messages(
            store,
            project_id=project_id,
            session=session,
            conversation_id=conversation_id,
            user_text="확인한 기억만 저장해 주세요.",
        )

        def create_and_claim(
            *,
            suffix: str,
            call_started: bool,
        ) -> dict:
            candidate = store.create_yujin_memory_candidate(
                project_id=project_id,
                conversation_id=conversation_id,
                client_request_id=f"candidate-{suffix}",
                source_message_ids=(message["message_id"],),
                memory_scope="creator",
                category="workflow",
                proposed_text=f"명시적으로 확인한 기억 {suffix}만 저장합니다.",
            )
            store.transition_yujin_memory_candidate(
                project_id=project_id,
                candidate_id=candidate["candidate_id"],
                action="approve",
            )
            claim_token = "claim-" + suffix * 64
            store.claim_yujin_memory_store(
                project_id=project_id,
                candidate_id=candidate["candidate_id"],
                client_request_id=f"store-{suffix}-1",
                claim_token=claim_token,
            )
            if call_started:
                store.mark_yujin_memory_store_call_started(
                    project_id=project_id,
                    candidate_id=candidate["candidate_id"],
                    claim_token=claim_token,
                )
            return candidate

        pre_call = create_and_claim(suffix="a", call_started=False)
        started = create_and_claim(suffix="b", call_started=True)
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
            candidate_id=pre_call["candidate_id"],
            client_request_id="store-a-2",
            claim_token="claim-" + "c" * 64,
        )
        reconciled = store.claim_yujin_memory_store(
            project_id=project_id,
            candidate_id=started["candidate_id"],
            client_request_id="store-b-2",
            claim_token="claim-" + "d" * 64,
        )

        assert live[pre_call["candidate_id"]]["retryable"] is False
        assert live[started["candidate_id"]]["retryable"] is False
        assert expired[pre_call["candidate_id"]]["retryable"] is True
        assert expired[started["candidate_id"]]["retryable"] is True
        assert reclaimed["action"] == "add"
        assert reconciled["action"] == "reconcile"
        assert reclaimed["candidate"]["retryable"] is False
        assert reconciled["candidate"]["retryable"] is False
        assert not {
            "write_claimed_at",
            "provider_call_started_at",
            "provider_event_ref",
            "provider_memory_ref",
        } & set(expired[pre_call["candidate_id"]])
    finally:
        _cleanup_postgres_hermes_project(store, project_id)


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("VIDEOBOX_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set VIDEOBOX_TEST_POSTGRES_URL to run PostgreSQL store integration tests")
    return value


def test_publish_terminal_current_truth_lock_sql_is_deterministic_without_postgres() -> None:
    calls: list[tuple[str, tuple[str, ...] | None]] = []

    class RecordingPostgresConnection:
        def execute(self, statement: str, parameters=None):
            calls.append(
                (
                    " ".join(translate_sql(statement).split()),
                    parameters,
                )
            )
            return SimpleNamespace()

    LocalProjectStore._lock_terminal_current_truth(
        connection=RecordingPostgresConnection(),
        project_id="project-a",
        session_id="session-a",
    )

    assert calls == [
        (
            "SELECT session_id FROM editing_sessions "
            "WHERE project_id = %s AND session_id = %s FOR UPDATE",
            ("project-a", "session-a"),
        ),
        (
            "INSERT INTO director_asset_index_revisions "
            "(project_id, revision) VALUES (%s, 0) "
            "ON CONFLICT (project_id) DO NOTHING",
            ("project-a",),
        ),
        (
            "SELECT revision FROM director_asset_index_revisions "
            "WHERE project_id = %s FOR UPDATE",
            ("project-a",),
        ),
    ]


def test_read_context_current_truth_lock_sql_is_deterministic_without_postgres() -> None:
    calls: list[tuple[str, tuple[str, ...] | None]] = []
    rows = iter(
        (
            {"session_id": "session-a", "session_revision": 3},
            {"revision": 7},
        )
    )

    class RecordingPostgresConnection:
        def execute(self, statement: str, parameters=None):
            calls.append(
                (
                    " ".join(translate_sql(statement).split()),
                    parameters,
                )
            )
            if statement.lstrip().startswith("INSERT"):
                return SimpleNamespace()
            return SimpleNamespace(fetchone=lambda: next(rows))

    current = LocalProjectStore._read_current_hermes_scope_with_lock(
        connection=RecordingPostgresConnection(),
        project_id="project-a",
        session_id="session-a",
    )

    assert current == (True, 3, 7)
    assert calls == [
        (
            "SELECT session_id, session_revision FROM editing_sessions "
            "WHERE project_id = %s AND session_id = %s FOR UPDATE",
            ("project-a", "session-a"),
        ),
        (
            "INSERT INTO director_asset_index_revisions "
            "(project_id, revision) VALUES (%s, 0) "
            "ON CONFLICT (project_id) DO NOTHING",
            ("project-a",),
        ),
        (
            "SELECT revision FROM director_asset_index_revisions "
            "WHERE project_id = %s FOR UPDATE",
            ("project-a",),
        ),
    ]


def test_postgres_read_context_full_consume_locks_truth_before_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    statements: list[str] = []
    ledger = {
        "jti": "cap-read",
        "project_id": "project-a",
        "conversation_id": "conversation-a",
        "run_id": "run-a",
        "session_id": "session-a",
        "session_revision": 3,
        "asset_index_revision": 7,
        "action": "read_context",
        "state": "issued",
        "expires_at": int(instant.timestamp()) + 300,
    }

    class RecordingPostgresConnection:
        in_transaction = False

        def execute(self, statement: str, parameters=None):
            normalized = " ".join(translate_sql(statement).split())
            statements.append(normalized)
            if normalized == "BEGIN":
                self.in_transaction = True
                return SimpleNamespace()
            if normalized.startswith(
                "SELECT session_id, session_revision FROM editing_sessions"
            ):
                return SimpleNamespace(
                    fetchone=lambda: {
                        "session_id": "session-a",
                        "session_revision": 3,
                    }
                )
            if normalized.startswith(
                "SELECT revision FROM director_asset_index_revisions"
            ):
                return SimpleNamespace(fetchone=lambda: {"revision": 7})
            if normalized.startswith(
                "SELECT * FROM hermes_capability_ledger"
            ):
                return SimpleNamespace(fetchone=lambda: ledger)
            return SimpleNamespace(rowcount=1)

        def commit(self) -> None:
            self.in_transaction = False

        def rollback(self) -> None:
            self.in_transaction = False

        def close(self) -> None:
            return None

    connection = RecordingPostgresConnection()
    store = LocalProjectStore(
        tmp_path / "projects",
        now=lambda: instant,
    )
    monkeypatch.setattr(store, "_connection", lambda _project_id: connection)
    monkeypatch.setattr(
        store,
        "_purge_expired_hermes_capabilities",
        lambda **_: None,
    )

    result = store.consume_registered_hermes_capability(
        project_id="project-a",
        capability_id="cap-read",
        conversation_id="conversation-a",
        run_id="run-a",
        session_id="session-a",
        session_revision=3,
        asset_index_revision=7,
        action="read_context",
    )

    assert result == "accepted"
    truth_session = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith(
            "SELECT session_id, session_revision FROM editing_sessions"
        )
    )
    truth_asset = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith(
            "SELECT revision FROM director_asset_index_revisions"
        )
    )
    ledger_lock = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT * FROM hermes_capability_ledger")
    )
    ledger_update = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("UPDATE hermes_capability_ledger")
    )
    assert truth_session < truth_asset < ledger_lock < ledger_update


def test_postgres_store_bootstraps_and_lists_a_project(tmp_path: Path, postgres_url: str) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)

    project = store.bootstrap_project(f"Postgres project {uuid4().hex}")

    assert next(item for item in store.list_projects() if item["project_id"] == project.project_id) == {
        "project_id": project.project_id,
        "name": project.name,
        "status": "draft",
        "root_storage_uri": f"local://projects/{project.project_id}",
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def test_postgres_legacy_jti_only_hermes_capability_methods_never_create_authority(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes ledger {uuid4().hex}")

    assert store.consume_hermes_capability(
        project_id=project.project_id,
        jti="missing-jti",
        expires_at=1_900_000_000,
    ) == "missing"
    store.revoke_hermes_capability(
        project_id=project.project_id,
        jti="missing-jti",
        expires_at=1_900_000_000,
    )
    connection = store._connection(project.project_id)
    try:
        assert connection.execute(
            "SELECT jti FROM hermes_capability_ledger WHERE project_id = ? AND jti = ?",
            (project.project_id, "missing-jti"),
        ).fetchone() is None
    finally:
        connection.close()


def test_postgres_hermes_capability_lifecycle_is_scoped_atomic_and_audited(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(f"Hermes C3 lifecycle {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={"segments": [], "history": []},
    )
    prefix = uuid4().hex
    read_id = f"{prefix}-read"
    publish_id = f"{prefix}-publish"
    expires_at = int(instant.timestamp()) + 300
    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": read_id,
                    "action": "read_context",
                    "expires_at": expires_at,
                },
                {
                    "capability_id": publish_id,
                    "action": "publish_proposal",
                    "expires_at": expires_at,
                },
            ),
        )
        assert store.get_expected_hermes_capability(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            action="read_context",
        )["capability_id"] == read_id
        assert store.consume_registered_hermes_capability(
            project_id=project.project_id,
            capability_id=read_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            action="read_context",
        ) == "accepted"
        assert store.consume_registered_hermes_capability(
            project_id=project.project_id,
            capability_id=read_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            action="read_context",
        ) == "hermes_capability_replayed"
        assert store.revoke_issued_hermes_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            reason="hermes_capability_revoked",
        ) == 1
        assert store.revoke_issued_hermes_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            reason="hermes_capability_revoked",
        ) == 0
        denial = store.record_hermes_capability_denial(
            project_id=project.project_id,
            conversation_id="missing-conversation",
            run_id="missing-run",
            action="read_context",
            reason="hermes_capability_signature_invalid",
        )
        assert denial["capability_id"] is None

        connection = store._connection(project.project_id)
        try:
            rows = connection.execute(
                """
                SELECT jti, lifecycle_version, state
                FROM hermes_capability_ledger
                WHERE project_id = ?
                ORDER BY jti
                """,
                (project.project_id,),
            ).fetchall()
            audit_columns = {
                str(row["column_name"])
                for row in connection.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'hermes_capability_audit'
                    """
                ).fetchall()
            }
        finally:
            connection.close()
        assert {(row["jti"], row["state"]) for row in rows} == {
            (read_id, "consumed"),
            (publish_id, "revoked"),
        }
        assert {row["lifecycle_version"] for row in rows} == {
            "videobox.yujin-capability.v1"
        }
        assert audit_columns == {
            "audit_event_id",
            "capability_id",
            "project_id",
            "conversation_id",
            "run_id",
            "action",
            "outcome",
            "reason",
            "occurred_at",
        }
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


@pytest.mark.parametrize(
    "inject_publish_audit_fault",
    (False, True),
    ids=("success", "fault-rollback"),
)
def test_postgres_publish_proposal_consume_is_atomic_with_terminal(
    tmp_path: Path,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    inject_publish_audit_fault: bool,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes C3 publish terminal {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [{"segment_id": "segment-1"}],
            "history": [],
        },
    )
    conversation_id = f"conversation-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    durable = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="proposal",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    prefix = uuid4().hex
    publish_id = f"{prefix}-publish"
    expires_at = int(instant.timestamp()) + 300
    proposal_id = f"proposal-{uuid4().hex}"
    candidate = DirectorCandidate(
        candidate_id=f"candidate-{uuid4().hex}",
        visible_reference_code="P00-C01",
        media_type="broll",
        asset_id="candidate-only",
        library_asset_id=None,
        reason_chips=("candidate",),
        scores={},
        availability="candidate_only",
        review_status="pending",
        preview_uri=None,
        controls={},
        expected_content_sha256=None,
        media_revision="candidate-r1",
        canonical_metadata={},
    )
    proposal = DirectorProposal(
        proposal_id=proposal_id,
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=0,
        source_session_id=session["session_id"],
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="candidate_only",
        diff={"proposal_mode": "candidate_only"},
        expires_at=None,
        candidates=(candidate,),
    )
    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=durable["run_id"],
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": f"{prefix}-read",
                    "action": "read_context",
                    "expires_at": expires_at,
                },
                {
                    "capability_id": publish_id,
                    "action": "publish_proposal",
                    "expires_at": expires_at,
                },
            ),
        )
        if inject_publish_audit_fault:
            original_append = store._append_hermes_capability_audit

            def fail_after_consumed_audit(connection, **kwargs):
                event = original_append(connection, **kwargs)
                if kwargs["reason"] == "hermes_capability_consumed":
                    raise OSError("postgres publish audit fault")
                return event

            monkeypatch.setattr(
                store,
                "_append_hermes_capability_audit",
                fail_after_consumed_audit,
            )
        completion_kwargs = {
            "project_id": project.project_id,
            "run_id": durable["run_id"],
            "owner_token": durable["owner_token"],
            "status": "completed",
            "assistant_text": "candidate",
            "retryable": False,
            "proposal": proposal,
            "verified_publish_capability": {
                "capability_id": publish_id,
                "project_id": project.project_id,
                "conversation_id": conversation_id,
                "run_id": durable["run_id"],
                "session_id": session["session_id"],
                "session_revision": session["session_revision"],
                "asset_index_revision": 0,
                "action": "publish_proposal",
                "issued_at": int(instant.timestamp()),
                "not_before": int(instant.timestamp()),
                "expires_at": expires_at,
            },
        }
        if inject_publish_audit_fault:
            with pytest.raises(
                OSError,
                match="postgres publish audit fault",
            ):
                store.complete_director_hermes_run(**completion_kwargs)
        else:
            assert store.complete_director_hermes_run(**completion_kwargs)
        connection = store._connection(project.project_id)
        try:
            publish = connection.execute(
                """
                SELECT state FROM hermes_capability_ledger
                WHERE project_id = ? AND jti = ?
                """,
                (project.project_id, publish_id),
            ).fetchone()
            accepted_audit = connection.execute(
                """
                SELECT COUNT(*) AS count FROM hermes_capability_audit
                WHERE project_id = ? AND capability_id = ?
                  AND reason = 'hermes_capability_consumed'
                """,
                (project.project_id, publish_id),
            ).fetchone()
            run = connection.execute(
                """
                SELECT status FROM director_hermes_runs
                WHERE project_id = ? AND run_id = ?
                """,
                (project.project_id, durable["run_id"]),
            ).fetchone()
            terminal_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM director_hermes_run_events
                WHERE project_id = ? AND run_id = ?
                  AND event_type IN ('run_completed', 'blocked')
                """,
                (project.project_id, durable["run_id"]),
            ).fetchone()
        finally:
            connection.close()
        if inject_publish_audit_fault:
            assert publish["state"] == "issued"
            assert accepted_audit["count"] == 0
            assert run["status"] == "pending"
            assert terminal_count["count"] == 0
            with pytest.raises(KeyError, match="Director proposal not found"):
                store.get_director_proposal(
                    project.project_id,
                    proposal_id,
                )
        else:
            assert publish["state"] == "consumed"
            assert accepted_audit["count"] == 1
            assert run["status"] == "completed"
            assert terminal_count["count"] == 1
            assert store.get_director_proposal(
                project.project_id,
                proposal_id,
            ).status == "candidate_only"
    finally:
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "DELETE FROM director_proposal_lifecycle_events "
                "WHERE proposal_id = ?",
                (proposal_id,),
            )
            connection.execute(
                "DELETE FROM director_proposals "
                "WHERE project_id = ? AND proposal_id = ?",
                (project.project_id, proposal_id),
            )
            connection.execute(
                "DELETE FROM director_proposal_revisions "
                "WHERE project_id = ?",
                (project.project_id,),
            )
            connection.commit()
        finally:
            connection.close()
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_postgres_publish_terminal_serializes_current_truth_before_session_writer(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes C3 publish current truth {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [{"segment_id": "segment-1"}],
            "history": [],
        },
    )
    conversation_id = f"conversation-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    durable = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="proposal",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    prefix = uuid4().hex
    publish_id = f"{prefix}-publish"
    expires_at = int(instant.timestamp()) + 300
    proposal_id = f"proposal-{uuid4().hex}"
    proposal = DirectorProposal(
        proposal_id=proposal_id,
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=0,
        source_session_id=session["session_id"],
        target_segment_ids=("segment-1",),
        source_script_segment_ids=("segment-1",),
        status="candidate_only",
        diff={"proposal_mode": "candidate_only"},
        expires_at=None,
        candidates=(
            DirectorCandidate(
                candidate_id=f"candidate-{uuid4().hex}",
                visible_reference_code="P00-C01",
                media_type="broll",
                asset_id="candidate-only",
                library_asset_id=None,
                reason_chips=("candidate",),
                scores={},
                availability="candidate_only",
                review_status="pending",
                preview_uri=None,
                controls={},
                expected_content_sha256=None,
                media_revision="candidate-r1",
                canonical_metadata={},
            ),
        ),
    )
    verified = {
        "capability_id": publish_id,
        "project_id": project.project_id,
        "conversation_id": conversation_id,
        "run_id": durable["run_id"],
        "session_id": session["session_id"],
        "session_revision": session["session_revision"],
        "asset_index_revision": 0,
        "action": "publish_proposal",
        "issued_at": int(instant.timestamp()),
        "not_before": int(instant.timestamp()),
        "expires_at": expires_at,
    }
    truth_checked = Event()
    release_terminal = Event()
    original_decide = store._decide_terminal_publish_capability

    def pause_after_current_truth(**kwargs):
        decision = original_decide(**kwargs)
        truth_checked.set()
        if not release_terminal.wait(timeout=10):
            raise TimeoutError("terminal current-truth gate timed out")
        return decision

    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=durable["run_id"],
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": f"{prefix}-read",
                    "action": "read_context",
                    "expires_at": expires_at,
                },
                {
                    "capability_id": publish_id,
                    "action": "publish_proposal",
                    "expires_at": expires_at,
                },
            ),
        )
        with patch.object(
            store,
            "_decide_terminal_publish_capability",
            pause_after_current_truth,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                terminal_future = executor.submit(
                    store.complete_director_hermes_run,
                    project_id=project.project_id,
                    run_id=durable["run_id"],
                    owner_token=durable["owner_token"],
                    status="completed",
                    assistant_text="candidate",
                    retryable=False,
                    proposal=proposal,
                    verified_publish_capability=verified,
                )
                assert truth_checked.wait(timeout=10)
                writer_payload = deepcopy(session)
                writer_payload["history"] = ["concurrent-edit"]
                writer_future = executor.submit(
                    store.update_editing_session,
                    project_id=project.project_id,
                    session_id=session["session_id"],
                    session_payload=writer_payload,
                    expected_revision=session["session_revision"],
                )
                writer_finished_while_terminal_paused = False
                try:
                    writer_result = writer_future.result(timeout=1)
                    writer_finished_while_terminal_paused = True
                except FutureTimeoutError:
                    writer_result = None
                finally:
                    release_terminal.set()
                terminal_result = terminal_future.result(timeout=10)
                if writer_result is None:
                    writer_result = writer_future.result(timeout=10)

        assert writer_finished_while_terminal_paused is False
        assert terminal_result is True
        assert writer_result["session_revision"] == 2
        assert store.get_asset_index_revision(project.project_id) == 0
        assert store.get_director_proposal(
            project.project_id,
            proposal_id,
        ).status == "candidate_only"
    finally:
        release_terminal.set()
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "DELETE FROM director_proposal_lifecycle_events "
                "WHERE proposal_id = ?",
                (proposal_id,),
            )
            connection.execute(
                "DELETE FROM director_proposals "
                "WHERE project_id = ? AND proposal_id = ?",
                (project.project_id, proposal_id),
            )
            connection.execute(
                "DELETE FROM director_proposal_revisions "
                "WHERE project_id = ?",
                (project.project_id,),
            )
            connection.commit()
        finally:
            connection.close()
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_postgres_hermes_capability_expired_issued_consume_is_denied_and_audited(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    clock = [datetime(2026, 7, 30, 12, 0, tzinfo=UTC)]
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: clock[0],
    )
    project = store.bootstrap_project(f"Hermes C3 expired {uuid4().hex}")
    prefix = uuid4().hex
    expires_at = int(clock[0].timestamp()) + 300
    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id="session-1",
            session_revision=3,
            asset_index_revision=7,
            capabilities=(
                {
                    "capability_id": f"{prefix}-read",
                    "action": "read_context",
                    "expires_at": expires_at,
                },
                {
                    "capability_id": f"{prefix}-publish",
                    "action": "publish_proposal",
                    "expires_at": expires_at,
                },
            ),
        )
        clock[0] = datetime.fromtimestamp(expires_at + 1, tz=UTC)

        assert store.consume_registered_hermes_capability(
            project_id=project.project_id,
            capability_id=f"{prefix}-read",
            conversation_id="conversation-1",
            run_id="run-1",
            session_id="session-1",
            session_revision=3,
            asset_index_revision=7,
            action="read_context",
        ) == "hermes_capability_expired"

        connection = store._connection(project.project_id)
        try:
            row = connection.execute(
                """
                SELECT state FROM hermes_capability_ledger
                WHERE project_id = ? AND jti = ?
                """,
                (project.project_id, f"{prefix}-read"),
            ).fetchone()
            denial = connection.execute(
                """
                SELECT capability_id, outcome, reason
                FROM hermes_capability_audit
                WHERE project_id = ? AND capability_id = ?
                  AND reason = 'hermes_capability_expired'
                """,
                (project.project_id, f"{prefix}-read"),
            ).fetchone()
        finally:
            connection.close()
        assert row["state"] == "issued"
        assert dict(denial) == {
            "capability_id": f"{prefix}-read",
            "outcome": "denied",
            "reason": "hermes_capability_expired",
        }
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


@pytest.mark.parametrize(
    "changed_truth",
    ("session_revision", "asset_index_revision"),
)
def test_postgres_read_context_consume_rechecks_current_truth_before_consume(
    tmp_path: Path,
    postgres_url: str,
    changed_truth: str,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes read consume race {changed_truth} {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={"segments": [], "history": []},
    )
    prefix = uuid4().hex
    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id="conversation-1",
            run_id="run-1",
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": f"{prefix}-read",
                    "action": "read_context",
                    "expires_at": int(instant.timestamp()) + 300,
                },
                {
                    "capability_id": f"{prefix}-publish",
                    "action": "publish_proposal",
                    "expires_at": int(instant.timestamp()) + 300,
                },
            ),
        )
        if changed_truth == "session_revision":
            store.update_editing_session(
                project_id=project.project_id,
                session_id=session["session_id"],
                session_payload={"segments": [], "history": []},
                expected_revision=session["session_revision"],
            )
        else:
            assert store.bump_asset_index_revision(project.project_id) == 1

        result = store.consume_registered_hermes_capability(
            project_id=project.project_id,
            capability_id=f"{prefix}-read",
            conversation_id="conversation-1",
            run_id="run-1",
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            action="read_context",
        )

        assert result == "hermes_capability_scope_forbidden"
        connection = store._connection(project.project_id)
        try:
            state = connection.execute(
                "SELECT state FROM hermes_capability_ledger "
                "WHERE project_id = ? AND jti = ?",
                (project.project_id, f"{prefix}-read"),
            ).fetchone()["state"]
            denial = connection.execute(
                "SELECT outcome, reason FROM hermes_capability_audit "
                "WHERE project_id = ? AND capability_id = ? "
                "AND outcome = 'denied' "
                "AND reason = 'hermes_capability_scope_forbidden'",
                (project.project_id, f"{prefix}-read"),
            ).fetchone()
        finally:
            connection.close()
        assert state == "issued"
        assert dict(denial) == {
            "outcome": "denied",
            "reason": "hermes_capability_scope_forbidden",
        }
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_postgres_current_truth_then_revoke_and_read_consume_settle_without_lock_inversion(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes read-revoke lock order {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conversation-{uuid4().hex}"
    run_id = f"run-{uuid4().hex}"
    prefix = uuid4().hex
    read_id = f"{prefix}-read"
    terminal_truth_locked = Event()
    release_terminal = Event()
    consume_truth_attempted = Event()
    consume_ledger_locked = Event()
    inversion_observed = Event()
    consume_thread_id: list[int] = []
    original_execute = _PostgresConnection.execute

    def observe_lock_order(self, statement: str, parameters=None):
        normalized = " ".join(statement.split())
        is_consume_thread = (
            bool(consume_thread_id)
            and get_ident() == consume_thread_id[0]
        )
        if is_consume_thread and normalized.startswith(
            "SELECT session_id, session_revision FROM editing_sessions"
        ):
            if consume_ledger_locked.is_set():
                inversion_observed.set()
            consume_truth_attempted.set()
        result = original_execute(self, statement, parameters)
        if (
            is_consume_thread
            and normalized.startswith(
                "SELECT * FROM hermes_capability_ledger"
            )
            and "AND jti = ?" in normalized
        ):
            consume_ledger_locked.set()
        return result

    def consume_read_capability() -> str:
        consume_thread_id.append(get_ident())
        return store.consume_registered_hermes_capability(
            project_id=project.project_id,
            capability_id=read_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            action="read_context",
        )

    def revoke_after_current_truth_lock() -> int:
        connection = store._connection(project.project_id)
        try:
            store._begin_hermes_capability_transaction(connection)
            store._lock_terminal_current_truth(
                connection=connection,
                project_id=project.project_id,
                session_id=session["session_id"],
            )
            terminal_truth_locked.set()
            if not release_terminal.wait(timeout=10):
                raise TimeoutError("terminal revoke release timed out")
            revoked = store._revoke_issued_hermes_capabilities_with_connection(
                connection=connection,
                project_id=project.project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                occurred_at=instant.isoformat(),
            )
            connection.commit()
            return revoked
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": read_id,
                    "action": "read_context",
                    "expires_at": int(instant.timestamp()) + 300,
                },
                {
                    "capability_id": f"{prefix}-publish",
                    "action": "publish_proposal",
                    "expires_at": int(instant.timestamp()) + 300,
                },
            ),
        )
        with patch.object(
            _PostgresConnection,
            "execute",
            observe_lock_order,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                terminal_future = executor.submit(
                    revoke_after_current_truth_lock
                )
                assert terminal_truth_locked.wait(timeout=10)
                consume_future = executor.submit(consume_read_capability)
                assert consume_truth_attempted.wait(timeout=10)
                release_terminal.set()
                assert terminal_future.result(timeout=10) == 2
                assert (
                    consume_future.result(timeout=10)
                    == "hermes_capability_revoked"
                )

        assert inversion_observed.is_set() is False
    finally:
        release_terminal.set()
        _cleanup_postgres_hermes_project(store, project.project_id)


@pytest.mark.parametrize(
    "inject_recovery_audit_fault",
    (False, True),
    ids=("success", "fault-rollback"),
)
def test_postgres_recover_interrupted_revokes_issued_capabilities_atomically(
    tmp_path: Path,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    inject_recovery_audit_fault: bool,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes C3 recovery revoke {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conversation-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="orphan",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    prefix = uuid4().hex
    expires_at = int(instant.timestamp()) + 300
    try:
        store.register_hermes_run_capabilities(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=run["run_id"],
            session_id=session["session_id"],
            session_revision=session["session_revision"],
            asset_index_revision=0,
            capabilities=(
                {
                    "capability_id": f"{prefix}-old-key-read",
                    "action": "read_context",
                    "expires_at": expires_at,
                },
                {
                    "capability_id": f"{prefix}-old-key-publish",
                    "action": "publish_proposal",
                    "expires_at": expires_at,
                },
            ),
        )
        if inject_recovery_audit_fault:
            original_append = store._append_hermes_capability_audit

            def fail_after_revoke_audit(connection, **kwargs):
                event = original_append(connection, **kwargs)
                if kwargs["reason"] == "hermes_capability_revoked":
                    raise OSError("postgres recovery revoke audit fault")
                return event

            monkeypatch.setattr(
                store,
                "_append_hermes_capability_audit",
                fail_after_revoke_audit,
            )
            with pytest.raises(
                OSError,
                match="postgres recovery revoke audit fault",
            ):
                store.recover_interrupted_director_hermes_runs(
                    project_id=project.project_id
                )
            recovered = []
        else:
            recovered = store.recover_interrupted_director_hermes_runs(
                project_id=project.project_id
            )

        connection = store._connection(project.project_id)
        try:
            states = {
                row["state"]
                for row in connection.execute(
                    "SELECT state FROM hermes_capability_ledger "
                    "WHERE project_id = ? AND run_id = ?",
                    (project.project_id, run["run_id"]),
                ).fetchall()
            }
            revoke_audits = connection.execute(
                """
                SELECT COUNT(*) AS count FROM hermes_capability_audit
                WHERE project_id = ? AND run_id = ?
                  AND reason = 'hermes_capability_revoked'
                """,
                (project.project_id, run["run_id"]),
            ).fetchone()
        finally:
            connection.close()
        assert [item["run_id"] for item in recovered] == (
            [] if inject_recovery_audit_fault else [run["run_id"]]
        )
        assert store.get_director_hermes_run(
            project_id=project.project_id,
            run_id=run["run_id"],
        )["status"] == (
            "pending" if inject_recovery_audit_fault else "interrupted"
        )
        assert states == (
            {"issued"} if inject_recovery_audit_fault else {"revoked"}
        )
        assert revoke_audits["count"] == (
            0 if inject_recovery_audit_fault else 2
        )
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_postgres_hermes_capability_migrates_pre_c3_rows_without_fabrication(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    legacy_project_id = f"legacy-{uuid4().hex}"
    connection = _PostgresConnection(postgres_url)
    try:
        connection.execute("DROP TABLE IF EXISTS hermes_capability_audit")
        connection.execute("DROP TABLE IF EXISTS hermes_capability_ledger")
        connection.execute(
            """
            CREATE TABLE hermes_capability_ledger (
                project_id TEXT NOT NULL,
                jti TEXT NOT NULL,
                state TEXT NOT NULL,
                expires_at BIGINT NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (project_id, jti)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO hermes_capability_ledger (
                project_id, jti, state, expires_at, recorded_at
            ) VALUES (?, 'legacy-jti', 'revoked', 1900000000, ?)
            """,
            (legacy_project_id, datetime(2026, 7, 30, tzinfo=UTC).isoformat()),
        )
        connection.commit()
    finally:
        connection.close()

    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    connection = store._connection(legacy_project_id)
    try:
        legacy = connection.execute(
            """
            SELECT * FROM hermes_capability_ledger
            WHERE project_id = ? AND jti = 'legacy-jti'
            """,
            (legacy_project_id,),
        ).fetchone()
        audit_count = connection.execute(
            "SELECT COUNT(*) AS count FROM hermes_capability_audit"
        ).fetchone()["count"]
    finally:
        connection.close()
    assert legacy["lifecycle_version"] == "legacy_retired"
    assert legacy["state"] == "revoked"
    assert all(
        legacy[field] is None
        for field in (
            "conversation_id",
            "run_id",
            "session_id",
            "session_revision",
            "asset_index_revision",
            "action",
        )
    )
    assert legacy["updated_at"] == legacy["recorded_at"]
    assert audit_count == 0
    assert store.get_expected_hermes_capability(
        project_id=legacy_project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        action="read_context",
    ) is None


def test_postgres_hermes_events_use_durable_cursor_and_terminal_cas(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes events {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert store.append_director_hermes_draft_event(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        assistant_draft_text="visible",
        event_text="visible",
        expected_event_id=2,
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="visible answer",
        public_text="visible",
        retryable=False,
    )
    assert [
        item["event_id"]
        for item in store.list_director_hermes_run_events(
            project_id=project.project_id,
            conversation_id=conversation_id,
            run_id=run["run_id"],
        )
    ] == [1, 2, 3, 4]


def test_postgres_hermes_cursor_and_terminal_have_one_concurrent_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes CAS {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        draft_results = list(
            executor.map(
                lambda suffix: store.append_director_hermes_draft_event(
                    project_id=project.project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    assistant_draft_text=f"visible {suffix}",
                    event_text=f"visible {suffix}",
                    expected_event_id=2,
                ),
                ("one", "two"),
            )
        )
    assert sorted(draft_results) == [False, True]
    durable = store.get_director_hermes_run(
        project_id=project.project_id, run_id=run["run_id"]
    )
    public_text = durable["assistant_draft_text"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        terminal_results = list(
            executor.map(
                lambda _: store.complete_director_hermes_run(
                    project_id=project.project_id,
                    run_id=run["run_id"],
                    owner_token=run["owner_token"],
                    status="completed",
                    assistant_text=f"{public_text} final",
                    public_text=public_text,
                    retryable=False,
                ),
                range(2),
            )
        )
    assert sorted(terminal_results) == [False, True]
    events = store.list_director_hermes_run_events(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=run["run_id"],
    )
    assert [item["event_id"] for item in events] == [1, 2, 3, 4]
    assert sum(item["event_type"] == "run_completed" for item in events) == 1


def test_postgres_pre_c1_terminal_tombstone_backfills_exact_replay(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes legacy {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="hello",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=run["run_id"],
        owner_token=run["owner_token"],
        status="completed",
        assistant_text="legacy answer",
        public_text="",
        retryable=False,
    )
    connection = store._connection(project.project_id)
    try:
        connection.execute(
            "DELETE FROM director_hermes_run_events "
            "WHERE project_id = ? AND run_id = ?",
            (project.project_id, run["run_id"]),
        )
        connection.execute(
            "UPDATE director_hermes_runs SET next_event_id = 1 "
            "WHERE project_id = ? AND run_id = ?",
            (project.project_id, run["run_id"]),
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = PostgresProjectStore(tmp_path, database_url=postgres_url)
    assert upgraded.list_director_hermes_run_events(
        project_id=project.project_id,
        conversation_id=conversation_id,
        run_id=run["run_id"],
    ) == [
        {
            "event_id": 1,
            "event_type": "run_started",
            "text": "",
            "retryable": False,
        },
        {
            "event_id": 2,
            "event_type": "run_completed",
            "text": "legacy answer",
            "retryable": False,
        },
    ]


def test_postgres_pre_c2_retry_column_migrates_without_losing_existing_run(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes retry migration {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    run = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"message-{uuid4().hex}",
        user_text="migration source",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
    )

    try:
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "ALTER TABLE director_hermes_runs "
                "DROP COLUMN retry_of_run_id"
            )
            connection.commit()
        finally:
            connection.close()

        upgraded = PostgresProjectStore(tmp_path, database_url=postgres_url)
        preserved = upgraded.get_director_hermes_run(
            project_id=project.project_id,
            run_id=run["run_id"],
        )
        assert preserved["run_id"] == run["run_id"]
        assert preserved["user_text"] == "migration source"
        assert preserved["status"] == "pending"
        assert preserved["retry_of_run_id"] is None
    finally:
        recovered = PostgresProjectStore(tmp_path, database_url=postgres_url)
        _cleanup_postgres_hermes_project(recovered, project.project_id)


def test_postgres_pre_message_order_migration_preserves_fixed_clock_exchanges(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Director message order migration {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={"segments": [], "history": []},
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    first = store.append_director_exchange(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="message-1",
        user_text="user-1",
        assistant_text="assistant-1",
    )
    store.append_director_exchange(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id="message-2",
        user_text="user-2",
        assistant_text="assistant-2",
    )

    try:
        connection = store._connection(project.project_id)
        try:
            connection.execute(
                "DROP INDEX IF EXISTS "
                "director_messages_conversation_order_idx"
            )
            connection.execute(
                "ALTER TABLE director_messages DROP COLUMN message_order"
            )
            connection.commit()
        finally:
            connection.close()

        upgraded = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        replay = upgraded.append_director_exchange(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            client_message_id="message-1",
            user_text="user-1",
            assistant_text="must-not-replace",
        )
        assert replay == first
        assert [
            message["text"]
            for message in upgraded.list_director_messages(
                project_id=project.project_id,
                conversation_id=conversation_id,
            )
        ] == ["user-1", "assistant-1", "user-2", "assistant-2"]

        connection = upgraded._connection(project.project_id)
        try:
            order_row = connection.execute(
                """
                SELECT COUNT(*) AS message_count,
                       COUNT(message_order) AS non_null_count,
                       COUNT(DISTINCT message_order) AS unique_count
                FROM director_messages
                WHERE project_id = ? AND conversation_id = ?
                """,
                (project.project_id, conversation_id),
            ).fetchone()
        finally:
            connection.close()
        assert order_row is not None
        assert (
            int(order_row["message_count"]),
            int(order_row["non_null_count"]),
            int(order_row["unique_count"]),
        ) == (4, 4, 4)

        repeated = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        assert [
            message["text"]
            for message in repeated.list_director_messages(
                project_id=project.project_id,
                conversation_id=conversation_id,
            )
        ] == ["user-1", "assistant-1", "user-2", "assistant-2"]
    finally:
        recovered = PostgresProjectStore(
            tmp_path,
            database_url=postgres_url,
            now=lambda: instant,
        )
        _cleanup_postgres_hermes_project(recovered, project.project_id)


@pytest.mark.parametrize("source_status", ("blocked", "interrupted"))
def test_postgres_retry_is_linked_and_identity_atomic(
    tmp_path: Path,
    postgres_url: str,
    source_status: str,
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(
        f"Hermes retry atomic {source_status} {uuid4().hex}"
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "caption_text": "장면",
                }
            ],
            "history": [],
        },
    )
    conversation_id = f"conv-{uuid4().hex}"
    store.create_director_conversation(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
    )
    source = store.begin_director_hermes_run(
        project_id=project.project_id,
        session_id=session["session_id"],
        conversation_id=conversation_id,
        client_message_id=f"source-{uuid4().hex}",
        user_text="retry exact text",
        expected_session_revision=session["session_revision"],
        expected_asset_index_revision=0,
        selected_segment_id="segment-1",
    )
    assert store.complete_director_hermes_run(
        project_id=project.project_id,
        run_id=source["run_id"],
        owner_token=source["owner_token"],
        status=source_status,
        assistant_text="terminal",
        public_text="",
        retryable=True,
    )

    try:
        before_messages = store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        )
        with pytest.raises(
            ValueError,
            match="hermes_run_retry_identity_mismatch",
        ):
            store.begin_director_hermes_run(
                project_id=project.project_id,
                session_id=session["session_id"],
                conversation_id=conversation_id,
                client_message_id=f"invalid-{uuid4().hex}",
                user_text="changed text",
                expected_session_revision=session["session_revision"],
                expected_asset_index_revision=0,
                selected_segment_id="segment-1",
                retry_of_run_id=source["run_id"],
            )
        with pytest.raises(KeyError, match="director_hermes_run_missing"):
            store.begin_director_hermes_run(
                project_id=project.project_id,
                session_id=session["session_id"],
                conversation_id="wrong-conversation",
                client_message_id=f"wrong-scope-{uuid4().hex}",
                user_text="retry exact text",
                expected_session_revision=session["session_revision"],
                expected_asset_index_revision=0,
                selected_segment_id="segment-1",
                retry_of_run_id=source["run_id"],
            )
        assert store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        ) == before_messages

        retried = store.begin_director_hermes_run(
            project_id=project.project_id,
            session_id=session["session_id"],
            conversation_id=conversation_id,
            client_message_id=f"retry-{uuid4().hex}",
            user_text="retry exact text",
            expected_session_revision=session["session_revision"],
            expected_asset_index_revision=0,
            selected_segment_id="segment-1",
            retry_of_run_id=source["run_id"],
        )
        durable = store.get_director_hermes_run(
            project_id=project.project_id,
            run_id=retried["run_id"],
        )
        assert durable["retry_of_run_id"] == source["run_id"]
        assert durable["status"] == "pending"
        assert [
            event["event_type"]
            for event in store.list_director_hermes_run_events(
                project_id=project.project_id,
                conversation_id=conversation_id,
                run_id=retried["run_id"],
            )
        ] == ["run_started"]
        after_messages = store.list_director_messages(
            project_id=project.project_id,
            conversation_id=conversation_id,
        )
        assert len(after_messages) == len(before_messages) + 1
        assert after_messages[-1]["role"] == "user"
        assert after_messages[-1]["text"] == "retry exact text"
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_sqlite_legacy_jti_only_hermes_capability_methods_never_create_authority(
    tmp_path: Path,
) -> None:
    instant = datetime(2026, 7, 19, tzinfo=UTC)
    store = LocalProjectStore(tmp_path, now=lambda: instant)
    project = store.bootstrap_project("Hermes legacy JTI-only denial")

    assert store.consume_hermes_capability(
        project_id=project.project_id,
        jti="missing-jti",
        expires_at=int(instant.timestamp()) + 120,
    ) == "missing"
    store.revoke_hermes_capability(
        project_id=project.project_id,
        jti="missing-jti",
        expires_at=int(instant.timestamp()) + 120,
    )

    with sqlite3.connect(store.database_path(project.project_id)) as connection:
        rows = connection.execute("SELECT jti FROM hermes_capability_ledger ORDER BY jti").fetchall()
    assert rows == []


def test_sqlite_concurrent_registered_hermes_capability_consumption_has_one_winner(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Hermes concurrent SQLite ledger")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={"segments": [], "history": []},
    )
    store.register_hermes_run_capabilities(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        asset_index_revision=0,
        capabilities=(
            {
                "capability_id": "concurrent-jti",
                "action": "read_context",
                "expires_at": 1_900_000_000,
            },
            {
                "capability_id": "publish-jti",
                "action": "publish_proposal",
                "expires_at": 1_900_000_000,
            },
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: store.consume_registered_hermes_capability(
                    project_id=project.project_id,
                    capability_id="concurrent-jti",
                    conversation_id="conversation-1",
                    run_id="run-1",
                    session_id=session["session_id"],
                    session_revision=session["session_revision"],
                    asset_index_revision=0,
                    action="read_context",
                ),
                range(2),
            )
        )

    assert sorted(results) == ["accepted", "hermes_capability_replayed"]


def test_postgres_concurrent_registered_hermes_capability_consumption_has_one_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"Hermes concurrent ledger {uuid4().hex}")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline-1",
        session_payload={"segments": [], "history": []},
    )
    store.register_hermes_run_capabilities(
        project_id=project.project_id,
        conversation_id="conversation-1",
        run_id="run-1",
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        asset_index_revision=0,
        capabilities=(
            {
                "capability_id": "concurrent-jti",
                "action": "read_context",
                "expires_at": 1_900_000_000,
            },
            {
                "capability_id": "publish-jti",
                "action": "publish_proposal",
                "expires_at": 1_900_000_000,
            },
        ),
    )

    results = _run_two_requests_at_same_insert(
        statement_marker="BEGIN",
        request=lambda: {
            "state": store.consume_registered_hermes_capability(
                project_id=project.project_id,
                capability_id="concurrent-jti",
                conversation_id="conversation-1",
                run_id="run-1",
                session_id=session["session_id"],
                session_revision=session["session_revision"],
                asset_index_revision=0,
                action="read_context",
            )
        },
    )

    assert sorted(item["state"] for item in results) == [
        "accepted",
        "hermes_capability_replayed",
    ]


def test_postgres_concurrent_same_scope_hermes_capability_registration_has_one_pair(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    instant = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    store = PostgresProjectStore(
        tmp_path,
        database_url=postgres_url,
        now=lambda: instant,
    )
    project = store.bootstrap_project(
        f"Hermes concurrent registration {uuid4().hex}"
    )
    prefix = uuid4().hex
    barrier = Barrier(2)
    original_execute = _PostgresConnection.execute

    def gate_begin(self, statement: str, parameters=None):
        if statement.strip() == "BEGIN":
            barrier.wait(timeout=10)
        return original_execute(self, statement, parameters)

    def register(index: int) -> str:
        try:
            store.register_hermes_run_capabilities(
                project_id=project.project_id,
                conversation_id="conversation-1",
                run_id="run-1",
                session_id="session-1",
                session_revision=3,
                asset_index_revision=7,
                capabilities=(
                    {
                        "capability_id": f"{prefix}-{index}-read",
                        "action": "read_context",
                        "expires_at": int(instant.timestamp()) + 300,
                    },
                    {
                        "capability_id": f"{prefix}-{index}-publish",
                        "action": "publish_proposal",
                        "expires_at": int(instant.timestamp()) + 300,
                    },
                ),
            )
        except ValueError as exc:
            assert str(exc) == "hermes_capability_registration_conflict"
            return "conflict"
        return "accepted"

    try:
        with patch.object(_PostgresConnection, "execute", gate_begin):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(register, range(2)))

        connection = store._connection(project.project_id)
        try:
            rows = connection.execute(
                """
                SELECT jti, action FROM hermes_capability_ledger
                WHERE project_id = ?
                  AND lifecycle_version = 'videobox.yujin-capability.v1'
                ORDER BY action
                """,
                (project.project_id,),
            ).fetchall()
            audit_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM hermes_capability_audit
                WHERE project_id = ?
                  AND reason = 'hermes_capability_registered'
                """,
                (project.project_id,),
            ).fetchone()["count"]
        finally:
            connection.close()
        assert sorted(results) == ["accepted", "conflict"]
        assert len(rows) == 2
        assert {row["action"] for row in rows} == {
            "read_context",
            "publish_proposal",
        }
        assert audit_count == 2
    finally:
        _cleanup_postgres_hermes_project(store, project.project_id)


def test_postgres_concurrent_creation_brief_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent brief {uuid4().hex}")
    script = tmp_path / "same.txt"
    script.write_text("동일한 클릭은 하나의 brief만 만들어야 합니다.", encoding="utf-8")
    script_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.SCRIPT_DOCUMENT,
        source_path=script,
    )
    payload = {
        "project_id": project.project_id,
        "script_filename": "same.txt",
        "script_text": "동일한 클릭은 하나의 brief만 만들어야 합니다.",
        "idempotency_key": "same-click",
        "capability_profile": {},
        "script_asset_id": script_asset.asset_id,
        "runtime": type("NoQuestions", (), {"plan_questions": lambda *_args, **_kwargs: []})(),
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO creation_briefs",
        request=lambda: store.create_creation_brief(**payload),
    )

    assert {result["brief_id"] for result in results}.__len__() == 1
    assert len(store.list_creation_briefs(project_id=project.project_id)) == 1


def test_postgres_concurrent_readiness_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent readiness {uuid4().hex}")
    brief = _approve_postgres_brief(store, project.project_id)
    payload = {
        "project_id": project.project_id,
        "brief_id": brief["brief_id"],
        "narration_choice": {"kind": "silent"},
        "idempotency_key": "same-click",
        "expected_brief_revision": brief["revision"],
        "defer": False,
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO draft_readiness",
        request=lambda: store.start_draft_readiness(**payload),
    )

    assert {result["readiness_id"] for result in results}.__len__() == 1
    assert len(store.list_draft_readiness(project_id=project.project_id)) == 1


def test_postgres_concurrent_atomic_bundle_reuses_one_idempotency_winner(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL concurrent bundle {uuid4().hex}")
    brief = _approve_postgres_brief(store, project.project_id)
    readiness = store.start_draft_readiness(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        narration_choice={"kind": "silent"},
        idempotency_key="ready",
        expected_brief_revision=brief["revision"],
        defer=False,
    )
    payload = {
        "project_id": project.project_id,
        "brief_id": brief["brief_id"],
        "expected_brief_revision": brief["revision"],
        "readiness_id": readiness["readiness_id"],
        "expected_readiness_revision": readiness["revision"],
        "idempotency_key": "same-click",
        "allow_placeholder": True,
    }

    results = _run_two_requests_at_same_insert(
        statement_marker="INSERT INTO atomic_draft_bundles",
        request=lambda: store.materialize_atomic_draft_bundle(**payload),
    )

    assert {result["bundle_id"] for result in results}.__len__() == 1
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1


def test_api_selects_postgres_store_when_database_url_is_configured(
    monkeypatch, tmp_path: Path, postgres_url: str
) -> None:
    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", postgres_url)

    with TestClient(create_app(projects_root=tmp_path)) as client:
        assert isinstance(client.app.state.store, PostgresProjectStore)
        created = client.post("/api/projects", json={"name": f"API PostgreSQL project {uuid4().hex}"})
        listed = client.get("/api/projects")

    assert created.status_code == 201
    assert created.json()["project_id"] in {item["project_id"] for item in listed.json()["projects"]}


def test_postgres_store_persists_existing_project_asset_and_timeline_mutation(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL mutation project {uuid4().hex}")
    source_audio = tmp_path / "existing-project-narration.wav"
    source_audio.write_bytes(b"narration bytes")

    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=source_audio,
        metadata={"source": "postgres-integration"},
    )
    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    updated = store.update_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
        timeline_payload={
            **saved,
            "version": "v002",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )
    fetched = store.get_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"])

    assert (tmp_path / "projects" / project.project_id / "inputs" / "narration" / source_audio.name).read_bytes() == b"narration bytes"
    assert updated["version"] == "v002"
    assert fetched["tracks"][0]["clips"][0]["asset_id"] == asset.asset_id
    assert fetched["summary"]["track_count"] == 1


def test_postgres_restart_reconciliation_preserves_batch_destination_registered_in_postgres_despite_stale_sqlite(
    tmp_path: Path, postgres_url: str
) -> None:
    root = tmp_path / "projects"
    store = PostgresProjectStore(root, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL reconciliation project {uuid4().hex}")
    source = tmp_path / "registered.mp4"
    source.write_bytes(b"registered-by-postgres")
    registered = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    destination = store.resolve_storage_uri(project_id=project.project_id, storage_uri=registered.storage_uri)
    operations = store.project_root(project.project_id) / ".batch-director-operations"
    stage = operations / "op-postgres-authority" / "stage.mp4"
    stage.parent.mkdir(parents=True)
    stage.write_bytes(b"discarded-stage")
    (store.project_root(project.project_id) / "db").mkdir(exist_ok=True)
    stale_sqlite = store.database_path(project.project_id)
    with sqlite3.connect(stale_sqlite) as stale_connection:
        stale_connection.execute("CREATE TABLE assets (asset_id TEXT, project_id TEXT, storage_uri TEXT)")
        stale_connection.execute(
            "INSERT INTO assets (asset_id, project_id, storage_uri) VALUES (?, ?, ?)",
            ("stale-asset", project.project_id, "local://projects/stale/assets/imported/other.mp4"),
        )
    manifest = operations / "op-postgres-authority.json"
    manifest.write_text(
        json.dumps(
            {
                "operation_id": "op-postgres-authority",
                "status": "staging",
                "entries": [
                    {
                        "staged_path": str(stage),
                        "destination_path": str(destination),
                        "sha256": sha256(destination.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    PostgresProjectStore(root, database_url=postgres_url)

    assert destination.read_bytes() == b"registered-by-postgres"
    assert not stage.exists()
    assert not manifest.exists()


def test_postgres_store_scopes_identical_timeline_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first timeline project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second timeline project {uuid4().hex}")

    first_timeline = store.save_timeline_run(
        project_id=first_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )
    second_timeline = store.save_timeline_run(
        project_id=second_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )

    assert first_timeline["timeline_id"] == second_timeline["timeline_id"] == "timeline_001"
    assert store.get_timeline_run(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"]
    )["project_id"] == first_project.project_id
    assert store.get_timeline_run(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"]
    )["project_id"] == second_project.project_id
    assert store._list_timeline_ids(project_id=first_project.project_id) == ["timeline_001"]
    assert store._list_timeline_ids(project_id=second_project.project_id) == ["timeline_001"]


def test_postgres_store_scopes_identical_session_and_export_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first scoped IDs project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second scoped IDs project {uuid4().hex}")

    def save_timeline(project_id: str) -> dict:
        return store.save_timeline_run(
            project_id=project_id,
            output_mode="review",
            timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
        )

    first_timeline = save_timeline(first_project.project_id)
    second_timeline = save_timeline(second_project.project_id)
    first_session = store.save_editing_session(
        project_id=first_project.project_id,
        timeline_id=first_timeline["timeline_id"],
        session_payload={"caption_style": "first", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    second_session = store.save_editing_session(
        project_id=second_project.project_id,
        timeline_id=second_timeline["timeline_id"],
        session_payload={"caption_style": "second", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    assert first_session["session_id"] == second_session["session_id"] == "editing_session_001"

    store.update_editing_session(
        project_id=first_project.project_id,
        session_id=first_session["session_id"],
        session_payload={"caption_style": "first-updated", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
        expected_revision=1,
    )
    assert store.get_editing_session(project_id=first_project.project_id, session_id=first_session["session_id"])["caption_style"] == "first-updated"
    assert store.get_editing_session(project_id=second_project.project_id, session_id=second_session["session_id"])["caption_style"] == "second"

    first_source = tmp_path / "first-draft"
    second_source = tmp_path / "second-draft"
    first_source.mkdir()
    second_source.mkdir()
    (first_source / "draft.txt").write_text("first", encoding="utf-8")
    (second_source / "draft.txt").write_text("second", encoding="utf-8")
    first_export = store.save_capcut_draft_export(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"], source_draft_path=first_source
    )
    second_export = store.save_capcut_draft_export(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"], source_draft_path=second_source
    )
    assert first_export["export_id"] == second_export["export_id"] == "export_001"

    store.update_capcut_draft_handoff(
        project_id=first_project.project_id, export_id=first_export["export_id"], handoff={"owner": "first"}
    )
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["handoff"] is None
    store._prune_old_exports(project_id=first_project.project_id, export_type="capcut_draft_export", keep_last=0)
    with pytest.raises(KeyError):
        store.get_capcut_draft_export(project_id=first_project.project_id, export_id=first_export["export_id"])
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["export_id"] == "export_001"


def test_postgres_store_scopes_assets_collections_and_jobs_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first operational scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second operational scope project {uuid4().hex}")
    first_source = tmp_path / "first.wav"
    second_source = tmp_path / "second.wav"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first_asset = store.register_asset(project_id=first_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=first_source)
    second_asset = store.register_asset(project_id=second_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=second_source)

    assert [item["asset_id"] for item in store.list_assets(project_id=first_project.project_id)] == [first_asset.asset_id]
    with pytest.raises(KeyError):
        store.get_asset(project_id=second_project.project_id, asset_id=first_asset.asset_id)
    store.update_asset_metadata(project_id=first_project.project_id, asset_id=first_asset.asset_id, metadata_patch={"owner": "first"})
    assert store.get_asset(project_id=second_project.project_id, asset_id=second_asset.asset_id)["metadata"] == {}

    for project, asset, suffix in ((first_project, first_asset, "first"), (second_project, second_asset, "second")):
        store._execute(
            project.project_id,
            "INSERT INTO segments (segment_id, project_id, text) VALUES (?, ?, ?)",
            (f"segment_{suffix}", project.project_id, suffix),
        )
        store._execute(
            project.project_id,
            "INSERT INTO recommendations (recommendation_id, project_id, recommendation_type, auto_apply_allowed, review_required, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"recommendation_{suffix}", project.project_id, "broll", 0, 0, "2026-07-19T00:00:00+00:00"),
        )

    assert [item["segment_id"] for item in store.list_segments(project_id=first_project.project_id)] == ["segment_first"]
    assert [item["recommendation_id"] for item in store.list_recommendation_rows(project_id=second_project.project_id)] == ["recommendation_second"]

    first_job = store.create_job(project_id=first_project.project_id, job_type=JobType.TIMELINE_BUILD)
    second_job = store.create_job(project_id=second_project.project_id, job_type=JobType.TIMELINE_BUILD)
    assert first_job["job_id"] == second_job["job_id"] == "timeline_build_job_001"
    store.update_job(project_id=first_project.project_id, job_id=first_job["job_id"], status=JobStatus.SUCCEEDED)
    assert store.get_job(project_id=second_project.project_id, job_id=second_job["job_id"])["status"] == JobStatus.PENDING.value
    assert [item["job_id"] for item in store.list_jobs(project_id=first_project.project_id)] == [first_job["job_id"]]


def test_postgres_store_scopes_tts_candidates_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first provider scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second provider scope project {uuid4().hex}")
    accepted = SimpleNamespace(technical_status="accepted", operator_review_status="pending")
    first_candidate = store.save_tts_candidate(
        project_id=first_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="first", acceptance=accepted
    )
    second_candidate = store.save_tts_candidate(
        project_id=second_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="second", acceptance=accepted
    )
    assert first_candidate["candidate_id"] == second_candidate["candidate_id"] == "tts_candidate_001"
    store.update_tts_candidate_listening_review(
        project_id=first_project.project_id, candidate_id=first_candidate["candidate_id"], decision="approved"
    )
    assert store.get_tts_candidate(project_id=second_project.project_id, candidate_id=second_candidate["candidate_id"])["operator_review_status"] == "pending"
    assert [item["candidate_id"] for item in store.list_tts_candidates(project_id=first_project.project_id, segment_id="segment_001")] == ["tts_candidate_001"]


def test_postgres_yujin_tts_terminal_attestation_rolls_back_after_asset_bytes_change(
    tmp_path: Path,
    postgres_url: str,
) -> None:
    store = PostgresProjectStore(
        tmp_path / "postgres-yujin-tts",
        database_url=postgres_url,
    )
    project = store.bootstrap_project(
        f"PostgreSQL Yujin TTS CAS {uuid4().hex}"
    )
    project_id = project.project_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=f"timeline-{uuid4().hex}",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "unchanged",
                "start_sec": 0.0,
                "end_sec": 1.0,
            }],
            "history": [],
        },
    )
    source = tmp_path / f"tts-{uuid4().hex}.wav"
    original_bytes = b"postgres-approved-generated-tts"
    source.write_bytes(original_bytes)
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.GENERATED_TTS_AUDIO,
        source_path=source,
    )
    acceptance = SimpleNamespace(
        technical_status="accepted",
        operator_review_status="approved",
        target_duration_sec=1.0,
        actual_duration_sec=1.0,
        failure_code=None,
    )
    tts_candidate = store.save_tts_candidate(
        project_id=project_id,
        segment_id="seg",
        asset_id=asset.asset_id,
        source_text="approved voice",
        acceptance=acceptance,
    )
    proposal_candidate = DirectorCandidate(
        candidate_id=f"voice-operation-{uuid4().hex}",
        visible_reference_code="P00-VOICE-01",
        media_type="voice",
        asset_id=asset.asset_id,
        library_asset_id=None,
        reason_chips=("voice",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "candidate_id": tts_candidate["candidate_id"],
            "asset_id": asset.asset_id,
        },
        expected_content_sha256=sha256(original_bytes).hexdigest(),
        media_revision=asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "voice",
            "yujin_actionable_operation": True,
            "command_kind": "apply_tts_candidate",
            "candidate_id": tts_candidate["candidate_id"],
            "source_media_kind": "generated_tts_audio",
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id=f"proposal-{uuid4().hex}",
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session["session_id"],
        target_segment_ids=("seg",),
        source_script_segment_ids=("seg",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(proposal_candidate,),
    )
    store.save_director_proposal(project_id, proposal)
    before = deepcopy(store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ))
    updated = select_segment_tts_replacement(
        session=before,
        segment_id="seg",
        recommendation_id=tts_candidate["candidate_id"],
        asset_id=asset.asset_id,
    )
    stored_asset = store.get_asset(
        project_id=project_id,
        asset_id=asset.asset_id,
    )
    stored_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=stored_asset["storage_uri"],
    )
    stored_path.write_bytes(b"tampered-after-proposal")

    with pytest.raises(
        EditingSessionRevisionConflict,
        match="attestation changed",
    ):
        store.update_yujin_b4_command_transaction(
            project_id=project_id,
            session_id=session["session_id"],
            proposal_id=proposal.proposal_id,
            candidate_id=proposal_candidate.candidate_id,
            command_kind="apply_tts_candidate",
            segment_id="seg",
            controls={
                "candidate_id": tts_candidate["candidate_id"],
                "asset_id": asset.asset_id,
            },
            session_payload=updated,
            expected_revision=session["session_revision"],
        )

    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
