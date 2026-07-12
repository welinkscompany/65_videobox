from __future__ import annotations

import json
from copy import deepcopy
import re
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_domain_models.ai_providers import GeminiKeyStatus
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.projects import ProjectRecord
from videobox_domain_models.recommendations import RecommendationRecord, RecommendationType
from videobox_domain_models.transcripts import TranscriptRecord
from videobox_core_engine.provider_trace import build_provider_trace
from videobox_storage.sqlite_schema import PROJECT_SCHEMA_STATEMENTS

# Heavy exports (rendered mp4s, CapCut drafts) can be large; keep only the most
# recent N per export_type per project so disk usage does not grow unbounded.
DEFAULT_EXPORT_RETENTION_COUNT = 5


class EditingSessionRevisionConflict(RuntimeError):
    """The persisted editing-session revision did not match the requested CAS revision."""


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


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
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = Path(projects_root)

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

    def database_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "db" / "project.sqlite"

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
        shutil.copy2(resolved_source, destination_path)
        storage_uri = self._path_to_uri(project_id, destination_path)
        asset = AssetRecord.create(
            project_id=project_id,
            asset_type=asset_type,
            storage_uri=storage_uri,
        )
        self._execute(
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
        return self._write_editing_session(
            project_id=project_id,
            timeline_id=timeline_id,
            session_id=session_id,
            session_payload=session_payload,
            is_new=True,
        )

    def update_editing_session(
        self,
        *,
        project_id: str,
        session_id: str,
        session_payload: dict[str, Any],
        timeline_id: str | None = None,
        expected_revision: int | None = None,
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
        )

    def save_review_state(
        self,
        *,
        project_id: str,
        timeline_id: str,
        status: str,
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
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(timeline_id) DO UPDATE SET
                status = excluded.status,
                approved_at = excluded.approved_at,
                updated_at = excluded.updated_at
            """,
            (timeline_id, project_id, status, approved_at, updated_at),
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
            WHERE segment_id = ?
            ORDER BY created_at ASC, candidate_id ASC
            """,
            (segment_id,),
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
            WHERE candidate_id = ?
            """,
            (candidate_id,),
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
            "UPDATE tts_candidates SET operator_review_status = ? WHERE candidate_id = ?",
            (normalized_decision, candidate_id),
        )
        candidate["operator_review_status"] = normalized_decision
        return candidate

    def save_gemini_provider_key(
        self,
        *,
        project_id: str,
        label: str,
        api_key_secret: str,
        primary_model: str,
        cheap_model: str,
        high_quality_model: str,
    ) -> dict[str, Any]:
        if self._count_rows(project_id, "gemini_provider_keys") >= 10:
            raise ValueError("Gemini key pool supports at most 10 keys.")
        sequence = self._count_rows(project_id, "gemini_provider_keys") + 1
        key_id = f"gemini_key_{sequence:03d}"
        created_at = self._now_iso()
        self._execute(
            project_id,
            """
            INSERT INTO gemini_provider_keys (
                key_id,
                project_id,
                label,
                api_key_secret,
                primary_model,
                cheap_model,
                high_quality_model,
                status,
                cooldown_until,
                consecutive_failures,
                last_error,
                last_used_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key_id,
                project_id,
                label,
                api_key_secret,
                primary_model,
                cheap_model,
                high_quality_model,
                GeminiKeyStatus.ACTIVE.value,
                None,
                0,
                None,
                None,
                created_at,
                created_at,
            ),
        )
        return self.get_gemini_provider_key(project_id=project_id, key_id=key_id)

    def list_gemini_provider_keys(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT key_id, project_id, label, primary_model, cheap_model, high_quality_model,
                       status, cooldown_until, consecutive_failures, last_error, last_used_at,
                       created_at, updated_at, api_key_secret
                FROM gemini_provider_keys
                ORDER BY created_at ASC, key_id ASC
                """
            ).fetchall()
        finally:
            connection.close()
        return [self._serialize_gemini_provider_key(dict(row)) for row in rows]

    def list_gemini_provider_keys_with_secrets(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT key_id, project_id, label, primary_model, cheap_model, high_quality_model,
                       status, cooldown_until, consecutive_failures, last_error, last_used_at,
                       created_at, updated_at, api_key_secret
                FROM gemini_provider_keys
                ORDER BY created_at ASC, key_id ASC
                """
            ).fetchall()
        finally:
            connection.close()
        return [self._serialize_gemini_provider_key(dict(row), include_secret=True) for row in rows]

    def get_gemini_provider_key(
        self,
        *,
        project_id: str,
        key_id: str,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT key_id, project_id, label, primary_model, cheap_model, high_quality_model,
                   status, cooldown_until, consecutive_failures, last_error, last_used_at,
                   created_at, updated_at, api_key_secret
            FROM gemini_provider_keys
            WHERE key_id = ?
            """,
            (key_id,),
        )
        if row is None:
            raise KeyError(f"Gemini provider key not found: {key_id}")
        return self._serialize_gemini_provider_key(dict(row), include_secret=include_secret)

    def update_gemini_provider_key(
        self,
        *,
        project_id: str,
        key_id: str,
        label: str | None = None,
        primary_model: str | None = None,
        cheap_model: str | None = None,
        high_quality_model: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_gemini_provider_key(
            project_id=project_id,
            key_id=key_id,
            include_secret=True,
        )
        self._execute(
            project_id,
            """
            UPDATE gemini_provider_keys
            SET label = ?,
                primary_model = ?,
                cheap_model = ?,
                high_quality_model = ?,
                updated_at = ?
            WHERE key_id = ?
            """,
            (
                label or current["label"],
                primary_model or current["primary_model"],
                cheap_model or current["cheap_model"],
                high_quality_model or current["high_quality_model"],
                self._now_iso(),
                key_id,
            ),
        )
        return self.get_gemini_provider_key(project_id=project_id, key_id=key_id)

    def set_gemini_provider_key_status(
        self,
        *,
        project_id: str,
        key_id: str,
        status: str,
    ) -> dict[str, Any]:
        if status not in {item.value for item in GeminiKeyStatus}:
            raise ValueError(f"Unsupported Gemini key status: {status}")
        cooldown_until = None if status != GeminiKeyStatus.COOLDOWN.value else self._now_iso()
        self._execute(
            project_id,
            """
            UPDATE gemini_provider_keys
            SET status = ?,
                cooldown_until = ?,
                updated_at = ?
            WHERE key_id = ?
            """,
            (status, cooldown_until, self._now_iso(), key_id),
        )
        return self.get_gemini_provider_key(project_id=project_id, key_id=key_id)

    def update_gemini_provider_key_runtime_state(
        self,
        *,
        project_id: str,
        key_id: str,
        status: str,
        cooldown_until: str | None,
        consecutive_failures: int,
        last_error: str | None,
        last_used_at: str | None,
    ) -> dict[str, Any]:
        if status not in {item.value for item in GeminiKeyStatus}:
            raise ValueError(f"Unsupported Gemini key status: {status}")
        self._execute(
            project_id,
            """
            UPDATE gemini_provider_keys
            SET status = ?,
                cooldown_until = ?,
                consecutive_failures = ?,
                last_error = ?,
                last_used_at = ?,
                updated_at = ?
            WHERE key_id = ?
            """,
            (
                status,
                cooldown_until,
                consecutive_failures,
                last_error,
                last_used_at,
                self._now_iso(),
                key_id,
            ),
        )
        return self.get_gemini_provider_key(project_id=project_id, key_id=key_id)

    def get_review_state(self, *, project_id: str, timeline_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT timeline_id, project_id, status, approved_at, updated_at
            FROM review_approvals
            WHERE timeline_id = ?
            """,
            (timeline_id,),
        )
        if row is None:
            raise KeyError(f"Review state not found: {timeline_id}")
        payload = dict(row)
        payload["status"] = str(payload.get("status") or "").strip().lower()
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
        return {"subtitle_id": subtitle_id, "file_uri": file_uri, "subtitle": payload}

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
        return {"preview_id": preview_id, "file_uri": file_uri, "preview": payload}

    def _next_export_sequence(self, project_id: str) -> int:
        # All export types (capcut / final_render / capcut_draft_export) share one
        # `exports` table with a single export_id primary key, but each type is
        # written to its own subdirectory. Numbering per-subdirectory would let two
        # different export types both compute "export_001" and collide on insert,
        # so the sequence must be derived from the shared table, not a directory.
        rows = self._fetchall(project_id, "SELECT export_id FROM exports", ())
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
            WHERE export_type = ?
            ORDER BY created_at DESC
            """,
            (export_type,),
        )
        for row in rows[keep_last:]:
            artifact_path = self.resolve_storage_uri(project_id=project_id, storage_uri=str(row["file_uri"]))
            shutil.rmtree(artifact_path.parent, ignore_errors=True)
            self._execute(
                project_id,
                "DELETE FROM exports WHERE export_id = ?",
                (row["export_id"],),
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, created_at
            FROM exports
            WHERE export_id = ?
            """,
            (export_id,),
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
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at
            FROM exports
            WHERE export_id = ?
            """,
            (export_id,),
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
            "created_at": row["created_at"],
        }

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
            WHERE job_id = ?
            """,
            (status.value, output_ref, error_message, started_at, finished_at, finished_progress_percent, job_id),
        )
        return self.get_job(project_id=project_id, job_id=job_id)

    def update_job_progress(self, *, project_id: str, job_id: str, progress_percent: int) -> None:
        self._execute(
            project_id,
            "UPDATE jobs SET progress_percent = ? WHERE job_id = ?",
            (max(0, min(100, progress_percent)), job_id),
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
            WHERE job_id = ?
            """,
            (job_id,),
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
                ORDER BY rowid ASC
                """
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def update_asset_metadata(self, *, project_id: str, asset_id: str, metadata_patch: dict[str, Any]) -> dict[str, Any]:
        asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        merged_metadata = {**asset["metadata"], **metadata_patch}
        self._execute(
            project_id,
            "UPDATE assets SET metadata_json = ? WHERE asset_id = ?",
            (json.dumps(merged_metadata, ensure_ascii=True), asset_id),
        )
        return self.get_asset(project_id=project_id, asset_id=asset_id)

    def get_asset(self, *, project_id: str, asset_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE asset_id = ?
            """,
            (asset_id,),
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
            ORDER BY created_at ASC
            """
            params: tuple[Any, ...] = ()
        else:
            query = """
            SELECT asset_id, project_id, asset_type, storage_uri, source_kind, mime_type, duration_sec, metadata_json, created_at
            FROM assets
            WHERE asset_type = ?
            ORDER BY created_at ASC
            """
            params = (asset_type.value,)
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
                ORDER BY start_sec ASC, segment_id ASC
                """
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
                ORDER BY created_at ASC
                """
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
            WHERE transcript_id = ?
            """,
            (transcript_id,),
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
            WHERE segment_analysis_id = ?
            """,
            (segment_analysis_id,),
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
            WHERE timeline_id = ?
            """,
            (timeline_id,),
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
            SELECT preview_id, project_id, timeline_id, file_uri, status, summary_json, created_at
            FROM preview_renders
            WHERE preview_id = ?
            """,
            (preview_id,),
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
        return payload

    def get_subtitle_run(self, *, project_id: str, subtitle_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id, project_id, timeline_id, format, file_uri, status, summary_json, created_at
            FROM subtitle_renders
            WHERE subtitle_id = ?
            """,
            (subtitle_id,),
        )
        if row is None:
            raise KeyError(f"Subtitle not found: {subtitle_id}")
        payload = dict(row)
        summary = json.loads(payload.pop("summary_json") or "{}")
        payload["notes"] = summary.get("notes") or ["Subtitle file generated from approved review timeline."]
        payload["summary"] = summary
        return payload

    def get_export_run(self, *, project_id: str, export_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT export_id, project_id, timeline_id, export_type, file_uri, status, metadata_json, created_at
            FROM exports
            WHERE export_id = ?
            """,
            (export_id,),
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
        return payload

    def get_editing_session(self, *, project_id: str, session_id: str) -> dict[str, Any]:
        row = self._fetchone(
            project_id,
            """
            SELECT session_id, project_id, timeline_id, file_uri, summary_json, session_revision, session_json, created_at, updated_at
            FROM editing_sessions
            WHERE session_id = ?
            """,
            (session_id,),
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
            ORDER BY updated_at DESC, created_at DESC, session_id DESC
            LIMIT 1
            """,
            (),
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
        relative_parts = storage_uri.removeprefix(prefix).split("/")
        return self.project_root(project_id).joinpath(*relative_parts)

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
        connection = sqlite3.connect(self.database_path(project_id))
        # WAL lets readers proceed while a writer holds the lock, and
        # busy_timeout makes any remaining contention retry instead of
        # immediately raising "database is locked" — both matter once
        # background job threads (see run_*_job in local_pipeline.py) write
        # to the same per-project database concurrently with polling reads.
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        for statement in PROJECT_SCHEMA_STATEMENTS:
            connection.execute(statement)
        self._ensure_recommendation_decision_state_column(connection)
        self._ensure_job_progress_percent_column(connection)
        self._ensure_editing_session_revision_column(connection)
        self._ensure_editing_session_json_column(connection)
        self._ensure_tts_candidate_acceptance_columns(connection)
        connection.commit()
        connection.row_factory = sqlite3.Row
        return connection

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
            connection.execute("ALTER TABLE jobs ADD COLUMN progress_percent INTEGER")

    def _ensure_editing_session_revision_column(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(editing_sessions)").fetchall()
        }
        if "session_revision" not in existing_columns:
            connection.execute("ALTER TABLE editing_sessions ADD COLUMN session_revision INTEGER NOT NULL DEFAULT 1")

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
        row = self._fetchone(project_id, f"SELECT COUNT(*) AS count FROM {table_name}", ())
        return int(row["count"]) if row is not None else 0

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def get_latest_subtitle_for_timeline(self, *, project_id: str, timeline_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            project_id,
            """
            SELECT subtitle_id
            FROM subtitle_renders
            WHERE timeline_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (timeline_id,),
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

    def _serialize_gemini_provider_key(
        self,
        payload: dict[str, Any],
        *,
        include_secret: bool = False,
    ) -> dict[str, Any]:
        secret = str(payload.pop("api_key_secret"))
        payload["masked_api_key"] = self._mask_api_key(secret)
        if include_secret:
            payload["api_key_secret"] = secret
        return payload

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
                    SET summary_json = ?, session_revision = ?, session_json = ?, updated_at = ?
                    WHERE session_id = ? AND (? IS NULL OR session_revision = ?)
                    """,
                    (
                        summary_json,
                        payload["session_revision"],
                        serialized_payload,
                        updated_at,
                        session_id,
                        expected_revision,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise EditingSessionRevisionConflict("Editing session revision is stale.")
                connection.commit()
                temporary_path.write_text(serialized_payload, encoding="utf-8")
                temporary_path.replace(session_path)
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                if temporary_path.exists():
                    temporary_path.unlink()
                raise
            finally:
                connection.close()
        return self.get_editing_session(project_id=project_id, session_id=session_id)

    def _timeline_file_path(self, *, project_id: str, timeline_id: str) -> Path:
        row = self._fetchone(
            project_id,
            """
            SELECT file_uri
            FROM timelines
            WHERE timeline_id = ?
            """,
            (timeline_id,),
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
                ORDER BY created_at ASC, timeline_id ASC
                """
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
            routing_mode=str(traces[0].get("routing_mode") or "local_first"),
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
