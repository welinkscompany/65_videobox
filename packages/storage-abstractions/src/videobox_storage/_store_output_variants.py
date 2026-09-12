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

from videobox_core_engine.highlight_scoring import select_highlight_segment_ids
from videobox_domain_models.output_variants import OutputVariant, VariantOverride


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

    def _new_short_form_variant(
        self,
        *,
        session: Mapping[str, Any],
        source_session_id: str,
        variant_id: str | None,
        selected_segment_ids: Sequence[str] | None,
        layout: Mapping[str, Any] | None,
    ) -> OutputVariant:
        """숏폼 변형본 하나를 **아직 저장하지 않고** 짓는다.

        `create_output_variant`(단추 경로)와 새 트랜잭션 메서드(유진의 "만들기")가
        **같은 모양**을 지어야 한다 -- 이 저장소는 같은 로직이 두 자리에 갈라져
        한쪽만 고쳐지는 함정에 반복해서 걸렸다(이 파일 머리말).
        """
        master_segments = [
            segment
            for segment in session.get("segments", [])
            if isinstance(segment, Mapping) and str(segment.get("segment_id") or "").strip()
        ]
        # **자동 하이라이트(owner 결정 2026-08-28).** 예전에는 여기서
        # `selected_segment_ids`를 비워 뒀고, 그 결과 `materialize_variant`가
        # 전체 장면을 그대로 썼다 -- "하이라이트"라는 이름과 달리 원본 전체였다.
        #
        # **고르는 일은 이제 저장소 밖에서 한다**(2026-09-11). 마케팅용 숏폼
        # 판단에는 유진이 필요하고 저장소에는 런타임이 없다 -- 부르는 쪽
        # (`routers/output_variants.py`)이 `short_form_scene_pick`으로 골라
        # 넘긴다. 여기 남은 자막 밀도 휴리스틱은 **아무도 안 넘겨줬을 때의
        # 대비책**이고, 그 사실은 라우터가 화면에 말해 준다.
        picked = tuple(
            str(segment_id).strip()
            for segment_id in (selected_segment_ids or ())
            if str(segment_id).strip()
        )
        master_ids = {str(segment["segment_id"]) for segment in master_segments}
        # 넘어온 목록이라도 지금 판에 없는 장면은 버린다 -- `OutputVariant`가
        # 마스터 부분집합을 요구한다.
        picked = tuple(segment_id for segment_id in picked if segment_id in master_ids)
        # 대비책도 **대표님이 이미 뺀 장면은 고르지 않는다.** 뺀 장면을 고르면
        # 숏폼이 그 길이만큼 자리를 내주는데 합성이 그 클립을 버려서 죽은 시간이
        # 된다(`materialize_variant`가 마지막 그물이지만 여기서 먼저 막는다).
        playable_master_segments = [
            segment
            for segment in master_segments
            if str(segment.get("cut_action") or "keep") != "remove"
        ]
        selected = (
            picked or select_highlight_segment_ids(playable_master_segments) or None
        )
        return OutputVariant(
            variant_id=variant_id or f"variant-{uuid.uuid4().hex}",
            kind="vertical_highlight",
            source_session_id=source_session_id,
            source_session_revision=int(session.get("session_revision") or 1),
            variant_revision=1,
            master_segment_ids=tuple(
                str(segment["segment_id"]) for segment in master_segments
            ) or None,
            selected_segment_ids=selected,
            # 숏폼 제목 띠(`shorts_layout.py`). 만들 때 같이 들어오는 이유: 제목은
            # 장면을 고른 그 판단에서 같이 나온다(`short_form_scene_pick`의 짜기
            # 호출 하나). 나중에 따로 저장하게 두면 만들기와 제목 사이에 제목
            # 없는 판이 한 번 렌더될 수 있다.
            overrides=VariantOverride(layout=dict(layout)) if layout else VariantOverride(),
        )

    def create_output_variant(
        self,
        *,
        project_id: str,
        source_session_id: str,
        kind: str,
        variant_id: str | None = None,
        selected_segment_ids: Sequence[str] | None = None,
        layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if kind != "vertical_highlight":
            raise ValueError("only_vertical_highlight_can_be_created_explicitly")
        session = self.get_editing_session(project_id=project_id, session_id=source_session_id)
        variant = self._new_short_form_variant(
            session=session,
            source_session_id=source_session_id,
            variant_id=variant_id,
            selected_segment_ids=selected_segment_ids,
            layout=layout,
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
                or int(current["source_session_revision"]) > variant.source_session_revision
                or str(current["kind"]) != variant.kind
            ):
                raise ValueError("variant_source_identity_mismatch")
            now = self._now_iso()
            connection.execute(
                "UPDATE output_variants SET source_session_revision = ?, variant_revision = ?, overrides_json = ?, locks_json = ?, "
                "conflicts_json = ?, selected_segment_ids_json = ?, master_segment_ids_json = ?, updated_at = ? "
                "WHERE project_id = ? AND variant_id = ? AND variant_revision = ?",
                (
                    variant.source_session_revision,
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

    def apply_director_variant_proposal_transaction(
        self,
        *,
        project_id: str,
        proposal_id: str,
        variant_id: str,
        expected_variant_revision: int,
        variant: OutputVariant,
    ) -> dict[str, Any]:
        """Atomically apply one render-only proposal and consume its lifecycle."""

        from videobox_storage.local_project_store import EditingSessionRevisionConflict

        if variant.variant_id != variant_id or variant.variant_revision != expected_variant_revision + 1:
            raise ValueError("variant_apply_identity_or_revision_invalid")
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            proposal = connection.execute(
                "SELECT status FROM director_proposals WHERE project_id = ? AND proposal_id = ?",
                (project_id, proposal_id),
            ).fetchone()
            if proposal is None:
                raise KeyError("director_proposal_missing")
            if str(proposal["status"]) != "ready":
                raise EditingSessionRevisionConflict("director_proposal_not_ready")
            current = connection.execute(
                "SELECT * FROM output_variants WHERE project_id = ? AND variant_id = ?",
                (project_id, variant_id),
            ).fetchone()
            if current is None:
                raise KeyError("output_variant_missing")
            if int(current["variant_revision"]) != expected_variant_revision:
                raise EditingSessionRevisionConflict("output_variant_revision_conflict")
            if (
                str(current["source_session_id"]) != variant.source_session_id
                # **판 버전은 앞으로만 간다**(2026-09-12). 전에는 "정확히 같을 때만"
                # 받았는데, 숏폼이 쓸 자리를 나누면 판 버전이 한 칸 올라간다 --
                # 그러면 "유진에게 말해서 다시 만들기"가 이 문에서 조용히 422로
                # 죽었다. 뒤로 가는 것은 여전히 막는다(낡은 모양을 덮어쓰는 일).
                # `update_output_variant`(단추 경로)가 이미 같은 규칙이다.
                or int(current["source_session_revision"]) > variant.source_session_revision
                or str(current["kind"]) != variant.kind
            ):
                raise ValueError("variant_source_identity_mismatch")
            now = self._now_iso()
            connection.execute(
                "UPDATE output_variants SET source_session_revision = ?, variant_revision = ?, overrides_json = ?, locks_json = ?, "
                "conflicts_json = ?, selected_segment_ids_json = ?, master_segment_ids_json = ?, updated_at = ? "
                "WHERE project_id = ? AND variant_id = ? AND variant_revision = ?",
                (
                    variant.source_session_revision,
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
            changed = connection.execute(
                "UPDATE director_proposals SET status = ?, updated_at = ? WHERE project_id = ? AND proposal_id = ? AND status = 'ready'",
                ("applied", now, project_id, proposal_id),
            ).rowcount
            if changed != 1:
                raise EditingSessionRevisionConflict("director_proposal_already_applied")
            connection.execute(
                "INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)",
                (proposal_id, "applied", "variant_transaction_apply", now),
            )
            connection.commit()
            return self.get_output_variant(project_id=project_id, variant_id=variant_id)
        except Exception:
            if getattr(connection, "in_transaction", False):
                connection.rollback()
            raise
        finally:
            connection.close()

    def apply_director_variant_create_proposal_transaction(
        self,
        *,
        project_id: str,
        proposal_id: str,
        source_session_id: str,
        expected_session_revision: int,
        variant_id: str | None = None,
        selected_segment_ids: Sequence[str] | None = None,
        layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """유진의 "숏폼 만들어줘"를 **한 트랜잭션**으로 만들고 그 제안을 소진한다.

        `create_output_variant`(단추 경로)를 그대로 못 쓰는 이유: 그 함수는 제안을
        모른다. 둘을 따로 부르면 변형본은 생겼는데 제안이 "ready"로 남는 창이
        생기고, 그 사이 재시도가 오면 두 번째 변형본을 또 지으려다
        `output_variants`의 `UNIQUE(project_id, source_session_id, kind)`에
        걸린다(그 자체는 안전하지만 제안 lifecycle이 결과와 어긋난다). 변형본
        갱신 경로(`apply_director_variant_proposal_transaction`)가 이미 같은
        이유로 한 트랜잭션을 쓴다 -- 이건 그 만들기(INSERT) 짝이다.
        """
        from videobox_storage.local_project_store import EditingSessionRevisionConflict

        session = self.get_editing_session(project_id=project_id, session_id=source_session_id)
        if int(session.get("session_revision") or 1) != expected_session_revision:
            raise EditingSessionRevisionConflict("session_revision_mismatch")
        variant = self._new_short_form_variant(
            session=session,
            source_session_id=source_session_id,
            variant_id=variant_id,
            selected_segment_ids=selected_segment_ids,
            layout=layout,
        )
        connection = self._connection(project_id)
        try:
            self._begin_output_variant_write(connection)
            proposal = connection.execute(
                "SELECT status FROM director_proposals WHERE project_id = ? AND proposal_id = ?",
                (project_id, proposal_id),
            ).fetchone()
            if proposal is None:
                raise KeyError("director_proposal_missing")
            if str(proposal["status"]) != "ready":
                raise EditingSessionRevisionConflict("director_proposal_not_ready")
            now = self._now_iso()
            connection.execute(
                "INSERT INTO output_variants (variant_id, project_id, kind, source_session_id, "
                "source_session_revision, variant_revision, overrides_json, locks_json, conflicts_json, "
                "selected_segment_ids_json, master_segment_ids_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._output_variant_values(project_id, variant, now, now),
            )
            changed = connection.execute(
                "UPDATE director_proposals SET status = ?, updated_at = ? WHERE project_id = ? AND proposal_id = ? AND status = 'ready'",
                ("applied", now, project_id, proposal_id),
            ).rowcount
            if changed != 1:
                raise EditingSessionRevisionConflict("director_proposal_already_applied")
            connection.execute(
                "INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)",
                (proposal_id, "applied", "variant_transaction_create", now),
            )
            connection.commit()
            return self.get_output_variant(project_id=project_id, variant_id=variant.variant_id)
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
