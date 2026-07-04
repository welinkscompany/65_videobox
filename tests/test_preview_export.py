from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from videobox_capcut_export import CapCutExportAdapter
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.recommendations import RecommendationType
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


def test_capcut_export_adapter_builds_structured_track_manifest_from_timeline_schema() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                },
                {
                    "track_id": "broll_overlay",
                    "track_type": "broll",
                    "clips": [
                        {
                            "clip_id": "clip_broll_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/asset_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "broll",
                            "recommendation_id": "broll_rec_001",
                        }
                    ],
                },
                {
                    "track_id": "music_bed",
                    "track_type": "bgm",
                    "clips": [
                        {
                            "clip_id": "clip_bgm_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/music/music_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "bgm",
                            "recommendation_id": "bgm_rec_001",
                        }
                    ],
                },
            ],
            "review_flags": [],
        },
        subtitle_file_uri="local://projects/project_123/subtitles/subtitle_001.srt",
    )

    assert payload["adapter"] == "capcut_v1_port"
    assert "spreadsheet_id" not in payload
    assert "draft_path" not in payload
    assert payload["tracks"][0]["track_id"] == "narration_primary"
    assert [track["track_name"] for track in payload["capcut_tracks"]] == [
        "voiceover",
        "broll",
        "subtitle",
        "bgm",
    ]
    assert payload["capcut_tracks"][0]["track_role"] == "audio"
    assert payload["capcut_tracks"][0]["segments"][0]["source_uri"].endswith("/inputs/narration/source.wav")
    assert payload["capcut_tracks"][1]["track_role"] == "video"
    assert payload["capcut_tracks"][1]["segments"][0]["recommendation_id"] == "broll_rec_001"
    assert payload["capcut_tracks"][2]["track_role"] == "text"
    assert payload["capcut_tracks"][2]["source_uri"].endswith(".srt")
    assert payload["capcut_tracks"][3]["track_role"] == "audio"


def test_capcut_export_adapter_maps_hook_title_overlay_metadata() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "export_overlays": [
                {
                    "overlay_type": "hook_title",
                    "text": "Start strong",
                    "start_sec": 0.0,
                    "end_sec": 1.5,
                }
            ],
            "review_flags": [],
        },
    )

    hook_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "hook_title")

    assert hook_track["track_role"] == "text"
    assert hook_track["segments"] == [
        {
            "overlay_type": "hook_title",
            "text": "Start strong",
            "start_sec": 0.0,
            "end_sec": 1.5,
        }
    ]


def test_capcut_export_adapter_sequentially_fills_broll_segment_windows() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "tracks": [
                {
                    "track_id": "broll_overlay",
                    "track_type": "broll",
                    "clips": [
                        {
                            "clip_id": "clip_broll_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/asset_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "broll",
                            "recommendation_id": "broll_rec_001",
                            "source_duration_sec": 0.75,
                        },
                        {
                            "clip_id": "clip_broll_002",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/asset_002",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "broll",
                            "recommendation_id": "broll_rec_002",
                            "source_duration_sec": 1.5,
                        },
                    ],
                }
            ],
            "review_flags": [],
        },
    )

    broll_segments = payload["capcut_tracks"][0]["segments"]

    assert payload["capcut_tracks"][0]["placement_mode"] == "sequential_fill"
    assert payload["capcut_tracks"][0]["allow_empty_gaps"] is True
    assert broll_segments[0]["planned_start_sec"] == 0.0
    assert broll_segments[0]["planned_end_sec"] == 0.75
    assert broll_segments[1]["planned_start_sec"] == 0.75
    assert broll_segments[1]["planned_end_sec"] == 2.0


