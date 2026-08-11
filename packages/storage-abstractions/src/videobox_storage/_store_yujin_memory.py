"""유진 기억(memory) 갈래 -- 후보 생성·승인·저장·삭제와 그 감사 기록.

`local_project_store.py`에서 **그대로** 떼어 온 코드다. 동작은 한 줄도 바꾸지 않았다.
`LocalProjectStore`가 이 mixin을 상속하므로, 여기 있는 메서드는 base가 쥔
`_clock` / `_connection` / `_fetchall` / `_now_iso` 넷을 그대로 쓴다 -- 전부 `self.`
조회라 MRO가 흡수한다. 지금까지 뗀 세 갈래 중 외부 의존이 가장 적다.

별도 모듈 + 위임이 아니라 mixin인 이유는 앞의 둘과 같다
(`_store_hermes_capability.py` 문서 참고). 게다가 이 갈래는 base가 역참조한다 --
스키마 준비 코드가 `_ensure_yujin_memory_operation_columns`를 부른다. 모듈로 떼면
순환 import가 되고, 위임으로 바꾸면 인스턴스에 monkeypatch 하는 테스트와
`PostgresProjectStore._connection` 재정의가 조용히 깨진다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from videobox_core_engine.yujin_memory_policy import validate_yujin_memory_candidate

# 이 갈래에서만 쓴다. base에서 함께 옮겨 왔고 base가 여기서 다시 가져간다.
YUJIN_MEMORY_STORE_CLAIM_LEASE_SECONDS = 60


def _director_exchange_was_blocked(metadata_json: object) -> bool:
    """Did this local turn fail?  Unreadable metadata counts as blocked.

    A reply the owner never actually received must not become the source of a
    saved memory, so anything we cannot confirm as good is treated as bad.
    """
    if metadata_json is None:
        return True
    if isinstance(metadata_json, dict):
        return str(metadata_json.get("status") or "") == "blocked"
    try:
        parsed = json.loads(metadata_json)
    except (TypeError, ValueError):
        return True
    return isinstance(parsed, dict) and str(parsed.get("status") or "") == "blocked"


class YujinMemoryMixin:
    """유진이 기억을 제안·승인·저장·삭제하는 갈래."""

    def _yujin_memory_candidate_payload(
        self,
        row: Any,
    ) -> dict[str, Any]:
        status = str(row["status"])
        storage_status = str(row["storage_status"])
        if status not in {"pending", "approved", "rejected"}:
            raise ValueError("memory_candidate_consent_status_invalid")
        expired_pre_call_claim = False
        if (
            storage_status == "claimed"
            and row["write_claim_token"] is not None
        ):
            try:
                claimed_at = datetime.fromisoformat(
                    str(row["write_claimed_at"])
                )
                expired_pre_call_claim = (
                    self._clock().astimezone(UTC)
                    >= claimed_at.astimezone(UTC)
                    + timedelta(
                        seconds=YUJIN_MEMORY_STORE_CLAIM_LEASE_SECONDS
                    )
                )
            except (TypeError, ValueError):
                expired_pre_call_claim = False
        return {
            "candidate_id": str(row["candidate_id"]),
            "project_id": str(row["project_id"]),
            "conversation_id": str(row["conversation_id"]),
            "client_request_id": str(row["client_request_id"]),
            "source_message_ids": tuple(
                str(value)
                for value in json.loads(str(row["source_message_ids_json"]))
            ),
            "memory_scope": str(row["memory_scope"]),
            "category": str(row["category"]),
            "proposed_text": str(row["proposed_text"]),
            "status": status,
            "storage_status": storage_status,
            "retryable": expired_pre_call_claim
            or storage_status
            in {"event_pending", "failed_retryable", "ambiguous"},
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _validate_yujin_memory_source_ids(
        source_message_ids: tuple[str, ...],
    ) -> None:
        if (
            not 1 <= len(source_message_ids) <= 8
            or len(set(source_message_ids)) != len(source_message_ids)
            or any(
                not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value)
                is None
                for value in source_message_ids
            )
        ):
            raise ValueError("memory_candidate_source_ids_invalid")

    @staticmethod
    def _yujin_memory_request_fingerprint(
        *,
        conversation_id: str,
        source_message_ids: tuple[str, ...],
        memory_scope: str,
        category: str,
        proposed_text: str,
    ) -> str:
        canonical = json.dumps(
            {
                "category": category,
                "conversation_id": conversation_id,
                "memory_scope": memory_scope,
                "proposed_text": proposed_text,
                "source_message_ids": source_message_ids,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _lock_yujin_memory_candidate(
        connection: Any,
        *,
        project_id: str,
        candidate_id: str,
    ) -> Any:
        suffix = (
            ""
            if isinstance(connection, sqlite3.Connection)
            else " FOR UPDATE"
        )
        return connection.execute(
            "SELECT * FROM yujin_memory_candidates "
            "WHERE project_id = ? AND candidate_id = ?" + suffix,
            (project_id, candidate_id),
        ).fetchone()

    @staticmethod
    def _append_yujin_memory_audit(
        connection: Any,
        *,
        candidate_id: str,
        project_id: str,
        action: str,
        status: str,
        occurred_at: str,
    ) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(event_order), 0) + 1 AS next_event_order "
            "FROM yujin_memory_candidate_audit "
            "WHERE project_id = ? AND candidate_id = ?",
            (project_id, candidate_id),
        ).fetchone()
        event_order = int(row["next_event_order"])
        connection.execute(
            """
            INSERT INTO yujin_memory_candidate_audit (
                audit_event_id, candidate_id, project_id,
                event_order, action, status, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"memory-audit-{uuid.uuid4().hex}",
                candidate_id,
                project_id,
                event_order,
                action,
                status,
                occurred_at,
            ),
        )

    @staticmethod
    def _append_yujin_memory_operation_audit(
        connection: Any,
        *,
        candidate_id: str,
        project_id: str,
        action: str,
        storage_status: str,
        occurred_at: str,
    ) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(event_order), 0) + 1 "
            "AS next_event_order "
            "FROM yujin_memory_operation_audit "
            "WHERE project_id = ? AND candidate_id = ?",
            (project_id, candidate_id),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO yujin_memory_operation_audit (
                operation_audit_id, candidate_id, project_id,
                event_order, action, storage_status, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"memory-operation-audit-{uuid.uuid4().hex}",
                candidate_id,
                project_id,
                int(row["next_event_order"]),
                action,
                storage_status,
                occurred_at,
            ),
        )

    def get_yujin_memory_source_texts(
        self,
        *,
        project_id: str,
        conversation_id: str,
        source_message_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        self._validate_yujin_memory_source_ids(source_message_ids)
        connection = self._connection(project_id)
        try:
            conversation = connection.execute(
                "SELECT conversation_id FROM director_conversations "
                "WHERE project_id = ? AND conversation_id = ?",
                (project_id, conversation_id),
            ).fetchone()
            if conversation is None:
                raise KeyError("yujin_memory_source_missing")
            rows = self._completed_yujin_memory_source_rows(
                connection,
                project_id=project_id,
                conversation_id=conversation_id,
                source_message_ids=source_message_ids,
            )
            return tuple(str(row["text"]) for row in rows)
        finally:
            connection.close()

    @staticmethod
    def _completed_yujin_memory_source_rows(
        connection: Any,
        *,
        project_id: str,
        conversation_id: str,
        source_message_ids: tuple[str, ...],
    ) -> list[Any]:
        placeholders = ",".join("?" for _ in source_message_ids)
        rows = connection.execute(
            """
            SELECT message.message_id, message.text, message.message_order,
                   -- "Is this message owned by a completed run", not "what is
                   -- the status of whichever owning row we read first".  With
                   -- LIMIT 1 an unrelated non-completed row could veto a
                   -- message its own completed run already earned, and which
                   -- row won would depend on storage order.
                   (
                     SELECT MAX(CASE WHEN run.status = 'completed' THEN 1 ELSE 0 END)
                     FROM director_hermes_runs AS run
                     WHERE run.project_id = message.project_id
                       AND run.conversation_id = message.conversation_id
                       AND (
                         run.user_message_id = message.message_id
                         OR run.assistant_message_id = message.message_id
                       )
                   ) AS has_completed_run,
                   (
                     SELECT reply.metadata_json
                     FROM director_messages AS reply
                     WHERE reply.project_id = message.project_id
                       AND reply.conversation_id = message.conversation_id
                       AND reply.role = 'assistant'
                       AND reply.message_order = (
                         CASE WHEN message.role = 'user'
                              THEN message.message_order + 1
                              ELSE message.message_order END
                       )
                     LIMIT 1
                   ) AS exchange_metadata_json
            FROM director_messages AS message
            WHERE message.project_id = ?
              AND message.conversation_id = ?
              AND message.message_id IN ("""
            + placeholders
            + """)
              AND (
                EXISTS (
                  SELECT 1
                  FROM director_hermes_runs AS run
                  WHERE run.project_id = message.project_id
                    AND run.conversation_id = message.conversation_id
                    AND run.status = 'completed'
                    AND (
                      run.user_message_id = message.message_id
                      OR run.assistant_message_id = message.message_id
                    )
                )
                -- The local-first route (the one the editor screen calls) has
                -- no run object at all, so a run-only rule locked the owner
                -- out of saving a memory from a conversation they actually
                -- had.  A completed local turn is the request/response pair
                -- written by append_director_exchange: the user row carries a
                -- client_message_id and its assistant row is not blocked.
                -- A bare append_director_message stays excluded -- it has no
                -- client_message_id and belongs to no turn.
                OR EXISTS (
                  SELECT 1
                  FROM director_messages AS pair
                  WHERE pair.conversation_id = message.conversation_id
                    AND pair.project_id = message.project_id
                    -- A message any run owns is judged by that run's status
                    -- above, never by this branch.  Otherwise a pending,
                    -- blocked or interrupted run would qualify here purely
                    -- because its two rows sit next to each other.
                    AND NOT EXISTS (
                      SELECT 1
                      FROM director_hermes_runs AS owning
                      WHERE owning.conversation_id = message.conversation_id
                        AND owning.project_id = message.project_id
                        AND (
                          owning.user_message_id IN (message.message_id, pair.message_id)
                          OR owning.assistant_message_id IN (message.message_id, pair.message_id)
                        )
                    )
                    AND (
                      (
                        message.role = 'user'
                        AND message.client_message_id IS NOT NULL
                        AND pair.role = 'assistant'
                        AND pair.message_order = message.message_order + 1
                      )
                      OR (
                        message.role = 'assistant'
                        AND pair.role = 'user'
                        AND pair.client_message_id IS NOT NULL
                        AND pair.message_order = message.message_order - 1
                      )
                    )
                )
              )
            ORDER BY message.message_order, message.message_id
            """,
            (project_id, conversation_id, *source_message_ids),
        ).fetchall()
        # The "was this turn blocked?" test reads JSON, and the two backends
        # spell that differently (SQLite json_extract vs PostgreSQL ->>).  The
        # SQL stays dialect-free and Python decides.
        rows = [
            row
            for row in rows
            if int(row["has_completed_run"] or 0) == 1
            or not _director_exchange_was_blocked(row["exchange_metadata_json"])
        ]
        if len(rows) != len(source_message_ids):
            raise KeyError("yujin_memory_source_missing")
        return rows

    def create_yujin_memory_candidate(
        self,
        *,
        project_id: str,
        conversation_id: str,
        client_request_id: str,
        source_message_ids: tuple[str, ...],
        memory_scope: str,
        category: str,
        proposed_text: str,
    ) -> dict[str, Any]:
        self._validate_yujin_memory_source_ids(source_message_ids)
        if (
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                client_request_id,
            )
            is None
        ):
            raise ValueError("memory_candidate_request_id_invalid")
        if memory_scope != "creator":
            raise ValueError("memory_candidate_scope_unsupported")
        if category not in {"pacing", "caption", "audio", "tone", "workflow"}:
            raise ValueError("memory_candidate_category_unsupported")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if not isinstance(connection, sqlite3.Connection):
                connection.execute(
                    "LOCK TABLE yujin_memory_candidates "
                    "IN SHARE ROW EXCLUSIVE MODE"
                )
            conversation = connection.execute(
                "SELECT conversation_id FROM director_conversations "
                "WHERE project_id = ? AND conversation_id = ?",
                (project_id, conversation_id),
            ).fetchone()
            if conversation is None:
                raise KeyError("yujin_memory_source_missing")
            source_rows = self._completed_yujin_memory_source_rows(
                connection,
                project_id=project_id,
                conversation_id=conversation_id,
                source_message_ids=source_message_ids,
            )
            canonical_source_message_ids = tuple(
                str(row["message_id"]) for row in source_rows
            )
            proposed_text = validate_yujin_memory_candidate(
                category=category,
                proposed_text=proposed_text,
                source_texts=tuple(
                    str(row["text"]) for row in source_rows
                ),
            )
            fingerprint = self._yujin_memory_request_fingerprint(
                conversation_id=conversation_id,
                source_message_ids=canonical_source_message_ids,
                memory_scope=memory_scope,
                category=category,
                proposed_text=proposed_text,
            )
            existing = connection.execute(
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? AND conversation_id = ? "
                "AND client_request_id = ?",
                (project_id, conversation_id, client_request_id),
            ).fetchone()
            if existing is not None:
                if str(existing["request_fingerprint"]) != fingerprint:
                    raise ValueError("memory_candidate_request_conflict")
                connection.commit()
                return self._yujin_memory_candidate_payload(existing)

            candidate_id = f"memory-candidate-{uuid.uuid4().hex}"
            now = self._now_iso()
            connection.execute(
                """
                INSERT INTO yujin_memory_candidates (
                    candidate_id, project_id, conversation_id,
                    client_request_id, request_fingerprint,
                    source_message_ids_json, memory_scope, category,
                    proposed_text, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    candidate_id,
                    project_id,
                    conversation_id,
                    client_request_id,
                    fingerprint,
                    json.dumps(
                        canonical_source_message_ids,
                        ensure_ascii=True,
                    ),
                    memory_scope,
                    category,
                    proposed_text,
                    now,
                    now,
                ),
            )
            self._append_yujin_memory_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="create",
                status="pending",
                occurred_at=now,
            )
            row = connection.execute(
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            connection.commit()
            return self._yujin_memory_candidate_payload(row)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_yujin_memory_candidates(
        self,
        *,
        project_id: str,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if conversation_id is None:
            rows = self._fetchall(
                project_id,
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? "
                "ORDER BY created_at DESC, candidate_id DESC LIMIT 100",
                (project_id,),
            )
        else:
            connection = self._connection(project_id)
            try:
                conversation = connection.execute(
                    "SELECT conversation_id FROM director_conversations "
                    "WHERE project_id = ? AND conversation_id = ?",
                    (project_id, conversation_id),
                ).fetchone()
                if conversation is None:
                    raise KeyError(
                        "memory_candidate_conversation_missing"
                    )
                rows = connection.execute(
                    "SELECT * FROM yujin_memory_candidates "
                    "WHERE project_id = ? AND conversation_id = ? "
                    "ORDER BY created_at DESC, candidate_id DESC LIMIT 100",
                    (project_id, conversation_id),
                ).fetchall()
            finally:
                connection.close()
        return [self._yujin_memory_candidate_payload(row) for row in rows]

    def list_yujin_memory_retrieval_rows(
        self,
        *,
        project_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        """Return private approved+stored rows for one owned conversation."""

        connection = self._connection(project_id)
        try:
            conversation = connection.execute(
                "SELECT conversation_id FROM director_conversations "
                "WHERE project_id = ? AND conversation_id = ?",
                (project_id, conversation_id),
            ).fetchone()
            if conversation is None:
                return []
            rows = connection.execute(
                """
                SELECT candidate_id, project_id, conversation_id, status,
                       storage_status, provider_memory_ref AS memory_ref,
                       external_ref, proposed_text AS text, category
                FROM yujin_memory_candidates
                WHERE project_id = ? AND conversation_id = ?
                  AND status = 'approved' AND storage_status = 'stored'
                  AND provider_memory_ref IS NOT NULL
                  AND external_ref IS NOT NULL
                ORDER BY category, proposed_text, candidate_id
                LIMIT 100
                """,
                (project_id, conversation_id),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def transition_yujin_memory_candidate(
        self,
        *,
        project_id: str,
        candidate_id: str,
        action: Literal["approve", "reject"],
    ) -> dict[str, Any]:
        if action not in {"approve", "reject"}:
            raise ValueError("memory_candidate_action_invalid")
        target = "approved" if action == "approve" else "rejected"
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            current = str(row["status"])
            if current == target:
                connection.commit()
                return self._yujin_memory_candidate_payload(row)
            if current != "pending":
                raise ValueError("memory_candidate_terminal_conflict")
            now = self._now_iso()
            updated = connection.execute(
                "UPDATE yujin_memory_candidates "
                "SET status = ?, updated_at = ? "
                "WHERE project_id = ? AND candidate_id = ? "
                "AND status = 'pending'",
                (target, now, project_id, candidate_id),
            )
            if updated.rowcount != 1:
                raise ValueError("memory_candidate_terminal_conflict")
            self._append_yujin_memory_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action=action,
                status=target,
                occurred_at=now,
            )
            result = connection.execute(
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            connection.commit()
            return self._yujin_memory_candidate_payload(result)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def claim_yujin_memory_store(
        self,
        *,
        project_id: str,
        candidate_id: str,
        client_request_id: str,
        claim_token: str,
    ) -> dict[str, Any]:
        if re.fullmatch(r"claim-[0-9a-f]{64}", claim_token) is None:
            raise ValueError("memory_store_claim_invalid")
        if (
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                client_request_id,
            )
            is None
        ):
            raise ValueError("memory_store_request_id_invalid")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            status = str(row["status"])
            storage_status = str(row["storage_status"])
            if storage_status == "deleted":
                raise ValueError("memory_candidate_deleted")
            if storage_status == "stored":
                connection.commit()
                return {
                    "action": "stored",
                    "candidate": self._yujin_memory_candidate_payload(row),
                    "storage_status": "stored",
                }
            if status != "approved":
                raise ValueError("memory_candidate_not_approved")
            same_request = (
                row["store_client_request_id"] is not None
                and str(row["store_client_request_id"])
                == client_request_id
                and storage_status != "not_requested"
            )
            recover_started_call = False
            claim_expired = False
            if row["write_claim_token"] is not None:
                try:
                    claimed_at = datetime.fromisoformat(
                        str(row["write_claimed_at"])
                    )
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        "memory_candidate_store_in_progress"
                    ) from error
                claim_expired = (
                    self._clock()
                    >= claimed_at
                    + timedelta(
                        seconds=YUJIN_MEMORY_STORE_CLAIM_LEASE_SECONDS
                    )
                )
                recover_started_call = (
                    claim_expired
                    and row["provider_call_started_at"] is not None
                )
            if (
                same_request
                and not claim_expired
                and row["provider_memory_ref"] is None
            ):
                connection.commit()
                return {
                    "action": "replay",
                    "candidate": self._yujin_memory_candidate_payload(row),
                    "storage_status": storage_status,
                }
            if row["write_claim_token"] is not None:
                if not claim_expired:
                    raise ValueError(
                        "memory_candidate_store_in_progress"
                    )

            external_ref = (
                str(row["external_ref"])
                if row["external_ref"] is not None
                else "ext-"
                + hashlib.sha256(uuid.uuid4().bytes).hexdigest()
            )
            operation_id = (
                str(row["operation_id"])
                if row["operation_id"] is not None
                else "op-"
                + hashlib.sha256(uuid.uuid4().bytes).hexdigest()
            )
            now = self._now_iso()
            connection.execute(
                """
                UPDATE yujin_memory_candidates
                SET external_ref = ?, operation_id = ?,
                    store_client_request_id = ?,
                    write_claim_token = ?, write_claimed_at = ?,
                    provider_call_started_at = NULL,
                    attempt_count = attempt_count + 1,
                    storage_status = 'claimed', updated_at = ?
                WHERE project_id = ? AND candidate_id = ?
                """,
                (
                    external_ref,
                    operation_id,
                    client_request_id,
                    claim_token,
                    now,
                    now,
                    project_id,
                    candidate_id,
                ),
            )
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="claim",
                storage_status="claimed",
                occurred_at=now,
            )
            current = connection.execute(
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            connection.commit()
            if current["provider_memory_ref"] is not None:
                action = "finalize"
            elif current["provider_event_ref"] is not None:
                action = "reconcile"
            elif recover_started_call:
                action = "reconcile"
            elif storage_status == "ambiguous":
                action = "reconcile"
            else:
                action = "add"
            return {
                "action": action,
                "candidate": self._yujin_memory_candidate_payload(current),
                "text": str(current["proposed_text"]),
                "category": str(current["category"]),
                "external_ref": external_ref,
                "operation_id": operation_id,
                "event_ref": (
                    str(current["provider_event_ref"])
                    if current["provider_event_ref"] is not None
                    else None
                ),
            }
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_yujin_memory_store_call_started(
        self,
        *,
        project_id: str,
        candidate_id: str,
        claim_token: str,
    ) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            now = self._now_iso()
            updated = connection.execute(
                """
                UPDATE yujin_memory_candidates
                SET provider_call_started_at = ?, updated_at = ?
                WHERE project_id = ? AND candidate_id = ?
                  AND write_claim_token = ?
                  AND storage_status = 'claimed'
                """,
                (
                    now,
                    now,
                    project_id,
                    candidate_id,
                    claim_token,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("memory_store_claim_conflict")
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="call_started",
                storage_status="claimed",
                occurred_at=now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def record_yujin_memory_provider_outcome(
        self,
        *,
        project_id: str,
        candidate_id: str,
        claim_token: str,
        status: str,
        memory_ref: str | None,
        event_ref: str | None,
    ) -> None:
        if status not in {
            "stored",
            "event_pending",
            "failed_retryable",
            "ambiguous",
        }:
            raise ValueError("memory_write_outcome_invalid")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            if str(row["write_claim_token"] or "") != claim_token:
                raise ValueError("memory_store_claim_conflict")
            if status == "stored":
                if (
                    memory_ref is None
                    or re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}",
                        memory_ref,
                    )
                    is None
                    or event_ref is not None
                ):
                    raise ValueError("memory_write_outcome_invalid")
                provider_memory_ref = memory_ref
                provider_event_ref = None
                storage_status = "claimed"
            elif status == "event_pending":
                if (
                    event_ref is None
                    or re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}",
                        event_ref,
                    )
                    is None
                    or memory_ref is not None
                ):
                    raise ValueError("memory_write_outcome_invalid")
                provider_memory_ref = None
                provider_event_ref = event_ref
                storage_status = "event_pending"
            else:
                provider_memory_ref = None
                provider_event_ref = (
                    event_ref if status == "ambiguous" else None
                )
                storage_status = status
            now = self._now_iso()
            connection.execute(
                """
                UPDATE yujin_memory_candidates
                SET provider_memory_ref = ?, provider_event_ref = ?,
                    write_claim_token = NULL, write_claimed_at = NULL,
                    provider_call_started_at = NULL,
                    storage_status = ?, updated_at = ?
                WHERE project_id = ? AND candidate_id = ?
                """,
                (
                    provider_memory_ref,
                    provider_event_ref,
                    storage_status,
                    now,
                    project_id,
                    candidate_id,
                ),
            )
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="outcome",
                storage_status=storage_status,
                occurred_at=now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def finalize_yujin_memory_store(
        self,
        *,
        project_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            if str(row["storage_status"]) == "stored":
                connection.commit()
                return self._yujin_memory_candidate_payload(row)
            if (
                str(row["status"]) != "approved"
                or row["provider_memory_ref"] is None
            ):
                raise ValueError("memory_store_not_settled")
            now = self._now_iso()
            connection.execute(
                "UPDATE yujin_memory_candidates "
                "SET storage_status = 'stored', write_claim_token = NULL, "
                "write_claimed_at = NULL, provider_call_started_at = NULL, "
                "updated_at = ? "
                "WHERE project_id = ? AND candidate_id = ? "
                "AND status = 'approved' "
                "AND provider_memory_ref IS NOT NULL",
                (now, project_id, candidate_id),
            )
            self._append_yujin_memory_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="store",
                status="approved",
                occurred_at=now,
            )
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="finalize",
                storage_status="stored",
                occurred_at=now,
            )
            current = connection.execute(
                "SELECT * FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            connection.commit()
            return self._yujin_memory_candidate_payload(current)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def release_yujin_memory_store_claim(
        self,
        *,
        project_id: str,
        candidate_id: str,
        claim_token: str,
        storage_status: str = "failed_retryable",
        event_ref: str | None = None,
    ) -> None:
        if storage_status not in {"failed_retryable", "ambiguous"}:
            raise ValueError("memory_write_outcome_invalid")
        if event_ref is not None and re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", event_ref
        ) is None:
            raise ValueError("memory_write_outcome_invalid")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            now = self._now_iso()
            updated = connection.execute(
                """
                UPDATE yujin_memory_candidates
                SET write_claim_token = NULL, write_claimed_at = NULL,
                    provider_call_started_at = NULL,
                    storage_status = ?, provider_event_ref = ?
                WHERE project_id = ? AND candidate_id = ?
                  AND write_claim_token = ?
                """,
                (
                    storage_status,
                    event_ref,
                    project_id,
                    candidate_id,
                    claim_token,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("memory_store_claim_conflict")
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="release",
                storage_status=storage_status,
                occurred_at=now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_yujin_memory_store_state(
        self, *, project_id: str, candidate_id: str
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT candidate_id, status, storage_status "
                "FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            if row is None:
                raise KeyError("memory_candidate_missing")
            storage_status = str(row["storage_status"])
            return {
                "candidate_id": str(row["candidate_id"]),
                "status": str(row["status"]),
                "storage_status": storage_status,
                "retryable": storage_status
                in {
                    "event_pending",
                    "failed_retryable",
                    "ambiguous",
                },
            }
        finally:
            connection.close()

    def get_yujin_memory_private_mapping(
        self, *, project_id: str, candidate_id: str
    ) -> dict[str, str]:
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT status, storage_status, external_ref, "
                "provider_memory_ref FROM yujin_memory_candidates "
                "WHERE project_id = ? AND candidate_id = ?",
                (project_id, candidate_id),
            ).fetchone()
            if row is None:
                raise KeyError("memory_candidate_missing")
            if (
                str(row["status"]) != "approved"
                or str(row["storage_status"]) != "stored"
                or row["external_ref"] is None
                or row["provider_memory_ref"] is None
            ):
                raise ValueError("memory_candidate_not_stored")
            return {
                "external_ref": str(row["external_ref"]),
                "memory_ref": str(row["provider_memory_ref"]),
            }
        finally:
            connection.close()

    def mark_yujin_memory_delete_call_started(
        self, *, project_id: str, candidate_id: str
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            if (
                str(row["status"]) != "approved"
                or str(row["storage_status"]) != "stored"
                or row["external_ref"] is None
                or row["provider_memory_ref"] is None
            ):
                raise ValueError("memory_candidate_not_stored")
            prior = connection.execute(
                "SELECT 1 FROM yujin_memory_operation_audit "
                "WHERE project_id = ? AND candidate_id = ? "
                "AND action = 'call_started' "
                "AND storage_status = 'stored' LIMIT 1",
                (project_id, candidate_id),
            ).fetchone()
            allow_absent = prior is not None
            if not allow_absent:
                self._append_yujin_memory_operation_audit(
                    connection,
                    candidate_id=candidate_id,
                    project_id=project_id,
                    action="call_started",
                    storage_status="stored",
                    occurred_at=self._now_iso(),
                )
            connection.commit()
            return {
                "external_ref": str(row["external_ref"]),
                "memory_ref": str(row["provider_memory_ref"]),
                "allow_absent": allow_absent,
            }
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_yujin_memory_deleted(
        self, *, project_id: str, candidate_id: str
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._lock_yujin_memory_candidate(
                connection,
                project_id=project_id,
                candidate_id=candidate_id,
            )
            if row is None:
                raise KeyError("memory_candidate_missing")
            if str(row["storage_status"]) == "deleted":
                connection.commit()
                return self.get_yujin_memory_store_state(
                    project_id=project_id,
                    candidate_id=candidate_id,
                )
            if (
                str(row["status"]) != "approved"
                or str(row["storage_status"]) != "stored"
            ):
                raise ValueError("memory_candidate_not_stored")
            now = self._now_iso()
            updated = connection.execute(
                "UPDATE yujin_memory_candidates "
                "SET storage_status = 'deleted', "
                "provider_memory_ref = NULL, provider_event_ref = NULL, "
                "updated_at = ? "
                "WHERE project_id = ? AND candidate_id = ? "
                "AND status = 'approved' AND storage_status = 'stored'",
                (now, project_id, candidate_id),
            )
            if updated.rowcount != 1:
                raise ValueError("memory_delete_conflict")
            self._append_yujin_memory_operation_audit(
                connection,
                candidate_id=candidate_id,
                project_id=project_id,
                action="delete",
                storage_status="deleted",
                occurred_at=now,
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_yujin_memory_store_state(
            project_id=project_id,
            candidate_id=candidate_id,
        )

    def list_yujin_memory_operation_audit(
        self, *, project_id: str, candidate_id: str
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            project_id,
            """
            SELECT operation_audit_id, candidate_id, project_id,
                   event_order, action, storage_status, occurred_at
            FROM yujin_memory_operation_audit
            WHERE project_id = ? AND candidate_id = ?
            ORDER BY event_order
            """,
            (project_id, candidate_id),
        )
        return [dict(row) for row in rows]

    def list_yujin_memory_candidate_audit(
        self,
        *,
        project_id: str,
        candidate_id: str,
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            project_id,
            """
            SELECT audit_event_id, candidate_id, project_id, event_order,
                   action, status, occurred_at
            FROM yujin_memory_candidate_audit
            WHERE project_id = ? AND candidate_id = ?
            ORDER BY event_order
            """,
            (project_id, candidate_id),
        )
        return [dict(row) for row in rows]

