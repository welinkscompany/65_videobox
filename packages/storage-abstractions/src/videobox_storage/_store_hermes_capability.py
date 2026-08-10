"""Hermes 능력 원장(capability ledger) 갈래.

`local_project_store.py`에서 **그대로** 떼어 온 코드다. 동작은 한 줄도 바꾸지
않았다.  `LocalProjectStore`가 이 mixin을 상속하므로, 여기 있는 메서드는 base가
쥔 `_connection` / `_now_iso` / `_fetchone` / `_clock`을 그대로 쓴다.

별도 모듈 + 위임이 아니라 mixin인 이유: base의 `_connection`이
`_ensure_hermes_capability_lifecycle_schema`를 부르므로 분리하면 실제 import
순환이 생기고, 위임으로 바꾸면 인스턴스에 `_append_hermes_capability_audit`를
monkeypatch 하는 테스트와 `PostgresProjectStore._connection` 재정의가 조용히
깨진다.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from videobox_storage.sqlite_schema import (
    HERMES_CAPABILITY_LEDGER_SCHEMA_STATEMENT,
)

HERMES_CAPABILITY_DENIAL_REASONS = frozenset(
    {
        "hermes_capability_malformed",
        "hermes_capability_signature_invalid",
        "hermes_capability_key_unknown",
        "hermes_capability_expired",
        "hermes_capability_not_yet_valid",
        "hermes_capability_scope_forbidden",
        "hermes_capability_action_forbidden",
        "hermes_capability_replayed",
        "hermes_capability_revoked",
        "hermes_capability_unavailable",
    }
)
HERMES_AUTHORITY_ID_MAX_LENGTH = 255
HERMES_AUTHORITY_ID_PATTERN = re.compile(
    rf"[A-Za-z0-9][A-Za-z0-9._:-]{{0,{HERMES_AUTHORITY_ID_MAX_LENGTH - 1}}}\Z",
    re.ASCII,
)


class HermesCapabilityMixin:
    """Hermes 능력 원장의 등록·소비·폐기·감사 갈래."""

    def register_hermes_run_capabilities(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        capabilities: tuple[Mapping[str, Any], Mapping[str, Any]],
    ) -> None:
        normalized = self._validate_hermes_capability_registration(
            project_id=project_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
            capabilities=capabilities,
        )
        connection = self._connection(project_id)
        try:
            self._begin_hermes_capability_transaction(connection)
            now = self._now_iso()
            for capability in normalized:
                existing = connection.execute(
                    """
                    SELECT 1 FROM hermes_capability_ledger
                    WHERE project_id = ?
                      AND (
                          jti = ?
                          OR (
                              lifecycle_version =
                                  'videobox.yujin-capability.v1'
                              AND conversation_id = ?
                              AND run_id = ?
                              AND action = ?
                          )
                      )
                    """,
                    (
                        project_id,
                        capability["capability_id"],
                        conversation_id,
                        run_id,
                        capability["action"],
                    ),
                ).fetchone()
                if existing is not None:
                    raise ValueError("hermes_capability_registration_conflict")
                connection.execute(
                    """
                    INSERT INTO hermes_capability_ledger (
                        project_id, jti, lifecycle_version, conversation_id,
                        run_id, session_id, session_revision,
                        asset_index_revision, action, state, expires_at,
                        recorded_at, updated_at
                    ) VALUES (
                        ?, ?, 'videobox.yujin-capability.v1', ?, ?, ?, ?, ?,
                        ?, 'issued', ?, ?, ?
                    )
                    """,
                    (
                        project_id,
                        capability["capability_id"],
                        conversation_id,
                        run_id,
                        session_id,
                        session_revision,
                        asset_index_revision,
                        capability["action"],
                        capability["expires_at"],
                        now,
                        now,
                    ),
                )
                self._append_hermes_capability_audit(
                    connection,
                    capability_id=str(capability["capability_id"]),
                    project_id=project_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    action=str(capability["action"]),
                    outcome="accepted",
                    reason="hermes_capability_registered",
                    occurred_at=now,
                )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise ValueError("hermes_capability_registration_conflict") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_expected_hermes_capability(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        action: str,
    ) -> dict[str, Any] | None:
        self._validate_hermes_authority_id(project_id)
        self._validate_hermes_authority_id(conversation_id)
        self._validate_hermes_authority_id(run_id)
        self._validate_hermes_capability_action(action)
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT * FROM hermes_capability_ledger
                WHERE project_id = ?
                  AND lifecycle_version = 'videobox.yujin-capability.v1'
                  AND conversation_id = ?
                  AND run_id = ?
                  AND action = ?
                ORDER BY jti
                """,
                (project_id, conversation_id, run_id, action),
            ).fetchall()
        finally:
            connection.close()
        if len(rows) != 1:
            return None
        return self._expected_hermes_capability_payload(rows[0])

    def consume_registered_hermes_capability(
        self,
        *,
        project_id: str,
        capability_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        action: str,
    ) -> str:
        self._validate_hermes_expected_scope(
            project_id=project_id,
            capability_id=capability_id,
            conversation_id=conversation_id,
            run_id=run_id,
            session_id=session_id,
            session_revision=session_revision,
            asset_index_revision=asset_index_revision,
            action=action,
        )
        connection = self._connection(project_id)
        try:
            self._begin_hermes_capability_transaction(connection)
            current_scope: tuple[bool, int | None, int] | None = None
            if action == "read_context":
                current_scope = self._read_current_hermes_scope_with_lock(
                    connection=connection,
                    project_id=project_id,
                    session_id=session_id,
                )
            lock_suffix = "" if isinstance(connection, sqlite3.Connection) else " FOR UPDATE"
            row = connection.execute(
                """
                SELECT * FROM hermes_capability_ledger
                WHERE project_id = ? AND jti = ?
                  AND lifecycle_version = 'videobox.yujin-capability.v1'
                """
                + lock_suffix,
                (project_id, capability_id),
            ).fetchone()
            now = self._now_iso()
            if row is None:
                self._append_hermes_capability_audit(
                    connection,
                    capability_id=None,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    action=action,
                    outcome="denied",
                    reason="hermes_capability_scope_forbidden",
                    occurred_at=now,
                )
                connection.commit()
                return "hermes_capability_scope_forbidden"
            if any(
                row[field] != expected
                for field, expected in (
                    ("conversation_id", conversation_id),
                    ("run_id", run_id),
                    ("session_id", session_id),
                    ("session_revision", session_revision),
                    ("asset_index_revision", asset_index_revision),
                    ("action", action),
                )
            ):
                self._append_hermes_capability_audit(
                    connection,
                    capability_id=str(row["jti"]),
                    project_id=str(row["project_id"]),
                    conversation_id=str(row["conversation_id"]),
                    run_id=str(row["run_id"]),
                    action=str(row["action"]),
                    outcome="denied",
                    reason="hermes_capability_scope_forbidden",
                    occurred_at=now,
                )
                connection.commit()
                return "hermes_capability_scope_forbidden"
            state = str(row["state"])
            if state == "consumed":
                reason = "hermes_capability_replayed"
            elif state == "revoked":
                reason = "hermes_capability_revoked"
            elif int(row["expires_at"]) <= int(self._clock().timestamp()):
                reason = "hermes_capability_expired"
            elif state != "issued":
                reason = "hermes_capability_unavailable"
            else:
                reason = ""
            if reason:
                self._append_hermes_capability_audit(
                    connection,
                    capability_id=str(row["jti"]),
                    project_id=str(row["project_id"]),
                    conversation_id=str(row["conversation_id"]),
                    run_id=str(row["run_id"]),
                    action=str(row["action"]),
                    outcome="denied",
                    reason=reason,
                    occurred_at=now,
                )
                connection.commit()
                return reason
            if action == "read_context":
                assert current_scope is not None
                (
                    scope_exists,
                    current_session_revision,
                    current_asset_index_revision,
                ) = current_scope
                if (
                    not scope_exists
                    or current_session_revision != session_revision
                    or current_asset_index_revision
                    != asset_index_revision
                ):
                    self._append_hermes_capability_audit(
                        connection,
                        capability_id=str(row["jti"]),
                        project_id=str(row["project_id"]),
                        conversation_id=str(row["conversation_id"]),
                        run_id=str(row["run_id"]),
                        action=str(row["action"]),
                        outcome="denied",
                        reason="hermes_capability_scope_forbidden",
                        occurred_at=now,
                    )
                    connection.commit()
                    return "hermes_capability_scope_forbidden"
            updated = connection.execute(
                """
                UPDATE hermes_capability_ledger
                SET state = 'consumed', updated_at = ?
                WHERE project_id = ? AND jti = ?
                  AND lifecycle_version = 'videobox.yujin-capability.v1'
                  AND state = 'issued'
                """,
                (now, project_id, capability_id),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return "hermes_capability_unavailable"
            self._append_hermes_capability_audit(
                connection,
                capability_id=capability_id,
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                action=action,
                outcome="accepted",
                reason="hermes_capability_consumed",
                occurred_at=now,
            )
            connection.commit()
            try:
                self._purge_expired_hermes_capabilities(
                    project_id=project_id
                )
            except Exception:
                pass
            return "accepted"
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def revoke_issued_hermes_capabilities(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        reason: str,
    ) -> int:
        if reason != "hermes_capability_revoked":
            raise ValueError("hermes_capability_audit_reason_invalid")
        self._validate_hermes_authority_id(project_id)
        self._validate_hermes_authority_id(conversation_id)
        self._validate_hermes_authority_id(run_id)
        connection = self._connection(project_id)
        try:
            self._begin_hermes_capability_transaction(connection)
            revoked = self._revoke_issued_hermes_capabilities_with_connection(
                connection=connection,
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                occurred_at=self._now_iso(),
            )
            connection.commit()
            return revoked
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _revoke_issued_hermes_capabilities_with_connection(
        self,
        *,
        connection: Any,
        project_id: str,
        conversation_id: str,
        run_id: str,
        occurred_at: str,
    ) -> int:
        lock_suffix = (
            "" if isinstance(connection, sqlite3.Connection) else " FOR UPDATE"
        )
        rows = connection.execute(
            """
            SELECT * FROM hermes_capability_ledger
            WHERE project_id = ?
              AND lifecycle_version = 'videobox.yujin-capability.v1'
              AND conversation_id = ?
              AND run_id = ?
            ORDER BY jti
            """
            + lock_suffix,
            (project_id, conversation_id, run_id),
        ).fetchall()
        revoked = 0
        for row in rows:
            if str(row["state"]) != "issued":
                continue
            updated = connection.execute(
                """
                UPDATE hermes_capability_ledger
                SET state = 'revoked', updated_at = ?
                WHERE project_id = ? AND jti = ? AND state = 'issued'
                """,
                (occurred_at, project_id, str(row["jti"])),
            )
            if updated.rowcount != 1:
                continue
            revoked += 1
            self._append_hermes_capability_audit(
                connection,
                capability_id=str(row["jti"]),
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                action=str(row["action"]),
                outcome="accepted",
                reason="hermes_capability_revoked",
                occurred_at=occurred_at,
            )
        return revoked

    def record_hermes_capability_denial(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        action: str,
        reason: str,
        use_registered_capability_id: bool = True,
    ) -> dict[str, Any]:
        if reason not in HERMES_CAPABILITY_DENIAL_REASONS:
            raise ValueError("hermes_capability_audit_reason_invalid")
        if type(use_registered_capability_id) is not bool:
            raise ValueError("hermes_capability_audit_scope_invalid")
        self._validate_hermes_authority_id(project_id)
        self._validate_hermes_authority_id(conversation_id)
        self._validate_hermes_authority_id(run_id)
        self._validate_hermes_capability_action(action)
        connection = self._connection(project_id)
        try:
            self._begin_hermes_capability_transaction(connection)
            rows = connection.execute(
                """
                SELECT * FROM hermes_capability_ledger
                WHERE project_id = ?
                  AND lifecycle_version = 'videobox.yujin-capability.v1'
                  AND conversation_id = ?
                  AND run_id = ?
                  AND action = ?
                ORDER BY jti
                """,
                (project_id, conversation_id, run_id, action),
            ).fetchall()
            trusted = (
                rows[0]
                if use_registered_capability_id and len(rows) == 1
                else None
            )
            event = self._append_hermes_capability_audit(
                connection,
                capability_id=(
                    str(trusted["jti"]) if trusted is not None else None
                ),
                project_id=project_id,
                conversation_id=conversation_id,
                run_id=run_id,
                action=action,
                outcome="denied",
                reason=reason,
                occurred_at=self._now_iso(),
            )
            connection.commit()
            return event
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def consume_hermes_capability(self, *, project_id: str, jti: str, expires_at: int) -> str:
        """Legacy jti-only compatibility surface; it never creates authority."""
        row = self._fetchone(
            project_id,
            """
            SELECT lifecycle_version, state
            FROM hermes_capability_ledger
            WHERE project_id = ? AND jti = ?
            """,
            (project_id, jti),
        )
        if row is None:
            return "missing"
        if str(row["lifecycle_version"]) == "legacy_retired":
            return "legacy_retired"
        return "unavailable"

    def revoke_hermes_capability(self, *, project_id: str, jti: str, expires_at: int) -> None:
        """Legacy jti-only compatibility surface; scoped C3 revoke is required."""
        return None

    @staticmethod
    def _begin_hermes_capability_transaction(connection: Any) -> None:
        connection.execute(
            "BEGIN IMMEDIATE" if isinstance(connection, sqlite3.Connection) else "BEGIN"
        )

    @staticmethod
    def _read_current_hermes_scope_with_lock(
        *,
        connection: Any,
        project_id: str,
        session_id: str,
    ) -> tuple[bool, int | None, int]:
        lock_suffix = (
            "" if isinstance(connection, sqlite3.Connection) else " FOR UPDATE"
        )
        session = connection.execute(
            """
            SELECT session_id, session_revision FROM editing_sessions
            WHERE project_id = ? AND session_id = ?
            """
            + lock_suffix,
            (project_id, session_id),
        ).fetchone()
        if session is None:
            return (False, None, 0)
        if not isinstance(connection, sqlite3.Connection):
            connection.execute(
                """
                INSERT INTO director_asset_index_revisions
                    (project_id, revision)
                VALUES (?, 0)
                ON CONFLICT (project_id) DO NOTHING
                """,
                (project_id,),
            )
        asset_index = connection.execute(
            """
            SELECT revision FROM director_asset_index_revisions
            WHERE project_id = ?
            """
            + lock_suffix,
            (project_id,),
        ).fetchone()
        return (
            True,
            int(session["session_revision"]),
            int(asset_index["revision"]) if asset_index is not None else 0,
        )

    @staticmethod
    def _expected_hermes_capability_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "capability_id": str(row["jti"]),
            "project_id": str(row["project_id"]),
            "conversation_id": str(row["conversation_id"]),
            "run_id": str(row["run_id"]),
            "session_id": str(row["session_id"]),
            "session_revision": int(row["session_revision"]),
            "asset_index_revision": int(row["asset_index_revision"]),
            "action": str(row["action"]),
            "state": str(row["state"]),
            "expires_at": int(row["expires_at"]),
        }

    @classmethod
    def _append_hermes_capability_audit(
        cls,
        connection: Any,
        *,
        capability_id: str | None,
        project_id: str,
        conversation_id: str | None,
        run_id: str | None,
        action: str | None,
        outcome: str,
        reason: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        cls._validate_hermes_authority_id(project_id)
        if capability_id is not None:
            cls._validate_hermes_authority_id(capability_id)
        if conversation_id is not None:
            cls._validate_hermes_authority_id(conversation_id)
        if run_id is not None:
            cls._validate_hermes_authority_id(run_id)
        if action is not None:
            cls._validate_hermes_capability_action(action)
        event = {
            "audit_event_id": f"hermes-audit-{uuid.uuid4().hex}",
            "capability_id": capability_id,
            "project_id": project_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "action": action,
            "outcome": outcome,
            "reason": reason,
            "occurred_at": occurred_at,
        }
        connection.execute(
            """
            INSERT INTO hermes_capability_audit (
                audit_event_id, capability_id, project_id, conversation_id,
                run_id, action, outcome, reason, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(event.values()),
        )
        return event

    def _validate_hermes_capability_registration(
        self,
        *,
        project_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        capabilities: tuple[Mapping[str, Any], Mapping[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            self._validate_hermes_expected_scope(
                project_id=project_id,
                capability_id="registration-placeholder",
                conversation_id=conversation_id,
                run_id=run_id,
                session_id=session_id,
                session_revision=session_revision,
                asset_index_revision=asset_index_revision,
                action="read_context",
            )
        except ValueError as exc:
            raise ValueError("hermes_capability_registration_invalid") from exc
        items = tuple(capabilities)
        if len(items) != 2:
            raise ValueError("hermes_capability_registration_invalid")
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping) or set(item) != {
                "capability_id",
                "action",
                "expires_at",
            }:
                raise ValueError("hermes_capability_registration_invalid")
            capability_id = item["capability_id"]
            action = item["action"]
            expires_at = item["expires_at"]
            try:
                self._validate_hermes_authority_id(capability_id)
                self._validate_hermes_capability_action(action)
            except ValueError as exc:
                raise ValueError("hermes_capability_registration_invalid") from exc
            if (
                not isinstance(expires_at, int)
                or isinstance(expires_at, bool)
                or expires_at <= int(self._clock().timestamp())
            ):
                raise ValueError("hermes_capability_registration_invalid")
            normalized.append(
                {
                    "capability_id": capability_id,
                    "action": action,
                    "expires_at": expires_at,
                }
            )
        if (
            {item["action"] for item in normalized}
            != {"read_context", "publish_proposal"}
            or len({item["capability_id"] for item in normalized}) != 2
        ):
            raise ValueError("hermes_capability_registration_invalid")
        return normalized[0], normalized[1]

    @staticmethod
    def _validate_hermes_authority_id(value: object) -> str:
        if (
            type(value) is not str
            or HERMES_AUTHORITY_ID_PATTERN.fullmatch(value) is None
        ):
            raise ValueError("hermes_capability_expected_invalid")
        return value

    @staticmethod
    def _validate_hermes_capability_action(value: object) -> str:
        if (
            type(value) is not str
            or value not in {"read_context", "publish_proposal"}
        ):
            raise ValueError("hermes_capability_action_forbidden")
        return value

    @staticmethod
    def _validate_hermes_expected_scope(
        *,
        project_id: str,
        capability_id: str,
        conversation_id: str,
        run_id: str,
        session_id: str,
        session_revision: int,
        asset_index_revision: int,
        action: str,
    ) -> None:
        for value in (
            project_id,
            capability_id,
            conversation_id,
            run_id,
            session_id,
        ):
            HermesCapabilityMixin._validate_hermes_authority_id(value)
        HermesCapabilityMixin._validate_hermes_capability_action(action)
        if (
            not isinstance(session_revision, int)
            or isinstance(session_revision, bool)
            or session_revision <= 0
            or not isinstance(asset_index_revision, int)
            or isinstance(asset_index_revision, bool)
            or asset_index_revision < 0
        ):
            raise ValueError("hermes_capability_expected_invalid")

    def _purge_expired_hermes_capabilities(self, *, project_id: str) -> None:
        """Bound the short-lived capability ledger after its decision is committed."""
        connection = self._connection(project_id)
        try:
            connection.execute(
                "DELETE FROM hermes_capability_ledger WHERE project_id = ? AND expires_at <= ?",
                (project_id, int(self._clock().timestamp())),
            )
            connection.commit()
        finally:
            connection.close()

    def _ensure_hermes_capability_lifecycle_schema(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")
        try:
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(hermes_capability_ledger)"
                ).fetchall()
            }
            if columns and "lifecycle_version" not in columns:
                connection.execute(
                    "ALTER TABLE hermes_capability_ledger "
                    "RENAME TO hermes_capability_ledger_pre_c3"
                )
                connection.execute(HERMES_CAPABILITY_LEDGER_SCHEMA_STATEMENT)
                connection.execute(
                    """
                    INSERT INTO hermes_capability_ledger (
                        project_id, jti, lifecycle_version, conversation_id,
                        run_id, session_id, session_revision,
                        asset_index_revision, action, state, expires_at,
                        recorded_at, updated_at
                    )
                    SELECT project_id, jti, 'legacy_retired', NULL, NULL, NULL,
                           NULL, NULL, NULL, state, expires_at, recorded_at,
                           recorded_at
                    FROM hermes_capability_ledger_pre_c3
                    """
                )
                connection.execute(
                    "DROP TABLE hermes_capability_ledger_pre_c3"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_hermes_capability_ledger_expiry
                ON hermes_capability_ledger (project_id, expires_at)
                """
            )
            connection.execute(
                "DROP INDEX IF EXISTS idx_hermes_capability_ledger_scope"
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_hermes_capability_v1_scope_action
                ON hermes_capability_ledger (
                    project_id, conversation_id, run_id, action
                )
                WHERE lifecycle_version =
                    'videobox.yujin-capability.v1'
                """
            )
            if owns_transaction:
                connection.commit()
        except Exception:
            if owns_transaction and connection.in_transaction:
                connection.rollback()
            raise
