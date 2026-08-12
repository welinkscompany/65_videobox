from __future__ import annotations

import sqlite3
import hashlib
import json
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from videobox_storage.library_user_asset_store import (
    LibraryUserAssetStore,
    ensure_library_user_asset_schema,
)
from videobox_storage.footage_organizer_store import (
    FootageOrganizerStore,
    ensure_footage_organizer_schema,
)


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
        # User assets use an additive lifecycle schema in this same global DB.
        # Keep this as a small facade so existing API/bootstrap callers do not
        # need to know which part of the library owns a row.
        self.user_asset_store = LibraryUserAssetStore(self.root)
        self.footage_organizer_store = FootageOrganizerStore(self.root)
        # Short facade name for callers that treat this as one global store.
        self.footage_store = self.footage_organizer_store

    def register_user_asset(self, **kwargs: Any):
        return self.user_asset_store.register_asset(**kwargs)

    def list_user_assets(self, **kwargs: Any):
        return self.user_asset_store.list_assets(**kwargs)

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
                        evidence_timestamp, evidence_sha256, tags_json, attribution_required, attribution_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(pack_id, version, library_asset_id) DO UPDATE SET
                        asset_id = excluded.asset_id, media_type = excluded.media_type,
                        duration_seconds = excluded.duration_seconds, sha256 = excluded.sha256,
                        path = excluded.path, source = excluded.source, creator = excluded.creator,
                        official_license_url = excluded.official_license_url,
                        evidence_timestamp = excluded.evidence_timestamp, evidence_sha256 = excluded.evidence_sha256,
                        tags_json = excluded.tags_json, attribution_required = excluded.attribution_required,
                        attribution_text = excluded.attribution_text
                    """,
                    (
                        pack_id, version, asset["library_asset_id"], asset["asset_id"], asset["media_type"],
                        asset["duration_seconds"], asset["sha256"], str(asset["path"]), asset["source"],
                        asset["creator"], license_data["official_url"], license_data["evidence_timestamp"],
                        license_data["evidence_sha256"], json.dumps(asset.get("tags", [])),
                        int(bool(license_data.get("attribution_required", False))), str(license_data.get("attribution_text", "")),
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

    def list_pack_asset_digests(self, *, pack_id: str, version: str) -> dict[str, str]:
        """What one pack version already has indexed, without touching a file.

        A caller that periodically reconciles a folder against the library
        needs to know what is already registered.  Doing that through
        ``search()`` or ``inspect_active_assets()`` would re-hash every file on
        the disk on every pass; this is a plain read of the index.
        """
        connection = self._connection()
        try:
            rows = connection.execute(
                "SELECT library_asset_id, sha256 FROM media_assets WHERE pack_id = ? AND version = ?",
                (pack_id, version),
            ).fetchall()
        finally:
            connection.close()
        return {str(row["library_asset_id"]): str(row["sha256"]) for row in rows}

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
                       a.evidence_sha256, a.version, a.tags_json, a.attribution_required, a.attribution_text
                FROM media_assets a
                JOIN media_packs p ON p.pack_id = a.pack_id AND p.version = a.version
                WHERE p.active = 1 AND p.verified = 1
                ORDER BY a.library_asset_id
                """
            ).fetchall()
        finally:
            connection.close()
        normalized_query = (query or "").strip().lower()
        results = [self._normalize_asset_row(row) for row in rows if self._is_currently_verified(Path(str(row["path"])), str(row["sha256"]))]
        if not normalized_query:
            return results
        return [item for item in results if normalized_query in " ".join(map(str, item.values())).lower()]

    def inspect_active_assets(self) -> list[dict[str, Any]]:
        """Inspection-only view retaining missing/tampered entries for recovery UI."""
        connection = self._connection()
        try:
            rows = connection.execute(
                """SELECT a.library_asset_id, a.asset_id, a.media_type, a.duration_seconds, a.sha256,
                           a.path, a.source, a.creator, a.official_license_url, a.evidence_timestamp,
                           a.evidence_sha256, a.version, a.tags_json, a.attribution_required, a.attribution_text
                    FROM media_assets a JOIN media_packs p ON p.pack_id = a.pack_id AND p.version = a.version
                    WHERE p.active = 1 AND p.verified = 1 ORDER BY a.library_asset_id"""
            ).fetchall()
        finally:
            connection.close()
        assets = []
        for row in rows:
            item = self._normalize_asset_row(row)
            path = Path(str(item["path"]))
            item["verified"] = bool(path.is_file() and self._is_currently_verified(path, str(item["sha256"])))
            # A physically present but checksum-invalid asset is unavailable to
            # preview/apply; recovery UI can still inspect the row.
            item["available"] = item["verified"]
            assets.append(item)
        return assets

    def list_assets_needing_audio_analysis(
        self, *, description_version: int = 1
    ) -> list[dict[str, Any]]:
        """Active assets that have never been measured, whose bytes changed, or
        whose embedding is still missing.

        The last case matters: measuring needs only ffmpeg, embedding needs the
        local model. When the model is away the measurements are still worth
        keeping, and the asset has to come back for its vector later rather
        than being quietly treated as done.
        """
        connection = self._connection()
        try:
            pack_rows = connection.execute(
                """SELECT a.library_asset_id, a.asset_id, a.media_type, a.sha256, a.path
                    FROM media_assets a
                    JOIN media_packs p ON p.pack_id = a.pack_id AND p.version = a.version
                    LEFT JOIN library_audio_descriptors d ON d.library_asset_id = a.library_asset_id
                    WHERE p.active = 1 AND p.verified = 1
                      AND (d.library_asset_id IS NULL OR d.sha256 <> a.sha256
                           OR d.embedding_json IS NULL OR d.description_version < ?)
                    ORDER BY a.library_asset_id""",
                (int(description_version),),
            ).fetchall()
            user_rows = connection.execute(
                """SELECT u.library_asset_id, u.media_type, u.content_sha256,
                          u.managed_relative_path, u.user_json,
                          d.library_asset_id AS descriptor_id
                   FROM library_user_assets u
                   LEFT JOIN library_audio_descriptors d
                     ON d.library_asset_id = u.library_asset_id
                   WHERE u.origin = 'user' AND u.lifecycle = 'ready'
                     AND u.media_type IN ('music', 'sfx')
                     AND (d.library_asset_id IS NULL OR d.sha256 <> u.content_sha256
                          OR d.embedding_json IS NULL OR d.description_version < ?)
                   ORDER BY u.library_asset_id""",
                (int(description_version),),
            ).fetchall()
        finally:
            connection.close()
        pending = [dict(row) for row in pack_rows]
        for row in user_rows:
            item = dict(row)
            item["asset_id"] = item["library_asset_id"]
            item["sha256"] = item.pop("content_sha256")
            item["path"] = str(self._resolve_managed_path(item.pop("managed_relative_path")))
            item["user_metadata"] = json.loads(str(item.pop("user_json") or "{}"))
            item.pop("descriptor_id", None)
            pending.append(item)
        pending.sort(key=lambda item: str(item["library_asset_id"]))
        return pending

    def save_audio_descriptor(
        self,
        *,
        library_asset_id: str,
        sha256: str,
        measurements: dict[str, float],
        words: dict[str, str],
        description: str,
        embedding: list[float] | None,
        description_version: int = 1,
    ) -> None:
        connection = self._connection()
        try:
            connection.execute(
                """
                INSERT INTO library_audio_descriptors (
                    library_asset_id, sha256, duration_seconds, loudness_rms, brightness_hz,
                    onset_rate_per_second, words_json, description, embedding_json,
                    description_version, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_asset_id) DO UPDATE SET
                    sha256 = excluded.sha256, duration_seconds = excluded.duration_seconds,
                    loudness_rms = excluded.loudness_rms, brightness_hz = excluded.brightness_hz,
                    onset_rate_per_second = excluded.onset_rate_per_second,
                    words_json = excluded.words_json, description = excluded.description,
                    embedding_json = excluded.embedding_json,
                    description_version = excluded.description_version,
                    analyzed_at = excluded.analyzed_at
                """,
                (
                    library_asset_id,
                    sha256,
                    float(measurements["duration_seconds"]),
                    float(measurements["loudness_rms"]),
                    float(measurements["brightness_hz"]),
                    float(measurements["onset_rate_per_second"]),
                    json.dumps(words, ensure_ascii=False),
                    description,
                    json.dumps(embedding) if embedding is not None else None,
                    int(description_version),
                    self._now(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_audio_descriptor(self, *, library_asset_id: str) -> dict[str, Any] | None:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM library_audio_descriptors WHERE library_asset_id = ?",
                (library_asset_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._normalize_descriptor_row(row) if row is not None else None

    @staticmethod
    def _normalize_descriptor_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["words"] = json.loads(str(item.pop("words_json")))
        raw_embedding = item.pop("embedding_json", None)
        item["embedding"] = json.loads(str(raw_embedding)) if raw_embedding else None
        return item

    def find_audio_matches(
        self, *, query_embedding: list[float], media_type: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Rank one kind of library asset against a query by cosine similarity.

        Restricted to a single media_type on purpose: a scene needs music or an
        effect, never whichever of the two happens to score highest.
        """
        query = tuple(float(value) for value in query_embedding)
        if not query or not all(math.isfinite(value) for value in query):
            raise ValueError("query_embedding must contain finite values")
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            raise ValueError("query_embedding must not be all zeros")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        connection = self._connection()
        try:
            rows = connection.execute(
                """SELECT d.library_asset_id, d.description, d.words_json, d.embedding_json,
                          d.duration_seconds, a.asset_id, a.media_type, '{}' AS user_json
                    FROM library_audio_descriptors d
                    JOIN media_assets a ON a.library_asset_id = d.library_asset_id
                    JOIN media_packs p ON p.pack_id = a.pack_id AND p.version = a.version
                    WHERE p.active = 1 AND p.verified = 1 AND a.media_type = ?
                      AND d.embedding_json IS NOT NULL
                    UNION ALL
                    SELECT d.library_asset_id, d.description, d.words_json, d.embedding_json,
                          d.duration_seconds, u.library_asset_id AS asset_id, u.media_type,
                          u.user_json
                    FROM library_audio_descriptors d
                    JOIN library_user_assets u ON u.library_asset_id = d.library_asset_id
                    WHERE u.origin = 'user' AND u.lifecycle = 'ready' AND u.media_type = ?
                      AND d.embedding_json IS NOT NULL""",
                (media_type, media_type),
            ).fetchall()
        finally:
            connection.close()

        matches: list[dict[str, Any]] = []
        for row in rows:
            vector = json.loads(str(row["embedding_json"]))
            if len(vector) != len(query):
                # A model change leaves old vectors incomparable. Skip them
                # rather than ranking on a truncated dot product; they come
                # back as pending once their embedding is cleared.
                continue
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                continue
            score = sum(a * b for a, b in zip(query, vector, strict=True)) / (query_norm * norm)
            matches.append({
                "library_asset_id": str(row["library_asset_id"]),
                "asset_id": str(row["asset_id"]),
                "media_type": str(row["media_type"]),
                "description": str(row["description"]),
                "words": json.loads(str(row["words_json"])),
                "user_metadata": json.loads(str(row["user_json"] or "{}")),
                "duration_seconds": float(row["duration_seconds"]),
                "score": round(score, 6),
            })
        matches.sort(key=lambda match: (-match["score"], match["library_asset_id"]))
        return matches[:limit]

    # ------------------------------------------------------------------
    # The owner's own footage
    # ------------------------------------------------------------------

    def list_footage_needing_analysis(
        self, *, paths: Iterable[Path], description_version: int = 1
    ) -> list[dict[str, Any]]:
        """Of the files present, the ones not yet described at this version.

        Hashing is the price of knowing, and it is what makes re-adding or
        renaming the same clip free rather than a second analysis.
        """
        connection = self._connection()
        try:
            rows = connection.execute(
                """SELECT content_sha256 FROM footage_index
                    WHERE embedding_json IS NOT NULL AND description_version >= ?""",
                (int(description_version),),
            ).fetchall()
            user_rows = connection.execute(
                """SELECT library_asset_id, content_sha256, managed_relative_path, user_json
                   FROM library_user_assets
                   WHERE origin = 'user' AND lifecycle = 'ready' AND media_type = 'broll'"""
            ).fetchall()
        finally:
            connection.close()
        done = {str(row["content_sha256"]) for row in rows}
        user_by_hash: dict[str, dict[str, Any]] = {}
        for row in user_rows:
            item = dict(row)
            item["path"] = self._resolve_managed_path(item.pop("managed_relative_path"))
            item["user_metadata"] = json.loads(str(item.pop("user_json") or "{}"))
            user_by_hash[str(item["content_sha256"])] = item

        pending: list[dict[str, Any]] = []
        queued: set[str] = set()

        def add_path(file_path: Path, known: dict[str, Any] | None = None) -> None:
            if not file_path.is_file():
                return
            digest = _sha256_file(file_path)
            if digest in done or digest in queued:
                return
            queued.add(digest)
            item: dict[str, Any] = {"content_sha256": digest, "filename": file_path.name, "path": str(file_path)}
            if known is not None:
                item["library_asset_id"] = known["library_asset_id"]
                item["user_metadata"] = known["user_metadata"]
            pending.append(item)

        for path in paths:
            file_path = Path(path)
            if file_path.is_file():
                digest = _sha256_file(file_path)
                add_path(file_path, user_by_hash.get(digest))
        for known in user_by_hash.values():
            add_path(Path(str(known["path"])), known)
        return pending

    def save_footage_descriptor(
        self,
        *,
        content_sha256: str,
        library_asset_id: str | None = None,
        filename: str,
        duration_seconds: float,
        width: int,
        height: int,
        tags: dict[str, Any],
        description: str,
        embedding: list[float] | None,
        description_version: int = 1,
    ) -> None:
        # Orientation comes from the real frame size, never from a tag a model
        # guessed: choosing footage for a short is a yes/no question.
        orientation = "가로" if int(width) >= int(height) else "세로"
        connection = self._connection()
        try:
            connection.execute(
                """
                INSERT INTO footage_index (
                    content_sha256, library_asset_id, filename, duration_seconds, width, height, orientation,
                    tags_json, description, embedding_json, description_version, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_sha256) DO UPDATE SET
                    library_asset_id = COALESCE(excluded.library_asset_id, footage_index.library_asset_id),
                    filename = excluded.filename, duration_seconds = excluded.duration_seconds,
                    width = excluded.width, height = excluded.height, orientation = excluded.orientation,
                    tags_json = excluded.tags_json, description = excluded.description,
                    embedding_json = excluded.embedding_json,
                    description_version = excluded.description_version,
                    analyzed_at = excluded.analyzed_at
                """,
                (
                    content_sha256, library_asset_id, filename, float(duration_seconds), int(width), int(height),
                    orientation, json.dumps(tags, ensure_ascii=False), description,
                    json.dumps(embedding) if embedding is not None else None,
                    int(description_version), self._now(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_footage_descriptor(self, *, content_sha256: str) -> dict[str, Any] | None:
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM footage_index WHERE content_sha256 = ?", (content_sha256,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        item = dict(row)
        item["tags"] = json.loads(str(item.pop("tags_json")))
        raw = item.pop("embedding_json", None)
        item["embedding"] = json.loads(str(raw)) if raw else None
        return item

    def find_footage_matches(
        self, *, query_embedding: list[float], orientation: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        query = tuple(float(value) for value in query_embedding)
        if not query or not all(math.isfinite(value) for value in query):
            raise ValueError("query_embedding must contain finite values")
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            raise ValueError("query_embedding must not be all zeros")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        sql = """SELECT content_sha256, filename, duration_seconds, orientation, tags_json,
                        description, embedding_json
                 FROM footage_index WHERE embedding_json IS NOT NULL"""
        parameters: tuple[Any, ...] = ()
        if orientation is not None:
            sql += " AND orientation = ?"
            parameters = (orientation,)
        connection = self._connection()
        try:
            rows = connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()

        matches: list[dict[str, Any]] = []
        for row in rows:
            vector = json.loads(str(row["embedding_json"]))
            if len(vector) != len(query):
                continue
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                continue
            score = sum(a * b for a, b in zip(query, vector, strict=True)) / (query_norm * norm)
            matches.append({
                "content_sha256": str(row["content_sha256"]),
                "filename": str(row["filename"]),
                "duration_seconds": float(row["duration_seconds"]),
                "orientation": str(row["orientation"]),
                "tags": json.loads(str(row["tags_json"])),
                "description": str(row["description"]),
                "score": round(score, 6),
            })
        matches.sort(key=lambda match: (-match["score"], match["filename"]))
        return matches[:limit]

    def install_state(self) -> dict[str, object]:
        assets = self.inspect_active_assets()
        if not assets:
            return {"status": "not_installed", "installed_asset_count": 0}
        valid_count = sum(bool(item["verified"]) for item in assets)
        return {"status": "installed" if valid_count == len(assets) else "degraded", "installed_asset_count": len(assets)}

    @staticmethod
    def _normalize_asset_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = json.loads(str(item.pop("tags_json", "[]")))
        item["attribution_required"] = bool(item["attribution_required"])
        return item

    def get_verified_asset(self, *, library_asset_id: str) -> dict[str, Any] | None:
        """Return one currently active, checksum-verified library asset."""
        for asset in self.search():
            if str(asset["library_asset_id"]) == library_asset_id:
                return asset
        return None

    def snapshot_verified_asset(self, *, library_asset_id: str) -> tuple[dict[str, Any], Path] | None:
        """Copy verified bytes to a controlled snapshot and verify those bytes.

        The caller must remove the returned file once it has been registered or
        streamed.  This avoids using a pack path after its verification result.
        """
        asset = self.get_verified_asset(library_asset_id=library_asset_id)
        if asset is None:
            return None
        source_path = Path(str(asset["path"]))
        snapshot_root = self.root / "verified-snapshots"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        snapshot_dir = Path(tempfile.mkdtemp(prefix="media-", dir=snapshot_root))
        snapshot_path = snapshot_dir / source_path.name
        try:
            digest = hashlib.sha256()
            with source_path.open("rb") as source, snapshot_path.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    destination.write(chunk)
            if digest.hexdigest() != str(asset["sha256"]):
                raise FileNotFoundError("asset_missing")
            return asset, snapshot_path
        except Exception:
            self.remove_verified_snapshot(snapshot_path)
            raise

    @staticmethod
    def remove_verified_snapshot(snapshot_path: Path) -> None:
        snapshot_path.unlink(missing_ok=True)
        try:
            snapshot_path.parent.rmdir()
        except OSError:
            pass

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
                tags_json TEXT NOT NULL DEFAULT '[]', attribution_required INTEGER NOT NULL DEFAULT 0, attribution_text TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (pack_id, version, library_asset_id),
                FOREIGN KEY (pack_id, version) REFERENCES media_packs(pack_id, version) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS library_favorites (
                library_asset_id TEXT PRIMARY KEY, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recent_library_usage (
                library_asset_id TEXT PRIMARY KEY, used_at TEXT NOT NULL
            );
            -- What each asset actually sounds like, plus the vector that makes
            -- it findable. Keyed on the checksum that was analysed, so a
            -- replaced or newly added file comes back as pending on its own --
            -- nobody has to remember to re-run anything after adding music.
            CREATE TABLE IF NOT EXISTS library_audio_descriptors (
                library_asset_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                duration_seconds REAL NOT NULL, loudness_rms REAL NOT NULL,
                brightness_hz REAL NOT NULL, onset_rate_per_second REAL NOT NULL,
                words_json TEXT NOT NULL, description TEXT NOT NULL,
                embedding_json TEXT, description_version INTEGER NOT NULL DEFAULT 1,
                analyzed_at TEXT NOT NULL
            );
            -- The owner's own footage, indexed by what is in the file rather
            -- than by which project happens to hold a copy. Analysis used to
            -- live per project, so footage sitting in the library was invisible
            -- until imported, and the same clip was analysed once per project
            -- that used it.
            CREATE TABLE IF NOT EXISTS footage_index (
                content_sha256 TEXT PRIMARY KEY, library_asset_id TEXT, filename TEXT NOT NULL,
                duration_seconds REAL NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                orientation TEXT NOT NULL, tags_json TEXT NOT NULL, description TEXT NOT NULL,
                embedding_json TEXT, description_version INTEGER NOT NULL DEFAULT 1,
                analyzed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS license_evidence (
                pack_id TEXT NOT NULL, version TEXT NOT NULL, library_asset_id TEXT NOT NULL,
                official_url TEXT NOT NULL, evidence_timestamp TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
                PRIMARY KEY (pack_id, version, library_asset_id)
            );
            """
        )
        for statement in (
            "ALTER TABLE media_assets ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE media_assets ADD COLUMN attribution_required INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE media_assets ADD COLUMN attribution_text TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE library_audio_descriptors ADD COLUMN description_version INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE footage_index ADD COLUMN library_asset_id TEXT",
        ):
            try:
                connection.execute(statement)
            except sqlite3.OperationalError:
                pass
        ensure_library_user_asset_schema(connection)
        ensure_footage_organizer_schema(connection)
        return connection

    def _resolve_managed_path(self, relative: str) -> Path:
        """Resolve a user asset path inside this store's managed root."""
        base = self.root.resolve()
        candidate = (base / str(relative)).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise ValueError("managed asset path escaped library root") from error
        return candidate

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
