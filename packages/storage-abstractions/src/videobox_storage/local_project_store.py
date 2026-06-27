from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.projects import ProjectRecord
from videobox_domain_models.transcripts import TranscriptRecord
from videobox_storage.sqlite_schema import PROJECT_SCHEMA_STATEMENTS


class LocalProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = Path(projects_root)

    def bootstrap_project(self, name: str) -> ProjectRecord:
        project = ProjectRecord.create(name=name)
        project_root = self.project_root(project.project_id)
        self._create_project_layout(project_root)
        self._bootstrap_database(project_root / "db" / "project.sqlite", project)
        return project

    def project_root(self, project_id: str) -> Path:
        return self.projects_root / "projects" / project_id

    def database_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "db" / "project.sqlite"

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
        sequence = self._next_sequence(self.project_root(project_id) / "analysis" / "transcripts", "transcript_*.json")
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
        sequence = self._next_sequence(self.project_root(project_id) / "analysis" / "segments", "segment_analysis_*.json")
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
                    1 if segment.get("review_required") else 0,
                    json.dumps(
                        {
                            "transcript_id": transcript_id,
                            "script_asset_id": script_asset_id,
                        },
                        ensure_ascii=True,
                    ),
                ),
            )
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
                finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        self._execute(
            project_id,
            """
            UPDATE jobs
            SET status = ?,
                output_ref = COALESCE(?, output_ref),
                error_message = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = COALESCE(?, finished_at)
            WHERE job_id = ?
            """,
            (status.value, output_ref, error_message, started_at, finished_at, job_id),
        )
        return self.get_job(project_id=project_id, job_id=job_id)

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
                finished_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        )
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return dict(row)

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
        return payload

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
            project_root / "timelines",
            project_root / "previews",
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
        }
        return mapping.get(asset_type, Path("assets") / "imported")

    def _path_to_uri(self, project_id: str, path: Path) -> str:
        relative_path = path.relative_to(self.project_root(project_id)).as_posix()
        return f"local://projects/{project_id}/{relative_path}"

    def _next_sequence(self, directory: Path, pattern: str) -> int:
        return len(list(directory.glob(pattern))) + 1

    def _connection(self, project_id: str) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path(project_id))
        connection.row_factory = sqlite3.Row
        return connection

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

    def _count_rows(self, project_id: str, table_name: str) -> int:
        row = self._fetchone(project_id, f"SELECT COUNT(*) AS count FROM {table_name}", ())
        return int(row["count"]) if row is not None else 0

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()
