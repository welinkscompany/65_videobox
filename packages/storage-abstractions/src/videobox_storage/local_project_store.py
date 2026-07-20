from __future__ import annotations

import json
import hashlib
import math
from copy import deepcopy
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_domain_models.projects import ProjectRecord
from videobox_domain_models.recommendations import RecommendationRecord, RecommendationType
from videobox_domain_models.transcripts import TranscriptRecord
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_core_engine.exact_preview import ExactPreviewRequest
from videobox_storage.sqlite_schema import PROJECT_SCHEMA_STATEMENTS
from videobox_domain_models.director_proposals import DirectorProposal
from videobox_core_engine.director_proposals import proposal_from_payload, proposal_to_payload
from videobox_core_engine.creation_interview import (
    CreationInterviewRuntime,
    DeterministicCreationInterviewRuntime,
    MAX_CREATION_INTERVIEW_QUESTIONS,
)

# Heavy exports (rendered mp4s, CapCut drafts) can be large; keep only the most
# recent N per export_type per project so disk usage does not grow unbounded.
DEFAULT_EXPORT_RETENTION_COUNT = 5
RETIRED_CREDENTIAL_TABLE = "g" + "emini_provider_keys"


class EditingSessionRevisionConflict(RuntimeError):
    """The persisted editing-session revision did not match the requested CAS revision."""


class EditingSessionPostCommitFileWriteError(OSError):
    """SQLite committed an editing session, but its convenience JSON mirror did not.

    The SQLite ``session_json`` column is authoritative and will recreate the
    mirror on the next read.  Callers that own files registered in the same
    transaction must therefore *not* compensate those files.
    """


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_review_flag_code(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()


VALID_STORE_BLOCKING_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "sfx_review_required",
    "tts_replacement_review_required",
}
VALID_STORE_TRACK_TYPES = {"narration", "broll", "bgm", "sfx"}
VALID_STORE_BLOCKING_RECOMMENDATION_TYPES = {
    RecommendationType.TTS_REPLACEMENT.value,
    RecommendationType.BROLL.value,
    RecommendationType.BGM.value,
    RecommendationType.SFX.value,
    RecommendationType.OVERLAY.value,
}


