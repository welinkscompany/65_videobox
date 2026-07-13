from __future__ import annotations

import sqlite3
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


class MediaLibraryStore:
    """Global, optional index for verified installed media packs.

    This database intentionally has no dependency on project databases.  A
    failure to open it must therefore be handled by library callers, never by
    the project editing path.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.database_path = self.root / "media_library.sqlite"
        self._verification_cache: dict[tuple[str, int, int, str], bool] = {}

    def index_verified_pack(
        self,
        *,
        pack_id: str,
        version: str,
        install_path: Path,
        assets: Iterable[dict[str, Any]],
        active: bool = True,
    ) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if active:
                connection.execute("UPDATE media_packs SET active = 0 WHERE pack_id = ?", (pack_id,))
            connection.execute(
                """
                INSERT INTO media_packs (pack_id, version, install_path, verified, active, installed_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(pack_id, version) DO UPDATE SET
                    install_path = excluded.install_path, verified = 1, active = excluded.active
                """,
                (pack_id, version, str(install_path), int(active), self._now()),
            )
            for asset in assets:
                license_data = asset["license"]
                assert isinstance(license_data, dict)
                connection.execute(
                    """
                    INSERT INTO media_assets (
                        pack_id, version, library_asset_id, asset_id, media_type, duration_seconds,
                        sha256, path, source, creator, official_license_url,
                        evidence_timestamp, evidence_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pack_id, version, library_asset_id) DO UPDATE SET
                        asset_id = excluded.asset_id, media_type = excluded.media_type,
                        duration_seconds = excluded.duration_seconds, sha256 = excluded.sha256,
                        path = excluded.path, source = excluded.source, creator = excluded.creator,
                        official_license_url = excluded.official_license_url,
                        evidence_timestamp = excluded.evidence_timestamp, evidence_sha256 = excluded.evidence_sha256
                    """,
                    (
                        pack_id, version, asset["library_asset_id"], asset["asset_id"], asset["media_type"],
                        asset["duration_seconds"], asset["sha256"], str(asset["path"]), asset["source"],
                        asset["creator"], license_data["official_url"], license_data["evidence_timestamp"],
                        license_data["evidence_sha256"],
                    ),
                )
                # Evidence records are append-only: package evidence is never rewritten.
                connection.execute(
                    """
                    INSERT OR IGNORE INTO license_evidence (
                        pack_id, version, library_asset_id, official_url, evidence_timestamp, evidence_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (pack_id, version, asset["library_asset_id"], license_data["official_url"], license_data["evidence_timestamp"], license_data["evidence_sha256"]),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def activate_pack(self, *, pack_id: str, version: str, install_path: Path) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE media_packs SET active = 0 WHERE pack_id = ?", (pack_id,))
            cursor = connection.execute(
                """UPDATE media_packs SET active = 1, install_path = ?
                   WHERE pack_id = ? AND version = ? AND verified = 1""",
                (str(install_path), pack_id, version),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Verified pack not indexed: {pack_id}@{version}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def is_active_verified_pack(self, *, pack_id: str, version: str, install_path: Path) -> bool:
        connection = self._connection()
        try:
            row = connection.execute(
                """SELECT 1 FROM media_packs
                   WHERE pack_id = ? AND version = ? AND install_path = ? AND verified = 1 AND active = 1""",
                (pack_id, version, str(install_path)),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def get_pack(self, *, pack_id: str, version: str) -> dict[str, Any] | None:
        connection = self._connection()
        try:
            row = connection.execute("SELECT pack_id, version, install_path, verified, active, installed_at FROM media_packs WHERE pack_id = ? AND version = ?", (pack_id, version)).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    def remove_pack(self, *, pack_id: str, version: str) -> None:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT active FROM media_packs WHERE pack_id = ? AND version = ?", (pack_id, version)).fetchone()
            if row is not None and bool(row[0]):
                raise ValueError("active pack versions cannot be removed")
            connection.execute("DELETE FROM media_packs WHERE pack_id = ? AND version = ?", (pack_id, version))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def remove_inactive_versions(self, *, pack_id: str) -> list[str]:
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT version FROM media_packs WHERE pack_id = ? AND active = 0 ORDER BY version", (pack_id,)
            ).fetchall()
            connection.execute("DELETE FROM media_packs WHERE pack_id = ? AND active = 0", (pack_id,))
            connection.commit()
            return [str(row[0]) for row in rows]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def search(self, *, query: str | None = None) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT a.library_asset_id, a.asset_id, a.media_type, a.duration_seconds, a.sha256,
                       a.path, a.source, a.creator, a.official_license_url, a.evidence_timestamp,
                       a.evidence_sha256, a.version
                FROM media_assets a
                JOIN media_packs p ON p.pack_id = a.pack_id AND p.version = a.version
                WHERE p.active = 1 AND p.verified = 1
                ORDER BY a.library_asset_id
                """
            ).fetchall()
        finally:
            connection.close()
        normalized_query = (query or "").strip().lower()
        results = [dict(row) for row in rows if self._is_currently_verified(Path(str(row["path"])), str(row["sha256"]))]
        if not normalized_query:
            return results
        return [item for item in results if normalized_query in " ".join(map(str, item.values())).lower()]

    def get_verified_asset(self, *, library_asset_id: str) -> dict[str, Any] | None:
        """Return one currently active, checksum-verified library asset."""
        for asset in self.search():
            if str(asset["library_asset_id"]) == library_asset_id:
                return asset
        return None

    def _is_currently_verified(self, path: Path, expected_sha256: str) -> bool:
        try:
            stat = path.stat()
            if not path.is_file():
                return False
            resolved_path = str(path.resolve())
            key = (resolved_path, stat.st_size, stat.st_mtime_ns, expected_sha256)
            cached = self._verification_cache.get(key)
            if cached is not None:
                return cached
            verified = _sha256_file(path) == expected_sha256
        except OSError:
            return False
        self._verification_cache[key] = verified
        return verified

    def set_favorite(self, *, library_asset_id: str, enabled: bool) -> None:
        connection = self._connection()
        try:
            if enabled:
                connection.execute("INSERT OR IGNORE INTO library_favorites (library_asset_id, created_at) VALUES (?, ?)", (library_asset_id, self._now()))
            else:
                connection.execute("DELETE FROM library_favorites WHERE library_asset_id = ?", (library_asset_id,))
            connection.commit()
        finally:
            connection.close()

    def list_favorites(self) -> list[str]:
        connection = self._connection()
        try:
            return [str(row[0]) for row in connection.execute("SELECT library_asset_id FROM library_favorites ORDER BY created_at DESC, library_asset_id").fetchall()]
        finally:
            connection.close()

    def mark_recent_usage(self, *, library_asset_id: str) -> None:
        connection = self._connection()
        try:
            connection.execute("INSERT INTO recent_library_usage (library_asset_id, used_at) VALUES (?, ?) ON CONFLICT(library_asset_id) DO UPDATE SET used_at = excluded.used_at", (library_asset_id, self._now()))
            connection.commit()
        finally:
            connection.close()

    def list_recent_usage(self) -> list[str]:
        connection = self._connection()
        try:
            return [str(row[0]) for row in connection.execute("SELECT library_asset_id FROM recent_library_usage ORDER BY used_at DESC, library_asset_id").fetchall()]
        finally:
            connection.close()

    def get_license_evidence(self, *, pack_id: str, version: str, library_asset_id: str) -> dict[str, Any]:
        connection = self._connection()
        try:
            row = connection.execute("SELECT official_url, evidence_timestamp, evidence_sha256 FROM license_evidence WHERE pack_id = ? AND version = ? AND library_asset_id = ?", (pack_id, version, library_asset_id)).fetchone()
            if row is None:
                raise KeyError("License evidence not found")
            return dict(row)
        finally:
            connection.close()

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS media_packs (
                pack_id TEXT NOT NULL, version TEXT NOT NULL, install_path TEXT NOT NULL,
                verified INTEGER NOT NULL, active INTEGER NOT NULL, installed_at TEXT NOT NULL,
                PRIMARY KEY (pack_id, version)
            );
            CREATE TABLE IF NOT EXISTS media_assets (
                pack_id TEXT NOT NULL, version TEXT NOT NULL, library_asset_id TEXT NOT NULL,
                asset_id TEXT NOT NULL, media_type TEXT NOT NULL, duration_seconds REAL NOT NULL,
                sha256 TEXT NOT NULL, path TEXT NOT NULL, source TEXT NOT NULL, creator TEXT NOT NULL,
                official_license_url TEXT NOT NULL, evidence_timestamp TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
                PRIMARY KEY (pack_id, version, library_asset_id),
                FOREIGN KEY (pack_id, version) REFERENCES media_packs(pack_id, version) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS library_favorites (
                library_asset_id TEXT PRIMARY KEY, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recent_library_usage (
                library_asset_id TEXT PRIMARY KEY, used_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS license_evidence (
                pack_id TEXT NOT NULL, version TEXT NOT NULL, library_asset_id TEXT NOT NULL,
                official_url TEXT NOT NULL, evidence_timestamp TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
                PRIMARY KEY (pack_id, version, library_asset_id)
            );
            """
        )
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
