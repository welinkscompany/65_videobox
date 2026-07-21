from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore


def test_bootstrap_project_creates_expected_layout(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Local First Project")

    project_root = tmp_path / "projects" / project.project_id
    assert project_root.exists()
    assert (project_root / "db" / "project.sqlite").exists()
    assert (project_root / "inputs" / "narration").exists()
    assert (project_root / "inputs" / "raw_video").exists()
    assert (project_root / "inputs" / "scripts").exists()
    assert (project_root / "inputs" / "voice_samples").exists()
    assert (project_root / "assets" / "imported").exists()
    assert (project_root / "assets" / "generated").exists()
    assert (project_root / "analysis" / "transcripts").exists()
    assert (project_root / "analysis" / "segments").exists()
    assert (project_root / "analysis" / "recommendations").exists()
    assert (project_root / "timelines").exists()
    assert (project_root / "previews").exists()
    assert (project_root / "exports" / "capcut").exists()
    assert (project_root / "cache").exists()
    assert (project_root / "logs").exists()


def test_bootstrap_project_creates_sqlite_tables(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Schema Check")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    connection = sqlite3.connect(database_path)
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "projects",
        "assets",
        "segments",
        "recommendations",
        "jobs",
        "timelines",
        "exports",
        "voice_samples",
    }.issubset(table_names)


def test_connection_initialization_failure_closes_the_open_sqlite_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Connection Cleanup")
    from videobox_storage import local_project_store

    original_connect = local_project_store.sqlite3.connect

    class _FailingSetupConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.connection = connection
            self.closed = False

        def execute(self, statement: str, *args: object, **kwargs: object):
            if statement == "PRAGMA busy_timeout=5000":
                raise sqlite3.OperationalError("injected setup failure")
            return self.connection.execute(statement, *args, **kwargs)

        def close(self) -> None:
            self.closed = True
            self.connection.close()

    wrappers: list[_FailingSetupConnection] = []

    def failing_connect(*args: object, **kwargs: object) -> _FailingSetupConnection:
        connection = original_connect(*args, **kwargs)
        wrapper = _FailingSetupConnection(connection)
        wrappers.append(wrapper)
        return wrapper

    monkeypatch.setattr(local_project_store.sqlite3, "connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError, match="injected setup failure"):
        store._connection(project.project_id)

    assert len(wrappers) == 1 and wrappers[0].closed is True


def test_save_timeline_run_summary_ignores_unknown_review_flag_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [
                {
                    "code": "legacy_review_required",
                    "segment_id": "seg_legacy",
                    "message": "Legacy blocker that should not count.",
                },
                {
                    "code": "segment_review_required",
                    "segment_id": "seg_001",
                    "message": "Canonical blocker that should count.",
                },
            ],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["review_flag_count"] == 1


def test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Pending Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_unknown_pending",
                    "target_segment_id": "seg_legacy",
                    "recommendation_type": "legacy_overlay_pick",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                }
            ],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["pending_recommendation_count"] == 0


def test_save_timeline_run_summary_ignores_unknown_track_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Track Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clips": [{"clip_id": "clip_legacy_001"}],
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001"}],
                },
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["track_count"] == 1


def test_save_timeline_run_summary_ignores_unknown_applied_recommendation_count(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Applied Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_unknown_applied",
                    "target_segment_id": "seg_legacy",
                    "recommendation_type": "legacy_overlay_pick",
                    "selected_asset_id": "asset_legacy_001",
                    "score": 0.5,
                    "reason": "Unknown applied recommendation should not count.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                },
                {
                    "recommendation_id": "rec_broll_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "broll",
                    "selected_asset_id": "asset_broll_001",
                    "score": 0.91,
                    "reason": "Canonical applied recommendation should count.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                },
            ],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["applied_recommendation_count"] == 1


def test_save_capcut_export_metadata_ignores_unknown_track_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Export Metadata Count Project")

    saved = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id="timeline_001",
        export_payload={
            "adapter": "capcut",
            "tracks": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clips": [{"clip_id": "clip_legacy_001"}],
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001"}],
                },
            ],
        },
    )

    fetched = store.get_export_run(
        project_id=project.project_id,
        export_id=saved["export_id"],
    )

    assert fetched["metadata"]["track_count"] == 1


def test_save_preview_run_summary_ignores_unknown_track_clip_group_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Preview Summary Count Project")

    saved = store.save_preview_run(
        project_id=project.project_id,
        timeline_id="timeline_001",
        preview_payload={
            "timeline_id": "timeline_001",
            "artifact_kind": "playable_html_preview",
            "clips": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clip_count": 1,
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clip_count": 1,
                },
            ],
            "player_html": "<html></html>",
        },
    )

    fetched = store.get_preview_run(
        project_id=project.project_id,
        preview_id=saved["preview_id"],
    )

    assert fetched["summary"]["clip_group_count"] == 1
