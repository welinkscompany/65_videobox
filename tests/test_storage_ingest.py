from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def test_register_asset_copies_source_and_persists_asset_record(tmp_path: Path) -> None:
    source_audio = tmp_path / "take-01.wav"
    source_audio.write_bytes(b"audio bytes")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Ingest Project")

    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=source_audio,
    )

    copied_file = (
        tmp_path / "projects" / project.project_id / "inputs" / "narration" / source_audio.name
    )
    assert copied_file.read_bytes() == b"audio bytes"
    assert asset.storage_uri.endswith(f"/inputs/narration/{source_audio.name}")

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT asset_type, storage_uri FROM assets WHERE asset_id = ?",
            (asset.asset_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row == (AssetType.NARRATION_AUDIO.value, asset.storage_uri)


def test_persist_transcript_and_segments_write_json_artifacts(tmp_path: Path) -> None:
    source_audio = tmp_path / "take-01.wav"
    source_audio.write_bytes(b"audio bytes")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Analysis Project")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=source_audio,
    )

    transcript = store.save_transcript(
        project_id=project.project_id,
        source_asset_id=asset.asset_id,
        transcript_text="Line one. Line two restart.",
        segments=[
            {"start_sec": 0.0, "end_sec": 1.0, "text": "Line one."},
            {"start_sec": 1.0, "end_sec": 2.1, "text": "Line two restart."},
        ],
    )
    segment_run = store.save_segment_analysis(
        project_id=project.project_id,
        transcript_id=transcript["transcript_id"],
        script_asset_id=None,
        segments=[
            {
                "text": "Line one.",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "confidence": 0.99,
                "review_required": False,
                "cleanup_decision": "keep",
            },
            {
                "text": "Line two restart.",
                "start_sec": 1.0,
                "end_sec": 2.1,
                "confidence": 0.7,
                "review_required": True,
                "cleanup_decision": "review",
            },
        ],
    )

    transcript_path = (
        tmp_path / "projects" / project.project_id / "analysis" / "transcripts" / "transcript_001.json"
    )
    segment_path = (
        tmp_path / "projects" / project.project_id / "analysis" / "segments" / "segment_analysis_001.json"
    )
    assert json.loads(transcript_path.read_text(encoding="utf-8"))["source_asset_id"] == asset.asset_id
    assert json.loads(segment_path.read_text(encoding="utf-8"))["transcript_id"] == transcript["transcript_id"]
    assert len(segment_run["segments"]) == 2

    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        segment_count = connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    finally:
        connection.close()

    assert segment_count == 2
