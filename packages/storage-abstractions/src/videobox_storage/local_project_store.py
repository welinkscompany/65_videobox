from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_domain_models.ai_providers import GeminiKeyStatus
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.projects import ProjectRecord
from videobox_domain_models.recommendations import RecommendationRecord, RecommendationType
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

    def project_root(self, project_id: str) -> Path:
        return self.projects_root / "projects" / project_id

    def database_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "db" / "project.sqlite"

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
                "auto_apply_allowed": bool(item.get("auto_apply_allowed", record.auto_apply_allowed)),
                "review_required": bool(item.get("review_required", record.review_required)),
                "payload": item.get("payload", record.payload or {}),
                "created_at": record.created_at.isoformat(),
            }
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
                    payload_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        summary_json = json.dumps(
            {
                "track_count": len(payload.get("tracks", [])),
                "review_flag_count": len(payload.get("review_flags", [])),
                "applied_recommendation_count": len(payload.get("applied_recommendations", [])),
                "pending_recommendation_count": len(payload.get("pending_recommendations", [])),
            },
            ensure_ascii=True,
        )
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
        initial_review_status = (
            "blocked"
            if payload.get("review_flags") or payload.get("pending_recommendations")
            else "draft"
        )
        self.save_review_state(
            project_id=project_id,
            timeline_id=timeline_id,
            status=initial_review_status,
        )
        return {"timeline_id": timeline_id, "file_uri": file_uri, "timeline": payload}

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
        return self.get_review_state(project_id=project_id, timeline_id=timeline_id)

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
        return dict(row)

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
            {"entry_count": len(entries)},
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
                "clip_group_count": len(payload.get("clips", [])),
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

    def save_capcut_export(
        self,
        *,
        project_id: str,
        timeline_id: str,
        export_payload: dict[str, Any],
    ) -> dict[str, Any]:
        sequence = self._next_sequence(
            self.project_root(project_id) / "exports" / "capcut",
            "export_*",
        )
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
        if not existing_notes or not existing_notes[0].lower().startswith("mock capcut"):
            payload["notes"] = [
                "Mock CapCut payload for local post-editing handoff.",
                *existing_notes,
            ]
        else:
            payload["notes"] = existing_notes
        payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        notes_path.write_text(
            "Mock CapCut export payload generated from timeline JSON.\n"
            "This is a local handoff artifact for post-editing.\n",
            encoding="utf-8",
        )
        metadata_json = json.dumps(
            {
                "timeline_id": timeline_id,
                "adapter": payload.get("adapter"),
                "track_count": len(payload.get("tracks", [])),
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
        return {"export_id": export_id, "file_uri": file_uri, "export": payload}

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
                    finished_at
                FROM jobs
                ORDER BY rowid ASC
                """
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

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
            payload["review_required"] = bool(payload["review_required"])
            payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
            items.append(payload)
        return items

    def list_recommendation_rows(self, *, project_id: str) -> list[dict[str, Any]]:
        connection = self._connection(project_id)
        try:
            rows = connection.execute(
                """
                SELECT recommendation_id, project_id, target_segment_id, recommendation_type,
                       selected_asset_id, score, reason, auto_apply_allowed,
                       review_required, payload_json, created_at
                FROM recommendations
                ORDER BY created_at ASC
                """
            ).fetchall()
        finally:
            connection.close()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["auto_apply_allowed"] = bool(payload["auto_apply_allowed"])
            payload["review_required"] = bool(payload["review_required"])
            payload["payload"] = json.loads(payload.pop("payload_json") or "{}")
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
        if payload["recommendation_type"] != recommendation_type.value:
            raise KeyError(f"Recommendation run type mismatch: {recommendation_run_id}")
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
        payload["summary"] = json.loads(row["summary_json"] or "{}")
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
        payload["notes"] = ["Subtitle file generated from approved review timeline."]
        payload["summary"] = json.loads(payload.pop("summary_json") or "{}")
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
        payload["metadata"] = json.loads(row["metadata_json"] or "{}")
        return payload

    def build_review_snapshot(
        self,
        *,
        project_id: str,
        timeline_id: str | None = None,
        segments: list[dict[str, Any]],
        recommendations: list[dict[str, Any]],
        timeline_review_flags: list[dict[str, Any]],
    ) -> dict[str, Any]:
        applied = [
            item for item in recommendations
            if bool(item.get("auto_apply_allowed")) and not bool(item.get("review_required"))
        ]
        pending = [
            item for item in recommendations
            if not (bool(item.get("auto_apply_allowed")) and not bool(item.get("review_required")))
        ]
        if timeline_id:
            try:
                review_status = self.get_review_state(
                    project_id=project_id,
                    timeline_id=str(timeline_id),
                )["status"]
            except KeyError:
                review_status = "blocked" if timeline_review_flags or pending else "draft"
        else:
            review_status = "blocked"
        return {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "review_status": review_status,
            "segments": segments,
            "applied_recommendations": applied,
            "pending_recommendations": pending,
            "review_flags": timeline_review_flags,
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
