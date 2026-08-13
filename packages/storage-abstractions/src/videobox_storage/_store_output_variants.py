"""Persistence boundary for linked output variants.

The mixin stores variant metadata separately from the historic editing-session
JSON.  It intentionally accepts the same connection abstraction as the local
and PostgreSQL stores, so the identity and CAS rules remain backend-neutral.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from videobox_domain_models.output_variants import OutputVariant


class OutputVariantMixin:
    def list_output_variants(
        self, *, project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            query = "SELECT * FROM output_variants WHERE project_id = ?"
            params: list[object] = [project_id]
            if session_id is not None:
                query += " AND source_session_id = ?"
                params.append(session_id)
            query += " ORDER BY source_session_revision DESC, CASE kind WHEN 'horizontal' THEN 1 WHEN 'vertical_full' THEN 2 ELSE 3 END, variant_id"
            return [self._output_variant_row(row) for row in connection.execute(query, tuple(params)).fetchall()]
        finally:
            connection.close()

    def get_output_variant(self, *, project_id: str, variant_id: str) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT * FROM output_variants WHERE project_id = ? AND variant_id = ?",
                (project_id, variant_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"Output variant not found: {variant_id}")
            return self._output_variant_row(row)
        finally:
            connection.close()

    def ensure_output_variants(
        self, *, project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Seed the two required default views for the latest session once."""

        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            if session_id is None:
                session_row = connection.execute(
                    "SELECT session_id, session_revision, session_json FROM editing_sessions "
                    "WHERE project_id = ? ORDER BY session_revision DESC, updated_at DESC, session_id DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
            else:
                session_row = connection.execute(
                    "SELECT session_id, session_revision, session_json FROM editing_sessions "
                    "WHERE project_id = ? AND session_id = ?",
                    (project_id, session_id),
                ).fetchone()
            if session_row is None:
                connection.commit()
                return []

            source_session_id = str(session_row["session_id"])
            source_session_revision = int(session_row["session_revision"] or 1)
            session_payload = json.loads(str(session_row["session_json"] or "{}"))
            master_segment_ids = tuple(
                str(segment["segment_id"])
                for segment in session_payload.get("segments", [])
                if isinstance(segment, Mapping) and str(segment.get("segment_id") or "").strip()
            )
            now = self._now_iso()
            for kind in ("horizontal", "vertical_full"):
                variant_id = f"variant-{source_session_id}-{kind}"
                variant = OutputVariant(
                    variant_id=variant_id,
                    kind=kind,
                    source_session_id=source_session_id,
                    source_session_revision=source_session_revision,
                    variant_revision=1,
                    master_segment_ids=master_segment_ids or None,
                )
                connection.execute(
                    "INSERT INTO output_variants (variant_id, project_id, kind, source_session_id, "
                    "source_session_revision, variant_revision, overrides_json, locks_json, conflicts_json, "
                    "selected_segment_ids_json, master_segment_ids_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    self._output_variant_values(project_id, variant, now, now),
                )
            rows = connection.execute(
                "SELECT * FROM output_variants WHERE project_id = ? AND source_session_id = ? "
                "ORDER BY CASE kind WHEN 'horizontal' THEN 1 WHEN 'vertical_full' THEN 2 ELSE 3 END, variant_id",
                (project_id, source_session_id),
            ).fetchall()
            connection.commit()
            return [self._output_variant_row(row) for row in rows]
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def create_output_variant(
        self,
        *,
        project_id: str,
        source_session_id: str,
        kind: str,
        variant_id: str | None = None,
    ) -> dict[str, Any]:
        if kind != "vertical_highlight":
            raise ValueError("only_vertical_highlight_can_be_created_explicitly")
        session = self.get_editing_session(project_id=project_id, session_id=source_session_id)
        variant = OutputVariant(
            variant_id=variant_id or f"variant-{uuid.uuid4().hex}",
            kind="vertical_highlight",
            source_session_id=source_session_id,
            source_session_revision=int(session.get("session_revision") or 1),
            variant_revision=1,
            master_segment_ids=tuple(
                str(segment["segment_id"])
                for segment in session.get("segments", [])
                if isinstance(segment, Mapping) and str(segment.get("segment_id") or "").strip()
            ) or None,
        )
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            now = self._now_iso()
            connection.execute(
                "INSERT INTO output_variants (variant_id, project_id, kind, source_session_id, "
                "source_session_revision, variant_revision, overrides_json, locks_json, conflicts_json, "
                "selected_segment_ids_json, master_segment_ids_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._output_variant_values(project_id, variant, now, now),
            )
            connection.commit()
            return self.get_output_variant(project_id=project_id, variant_id=variant.variant_id)
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def update_output_variant(
        self,
        *,
        project_id: str,
        variant_id: str,
        expected_variant_revision: int,
        variant: OutputVariant,
    ) -> dict[str, Any]:
        from videobox_storage.local_project_store import EditingSessionRevisionConflict

        if variant.variant_id != variant_id:
            raise ValueError("variant_identity_mismatch")
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            current = connection.execute(
                "SELECT * FROM output_variants WHERE project_id = ? AND variant_id = ?",
                (project_id, variant_id),
            ).fetchone()
            if current is None:
                raise KeyError(f"Output variant not found: {variant_id}")
            current_revision = int(current["variant_revision"])
            if current_revision != int(expected_variant_revision):
                raise EditingSessionRevisionConflict("output variant revision conflict")
            if variant.variant_revision != current_revision + 1:
                raise ValueError("variant_revision_must_advance_by_one")
            if (
                str(current["source_session_id"]) != variant.source_session_id
                or int(current["source_session_revision"]) != variant.source_session_revision
                or str(current["kind"]) != variant.kind
            ):
                raise ValueError("variant_source_identity_mismatch")
            now = self._now_iso()
            connection.execute(
                "UPDATE output_variants SET variant_revision = ?, overrides_json = ?, locks_json = ?, "
                "conflicts_json = ?, selected_segment_ids_json = ?, master_segment_ids_json = ?, updated_at = ? "
                "WHERE project_id = ? AND variant_id = ? AND variant_revision = ?",
                (
                    variant.variant_revision,
                    json.dumps(variant.overrides.model_dump(mode="json"), ensure_ascii=False),
                    json.dumps([lock.model_dump(mode="json") for lock in variant.locks], ensure_ascii=False),
                    json.dumps([conflict.model_dump(mode="json") for conflict in variant.conflicts], ensure_ascii=False),
                    json.dumps(list(variant.selected_segment_ids), ensure_ascii=False) if variant.selected_segment_ids is not None else None,
                    json.dumps(list(variant.master_segment_ids), ensure_ascii=False) if variant.master_segment_ids is not None else None,
                    now,
                    project_id,
                    variant_id,
                    expected_variant_revision,
                ),
            )
            connection.commit()
            return self.get_output_variant(project_id=project_id, variant_id=variant_id)
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def save_variant_materialization(
        self,
        *,
        project_id: str,
        variant_id: str,
        source_session_id: str,
        source_session_revision: int,
        source_variant_revision: int,
        timeline_id: str,
        segments: Sequence[Mapping[str, object]],
    ) -> dict[str, Any]:
        variant = self.get_output_variant(project_id=project_id, variant_id=variant_id)
        if (
            variant["source_session_id"] != source_session_id
            or int(variant["source_session_revision"]) != int(source_session_revision)
            or int(variant["variant_revision"]) != int(source_variant_revision)
        ):
            raise ValueError("source_session_or_variant_revision_mismatch")
        materialization_id = f"materialization-{variant_id}-{source_variant_revision}"
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            now = self._now_iso()
            connection.execute(
                "INSERT INTO variant_materializations (materialization_id, project_id, variant_id, "
                "source_session_id, source_session_revision, source_variant_revision, timeline_id, "
                "segments_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, variant_id, source_variant_revision) DO UPDATE SET "
                "timeline_id = excluded.timeline_id, segments_json = excluded.segments_json, updated_at = excluded.updated_at",
                (
                    materialization_id,
                    project_id,
                    variant_id,
                    source_session_id,
                    int(source_session_revision),
                    int(source_variant_revision),
                    timeline_id,
                    json.dumps([dict(segment) for segment in segments], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM variant_materializations WHERE project_id = ? AND variant_id = ? AND source_variant_revision = ?",
                (project_id, variant_id, int(source_variant_revision)),
            ).fetchone()
            connection.commit()
            return self._materialization_row(row)
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_variant_materialization(
        self, *, project_id: str, variant_id: str, source_variant_revision: int
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            row = connection.execute(
                "SELECT * FROM variant_materializations WHERE project_id = ? AND variant_id = ? AND source_variant_revision = ?",
                (project_id, variant_id, int(source_variant_revision)),
            ).fetchone()
            if row is None:
                raise KeyError("Variant materialization not found")
            return self._materialization_row(row)
        finally:
            connection.close()

    @staticmethod
    def _begin_output_variant_write(connection: Any) -> None:
        if isinstance(connection, sqlite3.Connection):
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("LOCK TABLE output_variants, variant_materializations IN SHARE ROW EXCLUSIVE MODE")

    @staticmethod
    def _output_variant_values(
        project_id: str, variant: OutputVariant, created_at: str, updated_at: str
    ) -> tuple[object, ...]:
        return (
            variant.variant_id,
            project_id,
            variant.kind,
            variant.source_session_id,
            variant.source_session_revision,
            variant.variant_revision,
            json.dumps(variant.overrides.model_dump(mode="json"), ensure_ascii=False),
            json.dumps([lock.model_dump(mode="json") for lock in variant.locks], ensure_ascii=False),
            json.dumps([conflict.model_dump(mode="json") for conflict in variant.conflicts], ensure_ascii=False),
            json.dumps(list(variant.selected_segment_ids), ensure_ascii=False) if variant.selected_segment_ids is not None else None,
            json.dumps(list(variant.master_segment_ids), ensure_ascii=False) if variant.master_segment_ids is not None else None,
            created_at,
            updated_at,
        )

    @staticmethod
    def _json_column(row: Any, key: str, default: object) -> object:
        value = row[key]
        return default if value in (None, "") else json.loads(str(value))

    @classmethod
    def _output_variant_row(cls, row: Any) -> dict[str, Any]:
        payload = {
            "variant_id": str(row["variant_id"]),
            "project_id": str(row["project_id"]),
            "kind": str(row["kind"]),
            "source_session_id": str(row["source_session_id"]),
            "source_session_revision": int(row["source_session_revision"]),
            "variant_revision": int(row["variant_revision"]),
            "overrides": cls._json_column(row, "overrides_json", {}),
            "locks": cls._json_column(row, "locks_json", []),
            "conflicts": cls._json_column(row, "conflicts_json", []),
            "selected_segment_ids": cls._json_column(row, "selected_segment_ids_json", None),
            "master_segment_ids": cls._json_column(row, "master_segment_ids_json", None),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        OutputVariant.model_validate({key: value for key, value in payload.items() if key not in {"project_id", "created_at", "updated_at"}})
        return payload

    @classmethod
    def _materialization_row(cls, row: Any) -> dict[str, Any]:
        return {
            "materialization_id": str(row["materialization_id"]),
            "project_id": str(row["project_id"]),
            "variant_id": str(row["variant_id"]),
            "source_session_id": str(row["source_session_id"]),
            "source_session_revision": int(row["source_session_revision"]),
            "source_variant_revision": int(row["source_variant_revision"]),
            "timeline_id": str(row["timeline_id"]),
            "segments": cls._json_column(row, "segments_json", []),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