def test_capcut_export_adapter_keeps_multiple_broll_clips_when_source_duration_metadata_is_missing() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "tracks": [
                {
                    "track_id": "broll_overlay",
                    "track_type": "broll",
                    "clips": [
                        {
                            "clip_id": "clip_broll_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/asset_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "broll",
                            "recommendation_id": "broll_rec_001",
                        },
                        {
                            "clip_id": "clip_broll_002",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/asset_002",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "broll",
                            "recommendation_id": "broll_rec_002",
                        },
                    ],
                }
            ],
            "review_flags": [],
        },
    )

    broll_segments = payload["capcut_tracks"][0]["segments"]

    assert len(broll_segments) == 2
    assert broll_segments[0]["planned_start_sec"] == 0.0
    assert broll_segments[0]["planned_end_sec"] == 1.0
    assert broll_segments[1]["planned_start_sec"] == 1.0
    assert broll_segments[1]["planned_end_sec"] == 2.0


def test_capcut_export_adapter_uses_segment_level_narration_sources_for_approved_tts_replacement() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": "local://projects/project_123/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                    {
                        "recommendation_id": "rec_tts_seg_001",
                        "target_segment_id": "seg_001",
                        "recommendation_type": "tts_replacement",
                        "selected_asset_id": "asset_tts_001",
                        "score": 1.0,
                        "reason": "Approved narration replacement.",
                        "auto_apply_allowed": True,
                        "review_required": False,
                        "payload": {
                            "selected_asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav"
                        },
                    }
                ],
                "pending_recommendations": [],
            },
        )

    voiceover_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "voiceover")

    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        "local://projects/project_123/assets/generated/asset_tts_001.wav",
        "local://projects/project_123/inputs/narration/source.wav",
    ]


def test_capcut_export_adapter_matches_trimmed_tts_recommendation_type_for_segment_level_narration_sources() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": "local://projects/project_123/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": " tts_replacement ",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved trimmed narration replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav"
                    },
                }
            ],
            "pending_recommendations": [],
        },
    )

    voiceover_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "voiceover")

    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        "local://projects/project_123/assets/generated/asset_tts_001.wav",
        "local://projects/project_123/inputs/narration/source.wav",
    ]


def test_capcut_export_adapter_matches_mixed_case_tts_recommendation_type_for_segment_level_narration_sources() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": "local://projects/project_123/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": " TTS_REPLACEMENT ",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved mixed-case narration replacement.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav"
                    },
                }
            ],
            "pending_recommendations": [],
        },
    )

    voiceover_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "voiceover")

    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        "local://projects/project_123/assets/generated/asset_tts_001.wav",
        "local://projects/project_123/inputs/narration/source.wav",
    ]


def test_capcut_export_adapter_matches_trimmed_tts_target_segment_id_for_segment_level_narration_sources() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": "local://projects/project_123/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": " seg_001 ",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved narration replacement with trimmed target segment id.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {
                        "selected_asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav"
                    },
                }
            ],
            "pending_recommendations": [],
        },
    )

    voiceover_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "voiceover")

    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        "local://projects/project_123/assets/generated/asset_tts_001.wav",
        "local://projects/project_123/inputs/narration/source.wav",
    ]


def test_capcut_export_adapter_treats_string_false_tts_review_required_as_false_for_segment_level_narration_sources() -> None:
    adapter = CapCutExportAdapter()

    payload = adapter.build_payload(
        project_id="project_123",
        timeline={
            "timeline_id": "timeline_001",
            "narration_source_uri": "local://projects/project_123/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": "local://projects/project_123/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_tts_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "tts_replacement",
                    "selected_asset_id": "asset_tts_001",
                    "score": 1.0,
                    "reason": "Approved narration replacement with legacy string false review_required.",
                    "auto_apply_allowed": "true",
                    "review_required": "false",
                    "payload": {
                        "selected_asset_uri": "local://projects/project_123/assets/generated/asset_tts_001.wav"
                    },
                }
            ],
            "pending_recommendations": [],
        },
    )

    voiceover_track = next(track for track in payload["capcut_tracks"] if track["track_name"] == "voiceover")

    assert [segment["source_uri"] for segment in voiceover_track["segments"]] == [
        "local://projects/project_123/assets/generated/asset_tts_001.wav",
        "local://projects/project_123/inputs/narration/source.wav",
    ]


