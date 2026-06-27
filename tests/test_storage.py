from __future__ import annotations

import sqlite3
from pathlib import Path

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
