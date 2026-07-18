from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.postgres_project_store import PostgresProjectStore


@pytest.fixture
def postgres_url() -> str:
    value = os.environ.get("VIDEOBOX_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set VIDEOBOX_TEST_POSTGRES_URL to run PostgreSQL store integration tests")
    return value


def test_postgres_store_bootstraps_and_lists_a_project(tmp_path: Path, postgres_url: str) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)

    project = store.bootstrap_project(f"Postgres project {uuid4().hex}")

    assert next(item for item in store.list_projects() if item["project_id"] == project.project_id) == {
        "project_id": project.project_id,
        "name": project.name,
        "status": "draft",
        "root_storage_uri": f"local://projects/{project.project_id}",
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def test_api_selects_postgres_store_when_database_url_is_configured(
    monkeypatch, tmp_path: Path, postgres_url: str
) -> None:
    monkeypatch.setenv("VIDEOBOX_DATABASE_URL", postgres_url)

    with TestClient(create_app(projects_root=tmp_path)) as client:
        assert isinstance(client.app.state.store, PostgresProjectStore)
        created = client.post("/api/projects", json={"name": f"API PostgreSQL project {uuid4().hex}"})
        listed = client.get("/api/projects")

    assert created.status_code == 201
    assert created.json()["project_id"] in {item["project_id"] for item in listed.json()["projects"]}


def test_postgres_store_persists_existing_project_asset_and_timeline_mutation(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    project = store.bootstrap_project(f"PostgreSQL mutation project {uuid4().hex}")
    source_audio = tmp_path / "existing-project-narration.wav"
    source_audio.write_bytes(b"narration bytes")

    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=source_audio,
        metadata={"source": "postgres-integration"},
    )
    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    updated = store.update_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
        timeline_payload={
            **saved,
            "version": "v002",
            "tracks": [
                {
                    "track_id": "narration_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001", "asset_id": asset.asset_id}],
                }
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )
    fetched = store.get_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"])

    assert (tmp_path / "projects" / project.project_id / "inputs" / "narration" / source_audio.name).read_bytes() == b"narration bytes"
    assert updated["version"] == "v002"
    assert fetched["tracks"][0]["clips"][0]["asset_id"] == asset.asset_id
    assert fetched["summary"]["track_count"] == 1


def test_postgres_store_scopes_identical_timeline_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first timeline project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second timeline project {uuid4().hex}")

    first_timeline = store.save_timeline_run(
        project_id=first_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )
    second_timeline = store.save_timeline_run(
        project_id=second_project.project_id,
        output_mode="review",
        timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
    )

    assert first_timeline["timeline_id"] == second_timeline["timeline_id"] == "timeline_001"
    assert store.get_timeline_run(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"]
    )["project_id"] == first_project.project_id
    assert store.get_timeline_run(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"]
    )["project_id"] == second_project.project_id
    assert store._list_timeline_ids(project_id=first_project.project_id) == ["timeline_001"]
    assert store._list_timeline_ids(project_id=second_project.project_id) == ["timeline_001"]


