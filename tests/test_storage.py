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
        "gemini_provider_keys",
    }.issubset(table_names)


def test_gemini_key_pool_persistence_round_trip_masks_secrets_and_limits_key_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Gemini Key Project")

    saved = store.save_gemini_provider_key(
        project_id=project.project_id,
        label="Primary Gemini",
        api_key_secret="AIza-sample-secret-1234",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )

    assert saved["masked_api_key"].startswith("AIza")
    assert "secret" not in saved["masked_api_key"]
    assert "api_key_secret" not in saved

    fetched = store.get_gemini_provider_key(project_id=project.project_id, key_id=saved["key_id"])
    assert fetched["key_id"] == saved["key_id"]
    assert fetched["label"] == "Primary Gemini"
    assert fetched["status"] == "active"
    assert fetched["primary_model"] == "gemini-2.5-flash"
    assert "api_key_secret" not in fetched

    with_secret = store.get_gemini_provider_key(
        project_id=project.project_id,
        key_id=saved["key_id"],
        include_secret=True,
    )
    assert with_secret["api_key_secret"] == "AIza-sample-secret-1234"

    for index in range(2, 11):
        store.save_gemini_provider_key(
            project_id=project.project_id,
            label=f"Gemini {index}",
            api_key_secret=f"AIza-sample-secret-{index}",
            primary_model="gemini-2.5-flash",
            cheap_model="gemini-2.5-flash-lite",
            high_quality_model="gemini-2.5-pro",
        )

    try:
        store.save_gemini_provider_key(
            project_id=project.project_id,
            label="Gemini 11",
            api_key_secret="AIza-over-limit",
            primary_model="gemini-2.5-flash",
            cheap_model="gemini-2.5-flash-lite",
            high_quality_model="gemini-2.5-pro",
        )
    except ValueError as exc:
        assert "10" in str(exc)
    else:
        raise AssertionError("Expected Gemini provider key limit to be enforced")


def test_gemini_key_state_updates_persist_for_dashboard_visibility(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Gemini State Project")
    saved = store.save_gemini_provider_key(
        project_id=project.project_id,
        label="Primary Gemini",
        api_key_secret="AIza-sample-secret-1234",
        primary_model="gemini-2.5-flash",
        cheap_model="gemini-2.5-flash-lite",
        high_quality_model="gemini-2.5-pro",
    )

    updated = store.update_gemini_provider_key(
        project_id=project.project_id,
        key_id=saved["key_id"],
        label="Primary Gemini Updated",
        cheap_model="gemini-2.5-flash",
    )
    assert updated["label"] == "Primary Gemini Updated"
    assert updated["cheap_model"] == "gemini-2.5-flash"

    disabled = store.set_gemini_provider_key_status(
        project_id=project.project_id,
        key_id=saved["key_id"],
        status="disabled",
    )
    assert disabled["status"] == "disabled"

    enabled = store.set_gemini_provider_key_status(
        project_id=project.project_id,
        key_id=saved["key_id"],
        status="active",
    )
    assert enabled["status"] == "active"

    listed = store.list_gemini_provider_keys(project_id=project.project_id)
    assert listed[0]["key_id"] == saved["key_id"]
    assert listed[0]["label"] == "Primary Gemini Updated"
    assert "api_key_secret" not in listed[0]
