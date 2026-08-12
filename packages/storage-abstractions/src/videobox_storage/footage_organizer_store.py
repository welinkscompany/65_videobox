"""SQLite persistence for non-destructive footage organization."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4

from videobox_domain_models.footage_organizer import (
    FootageProposal,
    FootageProposalSegment,
    FootageProposalStatus,
    FootageSource,
    FootageSourceSegment,
    VirtualSequence,
    VirtualSequenceItem,
)
from videobox_storage.library_user_asset_store import ensure_library_user_asset_schema


FOOTAGE_ORGANIZER_SCHEMA = """
CREATE TABLE IF NOT EXISTS library_footage_sources (
    source_id TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    library_asset_id TEXT NOT NULL,
    FOREIGN KEY (library_asset_id) REFERENCES library_user_assets(library_asset_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS library_source_segments (
    segment_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    start_sec REAL NOT NULL CHECK (start_sec >= 0),
    end_sec REAL NOT NULL CHECK (end_sec > start_sec),
    label TEXT NOT NULL DEFAULT '',
    machine_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES library_footage_sources(source_id) ON DELETE RESTRICT,
    UNIQUE (source_id, start_sec, end_sec)
);
CREATE INDEX IF NOT EXISTS idx_library_source_segments_source
    ON library_source_segments (source_id, start_sec, segment_id);
CREATE TABLE IF NOT EXISTS footage_proposals (
    proposal_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'rejected', 'stale')),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    confirmed_json TEXT NOT NULL DEFAULT '{}',
    machine_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES library_footage_sources(source_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_footage_proposals_source
    ON footage_proposals (source_id, updated_at, proposal_id);
CREATE TABLE IF NOT EXISTS footage_proposal_segments (
    proposal_segment_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    segment_order INTEGER NOT NULL CHECK (segment_order >= 1),
    source_segment_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    start_sec REAL NOT NULL CHECK (start_sec >= 0),
    end_sec REAL NOT NULL CHECK (end_sec > start_sec),
    machine_json TEXT NOT NULL DEFAULT '{}',
    confirmed_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (proposal_id) REFERENCES footage_proposals(proposal_id) ON DELETE CASCADE,
    FOREIGN KEY (source_segment_id) REFERENCES library_source_segments(segment_id) ON DELETE RESTRICT,
    UNIQUE (proposal_id, segment_order)
);
CREATE INDEX IF NOT EXISTS idx_footage_proposal_segments_source
    ON footage_proposal_segments (source_segment_id, proposal_id);
CREATE TABLE IF NOT EXISTS library_virtual_sequences (
    sequence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES library_footage_sources(source_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS library_virtual_sequence_items (
    item_id TEXT PRIMARY KEY,
    sequence_id TEXT NOT NULL,
    item_order INTEGER NOT NULL CHECK (item_order >= 1),
    source_segment_id TEXT NOT NULL,
    start_sec REAL,
    end_sec REAL,
    FOREIGN KEY (sequence_id) REFERENCES library_virtual_sequences(sequence_id) ON DELETE CASCADE,
    FOREIGN KEY (source_segment_id) REFERENCES library_source_segments(segment_id) ON DELETE RESTRICT,
    CHECK ((start_sec IS NULL AND end_sec IS NULL) OR (start_sec >= 0 AND end_sec > start_sec)),
    UNIQUE (sequence_id, item_order)
);
CREATE INDEX IF NOT EXISTS idx_library_virtual_sequence_items_order
    ON library_virtual_sequence_items (sequence_id, item_order);
CREATE TRIGGER IF NOT EXISTS footage_sources_require_asset_insert
BEFORE INSERT ON library_footage_sources
WHEN NEW.library_asset_id IS NULL OR trim(NEW.library_asset_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'library_asset_id is required');
END;
CREATE TRIGGER IF NOT EXISTS footage_sources_require_asset_update
BEFORE UPDATE OF library_asset_id ON library_footage_sources
WHEN NEW.library_asset_id IS NULL OR trim(NEW.library_asset_id) = ''
BEGIN
    SELECT RAISE(ABORT, 'library_asset_id is required');
END;
CREATE TRIGGER IF NOT EXISTS footage_sources_require_canonical_asset_insert
BEFORE INSERT ON library_footage_sources
WHEN NOT EXISTS (
    SELECT 1 FROM library_user_assets
    WHERE library_asset_id = NEW.library_asset_id
      AND content_sha256 = NEW.source_sha256
)
BEGIN
    SELECT RAISE(ABORT, 'source must reference canonical library asset');
END;
CREATE TRIGGER IF NOT EXISTS footage_sources_require_canonical_asset_update
BEFORE UPDATE OF library_asset_id, source_sha256 ON library_footage_sources
WHEN NOT EXISTS (
    SELECT 1 FROM library_user_assets
    WHERE library_asset_id = NEW.library_asset_id
      AND content_sha256 = NEW.source_sha256
)
BEGIN
    SELECT RAISE(ABORT, 'source must reference canonical library asset');
END;
CREATE TRIGGER IF NOT EXISTS footage_sources_identity_immutable
BEFORE UPDATE OF source_id, source_sha256, library_asset_id ON library_footage_sources
WHEN NEW.source_id <> OLD.source_id
  OR NEW.source_sha256 <> OLD.source_sha256
  OR COALESCE(NEW.library_asset_id, '') <> COALESCE(OLD.library_asset_id, '')
BEGIN
    SELECT RAISE(ABORT, 'footage source identity is immutable');
END;
CREATE TRIGGER IF NOT EXISTS source_segments_finite_bounds_insert
BEFORE INSERT ON library_source_segments
WHEN NOT (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec
          AND NEW.start_sec < 1.7976931348623157e+308
          AND NEW.end_sec < 1.7976931348623157e+308)
BEGIN
    SELECT RAISE(ABORT, 'source segment boundaries must be finite');
END;
CREATE TRIGGER IF NOT EXISTS source_segments_finite_bounds_update
BEFORE UPDATE OF source_id, source_sha256, start_sec, end_sec ON library_source_segments
WHEN NEW.source_id <> OLD.source_id
  OR NEW.source_sha256 <> OLD.source_sha256
  OR NEW.start_sec <> OLD.start_sec
  OR NEW.end_sec <> OLD.end_sec
  OR NOT (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec
          AND NEW.start_sec < 1.7976931348623157e+308
          AND NEW.end_sec < 1.7976931348623157e+308)
BEGIN
    SELECT RAISE(ABORT, 'source segment identity or boundaries are immutable');
END;
CREATE TRIGGER IF NOT EXISTS source_segments_parent_hash_insert
BEFORE INSERT ON library_source_segments
WHEN NOT EXISTS (
    SELECT 1 FROM library_footage_sources s
    JOIN library_user_assets a ON a.library_asset_id = s.library_asset_id
    WHERE s.source_id = NEW.source_id AND s.source_sha256 = NEW.source_sha256
      AND trim(COALESCE(s.library_asset_id, '')) <> ''
      AND lower(a.content_sha256) = lower(s.source_sha256)
)
BEGIN
    SELECT RAISE(ABORT, 'source segment hash does not match source');
END;
CREATE TRIGGER IF NOT EXISTS footage_proposals_identity_immutable
BEFORE UPDATE OF proposal_id, source_id, source_sha256 ON footage_proposals
WHEN NEW.proposal_id <> OLD.proposal_id OR NEW.source_id <> OLD.source_id OR NEW.source_sha256 <> OLD.source_sha256
BEGIN SELECT RAISE(ABORT, 'footage proposal identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS footage_proposals_parent_hash_insert
BEFORE INSERT ON footage_proposals
WHEN NOT EXISTS (SELECT 1 FROM library_footage_sources WHERE source_id = NEW.source_id AND source_sha256 = NEW.source_sha256 AND trim(COALESCE(library_asset_id, '')) <> '')
BEGIN SELECT RAISE(ABORT, 'footage proposal source hash does not match source'); END;
CREATE TRIGGER IF NOT EXISTS footage_proposals_parent_hash_update
BEFORE UPDATE OF source_id, source_sha256 ON footage_proposals
WHEN NOT EXISTS (SELECT 1 FROM library_footage_sources WHERE source_id = NEW.source_id AND source_sha256 = NEW.source_sha256 AND trim(COALESCE(library_asset_id, '')) <> '')
BEGIN SELECT RAISE(ABORT, 'footage proposal source hash does not match source'); END;
CREATE TRIGGER IF NOT EXISTS footage_proposal_segments_integrity_insert
BEFORE INSERT ON footage_proposal_segments
WHEN NOT (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec AND NEW.start_sec < 1.7976931348623157e+308 AND NEW.end_sec < 1.7976931348623157e+308)
  OR NOT EXISTS (
      SELECT 1 FROM footage_proposals p
      JOIN library_source_segments s ON s.segment_id = NEW.source_segment_id
      JOIN library_footage_sources src ON src.source_id = p.source_id
      JOIN library_user_assets a ON a.library_asset_id = src.library_asset_id
      WHERE p.proposal_id = NEW.proposal_id AND p.source_id = s.source_id
        AND p.source_sha256 = NEW.source_sha256 AND s.source_sha256 = NEW.source_sha256
        AND trim(COALESCE(src.library_asset_id, '')) <> ''
        AND lower(a.content_sha256) = lower(src.source_sha256)
  )
BEGIN SELECT RAISE(ABORT, 'footage proposal segment integrity violation'); END;
CREATE TRIGGER IF NOT EXISTS footage_proposal_segments_integrity_update
BEFORE UPDATE OF proposal_id, source_segment_id, source_sha256, start_sec, end_sec ON footage_proposal_segments
WHEN NEW.proposal_id <> OLD.proposal_id OR NEW.source_segment_id <> OLD.source_segment_id OR NEW.source_sha256 <> OLD.source_sha256
  OR NOT (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec AND NEW.start_sec < 1.7976931348623157e+308 AND NEW.end_sec < 1.7976931348623157e+308)
BEGIN SELECT RAISE(ABORT, 'footage proposal segment identity or boundaries are immutable'); END;
CREATE TRIGGER IF NOT EXISTS virtual_sequences_identity_immutable
BEFORE UPDATE OF sequence_id, source_id, source_sha256 ON library_virtual_sequences
WHEN NEW.sequence_id <> OLD.sequence_id OR NEW.source_id <> OLD.source_id OR NEW.source_sha256 <> OLD.source_sha256
BEGIN SELECT RAISE(ABORT, 'virtual sequence identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS virtual_sequences_parent_hash_insert
BEFORE INSERT ON library_virtual_sequences
WHEN NOT EXISTS (SELECT 1 FROM library_footage_sources WHERE source_id = NEW.source_id AND source_sha256 = NEW.source_sha256 AND trim(COALESCE(library_asset_id, '')) <> '')
BEGIN SELECT RAISE(ABORT, 'virtual sequence source hash does not match source'); END;
CREATE TRIGGER IF NOT EXISTS virtual_sequences_parent_hash_update
BEFORE UPDATE OF source_id, source_sha256 ON library_virtual_sequences
WHEN NOT EXISTS (SELECT 1 FROM library_footage_sources WHERE source_id = NEW.source_id AND source_sha256 = NEW.source_sha256 AND trim(COALESCE(library_asset_id, '')) <> '')
BEGIN SELECT RAISE(ABORT, 'virtual sequence source hash does not match source'); END;
CREATE TRIGGER IF NOT EXISTS virtual_sequence_items_integrity_insert
BEFORE INSERT ON library_virtual_sequence_items
WHEN NOT ((NEW.start_sec IS NULL AND NEW.end_sec IS NULL) OR (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec AND NEW.start_sec < 1.7976931348623157e+308 AND NEW.end_sec < 1.7976931348623157e+308))
  OR NOT EXISTS (
      SELECT 1 FROM library_virtual_sequences v
      JOIN library_source_segments s ON s.segment_id = NEW.source_segment_id
      WHERE v.sequence_id = NEW.sequence_id AND v.source_id = s.source_id
        AND v.source_sha256 = s.source_sha256
  )
BEGIN SELECT RAISE(ABORT, 'virtual sequence item boundaries must be finite'); END;
CREATE TRIGGER IF NOT EXISTS virtual_sequence_items_integrity_update
BEFORE UPDATE OF sequence_id, source_segment_id, start_sec, end_sec, item_order ON library_virtual_sequence_items
WHEN NEW.sequence_id <> OLD.sequence_id OR NEW.source_segment_id <> OLD.source_segment_id
  OR NOT ((NEW.start_sec IS NULL AND NEW.end_sec IS NULL) OR (NEW.start_sec >= 0 AND NEW.end_sec > NEW.start_sec AND NEW.start_sec < 1.7976931348623157e+308 AND NEW.end_sec < 1.7976931348623157e+308))
BEGIN SELECT RAISE(ABORT, 'virtual sequence item identity or boundaries are immutable'); END;
"""


class OptimisticRevisionConflict(RuntimeError):
    """The caller attempted to update a proposal using an old revision."""


def ensure_footage_organizer_schema(connection: sqlite3.Connection) -> None:
    """Install only additive tables; safe to run for every global DB connection."""
    # Trigger bodies are additive schema code, but ``IF NOT EXISTS`` would
    # leave an older body in a database migrated by a prior release. Replace
    # only the hardened guards so existing global libraries receive them.
    for trigger in (
        "source_segments_finite_bounds_update",
        "source_segments_parent_hash_insert",
        "footage_proposal_segments_integrity_insert",
        "virtual_sequence_items_integrity_insert",
    ):
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    connection.executescript(FOOTAGE_ORGANIZER_SCHEMA)
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(library_footage_sources)")}
    if "library_asset_id" not in columns:
        try:
            connection.execute("ALTER TABLE library_footage_sources ADD COLUMN library_asset_id TEXT REFERENCES library_user_assets(library_asset_id) ON DELETE RESTRICT")
        except sqlite3.OperationalError as error:
            # Another connection may have added the same additive column.  A
            # lock/error other than the documented duplicate is real and must
            # not be hidden by migration retries.
            if "duplicate column name" not in str(error).lower():
                raise


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True)


def _from_time(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class FootageOrganizerStore:
    """Store source references, proposals, and virtual sequences in the library DB."""

    def __init__(self, root: Path | Any) -> None:
        # ``Path.root`` is the filesystem anchor (``\\`` on Windows), not a
        # library-store root.  Only unwrap an actual store facade here.
        self.root = Path(root) if isinstance(root, (str, Path)) else Path(root.root)
        self.database_path = self.root / "media_library.sqlite"

    def register_source(
        self, *, source_id: str, source_sha256: str, library_asset_id: str, filename: str = ""
    ) -> FootageSource:
        if not isinstance(library_asset_id, str) or not library_asset_id.strip():
            raise ValueError("library_asset_id is required")
        source = FootageSource.create(
            source_id=source_id, source_sha256=source_sha256, filename=filename,
            library_asset_id=library_asset_id,
        )
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM library_footage_sources WHERE source_id = ?", (source.source_id,)
            ).fetchone()
            if existing is not None:
                if str(existing["source_sha256"]) != source.source_sha256:
                    raise ValueError("source hash is immutable")
                if str(existing["library_asset_id"]) != source.library_asset_id:
                    raise ValueError("source identity is immutable")
                connection.commit()
                return self._source_row(existing)
            asset_row = connection.execute(
                "SELECT content_sha256 FROM library_user_assets WHERE library_asset_id = ?",
                (source.library_asset_id,),
            ).fetchone()
            if asset_row is None:
                raise KeyError(f"library asset not found: {source.library_asset_id}")
            if str(asset_row["content_sha256"]).lower() != source.source_sha256:
                raise ValueError("source hash does not match canonical library asset")
            connection.execute(
                "INSERT INTO library_footage_sources (source_id, source_sha256, filename, created_at, library_asset_id) VALUES (?, ?, ?, ?, ?)",
                (source.source_id, source.source_sha256, source.filename, source.created_at.isoformat(), source.library_asset_id),
            )
            connection.commit()
            return source
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_source(self, source_id: str) -> FootageSource | None:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM library_footage_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
        finally:
            connection.close()
        return self._source_row(row) if row is not None else None

    def list_sources(self) -> list[FootageSource]:
        """Return only canonical sources; legacy orphan rows are quarantined."""
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT * FROM library_footage_sources ORDER BY created_at, source_id"
            ).fetchall()
        finally:
            connection.close()
        return [source for row in rows if (source := self._source_row(row)) is not None]

    def list_quarantined_sources(self) -> list[str]:
        """Report pre-canonical source rows without attempting to materialize them."""
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT source_id FROM library_footage_sources WHERE library_asset_id IS NULL OR trim(library_asset_id) = '' ORDER BY source_id"
            ).fetchall()
        finally:
            connection.close()
        return [str(row["source_id"]) for row in rows]

    def delete_source(self, source_id: str) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT library_asset_id FROM library_footage_sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if row is None:
                raise KeyError(source_id)
            if row["library_asset_id"] is None or not str(row["library_asset_id"]).strip():
                raise ValueError("source is quarantined: missing canonical library asset")
            connection.execute("DELETE FROM library_footage_sources WHERE source_id = ?", (source_id,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_source_segment(
        self,
        *,
        source_id: str,
        start_sec: float,
        end_sec: float,
        label: str = "",
        machine_fields: Mapping[str, Any] | None = None,
        segment_id: str | None = None,
    ) -> FootageSourceSegment:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            source_row = connection.execute(
                "SELECT source_sha256, library_asset_id FROM library_footage_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if source_row is None:
                raise KeyError(source_id)
            if source_row["library_asset_id"] is None or not str(source_row["library_asset_id"]).strip():
                raise ValueError("source is quarantined: missing canonical library asset")
            segment = FootageSourceSegment.create(
                source_id=source_id,
                source_sha256=str(source_row["source_sha256"]),
                start_sec=start_sec,
                end_sec=end_sec,
                label=label,
                machine_fields=machine_fields,
                segment_id=segment_id,
            )
            connection.execute(
                """INSERT INTO library_source_segments
                   (segment_id, source_id, source_sha256, start_sec, end_sec, label, machine_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (segment.segment_id, segment.source_id, segment.source_sha256, segment.start_sec,
                 segment.end_sec, segment.label, _json(segment.machine_fields), segment.created_at.isoformat()),
            )
            connection.commit()
            return segment
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_source_segment(self, *, segment_id: str, start_sec: float, end_sec: float) -> None:
        raise ValueError("source segment boundaries are immutable")

    def create_proposal(
        self,
        *,
        source_id: str,
        source_sha256: str,
        segments: Iterable[FootageSourceSegment | FootageProposalSegment],
        proposal_id: str | None = None,
        confirmed_fields: Mapping[str, Any] | None = None,
        machine_fields: Mapping[str, Any] | None = None,
    ) -> FootageProposal:
        proposal_id = proposal_id or f"fprop_{uuid4().hex}"
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            source_row = connection.execute(
                "SELECT source_sha256, library_asset_id FROM library_footage_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if source_row is None:
                raise KeyError(source_id)
            if source_row["library_asset_id"] is None or not str(source_row["library_asset_id"]).strip():
                raise ValueError("source is quarantined: missing canonical library asset")
            actual_hash = str(source_row["source_sha256"])
            if actual_hash != source_sha256.lower():
                raise ValueError("source hash does not match immutable source")
            normalized = self._proposal_segments(connection, source_id, actual_hash, segments)
            now = _now()
            connection.execute(
                """INSERT INTO footage_proposals
                   (proposal_id, source_id, source_sha256, status, revision, confirmed_json, machine_json, created_at, updated_at)
                   VALUES (?, ?, ?, 'draft', 1, ?, ?, ?, ?)""",
                (proposal_id, source_id, actual_hash, _json(confirmed_fields), _json(machine_fields), now, now),
            )
            self._insert_proposal_segments(connection, proposal_id, normalized)
            connection.commit()
            return FootageProposal(
                proposal_id, source_id, actual_hash, FootageProposalStatus.DRAFT, 1,
                tuple(normalized), dict(confirmed_fields or {}), dict(machine_fields or {}),
                _from_time(now), _from_time(now),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_proposal(self, proposal_id: str) -> FootageProposal | None:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM footage_proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                return None
            if not self._source_is_canonical(connection, str(row["source_id"]), str(row["source_sha256"])):
                return None
            segments = self._load_proposal_segments(connection, proposal_id)
        finally:
            connection.close()
        return self._proposal_row(row, segments)

    def set_proposal_status(
        self, *, proposal_id: str, status: FootageProposalStatus | str, expected_revision: int
    ) -> FootageProposal:
        try:
            target = FootageProposalStatus(status)
        except ValueError as error:
            raise ValueError("status must be draft, approved, rejected or stale") from error
        return self._update_proposal(
            proposal_id=proposal_id,
            expected_revision=expected_revision,
            status=target,
        )

    def confirm_proposal_fields(
        self, *, proposal_id: str, expected_revision: int, fields: Mapping[str, Any]
    ) -> FootageProposal:
        if not isinstance(fields, Mapping):
            raise ValueError("fields must be an object")
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._claim_revision(connection, proposal_id, expected_revision)
            confirmed = {**json.loads(str(row["confirmed_json"])), **dict(fields)}
            revision = int(row["revision"]) + 1
            now = _now()
            connection.execute(
                "UPDATE footage_proposals SET confirmed_json = ?, revision = ?, updated_at = ? WHERE proposal_id = ?",
                (_json(confirmed), revision, now, proposal_id),
            )
            connection.commit()
            return self.get_proposal(proposal_id)  # type: ignore[return-value]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reanalyze_proposal(
        self,
        *,
        proposal_id: str,
        expected_revision: int,
        segments: Iterable[FootageSourceSegment | FootageProposalSegment],
        machine_fields: Mapping[str, Any] | None = None,
    ) -> FootageProposal:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._claim_revision(connection, proposal_id, expected_revision)
            normalized = self._proposal_segments(
                connection, str(row["source_id"]), str(row["source_sha256"]), segments,
                old_segments=self._load_proposal_segments(connection, proposal_id),
            )
            revision = int(row["revision"]) + 1
            now = _now()
            connection.execute("DELETE FROM footage_proposal_segments WHERE proposal_id = ?", (proposal_id,))
            self._insert_proposal_segments(connection, proposal_id, normalized)
            connection.execute(
                "UPDATE footage_proposals SET machine_json = ?, revision = ?, updated_at = ? WHERE proposal_id = ?",
                (_json(machine_fields), revision, now, proposal_id),
            )
            connection.commit()
            return self.get_proposal(proposal_id)  # type: ignore[return-value]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_virtual_sequence(
        self,
        *,
        source_id: str,
        items: Iterable[VirtualSequenceItem],
        name: str = "",
        sequence_id: str | None = None,
    ) -> VirtualSequence:
        sequence_id = sequence_id or f"vseq_{uuid4().hex}"
        ordered = sorted(tuple(items), key=lambda item: item.item_order)
        if [item.item_order for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("sequence item order must be unique and contiguous")
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            source_row = connection.execute("SELECT source_sha256, library_asset_id FROM library_footage_sources WHERE source_id = ?", (source_id,)).fetchone()
            if source_row is None:
                raise KeyError(source_id)
            if source_row["library_asset_id"] is None or not str(source_row["library_asset_id"]).strip():
                raise ValueError("source is quarantined: missing canonical library asset")
            connection.execute(
                "INSERT INTO library_virtual_sequences (sequence_id, source_id, source_sha256, name, created_at) VALUES (?, ?, ?, ?, ?)",
                (sequence_id, source_id, str(source_row["source_sha256"]), name, _now()),
            )
            for item in ordered:
                segment = connection.execute("SELECT source_id FROM library_source_segments WHERE segment_id = ?", (item.source_segment_id,)).fetchone()
                if segment is None or str(segment["source_id"]) != source_id:
                    raise ValueError("sequence item references a segment from another source")
                connection.execute(
                    "INSERT INTO library_virtual_sequence_items (item_id, sequence_id, item_order, source_segment_id, start_sec, end_sec) VALUES (?, ?, ?, ?, ?, ?)",
                    (item.item_id, sequence_id, item.item_order, item.source_segment_id, item.start_sec, item.end_sec),
                )
            connection.commit()
            return VirtualSequence(sequence_id, source_id, str(source_row["source_sha256"]), tuple(ordered), name, 1)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_virtual_sequence(self, sequence_id: str) -> VirtualSequence | None:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM library_virtual_sequences WHERE sequence_id = ?", (sequence_id,)
            ).fetchone()
            if row is None:
                return None
            if not self._source_is_canonical(connection, str(row["source_id"]), str(row["source_sha256"])):
                return None
            item_rows = connection.execute(
                "SELECT * FROM library_virtual_sequence_items WHERE sequence_id = ? ORDER BY item_order",
                (sequence_id,),
            ).fetchall()
        finally:
            connection.close()
        items = tuple(
            VirtualSequenceItem.create(
                item_id=str(item["item_id"]),
                source_segment_id=str(item["source_segment_id"]),
                item_order=int(item["item_order"]),
                start_sec=float(item["start_sec"]) if item["start_sec"] is not None else None,
                end_sec=float(item["end_sec"]) if item["end_sec"] is not None else None,
            )
            for item in item_rows
        )
        return VirtualSequence(
            str(row["sequence_id"]), str(row["source_id"]), str(row["source_sha256"]),
            items, str(row["name"]), int(row["revision"]),
        )

    def list_proposals(self, *, source_id: str | None = None) -> list[FootageProposal]:
        connection = self._connection()
        try:
            if source_id is None:
                rows = connection.execute(
                    "SELECT * FROM footage_proposals ORDER BY updated_at, proposal_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM footage_proposals WHERE source_id = ? ORDER BY updated_at, proposal_id",
                    (source_id,),
                ).fetchall()
            result = []
            for row in rows:
                if self._source_is_canonical(connection, str(row["source_id"]), str(row["source_sha256"])):
                    result.append(self._proposal_row(row, self._load_proposal_segments(connection, str(row["proposal_id"]))))
            return result
        finally:
            connection.close()

    def _update_proposal(self, *, proposal_id: str, expected_revision: int, status: FootageProposalStatus) -> FootageProposal:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._claim_revision(connection, proposal_id, expected_revision)
            revision = int(row["revision"]) + 1
            now = _now()
            connection.execute("UPDATE footage_proposals SET status = ?, revision = ?, updated_at = ? WHERE proposal_id = ?", (status.value, revision, now, proposal_id))
            connection.commit()
            return self.get_proposal(proposal_id)  # type: ignore[return-value]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _claim_revision(connection: sqlite3.Connection, proposal_id: str, expected_revision: int) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM footage_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        if int(row["revision"]) != expected_revision:
            raise OptimisticRevisionConflict(f"proposal revision is {row['revision']}, expected {expected_revision}")
        return row

    @staticmethod
    def _proposal_segments(
        connection: sqlite3.Connection,
        source_id: str,
        source_sha256: str,
        segments: Iterable[FootageSourceSegment | FootageProposalSegment],
        old_segments: Iterable[FootageProposalSegment] = (),
    ) -> list[FootageProposalSegment]:
        old_confirmed = {segment.source_segment_id: dict(segment.confirmed_fields) for segment in old_segments}
        result: list[FootageProposalSegment] = []
        for value in segments:
            source_segment_id = value.segment_id if isinstance(value, FootageSourceSegment) else value.source_segment_id
            row = connection.execute("SELECT * FROM library_source_segments WHERE segment_id = ? AND source_id = ?", (source_segment_id, source_id)).fetchone()
            if row is None:
                raise ValueError("proposal segment must reference a source segment from its source")
            if str(row["source_sha256"]) != source_sha256:
                raise ValueError("source hash does not match immutable source")
            machine = value.machine_fields if isinstance(value, FootageSourceSegment) else value.machine_fields
            confirmed = old_confirmed.get(source_segment_id, {})
            if isinstance(value, FootageProposalSegment):
                confirmed = {**confirmed, **value.confirmed_fields}
            result.append(FootageProposalSegment.create(
                source_segment_id=source_segment_id,
                source_sha256=source_sha256,
                start_sec=float(row["start_sec"]),
                end_sec=float(row["end_sec"]),
                machine_fields=machine,
                confirmed_fields=confirmed,
            ))
        return result

    @staticmethod
    def _insert_proposal_segments(connection: sqlite3.Connection, proposal_id: str, segments: Iterable[FootageProposalSegment]) -> None:
        for order, segment in enumerate(segments, 1):
            connection.execute(
                """INSERT INTO footage_proposal_segments
                   (proposal_segment_id, proposal_id, segment_order, source_segment_id, source_sha256, start_sec, end_sec, machine_json, confirmed_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (segment.segment_id, proposal_id, order, segment.source_segment_id, segment.source_sha256,
                 segment.start_sec, segment.end_sec, _json(segment.machine_fields), _json(segment.confirmed_fields)),
            )

    @classmethod
    def _load_proposal_segments(cls, connection: sqlite3.Connection, proposal_id: str) -> list[FootageProposalSegment]:
        rows = connection.execute("SELECT * FROM footage_proposal_segments WHERE proposal_id = ? ORDER BY segment_order", (proposal_id,)).fetchall()
        return [FootageProposalSegment.create(
            segment_id=str(row["proposal_segment_id"]), source_segment_id=str(row["source_segment_id"]),
            source_sha256=str(row["source_sha256"]), start_sec=float(row["start_sec"]), end_sec=float(row["end_sec"]),
            machine_fields=json.loads(str(row["machine_json"])), confirmed_fields=json.loads(str(row["confirmed_json"])),
        ) for row in rows]

    @staticmethod
    def _proposal_row(row: sqlite3.Row, segments: Iterable[FootageProposalSegment]) -> FootageProposal:
        return FootageProposal(
            str(row["proposal_id"]), str(row["source_id"]), str(row["source_sha256"]),
            FootageProposalStatus(str(row["status"])), int(row["revision"]), tuple(segments),
            json.loads(str(row["confirmed_json"])), json.loads(str(row["machine_json"])),
            _from_time(row["created_at"]), _from_time(row["updated_at"]),
        )

    @staticmethod
    def _source_row(row: sqlite3.Row) -> FootageSource | None:
        if row["library_asset_id"] is None or not str(row["library_asset_id"]).strip():
            return None
        return FootageSource.create(source_id=str(row["source_id"]), source_sha256=str(row["source_sha256"]), filename=str(row["filename"]), library_asset_id=row["library_asset_id"], created_at=_from_time(row["created_at"]))

    @staticmethod
    def _source_is_canonical(connection: sqlite3.Connection, source_id: str, source_sha256: str) -> bool:
        row = connection.execute(
            """SELECT 1 FROM library_footage_sources s
               JOIN library_user_assets a ON a.library_asset_id = s.library_asset_id
               WHERE s.source_id = ? AND s.source_sha256 = ?
                 AND trim(COALESCE(s.library_asset_id, '')) <> ''
                 AND lower(a.content_sha256) = lower(s.source_sha256)""",
            (source_id, source_sha256),
        ).fetchone()
        return row is not None

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_library_user_asset_schema(connection)
        ensure_footage_organizer_schema(connection)
        return connection
