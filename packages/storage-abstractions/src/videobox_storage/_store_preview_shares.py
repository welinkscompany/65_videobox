"""Persistence boundary for preview share links.

owner 요청(2026-08-28): 프리뷰 공유 링크 -- 토큰 링크 방식 승인. 이 앱은 지금까지
인증이 전혀 없었다는 점을 밝혀 둔다. 토큰 하나가 완성본 하나에만 닿는 credential이고,
그 밖의 어떤 것도 열지 않는다.

저장은 `output_variants`와 같은 프로젝트별 SQLite 파일에 두지만, 토큰만으로 찾는
조회(`get_preview_share_by_token`)는 project_id를 모른 채로 들어온다. 이 저장소는
project마다 SQLite 파일이 갈라져 있어(각 `database_path(project_id)`) 진짜 전역
조회가 없다 -- `list_all_jobs`가 이미 같은 이유로 project를 순회해서 합친다
(`local_project_store.py` 참고). 여기서도 같은 방식을 그대로 따른다: 로컬 1인용
도구 규모에서는 충분하고, 전역 색인이 필요해지면 그때 새로 만든다.
"""

from __future__ import annotations

import secrets
import sqlite3
from typing import Any


class PreviewShareMixin:
    def create_preview_share(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        export = self.get_final_render_export(project_id=project_id, export_id=export_id)
        if str(export.get("export_type")) != "final_render":
            raise ValueError("preview_share_requires_final_render")
        if str(export.get("status")) != "succeeded":
            raise ValueError("preview_share_requires_succeeded_export")
        # uuid가 아니라 secrets를 쓴다 -- 이 토큰이 완성본 접근을 여는 credential이라
        # 추측 가능성이 낮아야 한다(uuid4는 이 용도로 충분히 안전하다고 보지 않는다).
        token = secrets.token_urlsafe(32)
        share_id = f"preview-share-{secrets.token_hex(16)}"
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write_table(connection, "preview_shares")
            now = self._now_iso()
            connection.execute(
                "INSERT INTO preview_shares (share_id, project_id, export_id, token, created_at, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (share_id, project_id, export_id, token, now),
            )
            connection.commit()
            return {
                "share_id": share_id,
                "project_id": project_id,
                "export_id": export_id,
                "token": token,
                "created_at": now,
                "revoked_at": None,
            }
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_preview_share_by_token(self, *, token: str) -> dict[str, Any] | None:
        for project in self.list_projects(include_archived=True):
            project_id = str(project["project_id"])
            connection = self._connection(project_id)
            try:
                row = connection.execute(
                    "SELECT * FROM preview_shares WHERE project_id = ? AND token = ?",
                    (project_id, token),
                ).fetchone()
            finally:
                connection.close()
            if row is None:
                continue
            if row["revoked_at"]:
                return None
            return self._preview_share_row(row)
        return None

    def revoke_preview_share(self, *, project_id: str, share_id: str) -> None:
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write_table(connection, "preview_shares")
            row = connection.execute(
                "SELECT share_id FROM preview_shares WHERE project_id = ? AND share_id = ?",
                (project_id, share_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"Preview share not found: {share_id}")
            connection.execute(
                "UPDATE preview_shares SET revoked_at = ? WHERE project_id = ? AND share_id = ? AND revoked_at IS NULL",
                (self._now_iso(), project_id, share_id),
            )
            connection.commit()
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def list_preview_shares(
        self, *, project_id: str, export_id: str | None = None
    ) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            query = "SELECT * FROM preview_shares WHERE project_id = ?"
            params: list[object] = [project_id]
            if export_id is not None:
                query += " AND export_id = ?"
                params.append(export_id)
            query += " ORDER BY created_at DESC"
            rows = connection.execute(query, tuple(params)).fetchall()
        finally:
            connection.close()
        # 만든 뒤에는 토큰을 다시 내보내지 않는다 -- 목록은 관리용이지, 재발급 창구가 아니다.
        return [
            {key: value for key, value in self._preview_share_row(row).items() if key != "token"}
            for row in rows
        ]

    @staticmethod
    def _begin_output_variant_write_table(connection: Any, table_name: str) -> None:
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"LOCK TABLE {table_name} IN SHARE ROW EXCLUSIVE MODE")

    @staticmethod
    def _preview_share_row(row: Any) -> dict[str, Any]:
        return {
            "share_id": str(row["share_id"]),
            "project_id": str(row["project_id"]),
            "export_id": str(row["export_id"]),
            "token": str(row["token"]),
            "created_at": str(row["created_at"]),
            "revoked_at": str(row["revoked_at"]) if row["revoked_at"] else None,
        }