def _is_store_supported_recommendation_type(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_recommendation_type(item.get("recommendation_type")) in VALID_STORE_BLOCKING_RECOMMENDATION_TYPES


def _is_store_supported_track(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_track_type(item.get("track_type")) in VALID_STORE_TRACK_TYPES


def _is_store_supported_track_summary(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return _canonical_track_type(item.get("track_type")) in VALID_STORE_TRACK_TYPES


def _is_store_blocking_review_flag(flag: object) -> bool:
    if not isinstance(flag, dict):
        return False
    code = flag.get("code")
    segment_id = flag.get("segment_id")
    return (
        isinstance(code, str)
        and _canonical_review_flag_code(code) in VALID_STORE_BLOCKING_REVIEW_FLAG_CODES
        and isinstance(segment_id, str)
        and bool(segment_id.strip())
    )


def _is_store_blocking_pending_recommendation(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    recommendation_id = item.get("recommendation_id")
    target_segment_id = item.get("target_segment_id")
    recommendation_type = item.get("recommendation_type")
    decision_state = str(item.get("decision_state") or "").strip().lower()
    if decision_state and decision_state != "pending":
        return False
    if _normalize_boolish(item.get("auto_apply_allowed", False)) and not _normalize_boolish(
        item.get("review_required", False)
    ):
        return False
    return (
        isinstance(recommendation_id, str)
        and bool(recommendation_id.strip())
        and isinstance(target_segment_id, str)
        and bool(target_segment_id.strip())
        and _canonical_recommendation_type(recommendation_type) in VALID_STORE_BLOCKING_RECOMMENDATION_TYPES
    )


def _normalize_review_flag_payloads(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = _canonical_review_flag_code(item.get("code"))
        segment_id = str(item.get("segment_id") or "").strip()
        if not code or not segment_id:
            continue
        message = str(item.get("message") or "").strip()
        normalized.append(
            {
                "code": code,
                "segment_id": segment_id,
                "message": message or "Operator review required before approval or output.",
            }
        )
    return normalized


def _timeline_summary_json(payload: dict[str, Any]) -> str:
    tracks = payload.get("tracks", [])
    review_flags = payload.get("review_flags", [])
    applied_recommendations = payload.get("applied_recommendations", [])
    pending_recommendations = payload.get("pending_recommendations", [])
    return json.dumps(
        {
            "track_count": sum(1 for track in tracks if _is_store_supported_track(track))
            if isinstance(tracks, list)
            else 0,
            "review_flag_count": sum(
                1 for flag in review_flags if _is_store_blocking_review_flag(flag)
            )
            if isinstance(review_flags, list)
            else 0,
            "applied_recommendation_count": sum(
                1
                for item in applied_recommendations
                if _is_store_supported_recommendation_type(item)
            )
            if isinstance(applied_recommendations, list)
            else 0,
            "pending_recommendation_count": sum(
                1
                for item in pending_recommendations
                if _is_store_blocking_pending_recommendation(item)
            )
            if isinstance(pending_recommendations, list)
            else 0,
        },
        ensure_ascii=True,
    )


class LocalProjectStore:
    def __init__(
        self,
        projects_root: Path,
        now: Callable[[], datetime] | None = None,
        *,
        atomic_bundle_fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.projects_root = Path(projects_root)
        self._clock = now or (lambda: datetime.now(UTC))
        # A new store instance is a new local API process.  Exact-preview
        # workers lease this epoch, which lets startup reclaim a recent dead
        # process without weakening the generation/owner publish fence.
        self.exact_preview_process_epoch = uuid.uuid4().hex
        # Deliberately injectable only for deterministic failure-contract tests.
        # Production callers leave this unset; it is never a runtime provider hook.
        self._atomic_bundle_fault_hook = atomic_bundle_fault_hook
        self._reconcile_batch_director_operations()
        self._reconcile_atomic_draft_bundle_operations()

    def _reconcile_atomic_draft_bundle_operations(self) -> None:
        """Discard uncommitted draft-bundle stages left by a crash.

        The SQLite bundle row is authoritative.  A stage with no matching
        committed bundle is disposable and must never become a later draft.
        """
        projects = self.projects_root / "projects"
        if not projects.exists(): return
        for project_root in projects.iterdir():
            staging = project_root / "staging"
            if not staging.is_dir(): continue
            for candidate in staging.glob("draft-bundle-*"):
                manifest = candidate / "operation.json"
                if candidate.is_dir() and manifest.exists(): shutil.rmtree(candidate, ignore_errors=True)

    def _write_atomic_bundle_manifest(self, stage: Path, manifest: dict[str, Any]) -> None:
        """Durably publish the stage inventory before any mirror is made visible."""
        target = stage / "operation.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(target)

    def _atomic_bundle_fault(self, event: str) -> None:
        if self._atomic_bundle_fault_hook is not None:
            self._atomic_bundle_fault_hook(event)

    def bootstrap_project(self, name: str) -> ProjectRecord:
        project = ProjectRecord.create(name=name)
        project_root = self.project_root(project.project_id)
        self._create_project_layout(project_root)
        self._bootstrap_database(project_root / "db" / "project.sqlite", project)
        return project

    def list_projects(self) -> list[dict[str, Any]]:
        projects_directory = self.projects_root / "projects"
        if not projects_directory.exists():
            return []
        items: list[dict[str, Any]] = []
        for project_directory in sorted(projects_directory.iterdir()):
            if not project_directory.is_dir():
                continue
            database_path = project_directory / "db" / "project.sqlite"
            if not database_path.exists():
                continue
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    """
                    SELECT project_id, name, status, root_storage_uri, created_at, updated_at
                    FROM projects
                    LIMIT 1
                    """
                ).fetchone()
            finally:
                connection.close()
            if row is not None:
                items.append(dict(row))
        return items

    def list_all_jobs(self) -> list[dict[str, Any]]:
        # Jobs live in one SQLite file per project (see database_path) with no
        # shared/global jobs table, so a cross-project view has to iterate
        # every project directory and merge — the same approach list_projects
        # already uses. Fine at the project counts a local-first single-user
        # tool expects; would need a real index if that ever changes.
        all_jobs: list[dict[str, Any]] = []
        for project in self.list_projects():
            project_id = str(project["project_id"])
            for job in self.list_jobs(project_id=project_id):
                all_jobs.append({"project_name": project["name"], **job})
        return all_jobs

    def project_root(self, project_id: str) -> Path:
        return self.projects_root / "projects" / project_id

    def _reconcile_batch_director_operations(self) -> None:
        """Recover only disposable batch-apply files left around a process crash.

        A manifest is deliberately filesystem-durable before bytes leave staging.
        On restart, a destination is preserved only when SQLite owns the exact
        URI and hash; every other staged/destination file is compensation work.
        """
        projects = self.projects_root / "projects"
        if not projects.exists():
            return
        for project_root in projects.iterdir():
            if not project_root.is_dir() or not (project_root / "db" / "project.sqlite").is_file():
                continue
            operations = project_root / ".batch-director-operations"
            if not operations.exists():
                continue
            project_id = project_root.name
            for manifest in operations.glob("*.json"):
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                    if not self._batch_manifest_paths_are_safe(
                        project_root=project_root,
                        operations=operations,
                        manifest=manifest,
                        payload=payload,
                    ):
                        # A manifest can be hand-edited or partially corrupt.
                        # Retain it for inspection rather than using its paths
                        # as deletion authority.
                        continue
                    entries = list(payload.get("entries") or []) if isinstance(payload, dict) else []
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        destination = Path(str(entry.get("destination_path") or ""))
                        staged = Path(str(entry.get("staged_path") or ""))
                        digest = str(entry.get("sha256") or "")
                        if destination.exists() and not self._batch_destination_is_registered(project_id, destination, digest):
                            destination.unlink()
                        if staged.exists():
                            staged.unlink()
                        if staged.parent != operations and staged.parent.exists() and not any(staged.parent.iterdir()):
                            staged.parent.rmdir()
                except (OSError, ValueError, json.JSONDecodeError):
                    # A corrupt manifest must not make startup unavailable;
                    # it is retained for operator inspection rather than
                    # guessing which files it owns.
                    continue
                manifest.unlink(missing_ok=True)
            # ``.tmp`` is only the atomically-written manifest sidecar.  It is
            # safe to remove from the operation root even when no final JSON
            # was written; do not infer ownership from arbitrary nested files.
            for temporary in operations.glob("*.tmp"):
                if temporary.is_file():
                    temporary.unlink(missing_ok=True)
            for operation_dir in operations.iterdir():
                if operation_dir.is_dir() and not any(operation_dir.iterdir()):
                    operation_dir.rmdir()
            if operations.exists() and not any(operations.iterdir()):
                operations.rmdir()

    @staticmethod
    def _batch_manifest_paths_are_safe(*, project_root: Path, operations: Path, manifest: Path, payload: object) -> bool:
        """Return true only when every cleanup path is one this batch owns."""
        if not isinstance(payload, dict):
            return False
        operation_id = payload.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id or manifest.stem != operation_id:
            return False
        operation_root = (operations / operation_id).resolve()
        # Current batch materialization uses assets/imported.  The media roots
        # remain accepted solely for pre-existing project layouts that used the
        # same crash-recovery manifest contract.
        destination_roots = tuple(
            (project_root / relative).resolve()
            for relative in (Path("assets") / "imported", Path("media") / "broll", Path("media") / "bgm", Path("media") / "sfx")
        )
        try:
            operation_root.relative_to(operations.resolve())
            for destination_root in destination_roots:
                destination_root.relative_to(project_root.resolve())
        except ValueError:
            return False
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            staged_value = entry.get("staged_path")
            destination_value = entry.get("destination_path")
            digest = entry.get("sha256")
            if not isinstance(staged_value, str) or not isinstance(destination_value, str) or not isinstance(digest, str) or not digest:
                return False
            try:
                resolved_staged = Path(staged_value).resolve()
                # Older manifests used a one-file stage directly under the
                # operations root.  Keep recovery compatible, but never allow
                # another operation directory to be claimed.
                if not _is_relative_to(resolved_staged, operation_root) and resolved_staged.parent != operations.resolve():
                    return False
                resolved_destination = Path(destination_value).resolve()
                if not any(_is_relative_to(resolved_destination, root) for root in destination_roots):
                    return False
            except ValueError:
                return False
        return True

    def _batch_destination_is_registered(self, project_id: str, destination: Path, digest: str) -> bool:
        try:
            root = self.project_root(project_id).resolve()
            resolved = destination.resolve()
            if root not in resolved.parents or not digest or not resolved.is_file() or sha256_file(resolved) != digest:
                return False
            uri = self._path_to_uri(project_id, resolved)
            connection = sqlite3.connect(self.database_path(project_id))
            try:
                row = connection.execute("SELECT asset_id FROM assets WHERE project_id = ? AND storage_uri = ?", (project_id, uri)).fetchone()
                return row is not None
            finally:
                connection.close()
        except (OSError, ValueError, sqlite3.Error):
            return False

    def database_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "db" / "project.sqlite"

    def begin_exact_preview(
        self, *, project_id: str, request: Any, fingerprint: str, duration_sec: float | None = None
    ) -> dict[str, Any]:
        """Create or coalesce a durable exact-preview generation.

        This is deliberately storage-only: ffmpeg workers claim and publish a
        generation separately, so a late worker cannot turn an obsolete record
        back into the current artifact.
        """
        session_id = str(request.session_id)
        expected_revision = int(request.expected_revision)
        profile = str(request.profile)
        cache_key = str(request.cache_key(source_fingerprint=fingerprint))
        if request.end_sec is not None and duration_sec is None:
            raise ValueError("exact_preview_duration_required")
        if duration_sec is not None:
            request.validate_duration(float(duration_sec))
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            ).fetchone()
            if session is None:
                raise KeyError(f"Editing session not found: {session_id}")
            if int(session["session_revision"]) != expected_revision:
                raise EditingSessionRevisionConflict("exact preview session revision is stale")
            existing = connection.execute(
                """SELECT * FROM exact_preview_renders WHERE project_id = ? AND session_id = ?
                   AND cache_key = ? AND state IN ('pending', 'running', 'succeeded')
                   ORDER BY created_at DESC LIMIT 1""",
                (project_id, session_id, cache_key),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._exact_preview_row(dict(existing))
            connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = 'superseded', updated_at = ?
                   WHERE project_id = ? AND session_id = ? AND state IN ('pending', 'running', 'succeeded')""",
                (now, now, project_id, session_id),
            )
            generation_id = f"exact_preview_{uuid.uuid4().hex}"
            connection.execute(
                """INSERT INTO exact_preview_renders (
                    generation_id, project_id, session_id, expected_revision, cache_key, fingerprint,
                    start_sec, end_sec, duration_sec, profile, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (generation_id, project_id, session_id, expected_revision, cache_key, fingerprint,
                 request.start_sec, request.end_sec, duration_sec, profile, now, now),
            )
            row = connection.execute("SELECT * FROM exact_preview_renders WHERE generation_id = ?", (generation_id,)).fetchone()
            connection.commit()
            return self._exact_preview_row(dict(row))
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def claim_exact_preview(self, *, project_id: str, generation_id: str, owner_token: str) -> bool:
        if not owner_token:
            raise ValueError("exact_preview_claim_token_required")
        connection = self._connection(project_id)
        try:
            now = self._now_iso()
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'running', claim_token = ?, claimed_at = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'pending'""",
                (owner_token, now, now, project_id, generation_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def finish_exact_preview(
        self, *, project_id: str, generation_id: str, fingerprint: str, artifact_path: Path, owner_token: str
    ) -> bool:
        """Atomically copy/rename then publish only a still-current generation."""
        artifact_path = Path(artifact_path)
        if not owner_token:
            raise ValueError("exact_preview_claim_token_required")
        if not artifact_path.is_file():
            raise FileNotFoundError(artifact_path)
        connection = self._connection(project_id)
        temporary: Path | None = None
        published: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id)).fetchone()
            if (
                row is None
                or str(row["fingerprint"]) != fingerprint
                or str(row["state"]) != "running"
                or str(row["claim_token"] or "") != owner_token
            ):
                connection.rollback()
                return False
            current = connection.execute(
                "SELECT session_revision FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, str(row["session_id"])),
            ).fetchone()
            if current is None or int(current["session_revision"]) != int(row["expected_revision"]):
                connection.execute("UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?, invalidated_reason = 'session_revision_changed', updated_at = ? WHERE generation_id = ?", (self._now_iso(), self._now_iso(), generation_id))
                connection.commit()
                return False
            destination_dir = self.project_root(project_id) / "derived" / "exact_previews"
            destination_dir.mkdir(parents=True, exist_ok=True)
            published = destination_dir / f"{generation_id}.mp4"
            temporary = destination_dir / f".{generation_id}.{uuid.uuid4().hex}.tmp"
            shutil.copyfile(artifact_path, temporary)
            temporary.replace(published)
            uri = self._path_to_uri(project_id, published)
            # Fence again after the filesystem publication but before the DB pointer.
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'succeeded', artifact_uri = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND fingerprint = ?
                   AND state = 'running' AND claim_token = ?""",
                (uri, self._now_iso(), project_id, generation_id, fingerprint, owner_token),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                published.unlink(missing_ok=True)
                return False
            connection.commit()
            return True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            if published is not None:
                published.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            connection.close()

    def get_exact_preview(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT * FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, generation_id))
        if row is None:
            raise KeyError(f"Exact preview not found: {generation_id}")
        return self._exact_preview_row(dict(row))

    def get_latest_exact_preview(self, *, project_id: str, session_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            """SELECT * FROM exact_preview_renders WHERE project_id = ? AND session_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (project_id, session_id),
        )
        return self._exact_preview_row(dict(row)) if row is not None else None

    def mark_exact_preview_stale(self, *, project_id: str, generation_id: str, reason: str) -> bool:
        """Invalidate a durable preview after read-time source/revision validation."""
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ?
                   AND state IN ('pending', 'running', 'succeeded')""",
                (self._now_iso(), reason, self._now_iso(), project_id, generation_id),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def fail_exact_preview(self, *, project_id: str, generation_id: str, owner_token: str, error_message: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = ?, updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'running' AND claim_token = ?""",
                (error_message[:1000], self._now_iso(), project_id, generation_id, owner_token),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def recover_stale_exact_preview_claims(self, *, project_id: str, older_than_seconds: float = 900) -> int:
        cutoff = (self._clock() - timedelta(seconds=older_than_seconds)).isoformat()
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = 'stale_running_claim',
                   updated_at = ? WHERE project_id = ? AND state = 'running' AND claimed_at < ?""",
                (self._now_iso(), project_id, cutoff),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def recover_inherited_exact_preview_claims(self, *, project_id: str, process_epoch: str) -> int:
        """Fence off running claims owned by a previous local API process."""
        if not process_epoch:
            raise ValueError("exact_preview_process_epoch_required")
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'failed', error_message = 'process_restarted',
                   updated_at = ?
                   WHERE project_id = ? AND state = 'running'
                   AND (claim_token IS NULL OR claim_token NOT LIKE ?)""",
                (self._now_iso(), project_id, f"exact-preview-worker:{process_epoch}:%"),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def retry_exact_preview(self, *, project_id: str, generation_id: str) -> dict[str, Any]:
        row = self.get_exact_preview(project_id=project_id, generation_id=generation_id)
        if str(row["state"]) != "failed":
            raise ValueError("exact_preview_retry_not_failed")
        request = ExactPreviewRequest(
            session_id=str(row["session_id"]), expected_revision=int(row["expected_revision"]),
            start_sec=row["start_sec"], end_sec=row["end_sec"], profile=str(row["profile"]),
        )
        duration_sec = row.get("duration_sec")
        if request.end_sec is not None and duration_sec is None:
            raise ValueError("exact_preview_duration_required")
        if duration_sec is not None:
            request.validate_duration(float(duration_sec))
        # Failed rows must not coalesce with a retry; a distinct cache identity
        # makes generation ownership explicit while preserving the source fence.
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
                   invalidated_reason = 'retry', updated_at = ?
                   WHERE project_id = ? AND generation_id = ? AND state = 'failed'""",
                (self._now_iso(), self._now_iso(), project_id, generation_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ValueError("exact_preview_retry_not_failed")
            connection.commit()
        finally:
            connection.close()
        return self.begin_exact_preview(
            project_id=project_id, request=request, fingerprint=str(row["fingerprint"]), duration_sec=duration_sec
        )

    def cleanup_exact_preview_artifacts(
        self, *, project_id: str, keep_last: int = 5, orphan_older_than_seconds: float = 300
    ) -> int:
        """Prune retained stale rows and crash-orphaned files inside this project only."""
        rows = self._fetchall(project_id, "SELECT generation_id, artifact_uri FROM exact_preview_renders WHERE project_id = ? AND state IN ('obsolete', 'failed') ORDER BY updated_at DESC", (project_id,))
        removed = 0
        for row in rows[max(keep_last, 0):]:
            uri = row["artifact_uri"]
            if uri:
                self.resolve_storage_uri(project_id=project_id, storage_uri=str(uri)).unlink(missing_ok=True)
            self._execute(project_id, "DELETE FROM exact_preview_renders WHERE project_id = ? AND generation_id = ?", (project_id, str(row["generation_id"])))
            removed += 1
        preview_root = self.project_root(project_id) / "derived" / "exact_previews"
        if not preview_root.is_dir():
            return removed
        referenced = {
            self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["artifact_uri"])).resolve()
            for row in self._fetchall(
                project_id,
                "SELECT artifact_uri FROM exact_preview_renders WHERE project_id = ? AND artifact_uri IS NOT NULL",
                (project_id,),
            )
        }
        active_generation_ids = {
            str(row["generation_id"])
            for row in self._fetchall(
                project_id,
                "SELECT generation_id FROM exact_preview_renders WHERE project_id = ? AND state IN ('pending', 'running')",
                (project_id,),
            )
        }
        root = preview_root.resolve()
        cutoff = self._clock().timestamp() - orphan_older_than_seconds
        for candidate in preview_root.iterdir():
            try:
                resolved = candidate.resolve()
                if not _is_relative_to(resolved, root) or resolved in referenced or not candidate.is_file():
                    continue
                # Only this renderer's published names and atomic temporary
                # names are eligible; unrelated derived files are untouched.
                if not (candidate.name.startswith("exact_preview_") and candidate.suffix == ".mp4") and not candidate.name.startswith(".exact_preview_"):
                    continue
                # finish_exact_preview publishes `.<generation>.<nonce>.tmp`
                # then `<generation>.mp4` before its fenced DB pointer update.
                # Those files are deliberately unreferenced during that small
                # window, so an active claim is an ownership fence for cleanup.
                if any(
                    candidate.name == f"{generation_id}.mp4"
                    or candidate.name.startswith(f".{generation_id}.")
                    for generation_id in active_generation_ids
                ):
                    continue
                if candidate.stat().st_mtime > cutoff:
                    continue
                candidate.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    @staticmethod
    def _exact_preview_row(row: dict[str, Any]) -> dict[str, Any]:
        row["start_sec"] = float(row["start_sec"]) if row.get("start_sec") is not None else None
        row["end_sec"] = float(row["end_sec"]) if row.get("end_sec") is not None else None
        row["duration_sec"] = float(row["duration_sec"]) if row.get("duration_sec") is not None else None
        row["expected_revision"] = int(row["expected_revision"])
        return row

    def thumbnail_storage_path(self, *, project_id: str, asset_id: str) -> Path:
        return self.project_root(project_id) / "derived" / "thumbnails" / f"{asset_id}.jpg"

    def thumbnail_storage_uri(self, *, project_id: str, asset_id: str) -> str:
        return self._path_to_uri(project_id, self.thumbnail_storage_path(project_id=project_id, asset_id=asset_id))

    def get_project(self, *, project_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT project_id, name, status, root_storage_uri, created_at, updated_at
            FROM projects
            WHERE project_id = ?
            """,
            (project_id,),
        )
        if row is None:
            raise KeyError(f"Project not found: {project_id}")
        return dict(row)

    def consume_hermes_capability(self, *, project_id: str, jti: str, expires_at: int) -> str:
        """Atomically consume one project-scoped capability across API restarts."""
        connection = self._connection(project_id)
        try:
            existing = connection.execute(
                "SELECT state FROM hermes_capability_ledger WHERE project_id = ? AND jti = ?",
                (project_id, jti),
            ).fetchone()
            if existing is not None:
                result = str(existing["state"])
            else:
                try:
                    connection.execute(
                        "INSERT INTO hermes_capability_ledger (project_id, jti, state, expires_at, recorded_at) VALUES (?, ?, 'consumed', ?, ?)",
                        (project_id, jti, expires_at, self._now_iso()),
                    )
                    connection.commit()
                    result = "accepted"
                except sqlite3.IntegrityError:
                    connection.rollback()
                    row = connection.execute(
                        "SELECT state FROM hermes_capability_ledger WHERE project_id = ? AND jti = ?",
                        (project_id, jti),
                    ).fetchone()
                    result = str(row["state"]) if row is not None else "unavailable"
        finally:
            connection.close()
        self._purge_expired_hermes_capabilities(project_id=project_id)
        return result

    def revoke_hermes_capability(self, *, project_id: str, jti: str, expires_at: int) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute(
                """
                INSERT INTO hermes_capability_ledger (project_id, jti, state, expires_at, recorded_at)
                VALUES (?, ?, 'revoked', ?, ?)
                ON CONFLICT (project_id, jti) DO UPDATE SET
                    state = EXCLUDED.state,
                    expires_at = EXCLUDED.expires_at,
                    recorded_at = EXCLUDED.recorded_at
                """,
                (project_id, jti, expires_at, self._now_iso()),
            )
            connection.commit()
        finally:
            connection.close()
        self._purge_expired_hermes_capabilities(project_id=project_id)

    def _purge_expired_hermes_capabilities(self, *, project_id: str) -> None:
        """Bound the short-lived capability ledger after its decision is committed."""
        connection = self._connection(project_id)
        try:
            connection.execute(
                "DELETE FROM hermes_capability_ledger WHERE project_id = ? AND expires_at <= ?",
                (project_id, int(self._clock().timestamp())),
            )
            connection.commit()
        finally:
            connection.close()

    def create_creation_brief(
        self,
        *,
        project_id: str,
        script_filename: str,
        script_text: str,
        idempotency_key: str,
        capability_profile: dict[str, Any],
        script_asset_id: str | None = None,
        runtime: CreationInterviewRuntime | None = None,
    ) -> dict[str, Any]:
        """Persist a local-only interview before any optional provider exists."""
        self._validate_creation_brief_input(
            script_filename=script_filename, script_text=script_text, idempotency_key=idempotency_key
        )
        existing = self._fetchone(
            project_id, "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)
        )
        if existing is not None:
            return self._creation_brief_payload(existing)
        owned_script_asset = script_asset_id is None
        if script_asset_id is None:
            script_asset_id = self._materialize_creation_brief_script(
                project_id=project_id, script_filename=script_filename, script_text=script_text
            )
        else:
            asset = self.get_asset(project_id=project_id, asset_id=script_asset_id)
            if asset["asset_type"] != AssetType.SCRIPT_DOCUMENT.value:
                raise ValueError("creation_brief_script_asset_invalid")
        planner = runtime or DeterministicCreationInterviewRuntime()
        try:
            questions = self._normalize_creation_interview_questions(
                planner.plan_questions(script_text=script_text)
            )
        except Exception:
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            raise
        now = self._clock().isoformat()
        brief_id = f"brief-{uuid.uuid4().hex}"
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                connection.commit()
                payload = self._creation_brief_payload(existing)
                # A competing request may have materialized its retained
                # input while waiting for the idempotency-row lock. It never
                # became part of the winning brief, so remove it before
                # returning the durable winner.
                if owned_script_asset and script_asset_id:
                    connection.close()
                    self.delete_asset(project_id=project_id, asset_id=script_asset_id)
                return payload
            connection.execute(
                """
                INSERT INTO creation_briefs (
                    brief_id, project_id, idempotency_key, script_filename, script_text,
                    script_asset_id, script_asset_owned, capability_profile_json, questions_json, answers_json,
                    current_step, status, revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 0, 'interviewing', 1, ?, ?)
                """,
                (
                    brief_id, project_id, idempotency_key, script_filename, script_text,
                    script_asset_id, int(owned_script_asset), json.dumps(capability_profile, ensure_ascii=False, sort_keys=True),
                    json.dumps(questions, ensure_ascii=False), now, now,
                ),
            )
            row = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(row)
        except sqlite3.IntegrityError:
            connection.rollback()
            existing = self._fetchone(
                project_id, "SELECT * FROM creation_briefs WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)
            )
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            if existing is None:
                raise
            return self._creation_brief_payload(existing)
        except Exception:
            connection.rollback()
            if owned_script_asset and script_asset_id:
                self.delete_asset(project_id=project_id, asset_id=script_asset_id)
            raise
        finally:
            connection.close()

    def get_creation_brief(self, *, project_id: str, brief_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?",
            (project_id, brief_id),
        )
        if row is None:
            raise KeyError(f"Creation brief not found: {brief_id}")
        return self._creation_brief_payload(row)

    def list_creation_briefs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? ORDER BY created_at DESC, brief_id DESC",
                (project_id,),
            ).fetchall()
            return [self._creation_brief_payload(row) for row in rows]
        finally:
            connection.close()

    def answer_creation_brief_question(
        self, *, project_id: str, brief_id: str, question_id: str, answer: str, expected_revision: int
    ) -> dict[str, Any]:
        normalized = answer.strip()
        if not normalized:
            raise ValueError("creation_brief_answer_required")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            ).fetchone()
            if row is None:
                raise KeyError(f"Creation brief not found: {brief_id}")
            self._assert_creation_brief_mutable(row)
            if int(row["revision"]) != expected_revision:
                raise ValueError("creation_brief_revision_conflict")
            if row["status"] != "interviewing":
                raise ValueError("creation_brief_not_interviewing")
            questions = json.loads(row["questions_json"])
            question = next((item for item in questions if item["question_id"] == question_id), None)
            if question is None:
                raise ValueError("creation_brief_question_not_found")
            if questions[int(row["current_step"])]["question_id"] != question_id:
                raise ValueError("creation_brief_question_not_current")
            answers = json.loads(row["answers_json"])
            answers[question["field"]] = normalized
            # The cursor advances from the question just answered.  Counting all
            # saved answers would skip a question after the creator returns to
            # revise an earlier answer.
            current_step = questions.index(question) + 1
            status = "ready_for_approval" if current_step == len(questions) else "interviewing"
            connection.execute(
                """UPDATE creation_briefs
                   SET answers_json = ?, current_step = ?, status = ?, revision = revision + 1, updated_at = ?
                   WHERE project_id = ? AND brief_id = ?""",
                (json.dumps(answers, ensure_ascii=False, sort_keys=True), current_step, status, self._clock().isoformat(), project_id, brief_id),
            )
            updated = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def bypass_creation_interview(
        self, *, project_id: str, brief_id: str, expected_revision: int | None = None
    ) -> dict[str, Any]:
        """Make the explicit manual choice durable; approval remains separate."""
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: (
                {item["field"]: json.loads(row["answers_json"]).get(item["field"], "건너뛰기") for item in json.loads(row["questions_json"])},
                len(json.loads(row["questions_json"])), "ready_for_approval", row["summary_text"],
            ),
        )

    def previous_creation_brief_question(
        self, *, project_id: str, brief_id: str, expected_revision: int
    ) -> dict[str, Any]:
        """Return to the prior durable question without discarding saved answers.

        A changed answer can alter the generated summary, so any earlier summary is
        cleared and must be reviewed again before approval.
        """
        def previous(row: sqlite3.Row) -> tuple[dict[str, str], int, str, str]:
            questions = json.loads(row["questions_json"])
            current_step = int(row["current_step"])
            if current_step <= 0 or not questions:
                raise ValueError("creation_brief_previous_question_unavailable")
            return (
                json.loads(row["answers_json"]),
                min(current_step - 1, len(questions) - 1),
                "interviewing",
                "",
            )

        return self._mutate_creation_brief(
            project_id=project_id,
            brief_id=brief_id,
            expected_revision=expected_revision,
            mutation=previous,
        )

    def update_creation_brief_summary(
        self, *, project_id: str, brief_id: str, summary: str, expected_revision: int
    ) -> dict[str, Any]:
        if not summary.strip():
            raise ValueError("creation_brief_summary_required")
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: (json.loads(row["answers_json"]), row["current_step"], "ready_for_approval", summary.strip()),
        )

    def approve_creation_brief(self, *, project_id: str, brief_id: str, expected_revision: int) -> dict[str, Any]:
        return self._mutate_creation_brief(
            project_id=project_id, brief_id=brief_id, expected_revision=expected_revision,
            mutation=lambda row: self._creation_brief_approval_mutation(row),
        )

    @staticmethod
    def _creation_brief_approval_mutation(row: sqlite3.Row) -> tuple[dict[str, str], int, str, str]:
        if str(row["status"]) != "ready_for_approval":
            raise ValueError("creation_brief_not_ready_for_approval")
        if not str(row["summary_text"]).strip():
            raise ValueError("creation_brief_summary_required")
        return json.loads(row["answers_json"]), int(row["current_step"]), "approved", str(row["summary_text"])

    def _mutate_creation_brief(
        self, *, project_id: str, brief_id: str, expected_revision: int | None,
        mutation: Callable[[sqlite3.Row], tuple[dict[str, str], int, str, str]],
    ) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)).fetchone()
            if row is None:
                raise KeyError(f"Creation brief not found: {brief_id}")
            self._assert_creation_brief_mutable(row)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError("creation_brief_revision_conflict")
            answers, current_step, status, summary = mutation(row)
            connection.execute(
                """UPDATE creation_briefs SET answers_json = ?, current_step = ?, status = ?, summary_text = ?,
                   revision = revision + 1, updated_at = ? WHERE project_id = ? AND brief_id = ?""",
                (json.dumps(answers, ensure_ascii=False, sort_keys=True), current_step, status, summary, self._clock().isoformat(), project_id, brief_id),
            )
            updated = connection.execute("SELECT * FROM creation_briefs WHERE brief_id = ?", (brief_id,)).fetchone()
            connection.commit()
            return self._creation_brief_payload(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _assert_creation_brief_mutable(row: sqlite3.Row) -> None:
        if row["status"] == "approved":
            raise ValueError("creation_brief_immutable")

    def delete_creation_brief(self, *, project_id: str, brief_id: str) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT script_asset_id, script_asset_owned FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            ).fetchone()
            cursor = connection.execute(
                "DELETE FROM creation_briefs WHERE project_id = ? AND brief_id = ?", (project_id, brief_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Creation brief not found: {brief_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is not None and bool(row["script_asset_owned"]) and row["script_asset_id"]:
            self.delete_asset(project_id=project_id, asset_id=str(row["script_asset_id"]))

    def _materialize_creation_brief_script(self, *, project_id: str, script_filename: str, script_text: str) -> str:
        directory = self.project_root(project_id) / "inputs" / "scripts"
        directory.mkdir(parents=True, exist_ok=True)
        staging = directory / f".creation-brief-{uuid.uuid4().hex}-{Path(script_filename).name}"
        try:
            staging.write_text(script_text, encoding="utf-8")
            asset = self.register_asset(
                project_id=project_id, asset_type=AssetType.SCRIPT_DOCUMENT, source_path=staging,
                source_kind="creation_brief_retained_input", mime_type="text/plain",
            )
            return asset.asset_id
        finally:
            staging.unlink(missing_ok=True)

    @staticmethod
    def _validate_creation_brief_input(*, script_filename: str, script_text: str, idempotency_key: str) -> None:
        if Path(script_filename).suffix.lower() not in {".txt", ".md", ".srt"}:
            raise ValueError("creation_brief_script_extension_invalid")
        if not idempotency_key.strip():
            raise ValueError("creation_brief_idempotency_key_required")
        if not script_text.strip():
            raise ValueError("creation_brief_script_empty")
        try:
            size = len(script_text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("creation_brief_script_not_utf8") from exc
        if size > 1024 * 1024:
            raise ValueError("creation_brief_script_too_large")

    @staticmethod
    def _normalize_creation_interview_questions(items: object) -> list[dict[str, str]]:
        if not isinstance(items, list):
            raise ValueError("creation_brief_questions_invalid")
        if len(items) > MAX_CREATION_INTERVIEW_QUESTIONS:
            raise ValueError("creation_brief_questions_too_many")
        normalized: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_fields: set[str] = set()
        for index, item in enumerate(items):
            field = str(getattr(item, "field", "")).strip()
            prompt = str(getattr(item, "prompt", "")).strip()
            provided_id = getattr(item, "question_id", None)
            question_id = f"question-{index + 1}" if provided_id is None else str(provided_id).strip()
            if not field or not prompt:
                raise ValueError("creation_brief_question_invalid")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", question_id):
                raise ValueError("creation_brief_question_id_invalid")
            if question_id in seen_ids:
                raise ValueError("creation_brief_question_id_duplicate")
            if field in seen_fields:
                raise ValueError("creation_brief_question_field_duplicate")
            seen_ids.add(question_id)
            seen_fields.add(field)
            normalized.append({"question_id": question_id, "field": field, "prompt": prompt})
        return normalized

    @staticmethod
    def _creation_brief_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "brief_id": row["brief_id"], "project_id": row["project_id"],
            "idempotency_key": row["idempotency_key"], "script_filename": row["script_filename"],
            "script_text": row["script_text"], "script_asset_id": row["script_asset_id"], "script_asset_owned": bool(row["script_asset_owned"]),
            "capability_profile": json.loads(row["capability_profile_json"]),
            "questions": json.loads(row["questions_json"]), "answers": json.loads(row["answers_json"]),
            "current_step": row["current_step"], "status": row["status"], "summary": row["summary_text"], "revision": row["revision"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    @staticmethod
    def _draft_readiness_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "readiness_id": row["readiness_id"], "project_id": row["project_id"], "brief_id": row["brief_id"],
            "approved_brief_revision": row["approved_brief_revision"], "input_fingerprint": row["input_fingerprint"],
            "narration": json.loads(row["narration_json"]), "capability": json.loads(row["capability_json"]),
            "idempotency_key": row["idempotency_key"], "status": row["status"], "revision": row["revision"],
            "cancel_requested": bool(row["cancel_requested"]), "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def _probe_playable_broll_duration(self, *, project_id: str, asset: dict[str, Any]) -> float | None:
        path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
        if not path.is_file() or shutil.which("ffprobe") is None:
            return None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            probe = json.loads(result.stdout) if result.returncode == 0 else {}
            duration_sec = float((probe.get("format") or {}).get("duration"))
            has_video = any(stream.get("codec_type") == "video" for stream in probe.get("streams") or [])
            return duration_sec if has_video and math.isfinite(duration_sec) and duration_sec > 0 else None
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _candidate_range_is_usable(candidate: dict[str, Any], duration_sec: float) -> bool:
        target_range = candidate.get("target_range") or {}
        try:
            start_sec, end_sec = float(target_range.get("start_sec")), float(target_range.get("end_sec"))
        except (TypeError, ValueError):
            return False
        return math.isfinite(start_sec) and math.isfinite(end_sec) and 0 <= start_sec < end_sec <= duration_sec

    def _draft_readiness_sources_match(self, *, project_id: str, result: dict[str, Any]) -> bool:
        try:
            for item in result.get("source_snapshot") or []:
                asset = self.get_asset(project_id=project_id, asset_id=str(item["asset_id"]))
                path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
                if not path.is_file() or sha256_file(path) != item.get("sha256"):
                    return False
        except (KeyError, TypeError, ValueError, OSError):
            return False
        return True

    def _normalize_draft_readiness_result(self, *, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._draft_readiness_sources_match(project_id=project_id, result=payload["result"]):
            return payload["result"]
        try:
            brief = self.get_creation_brief(project_id=project_id, brief_id=str(payload["brief_id"]))
            planned = self._draft_readiness_plan(project_id=project_id, brief=brief, narration=dict(payload["narration"]))
        except (KeyError, ValueError, TypeError):
            return payload["result"]
        existing = {str(item.get("asset_id")): item for item in payload["result"].get("broll_candidates", []) if isinstance(item, dict)}
        candidates = []
        for item in planned["broll_candidates"]:
            restored = deepcopy(item)
            previous = existing.get(str(item["asset_id"]))
            if previous and self._candidate_range_is_usable(previous, float(item["media_duration_sec"])):
                restored["target_range"] = deepcopy(previous["target_range"])
                restored["skipped"] = bool(previous.get("skipped"))
            candidates.append(restored)
        result = deepcopy(payload["result"])
        result["broll_candidates"] = candidates
        if candidates != payload["result"].get("broll_candidates", []) or (not result.get("gap_slots") and planned["gap_slots"]):
            result["gap_slots"] = planned["gap_slots"]
        result["source_snapshot"] = planned["source_snapshot"]
        return result

    def _draft_readiness_plan(self, *, project_id: str, brief: dict[str, Any], narration: dict[str, Any]) -> dict[str, Any]:
        sentences = [value.strip() for value in re.split(r"[.!?\n]+", str(brief["script_text"])) if value.strip()]
        segments = [{"segment_id": f"script-{index + 1}", "text": text, "start_sec": index * 5, "end_sec": (index + 1) * 5} for index, text in enumerate(sentences or [str(brief["script_text"]).strip()])]
        assets = self.list_assets(project_id=project_id)
        playable_broll = [(item, self._probe_playable_broll_duration(project_id=project_id, asset=item)) for item in assets if item["asset_type"] == AssetType.BROLL_VIDEO.value]
        playable_broll = [(item, duration_sec) for item, duration_sec in playable_broll if duration_sec is not None]
        broll = []
        for index, (segment, (item, duration_sec)) in enumerate(zip(segments, playable_broll)):
            broll.append({"asset_id": item["asset_id"], "rank": index + 1, "label": item["metadata"].get("title") or f"장면 영상 {index + 1}", "segment_id": segment["segment_id"], "target_range": {"start_sec": 0, "end_sec": min(5.0, duration_sec)}, "media_duration_sec": duration_sec, "media_type": "broll_video", "selection": item["asset_id"], "skipped": False})
        def choice(asset_type: AssetType, label: str) -> dict[str, Any]:
            item = next((asset for asset in assets if asset["asset_type"] == asset_type.value), None)
            return {"selection": item["asset_id"], "reason": "프로젝트 자산에서 골랐어요."} if item else {"selection": None, "reason": f"프로젝트에 사용할 {label}이 없어요."}
        covered_segment_ids = {str(item["segment_id"]) for item in broll}
        gaps = [
            {"gap_slot_id": f"gap-broll-{index + 1}", "segment_id": segment["segment_id"], "reason": "장면을 보여 줄 영상이 없어요.", "target_range": {"start_sec": segment["start_sec"], "end_sec": segment["end_sec"]}, "media_type": "broll_video"}
            for index, segment in enumerate(segments)
            if str(segment["segment_id"]) not in covered_segment_ids
        ]
        selected_ids = [brief.get("script_asset_id"), narration.get("asset_id")] + [item["asset_id"] for item in broll]
        snapshots = []
        for asset_id in dict.fromkeys(str(item) for item in selected_ids if item):
            asset = self.get_asset(project_id=project_id, asset_id=asset_id)
            path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(asset["storage_uri"]))
            if not path.is_file(): raise ValueError("draft_readiness_source_missing")
            snapshots.append({"asset_id": asset_id, "sha256": sha256_file(path), "media_revision": asset["created_at"], "asset_type": asset["asset_type"]})
        return {"script_segments": segments, "caption_texts": [item["text"] for item in segments], "narration": narration,
                "broll_candidates": broll, "bgm": choice(AssetType.BGM, "배경음"), "sfx": choice(AssetType.SFX, "효과음"), "gap_slots": gaps, "source_snapshot": snapshots}

    def start_draft_readiness(self, *, project_id: str, brief_id: str, narration_choice: dict[str, Any], idempotency_key: str, expected_brief_revision: int, capability: dict[str, Any] | None = None, defer: bool = True) -> dict[str, Any]:
        brief = self.get_creation_brief(project_id=project_id, brief_id=brief_id)
        if brief["status"] != "approved": raise ValueError("draft_readiness_brief_not_approved")
        if brief["revision"] != expected_brief_revision: raise ValueError("draft_readiness_brief_revision_conflict")
        kind = str(narration_choice.get("kind") or "")
        if kind not in {"silent", "existing", "source_video"}: raise ValueError("draft_readiness_narration_invalid")
        if kind in {"existing", "source_video"}:
            asset = self.get_asset(project_id=project_id, asset_id=str(narration_choice.get("asset_id") or ""))
            if asset["asset_type"] == AssetType.VOICE_SAMPLE_AUDIO.value: raise ValueError("draft_readiness_narration_voice_sample_invalid")
            required = AssetType.NARRATION_AUDIO.value if kind == "existing" else AssetType.RAW_VIDEO.value
            if asset["asset_type"] != required: raise ValueError("draft_readiness_narration_asset_invalid")
        fingerprint = hashlib.sha256(f"{brief_id}:{brief['revision']}:{brief['script_asset_id']}".encode()).hexdigest()
        # Asset reads use their own store connection; snapshot them before the
        # readiness write transaction so SQLite never nests writers.
        prepared_result = None if defer else self._draft_readiness_plan(project_id=project_id, brief=brief, narration=narration_choice)
        connection = self._connection(project_id); now = self._now_iso()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND idempotency_key = ?", (project_id, idempotency_key)).fetchone()
            if existing is not None:
                connection.commit(); return self._draft_readiness_payload(existing)
            readiness_id = f"readiness_{uuid.uuid4().hex[:12]}"
            result = prepared_result
            status = "asset_check" if defer else ("needs_assets" if result["gap_slots"] else "ready")
            connection.execute("INSERT INTO draft_readiness (readiness_id, project_id, brief_id, approved_brief_revision, input_fingerprint, narration_json, capability_json, idempotency_key, status, revision, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)", (readiness_id, project_id, brief_id, brief["revision"], fingerprint, json.dumps(narration_choice, ensure_ascii=False), json.dumps(capability or {}, ensure_ascii=False), idempotency_key, status, json.dumps(result, ensure_ascii=False) if result else None, now, now))
            row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            existing = self._fetchone(
                project_id,
                "SELECT * FROM draft_readiness WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            )
            if existing is None:
                raise
            return self._draft_readiness_payload(existing)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def get_draft_readiness(self, *, project_id: str, readiness_id: str) -> dict[str, Any]:
        row = self._fetchone(project_id, "SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id))
        if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
        payload = self._draft_readiness_payload(row)
        if payload["status"] not in {"ready", "needs_assets"} or not payload["result"]:
            return payload
        normalized_result = self._normalize_draft_readiness_result(project_id=project_id, payload=payload)
        normalized_status = "needs_assets" if normalized_result.get("gap_slots") else payload["status"]
        if normalized_result == payload["result"] and normalized_status == payload["status"]:
            return payload
        self._execute(project_id, "UPDATE draft_readiness SET result_json = ?, status = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(normalized_result, ensure_ascii=False), normalized_status, self._now_iso(), readiness_id, payload["revision"]))
        refreshed = self._fetchone(project_id, "SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id))
        if refreshed is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
        return self._draft_readiness_payload(refreshed)

    def list_draft_readiness(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            readiness_ids = [str(row["readiness_id"]) for row in connection.execute("SELECT readiness_id FROM draft_readiness WHERE project_id = ? ORDER BY created_at DESC", (project_id,)).fetchall()]
        finally:
            connection.close()
        return [self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id) for readiness_id in readiness_ids]

    def list_editing_sessions(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try: return [dict(row) for row in connection.execute("SELECT * FROM editing_sessions WHERE project_id = ?", (project_id,)).fetchall()]
        finally: connection.close()

    def materialize_atomic_draft_bundle(
        self, *, project_id: str, brief_id: str, expected_brief_revision: int,
        readiness_id: str, expected_readiness_revision: int, idempotency_key: str,
        allow_placeholder: bool = False,
    ) -> dict[str, Any]:
        """Create the first editable draft as one durable operation.

        This intentionally does not call ``save_timeline_run`` followed by
        ``save_editing_session``: either both rows (and their staged mirrors)
        become visible, or neither does.  A readiness snapshot is rechecked
        under the writer lock so a later script/media change cannot be applied.
        """
        if not idempotency_key.strip():
            raise ValueError("atomic_draft_bundle_idempotency_required")
        brief = self.get_creation_brief(project_id=project_id, brief_id=brief_id)
        readiness = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if brief["status"] != "approved": raise ValueError("atomic_draft_bundle_brief_not_approved")
        if int(brief["revision"]) != int(expected_brief_revision): raise ValueError("atomic_draft_bundle_brief_revision_conflict")
        if readiness["brief_id"] != brief_id: raise ValueError("atomic_draft_bundle_brief_mismatch")
        if int(readiness["revision"]) != int(expected_readiness_revision): raise ValueError("atomic_draft_bundle_readiness_revision_conflict")
        if readiness["status"] not in {"ready", "needs_assets"}: raise ValueError("atomic_draft_bundle_not_ready")
        result = readiness.get("result") or {}
        gaps = list(result.get("gap_slots") or [])
        if gaps and not allow_placeholder: raise ValueError("atomic_draft_bundle_gaps_require_placeholder_approval")
        fingerprint = hashlib.sha256(json.dumps({"brief": [brief_id, brief["revision"], brief.get("script_asset_id")], "readiness": [readiness_id, readiness["revision"], readiness.get("input_fingerprint")], "placeholder": allow_placeholder}, sort_keys=True).encode()).hexdigest()
        root = self.project_root(project_id); stage = root / "staging" / f"draft-bundle-{uuid.uuid4().hex}"
        stage.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {
            "kind": "atomic_draft_bundle",
            "status": "staging",
            "fingerprint": fingerprint,
            "artifacts": [],
        }
        self._write_atomic_bundle_manifest(stage, manifest)
        created: list[Path] = []
        try:
            def publish(staged: Path, target: Path, *, kind: str) -> None:
                """Record source SHA first, then atomically mirror one staged artifact."""
                digest = sha256_file(staged)
                manifest["artifacts"].append(
                    {
                        "kind": kind,
                        "staged_name": staged.name,
                        "target_uri": self._path_to_uri(project_id, target),
                        "sha256": digest,
                    }
                )
                self._write_atomic_bundle_manifest(stage, manifest)
                temporary = target.with_suffix(target.suffix + ".stage")
                shutil.copy2(staged, temporary)
                if sha256_file(temporary) != digest:
                    temporary.unlink(missing_ok=True)
                    raise OSError("atomic_draft_bundle_staged_copy_sha_mismatch")
                temporary.replace(target)
                created.append(target)
                self._atomic_bundle_fault(f"after_copy:{len(created)}")
            connection = self._connection(project_id)
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute("SELECT * FROM atomic_draft_bundles WHERE project_id=? AND idempotency_key=?", (project_id, idempotency_key)).fetchone()
                if existing is not None:
                    if str(existing["input_fingerprint"]) != fingerprint: raise ValueError("atomic_draft_bundle_idempotency_conflict")
                    connection.commit(); return json.loads(str(existing["result_json"]))
                current_brief = connection.execute("SELECT revision,status FROM creation_briefs WHERE brief_id=? AND project_id=?", (brief_id, project_id)).fetchone()
                current_readiness = connection.execute("SELECT revision,status,result_json FROM draft_readiness WHERE readiness_id=? AND project_id=?", (readiness_id, project_id)).fetchone()
                if current_brief is None or str(current_brief["status"]) != "approved" or int(current_brief["revision"]) != int(expected_brief_revision): raise ValueError("atomic_draft_bundle_brief_revision_conflict")
                if current_readiness is None or int(current_readiness["revision"]) != int(expected_readiness_revision): raise ValueError("atomic_draft_bundle_readiness_revision_conflict")
                current_result = json.loads(str(current_readiness["result_json"] or "{}")); current_gaps = list(current_result.get("gap_slots") or [])
                if current_gaps and not allow_placeholder: raise ValueError("atomic_draft_bundle_gaps_require_placeholder_approval")
                for snapshot in current_result.get("source_snapshot", []):
                    source = connection.execute("SELECT storage_uri,created_at FROM assets WHERE project_id=? AND asset_id=?", (project_id, str(snapshot.get("asset_id") or ""))).fetchone()
                    if source is None or str(source["created_at"]) != str(snapshot.get("media_revision") or ""):
                        raise ValueError("atomic_draft_bundle_source_revision_conflict")
                    path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(source["storage_uri"]))
                    if not path.is_file() or sha256_file(path) != str(snapshot.get("sha256") or ""):
                        raise ValueError("atomic_draft_bundle_source_sha_conflict")
                timeline_id = f"timeline_draft_{uuid.uuid4().hex[:12]}"; session_id = f"editing_session_draft_{uuid.uuid4().hex[:12]}"; bundle_id = f"draft_bundle_{uuid.uuid4().hex[:12]}"; timeline_job_id = f"timeline_build_job_draft_{uuid.uuid4().hex[:12]}"
                narration = dict(readiness.get("narration") or {}); narration_asset_id = narration.get("asset_id")
                asset_ids: list[str] = []; silence_stage: Path | None = None
                if narration.get("kind") == "silent":
                    import wave
                    narration_asset_id = f"asset_silence_{uuid.uuid4().hex[:12]}"; silence_stage = stage / "silence.wav"
                    with wave.open(str(silence_stage), "wb") as wav:
                        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b"\x00\x00" * 16000)
                    destination = root / "assets" / "narration_audio" / f"{narration_asset_id}.wav"; destination.parent.mkdir(parents=True, exist_ok=True)
                    publish(silence_stage, destination, kind="narration_silence")
                    uri = self._path_to_uri(project_id, destination)
                    connection.execute("INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (narration_asset_id, project_id, AssetType.NARRATION_AUDIO.value, uri, "deterministic_silence", "audio/wav", 1.0, json.dumps({"draft_bundle_id": bundle_id, "provenance": "local deterministic silence"}), self._now_iso()))
                    asset_ids.append(narration_asset_id)
                elif narration.get("kind") == "source_video" and narration_asset_id:
                    source = connection.execute("SELECT asset_type,storage_uri FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                    if source is None or str(source["asset_type"]) != AssetType.RAW_VIDEO.value:
                        raise ValueError("atomic_draft_bundle_narration_invalid")
                    # CapCut's narration track accepts audio only.  Keep the raw-video
                    # source snapshot immutable and derive a local, inspectable WAV
                    # inside this operation rather than silently asking an external
                    # provider to extract it.
                    normalized_stage = stage / "source-video-narration.wav"
                    source_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(source["storage_uri"]))
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-i", str(source_path), "-vn", "-ac", "1", "-ar", "16000", str(normalized_stage)],
                            check=True, capture_output=True, timeout=60,
                        )
                    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                        raise ValueError("atomic_draft_bundle_source_video_audio_normalization_failed") from exc
                    narration_asset_id = f"asset_source_video_narration_{uuid.uuid4().hex[:12]}"
                    destination = root / "assets" / "narration_audio" / f"{narration_asset_id}.wav"
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    publish(normalized_stage, destination, kind="source_video_narration")
                    uri = self._path_to_uri(project_id, destination)
                    connection.execute(
                        "INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (narration_asset_id, project_id, AssetType.NARRATION_AUDIO.value, uri, "source_video_audio_normalized", "audio/wav", None, json.dumps({"draft_bundle_id": bundle_id, "source_asset_id": narration.get("asset_id")}), self._now_iso()),
                    )
                    asset_ids.append(narration_asset_id)
                elif narration_asset_id:
                    source = connection.execute("SELECT asset_type FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                    if source is None or str(source["asset_type"]) == AssetType.VOICE_SAMPLE_AUDIO.value: raise ValueError("atomic_draft_bundle_narration_invalid")
                    asset_ids.append(str(narration_asset_id))
                else: raise ValueError("atomic_draft_bundle_narration_missing")
                narration_asset = connection.execute("SELECT storage_uri,created_at FROM assets WHERE project_id=? AND asset_id=?", (project_id, narration_asset_id)).fetchone()
                if narration_asset is None:
                    raise ValueError("atomic_draft_bundle_narration_missing")
                narration_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(narration_asset["storage_uri"]))
                narration_sha256 = sha256_file(narration_path)
                narration_provenance = {"sha256": narration_sha256, "media_revision": str(narration_asset["created_at"])}
                placeholder_assets: list[tuple[str, dict[str, Any], str, str]] = []
                if current_gaps:
                    for gap in current_gaps:
                        placeholder_asset_id = f"asset_gap_placeholder_{uuid.uuid4().hex[:12]}"
                        destination = root / "assets" / "broll_video" / f"{placeholder_asset_id}.svg"; destination.parent.mkdir(parents=True, exist_ok=True)
                        placeholder_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'><rect width='100%' height='100%' fill='#f7f7f7'/><text x='640' y='360' text-anchor='middle' fill='#555' font-size='36'>자산이 필요한 임시 장면</text></svg>"
                        staged_placeholder = stage / destination.name
                        staged_placeholder.write_text(placeholder_svg, encoding="utf-8")
                        publish(staged_placeholder, destination, kind="gap_placeholder")
                        uri = self._path_to_uri(project_id, destination)
                        placeholder_created_at = self._now_iso(); placeholder_sha256 = sha256_file(destination)
                        connection.execute("INSERT INTO assets (asset_id,project_id,asset_type,storage_uri,source_kind,mime_type,duration_sec,metadata_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (placeholder_asset_id, project_id, AssetType.BROLL_VIDEO.value, uri, "draft_gap_placeholder", "image/svg+xml", None, json.dumps({"draft_bundle_id": bundle_id, "gap_slot_id": gap.get("gap_slot_id"), "label": "자산이 필요한 임시 장면", "in_app_only": True}), placeholder_created_at))
                        asset_ids.append(placeholder_asset_id)
                        placeholder_assets.append((placeholder_asset_id, gap, placeholder_sha256, placeholder_created_at))
                provenance_by_asset = {str(item.get("asset_id")): item for item in current_result.get("source_snapshot", []) if isinstance(item, dict)}
                segments = list(current_result.get("script_segments") or []); clips: list[dict[str, Any]] = []
                for index, item in enumerate(segments):
                    segment_id = f"segment_draft_{uuid.uuid4().hex[:10]}"; clips.append({"clip_id": f"clip_caption_{uuid.uuid4().hex[:10]}", "segment_id": segment_id, "text": item.get("text", ""), "start_sec": item.get("start_sec", index * 5), "end_sec": item.get("end_sec", (index + 1) * 5)})
                    connection.execute("INSERT INTO segments (segment_id,project_id,start_sec,end_sec,text,source_asset_id,metadata_json) VALUES (?,?,?,?,?,?,?)", (segment_id, project_id, clips[-1]["start_sec"], clips[-1]["end_sec"], clips[-1]["text"], brief.get("script_asset_id"), json.dumps({"draft_bundle_id": bundle_id})))
                broll = [item for item in current_result.get("broll_candidates", []) if not item.get("skipped")]
                for item in broll:
                    asset_ids.append(str(item["asset_id"])); provenance = provenance_by_asset.get(str(item["asset_id"]), {})
                    clips.append({"clip_id": f"clip_broll_{uuid.uuid4().hex[:10]}", "clip_type": "broll", "asset_id": item["asset_id"], "segment_id": item.get("segment_id") or (clips[0]["segment_id"] if clips else "segment_broll"), "start_sec": item.get("target_range", {}).get("start_sec", 0), "end_sec": item.get("target_range", {}).get("end_sec", 5), "media_controls": {}, "expected_content_sha256": provenance.get("sha256"), "media_revision": provenance.get("media_revision")})
                for placeholder_asset_id, gap, placeholder_sha256, placeholder_created_at in placeholder_assets:
                    clips.append({"clip_id": f"clip_gap_placeholder_{uuid.uuid4().hex[:10]}", "clip_type": "broll", "asset_id": placeholder_asset_id, "segment_id": gap.get("segment_id") or gap.get("gap_slot_id"), "gap_slot_id": gap.get("gap_slot_id"), "label": "자산이 필요한 임시 장면", "start_sec": gap.get("target_range", {}).get("start_sec", 0), "end_sec": gap.get("target_range", {}).get("end_sec", 5), "media_controls": {}, "expected_content_sha256": placeholder_sha256, "media_revision": placeholder_created_at})
                asset_uris = {str(row["asset_id"]): str(row["storage_uri"]) for row in connection.execute("SELECT asset_id,storage_uri FROM assets WHERE project_id=?", (project_id,)).fetchall()}
                narration_clip = {"clip_id": f"clip_narration_{uuid.uuid4().hex[:10]}", "clip_type": "narration", "asset_id": narration_asset_id, "segment_id": clips[0]["segment_id"] if clips else "segment_narration", "asset_uri": asset_uris[str(narration_asset_id)], "start_sec": 0, "end_sec": max([c["end_sec"] for c in clips] or [1]), "media_controls": {}, "expected_content_sha256": narration_provenance.get("sha256"), "media_revision": narration_provenance.get("media_revision")}
                broll_clips = [{**c, "asset_uri": asset_uris.get(str(c.get("asset_id")), "")} for c in clips if "asset_id" in c and c.get("asset_id") != narration_asset_id]
                tracks = [{"track_id": f"track_narration_{uuid.uuid4().hex[:8]}", "track_type": "narration", "clips": [narration_clip]}, {"track_id": f"track_caption_{uuid.uuid4().hex[:8]}", "track_type": "caption", "clips": [c for c in clips if "text" in c]}, {"track_id": f"track_broll_{uuid.uuid4().hex[:8]}", "track_type": "broll", "clips": broll_clips}]
                review_flags = [{"code": "draft_gap_placeholder", "segment_id": gap.get("gap_slot_id"), "message": "자산이 필요한 임시 장면입니다."} for gap in current_gaps]
                timeline = {"timeline_id": timeline_id, "project_id": project_id, "version": "draft-v1", "source_session_id": session_id, "source_session_revision": 1, "tracks": tracks, "gap_slots": current_gaps, "review_flags": review_flags, "pending_recommendations": [], "applied_recommendations": [], "bgm_policy": current_result.get("bgm"), "sfx_policy": current_result.get("sfx"), "placeholder_policy": "in_app_only" if current_gaps else None}
                session_segments = [
                    {
                        "segment_id": clip["segment_id"],
                        "caption_text": str(clip.get("text") or ""),
                        "start_sec": float(clip["start_sec"]),
                        "end_sec": float(clip["end_sec"]),
                        "cut_action": "keep",
                        "review_required": bool(current_gaps),
                        "broll_override": None,
                        "visual_overlays": [],
                        "music_override": None,
                        "sfx_override": None,
                        "tts_replacement": None,
                    }
                    for clip in clips if "text" in clip
                ]
                session = {"session_id": session_id, "project_id": project_id, "timeline_id": timeline_id, "tracks": tracks, "segments": session_segments, "gap_slots": current_gaps, "draft_bundle_id": bundle_id, "session_revision": 1, "history": [], "undo_stack": [], "redo_stack": []}
                timeline_path = root / "timelines" / f"{timeline_id}.json"; session_path = root / "editing_sessions" / f"{session_id}.json"; timeline_path.parent.mkdir(parents=True, exist_ok=True); session_path.parent.mkdir(parents=True, exist_ok=True)
                for target, payload, kind in ((timeline_path, timeline, "timeline_mirror"), (session_path, session, "session_mirror")):
                    staged = stage / target.name
                    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    publish(staged, target, kind=kind)
                now = self._now_iso(); timeline_uri = self._path_to_uri(project_id, timeline_path); session_uri = self._path_to_uri(project_id, session_path)
                connection.execute("INSERT INTO timelines (timeline_id,project_id,version,output_mode,file_uri,summary_json,created_at) VALUES (?,?,?,?,?,?,?)", (timeline_id, project_id, "draft-v1", "review", timeline_uri, json.dumps({"track_count": len(tracks), "gap_count": len(current_gaps)}), now))
                connection.execute("INSERT INTO editing_sessions (session_id,project_id,timeline_id,file_uri,summary_json,session_revision,session_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (session_id, project_id, timeline_id, session_uri, json.dumps({"draft_bundle_id": bundle_id}), 1, json.dumps(session, ensure_ascii=False), now, now))
                connection.execute("INSERT INTO jobs (job_id,project_id,job_type,status,input_ref,output_ref,error_message,started_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?)", (timeline_job_id, project_id, JobType.TIMELINE_BUILD.value, JobStatus.SUCCEEDED.value, readiness_id, timeline_id, None, now, now))
                connection.execute("INSERT INTO review_approvals (timeline_id,project_id,status,approved_at,updated_at,source_session_revision,is_current) VALUES (?,?,?,?,?,?,?)", (timeline_id, project_id, "blocked" if current_gaps else "draft", None, now, 1, 1))
                response = {"bundle_id": bundle_id, "session_id": session_id, "timeline_id": timeline_id, "timeline_job_id": timeline_job_id, "segment_ids": [c["segment_id"] for c in clips if "segment_id" in c], "asset_ids": list(dict.fromkeys(asset_ids)), "clip_ids": [c["clip_id"] for c in clips], "gap_slots": current_gaps, "output_blocked": bool(current_gaps)}
                connection.execute("INSERT INTO atomic_draft_bundles (bundle_id,project_id,brief_id,readiness_id,input_fingerprint,idempotency_key,session_id,timeline_id,result_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (bundle_id, project_id, brief_id, readiness_id, fingerprint, idempotency_key, session_id, timeline_id, json.dumps(response, ensure_ascii=False), now))
                self._atomic_bundle_fault("before_db_commit")
                connection.commit()
                manifest["status"] = "committed"
                self._write_atomic_bundle_manifest(stage, manifest)
                return response
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.rollback()
                existing = connection.execute(
                    "SELECT * FROM atomic_draft_bundles WHERE project_id=? AND idempotency_key=?",
                    (project_id, idempotency_key),
                ).fetchone()
                for path in created:
                    path.unlink(missing_ok=True)
                if existing is None:
                    raise
                if str(existing["input_fingerprint"]) != fingerprint:
                    raise ValueError("atomic_draft_bundle_idempotency_conflict")
                return json.loads(str(existing["result_json"]))
            except Exception:
                if connection.in_transaction: connection.rollback()
                for path in created:
                    path.unlink(missing_ok=True)
                raise
            finally: connection.close()
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def cancel_draft_readiness(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE"); row = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id)).fetchone()
            if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
            if int(row["revision"]) != expected_revision: raise ValueError("draft_readiness_revision_conflict")
            if row["status"] in {"ready", "needs_assets", "cancelled"}: raise ValueError("draft_readiness_not_cancellable")
            connection.execute("UPDATE draft_readiness SET status = 'cancelled', cancel_requested = 1, revision = revision + 1, updated_at = ? WHERE readiness_id = ?", (self._now_iso(), readiness_id)); row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def begin_draft_readiness_planning(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE"); row = connection.execute("SELECT * FROM draft_readiness WHERE project_id = ? AND readiness_id = ?", (project_id, readiness_id)).fetchone()
            if row is None: raise KeyError(f"Draft readiness not found: {readiness_id}")
            if int(row["revision"]) != expected_revision: raise ValueError("draft_readiness_revision_conflict")
            if row["status"] not in {"asset_check", "cancelled", "failed", "needs_assets"}: raise ValueError("draft_readiness_not_plannable")
            connection.execute("UPDATE draft_readiness SET status = 'planning', cancel_requested = 0, error_code = NULL, revision = revision + 1, updated_at = ? WHERE readiness_id = ?", (self._now_iso(), readiness_id))
            row = connection.execute("SELECT * FROM draft_readiness WHERE readiness_id = ?", (readiness_id,)).fetchone(); connection.commit(); return self._draft_readiness_payload(row)
        except Exception:
            if connection.in_transaction: connection.rollback()
            raise
        finally: connection.close()

    def complete_draft_readiness(self, *, project_id: str, readiness_id: str, expected_revision: int) -> dict[str, Any]:
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["status"] == "cancelled": raise ValueError("draft_readiness_cancelled")
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if row["status"] != "planning": raise ValueError("draft_readiness_not_planning")
        try:
            brief = self.get_creation_brief(project_id=project_id, brief_id=row["brief_id"]); result = self._draft_readiness_plan(project_id=project_id, brief=brief, narration=row["narration"])
        except Exception:
            self._execute(project_id, "UPDATE draft_readiness SET status = 'failed', error_code = 'draft_readiness_planning_failed', revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (self._now_iso(), readiness_id, expected_revision))
            raise
        self._execute(project_id, "UPDATE draft_readiness SET status = ?, result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", ("needs_assets" if result["gap_slots"] else "ready", json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision))
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def update_draft_readiness_candidate(self, *, project_id: str, readiness_id: str, asset_id: str, skipped: bool, expected_revision: int) -> dict[str, Any]:
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if row["status"] not in {"ready", "needs_assets"} or not row["result"]: raise ValueError("draft_readiness_candidate_not_editable")
        result = row["result"]
        candidates = result.get("broll_candidates", [])
        candidate = next((item for item in candidates if item.get("asset_id") == asset_id), None)
        if candidate is None: raise KeyError(f"Draft readiness candidate not found: {asset_id}")
        candidate["skipped"] = bool(skipped)
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE draft_readiness SET result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision))
            connection.commit()
            if cursor.rowcount != 1: raise ValueError("draft_readiness_revision_conflict")
        finally:
            connection.close()
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def update_draft_readiness_candidate_range(self, *, project_id: str, readiness_id: str, asset_id: str, start_sec: float, end_sec: float, expected_revision: int) -> dict[str, Any]:
        if not math.isfinite(start_sec) or not math.isfinite(end_sec) or start_sec < 0 or end_sec <= start_sec: raise ValueError("draft_readiness_candidate_range_invalid")
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        raw_duration = asset.get("duration_sec")
        if raw_duration is not None:
            duration_sec = float(raw_duration)
            if not math.isfinite(duration_sec) or duration_sec <= 0 or end_sec > duration_sec:
                raise ValueError("draft_readiness_candidate_range_invalid")
        row = self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)
        if row["revision"] != expected_revision: raise ValueError("draft_readiness_revision_conflict")
        if not row["result"]: raise ValueError("draft_readiness_candidate_not_editable")
        candidate = next((item for item in row["result"].get("broll_candidates", []) if item.get("asset_id") == asset_id), None)
        if candidate is None: raise KeyError(f"Draft readiness candidate not found: {asset_id}")
        candidate["target_range"] = {"start_sec": start_sec, "end_sec": end_sec}
        result = row["result"]
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE draft_readiness SET result_json = ?, revision = revision + 1, updated_at = ? WHERE readiness_id = ? AND revision = ?", (json.dumps(result, ensure_ascii=False), self._now_iso(), readiness_id, expected_revision)); connection.commit()
            if cursor.rowcount != 1: raise ValueError("draft_readiness_revision_conflict")
        finally: connection.close()
        return self.get_draft_readiness(project_id=project_id, readiness_id=readiness_id)

    def register_asset(
        self,
        *,
        project_id: str,
        asset_type: AssetType,
        source_path: Path,
        source_kind: str = "local_file",
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRecord:
        resolved_source = Path(source_path)
        if not resolved_source.exists():
            raise FileNotFoundError(f"Source asset does not exist: {resolved_source}")

        destination_dir = self.project_root(project_id) / self._asset_directory(asset_type)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / resolved_source.name
        if destination_path.exists():
            destination_path = destination_dir / f"{uuid.uuid4().hex}-{resolved_source.name}"
        shutil.copy2(resolved_source, destination_path)
        storage_uri = self._path_to_uri(project_id, destination_path)
        asset = AssetRecord.create(
            project_id=project_id,
            asset_type=asset_type,
            storage_uri=storage_uri,
        )
        self._execute_asset_index_mutation(
            project_id,
            """
            INSERT INTO assets (
                asset_id,
                project_id,
                asset_type,
                storage_uri,
                source_kind,
                mime_type,
                duration_sec,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.asset_id,
                asset.project_id,
                asset.asset_type.value,
                asset.storage_uri,
                source_kind,
                mime_type,
                None,
                json.dumps(metadata or {}, ensure_ascii=True),
                asset.created_at.isoformat(),
            ),
        )
        return asset

    def save_transcript(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        transcript_text: str,
        segments: list[dict[str, Any]],
        provider_name: str = "mock_stt",
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "transcripts",
            "transcript_*.json",
        )
        file_name = f"transcript_{sequence:03d}.json"
        transcript_path = self.project_root(project_id) / "analysis" / "transcripts" / file_name
        transcript_uri = self._path_to_uri(project_id, transcript_path)
        transcript = TranscriptRecord.create(
            project_id=project_id,
            source_asset_id=source_asset_id,
            transcript_uri=transcript_uri,
            transcript_text=transcript_text,
            provider_name=provider_name,
            transcript_id=f"transcript_{sequence:03d}",
        )
        payload = {
            "transcript_id": transcript.transcript_id,
            "project_id": transcript.project_id,
            "source_asset_id": transcript.source_asset_id,
            "transcript_uri": transcript.transcript_uri,
            "transcript_text": transcript.transcript_text,
            "provider_name": transcript.provider_name,
            "segments": segments,
            "created_at": transcript.created_at.isoformat(),
        }
        transcript_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        self._execute(
            project_id,
            """
            INSERT INTO transcripts (
                transcript_id,
                project_id,
                source_asset_id,
                transcript_uri,
                transcript_text,
                provider_name,
                segments_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transcript.transcript_id,
                transcript.project_id,
                transcript.source_asset_id,
                transcript.transcript_uri,
                transcript.transcript_text,
                transcript.provider_name,
                json.dumps(segments, ensure_ascii=True),
                transcript.created_at.isoformat(),
            ),
        )
        return payload

    def save_segment_analysis(
        self,
        *,
        project_id: str,
        transcript_id: str,
        script_asset_id: str | None,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "segments",
            "segment_analysis_*.json",
        )
        file_name = f"segment_analysis_{sequence:03d}.json"
        analysis_path = self.project_root(project_id) / "analysis" / "segments" / file_name
        analysis_id = f"segment_analysis_{sequence:03d}"
        payload = {
            "segment_analysis_id": analysis_id,
            "project_id": project_id,
            "transcript_id": transcript_id,
            "script_asset_id": script_asset_id,
            "file_uri": self._path_to_uri(project_id, analysis_path),
            "segments_uri": self._path_to_uri(project_id, analysis_path),
            "segments": segments,
        }
        analysis_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        self._execute(
            project_id,
            """
            INSERT INTO segment_analysis_runs (
                segment_analysis_id,
                project_id,
                transcript_id,
                script_asset_id,
                file_uri,
                segments_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                analysis_id,
                project_id,
                transcript_id,
                script_asset_id,
                payload["file_uri"],
                json.dumps(segments, ensure_ascii=True),
            ),
        )
        for index, segment in enumerate(segments, start=1):
            segment_metadata = {
                "transcript_id": transcript_id,
                "script_asset_id": script_asset_id,
            }
            if "provider_trace" in segment:
                segment_metadata["provider_trace"] = segment["provider_trace"]
            self._execute(
                project_id,
                """
                INSERT INTO segments (
                    segment_id,
                    project_id,
                    start_sec,
                    end_sec,
                    text,
                    source_asset_id,
                    confidence,
                    cleanup_decision,
                    review_required,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.get("segment_id", f"seg_{index:03d}_{analysis_id}"),
                    project_id,
                    segment.get("start_sec"),
                    segment.get("end_sec"),
                    segment.get("text"),
                    segment.get("source_asset_id"),
                    segment.get("confidence"),
                    segment.get("cleanup_decision"),
                    1 if _normalize_boolish(segment.get("review_required")) else 0,
                    json.dumps(segment_metadata, ensure_ascii=True),
                ),
            )
        return payload

    def save_recommendation_run(
        self,
        *,
        project_id: str,
        recommendation_type: RecommendationType,
        source_job_id: str,
        recommendations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "recommendations",
            f"{recommendation_type.value}_*.json",
        )
        run_id = f"{recommendation_type.value}_{sequence:03d}"
        recommendation_path = (
            self.project_root(project_id) / "analysis" / "recommendations" / f"{run_id}.json"
        )
        persisted_items: list[dict[str, Any]] = []
        for item in recommendations:
            record = RecommendationRecord.create(
                project_id=project_id,
                target_segment_id=item["target_segment_id"],
                recommendation_type=recommendation_type,
                selected_asset_id=item.get("selected_asset_id"),
                reason=item["reason"],
                score=float(item["score"]),
                payload=item.get("payload"),
            )
            persisted = {
                "recommendation_id": record.recommendation_id,
                "project_id": project_id,
                "target_segment_id": record.target_segment_id,
                "recommendation_type": recommendation_type.value,
                "selected_asset_id": record.selected_asset_id,
                "score": record.score,
                "reason": record.reason,
                "auto_apply_allowed": _normalize_boolish(
                    item.get("auto_apply_allowed", record.auto_apply_allowed)
                ),
                "review_required": _normalize_boolish(
                    item.get("review_required", record.review_required)
                ),
                "payload": item.get("payload", record.payload or {}),
                "created_at": record.created_at.isoformat(),
            }
            persisted["decision_state"] = self._derive_recommendation_decision_state(persisted)
            persisted_items.append(persisted)
            self._execute(
                project_id,
                """
                INSERT INTO recommendations (
                    recommendation_id,
                    project_id,
                    target_segment_id,
                    recommendation_type,
                    selected_asset_id,
                    score,
                    reason,
                    auto_apply_allowed,
                    review_required,
                    decision_state,
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.recommendation_id,
                    project_id,
                    record.target_segment_id,
                    recommendation_type.value,
                    record.selected_asset_id,
                    record.score,
                    record.reason,
                    1 if persisted["auto_apply_allowed"] else 0,
                    1 if persisted["review_required"] else 0,
                    persisted["decision_state"],
                    json.dumps(persisted["payload"], ensure_ascii=True),
                    record.created_at.isoformat(),
                ),
            )
        payload = {
            "recommendation_run_id": run_id,
            "project_id": project_id,
            "source_job_id": source_job_id,
            "recommendation_type": recommendation_type.value,
            "file_uri": self._path_to_uri(project_id, recommendation_path),
            "recommendations": persisted_items,
        }
        recommendation_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return payload

    def save_timeline_run(
        self,
        *,
        project_id: str,
        output_mode: str,
        timeline_payload: dict[str, Any],
        source_session_revision: int | None = None,
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "timelines",
            "timeline_*.json",
        )
        timeline_id = f"timeline_{sequence:03d}"
        timeline_path = self.project_root(project_id) / "timelines" / f"{timeline_id}.json"
        file_uri = self._path_to_uri(project_id, timeline_path)
        payload = {
            "timeline_id": timeline_id,
            "project_id": project_id,
            "version": str(timeline_payload.get("version", "v001")),
            "output_mode": output_mode,
            "file_uri": file_uri,
            "created_at": self._now_iso(),
            **timeline_payload,
        }
        if source_session_revision is not None:
            payload["source_session_revision"] = int(source_session_revision)
        timeline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        summary_json = _timeline_summary_json(payload)
        self._execute(
            project_id,
            """
            INSERT INTO timelines (
                timeline_id,
                project_id,
                version,
                output_mode,
                file_uri,
                summary_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timeline_id,
                project_id,
                payload["version"],
                output_mode,
                file_uri,
                summary_json,
                payload["created_at"],
            ),
        )
        recommendation_blocker_sources: list[dict[str, Any]] = []
        for collection_key in ("pending_recommendations", "applied_recommendations"):
            collection = payload.get(collection_key)
            if isinstance(collection, list):
                recommendation_blocker_sources.extend(
                    item for item in collection if isinstance(item, dict)
                )
        has_pending_like_recommendation = any(
            _is_store_blocking_pending_recommendation(item)
            for item in recommendation_blocker_sources
        )
        review_flags = payload.get("review_flags")
        has_blocking_review_flag = isinstance(review_flags, list) and any(
            _is_store_blocking_review_flag(flag) for flag in review_flags
        )
        initial_review_status = (
            "blocked"
            if has_blocking_review_flag or has_pending_like_recommendation
            else "draft"
        )
        self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status=initial_review_status,
            source_session_revision=source_session_revision,
        )
        return {"timeline_id": timeline_id, "file_uri": file_uri, "timeline": payload}

    def save_editing_session(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "editing_sessions",
            "editing_session_*.json",
        )
        session_id = f"editing_session_{sequence:03d}"
        saved = self._write_editing_session(
            project_id=project_id,
            timeline_id=timeline_id,
            session_id=session_id,
            session_payload=session_payload,
            is_new=True,
        )
        try:
            self.bind_timeline_to_editing_session_revision(
                project_id=project_id,
                timeline_id=timeline_id,
                session_id=session_id,
                session_revision=int(saved["session_revision"]),
            )
        except KeyError:
            # A pre-timeline draft session cannot authorize any output until bound.
            pass
        return saved

    def bind_timeline_to_editing_session_revision(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_id: str,
        session_revision: int,
    ) -> dict[str, Any]:
        """Persist the editing-session revision consumed by a timeline and review."""
        timeline = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        timeline["source_session_id"] = str(session_id)
        timeline["source_session_revision"] = int(session_revision)
        updated = self.update_timeline_run(
            project_id=project_id,
            timeline_id=timeline_id,
            timeline_payload=timeline,
        )
        review = self.get_review_state(project_id=project_id, timeline_id=timeline_id)
        self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status=str(review["status"]),
            source_session_revision=int(session_revision),
        )
        return updated

    def update_editing_session(
        self,
        *,
        project_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        timeline_id: str | None = None,
        expected_revision: int | None = None,
        invalidate_output_freshness: bool = True,
    ) -> dict[str, Any]:
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        current_revision = int(existing.get("session_revision") or 1)
        expected_revision = current_revision if expected_revision is None else expected_revision
        session_payload = deepcopy(session_payload)
        if int(session_payload.get("session_revision") or 0) <= current_revision:
            session_payload["session_revision"] = current_revision + 1
        created_at = str(existing.get("created_at") or self._now_iso())
        return self._write_editing_session(
            project_id=project_id,
            timeline_id=timeline_id or str(existing["timeline_id"]),
            session_id=session_id,
            session_payload=session_payload,
            is_new=False,
            created_at=created_at,
            expected_revision=expected_revision,
            invalidate_output_freshness=invalidate_output_freshness,
        )

    def restore_editing_session_after_failed_publication(
        self,
        *,
        project_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        """CAS-restore the exact pre-publication session without staling its outputs.

        A partial regeneration briefly advances the session to bind its candidate
        timeline.  If publishing the result/job fails, that candidate never became
        observable, so the original revision and its artifacts remain authoritative.
        """
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        return self._write_editing_session(
            project_id=project_id,
            timeline_id=str(payload["timeline_id"]),
            session_id=session_id,
            session_payload=payload,
            is_new=False,
            created_at=str(existing["created_at"]),
            expected_revision=expected_revision,
            invalidate_output_freshness=False,
        )

    def apply_director_proposal_transaction(
        self, *, project_id: str, session_id: str, proposal_id: str,
        session_payload: dict[str, Any], expected_revision: int,
        proposal_base_revision: int, materialized_expectations: list[tuple[str, str, int]],
    ) -> dict[str, Any]:
        """Commit the session CAS and proposal consumption in the same SQLite transaction."""
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1

        def consume(connection: sqlite3.Connection) -> None:
            proposal_row = connection.execute("SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if proposal_row is None or str(proposal_row["status"]) != "ready":
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            if int(json.loads(str(proposal_row["proposal_json"])).get("base_session_revision") or 0) != proposal_base_revision:
                raise EditingSessionRevisionConflict("Director proposal base revision changed.")
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            current_index_revision = int(revision_row["revision"]) if revision_row is not None else 0
            for asset_id, expected_sha256, expected_index_revision in materialized_expectations:
                row = connection.execute("SELECT storage_uri, metadata_json FROM assets WHERE project_id = ? AND asset_id = ?", (project_id, asset_id)).fetchone()
                if row is None or current_index_revision != expected_index_revision:
                    raise EditingSessionRevisionConflict("Materialized asset index changed during proposal apply.")
                metadata = json.loads(str(row["metadata_json"] or "{}"))
                if int(metadata.get("director_materialized_asset_index_revision") or -1) != expected_index_revision:
                    raise EditingSessionRevisionConflict("Materialized asset revision changed during proposal apply.")
                path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["storage_uri"]))
                if not path.is_file() or sha256_file(path) != expected_sha256:
                    raise EditingSessionRevisionConflict("Materialized bytes changed during proposal apply.")
            now = self._now_iso()
            changed = connection.execute(
                "UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status = 'ready'",
                ("applied", now, proposal_id),
            )
            if changed.rowcount != 1:
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            connection.execute(
                "INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)",
                (proposal_id, "applied", "session_apply", now),
            )

        return self._write_editing_session(
            project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id,
            session_payload=payload, is_new=False, created_at=str(existing["created_at"]),
            expected_revision=expected_revision, transaction_hook=consume,
        )

    def batch_apply_director_proposal_transaction(
        self, *, project_id: str, session_id: str, proposal_id: str,
        session_payload: dict[str, Any], expected_revision: int, proposal_base_revision: int,
        expected_asset_index_revision: int, staged_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Register already-verified staged bytes and consume a proposal in one CAS write.

        Filesystem moves cannot participate in SQLite rollback, so every copied
        destination is tracked and removed on any failed database/session write.
        The caller owns removal of the disposable stage files in all cases.
        """
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1
        copied_paths: list[Path] = []

        def consume(connection: sqlite3.Connection) -> None:
            proposal_row = connection.execute("SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if proposal_row is None or str(proposal_row["status"]) != "ready":
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            if int(json.loads(str(proposal_row["proposal_json"])).get("base_session_revision") or 0) != proposal_base_revision:
                raise EditingSessionRevisionConflict("Director proposal base revision changed.")
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            current_revision = int(revision_row["revision"]) if revision_row is not None else 0
            if current_revision != expected_asset_index_revision:
                raise EditingSessionRevisionConflict("Director asset index changed before batch apply.")
            for item in staged_assets:
                staged = Path(str(item["staged_path"]))
                destination = Path(str(item["destination_path"]))
                digest = str(item["sha256"])
                if not staged.is_file() or sha256_file(staged) != digest:
                    raise ValueError("candidate_staging_sha_mismatch")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValueError("batch_destination_exists")
                shutil.copy2(staged, destination)
                copied_paths.append(destination)
                if sha256_file(destination) != digest:
                    raise ValueError("candidate_project_sha_mismatch")
            materialized_revision = current_revision + 1
            for item in staged_assets:
                record: AssetRecord = item["asset_record"]
                metadata = dict(item["metadata"])
                metadata["director_materialized_asset_index_revision"] = materialized_revision
                connection.execute(
                    """INSERT INTO assets (asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (record.asset_id, record.project_id, record.asset_type.value, record.storage_uri,
                     "director_materialized", None, None, json.dumps(metadata, ensure_ascii=True), record.created_at.isoformat()),
                )
            if staged_assets:
                actual_revision = self._increment_asset_index_revision_with_connection(connection, project_id)
                if actual_revision != materialized_revision:
                    raise EditingSessionRevisionConflict("Director asset index changed during batch apply.")
            now = self._now_iso()
            changed = connection.execute("UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status = 'ready'", ("applied", now, proposal_id))
            if changed.rowcount != 1:
                raise EditingSessionRevisionConflict("Director proposal is no longer ready.")
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal_id, "applied", "batch_session_apply", now))

        try:
            result = self._write_editing_session(
                project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id,
                session_payload=payload, is_new=False, created_at=str(existing["created_at"]),
                expected_revision=expected_revision, transaction_hook=consume,
            )
            for manifest_path in {Path(str(item.get("manifest_path"))) for item in staged_assets if item.get("manifest_path")}:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if isinstance(manifest, dict):
                        manifest["status"] = "committed"
                        temporary = manifest_path.with_suffix(".tmp")
                        temporary.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
                        temporary.replace(manifest_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    # Database commit is authoritative; the next startup can
                    # still prove and reconcile a stale manifest.
                    pass
            return result
        except EditingSessionPostCommitFileWriteError:
            # The DB transaction owns these assets now.  The read path repairs
            # its JSON mirror from SQLite, so preserving the bytes is safer
            # than trying to undo a committed transaction.
            raise
        except Exception:
            for path in copied_paths:
                if path.exists():
                    path.unlink()
            raise

    def save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
        source_session_revision: int | None = None,
    ) -> dict[str, Any]:
        if status not in {"draft", "blocked", "approved"}:
            raise ValueError(f"Unsupported review status: {status}")
        approved_at = self._now_iso() if status == "approved" else None
        updated_at = self._now_iso()
        self._execute(
            project_id,
            """
            INSERT INTO review_approvals (
                timeline_id,
                project_id,
                status,
                approved_at,
                updated_at,
                source_session_revision
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(timeline_id) DO UPDATE SET
                status = excluded.status,
                approved_at = excluded.approved_at,
                updated_at = excluded.updated_at,
                source_session_revision = COALESCE(excluded.source_session_revision, (SELECT session_revision FROM editing_sessions WHERE project_id = excluded.project_id AND timeline_id = excluded.timeline_id ORDER BY updated_at DESC LIMIT 1)),
                is_current = 1,
                invalidated_at = NULL,
                invalidated_reason = NULL
            """,
            (timeline_id, project_id, status, approved_at, updated_at, source_session_revision),
        )
        self.clear_operator_guidance(project_id=project_id, timeline_id=timeline_id)
        return self.get_review_state(project_id=project_id, timeline_id=timeline_id)

    def update_recommendation_review(
        self,
        *,
        project_id: str,
        recommendation_id: str,
        auto_apply_allowed: bool,
        review_required: bool,
        decision_state: str | None = None,
    ) -> None:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute(
                """
                UPDATE recommendations
                SET auto_apply_allowed = ?, review_required = ?, decision_state = COALESCE(?, decision_state)
                WHERE recommendation_id = ? AND project_id = ?
                """,
                (
                    1 if auto_apply_allowed else 0,
                    1 if review_required else 0,
                    decision_state,
                    recommendation_id,
                    project_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        if cursor.rowcount == 0:
            raise KeyError(f"Recommendation not found: {recommendation_id}")

    def update_timeline_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        timeline_payload: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        payload = deepcopy(timeline_payload)
        payload.pop("summary", None)
        payload["timeline_id"] = timeline_id
        payload["project_id"] = project_id
        payload["version"] = str(payload.get("version", existing.get("version", "v001")))
        payload["output_mode"] = str(payload.get("output_mode", existing.get("output_mode", "review")))
        payload["file_uri"] = str(existing.get("file_uri"))
        payload["created_at"] = str(existing.get("created_at"))

        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

        summary_json = _timeline_summary_json(payload)
        self._execute(
            project_id,
            """
            UPDATE timelines
            SET version = ?, output_mode = ?, summary_json = ?
            WHERE timeline_id = ? AND project_id = ?
            """,
            (
                payload["version"],
                payload["output_mode"],
                summary_json,
                timeline_id,
                project_id,
            ),
        )
        return self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)

    def discard_partial_regeneration_timeline(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> None:
        """Remove a timeline published before its owning session CAS lost.

        Partial regeneration constructs a new timeline before it can atomically
        advance the editing session.  A losing CAS must therefore make that
        timeline and its initial review ineligible before reporting conflict.
        """
        connection = self._connection(project_id)
        timeline_path: Path | None = None
        try:
            row = connection.execute(
                "SELECT file_uri FROM timelines WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            ).fetchone()
            if row is None:
                return
            timeline_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE review_approvals SET is_current = 0, invalidated_at = ?, invalidated_reason = ? WHERE project_id = ? AND timeline_id = ?",
                (self._now_iso(), "partial_regeneration_cas_conflict", project_id, timeline_id),
            )
            connection.execute(
                "DELETE FROM review_approvals WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            )
            connection.execute(
                "DELETE FROM timelines WHERE project_id = ? AND timeline_id = ?",
                (project_id, timeline_id),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        if timeline_path is not None:
            timeline_path.unlink(missing_ok=True)

    def mark_partial_regeneration_cleanup_needed(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> None:
        """Make a failed-to-delete candidate ineligible while reconciliation retries."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE review_approvals SET is_current = 0, invalidated_at = ?, invalidated_reason = ? "
                "WHERE project_id = ? AND timeline_id = ?",
                (
                    self._now_iso(),
                    "partial_regeneration_cleanup_failed",
                    project_id,
                    timeline_id,
                ),
            )
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def save_partial_regeneration_run(
        self,
        *,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "analysis" / "partial_regenerations",
            "partial_regeneration_*.json",
        )
        partial_regeneration_id = f"partial_regeneration_{sequence:03d}"
        created_at = self._now_iso()
        run_payload = {
            "partial_regeneration_id": partial_regeneration_id,
            "created_at": created_at,
            **payload,
        }
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(run_payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return run_payload

    def get_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
    ) -> dict[str, Any]:
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        if not file_path.exists():
            raise KeyError(f"Partial regeneration run not found: {partial_regeneration_id}")
        return json.loads(file_path.read_text(encoding="utf-8"))

    def discard_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
    ) -> None:
        """Remove a run that was written before its owning job was published."""
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.unlink(missing_ok=True)

    def update_partial_regeneration_run(
        self,
        *,
        project_id: str,
        partial_regeneration_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        existing = self.get_partial_regeneration_run(
            project_id=project_id,
            partial_regeneration_id=partial_regeneration_id,
        )

        updated = {
            **existing,
            **deepcopy(payload),
            "partial_regeneration_id": partial_regeneration_id,
            "created_at": str(existing["created_at"]),
        }
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "partial_regenerations"
            / f"{partial_regeneration_id}.json"
        )
        file_path.write_text(json.dumps(updated, indent=2, ensure_ascii=True), encoding="utf-8")
        return updated

    def create_director_conversation(self, *, project_id: str, session_id: str, conversation_id: str) -> dict[str, Any]:
        self.get_editing_session(project_id=project_id, session_id=session_id)
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute(
                "INSERT INTO director_conversations (conversation_id, project_id, session_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, project_id, session_id, now, now),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            row = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if row is None or str(row["project_id"]) != project_id or str(row["session_id"]) != session_id:
                raise ValueError("conversation_id_conflict") from None
        finally:
            connection.close()
        return {"conversation_id": conversation_id, "project_id": project_id, "session_id": session_id}

    def get_director_conversation(self, *, project_id: str, conversation_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT conversation_id, project_id, session_id FROM director_conversations WHERE conversation_id = ? AND project_id = ?",
            (conversation_id, project_id),
        )
        if row is None:
            raise KeyError("director_conversation_missing")
        return dict(row)

    def latest_director_conversation(self, *, project_id: str, session_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            "SELECT conversation_id, project_id, session_id FROM director_conversations WHERE project_id = ? AND session_id = ? ORDER BY updated_at DESC, conversation_id DESC LIMIT 1",
            (project_id, session_id),
        )
        return dict(row) if row is not None else None

    def append_director_message(
        self, *, project_id: str, session_id: str, conversation_id: str, role: str,
        text: str, proposal_id: str | None = None, client_message_id: str | None = None,
    ) -> dict[str, Any]:
        if role not in {"user", "assistant"} or not text.strip():
            raise ValueError("director message requires a supported role and text")
        now = self._now_iso()
        message_id = uuid.uuid4().hex
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT session_id FROM editing_sessions WHERE session_id = ? AND project_id = ?", (session_id, project_id)).fetchone()
            if session is None:
                raise KeyError("editing_session_missing")
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            connection.execute(
                "INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)",
                (message_id, conversation_id, project_id, session_id, role, text, proposal_id, client_message_id, now),
            )
            connection.execute("UPDATE director_conversations SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id))
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return {"message_id": message_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": role, "text": text, "proposal_id": proposal_id, "client_message_id": client_message_id, "created_at": now}

    def list_director_messages(self, *, project_id: str, conversation_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(project_id, "SELECT message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, created_at FROM director_messages WHERE conversation_id = ? AND project_id = ? ORDER BY created_at, rowid", (conversation_id, project_id))
        return [self._director_message_payload(row) for row in rows]

    def get_director_exchange_by_client_message_id(self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str, user_text: str) -> dict[str, Any] | None:
        conversation = self._fetchone(project_id, "SELECT session_id FROM director_conversations WHERE conversation_id = ? AND project_id = ?", (conversation_id, project_id))
        if conversation is None:
            raise KeyError("director_conversation_missing")
        if str(conversation["session_id"]) != session_id:
            raise ValueError("conversation_scope_mismatch")
        rows = self.list_director_messages(project_id=project_id, conversation_id=conversation_id)
        for index, item in enumerate(rows):
            if item.get("client_message_id") != client_message_id:
                continue
            if item.get("text") != user_text:
                raise ValueError("client_message_id_reused_with_different_content")
            if index + 1 >= len(rows) or rows[index + 1].get("role") != "assistant":
                raise ValueError("incomplete persisted director exchange")
            return {"user_message": item, "assistant_message": rows[index + 1]}
        return None

    def claim_director_message(self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str, user_text: str) -> str | None:
        """Exactly one caller owns local generation for a client message ID."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            now, token = self._now_iso(), uuid.uuid4().hex
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            row = connection.execute("SELECT project_id, session_id, user_text, heartbeat_at FROM director_message_claims WHERE conversation_id = ? AND client_message_id = ?", (conversation_id, client_message_id)).fetchone()
            if row is not None:
                if str(row["project_id"]) != project_id or str(row["session_id"]) != session_id:
                    raise ValueError("conversation_scope_mismatch")
                if str(row["user_text"]) != user_text:
                    raise ValueError("client_message_id_reused_with_different_content")
                claimed_at = datetime.fromisoformat(str(row["heartbeat_at"]))
                # Local runtime generation has a bounded 30s request timeout;
                # keep the lease materially above it so a live slow request is
                # never reclaimed merely for crossing that timeout boundary.
                if claimed_at.astimezone(UTC) <= self._clock().astimezone(UTC) - timedelta(seconds=300):
                    connection.execute(
                        "UPDATE director_message_claims SET owner_token = ?, heartbeat_at = ? WHERE conversation_id = ? AND client_message_id = ?",
                        (token, now, conversation_id, client_message_id),
                    )
                    connection.commit()
                    return token
                connection.commit()
                return False
            connection.execute("INSERT INTO director_message_claims (conversation_id, client_message_id, project_id, session_id, user_text, created_at, owner_token, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (conversation_id, client_message_id, project_id, session_id, user_text, now, token, now))
            connection.commit()
            return token
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat_director_message_claim(self, *, project_id: str, conversation_id: str, client_message_id: str, owner_token: str) -> bool:
        connection = self._connection(project_id)
        try:
            cursor = connection.execute("UPDATE director_message_claims SET heartbeat_at = ? WHERE conversation_id = ? AND client_message_id = ? AND owner_token = ?", (self._now_iso(), conversation_id, client_message_id, owner_token))
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def append_director_exchange(
        self, *, project_id: str, session_id: str, conversation_id: str, client_message_id: str,
        user_text: str, assistant_text: str, proposal_id: str | None = None, assistant_metadata: dict[str, Any] | None = None, owner_token: str | None = None,
    ) -> dict[str, Any]:
        """Persist the request and response atomically; retry returns the original DTO."""
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute("SELECT session_id FROM editing_sessions WHERE session_id = ? AND project_id = ?", (session_id, project_id)).fetchone()
            if session is None:
                raise KeyError("editing_session_missing")
            if owner_token is not None:
                claim = connection.execute("SELECT owner_token FROM director_message_claims WHERE conversation_id = ? AND client_message_id = ?", (conversation_id, client_message_id)).fetchone()
                if claim is None or str(claim["owner_token"]) != owner_token:
                    raise ValueError("director_message_claim_lost")
            conversation = connection.execute("SELECT project_id, session_id FROM director_conversations WHERE conversation_id = ?", (conversation_id,)).fetchone()
            if conversation is None:
                raise KeyError("director_conversation_missing")
            if str(conversation["project_id"]) != project_id or str(conversation["session_id"]) != session_id:
                raise ValueError("conversation_scope_mismatch")
            existing = connection.execute("SELECT message_id FROM director_messages WHERE conversation_id = ? AND client_message_id = ?", (conversation_id, client_message_id)).fetchone()
            if existing is not None:
                rows = connection.execute("SELECT message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, created_at FROM director_messages WHERE conversation_id = ? ORDER BY created_at, rowid", (conversation_id,)).fetchall()
                user_index = next(index for index, row in enumerate(rows) if str(row["message_id"]) == str(existing["message_id"]))
                if str(rows[user_index]["text"]) != user_text:
                    raise ValueError("client_message_id_reused_with_different_content")
                if user_index + 1 >= len(rows) or str(rows[user_index + 1]["role"]) != "assistant":
                    raise ValueError("incomplete persisted director exchange")
                connection.commit()
                return {"user_message": self._director_message_payload(rows[user_index]), "assistant_message": self._director_message_payload(rows[user_index + 1])}
            user_id, assistant_id = uuid.uuid4().hex, uuid.uuid4().hex
            connection.execute("INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, created_at) VALUES (?, ?, ?, ?, 'user', ?, NULL, '{}', ?, ?)", (user_id, conversation_id, project_id, session_id, user_text, client_message_id, now))
            connection.execute("INSERT INTO director_messages (message_id, conversation_id, project_id, session_id, role, text, proposal_id, metadata_json, client_message_id, created_at) VALUES (?, ?, ?, ?, 'assistant', ?, ?, ?, NULL, ?)", (assistant_id, conversation_id, project_id, session_id, assistant_text, proposal_id, json.dumps(assistant_metadata or {}, ensure_ascii=True, sort_keys=True), now))
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return {"user_message": {"message_id": user_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": "user", "text": user_text, "proposal_id": None, "metadata": {}, "client_message_id": client_message_id, "created_at": now}, "assistant_message": {"message_id": assistant_id, "conversation_id": conversation_id, "project_id": project_id, "session_id": session_id, "role": "assistant", "text": assistant_text, "proposal_id": proposal_id, "metadata": assistant_metadata or {}, "client_message_id": None, "created_at": now}}

    def _director_message_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["metadata"] = self._json_object(str(payload.pop("metadata_json", "{}")))
        return payload

    def save_director_proposal(self, project_id: str, proposal: DirectorProposal) -> DirectorProposal:
        payload = proposal_to_payload(proposal)
        canonical_payload = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        now = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
            INSERT INTO director_proposals (proposal_id, project_id, status, source_session_id, source_script_segment_ids_json, proposal_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (proposal.proposal_id, project_id, proposal.status, proposal.source_session_id, json.dumps(list(proposal.source_script_segment_ids)), canonical_payload, now, now))
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal.proposal_id, proposal.status, "created", now))
            connection.commit()
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            existing = self._fetchone(project_id, "SELECT proposal_json FROM director_proposals WHERE proposal_id = ?", (proposal.proposal_id,))
            if existing is not None:
                stored = json.dumps(json.loads(str(existing["proposal_json"])), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                if stored == canonical_payload:
                    return proposal
            raise ValueError(f"Director proposal is immutable and cannot be overwritten: {proposal.proposal_id}") from None
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return proposal

    def get_director_proposal(self, project_id: str, proposal_id: str, now: datetime | None = None) -> DirectorProposal:
        row = self._fetchone(project_id, "SELECT proposal_json, status FROM director_proposals WHERE proposal_id = ?", (proposal_id,))
        if row is None:
            raise KeyError(f"Director proposal not found: {proposal_id}")
        proposal = proposal_from_payload(json.loads(str(row["proposal_json"])))
        current_status = str(row["status"])
        instant = now or self._clock()
        if current_status == "ready" and proposal.expires_at and datetime.fromisoformat(proposal.expires_at).astimezone(UTC) <= instant.astimezone(UTC):
            changed_at = self._now_iso()
            connection = self._connection(project_id)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ?", ("expired", changed_at, proposal_id))
                connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (proposal_id, "expired", "expiry", changed_at))
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()
            current_status = "expired"
        if proposal.status != current_status:
            from dataclasses import replace
            proposal = replace(proposal, status=current_status)
        return proposal

    def list_director_proposals(self, project_id: str) -> list[DirectorProposal]:
        rows = self._fetchall(project_id, "SELECT proposal_id FROM director_proposals ORDER BY created_at, proposal_id", ())
        return [self.get_director_proposal(project_id, str(row["proposal_id"])) for row in rows]

    def get_director_proposal_lifecycle(self, project_id: str, proposal_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(project_id, "SELECT status, reason, changed_at FROM director_proposal_lifecycle_events WHERE proposal_id = ? ORDER BY event_id", (proposal_id,))
        return [dict(row) for row in rows]

    def save_director_preferences(self, project_id: str, preferences: dict[str, Any]) -> dict[str, list[str]]:
        allowed = ("pin_asset", "exclude_asset", "exclude_creator", "exclude_tag")
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,)).fetchone()
            current = json.loads(str(row["preferences_json"])) if row else {key: [] for key in allowed}
            canonical = {
                key: sorted({str(value).strip() for value in preferences[key] if str(value).strip()})
                if key in preferences else list(current.get(key, []))
                for key in allowed
            }
            connection.execute("INSERT INTO director_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at", (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()))
            connection.commit()
            return canonical
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def get_director_preferences(self, project_id: str) -> dict[str, list[str]]:
        row = self._fetchone(project_id, "SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,))
        return json.loads(str(row["preferences_json"])) if row else {"pin_asset": [], "exclude_asset": [], "exclude_creator": [], "exclude_tag": []}

    def get_project_media_library_preferences(self, project_id: str) -> dict[str, list[str]]:
        row = self._fetchone(
            project_id,
            "SELECT preferences_json FROM project_media_library_preferences WHERE project_id = ?",
            (project_id,),
        )
        return json.loads(str(row["preferences_json"])) if row else {"favorite_asset_ids": [], "recent_asset_ids": []}

    def set_project_media_library_favorite(
        self, *, project_id: str, library_asset_id: str, enabled: bool,
    ) -> dict[str, list[str]]:
        return self._mutate_project_media_library_preferences(
            project_id=project_id,
            mutate=lambda preferences: {
                **preferences,
                "favorite_asset_ids": sorted(
                    ([item for item in preferences["favorite_asset_ids"] if item != library_asset_id] + ([library_asset_id] if enabled else []))
                ),
            },
        )

    def mark_project_media_library_recent(
        self, *, project_id: str, library_asset_id: str,
    ) -> dict[str, list[str]]:
        return self._mutate_project_media_library_preferences(
            project_id=project_id,
            mutate=lambda preferences: {
                **preferences,
                "recent_asset_ids": [library_asset_id, *[item for item in preferences["recent_asset_ids"] if item != library_asset_id]][:10],
            },
        )

    def _mutate_project_media_library_preferences(self, *, project_id: str, mutate: Callable[[dict[str, list[str]]], dict[str, list[str]]]) -> dict[str, list[str]]:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT preferences_json FROM project_media_library_preferences WHERE project_id = ?", (project_id,)).fetchone()
            current = json.loads(str(row["preferences_json"])) if row else {"favorite_asset_ids": [], "recent_asset_ids": []}
            preferences = mutate({key: list(current.get(key, [])) for key in ("favorite_asset_ids", "recent_asset_ids")})
            self._save_project_media_library_preferences_with_connection(connection, project_id, preferences)
            connection.commit()
            return preferences
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _save_project_media_library_preferences(self, project_id: str, preferences: dict[str, list[str]]) -> None:
        canonical = {
            key: [str(value).strip() for value in preferences.get(key, []) if str(value).strip()]
            for key in ("favorite_asset_ids", "recent_asset_ids")
        }
        self._execute(
            project_id,
            "INSERT INTO project_media_library_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at",
            (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()),
        )

    def _save_project_media_library_preferences_with_connection(self, connection: sqlite3.Connection, project_id: str, preferences: dict[str, list[str]]) -> None:
        canonical = {
            key: [str(value).strip() for value in preferences.get(key, []) if str(value).strip()]
            for key in ("favorite_asset_ids", "recent_asset_ids")
        }
        connection.execute(
            "INSERT INTO project_media_library_preferences (project_id, preferences_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET preferences_json=excluded.preferences_json, updated_at=excluded.updated_at",
            (project_id, json.dumps(canonical, ensure_ascii=True), self._now_iso()),
        )

    def get_asset_index_revision(self, project_id: str) -> int:
        row = self._fetchone(project_id, "SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,))
        return int(row["revision"]) if row else 0

    def read_director_proposal_snapshot(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        """Return every proposal input from one SQLite read snapshot.

        Proposal composition must never pair candidates from one library state
        with a revision from another state.
        """
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN")
            session_row = connection.execute(
                "SELECT session_json, summary_json, session_revision, created_at, updated_at FROM editing_sessions WHERE project_id = ? AND session_id = ?",
                (project_id, session_id),
            ).fetchone()
            if session_row is None:
                raise KeyError(f"Editing session not found: {session_id}")
            session = json.loads(str(session_row["session_json"] or "{}"))
            session["summary"] = json.loads(str(session_row["summary_json"] or "{}"))
            session["session_revision"] = int(session_row["session_revision"])
            session["created_at"], session["updated_at"] = session_row["created_at"], session_row["updated_at"]
            asset_rows = connection.execute("SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at FROM assets WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            analysis_rows = connection.execute("SELECT * FROM media_analysis_runs WHERE project_id = ? ORDER BY created_at ASC, analysis_id ASC", (project_id,)).fetchall()
            preference_row = connection.execute("SELECT preferences_json FROM director_preferences WHERE project_id = ?", (project_id,)).fetchone()
            revision_row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
            hook = getattr(self, "_director_proposal_snapshot_hook", None)
            if hook is not None:
                hook()
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        assets = [{**dict(row), "metadata": json.loads(str(row["metadata_json"] or "{}"))} for row in asset_rows]
        analyses = [self._media_analysis_payload(row) for row in analysis_rows]
        return {
            "session": session, "assets": assets, "analyses": analyses,
            "preferences": json.loads(str(preference_row["preferences_json"])) if preference_row else {"pin_asset": [], "exclude_asset": [], "exclude_creator": [], "exclude_tag": []},
            "asset_index_revision": int(revision_row["revision"]) if revision_row else 0,
        }

    def next_director_proposal_revision(self, project_id: str) -> int:
        """Allocate a durable, project-scoped monotonic proposal revision."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO director_proposal_revisions (project_id, revision) VALUES (?, 1) ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1",
                (project_id,),
            )
            row = connection.execute("SELECT revision FROM director_proposal_revisions WHERE project_id = ?", (project_id,)).fetchone()
            connection.commit()
            return int(row["revision"])
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def bump_asset_index_revision(self, project_id: str) -> int:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            revision = self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
            return revision
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _increment_asset_index_revision_with_connection(self, connection: sqlite3.Connection, project_id: str) -> int:
        connection.execute("INSERT INTO director_asset_index_revisions (project_id, revision) VALUES (?, 1) ON CONFLICT(project_id) DO UPDATE SET revision = revision + 1", (project_id,))
        row = connection.execute("SELECT revision FROM director_asset_index_revisions WHERE project_id = ?", (project_id,)).fetchone()
        return int(row["revision"])

    def _execute_asset_index_mutation(self, project_id: str, statement: str, parameters: tuple[Any, ...]) -> None:
        """Commit an eligible asset-index mutation and its revision as one unit."""
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(statement, parameters)
            self._increment_asset_index_revision_with_connection(connection, project_id)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def mark_director_proposals_stale_for_script_alignment(self, project_id: str, source_session_id: str, source_script_segment_ids: list[str]) -> int:
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            changed = self._mark_director_proposals_stale_with_connection(connection, project_id, source_session_id, source_script_segment_ids)
            connection.commit()
            return changed
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _mark_director_proposals_stale_with_connection(self, connection: sqlite3.Connection, project_id: str, source_session_id: str, source_script_segment_ids: list[str]) -> int:
        wanted = set(source_script_segment_ids)
        rows = connection.execute("SELECT proposal_id, proposal_json FROM director_proposals WHERE source_session_id = ? AND status = 'ready'", (source_session_id,)).fetchall()
        changed = 0
        for row in rows:
            payload = json.loads(str(row["proposal_json"]))
            if not wanted.intersection(payload.get("source_script_segment_ids", [])):
                continue
            changed_at = self._now_iso()
            connection.execute("UPDATE director_proposals SET status = 'stale', updated_at = ? WHERE proposal_id = ?", (changed_at, row["proposal_id"]))
            connection.execute("INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)", (row["proposal_id"], "stale", "script_alignment", changed_at))
            changed += 1
        return changed

    def update_script_draft_alignment_and_stale_proposals(self, *, project_id: str, session_id: str, session_payload: dict[str, Any], expected_revision: int, source_script_segment_ids: list[str]) -> dict[str, Any]:
        existing = self.get_editing_session(project_id=project_id, session_id=session_id)
        payload = deepcopy(session_payload)
        if int(payload.get("session_revision") or 0) <= int(existing.get("session_revision") or 1):
            payload["session_revision"] = int(existing.get("session_revision") or 1) + 1
        return self._write_editing_session(project_id=project_id, timeline_id=str(existing["timeline_id"]), session_id=session_id, session_payload=payload, is_new=False, created_at=str(existing["created_at"]), expected_revision=expected_revision, transaction_hook=lambda connection: self._mark_director_proposals_stale_with_connection(connection, project_id, session_id, source_script_segment_ids))

    def save_tts_candidate(
        self,
        *,
        project_id: str,
        segment_id: str,
        asset_id: str,
        source_text: str,
        acceptance: Any | None = None,
    ) -> dict[str, Any]:
        sequence = self._count_rows(project_id, "tts_candidates") + 1
        candidate_id = f"tts_candidate_{sequence:03d}"
        created_at = self._now_iso()
        self._execute(
            project_id,
            """
            INSERT INTO tts_candidates (
                candidate_id, project_id, segment_id, asset_id, source_text,
                technical_status, operator_review_status, target_duration_sec,
                actual_duration_sec, failure_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                project_id,
                segment_id,
                asset_id,
                source_text,
                getattr(acceptance, "technical_status", "legacy_unverified"),
                getattr(acceptance, "operator_review_status", "pending"),
                getattr(acceptance, "target_duration_sec", None),
                getattr(acceptance, "actual_duration_sec", None),
                getattr(acceptance, "failure_code", None),
                created_at,
            ),
        )
        return {
            "candidate_id": candidate_id,
            "project_id": project_id,
            "segment_id": segment_id,
            "asset_id": asset_id,
            "source_text": source_text,
            "technical_status": getattr(acceptance, "technical_status", "legacy_unverified"),
            "operator_review_status": getattr(acceptance, "operator_review_status", "pending"),
            "target_duration_sec": getattr(acceptance, "target_duration_sec", None),
            "actual_duration_sec": getattr(acceptance, "actual_duration_sec", None),
            "failure_code": getattr(acceptance, "failure_code", None),
            "created_at": created_at,
        }

    def list_tts_candidates(self, *, project_id: str, segment_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            project_id,
            """
            SELECT candidate_id, project_id, segment_id, asset_id, source_text,
                   technical_status, operator_review_status, target_duration_sec,
                   actual_duration_sec, failure_code, created_at
            FROM tts_candidates
            WHERE project_id = ? AND segment_id = ?
            ORDER BY created_at ASC, candidate_id ASC
            """,
            (project_id, segment_id),
        )
        return [dict(row) for row in rows]

    def get_tts_candidate(self, *, project_id: str, candidate_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT candidate_id, project_id, segment_id, asset_id, source_text,
                   technical_status, operator_review_status, target_duration_sec,
                   actual_duration_sec, failure_code, created_at
            FROM tts_candidates
            WHERE project_id = ? AND candidate_id = ?
            """,
            (project_id, candidate_id),
        )
        if row is None:
            raise KeyError(f"TTS candidate not found: {candidate_id}")
        return dict(row)

    def update_tts_candidate_listening_review(
        self,
        *,
        project_id: str,
        candidate_id: str,
        decision: str,
    ) -> dict[str, Any]:
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("Listening review decision must be approved or rejected.")
        candidate = self.get_tts_candidate(project_id=project_id, candidate_id=candidate_id)
        if candidate["technical_status"] != "accepted":
            raise ValueError("Only technically accepted TTS candidates can receive a listening review.")
        if candidate["operator_review_status"] != "pending":
            raise ValueError("TTS candidate listening review has already been decided.")
        self._execute(
            project_id,
            "UPDATE tts_candidates SET operator_review_status = ? WHERE project_id = ? AND candidate_id = ?",
            (normalized_decision, project_id, candidate_id),
        )
        candidate["operator_review_status"] = normalized_decision
        return candidate

    def get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT timeline_id, project_id, status, approved_at, updated_at, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM review_approvals
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Review state not found: {timeline_id}")
        payload = dict(row)
        payload["status"] = str(payload.get("status") or "").strip().lower()
        payload["is_current"] = bool(payload.get("is_current"))
        return payload

    def save_subtitle_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        subtitle_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "subtitles",
            "subtitle_*.srt",
        )
        subtitle_id = f"subtitle_{sequence:03d}"
        subtitle_path = self.project_root(project_id) / "subtitles" / f"{subtitle_id}.srt"
        file_uri = self._path_to_uri(project_id, subtitle_path)
        entries = subtitle_payload.get("entries", [])
        subtitle_path.write_text(
            self._serialize_srt(entries),
            encoding="utf-8",
        )
        payload = {
            "subtitle_id": subtitle_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "format": subtitle_payload.get("format", "srt"),
            "file_uri": file_uri,
            "status": "succeeded",
            "created_at": self._now_iso(),
            "notes": subtitle_payload.get("notes", []),
        }
        summary_json = json.dumps(
            {
                "entry_count": len(entries),
                "notes": payload["notes"],
            },
            ensure_ascii=True,
        )
        self._execute(
            project_id,
            """
            INSERT INTO subtitle_renders (
                subtitle_id,
                project_id,
                timeline_id,
                format,
                file_uri,
                status,
                summary_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subtitle_id,
                project_id,
                timeline_id,
                payload["format"],
                file_uri,
                payload["status"],
                summary_json,
                payload["created_at"],
            ),
        )
        return {"subtitle_id": subtitle_id, "file_uri": file_uri, "subtitle": self.get_subtitle_run(project_id=project_id, subtitle_id=subtitle_id)}

    def save_preview_run(
        self,
        *,
        project_id: str,
        timeline_id: str,
        preview_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "previews",
            "preview_*.json",
        )
        preview_id = f"preview_{sequence:03d}"
        preview_path = self.project_root(project_id) / "previews" / f"{preview_id}.json"
        player_path = self.project_root(project_id) / "previews" / f"{preview_id}.html"
        file_uri = self._path_to_uri(project_id, preview_path)
        player_uri = self._path_to_uri(project_id, player_path)
        payload = {
            "preview_id": preview_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "file_uri": file_uri,
            "player_uri": player_uri,
            "status": "succeeded",
            "created_at": self._now_iso(),
            **{key: value for key, value in preview_payload.items() if key != "player_html"},
        }
        player_html = str(preview_payload.get("player_html", ""))
        player_path.write_text(player_html, encoding="utf-8")
        preview_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        summary_json = json.dumps(
            {
                "artifact_kind": payload.get("artifact_kind"),
                "clip_group_count": sum(
                    1 for clip_group in payload.get("clips", []) if _is_store_supported_track_summary(clip_group)
                )
                if isinstance(payload.get("clips", []), list)
                else 0,
            },
            ensure_ascii=True,
        )
        try:
            self._execute(
                project_id,
                """
                INSERT INTO preview_renders (
                    preview_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    status,
                    summary_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preview_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    payload["status"],
                    summary_json,
                    payload["created_at"],
                ),
            )
        except Exception:
            preview_path.unlink(missing_ok=True)
            player_path.unlink(missing_ok=True)
            raise
        return {"preview_id": preview_id, "file_uri": file_uri, "preview": self.get_preview_run(project_id=project_id, preview_id=preview_id)}

    def _next_export_sequence(self, project_id: str) -> int:
        # All export types (capcut / final_render / capcut_draft_export) share one
        # `exports` table with a single export_id primary key, but each type is
        # written to its own subdirectory. Numbering per-subdirectory would let two
        # different export types both compute "export_001" and collide on insert,
        # so the sequence must be derived from the shared table, not a directory.
        rows = self._fetchall(project_id, "SELECT export_id FROM exports WHERE project_id = ?", (project_id,))
        highest = 0
        for row in rows:
            match = re.search(r"(\d+)$", str(row["export_id"]))
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _prune_old_exports(
        self,
        *,
        project_id: str,
        export_type: str,
        keep_last: int = DEFAULT_EXPORT_RETENTION_COUNT,
    ) -> None:
        rows = self._fetchall(
            project_id,
            """
            SELECT export_id, file_uri
            FROM exports
            WHERE project_id = ? AND export_type = ?
            ORDER BY created_at DESC
            """,
            (project_id, export_type),
        )
        for row in rows[keep_last:]:
            artifact_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
            shutil.rmtree(artifact_path.parent, ignore_errors=True)
            self._execute(
                project_id,
                "DELETE FROM exports WHERE project_id = ? AND export_id = ?",
                (project_id, row["export_id"]),
            )

    def save_capcut_export(
        self,
        *,
        project_id: str,
        timeline_id: str,
        export_payload: dict[str, Any],
    ) -> dict[str, Any]:
        invariant_note = "CapCut remains an export target, not the internal source of truth."
        sequence = self._next_export_sequence(project_id)
        export_id = f"export_{sequence:03d}"
        export_directory = self.project_root(project_id) / "exports" / "capcut" / export_id
        export_directory.mkdir(parents=True, exist_ok=True)
        payload_path = export_directory / "capcut_payload.json"
        notes_path = export_directory / "README.txt"
        file_uri = self._path_to_uri(project_id, payload_path)
        payload = {
            "export_id": export_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "export_type": "capcut",
            "file_uri": file_uri,
            "status": "succeeded",
            "created_at": self._now_iso(),
            **export_payload,
        }
        existing_notes = [str(note) for note in payload.get("notes", [])]
        if existing_notes:
            payload["notes"] = existing_notes
        else:
            payload["notes"] = ["CapCut export manifest generated for local post-editing handoff."]
        if invariant_note not in payload["notes"]:
            payload["notes"].append(invariant_note)
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        readme_lines = payload["notes"] or ["CapCut export payload generated from timeline JSON."]
        notes_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
        metadata_json = json.dumps(
            {
                "timeline_id": timeline_id,
                "adapter": payload.get("adapter"),
                "track_count": sum(
                    1 for track in payload.get("tracks", []) if _is_store_supported_track(track)
                )
                if isinstance(payload.get("tracks", []), list)
                else 0,
            },
            ensure_ascii=True,
        )
        try:
            self._execute(
                project_id,
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "capcut",
                    file_uri,
                    payload["status"],
                    metadata_json,
                    payload["created_at"],
                ),
            )
        except Exception:
            shutil.rmtree(export_directory, ignore_errors=True)
            raise
        self._prune_old_exports(project_id=project_id, export_type="capcut")
        return {"export_id": export_id, "file_uri": file_uri, "export": payload}

    def save_final_render(
        self,
        *,
        project_id: str,
        timeline_id: str,
        source_output_path: Path,
        source_session_id: str | None = None,
        source_session_revision: int | None = None,
    ) -> dict[str, Any]:
        sequence = self._next_export_sequence(project_id)
        export_id = f"export_{sequence:03d}"
        export_directory = self.project_root(project_id) / "exports" / "final_render" / export_id
        export_directory.mkdir(parents=True, exist_ok=True)
        destination_path = export_directory / f"output{source_output_path.suffix or '.mp4'}"
        shutil.copy2(source_output_path, destination_path)
        file_uri = self._path_to_uri(project_id, destination_path)
        created_at = self._now_iso()
        try:
            self._execute(
                project_id,
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at
                    ,source_session_id,source_session_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "final_render",
                    file_uri,
                    "succeeded",
                    json.dumps({}, ensure_ascii=True),
                    created_at,
                    source_session_id,
                    source_session_revision,
                ),
            )
        except Exception:
            shutil.rmtree(export_directory, ignore_errors=True)
            raise
        self._prune_old_exports(project_id=project_id, export_type="final_render")
        return {"export_id": export_id, "file_uri": file_uri, "created_at": created_at}

    def get_final_render_export(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, created_at, source_session_id, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        return {
            "export_id": row["export_id"],
            "timeline_id": row["timeline_id"],
            "export_type": row["export_type"],
            "file_uri": row["file_uri"],
            "status": row["status"],
            "created_at": row["created_at"],
            "source_session_id": row["source_session_id"],
            "source_session_revision": row["source_session_revision"],
            "is_current": bool(row["is_current"]),
            "invalidated_at": row["invalidated_at"],
            "invalidated_reason": row["invalidated_reason"],
        }

    def save_capcut_draft_export(
        self,
        *,
        project_id: str,
        timeline_id: str,
        source_draft_path: Path,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        sequence = self._next_export_sequence(project_id)
        export_id = f"export_{sequence:03d}"
        export_directory = self.project_root(project_id) / "exports" / "capcut_draft" / export_id
        export_directory.parent.mkdir(parents=True, exist_ok=True)
        destination_path = export_directory / source_draft_path.name
        shutil.copytree(source_draft_path, destination_path)
        file_uri = self._path_to_uri(project_id, destination_path)
        created_at = self._now_iso()
        try:
            self._execute(
                project_id,
                """
                INSERT INTO exports (
                    export_id,
                    project_id,
                    timeline_id,
                    export_type,
                    file_uri,
                    status,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    project_id,
                    timeline_id,
                    "capcut_draft_export",
                    file_uri,
                    "succeeded",
                    json.dumps({"notes": notes or []}, ensure_ascii=True),
                    created_at,
                ),
            )
        except Exception:
            shutil.rmtree(export_directory, ignore_errors=True)
            raise
        self._prune_old_exports(project_id=project_id, export_type="capcut_draft_export")
        return {"export_id": export_id, "file_uri": file_uri, "created_at": created_at}

    def get_capcut_draft_export(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        return {
            "export_id": row["export_id"],
            "timeline_id": row["timeline_id"],
            "export_type": row["export_type"],
            "file_uri": row["file_uri"],
            "status": row["status"],
            "notes": list(metadata.get("notes") or []),
            "handoff": metadata.get("handoff"),
            "created_at": row["created_at"],
            "source_session_revision": row["source_session_revision"],
            "is_current": bool(row["is_current"]),
            "invalidated_at": row["invalidated_at"],
            "invalidated_reason": row["invalidated_reason"],
        }

    def update_capcut_draft_handoff(
        self, *, project_id: str, export_id: str, handoff: dict[str, Any]
    ) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            "SELECT metadata_json FROM exports WHERE project_id = ? AND export_id = ? AND export_type = ?",
            (project_id, export_id, "capcut_draft_export"),
        )
        if row is None:
            raise KeyError(f"CapCut draft export not found: {export_id}")
        metadata = json.loads(str(row["metadata_json"] or "{}"))
        metadata["handoff"] = handoff
        self._execute(
            project_id,
            "UPDATE exports SET metadata_json = ? WHERE project_id = ? AND export_id = ?",
            (json.dumps(metadata, ensure_ascii=True), project_id, export_id),
        )
        return self.get_capcut_draft_export(project_id=project_id, export_id=export_id)

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
                ORDER BY embeddings.analysis_id ASC, embeddings.embedding_id ASC
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
        return sorted(matches, key=lambda item: (-float(item["score"]), str(item["analysis_id"])))[:limit]

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
        return [str(row["analysis_id"]) for row in rows]

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
                connection.execute("DELETE FROM media_scene_windows WHERE analysis_id = ?", (analysis_id,))
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

    def create_job(
        self,
        *,
        project_id: str,
        job_type: JobType,
        input_ref: str | None = None,
        status: JobStatus = JobStatus.PENDING,
    ) -> dict[str, Any]:
        sequence = self._count_rows(project_id, "jobs") + 1
        job_id = f"{job_type.value}_job_{sequence:03d}"
        started_at = None if status is JobStatus.PENDING else self._now_iso()
        finished_at = started_at if status in {JobStatus.SUCCEEDED, JobStatus.FAILED} else None
        payload = {
            "job_id": job_id,
            "project_id": project_id,
            "job_type": job_type.value,
            "status": status.value,
            "input_ref": input_ref,
            "output_ref": None,
            "error_message": None,
            "started_at": started_at,
            "finished_at": finished_at,
            "progress_percent": None,
        }
        self._execute(
            project_id,
            """
            INSERT INTO jobs (
                job_id,
                project_id,
                job_type,
                status,
                input_ref,
                output_ref,
                error_message,
                started_at,
                finished_at,
                progress_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["job_id"],
                payload["project_id"],
                payload["job_type"],
                payload["status"],
                payload["input_ref"],
                payload["output_ref"],
                payload["error_message"],
                payload["started_at"],
                payload["finished_at"],
                payload["progress_percent"],
            ),
        )
        return payload

    def update_job(
        self,
        *,
        project_id: str,
        job_id: str,
        status: JobStatus,
        output_ref: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        started_at = self._now_iso() if status is JobStatus.RUNNING else None
        finished_at = self._now_iso() if status in {JobStatus.SUCCEEDED, JobStatus.FAILED} else None
        # A finished job always reports a definite progress value so the UI
        # doesn't get stuck showing a stale in-flight percentage.
        finished_progress_percent = 100 if status is JobStatus.SUCCEEDED else None
        self._execute(
            project_id,
            """
            UPDATE jobs
            SET status = ?,
                output_ref = COALESCE(?, output_ref),
                error_message = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = COALESCE(?, finished_at),
                progress_percent = COALESCE(?, progress_percent)
            WHERE project_id = ? AND job_id = ?
            """,
            (status.value, output_ref, error_message, started_at, finished_at, finished_progress_percent, project_id, job_id),
        )
        return self.get_job(project_id=project_id, job_id=job_id)

    def update_job_progress(self, *, project_id: str, job_id: str, progress_percent: int) -> None:
        self._execute(
            project_id,
            "UPDATE jobs SET progress_percent = ? WHERE project_id = ? AND job_id = ?",
            (max(0, min(100, progress_percent)), project_id, job_id),
        )

    def get_job(self, *, project_id: str, job_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT
                job_id,
                project_id,
                job_type,
                status,
                input_ref,
                output_ref,
                error_message,
                started_at,
                finished_at,
                progress_percent
            FROM jobs
            WHERE project_id = ? AND job_id = ?
            """,
            (project_id, job_id),
        )
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return dict(row)

    def list_jobs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT
                    job_id,
                    project_id,
                    job_type,
                    status,
                    input_ref,
                    output_ref,
                    error_message,
                    started_at,
                    finished_at,
                    progress_percent
                FROM jobs
                WHERE project_id = ?
                ORDER BY COALESCE(started_at, ''), job_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def update_asset_metadata(self, *, project_id: str, asset_id: str, metadata_patch: dict[str, Any]) -> dict[str, Any]:
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        merged_metadata = {**asset["metadata"], **metadata_patch}
        self._execute_asset_index_mutation(
            project_id,
            "UPDATE assets SET metadata_json = ? WHERE project_id = ? AND asset_id = ?",
            (json.dumps(merged_metadata, ensure_ascii=True), project_id, asset_id),
        )
        return self.get_asset(project_id=project_id, asset_id=asset_id)

    def get_asset(self, *, project_id: str, asset_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ? AND asset_id = ?
            """,
            (project_id, asset_id),
        )
        if row is None:
            raise KeyError(f"Asset not found: {asset_id}")
        payload = dict(row)
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
        return payload

    def list_assets(
        self,
        *,
        project_id: str,
        asset_type: AssetType | None = None,
    ) -> list[dict[str, Any]]:
        if asset_type is None:
            query = """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ?
            ORDER BY created_at ASC
            """
            params: tuple[Any, ...] = (project_id,)
        else:
            query = """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE project_id = ? AND asset_type = ?
            ORDER BY created_at ASC
            """
            params = (project_id, asset_type.value)
        connection = self._connection(project_id)
        try:
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
            items.append(payload)
        return items

    def list_segments(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT segment_id, project_id, start_sec, end_sec, text, source_asset_id,
                       confidence, cleanup_decision, review_required, metadata_json
                FROM segments
                WHERE project_id = ?
                ORDER BY start_sec ASC, segment_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["review_required"] = _normalize_boolish(payload["review_required"])
            payload["metadata"] = self._json_object(payload.pop("metadata_json"))
            payload["provider_trace"] = payload["metadata"].get("provider_trace") or build_provider_trace(
                final_provider="heuristic_fallback"
            )
            items.append(payload)
        return items

    def list_recommendation_rows(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT recommendation_id, project_id, target_segment_id, recommendation_type,
                       selected_asset_id, score, reason, auto_apply_allowed,
                       review_required, decision_state, payload_json, created_at
                FROM recommendations
                WHERE project_id = ?
                ORDER BY created_at ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["auto_apply_allowed"] = _normalize_boolish(payload["auto_apply_allowed"])
            payload["review_required"] = _normalize_boolish(payload["review_required"])
            payload["decision_state"] = self._normalize_recommendation_decision_state(payload)
            payload["payload"] = self._json_object(payload.pop("payload_json"))
            payload["provider_trace"] = payload["payload"].get("provider_trace") or build_provider_trace(
                final_provider="heuristic_fallback"
                if _canonical_recommendation_type(payload["recommendation_type"]) == RecommendationType.BROLL.value
                else "rule_based_fallback"
            )
            items.append(payload)
        return items

    def get_transcript(self, *, project_id: str, transcript_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT transcript_id, project_id, source_asset_id, transcript_uri, transcript_text, provider_name, segments_json, created_at
            FROM transcripts
            WHERE project_id = ? AND transcript_id = ?
            """,
            (project_id, transcript_id),
        )
        if row is None:
            raise KeyError(f"Transcript not found: {transcript_id}")
        payload = dict(row)
        payload["segments"] = json.loads(payload.pop("segments_json"))
        return payload

    def get_segment_analysis(self, *, project_id: str, segment_analysis_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT segment_analysis_id, project_id, transcript_id, script_asset_id, file_uri, segments_json, created_at
            FROM segment_analysis_runs
            WHERE project_id = ? AND segment_analysis_id = ?
            """,
            (project_id, segment_analysis_id),
        )
        if row is None:
            raise KeyError(f"Segment analysis not found: {segment_analysis_id}")
        payload = dict(row)
        payload["segments"] = json.loads(payload.pop("segments_json"))
        for segment in payload["segments"]:
            if "provider_trace" not in segment:
                metadata = segment.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    segment["metadata"] = metadata
                segment["provider_trace"] = metadata.get("provider_trace") or build_provider_trace(
                    final_provider="heuristic_fallback"
                )
        return payload

    def get_recommendation_run(
        self,
        *,
        project_id: str,
        recommendation_run_id: str,
        recommendation_type: RecommendationType,
    ) -> dict[str, Any]:
        file_path = (
            self.project_root(project_id)
            / "analysis"
            / "recommendations"
            / f"{recommendation_run_id}.json"
        )
        if not file_path.exists():
            raise KeyError(f"Recommendation run not found: {recommendation_run_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if _canonical_recommendation_type(payload.get("recommendation_type")) != recommendation_type.value:
            raise KeyError(f"Recommendation run type mismatch: {recommendation_run_id}")
        payload["recommendation_type"] = _canonical_recommendation_type(payload.get("recommendation_type"))
        fallback_provider = (
            "heuristic_fallback"
            if recommendation_type == RecommendationType.BROLL
            else "rule_based_fallback"
        )
        for item in payload.get("recommendations", []):
            item_payload = item.get("payload")
            if not isinstance(item_payload, dict):
                item_payload = {}
                item["payload"] = item_payload
            item["provider_trace"] = item.get("provider_trace") or item_payload.get("provider_trace") or build_provider_trace(
                final_provider=fallback_provider
            )
        return payload

    def get_timeline_run(self, *, project_id: str, timeline_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT timeline_id, project_id, version, output_mode, file_uri, summary_json, created_at
            FROM timelines
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Timeline not found: {timeline_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Timeline JSON missing: {timeline_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        return payload

    def get_persisted_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> dict[str, Any] | None:
        timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        operator_guidance = timeline_payload.get("operator_guidance")
        return operator_guidance if isinstance(operator_guidance, dict) else None

    def get_operator_guidance_reuse_key(
        self,
        *,
        project_id: str,
        timeline_id: str,
    ) -> str | None:
        timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
        reuse_key = timeline_payload.get("_operator_guidance_reuse_key")
        if not isinstance(reuse_key, str):
            return None
        normalized_reuse_key = reuse_key.strip()
        return normalized_reuse_key or None

    def save_operator_guidance(
        self,
        *,
        project_id: str,
        timeline_id: str,
        operator_guidance: dict[str, Any],
    ) -> dict[str, Any]:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["operator_guidance"] = operator_guidance
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        try:
            self._append_provider_trace_audit_event(
                project_id=project_id,
                event={
                    "artifact_type": "review_guidance",
                    "artifact_id": f"{timeline_id}:review_guidance:{self._next_provider_trace_event_sequence(project_id=project_id):03d}",
                    "timeline_id": timeline_id,
                    "created_at": self._now_iso(),
                    "provider_trace": operator_guidance.get("provider_trace")
                    or build_provider_trace(final_provider="heuristic_fallback"),
                },
            )
        except OSError:
            pass
        return operator_guidance

    def save_operator_guidance_reuse_key(
        self,
        *,
        project_id: str,
        timeline_id: str,
        reuse_key: str,
    ) -> str:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        normalized_reuse_key = str(reuse_key or "").strip()
        if normalized_reuse_key:
            payload["_operator_guidance_reuse_key"] = normalized_reuse_key
        else:
            payload.pop("_operator_guidance_reuse_key", None)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return normalized_reuse_key

    def save_provider_trace_audit_event(self, *, project_id: str, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("created_at", self._now_iso())
        authoritative_error: Exception | None = None
        if str(payload.get("status") or "") == JobStatus.FAILED.value:
            try:
                self._save_failed_provider_trace_run(project_id=project_id, event=payload)
            except Exception as exc:
                authoritative_error = exc
        try:
            self._append_provider_trace_audit_event(project_id=project_id, event=payload)
        except OSError:
            if authoritative_error is not None:
                raise authoritative_error
        else:
            authoritative_error = None
        if authoritative_error is not None:
            raise authoritative_error
        return payload

    def clear_operator_guidance(self, *, project_id: str, timeline_id: str) -> None:
        file_path = self._timeline_file_path(project_id=project_id, timeline_id=timeline_id)
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if "operator_guidance" not in payload and "_operator_guidance_reuse_key" not in payload:
            return
        payload.pop("operator_guidance", None)
        payload.pop("_operator_guidance_reuse_key", None)
        file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def get_preview_run(self, *, project_id: str, preview_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT preview_id, project_id, timeline_id, file_uri, status, summary_json, created_at, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM preview_renders
            WHERE project_id = ? AND preview_id = ?
            """,
            (project_id, preview_id),
        )
        if row is None:
            raise KeyError(f"Preview not found: {preview_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Preview artifact missing: {preview_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["provider_trace"] = payload.get("provider_trace") or build_provider_trace(final_provider="static_fallback")
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        payload["created_at"] = row["created_at"]
        payload["source_session_revision"] = row["source_session_revision"]
        payload["is_current"] = bool(row["is_current"])
        payload["invalidated_at"] = row["invalidated_at"]
        payload["invalidated_reason"] = row["invalidated_reason"]
        return payload

    def get_subtitle_run(self, *, project_id: str, subtitle_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id, project_id, timeline_id, format, file_uri, status, summary_json, created_at, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM subtitle_renders
            WHERE project_id = ? AND subtitle_id = ?
            """,
            (project_id, subtitle_id),
        )
        if row is None:
            raise KeyError(f"Subtitle not found: {subtitle_id}")
        payload = dict(row)
        summary = json.loads(payload.pop("summary_json") or "{}")
        payload["notes"] = summary.get("notes") or ["Subtitle file generated from approved review timeline."]
        payload["summary"] = summary
        payload["is_current"] = bool(payload.get("is_current"))
        return payload

    def get_export_run(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at, source_session_revision, is_current, invalidated_at, invalidated_reason
            FROM exports
            WHERE project_id = ? AND export_id = ?
            """,
            (project_id, export_id),
        )
        if row is None:
            raise KeyError(f"Export not found: {export_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Export artifact missing: {export_id}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        payload["provider_trace"] = payload.get("provider_trace") or build_provider_trace(final_provider="static_fallback")
        payload["metadata"] = json.loads(row["metadata_json"] or "{}")
        payload["created_at"] = row["created_at"]
        payload["source_session_revision"] = row["source_session_revision"]
        payload["is_current"] = bool(row["is_current"])
        payload["invalidated_at"] = row["invalidated_at"]
        payload["invalidated_reason"] = row["invalidated_reason"]
        payload["is_current"] = bool(payload["is_current"])
        return payload

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT session_id, project_id, timeline_id, file_uri, summary_json, session_revision, session_json, created_at, updated_at
            FROM editing_sessions
            WHERE project_id = ? AND session_id = ?
            """,
            (project_id, session_id),
        )
        if row is None:
            raise KeyError(f"Editing session not found: {session_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        canonical_json = str(row["session_json"] or "")
        try:
            payload = json.loads(canonical_json) if canonical_json and canonical_json != "{}" else {}
        except json.JSONDecodeError:
            payload = {}
        if not payload:
            if not file_path.exists():
                raise KeyError(f"Editing session JSON missing: {session_id}")
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        elif (not file_path.exists()) or file_path.read_text(encoding="utf-8") != canonical_json:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            recovery_path = file_path.with_name(f".{file_path.name}.{uuid.uuid4().hex}.tmp")
            recovery_path.write_text(canonical_json, encoding="utf-8")
            recovery_path.replace(file_path)
        payload["summary"] = json.loads(row["summary_json"] or "{}")
        payload["session_revision"] = int(row["session_revision"])
        payload["undo_count"] = len(payload.get("undo_stack", []))
        payload["redo_count"] = len(payload.get("redo_stack", []))
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        return payload

    def get_latest_editing_session(self, *, project_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT session_id
            FROM editing_sessions
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, session_id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        if row is None:
            raise KeyError(f"Editing session not found for project: {project_id}")
        return self.get_editing_session(project_id=project_id, session_id=str(row["session_id"]))

    def build_review_snapshot(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        segments: list[dict[str, Any]],
        recommendations: list[dict[str, Any]] | None = None,
        timeline_review_flags: list[dict[str, Any]],
        timeline_applied_recommendations: list[dict[str, Any]] | None = None,
        timeline_pending_recommendations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if timeline_applied_recommendations is not None or timeline_pending_recommendations is not None:
            applied_candidates: list[dict[str, Any]] = []
            for item in timeline_applied_recommendations or []:
                decision_state = self._normalize_recommendation_decision_state(item)
                applied_candidates.append(
                    self._review_snapshot_recommendation_payload(
                        item,
                        fallback_decision_state=decision_state,
                    )
                )
            pending_candidates: list[dict[str, Any]] = []
            for item in timeline_pending_recommendations or []:
                decision_state = self._normalize_recommendation_decision_state(item)
                pending_candidates.append(
                    self._review_snapshot_recommendation_payload(
                        item,
                        fallback_decision_state=decision_state,
                    )
                )
            applied = [
                item
                for item in applied_candidates
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            ]
            applied.extend(
                item
                for item in pending_candidates
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            )
            pending = [
                item
                for item in applied_candidates
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            ]
            pending.extend(
                item
                for item in pending_candidates
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            )
        else:
            recommendation_rows: list[dict[str, Any]] = []
            if any(
                isinstance(item, dict)
                and not str(item.get("recommendation_type") or "").strip()
                for item in recommendations or []
            ):
                recommendation_rows = self.list_recommendation_rows(project_id=project_id)
            normalized_recommendations = [
                self._review_snapshot_recommendation_payload(
                    self._hydrate_review_snapshot_recommendation_type(
                        recommendation=item,
                        recommendation_rows=recommendation_rows,
                    )
                )
                for item in recommendations or []
            ]
            applied = [
                item
                for item in normalized_recommendations
                if str(item.get("decision_state") or "") == "approved"
                and _is_store_supported_recommendation_type(item)
            ]
            pending = [
                item
                for item in normalized_recommendations
                if str(item.get("decision_state") or "") == "pending"
                and _is_store_blocking_pending_recommendation(item)
            ]
        has_blocking_review_flag = any(
            _is_store_blocking_review_flag(flag) for flag in timeline_review_flags
        )
        has_blocking_pending_recommendation = any(
            _is_store_blocking_pending_recommendation(item) for item in pending
        )
        if has_blocking_review_flag or has_blocking_pending_recommendation:
            review_status = "blocked"
        elif timeline_id:
            try:
                review_status = self.get_review_state(
                    project_id=project_id,
                    timeline_id=str(timeline_id),
                )["status"]
            except KeyError:
                review_status = "draft"
        else:
            review_status = "blocked"
        normalized_review_flags = _normalize_review_flag_payloads(timeline_review_flags)
        return {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "review_status": review_status,
            "segments": segments,
            "applied_recommendations": applied,
            "pending_recommendations": pending,
            "review_flags": normalized_review_flags,
        }

    def _review_snapshot_recommendation_payload(
        self,
        recommendation: dict[str, Any],
        *,
        fallback_decision_state: str | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(recommendation)
        payload["decision_state"] = fallback_decision_state or self._normalize_recommendation_decision_state(
            payload
        )
        payload["provider_trace"] = payload.get("provider_trace") or payload.get("payload", {}).get(
            "provider_trace"
        ) or build_provider_trace(
            final_provider=(
                "heuristic_fallback"
                if _canonical_recommendation_type(payload.get("recommendation_type"))
                == RecommendationType.BROLL.value
                else "rule_based_fallback"
            )
        )
        return payload

    def _hydrate_review_snapshot_recommendation_type(
        self,
        *,
        recommendation: dict[str, Any],
        recommendation_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = deepcopy(recommendation)
        if str(payload.get("recommendation_type") or "").strip():
            return payload

        matched_types = {
            str(row.get("recommendation_type") or "").strip()
            for row in recommendation_rows
            if isinstance(row, dict)
            and str(row.get("target_segment_id") or "").strip()
            == str(payload.get("target_segment_id") or "").strip()
            and str(row.get("selected_asset_id") or "").strip()
            == str(payload.get("selected_asset_id") or "").strip()
            and str(row.get("reason") or "").strip() == str(payload.get("reason") or "").strip()
            and float(row.get("score") or 0.0) == float(payload.get("score") or 0.0)
        }
        if len(matched_types) == 1:
            payload["recommendation_type"] = next(iter(matched_types))
        return payload

    def get_provider_trace_audit(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        jobs = self.list_jobs(project_id=project_id)
        entries: list[dict[str, Any]] = []
        filter_timeline_id = self._normalized_provider_trace_filter_value(timeline_id)
        filter_job_type = self._normalized_provider_trace_filter_value(job_type)
        filter_artifact_type = self._normalized_provider_trace_filter_value(artifact_type)
        filter_final_provider = self._normalized_provider_trace_filter_value(final_provider)
        filter_fallback_reason = self._normalized_provider_trace_filter_value(fallback_reason)
        upstream_segment_job_ids: set[str] = set()
        upstream_recommendation_job_ids: set[str] = set()
        use_exact_recommendation_lineage = False
        timeline_jobs_by_timeline_id = {
            str(job.get("output_ref") or ""): job
            for job in jobs
            if job["job_type"] == JobType.TIMELINE_BUILD.value and job.get("output_ref")
        }
        review_guidance_jobs_by_timeline_id = dict(timeline_jobs_by_timeline_id)
        timeline_ids_by_timeline_job_id = {
            str(job.get("job_id") or ""): str(job.get("output_ref") or "")
            for job in jobs
            if job["job_type"] == JobType.TIMELINE_BUILD.value and job.get("output_ref")
        }
        for job in jobs:
            if job["job_type"] != JobType.PARTIAL_REGENERATION.value or not job.get("output_ref"):
                continue
            try:
                partial_regeneration = self.get_partial_regeneration_run(
                    project_id=project_id,
                    partial_regeneration_id=str(job["output_ref"]),
                )
            except Exception:
                continue
            timeline_payload = partial_regeneration.get("timeline")
            if not isinstance(timeline_payload, dict):
                continue
            timeline_id = str(timeline_payload.get("timeline_id") or "").strip()
            if timeline_id:
                review_guidance_jobs_by_timeline_id[timeline_id] = job
                timeline_ids_by_timeline_job_id[str(job.get("job_id") or "")] = timeline_id
        if include_upstream and filter_timeline_id is not None:
            timeline_job = timeline_jobs_by_timeline_id.get(filter_timeline_id)
            if timeline_job is not None:
                segment_job_id = str(timeline_job.get("input_ref") or "")
            else:
                segment_job_id = ""
            try:
                timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=filter_timeline_id)
            except Exception:
                timeline_payload = {}
            lineage = timeline_payload.get("lineage")
            if isinstance(lineage, dict):
                segment_job_id = str(lineage.get("segment_analysis_job_id") or segment_job_id)
                recommendation_job_ids = lineage.get("recommendation_job_ids")
                if isinstance(recommendation_job_ids, list):
                    upstream_recommendation_job_ids = {
                        str(job_id).strip()
                        for job_id in recommendation_job_ids
                        if str(job_id).strip()
                    }
                    use_exact_recommendation_lineage = True
            if segment_job_id:
                upstream_segment_job_ids.add(segment_job_id)

        for job in jobs:
            job_type = str(job["job_type"])
            if job_type == JobType.SEGMENT_ANALYSIS.value and job.get("output_ref"):
                try:
                    analysis = self.get_segment_analysis(
                        project_id=project_id,
                        segment_analysis_id=str(job["output_ref"]),
                    )
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="segment_analysis",
                        artifact_id=str(analysis["segment_analysis_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(analysis.get("segments", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.BROLL_RECOMMENDATION.value and job.get("output_ref"):
                try:
                    run = self.get_recommendation_run(
                        project_id=project_id,
                        recommendation_run_id=str(job["output_ref"]),
                        recommendation_type=RecommendationType.BROLL,
                    )
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="broll_recommendation",
                        artifact_id=str(run["recommendation_run_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(run.get("source_job_id") or job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(run.get("recommendations", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.MUSIC_RECOMMENDATION.value and job.get("output_ref"):
                try:
                    run = self.get_recommendation_run(
                        project_id=project_id,
                        recommendation_run_id=str(job["output_ref"]),
                        recommendation_type=RecommendationType.BGM,
                    )
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="music_recommendation",
                        artifact_id=str(run["recommendation_run_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(run.get("source_job_id") or job.get("input_ref") or ""),
                        trace=self._merged_provider_trace(run.get("recommendations", [])),
                        timeline_id=None,
                    )
                )
            elif job_type == JobType.PREVIEW_RENDER.value and job.get("output_ref"):
                try:
                    preview = self.get_preview_run(project_id=project_id, preview_id=str(job["output_ref"]))
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="preview_render",
                        artifact_id=str(preview["preview_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=preview["provider_trace"],
                        timeline_id=str(preview.get("timeline_id") or ""),
                        created_at=str(preview.get("created_at") or ""),
                    )
                )
            elif job_type == JobType.SUBTITLE_RENDER.value and job.get("output_ref"):
                try:
                    subtitle = self.get_subtitle_run(project_id=project_id, subtitle_id=str(job["output_ref"]))
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="subtitle_render",
                        artifact_id=str(subtitle["subtitle_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=build_provider_trace(final_provider="static_fallback"),
                        timeline_id=str(subtitle.get("timeline_id") or ""),
                        created_at=str(subtitle.get("created_at") or ""),
                    )
                )
            elif job_type == JobType.CAPCUT_EXPORT.value and job.get("output_ref"):
                try:
                    export = self.get_export_run(project_id=project_id, export_id=str(job["output_ref"]))
                except Exception:
                    continue
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="capcut_export",
                        artifact_id=str(export["export_id"]),
                        job_type=job_type,
                        job=job,
                        source_job_id=str(job.get("input_ref") or ""),
                        trace=export["provider_trace"],
                        timeline_id=str(export.get("timeline_id") or ""),
                        created_at=str(export.get("created_at") or ""),
                    )
                )

        failed_entries_by_job_id: dict[str, dict[str, Any]] = {}
        for item in self._list_provider_trace_failed_runs(project_id=project_id):
            trace = item.get("provider_trace")
            if not isinstance(trace, dict):
                trace = build_provider_trace(
                    final_provider="unknown_failure",
                    fallback_reasons=["missing_provider_trace"],
                )
            job_id = str(item.get("job_id") or "")
            source_job_id = str(item.get("source_job_id") or "")
            resolved_timeline_id = str(item.get("timeline_id") or "") or timeline_ids_by_timeline_job_id.get(source_job_id, "")
            artifact_type = str(item.get("artifact_type") or item.get("job_type") or "unknown_failure")
            entry = self._provider_trace_entry(
                artifact_type=artifact_type,
                artifact_id=str(item.get("artifact_id") or job_id),
                job_type=str(item.get("job_type") or artifact_type),
                job=None,
                source_job_id=source_job_id or None,
                trace=trace,
                timeline_id=resolved_timeline_id or None,
                status=JobStatus.FAILED.value,
                finished_at=str(item.get("finished_at") or ""),
                created_at=str(item.get("created_at") or ""),
                error_message=str(item.get("error_message") or ""),
                job_id=job_id or None,
            )
            if job_id:
                failed_entries_by_job_id[job_id] = entry
            else:
                entries.append(entry)

        audit_events = self._list_provider_trace_audit_events(project_id=project_id)
        review_guidance_attempt_entries_by_key: dict[str, dict[str, Any]] = {}
        guidance_timeline_ids_with_events: set[str] = set()
        for item in audit_events:
            if str(item.get("status") or "") == JobStatus.FAILED.value:
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(
                        final_provider="unknown_failure",
                        fallback_reasons=["missing_provider_trace"],
                    )
                job_id = str(item.get("job_id") or "")
                source_job_id = str(item.get("source_job_id") or "")
                resolved_timeline_id = str(item.get("timeline_id") or "") or timeline_ids_by_timeline_job_id.get(source_job_id, "")
                artifact_type = str(item.get("artifact_type") or item.get("job_type") or "unknown_failure")
                entry = self._provider_trace_entry(
                    artifact_type=artifact_type,
                    artifact_id=str(item.get("artifact_id") or job_id),
                    job_type=str(item.get("job_type") or artifact_type),
                    job=None,
                    source_job_id=source_job_id or None,
                    trace=trace,
                    timeline_id=resolved_timeline_id or None,
                    status=JobStatus.FAILED.value,
                    finished_at=str(item.get("finished_at") or ""),
                    created_at=str(item.get("created_at") or ""),
                    error_message=str(item.get("error_message") or ""),
                    job_id=job_id or None,
                )
                if job_id and job_id in failed_entries_by_job_id:
                    failed_entries_by_job_id[job_id] = self._merge_provider_trace_failed_entries(
                        failed_entries_by_job_id[job_id],
                        entry,
                    )
                elif job_id:
                    failed_entries_by_job_id[job_id] = entry
                else:
                    entries.append(entry)
                continue
            if str(item.get("artifact_type") or "") == "review_guidance_attempt":
                timeline_id = str(item.get("timeline_id") or "")
                timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(final_provider="heuristic_fallback")
                timeline_job_id = timeline_job["job_id"] if timeline_job else ""
                job_id = str(item.get("job_id") or timeline_job_id or "") or None
                review_guidance_attempt_entries_by_key[f"{job_id or ''}|{timeline_id}|review_guidance_attempt"] = (
                    self._provider_trace_entry(
                        artifact_type="review_guidance_attempt",
                        artifact_id=str(item.get("artifact_id") or timeline_id),
                        job_type=str(item.get("job_type") or JobType.TIMELINE_BUILD.value),
                        job=None,
                        source_job_id=str(item.get("source_job_id") or timeline_job_id or "") or None,
                        trace=trace,
                        timeline_id=timeline_id or None,
                        status=str(item.get("status") or "available"),
                        finished_at=str(item.get("finished_at") or timeline_job.get("finished_at") or "") if timeline_job else str(item.get("finished_at") or ""),
                        created_at=str(item.get("created_at") or ""),
                        error_message=str(item.get("error_message") or "") or None,
                        job_id=job_id,
                    )
                )
                continue
            if str(item.get("artifact_type") or "") != "review_guidance":
                continue
            timeline_id = str(item.get("timeline_id") or "")
            if timeline_id:
                guidance_timeline_ids_with_events.add(timeline_id)
            timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
            trace = item.get("provider_trace")
            if not isinstance(trace, dict):
                trace = build_provider_trace(final_provider="heuristic_fallback")
            entries.append(
                self._provider_trace_entry(
                    artifact_type="review_guidance",
                    artifact_id=str(item.get("artifact_id") or timeline_id),
                    job_type=str(timeline_job.get("job_type") or JobType.TIMELINE_BUILD.value)
                    if timeline_job
                    else JobType.TIMELINE_BUILD.value,
                    job=None,
                    source_job_id=timeline_job["job_id"] if timeline_job else None,
                    trace=trace,
                    timeline_id=timeline_id or None,
                    status="available",
                    finished_at=str(timeline_job.get("finished_at") or "") if timeline_job else None,
                    created_at=str(item.get("created_at") or ""),
                    error_message=None,
                    job_id=timeline_job["job_id"] if timeline_job else None,
                    )
                )

        for timeline_id in self._list_timeline_ids(project_id=project_id):
            if timeline_id in guidance_timeline_ids_with_events:
                continue
            try:
                timeline_payload = self.get_timeline_run(project_id=project_id, timeline_id=timeline_id)
            except Exception:
                continue
            legacy_history = timeline_payload.get("operator_guidance_history")
            legacy_entries: list[dict[str, Any]] = []
            if isinstance(legacy_history, list):
                legacy_entries = [item for item in legacy_history if isinstance(item, dict)]
            elif isinstance(timeline_payload.get("operator_guidance"), dict):
                legacy_entries = [
                    {
                        "artifact_id": f"{timeline_id}:review_guidance:001",
                        "created_at": str(timeline_payload.get("created_at") or ""),
                        "provider_trace": timeline_payload["operator_guidance"].get("provider_trace")
                        or build_provider_trace(final_provider="heuristic_fallback"),
                    }
                ]
            timeline_job = review_guidance_jobs_by_timeline_id.get(timeline_id)
            for item in legacy_entries:
                trace = item.get("provider_trace")
                if not isinstance(trace, dict):
                    trace = build_provider_trace(final_provider="heuristic_fallback")
                entries.append(
                    self._provider_trace_entry(
                        artifact_type="review_guidance",
                        artifact_id=str(item.get("artifact_id") or timeline_id),
                        job_type=str(timeline_job.get("job_type") or JobType.TIMELINE_BUILD.value)
                        if timeline_job
                        else JobType.TIMELINE_BUILD.value,
                        job=None,
                        source_job_id=timeline_job["job_id"] if timeline_job else None,
                        trace=trace,
                        timeline_id=timeline_id,
                        status="available",
                        finished_at=str(timeline_job.get("finished_at") or "") if timeline_job else None,
                        created_at=str(item.get("created_at") or ""),
                        error_message=None,
                        job_id=timeline_job["job_id"] if timeline_job else None,
                    )
                )

        entries.extend(failed_entries_by_job_id.values())
        entries.extend(review_guidance_attempt_entries_by_key.values())
        entries = [
                entry
                for entry in entries
                if self._provider_trace_entry_matches_filters(
                    entry,
                    timeline_id=filter_timeline_id,
                    include_upstream=include_upstream,
                    upstream_segment_job_ids=upstream_segment_job_ids,
                    upstream_recommendation_job_ids=upstream_recommendation_job_ids,
                    use_exact_recommendation_lineage=use_exact_recommendation_lineage,
                    job_type=filter_job_type,
                    artifact_type=filter_artifact_type,
                    final_provider=filter_final_provider,
                    fallback_reason=filter_fallback_reason,
                )
        ]
        entries.sort(key=lambda item: (item["finished_at"] or item["created_at"] or "", item["artifact_type"]))
        direct_entries, upstream_entries = self._group_provider_trace_entries(
            entries,
            timeline_id=filter_timeline_id,
            include_upstream=include_upstream,
            upstream_segment_job_ids=upstream_segment_job_ids,
            upstream_recommendation_job_ids=upstream_recommendation_job_ids,
            use_exact_recommendation_lineage=use_exact_recommendation_lineage,
        )
        return {
            "summary": self._provider_trace_summary(entries),
            "entries": entries,
            "direct_entries": direct_entries,
            "upstream_entries": upstream_entries,
        }

    def resolve_storage_uri(self, *, project_id: str, storage_uri: str) -> Path:
        prefix = f"local://projects/{project_id}/"
        if not storage_uri.startswith(prefix):
            raise ValueError(f"Unsupported storage URI: {storage_uri}")
        project_root = self.project_root(project_id).resolve()
        relative_path = Path(*storage_uri.removeprefix(prefix).split("/"))
        resolved_path = (project_root / relative_path).resolve()
        if not _is_relative_to(resolved_path, project_root):
            raise ValueError("storage_uri_path_escape")
        return resolved_path

    def _create_project_layout(self, project_root: Path) -> None:
        for directory in (
            project_root / "db",
            project_root / "inputs" / "narration",
            project_root / "inputs" / "raw_video",
            project_root / "inputs" / "scripts",
            project_root / "inputs" / "voice_samples",
            project_root / "assets" / "imported",
            project_root / "assets" / "generated",
            project_root / "analysis" / "transcripts",
            project_root / "analysis" / "segments",
            project_root / "analysis" / "recommendations",
            project_root / "analysis" / "partial_regenerations",
            project_root / "editing_sessions",
            project_root / "timelines",
            project_root / "previews",
            project_root / "subtitles",
            project_root / "exports" / "capcut",
            project_root / "cache",
            project_root / "logs",
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _bootstrap_database(self, database_path: Path, project: ProjectRecord) -> None:
        connection = sqlite3.connect(database_path)
        try:
            for statement in PROJECT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(f"DROP TABLE IF EXISTS {RETIRED_CREDENTIAL_TABLE}")
            self._ensure_recommendation_decision_state_column(connection)
            connection.execute(
                """
                INSERT OR REPLACE INTO projects (
                    project_id,
                    name,
                    status,
                    root_storage_uri,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    project.name,
                    project.status.value,
                    project.root_storage_uri,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _asset_directory(self, asset_type: AssetType) -> Path:
        mapping = {
            AssetType.NARRATION_AUDIO: Path("inputs") / "narration",
            AssetType.SCRIPT_DOCUMENT: Path("inputs") / "scripts",
            AssetType.VOICE_SAMPLE_AUDIO: Path("inputs") / "voice_samples",
            AssetType.RAW_VIDEO: Path("inputs") / "raw_video",
            AssetType.BROLL_VIDEO: Path("assets") / "imported",
        }
        return mapping.get(asset_type, Path("assets") / "imported")

    def _path_to_uri(self, project_id: str, path: Path) -> str:
        relative_path = path.relative_to(self.project_root(project_id)).as_posix()
        return f"local://projects/{project_id}/{relative_path}"

    def _next_sequence(self, directory: Path, pattern: str) -> int:
        # Based on the highest existing numeric suffix, not the count of entries:
        # once older entries can be pruned (see _prune_old_exports), a count-based
        # sequence collides with still-existing higher-numbered entries.
        highest = 0
        for path in directory.glob(pattern):
            match = re.search(r"(\d+)$", path.stem)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest + 1

    def _connection(self, project_id: str) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path(project_id), timeout=5.0)
        # WAL lets readers proceed while a writer holds the lock, and
        # busy_timeout makes any remaining contention retry instead of
        # immediately raising "database is locked" — both matter once
        # background job threads (see run_*_job in local_pipeline.py) write
        # to the same per-project database concurrently with polling reads.
        connection.execute("PRAGMA busy_timeout=5000")
        # The database is initialized in WAL mode.  Concurrently asking SQLite
        # to change journal mode can itself take an exclusive lock; a racing
        # connection may safely continue with the already-established mode.
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
        for statement in PROJECT_SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.execute(f"DROP TABLE IF EXISTS {RETIRED_CREDENTIAL_TABLE}")
        self._ensure_recommendation_decision_state_column(connection)
        self._ensure_job_progress_percent_column(connection)
        self._ensure_editing_session_revision_column(connection)
        self._ensure_editing_session_json_column(connection)
        self._ensure_tts_candidate_acceptance_columns(connection)
        self._ensure_artifact_freshness_columns(connection)
        self._ensure_director_message_metadata_column(connection)
        self._ensure_director_claim_columns(connection)
        self._ensure_creation_brief_columns(connection)
        self._ensure_exact_preview_columns(connection)
        self._ensure_artifact_freshness_triggers(connection)
        connection.commit()
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_creation_brief_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(creation_briefs)").fetchall()}
        if columns and "summary_text" not in columns:
            connection.execute("ALTER TABLE creation_briefs ADD COLUMN summary_text TEXT NOT NULL DEFAULT ''")
        if columns and "script_asset_owned" not in columns:
            connection.execute("ALTER TABLE creation_briefs ADD COLUMN script_asset_owned INTEGER NOT NULL DEFAULT 0")

    def _ensure_exact_preview_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(exact_preview_renders)").fetchall()}
        if columns and "duration_sec" not in columns:
            connection.execute("ALTER TABLE exact_preview_renders ADD COLUMN duration_sec REAL")

    def _ensure_director_message_metadata_column(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(director_messages)").fetchall()}
        if "metadata_json" not in columns:
            connection.execute("ALTER TABLE director_messages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_director_claim_columns(self, connection: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(director_message_claims)").fetchall()}
        if "owner_token" not in columns:
            connection.execute("ALTER TABLE director_message_claims ADD COLUMN owner_token TEXT NOT NULL DEFAULT ''")
        if "heartbeat_at" not in columns:
            connection.execute("ALTER TABLE director_message_claims ADD COLUMN heartbeat_at TEXT NOT NULL DEFAULT ''")

    def _ensure_recommendation_decision_state_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(recommendations)").fetchall()
        }
        if "decision_state" not in existing_columns:
            connection.execute("ALTER TABLE recommendations ADD COLUMN decision_state TEXT")

    def _ensure_job_progress_percent_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "progress_percent" not in existing_columns:
            try:
                connection.execute("ALTER TABLE jobs ADD COLUMN progress_percent INTEGER")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    def _ensure_editing_session_revision_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(editing_sessions)").fetchall()
        }
        if "session_revision" not in existing_columns:
            connection.execute("ALTER TABLE editing_sessions ADD COLUMN session_revision INTEGER NOT NULL DEFAULT 1")

    def _ensure_artifact_freshness_columns(self, connection: sqlite3.Connection) -> None:
        # The schema intentionally remains backward-compatible with project
        # databases created before artifact lineage existed.  The column check
        # and ALTER therefore have to share a writer transaction: otherwise
        # two first-use connections can both observe a missing column and the
        # losing connection raises "duplicate column name".
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN IMMEDIATE")
        try:
            for table in ("review_approvals", "preview_renders", "subtitle_renders", "exports"):
                existing = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                for column, declaration in (
                    ("source_session_id", "TEXT"),
                    ("source_session_revision", "INTEGER"),
                    ("is_current", "INTEGER NOT NULL DEFAULT 1"),
                    ("invalidated_at", "TEXT"),
                    ("invalidated_reason", "TEXT"),
                ):
                    if column not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
            if owns_transaction:
                connection.commit()
        except Exception:
            if owns_transaction:
                connection.rollback()
            raise

    def _ensure_artifact_freshness_triggers(self, connection: sqlite3.Connection) -> None:
        # This migration deliberately replaces an earlier trigger definition so
        # that an explicit lineage revision is preserved.  _connection() is also
        # used by background jobs, so the replacement must be one SQLite writer
        # transaction; otherwise two connections can both observe a missing
        # trigger between DROP and CREATE.
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table, identifier in (("review_approvals", "timeline_id"), ("preview_renders", "preview_id"), ("subtitle_renders", "subtitle_id"), ("exports", "export_id")):
                trigger = f"set_{table}_session_freshness"
                connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                connection.execute(
                    f"CREATE TRIGGER {trigger} AFTER INSERT ON {table} BEGIN "
                    f"UPDATE {table} SET source_session_id = COALESCE(NEW.source_session_id, (SELECT session_id FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id ORDER BY updated_at DESC LIMIT 1)), source_session_revision = COALESCE(NEW.source_session_revision, (SELECT session_revision FROM editing_sessions WHERE project_id = NEW.project_id AND timeline_id = NEW.timeline_id AND (NEW.source_session_id IS NULL OR session_id = NEW.source_session_id) ORDER BY updated_at DESC LIMIT 1), 1), is_current = 1 WHERE {identifier} = NEW.{identifier}; END"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _ensure_editing_session_json_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(editing_sessions)").fetchall()}
        if "session_json" not in existing_columns:
            connection.execute("ALTER TABLE editing_sessions ADD COLUMN session_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_tts_candidate_acceptance_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(tts_candidates)").fetchall()
        }
        additions = (
            ("technical_status", "TEXT NOT NULL DEFAULT 'legacy_unverified'"),
            ("operator_review_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("target_duration_sec", "REAL"),
            ("actual_duration_sec", "REAL"),
            ("failure_code", "TEXT"),
        )
        for column_name, column_definition in additions:
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE tts_candidates ADD COLUMN {column_name} {column_definition}")

    def _derive_recommendation_decision_state(self, recommendation: dict[str, Any]) -> str:
        if _normalize_boolish(recommendation.get("auto_apply_allowed")) and not _normalize_boolish(
            recommendation.get("review_required")
        ):
            return "approved"
        return "pending"

    def _normalize_recommendation_decision_state(self, recommendation: dict[str, Any]) -> str:
        decision_state = str(recommendation.get("decision_state") or "").strip().lower()
        if decision_state in {"approved", "pending", "rejected"}:
            return decision_state
        return self._derive_recommendation_decision_state(recommendation)

    def _execute(self, project_id: str, query: str, params: tuple[Any, ...]) -> None:
        connection = self._connection(project_id)
        try:
            connection.execute(query, params)
            connection.commit()
        finally:
            connection.close()

    def _fetchone(
        self,
        project_id: str,
        query: str,
        params: tuple[Any, ...],
    ) -> sqlite3.Row | None:
        connection = self._connection(project_id)
        try:
            return connection.execute(query, params).fetchone()
        finally:
            connection.close()

    def _fetchall(
        self,
        project_id: str,
        query: str,
        params: tuple[Any, ...],
    ) -> list[sqlite3.Row]:
        connection = self._connection(project_id)
        try:
            return connection.execute(query, params).fetchall()
        finally:
            connection.close()

    def _count_rows(self, project_id: str, table_name: str) -> int:
        row = self._fetchone(project_id, f"SELECT COUNT(*) AS count FROM {table_name} WHERE project_id = ?", (project_id,))
        return int(row["count"]) if row is not None else 0

    def _now_iso(self) -> str:
        return self._clock().isoformat()

    def get_latest_subtitle_for_timeline(self, *, project_id: str, timeline_id: str, include_stale: bool = False) -> dict[str, Any] | None:
        current_filter = "" if include_stale else " AND COALESCE(is_current, 1) = 1"
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id
            FROM subtitle_renders
            WHERE project_id = ? AND timeline_id = ?""" + current_filter + """
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id, timeline_id),
        )
        if row is None:
            return None
        return self.get_subtitle_run(project_id=project_id, subtitle_id=str(row["subtitle_id"]))

    def _serialize_srt(self, entries: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for entry in entries:
            blocks.append(
                "\n".join(
                    [
                        str(entry["index"]),
                        f"{self._format_srt_timestamp(float(entry['start_sec']))} --> {self._format_srt_timestamp(float(entry['end_sec']))}",
                        str(entry["text"]),
                    ]
                )
            )
        return "\n\n".join(blocks) + ("\n" if blocks else "")

    def _format_srt_timestamp(self, seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def _mask_api_key(self, api_key_secret: str) -> str:
        if len(api_key_secret) <= 8:
            return "*" * len(api_key_secret)
        return f"{api_key_secret[:4]}***{api_key_secret[-4:]}"

    def _json_object(self, raw_value: str | None) -> dict[str, Any]:
        decoded = json.loads(raw_value or "{}")
        return decoded if isinstance(decoded, dict) else {}

    def _write_editing_session(
        self,
        *,
        project_id: str,
        timeline_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        is_new: bool,
        created_at: str | None = None,
        expected_revision: int | None = None,
        transaction_hook: Callable[[sqlite3.Connection], None] | None = None,
        invalidate_output_freshness: bool = True,
    ) -> dict[str, Any]:
        session_path = self.project_root(project_id) / "editing_sessions" / f"{session_id}.json"
        file_uri = self._path_to_uri(project_id, session_path)
        created_value = created_at or self._now_iso()
        updated_at = self._now_iso()
        payload = {
            "session_id": session_id,
            "project_id": project_id,
            "timeline_id": timeline_id,
            "session_revision": int(session_payload.get("session_revision") or 1),
            "caption_style": session_payload.get("caption_style"),
            "segments": session_payload.get("segments", []),
            "history": session_payload.get("history", []),
            "undo_stack": session_payload.get("undo_stack", []),
            "redo_stack": session_payload.get("redo_stack", []),
            "created_at": created_value,
            "updated_at": updated_at,
        }
        for key in (
            "script_asset_id",
            "timing_source",
            "narration_alignment_required",
            "stale_proposal_source_script_segment_ids",
            "output_freshness",
        ):
            if key in session_payload:
                payload[key] = session_payload[key]
        summary_json = json.dumps(
            {
                "segment_count": len(payload["segments"]),
                "history_count": len(payload["history"]),
                "undo_count": len(payload["undo_stack"]),
                "redo_count": len(payload["redo_stack"]),
            },
            ensure_ascii=True,
        )
        serialized_payload = json.dumps(payload, indent=2, ensure_ascii=True)
        if is_new:
            session_path.write_text(serialized_payload, encoding="utf-8")
            self._execute(
                project_id,
                """
                INSERT INTO editing_sessions (
                    session_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    summary_json,
                    session_revision,
                    session_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    project_id,
                    timeline_id,
                    file_uri,
                    summary_json,
                    payload["session_revision"],
                    serialized_payload,
                    created_value,
                    updated_at,
                ),
            )
        else:
            connection = self._connection(project_id)
            temporary_path = session_path.with_name(f".{session_path.name}.{uuid.uuid4().hex}.tmp")
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE editing_sessions
                    SET timeline_id = ?, summary_json = ?, session_revision = ?, session_json = ?, updated_at = ?
                    WHERE project_id = ? AND session_id = ? AND (? IS NULL OR session_revision = ?)
                    """,
                    (
                        timeline_id,
                        summary_json,
                        payload["session_revision"],
                        serialized_payload,
                        updated_at,
                        project_id,
                        session_id,
                        expected_revision,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise EditingSessionRevisionConflict("Editing session revision is stale.")
                if transaction_hook is not None:
                    transaction_hook(connection)
                if invalidate_output_freshness:
                    self._invalidate_output_freshness_with_connection(
                        connection, project_id=project_id, timeline_id=timeline_id,
                        source_session_id=session_id, source_session_revision=payload["session_revision"], reason="editing_session_mutation",
                    )
                connection.commit()
                try:
                    temporary_path.write_text(serialized_payload, encoding="utf-8")
                    temporary_path.replace(session_path)
                except Exception as exc:
                    raise EditingSessionPostCommitFileWriteError(
                        f"Editing-session SQLite commit succeeded but JSON mirror write failed: {exc}"
                    ) from exc
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                if temporary_path.exists():
                    temporary_path.unlink()
                raise
            finally:
                connection.close()
        return self.get_editing_session(project_id=project_id, session_id=session_id)

    def _invalidate_output_freshness_with_connection(
        self, connection: sqlite3.Connection, *, project_id: str, timeline_id: str,
        source_session_id: str, source_session_revision: int, reason: str,
    ) -> None:
        now = self._now_iso()
        for table in ("review_approvals", "subtitle_renders", "preview_renders", "exports"):
            connection.execute(
                f"UPDATE {table} SET is_current = 0, invalidated_at = ?, invalidated_reason = ? "
                f"WHERE project_id = ? AND timeline_id = ? AND COALESCE(is_current, 1) = 1",
                (now, reason, project_id, timeline_id),
            )
        connection.execute(
            """UPDATE exact_preview_renders SET state = 'obsolete', invalidated_at = ?,
               invalidated_reason = ?, updated_at = ?
               WHERE project_id = ? AND session_id = ? AND expected_revision < ?
               AND state IN ('pending', 'running', 'succeeded')""",
            (now, reason, now, project_id, source_session_id, source_session_revision),
        )

    def _timeline_file_path(self, *, project_id: str, timeline_id: str) -> Path:
        row = self._fetchone(
            project_id,
            """
            SELECT file_uri
            FROM timelines
            WHERE project_id = ? AND timeline_id = ?
            """,
            (project_id, timeline_id),
        )
        if row is None:
            raise KeyError(f"Timeline not found: {timeline_id}")
        file_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
        if not file_path.exists():
            raise KeyError(f"Timeline JSON missing: {timeline_id}")
        return file_path

    def _provider_trace_audit_log_path(self, *, project_id: str) -> Path:
        return self.project_root(project_id) / "logs" / "provider_trace_audit.jsonl"

    def _ensure_provider_trace_failed_runs_table(self, *, project_id: str) -> None:
        self._execute(
            project_id,
            """
            CREATE TABLE IF NOT EXISTS provider_trace_failed_runs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                source_job_id TEXT,
                artifact_id TEXT,
                timeline_id TEXT,
                error_message TEXT,
                provider_trace_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            )
            """,
            (),
        )

    def _save_failed_provider_trace_run(self, *, project_id: str, event: dict[str, Any]) -> None:
        self._ensure_provider_trace_failed_runs_table(project_id=project_id)
        provider_trace = event.get("provider_trace")
        self._execute(
            project_id,
            """
            INSERT OR REPLACE INTO provider_trace_failed_runs (
                job_id,
                project_id,
                job_type,
                source_job_id,
                artifact_id,
                timeline_id,
                error_message,
                provider_trace_json,
                created_at,
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.get("job_id") or ""),
                project_id,
                str(event.get("job_type") or event.get("artifact_type") or ""),
                str(event.get("source_job_id") or "") or None,
                str(event.get("artifact_id") or event.get("job_id") or ""),
                str(event.get("timeline_id") or "") or None,
                str(event.get("error_message") or ""),
                json.dumps(provider_trace, ensure_ascii=True) if isinstance(provider_trace, dict) else None,
                str(event.get("created_at") or self._now_iso()),
                str(event.get("finished_at") or ""),
            ),
        )

    def _list_provider_trace_failed_runs(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            try:
                rows = connection.execute(
                    """
                    SELECT
                        job_id,
                        project_id,
                        job_type,
                        source_job_id,
                        artifact_id,
                        timeline_id,
                        error_message,
                        provider_trace_json,
                        created_at,
                        finished_at
                    FROM provider_trace_failed_runs
                    ORDER BY created_at ASC, job_id ASC
                    """
                ).fetchall()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).lower():
                    return []
                raise
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_trace = payload.pop("provider_trace_json", None)
            try:
                decoded_trace = json.loads(raw_trace) if raw_trace else None
            except json.JSONDecodeError:
                decoded_trace = None
            payload["provider_trace"] = decoded_trace if isinstance(decoded_trace, dict) else None
            payload["artifact_type"] = str(payload.get("job_type") or "")
            items.append(payload)
        return items

    def _append_provider_trace_audit_event(self, *, project_id: str, event: dict[str, Any]) -> None:
        log_path = self._provider_trace_audit_log_path(project_id=project_id)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")

    def _list_provider_trace_audit_events(self, *, project_id: str) -> list[dict[str, Any]]:
        log_path = self._provider_trace_audit_log_path(project_id=project_id)
        if not log_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                events.append(decoded)
        return events

    def _next_provider_trace_event_sequence(self, *, project_id: str) -> int:
        return len(self._list_provider_trace_audit_events(project_id=project_id)) + 1

    def _list_timeline_ids(self, *, project_id: str) -> list[str]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT timeline_id
                FROM timelines
                WHERE project_id = ?
                ORDER BY created_at ASC, timeline_id ASC
                """,
                (project_id,),
            ).fetchall()
        finally:
            connection.close()
        return [str(row["timeline_id"]) for row in rows]

    def _merged_provider_trace(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        traces = [
            item.get("provider_trace")
            for item in items
            if isinstance(item.get("provider_trace"), dict)
        ]
        if not traces:
            return build_provider_trace(final_provider="heuristic_fallback")
        final_providers = {str(trace.get("final_provider") or "unknown") for trace in traces}
        fallback_reasons: list[str] = []
        for trace in traces:
            for reason in trace.get("fallback_reasons", []):
                text = str(reason).strip()
                if text and text not in fallback_reasons:
                    fallback_reasons.append(text)
        if len(final_providers) == 1:
            final_provider = next(iter(final_providers))
        else:
            final_provider = "mixed"
        return build_provider_trace(
            final_provider=final_provider,
            fallback_reasons=fallback_reasons,
            routing_mode=str(traces[0].get("routing_mode") or "local_only"),
        )

    def _provider_trace_entry(
        self,
        *,
        artifact_type: str,
        artifact_id: str,
        job_type: str | None,
        trace: dict[str, Any],
        job: dict[str, Any] | None = None,
        source_job_id: str | None = None,
        timeline_id: str | None = None,
        status: str | None = None,
        finished_at: str | None = None,
        created_at: str | None = None,
        error_message: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_job_id = job_id
        if resolved_job_id is None and job is not None:
            resolved_job_id = str(job.get("job_id") or "")
        resolved_job_type = job_type
        if resolved_job_type is None and job is not None:
            resolved_job_type = str(job.get("job_type") or "")
        resolved_source_job_id = source_job_id
        if resolved_source_job_id is None and job is not None:
            resolved_source_job_id = str(job.get("input_ref") or "")
        resolved_status = status
        if resolved_status is None and job is not None:
            resolved_status = str(job.get("status") or "")
        resolved_finished_at = finished_at
        if resolved_finished_at is None and job is not None:
            resolved_finished_at = str(job.get("finished_at") or "")
        resolved_error_message = error_message
        if resolved_error_message is None and job is not None:
            resolved_error_message = str(job.get("error_message") or "")
        return {
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "job_type": resolved_job_type,
            "job_id": resolved_job_id,
            "source_job_id": resolved_source_job_id,
            "timeline_id": timeline_id or None,
            "status": resolved_status or "available",
            "finished_at": resolved_finished_at,
            "created_at": created_at,
            "error_message": resolved_error_message,
            "provider_trace": trace,
        }

    def _provider_trace_summary(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        provider_counts: dict[str, int] = {}
        fallback_reason_counts: dict[str, int] = {}
        artifact_type_counts: dict[str, int] = {}
        fallback_entry_count = 0
        for entry in entries:
            artifact_type = str(entry["artifact_type"])
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1
            trace = entry["provider_trace"]
            final_provider = str(trace.get("final_provider") or "unknown")
            provider_counts[final_provider] = provider_counts.get(final_provider, 0) + 1
            reasons = [str(reason).strip() for reason in trace.get("fallback_reasons", []) if str(reason).strip()]
            if reasons:
                fallback_entry_count += 1
            for reason in reasons:
                fallback_reason_counts[reason] = fallback_reason_counts.get(reason, 0) + 1
        return {
            "total_entries": len(entries),
            "provider_counts": provider_counts,
            "fallback_entry_count": fallback_entry_count,
            "fallback_reason_counts": fallback_reason_counts,
            "artifact_type_counts": artifact_type_counts,
        }

    def _group_provider_trace_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        timeline_id: str | None,
        include_upstream: bool,
        upstream_segment_job_ids: set[str],
        upstream_recommendation_job_ids: set[str],
        use_exact_recommendation_lineage: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if timeline_id is None or not include_upstream:
            return entries, []

        direct_entries: list[dict[str, Any]] = []
        upstream_entries: list[dict[str, Any]] = []
        for entry in entries:
            entry_timeline_id = str(entry.get("timeline_id") or "")
            if entry_timeline_id == timeline_id:
                direct_entries.append(entry)
                continue
            if self._is_upstream_provider_trace_entry(
                entry,
                upstream_segment_job_ids=upstream_segment_job_ids,
                upstream_recommendation_job_ids=upstream_recommendation_job_ids,
                use_exact_recommendation_lineage=use_exact_recommendation_lineage,
            ):
                upstream_entries.append(entry)
                continue
            direct_entries.append(entry)
        return direct_entries, upstream_entries

    def _provider_trace_entry_matches_filters(
        self,
        entry: dict[str, Any],
        *,
        timeline_id: str | None = None,
        include_upstream: bool = False,
        upstream_segment_job_ids: set[str] | None = None,
        upstream_recommendation_job_ids: set[str] | None = None,
        use_exact_recommendation_lineage: bool = False,
        job_type: str | None = None,
        artifact_type: str | None = None,
        final_provider: str | None = None,
        fallback_reason: str | None = None,
    ) -> bool:
        if timeline_id is not None:
            entry_timeline_id = str(entry.get("timeline_id") or "")
            if entry_timeline_id != timeline_id:
                if not include_upstream or not self._is_upstream_provider_trace_entry(
                    entry,
                    upstream_segment_job_ids=upstream_segment_job_ids or set(),
                    upstream_recommendation_job_ids=upstream_recommendation_job_ids or set(),
                    use_exact_recommendation_lineage=use_exact_recommendation_lineage,
                ):
                    return False
        if job_type is not None and str(entry.get("job_type") or "") != job_type:
            return False
        if artifact_type is not None and str(entry.get("artifact_type") or "") != artifact_type:
            return False
        trace = entry.get("provider_trace")
        if not isinstance(trace, dict):
            return False
        if final_provider is not None and str(trace.get("final_provider") or "") != final_provider:
            return False
        if fallback_reason is not None:
            reasons = [str(reason).strip() for reason in trace.get("fallback_reasons", []) if str(reason).strip()]
            if fallback_reason not in reasons:
                return False
        return True

    def _normalized_provider_trace_filter_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def _is_upstream_provider_trace_entry(
        self,
        entry: dict[str, Any],
        *,
        upstream_segment_job_ids: set[str],
        upstream_recommendation_job_ids: set[str],
        use_exact_recommendation_lineage: bool,
    ) -> bool:
        if not upstream_segment_job_ids:
            return False
        entry_job_id = str(entry.get("job_id") or "")
        entry_source_job_id = str(entry.get("source_job_id") or "")
        if entry_job_id in upstream_segment_job_ids:
            return True
        if use_exact_recommendation_lineage:
            return entry_job_id in upstream_recommendation_job_ids
        return entry_source_job_id in upstream_segment_job_ids

    def _merge_provider_trace_failed_entries(
        self,
        primary: dict[str, Any],
        secondary: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(primary)
        for key in ("artifact_id", "job_type", "job_id", "source_job_id", "timeline_id", "status", "finished_at", "created_at", "error_message"):
            if not merged.get(key) and secondary.get(key):
                merged[key] = secondary[key]
        primary_trace = primary.get("provider_trace")
        secondary_trace = secondary.get("provider_trace")
        if self._is_missing_provider_trace(primary_trace) and isinstance(secondary_trace, dict):
            merged["provider_trace"] = secondary_trace
        return merged

    def _is_missing_provider_trace(self, trace: Any) -> bool:
        return isinstance(trace, dict) and trace == build_provider_trace(
            final_provider="unknown_failure",
            fallback_reasons=["missing_provider_trace"],
        )
