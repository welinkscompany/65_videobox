from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from videobox_domain_models.assets import AssetType
from videobox_domain_models.recommendations import RecommendationType
from videobox_storage.local_project_store import LocalProjectStore


def test_register_broll_asset_persists_metadata(tmp_path: Path) -> None:
    source_broll = tmp_path / "desk-tour.mp4"
    source_broll.write_bytes(b"video bytes")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Broll Project")

    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source_broll,
        metadata={"title": "Desk tour", "tags": ["desk", "office"]},
    )

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT metadata_json FROM assets WHERE asset_id = ?",
            (asset.asset_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert json.loads(row[0])["title"] == "Desk tour"


def test_save_recommendation_run_persists_json_and_rows(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Recommendation Project")

    result = store.save_recommendation_run(
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
                "reason": "Matched collaboration keywords",
                "auto_apply_allowed": True,
                "review_required": False,
                "payload": {"tags": ["team", "meeting"]},
            },
        ],
    )

    json_path = (
        tmp_path / "projects" / project.project_id / "analysis" / "recommendations" / "broll_001.json"
    )
    assert json.loads(json_path.read_text(encoding="utf-8"))["recommendation_type"] == "broll"
    assert len(result["recommendations"]) == 2

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM recommendations WHERE recommendation_type = ?",
            (RecommendationType.BROLL.value,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert row_count == 2