def test_postgres_store_scopes_identical_session_and_export_ids_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first scoped IDs project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second scoped IDs project {uuid4().hex}")

    def save_timeline(project_id: str) -> dict:
        return store.save_timeline_run(
            project_id=project_id,
            output_mode="review",
            timeline_payload={"version": "v001", "tracks": [], "review_flags": [], "pending_recommendations": [], "applied_recommendations": []},
        )

    first_timeline = save_timeline(first_project.project_id)
    second_timeline = save_timeline(second_project.project_id)
    first_session = store.save_editing_session(
        project_id=first_project.project_id,
        timeline_id=first_timeline["timeline_id"],
        session_payload={"caption_style": "first", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    second_session = store.save_editing_session(
        project_id=second_project.project_id,
        timeline_id=second_timeline["timeline_id"],
        session_payload={"caption_style": "second", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
    )
    assert first_session["session_id"] == second_session["session_id"] == "editing_session_001"

    store.update_editing_session(
        project_id=first_project.project_id,
        session_id=first_session["session_id"],
        session_payload={"caption_style": "first-updated", "segments": [], "history": [], "undo_stack": [], "redo_stack": []},
        expected_revision=1,
    )
    assert store.get_editing_session(project_id=first_project.project_id, session_id=first_session["session_id"])["caption_style"] == "first-updated"
    assert store.get_editing_session(project_id=second_project.project_id, session_id=second_session["session_id"])["caption_style"] == "second"

    first_source = tmp_path / "first-draft"
    second_source = tmp_path / "second-draft"
    first_source.mkdir()
    second_source.mkdir()
    (first_source / "draft.txt").write_text("first", encoding="utf-8")
    (second_source / "draft.txt").write_text("second", encoding="utf-8")
    first_export = store.save_capcut_draft_export(
        project_id=first_project.project_id, timeline_id=first_timeline["timeline_id"], source_draft_path=first_source
    )
    second_export = store.save_capcut_draft_export(
        project_id=second_project.project_id, timeline_id=second_timeline["timeline_id"], source_draft_path=second_source
    )
    assert first_export["export_id"] == second_export["export_id"] == "export_001"

    store.update_capcut_draft_handoff(
        project_id=first_project.project_id, export_id=first_export["export_id"], handoff={"owner": "first"}
    )
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["handoff"] is None
    store._prune_old_exports(project_id=first_project.project_id, export_type="capcut_draft_export", keep_last=0)
    with pytest.raises(KeyError):
        store.get_capcut_draft_export(project_id=first_project.project_id, export_id=first_export["export_id"])
    assert store.get_capcut_draft_export(project_id=second_project.project_id, export_id=second_export["export_id"])["export_id"] == "export_001"


def test_postgres_store_scopes_assets_collections_and_jobs_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first operational scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second operational scope project {uuid4().hex}")
    first_source = tmp_path / "first.wav"
    second_source = tmp_path / "second.wav"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first_asset = store.register_asset(project_id=first_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=first_source)
    second_asset = store.register_asset(project_id=second_project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=second_source)

    assert [item["asset_id"] for item in store.list_assets(project_id=first_project.project_id)] == [first_asset.asset_id]
    with pytest.raises(KeyError):
        store.get_asset(project_id=second_project.project_id, asset_id=first_asset.asset_id)
    store.update_asset_metadata(project_id=first_project.project_id, asset_id=first_asset.asset_id, metadata_patch={"owner": "first"})
    assert store.get_asset(project_id=second_project.project_id, asset_id=second_asset.asset_id)["metadata"] == {}

    for project, asset, suffix in ((first_project, first_asset, "first"), (second_project, second_asset, "second")):
        store._execute(
            project.project_id,
            "INSERT INTO segments (segment_id, project_id, text) VALUES (?, ?, ?)",
            (f"segment_{suffix}", project.project_id, suffix),
        )
        store._execute(
            project.project_id,
            "INSERT INTO recommendations (recommendation_id, project_id, recommendation_type, auto_apply_allowed, review_required, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"recommendation_{suffix}", project.project_id, "broll", 0, 0, "2026-07-19T00:00:00+00:00"),
        )

    assert [item["segment_id"] for item in store.list_segments(project_id=first_project.project_id)] == ["segment_first"]
    assert [item["recommendation_id"] for item in store.list_recommendation_rows(project_id=second_project.project_id)] == ["recommendation_second"]

    first_job = store.create_job(project_id=first_project.project_id, job_type=JobType.TIMELINE_BUILD)
    second_job = store.create_job(project_id=second_project.project_id, job_type=JobType.TIMELINE_BUILD)
    assert first_job["job_id"] == second_job["job_id"] == "timeline_build_job_001"
    store.update_job(project_id=first_project.project_id, job_id=first_job["job_id"], status=JobStatus.SUCCEEDED)
    assert store.get_job(project_id=second_project.project_id, job_id=second_job["job_id"])["status"] == JobStatus.PENDING.value
    assert [item["job_id"] for item in store.list_jobs(project_id=first_project.project_id)] == [first_job["job_id"]]


def test_postgres_store_scopes_tts_candidates_and_gemini_key_persistence_to_their_projects(
    tmp_path: Path, postgres_url: str
) -> None:
    store = PostgresProjectStore(tmp_path, database_url=postgres_url)
    first_project = store.bootstrap_project(f"PostgreSQL first provider scope project {uuid4().hex}")
    second_project = store.bootstrap_project(f"PostgreSQL second provider scope project {uuid4().hex}")
    accepted = SimpleNamespace(technical_status="accepted", operator_review_status="pending")
    first_candidate = store.save_tts_candidate(
        project_id=first_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="first", acceptance=accepted
    )
    second_candidate = store.save_tts_candidate(
        project_id=second_project.project_id, segment_id="segment_001", asset_id="asset_001", source_text="second", acceptance=accepted
    )
    assert first_candidate["candidate_id"] == second_candidate["candidate_id"] == "tts_candidate_001"
    store.update_tts_candidate_listening_review(
        project_id=first_project.project_id, candidate_id=first_candidate["candidate_id"], decision="approved"
    )
    assert store.get_tts_candidate(project_id=second_project.project_id, candidate_id=second_candidate["candidate_id"])["operator_review_status"] == "pending"
    assert [item["candidate_id"] for item in store.list_tts_candidates(project_id=first_project.project_id, segment_id="segment_001")] == ["tts_candidate_001"]

    first_key = store.save_gemini_provider_key(
        project_id=first_project.project_id, label="First", api_key_secret="first-secret", primary_model="primary", cheap_model="cheap", high_quality_model="quality"
    )
    second_key = store.save_gemini_provider_key(
        project_id=second_project.project_id, label="Second", api_key_secret="second-secret", primary_model="primary", cheap_model="cheap", high_quality_model="quality"
    )
    assert first_key["key_id"] == second_key["key_id"] == "gemini_key_001"
    store.set_gemini_provider_key_status(project_id=first_project.project_id, key_id=first_key["key_id"], status="disabled")
    assert store.get_gemini_provider_key(project_id=second_project.project_id, key_id=second_key["key_id"])["status"] == "active"
    assert [item["key_id"] for item in store.list_gemini_provider_keys(project_id=first_project.project_id)] == ["gemini_key_001"]
