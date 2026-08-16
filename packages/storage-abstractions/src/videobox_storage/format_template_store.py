"""저장된 포맷은 프로젝트에 매이지 않는다.

다음 영상은 보통 새 프로젝트다. 포맷을 프로젝트 안에 넣으면 정작 쓰고 싶을 때
지난 프로젝트를 뒤져야 한다. 그래서 라이브러리 자산과 같이 사용자 단위로 둔다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS format_templates (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class FormatTemplateStore:
    """owner가 이름 붙여 저장한 포맷들."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.database_path = self.root / "format_templates.sqlite"

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute(_SCHEMA)
        return connection

    @staticmethod
    def _row_to_template(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        payload["template_id"] = row["template_id"]
        payload["name"] = row["name"]
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        return payload

    def save_template(self, *, template: dict[str, Any]) -> dict[str, Any]:
        """같은 이름이면 새로 쌓지 않고 그 포맷을 고친다.

        같은 이름이 여러 개면 owner가 어느 것을 고를지 알 수 없다.
        """
        name = str(template.get("name") or "").strip()
        if not name:
            raise ValueError("format_template name must not be blank")
        payload = {key: value for key, value in template.items() if key not in {"template_id", "created_at", "updated_at"}}
        now = datetime.now(UTC).isoformat()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT template_id, created_at FROM format_templates WHERE name = ?", (name,)
            ).fetchone()
            if existing is None:
                template_id = f"format_template_{uuid.uuid4().hex[:12]}"
                connection.execute(
                    "INSERT INTO format_templates (template_id, name, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (template_id, name, json.dumps(payload, ensure_ascii=True), now, now),
                )
            else:
                template_id = str(existing["template_id"])
                connection.execute(
                    "UPDATE format_templates SET payload_json = ?, updated_at = ? WHERE template_id = ?",
                    (json.dumps(payload, ensure_ascii=True), now, template_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_template(template_id=template_id)

    def get_template(self, *, template_id: str) -> dict[str, Any]:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM format_templates WHERE template_id = ?", (template_id,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"Format template not found: {template_id}")
        return self._row_to_template(row)

    def list_templates(self) -> list[dict[str, Any]]:
        """최근에 만든 것이 위로 온다 — 방금 만든 포맷을 맨 아래에서 찾게 하지 않는다."""
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM format_templates ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_template(row) for row in rows]

    def delete_template(self, *, template_id: str) -> None:
        connection = self._connection()
        try:
            connection.execute("DELETE FROM format_templates WHERE template_id = ?", (template_id,))
            connection.commit()
        finally:
            connection.close()
