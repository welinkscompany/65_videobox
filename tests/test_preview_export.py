from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def test_save_preview_run_persists_artifacts_and_index(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Preview Project")

    result = store.save_preview_run(
        project_id=project.project_id,
        timeline_id="timeline_001",
        preview_payload={
            "timeline_id": "timeline_001",
            "artifact_kind": "mock_preview_bundle",
            "clips": [{"clip_id": "clip_001", "segment_id": "seg_001"}],
            "notes": ["Preview render is a structured local artifact in this phase."],
        },
    )

    manifest_path = tmp_path / "projects" / project.project_id / "previews" / "preview_001.json"
    assert manifest_path.exists()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["timeline_id"] == "timeline_001"
    assert result["preview_id"] == "preview_001"

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT file_uri, timeline_id, status FROM preview_renders WHERE preview_id = ?",
            (result["preview_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[1] == "timeline_001"
    assert row[2] == "succeeded"


def test_save_capcut_export_persists_payload_and_index(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Export Project")

    result = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id="timeline_001",
        export_payload={
            "timeline_id": "timeline_001",
            "adapter": "capcut_v1",
            "tracks": [{"track_id": "narration_primary", "track_type": "narration"}],
            "notes": ["CapCut remains an export target, not the internal source of truth."],
        },
    )

    export_manifest = (
        tmp_path
        / "projects"
        / project.project_id
        / "exports"
        / "capcut"
        / "export_001"
        / "capcut_payload.json"
    )
    assert export_manifest.exists()
    payload = json.loads(export_manifest.read_text(encoding="utf-8"))
    assert payload["timeline_id"] == "timeline_001"
    assert result["export_id"] == "export_001"

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT file_uri, timeline_id, status FROM exports WHERE export_id = ?",
            (result["export_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[1] == "timeline_001"
    assert row[2] == "succeeded"
    assert payload["notes"] == [
        "CapCut remains an export target, not the internal source of truth."
    ]
    readme_path = export_manifest.parent / "README.txt"
    assert readme_path.read_text(encoding="utf-8").strip() == payload["notes"][0]


class FailingPreviewRenderer:
    def build_preview_payload(self, *, project_id: str, timeline: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("preview renderer exploded")


def test_start_preview_render_marks_job_failed_when_renderer_errors(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Preview Failure Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(store, preview_renderer=FailingPreviewRenderer())

    with pytest.raises(RuntimeError, match="preview renderer exploded"):
        runner.start_preview_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    jobs = store.list_jobs(project_id=project.project_id)
    preview_job = jobs[-1]
    assert preview_job["job_type"] == JobType.PREVIEW_RENDER.value
    assert preview_job["status"] == JobStatus.FAILED.value
    assert preview_job["error_message"] == "preview renderer exploded"


def test_save_review_state_and_subtitle_run_persist_records(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review State Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )

    review_state = store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="draft",
    )
    approved_state = store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    subtitle = store.save_subtitle_run(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        subtitle_payload={
            "format": "srt",
            "entries": [
                {"index": 1, "start_sec": 0.0, "end_sec": 1.2, "text": "Office overview."},
            ],
            "notes": ["Subtitle file generated from reviewed timeline segments."],
        },
    )

    review_state_row = store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
    )
    subtitle_row = store.get_subtitle_run(
        project_id=project.project_id,
        subtitle_id=subtitle["subtitle_id"],
    )

    assert review_state["status"] == "draft"
    assert approved_state["status"] == "approved"
    assert review_state_row["status"] == "approved"
    assert subtitle_row["timeline_id"] == timeline["timeline_id"]
    assert subtitle_row["format"] == "srt"
    assert subtitle_row["file_uri"].endswith(".srt")
    assert subtitle_row["notes"] == ["Subtitle file generated from reviewed timeline segments."]


def test_save_capcut_export_preserves_invariant_note_with_ai_copy(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Export Guidance Project")

    result = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id="timeline_001",
        export_payload={
            "timeline_id": "timeline_001",
            "adapter": "capcut_v1",
            "tracks": [{"track_id": "narration_primary", "track_type": "narration"}],
            "notes": [
                "Export operator copy from local runtime.",
                "Open the CapCut payload and confirm subtitle attachment.",
            ],
        },
    )

    export_manifest = (
        tmp_path
        / "projects"
        / project.project_id
        / "exports"
        / "capcut"
        / result["export_id"]
        / "capcut_payload.json"
    )
    payload = json.loads(export_manifest.read_text(encoding="utf-8"))

    assert payload["notes"] == [
        "Export operator copy from local runtime.",
        "Open the CapCut payload and confirm subtitle attachment.",
        "CapCut remains an export target, not the internal source of truth.",
    ]


def test_start_subtitle_render_uses_only_segments_from_the_approved_timeline(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Scoped Subtitle Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Timeline line one.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            },
            {
                "segment_id": "seg_999",
                "text": "Stale line that should not ship.",
                "start_sec": 9.0,
                "end_sec": 10.0,
                "confidence": 0.91,
                "review_required": False,
                "cleanup_decision": "keep",
            },
        ],
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://assets/narration.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                            "recommendation_id": None,
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    runner = LocalPipelineRunner(store)

    subtitle_job = runner.start_subtitle_render(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
    )
    subtitle_result = runner.get_subtitle_result(
        project_id=project.project_id,
        job_id=subtitle_job["job_id"],
    )

    subtitle_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=subtitle_result["subtitle"]["file_uri"],
    )
    subtitle_text = subtitle_path.read_text(encoding="utf-8")

    assert "Timeline line one." in subtitle_text
    assert "Stale line that should not ship." not in subtitle_text