class FailingPreviewRenderer:
    def build_preview_payload(self, *, project_id: str, timeline: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("preview renderer exploded")


class LegacyOutputOperatorCopyBuilder:
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, object],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> list[str]:
        del project_id, timeline, subtitle_file_uri
        if output_target == "capcut_export":
            return ["Legacy export copy."]
        return ["Legacy preview copy."]


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


def test_start_preview_render_accepts_legacy_list_only_output_copy_builder(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Output Copy Project")
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
    runner = LocalPipelineRunner(
        store,
        output_operator_copy_builder=LegacyOutputOperatorCopyBuilder(),
    )

    result = runner.start_preview_render(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
    )
    preview = runner.get_preview_result(project_id=project.project_id, job_id=result["job_id"])

    assert preview["preview"]["notes"] == ["Legacy preview copy."]
    assert preview["preview"]["provider_trace"]["final_provider"] == "static_fallback"


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


def test_provider_trace_backfill_tolerates_non_object_json_shapes(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Provider Trace Backfill Project")
    store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id="transcript_001",
        script_asset_id=None,
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )
    store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.8,
                "reason": "Matched keywords: office",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"matched_tags": ["office"]},
            }
        ],
    )
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE segments SET metadata_json = '[]'")
        connection.execute("UPDATE recommendations SET payload_json = 'null'")
        connection.execute(
            "UPDATE segment_analysis_runs SET segments_json = ?",
            (json.dumps([{"segment_id": "seg_001", "text": "Office overview.", "start_sec": 0.0, "end_sec": 1.0, "confidence": 0.99, "review_required": False, "cleanup_decision": "keep", "metadata": []}], ensure_ascii=True),),
        )
        connection.commit()
    finally:
        connection.close()

    segments = store.list_segments(project_id=project.project_id)
    recommendations = store.list_recommendation_rows(project_id=project.project_id)
    analysis = store.get_segment_analysis(project_id=project.project_id, segment_analysis_id="segment_analysis_001")

    assert segments[0]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert recommendations[0]["provider_trace"]["final_provider"] == "heuristic_fallback"
    assert analysis["segments"][0]["provider_trace"]["final_provider"] == "heuristic_fallback"


def test_recommendation_run_provider_trace_backfill_tolerates_non_object_payload(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Recommendation Trace Backfill Project")
    run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.8,
                "reason": "Matched keywords: office",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"matched_tags": ["office"]},
            }
        ],
    )
    run_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "analysis"
        / "recommendations"
        / f"{run['recommendation_run_id']}.json"
    )
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["recommendations"][0]["payload"] = None
    run_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    loaded_run = store.get_recommendation_run(
        project_id=project.project_id,
        recommendation_run_id=run["recommendation_run_id"],
        recommendation_type=RecommendationType.BROLL,
    )

    assert loaded_run["recommendations"][0]["provider_trace"]["final_provider"] == "heuristic_fallback"


def test_recommendation_run_accepts_mixed_case_recommendation_type(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Recommendation Mixed Case Type Project")
    run = store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.8,
                "reason": "Matched keywords: office",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"matched_tags": ["office"]},
            }
        ],
    )
    run_path = (
        tmp_path
        / "projects"
        / project.project_id
        / "analysis"
        / "recommendations"
        / f"{run['recommendation_run_id']}.json"
    )
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["recommendation_type"] = " BROLL "
    run_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    loaded_run = store.get_recommendation_run(
        project_id=project.project_id,
        recommendation_run_id=run["recommendation_run_id"],
        recommendation_type=RecommendationType.BROLL,
    )

    assert loaded_run["recommendation_type"] == "broll"
    assert loaded_run["recommendations"][0]["provider_trace"]["final_provider"] == "heuristic_fallback"
