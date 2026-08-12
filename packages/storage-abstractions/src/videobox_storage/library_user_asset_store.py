"""SQLite authority for owner-managed global media assets.

The verified starter-pack tables in :mod:`media_library_store` are immutable
installation metadata.  This store is deliberately additive and owns the
copy/ingest lifecycle for user files and explicit project references.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4

from videobox_domain_models.library_assets import (
    LibraryAssetLifecycle,
    LibraryAssetOrigin,
    LibraryMediaType,
    LibraryUserAsset,
)


LIBRARY_USER_ASSET_SCHEMA = """
CREATE TABLE IF NOT EXISTS library_user_assets (
    library_asset_id TEXT PRIMARY KEY,
    media_type TEXT NOT NULL CHECK (media_type IN ('broll', 'music', 'sfx')),
    origin TEXT NOT NULL CHECK (origin IN ('builtin', 'user')),
    lifecycle TEXT NOT NULL CHECK (lifecycle IN ('processing', 'ready', 'needs_attention', 'trashed')),
    content_sha256 TEXT NOT NULL UNIQUE,
    managed_relative_path TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    mime_type TEXT NOT NULL,
    technical_json TEXT NOT NULL DEFAULT '{}',
    machine_json TEXT NOT NULL DEFAULT '{}',
    user_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    trashed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_library_user_assets_type_lifecycle
    ON library_user_assets (media_type, lifecycle, updated_at);
CREATE TABLE IF NOT EXISTS library_asset_derivatives (
    derivative_id TEXT PRIMARY KEY,
    library_asset_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    managed_relative_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    mime_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (library_asset_id) REFERENCES library_user_assets(library_asset_id) ON DELETE CASCADE,
    UNIQUE (library_asset_id, kind)
);
CREATE TABLE IF NOT EXISTS library_ingest_batches (
    ingest_batch_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'processing',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library_ingest_items (
    ingest_item_id TEXT PRIMARY KEY,
    ingest_batch_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    library_asset_id TEXT,
    filename TEXT NOT NULL,
    state TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (ingest_batch_id) REFERENCES library_ingest_batches(ingest_batch_id) ON DELETE CASCADE,
    FOREIGN KEY (library_asset_id) REFERENCES library_user_assets(library_asset_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_library_ingest_items_batch
    ON library_ingest_items (ingest_batch_id, created_at);
CREATE TABLE IF NOT EXISTS library_project_references (
    reference_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    library_asset_id TEXT NOT NULL,
    materialized_asset_id TEXT,
    location_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (library_asset_id) REFERENCES library_user_assets(library_asset_id) ON DELETE RESTRICT,
    UNIQUE (project_id, library_asset_id, materialized_asset_id)
);
CREATE INDEX IF NOT EXISTS idx_library_project_references_asset
    ON library_project_references (library_asset_id, project_id);
"""


def ensure_library_user_asset_schema(connection: sqlite3.Connection) -> None:
    """Create the additive global-library tables safely on every connection."""
    connection.executescript(LIBRARY_USER_ASSET_SCHEMA)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("managed_relative_path is required")
    normalized = value.replace("\\", "/").strip("/")
    windows = PureWindowsPath(value)
    parts = PurePosixPath(normalized).parts
    if windows.drive or value.startswith(("/", "\\")) or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("managed_relative_path must be a safe relative path")
    return normalized


def _json(value: Mapping[str, Any] | None) -> str:
    if value is None:
        return "{}"
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be an object")
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)


class LibraryUserAssetStore:
    """Persistent global user-media store backed by one SQLite database."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.database_path = self.root / "media_library.sqlite"

    def register_asset(self, **kwargs: Any) -> LibraryUserAsset:
        """Insert an asset or return the existing row with the same content hash."""
        asset = LibraryUserAsset.create(**kwargs)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM library_user_assets WHERE content_sha256 = ?",
                (asset.content_sha256,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return LibraryUserAsset.from_row(dict(existing))
            connection.execute(
                """
                INSERT INTO library_user_assets (
                    library_asset_id, media_type, origin, lifecycle, content_sha256,
                    managed_relative_path, byte_count, mime_type, technical_json,
                    machine_json, user_json, provenance_json, created_at, updated_at, trashed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.library_asset_id, asset.media_type.value, asset.origin.value,
                    asset.lifecycle.value, asset.content_sha256, _safe_relative_path(asset.managed_relative_path),
                    asset.byte_count, asset.mime_type, _json(asset.technical_metadata),
                    _json(asset.machine_metadata), _json(asset.user_metadata), _json(asset.provenance),
                    asset.created_at.isoformat(), asset.updated_at.isoformat(),
                    asset.trashed_at.isoformat() if asset.trashed_at else None,
                ),
            )
            connection.commit()
            return asset
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # Explicit name used by ingest/materializer callers.
    create_asset = register_asset

    def create_user_asset(self, **kwargs: Any) -> LibraryUserAsset:
        return self.register_asset(**kwargs)

    def get_asset(self, library_asset_id: str) -> LibraryUserAsset | None:
        connection = self._connection()
        try:
            row = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
        finally:
            connection.close()
        return LibraryUserAsset.from_row(dict(row)) if row is not None else None

    def find_by_content_sha256(self, content_sha256: str) -> LibraryUserAsset | None:
        connection = self._connection()
        try:
            row = connection.execute("SELECT * FROM library_user_assets WHERE content_sha256 = ?", (content_sha256.lower(),)).fetchone()
        finally:
            connection.close()
        return LibraryUserAsset.from_row(dict(row)) if row is not None else None

    # Alias matching content-addressed terminology in the ingest plan.
    get_by_content_sha256 = find_by_content_sha256
    find_by_hash = find_by_content_sha256

    def list_assets(
        self,
        *,
        media_type: LibraryMediaType | str | None = None,
        origin: LibraryAssetOrigin | str | None = None,
        lifecycle: LibraryAssetLifecycle | str | None = None,
        include_trashed: bool = False,
    ) -> list[LibraryUserAsset]:
        clauses: list[str] = []
        values: list[Any] = []
        if media_type is not None:
            clauses.append("media_type = ?"); values.append(LibraryMediaType(media_type).value)
        if origin is not None:
            clauses.append("origin = ?"); values.append(LibraryAssetOrigin(origin).value)
        if lifecycle is not None:
            clauses.append("lifecycle = ?"); values.append(LibraryAssetLifecycle(lifecycle).value)
        elif not include_trashed:
            clauses.append("lifecycle <> 'trashed'")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        connection = self._connection()
        try:
            rows = connection.execute(f"SELECT * FROM library_user_assets{where} ORDER BY created_at, library_asset_id", values).fetchall()
        finally:
            connection.close()
        return [LibraryUserAsset.from_row(dict(row)) for row in rows]

    def update_lifecycle(self, library_asset_id: str, lifecycle: LibraryAssetLifecycle | str) -> LibraryUserAsset:
        target = LibraryAssetLifecycle(lifecycle)
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            if row is None:
                raise KeyError(library_asset_id)
            if target is LibraryAssetLifecycle.TRASHED and str(row["origin"]) == LibraryAssetOrigin.BUILTIN.value:
                raise ValueError("builtin assets cannot be trashed")
            trashed_at = _now() if target is LibraryAssetLifecycle.TRASHED else None
            connection.execute("UPDATE library_user_assets SET lifecycle = ?, trashed_at = ?, updated_at = ? WHERE library_asset_id = ?", (target.value, trashed_at, _now(), library_asset_id))
            updated = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            connection.commit()
            assert updated is not None
            return LibraryUserAsset.from_row(dict(updated))
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    def trash_asset(self, library_asset_id: str) -> LibraryUserAsset:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            if row is None:
                raise KeyError(library_asset_id)
            refs = connection.execute("SELECT reference_id FROM library_project_references WHERE library_asset_id = ? LIMIT 1", (library_asset_id,)).fetchone()
            if refs is not None:
                raise ValueError(f"asset has project reference: {refs[0]}")
            if str(row["origin"]) == LibraryAssetOrigin.BUILTIN.value:
                raise ValueError("builtin assets cannot be trashed")
            now = _now()
            connection.execute("UPDATE library_user_assets SET lifecycle = 'trashed', trashed_at = ?, updated_at = ? WHERE library_asset_id = ?", (now, now, library_asset_id))
            updated = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            connection.commit()
            assert updated is not None
            return LibraryUserAsset.from_row(dict(updated))
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    trash = trash_asset

    def restore_asset(self, library_asset_id: str) -> LibraryUserAsset:
        asset = self.get_asset(library_asset_id)
        if asset is None:
            raise KeyError(library_asset_id)
        if asset.origin is LibraryAssetOrigin.BUILTIN:
            raise ValueError("builtin assets cannot be restored")
        return self.update_lifecycle(library_asset_id, LibraryAssetLifecycle.READY)

    restore = restore_asset

    def permanently_delete_asset(self, library_asset_id: str) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT origin, lifecycle FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            if row is None:
                raise KeyError(library_asset_id)
            if str(row["origin"]) == LibraryAssetOrigin.BUILTIN.value:
                raise ValueError("builtin assets cannot be permanently deleted")
            refs = connection.execute("SELECT reference_id FROM library_project_references WHERE library_asset_id = ? LIMIT 1", (library_asset_id,)).fetchone()
            if refs is not None:
                raise ValueError(f"asset has project reference: {refs[0]}")
            connection.execute("DELETE FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,))
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    permanently_delete = permanently_delete_asset

    def add_project_reference(
        self,
        *,
        project_id: str,
        library_asset_id: str,
        location: Mapping[str, Any] | None = None,
        materialized_asset_id: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        if not project_id.strip():
            raise ValueError("project_id is required")
        if self.get_asset(library_asset_id) is None:
            raise KeyError(library_asset_id)
        result = {"reference_id": reference_id or f"ref_{uuid4().hex}", "project_id": project_id, "library_asset_id": library_asset_id, "materialized_asset_id": materialized_asset_id, "location": dict(location or {}), "created_at": _now()}
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM library_project_references WHERE project_id = ? AND library_asset_id = ? AND materialized_asset_id IS ?", (project_id, library_asset_id, materialized_asset_id)).fetchone()
            if existing is not None:
                result = self._reference_row(dict(existing))
            else:
                connection.execute("INSERT INTO library_project_references (reference_id, project_id, library_asset_id, materialized_asset_id, location_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (result["reference_id"], project_id, library_asset_id, materialized_asset_id, _json(result["location"]), result["created_at"]))
            connection.commit()
            return result
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    add_reference = add_project_reference

    def remove_project_reference(self, reference_id: str) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM library_project_references WHERE reference_id = ?", (reference_id,))
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    remove_reference = remove_project_reference

    def list_project_references(self, *, library_asset_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []; values: list[Any] = []
        if library_asset_id is not None: clauses.append("library_asset_id = ?"); values.append(library_asset_id)
        if project_id is not None: clauses.append("project_id = ?"); values.append(project_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        connection = self._connection()
        try: rows = connection.execute(f"SELECT * FROM library_project_references{where} ORDER BY created_at, reference_id", values).fetchall()
        finally: connection.close()
        return [self._reference_row(dict(row)) for row in rows]

    def usage(self, library_asset_id: str) -> list[dict[str, Any]]:
        return self.list_project_references(library_asset_id=library_asset_id)

    get_usage = usage

    def create_ingest_batch(self, *, idempotency_key: str, provenance: Mapping[str, Any] | None = None, state: str = "processing") -> dict[str, Any]:
        now = _now(); batch_id = f"batch_{uuid4().hex}"
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM library_ingest_batches WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing is not None:
                connection.commit(); return self._batch_row(dict(existing))
            connection.execute("INSERT INTO library_ingest_batches VALUES (?, ?, ?, ?, ?, ?)", (batch_id, idempotency_key, _json(provenance), state, now, now))
            connection.commit()
            return {"ingest_batch_id": batch_id, "idempotency_key": idempotency_key, "provenance": dict(provenance or {}), "state": state, "created_at": now, "updated_at": now}
        except Exception:
            connection.rollback(); raise
        finally: connection.close()

    def record_ingest_item(self, *, batch_id: str, idempotency_key: str, library_asset_id: str | None, filename: str, state: str, error_code: str | None = None) -> dict[str, Any]:
        now = _now(); item_id = f"item_{uuid4().hex}"
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM library_ingest_items WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing is not None:
                connection.commit(); return self._ingest_item_row(dict(existing))
            connection.execute("INSERT INTO library_ingest_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (item_id, batch_id, idempotency_key, library_asset_id, filename, state, error_code, now, now))
            connection.commit()
            return {"ingest_item_id": item_id, "ingest_batch_id": batch_id, "idempotency_key": idempotency_key, "library_asset_id": library_asset_id, "filename": filename, "state": state, "error_code": error_code, "created_at": now, "updated_at": now}
        except Exception:
            connection.rollback(); raise
        finally: connection.close()

    def get_ingest_item(self, idempotency_key: str) -> dict[str, Any] | None:
        """Return one durable ingest item for response-loss reconciliation."""
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM library_ingest_items WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        finally:
            connection.close()
        return self._ingest_item_row(dict(row)) if row is not None else None

    def update_ingest_item(
        self,
        *,
        idempotency_key: str,
        library_asset_id: str | None = None,
        state: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        """Advance an existing item without creating a second retry row."""
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM library_ingest_items WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise KeyError(idempotency_key)
            connection.execute(
                """UPDATE library_ingest_items
                   SET library_asset_id = COALESCE(?, library_asset_id),
                       state = COALESCE(?, state), error_code = ?, updated_at = ?
                   WHERE idempotency_key = ?""",
                (library_asset_id, state, error_code, _now(), idempotency_key),
            )
            updated = connection.execute(
                "SELECT * FROM library_ingest_items WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            connection.commit()
            assert updated is not None
            return self._ingest_item_row(dict(updated))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_derivative(self, *, library_asset_id: str, kind: str, managed_relative_path: str, content_sha256: str, byte_count: int, mime_type: str, metadata: Mapping[str, Any] | None = None, derivative_id: str | None = None) -> dict[str, Any]:
        if self.get_asset(library_asset_id) is None: raise KeyError(library_asset_id)
        result = {"derivative_id": derivative_id or f"derivative_{uuid4().hex}", "library_asset_id": library_asset_id, "kind": kind, "managed_relative_path": _safe_relative_path(managed_relative_path), "content_sha256": content_sha256, "byte_count": byte_count, "mime_type": mime_type, "metadata": dict(metadata or {}), "created_at": _now()}
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM library_asset_derivatives WHERE library_asset_id = ? AND kind = ?", (library_asset_id, kind)).fetchone()
            if existing is not None: result = self._derivative_row(dict(existing))
            else: connection.execute("INSERT INTO library_asset_derivatives VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (result["derivative_id"], library_asset_id, kind, result["managed_relative_path"], content_sha256, byte_count, mime_type, _json(result["metadata"]), result["created_at"]))
            connection.commit(); return result
        except Exception: connection.rollback(); raise
        finally: connection.close()

    def _assert_no_references(self, library_asset_id: str) -> None:
        refs = self.list_project_references(library_asset_id=library_asset_id)
        if refs: raise ValueError(f"asset has project reference: {refs[0]['reference_id']}")

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        ensure_library_user_asset_schema(connection)
        return connection

    @staticmethod
    def _reference_row(row: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(row); row["location"] = json.loads(str(row.pop("location_json", "{}"))); return row

    @staticmethod
    def _batch_row(row: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(row); row["provenance"] = json.loads(str(row.pop("provenance_json", "{}"))); return row

    @staticmethod
    def _ingest_item_row(row: Mapping[str, Any]) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _derivative_row(row: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(row); row["metadata"] = json.loads(str(row.pop("metadata_json", "{}"))); return row
