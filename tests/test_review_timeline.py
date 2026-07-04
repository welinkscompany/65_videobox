from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from videobox_domain_models.recommendations import RecommendationType
from videobox_storage.local_project_store import LocalProjectStore


def test_save_timeline_run_persists_json_and_index(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Project")

    result = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [{"track_id": "narration_primary", "clips": []}],
            "review_flags": [{"code": "segment_review_required", "segment_id": "seg_001", "message": "Needs review"}],
        },
    )

    timeline_path = (
        tmp_path / "projects" / project.project_id / "timelines" / "timeline_001.json"
    )
    assert json.loads(timeline_path.read_text(encoding="utf-8"))["project_id"] == project.project_id
    assert result["timeline_id"] == "timeline_001"

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT file_uri, output_mode FROM timelines WHERE timeline_id = ?",
            (result["timeline_id"],),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[1] == "review"


def test_review_snapshot_splits_applied_and_pending_recommendations(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Project")
    store.save_recommendation_run(
        project_id=project.project_id,
        recommendation_type=RecommendationType.BROLL,
        source_job_id="segment_analysis_job_001",
        recommendations=[
            {
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.92,
                "reason": "Matched office overview keywords",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["office", "overview"]},
            },
            {
                "target_segment_id": "seg_002",
                "selected_asset_id": "asset_002",
                "score": 0.71,
                "reason": "Needs manual pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {"tags": ["team", "meeting"]},
            },
        ],
    )

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id="timeline_001",
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Office overview",
                "review_required": False,
                "cleanup_decision": "keep",
            },
            {
                "segment_id": "seg_002",
                "text": "Team meeting restart",
                "review_required": True,
                "cleanup_decision": "review",
            },
        ],
        recommendations=[
            {
                "recommendation_id": "rec_001",
                "target_segment_id": "seg_001",
                "selected_asset_id": "asset_001",
                "score": 0.92,
                "reason": "Matched office overview keywords",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["office", "overview"]},
            },
            {
                "recommendation_id": "rec_002",
                "target_segment_id": "seg_002",
                "selected_asset_id": "asset_002",
                "score": 0.71,
                "reason": "Needs manual pick",
                "auto_apply_allowed": False,
                "review_required": True,
                "payload": {"tags": ["team", "meeting"]},
            },
        ],
        timeline_review_flags=[
            {"code": "segment_review_required", "segment_id": "seg_002", "message": "Needs review"},
            {"code": "broll_review_required", "segment_id": "seg_002", "message": "Needs manual pick"},
        ],
    )

    assert len(snapshot["applied_recommendations"]) == 1
    assert len(snapshot["pending_recommendations"]) == 1
    assert len(snapshot["review_flags"]) == 2
    assert snapshot["timeline_id"] == "timeline_001"


def test_review_snapshot_uses_trimmed_broll_type_for_default_provider_trace(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Review Snapshot Trimmed Trace Project")

    snapshot = store.build_review_snapshot(
        project_id=project.project_id,
        timeline_id="timeline_001",
        segments=[],
        recommendations=[
            {
                "recommendation_id": "rec_trimmed_broll_trace",
                "target_segment_id": "seg_001",
                "recommendation_type": " broll ",
                "selected_asset_id": "asset_001",
                "score": 0.92,
                "reason": "Trimmed B-roll type should still keep heuristic fallback.",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["office"]},
            }
        ],
        timeline_review_flags=[],
    )

    assert snapshot["applied_recommendations"][0]["provider_trace"]["final_provider"] == "heuristic_fallback"
