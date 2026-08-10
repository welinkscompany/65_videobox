"""촬영본 분석(media analysis) 갈래.

`local_project_store.py`에서 **그대로** 떼어 온 코드다. 동작은 한 줄도 바꾸지
않았다. `LocalProjectStore`가 이 mixin을 상속하므로, 여기 있는 메서드는 base가
쥔 `_connection` / `_execute` / `_fetchone` / `_now_iso` / `project_root`와
자산 갈래의 `get_asset` / `update_asset_metadata` / `resolve_storage_uri` /
`_increment_asset_index_revision_with_connection`을 그대로 쓴다 -- 전부 `self.`
조회라 MRO가 흡수한다.

별도 모듈 + 위임이 아니라 mixin인 이유는 hermes 갈래와 같다
(`_store_hermes_capability.py` 문서 참고): 위임으로 바꾸면 인스턴스에 monkeypatch
하는 테스트와 `PostgresProjectStore._connection` 재정의가 조용히 깨진다.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from videobox_domain_models.media_analysis import MediaAnalysisStatus


def sha256_file(path: Path) -> str:
    """파일 해시. 원래 `local_project_store`에 있었는데 이 갈래가 쓴다.

    base가 이 mixin을 import하므로 반대로 import하면 순환이 된다. 정의를 여기로
    옮기고 base가 여기서 가져간다 -- hermes 상수와 같은 모양이다. 정의는 하나뿐이다.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class MediaAnalysisMixin:
    """분석 작업의 생성·청구·완료·복구와 장면/임베딩 기록 갈래."""

    def create_media_analysis(
        self,
        *,
        project_id: str,
        asset_id: str,
        idempotency_key: str,
        cache_key: str,
    ) -> dict[str, Any]:
        """Create a durable analysis run, or return the run already requested."""
        owned_key = f"{asset_id}::{idempotency_key}"
        existing = self._media_analysis_by_idempotency(project_id, asset_id, owned_key)
        if existing is not None:
            return existing
        now = self._now_iso()
        analysis_id = f"media_analysis_{uuid.uuid4().hex[:12]}"
        try:
            self._execute(
                project_id,
                """
                INSERT INTO media_analysis_runs (
                    analysis_id, project_id, asset_id, idempotency_key, cache_key,
                    status, attempt, progress_percent, error_code, error_message,
                    next_retry_at, cancel_requested, result_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, 0, NULL, ?, ?)
                """,
                (
                    analysis_id, project_id, asset_id, owned_key, cache_key,
                    MediaAnalysisStatus.QUEUED.value, now, now,
                ),
            )
        except sqlite3.IntegrityError:
            existing = self._media_analysis_by_idempotency(project_id, asset_id, owned_key)
            if existing is None:
                raise
            return existing
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def get_media_analysis(self, *, project_id: str, analysis_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT * FROM media_analysis_runs WHERE analysis_id = ? AND project_id = ?",
            (analysis_id, project_id),
        )
        if row is None:
            raise KeyError(f"Media analysis not found: {analysis_id}")
        payload = self._media_analysis_payload(row)
        if payload["status"] in {MediaAnalysisStatus.QUEUED.value, MediaAnalysisStatus.RUNNING.value}:
            active_ids = [item["analysis_id"] for item in self.list_media_analysis(project_id=project_id) if item["status"] in {MediaAnalysisStatus.QUEUED.value, MediaAnalysisStatus.RUNNING.value}]
            # A concurrent worker can transition this run between the row and
            # queue snapshots. Prefer an unavailable position over a 500.
            payload["queue_position"] = active_ids.index(analysis_id) + 1 if analysis_id in active_ids else None
        else:
            payload["queue_position"] = None
        return payload

    def record_media_analysis_profile(self, *, project_id: str, analysis_id: str, profile: dict[str, Any]) -> None:
        self._execute(project_id, "INSERT OR REPLACE INTO media_analysis_profiles (analysis_id, project_id, profile_json, created_at) VALUES (?, ?, ?, ?)", (analysis_id, project_id, json.dumps(profile, ensure_ascii=True, sort_keys=True), self._now_iso()))

    def get_media_analysis_profile(self, *, project_id: str, analysis_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT profile_json FROM media_analysis_profiles WHERE project_id = ? AND analysis_id = ?", (project_id, analysis_id))
        if row is None:
            raise KeyError(f"Media analysis profile not found: {analysis_id}")
        return json.loads(str(row["profile_json"]))

    def record_media_scene_windows(self, *, project_id: str, analysis_id: str, source_sha256: str, profile_hash: str, windows: list[dict[str, Any]]) -> None:
        # Workers can return after a user has cancelled.  Derived records must
        # never resurrect a terminally cancelled run.
        current = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if current["status"] != MediaAnalysisStatus.RUNNING.value or bool(current["cancel_requested"]):
            return
        for window in windows:
            self._execute(project_id, "INSERT OR REPLACE INTO media_scene_windows (scene_window_id, analysis_id, source_sha256, profile_hash, start_sec, end_sec, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)", (f"{analysis_id}:{window['start_sec']}:{window['end_sec']}", analysis_id, source_sha256, profile_hash, float(window["start_sec"]), float(window["end_sec"]), json.dumps(window.get("metadata") or {}, ensure_ascii=True)))

    def list_media_scene_windows(self, *, project_id: str, analysis_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute("SELECT * FROM media_scene_windows WHERE analysis_id = ? ORDER BY start_sec ASC", (analysis_id,)).fetchall()
        finally:
            connection.close()
        return [{**dict(row), "metadata": json.loads(str(row["metadata_json"]))} for row in rows]

    def record_media_embedding(self, *, project_id: str, analysis_id: str, source_sha256: str, profile_hash: str, embedding: list[float]) -> None:
        current = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if current["status"] != MediaAnalysisStatus.RUNNING.value or bool(current["cancel_requested"]):
            return
        self._execute(project_id, "INSERT OR REPLACE INTO media_embeddings (embedding_id, analysis_id, source_sha256, profile_hash, embedding_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (f"{analysis_id}:0", analysis_id, source_sha256, profile_hash, json.dumps(embedding), self._now_iso()))

    def list_media_embeddings(self, *, project_id: str, analysis_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute("SELECT * FROM media_embeddings WHERE analysis_id = ? ORDER BY embedding_id ASC", (analysis_id,)).fetchall()
        finally:
            connection.close()
        return [{**dict(row), "embedding": json.loads(str(row["embedding_json"]))} for row in rows]

    def find_local_media_embedding_matches(
        self,
        *,
        project_id: str,
        query_embedding: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Rank durable local media embeddings with deterministic cosine similarity."""
        query = tuple(float(value) for value in query_embedding)
        if not query or not all(math.isfinite(value) for value in query):
            raise ValueError("query_embedding must contain finite values")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        query_norm = math.sqrt(sum(value * value for value in query))
        if query_norm == 0:
            raise ValueError("query_embedding must not be a zero vector")
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT embeddings.embedding_id, embeddings.analysis_id, runs.asset_id,
                       embeddings.source_sha256, embeddings.profile_hash, embeddings.embedding_json
                FROM media_embeddings AS embeddings
                INNER JOIN media_analysis_runs AS runs ON runs.analysis_id = embeddings.analysis_id
                WHERE runs.project_id = ? AND runs.status = ? AND runs.cancel_requested = 0
                -- 최신이 마지막에 오게 둔다. 아래에서 자산마다 마지막 것만
                -- 남긴다 -- 분석 문구를 바꾸고 다시 돌리면 한 자산이 옛
                -- 임베딩과 새 임베딩을 둘 다 갖게 되고, 그대로 두면 같은
                -- 영상이 검색에 두 번 나오며 낡은 쪽이 이길 수도 있다.
                ORDER BY runs.created_at ASC, embeddings.analysis_id ASC, embeddings.embedding_id ASC
                """,
                (project_id, MediaAnalysisStatus.SUCCEEDED.value),
            ).fetchall()
        finally:
            connection.close()
        matches: list[dict[str, Any]] = []
        for row in rows:
            try:
                candidate = tuple(float(value) for value in json.loads(str(row["embedding_json"])))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if len(candidate) != len(query) or not candidate or not all(math.isfinite(value) for value in candidate):
                continue
            candidate_norm = math.sqrt(sum(value * value for value in candidate))
            if candidate_norm == 0:
                continue
            score = sum(left * right for left, right in zip(query, candidate)) / (query_norm * candidate_norm)
            matches.append(
                {
                    "analysis_id": str(row["analysis_id"]),
                    "asset_id": str(row["asset_id"]),
                    "source_sha256": str(row["source_sha256"]),
                    "profile_hash": str(row["profile_hash"]),
                    "score": score,
                }
            )
        newest_by_asset: dict[str, dict[str, Any]] = {}
        for match in matches:
            newest_by_asset[str(match["asset_id"])] = match
        return sorted(
            newest_by_asset.values(),
            key=lambda item: (-float(item["score"]), str(item["analysis_id"])),
        )[:limit]

    def list_media_analysis(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                "SELECT * FROM media_analysis_runs WHERE project_id = ? ORDER BY created_at ASC, analysis_id ASC",
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        items = [self._media_analysis_payload(row) for row in rows]
        position = 0
        for item in items:
            if item["status"] in {MediaAnalysisStatus.QUEUED.value, MediaAnalysisStatus.RUNNING.value}:
                position += 1
                item["queue_position"] = position
            else:
                item["queue_position"] = None
        return items

    def review_media_analysis(self, *, project_id: str, analysis_id: str, tags: dict[str, list[str]]) -> dict[str, Any]:
        current = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if current["status"] != MediaAnalysisStatus.NEEDS_REVIEW.value:
            raise ValueError("Only needs_review media analysis can be manually reviewed.")
        result = dict(current.get("result") or {})
        existing_tags = dict(result.get("tags") or {})
        existing_layers = dict(existing_tags.get("layers") or {})
        merged_layers = {name: list(values) for name, values in existing_layers.items()}
        for layer, values in tags.items():
            if layer not in merged_layers:
                raise ValueError(f"Unknown media tag layer: {layer}")
            merged_layers[layer] = list(dict.fromkeys([*merged_layers[layer], *values]))
        result["tags"] = {**existing_tags, "layers": merged_layers}
        self._execute(
            project_id,
            "UPDATE media_analysis_runs SET status = ?, result_json = ?, progress_percent = 100, updated_at = ? WHERE analysis_id = ? AND project_id = ?",
            (MediaAnalysisStatus.SUCCEEDED.value, json.dumps(result, ensure_ascii=True), self._now_iso(), analysis_id, project_id),
        )
        reviewed = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        searchable_tags = [tag for values in merged_layers.values() for tag in values]
        asset = self.get_asset(project_id=project_id, asset_id=str(current["asset_id"]))
        existing_tags = asset["metadata"].get("tags") if isinstance(asset["metadata"].get("tags"), list) else []
        self.update_asset_metadata(project_id=project_id, asset_id=str(current["asset_id"]), metadata_patch={"tags": list(dict.fromkeys([*existing_tags, *searchable_tags]))})
        return reviewed

    def retry_media_analysis(self, *, project_id: str, analysis_id: str) -> dict[str, Any]:
        current = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if current["status"] not in {MediaAnalysisStatus.FAILED.value, MediaAnalysisStatus.BLOCKED.value}:
            raise ValueError("Only failed or blocked media analysis can be retried.")
        self._execute(project_id, "UPDATE media_analysis_runs SET status = ?, error_code = NULL, error_message = NULL, next_retry_at = NULL, cancel_requested = 0, updated_at = ? WHERE analysis_id = ? AND project_id = ?", (MediaAnalysisStatus.QUEUED.value, self._now_iso(), analysis_id, project_id))
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def claim_media_analysis(self, *, project_id: str, analysis_id: str) -> dict[str, Any] | None:
        """Atomically claim a queued or due-retry run; None means another worker won."""
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, attempt = attempt + 1, progress_percent = 0, next_retry_at = NULL, updated_at = ?
                WHERE analysis_id = ? AND project_id = ? AND cancel_requested = 0
                  AND (
                    status = ?
                    OR (status = ? AND next_retry_at IS NOT NULL AND next_retry_at <= ?)
                  )
                """,
                (
                    MediaAnalysisStatus.RUNNING.value, now, analysis_id, project_id,
                    MediaAnalysisStatus.QUEUED.value, MediaAnalysisStatus.FAILED.value, now,
                ),
            )
            if cursor.rowcount == 1:
                connection.execute("DELETE FROM media_scene_windows WHERE analysis_id = ?", (analysis_id,))
                connection.execute("DELETE FROM media_embeddings WHERE analysis_id = ?", (analysis_id,))
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount != 1:
            return None
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def complete_media_analysis(
        self,
        *,
        project_id: str,
        analysis_id: str,
        expected_attempt: int,
        result: dict[str, Any],
        status: MediaAnalysisStatus = MediaAnalysisStatus.SUCCEEDED,
    ) -> dict[str, Any] | None:
        if status not in {MediaAnalysisStatus.SUCCEEDED, MediaAnalysisStatus.NEEDS_REVIEW}:
            raise ValueError("Completed media analysis must be succeeded or needs_review.")
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, result_json = ?, progress_percent = 100, error_code = NULL,
                    error_message = NULL, next_retry_at = NULL, updated_at = ?
                WHERE analysis_id = ? AND project_id = ? AND status = ? AND cancel_requested = 0 AND attempt = ?
                """,
                (
                    status.value, json.dumps(result, ensure_ascii=True), self._now_iso(), analysis_id, project_id,
                    MediaAnalysisStatus.RUNNING.value, expected_attempt,
                ),
            )
            if cursor.rowcount == 1:
                self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount != 1:
            return None
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def mark_media_analysis_blocked(
        self, *, project_id: str, analysis_id: str, expected_attempt: int, error_code: str, error_message: str
    ) -> dict[str, Any] | None:
        return self._set_media_analysis_error(
            project_id=project_id, analysis_id=analysis_id, status=MediaAnalysisStatus.BLOCKED,
            expected_attempt=expected_attempt, error_code=error_code, error_message=error_message, next_retry_at=None,
        )

    def fail_media_analysis(
        self, *, project_id: str, analysis_id: str, expected_attempt: int, error_code: str, error_message: str,
        next_retry_at: str | None = None,
    ) -> dict[str, Any] | None:
        return self._set_media_analysis_error(
            project_id=project_id, analysis_id=analysis_id, status=MediaAnalysisStatus.FAILED,
            expected_attempt=expected_attempt, error_code=error_code, error_message=error_message, next_retry_at=next_retry_at,
        )

    def request_media_analysis_cancel(
        self, *, project_id: str, analysis_id: str, expected_attempt: int
    ) -> dict[str, Any] | None:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, cancel_requested = 1, next_retry_at = NULL, updated_at = ?
                WHERE analysis_id = ? AND project_id = ? AND status IN (?, ?) AND cancel_requested = 0 AND attempt = ?
                """,
                (
                    MediaAnalysisStatus.CANCELLED.value, self._now_iso(), analysis_id, project_id,
                    MediaAnalysisStatus.RUNNING.value, MediaAnalysisStatus.QUEUED.value, expected_attempt,
                ),
            )
            if cursor.rowcount == 1:
                connection.execute("DELETE FROM media_scene_windows WHERE analysis_id = ?", (analysis_id,))
                connection.execute("DELETE FROM media_embeddings WHERE analysis_id = ?", (analysis_id,))
                self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount != 1:
            return None
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    def recover_orphaned_media_analysis_jobs(self, *, project_id: str) -> list[str]:
        connection = self._connection(project_id)
        try:
            # A spent retry budget leaves `failed` with no next_retry_at, and the
            # claim query only takes `failed` when a retry is booked and due. Nothing
            # else clears that, so the run stays frozen until the owner finds the
            # manual retry -- while the poller re-dispatches it every pass for
            # nothing. Grant one fresh attempt here, where a restart usually means
            # the owner has just changed the setting that caused the failure.
            #
            # This runs before the sweep below so a run that exhausts its budget
            # *during* this same sweep is not revived by it: that would be a loop,
            # not a recovery. It waits for the next restart, like everything else.
            revived = [
                str(row["analysis_id"])
                for row in connection.execute(
                    """
                    UPDATE media_analysis_runs
                    SET status = ?, error_code = NULL, error_message = NULL, progress_percent = 0, updated_at = ?
                    WHERE project_id = ? AND status = ? AND cancel_requested = 0 AND next_retry_at IS NULL
                    RETURNING analysis_id
                    """,
                    (MediaAnalysisStatus.QUEUED.value, self._now_iso(), project_id, MediaAnalysisStatus.FAILED.value),
                ).fetchall()
            ]
            # Three attempts means the initial run plus the two permitted retries.
            connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, error_code = ?, error_message = ?, next_retry_at = NULL, updated_at = ?
                WHERE project_id = ? AND status = ? AND cancel_requested = 0 AND attempt >= 3
                """,
                (MediaAnalysisStatus.FAILED.value, "RETRY_EXHAUSTED", "Recovered worker exceeded retry budget.", self._now_iso(), project_id, MediaAnalysisStatus.RUNNING.value),
            )
            rows = connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, progress_percent = 0, next_retry_at = NULL, updated_at = ?
                WHERE project_id = ? AND status = ? AND cancel_requested = 0 AND attempt < 3
                RETURNING analysis_id
                """,
                (MediaAnalysisStatus.QUEUED.value, self._now_iso(), project_id, MediaAnalysisStatus.RUNNING.value),
            ).fetchall()
            connection.commit()
        finally:
            connection.close()
        return [*revived, *(str(row["analysis_id"]) for row in rows)]

    def record_media_analysis_cache(self, *, project_id: str, asset_id: str, source_sha256: str, cache_key: str) -> None:
        """Keep immutable cache provenance; a new source makes prior derived data stale."""
        now = self._now_iso()
        self._execute(project_id, """
            UPDATE media_analysis_cache SET state = 'stale', tags_stale = 1, embedding_stale = 1,
                preview_stale = 1, proposal_index_stale = 1, stale_at = ?
            WHERE project_id = ? AND asset_id = ? AND source_sha256 <> ? AND state = 'active'
        """, (now, project_id, asset_id, source_sha256))
        self._execute(project_id, """
            INSERT OR IGNORE INTO media_analysis_cache (
                cache_id, project_id, asset_id, source_sha256, cache_key, state, created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (f"media_cache_{uuid.uuid4().hex}", project_id, asset_id, source_sha256, cache_key, now))

    def delete_asset(self, *, project_id: str, asset_id: str) -> None:
        """Delete the local asset and its disposable derived cache, retaining analysis history."""
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM media_analysis_cache WHERE project_id = ? AND asset_id = ?", (project_id, asset_id))
            cursor = connection.execute("DELETE FROM assets WHERE project_id = ? AND asset_id = ?", (project_id, asset_id))
            if cursor.rowcount != 1:
                raise KeyError(f"Asset not found: {asset_id}")
            self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        if path.exists():
            path.unlink()
        derived_dir = self.project_root(project_id) / "analysis" / "media_cache" / asset_id
        if derived_dir.exists():
            shutil.rmtree(derived_dir)

    def can_apply_media_analysis(self, *, project_id: str, analysis_id: str) -> bool:
        """Durable safety gate used by proposal/apply callers before consuming analysis."""
        analysis = self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)
        if analysis["status"] != MediaAnalysisStatus.SUCCEEDED.value or bool(analysis["cancel_requested"]):
            return False
        try:
            asset = self.get_asset(project_id=project_id, asset_id=str(analysis["asset_id"]))
            source = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
            if not source.exists():
                self._mark_media_cache_stale(project_id=project_id, asset_id=str(analysis["asset_id"]), source_sha256=str(analysis["idempotency_key"]).split("::", 1)[-1].split(":", 1)[0])
                return False
            current_sha = sha256_file(source)
        except (KeyError, OSError):
            return False
        expected_sha = str(analysis["idempotency_key"]).split("::", 1)[-1].split(":", 1)[0]
        if current_sha != expected_sha:
            self._mark_media_cache_stale(project_id=project_id, asset_id=str(analysis["asset_id"]), source_sha256=expected_sha)
            return False
        return True

    def _mark_media_cache_stale(self, *, project_id: str, asset_id: str, source_sha256: str) -> None:
        self._execute(project_id, """
            UPDATE media_analysis_cache SET state = 'stale', tags_stale = 1, embedding_stale = 1,
                preview_stale = 1, proposal_index_stale = 1, stale_at = ?
            WHERE project_id = ? AND asset_id = ? AND source_sha256 = ? AND state = 'active'
        """, (self._now_iso(), project_id, asset_id, source_sha256))

    def list_media_analysis_cache(self, *, project_id: str, asset_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute("SELECT * FROM media_analysis_cache WHERE project_id = ? AND asset_id = ? ORDER BY created_at ASC", (project_id, asset_id)).fetchall()
        finally:
            connection.close()
        return [{**dict(row), **{key: bool(dict(row)[key]) for key in ("tags_stale", "embedding_stale", "preview_stale", "proposal_index_stale")}} for row in rows]

    def prune_stale_media_analysis_cache(self, *, project_id: str, retention_days: int = 30) -> int:
        cutoff = (datetime.fromisoformat(self._now_iso()) - timedelta(days=retention_days)).isoformat()
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("DELETE FROM media_analysis_cache WHERE project_id = ? AND state = 'stale' AND stale_at <= ?", (project_id, cutoff))
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def _set_media_analysis_error(
        self, *, project_id: str, analysis_id: str, status: MediaAnalysisStatus, expected_attempt: int,
        error_code: str, error_message: str, next_retry_at: str | None,
    ) -> dict[str, Any] | None:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE media_analysis_runs
                SET status = ?, error_code = ?, error_message = ?, next_retry_at = ?, updated_at = ?
                WHERE analysis_id = ? AND project_id = ? AND status = ? AND cancel_requested = 0 AND attempt = ?
                """,
                (
                    status.value, error_code, error_message, next_retry_at, self._now_iso(), analysis_id,
                    project_id, MediaAnalysisStatus.RUNNING.value, expected_attempt,
                ),
            )
            if cursor.rowcount == 1:
                # Embeddings only mean anything next to the vision summary they
                # were built from, so a failed run must not leave them behind.
                # Scene windows are not like that (Task 28): ffmpeg derives them
                # before the vision call and they stay correct however that call
                # ends. Deleting them here was silently disabling b-roll range
                # recommendation for every analysis that did not fully succeed.
                connection.execute("DELETE FROM media_embeddings WHERE analysis_id = ?", (analysis_id,))
                self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount != 1:
            return None
        return self.get_media_analysis(project_id=project_id, analysis_id=analysis_id)

    @staticmethod
    def _is_media_analysis_final(item: dict[str, Any]) -> bool:
        return item["status"] in {
            MediaAnalysisStatus.SUCCEEDED.value, MediaAnalysisStatus.NEEDS_REVIEW.value,
            MediaAnalysisStatus.FAILED.value, MediaAnalysisStatus.CANCELLED.value,
        }

    def _media_analysis_by_idempotency(self, project_id: str, asset_id: str, idempotency_key: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            "SELECT * FROM media_analysis_runs WHERE project_id = ? AND asset_id = ? AND idempotency_key = ?",
            (project_id, asset_id, idempotency_key),
        )
        return self.get_media_analysis(project_id=project_id, analysis_id=str(row["analysis_id"])) if row is not None else None

    @staticmethod
    def _media_analysis_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["cancel_requested"] = bool(payload["cancel_requested"])
        payload["result"] = json.loads(payload.pop("result_json")) if payload["result_json"] else None
        return payload

