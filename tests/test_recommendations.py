from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path

import pytest

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


def test_rule_based_music_recommender_ignores_string_false_segment_review_required() -> None:
    from videobox_core_engine.recommenders import RuleBasedMusicRecommender
    from videobox_provider_interfaces.recommenders import RecommendationRequest

    recommender = RuleBasedMusicRecommender()

    candidates = recommender.recommend(
        RecommendationRequest(
            project_id="project_001",
            recommendation_type=RecommendationType.BGM,
            segments=[
                {
                    "segment_id": "seg_001",
                    "text": "Quarterly finance summary",
                    "review_required": "false",
                }
            ],
            assets=[],
        )
    )

    assert candidates[0].reason == "Suggested music mood for this segment: focused corporate."
    assert candidates[0].score == 0.66


def test_local_only_recommenders_are_exposed_without_local_first_aliases() -> None:
    from videobox_core_engine import LocalOnlyKeywordBrollRecommender, LocalOnlyMusicRecommender

    assert LocalOnlyKeywordBrollRecommender.__name__ == "LocalOnlyKeywordBrollRecommender"
    assert LocalOnlyMusicRecommender.__name__ == "LocalOnlyMusicRecommender"


@pytest.mark.parametrize(
    "legacy_name",
    ("LocalFirstKeywordBrollRecommender", "LocalFirstMusicRecommender"),
)
def test_legacy_local_first_recommender_exports_are_rejected_without_alias(legacy_name: str) -> None:
    core_engine = importlib.import_module("videobox_core_engine")

    with pytest.raises(AttributeError, match=rf"^module 'videobox_core_engine' has no attribute '{legacy_name}'$"):
        getattr(core_engine, legacy_name)
