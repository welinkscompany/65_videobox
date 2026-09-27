"""대표님 결재 결과를 한 번만 반영하는 저장 경계 (AK W1215-2, 2026-09-28).

AK-System 결재함이 대표님 결정을 자기 레지스트리 파일에 남기면, 호스트 동기화
(`videobox_mcp.ak_decision_sync`)가 그것을 읽어 API로 보내고, API가 여기를
부른다. 이 파일이 지키는 것은 셋이다.

1. **한 번만.** 같은 결정 번호가 같은 내용으로 다시 오면 아무것도 안 바꾸고
   `applied=False`를 돌려준다. 동기화는 몇 번을 돌아도 된다.
2. **뒤집지 않는다.** 같은 결정 번호에 다른 결과가 오면 거절한다 -- AK 결정은
   한 번 나면 끝이고, 다르게 온다면 어딘가 잘못된 것이라 조용히 덮으면 안 된다.
3. **남의 결정을 받지 않는다.** 결정 번호가 이 프로젝트·이 회차의 것
   (`vb-<kind>-<project>-<cycle>`)이 아니면 거절한다.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from videobox_domain_models.founder_approvals import (
    SELECTION_FIELD_BY_KIND,
    founder_decision_id,
    founder_outcome,
)


class FounderApprovalMixin:
    def apply_founder_approval_decision(
        self,
        *,
        project_id: str,
        decision_id: str,
        kind: str,
        cycle_id: str,
        status: str,
        selected_index: int | None = None,
        selected_text: str | None = None,
        decided_at: str | None = None,
        decided_via: str | None = None,
    ) -> dict[str, Any]:
        self.get_project(project_id=project_id)  # 없는 프로젝트면 KeyError -> 404
        if not str(cycle_id).strip():
            raise ValueError("founder_decision_cycle_id_required")
        outcome = founder_outcome(kind=kind, status=status)
        if decision_id != founder_decision_id(kind=kind, project_id=project_id, cycle_id=cycle_id):
            raise ValueError("founder_decision_id_mismatch")
        if kind in SELECTION_FIELD_BY_KIND and outcome == "approved":
            if selected_index is None or not str(selected_text or "").strip():
                raise ValueError("founder_decision_selection_required")
        if kind not in SELECTION_FIELD_BY_KIND or outcome == "rejected":
            # 업로드에는 고를 후보가 없고, 반려에는 고른 것이 없다.
            selected_index, selected_text = None, None
        incoming = {
            "kind": kind,
            "cycle_id": cycle_id,
            "status": status,
            "outcome": outcome,
            "selected_index": selected_index,
            "selected_text": selected_text,
        }
        connection = self._connection(project_id)
        try:
            self._begin_founder_approval_write(connection)
            existing = connection.execute(
                "SELECT * FROM founder_approval_decisions WHERE project_id = ? AND decision_id = ?",
                (project_id, decision_id),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                recorded = self._founder_approval_row(existing)
                if any(recorded[key] != value for key, value in incoming.items()):
                    raise ValueError(f"founder_decision_conflict: {decision_id}")
                return {"applied": False, "decision": recorded}
            applied_at = self._now_iso()
            connection.execute(
                "INSERT INTO founder_approval_decisions (project_id, decision_id, kind, cycle_id, status, outcome, "
                "selected_index, selected_text, decided_at, decided_via, applied_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id, decision_id, kind, cycle_id, status, outcome,
                    selected_index, selected_text, decided_at, decided_via, applied_at,
                ),
            )
            connection.commit()
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "applied": True,
            "decision": {
                "project_id": project_id,
                "decision_id": decision_id,
                **incoming,
                "decided_at": decided_at,
                "decided_via": decided_via,
                "applied_at": applied_at,
            },
        }

    def list_founder_approval_decisions(self, *, project_id: str) -> list[dict[str, Any]]:
        self.get_project(project_id=project_id)
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                "SELECT * FROM founder_approval_decisions WHERE project_id = ? ORDER BY applied_at, decision_id",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [self._founder_approval_row(row) for row in rows]

    def get_founder_gate_decision(
        self, *, project_id: str, kind: str, cycle_id: str
    ) -> dict[str, Any] | None:
        """이 게이트(프로젝트·종류·회차)에 대표님 결정이 돌아왔으면 그것, 아니면 None."""
        decision_id = founder_decision_id(kind=kind, project_id=project_id, cycle_id=cycle_id)
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT * FROM founder_approval_decisions WHERE project_id = ? AND decision_id = ?",
                (project_id, decision_id),
            ).fetchone()
        finally:
            connection.close()
        return self._founder_approval_row(row) if row is not None else None

    @staticmethod
    def _begin_founder_approval_write(connection: Any) -> None:
        # `_store_preview_shares.py`와 같은 모양 -- Postgres에서는 표를 잠가 두 동기화가
        # 동시에 같은 결정을 넣으려 할 때 하나만 들어가게 한다.
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("LOCK TABLE founder_approval_decisions IN SHARE ROW EXCLUSIVE MODE")

    @staticmethod
    def _founder_approval_row(row: Any) -> dict[str, Any]:
        return {
            "project_id": str(row["project_id"]),
            "decision_id": str(row["decision_id"]),
            "kind": str(row["kind"]),
            "cycle_id": str(row["cycle_id"]),
            "status": str(row["status"]),
            "outcome": str(row["outcome"]),
            "selected_index": int(row["selected_index"]) if row["selected_index"] is not None else None,
            "selected_text": str(row["selected_text"]) if row["selected_text"] is not None else None,
            "decided_at": str(row["decided_at"]) if row["decided_at"] else None,
            "decided_via": str(row["decided_via"]) if row["decided_via"] else None,
            "applied_at": str(row["applied_at"]),
        }
