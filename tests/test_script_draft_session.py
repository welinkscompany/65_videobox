from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.script_draft_session import (
    apply_narration_alignment_to_script_draft,
    build_provisional_script_draft_session,
)
from videobox_storage.local_project_store import LocalProjectStore


def test_script_draft_segments_blank_paragraphs_before_sentences_and_character_budget() -> None:
    session = build_provisional_script_draft_session(
        project_id="project_001",
        script_asset_id="asset_script_001",
        script_text="첫 문장입니다. 둘째 문장입니다.\n\n긴 문장은 종결부호 없이도 최대 글자 수를 넘으면 나뉘어야 합니다",
        max_characters=12,
        korean_characters_per_second=4,
    )

    assert [segment["caption_text"] for segment in session["segments"]] == [
        "첫 문장입니다.",
        "둘째 문장입니다.",
        "긴 문장은 종결부호 없이도",
        "최대 글자 수를 넘으면",
        "나뉘어야 합니다",
    ]
    assert session["timing_source"] == "provisional_script"
    assert session["narration_alignment_required"] is True
    assert all(segment["end_sec"] - segment["start_sec"] >= 2.0 for segment in session["segments"])
    assert [segment["source_script_segment_id"] for segment in session["segments"]] == [
        "script:asset_script_001:001",
        "script:asset_script_001:002",
        "script:asset_script_001:003",
        "script:asset_script_001:004",
        "script:asset_script_001:005",
    ]


def test_script_draft_splits_korean_terminal_punctuation_without_whitespace() -> None:
    session = build_provisional_script_draft_session(
        project_id="project_001",
        script_asset_id="asset_script_001",
        script_text="첫 문장입니다.둘째 문장입니다!셋째 문장입니다?",
    )

    assert [segment["caption_text"] for segment in session["segments"]] == ["첫 문장입니다.", "둘째 문장입니다!", "셋째 문장입니다?"]


def test_narration_alignment_replaces_provisional_bounds_preserves_source_identity_and_returns_stale_contract() -> None:
    provisional = build_provisional_script_draft_session(
        project_id="project_001",
        script_asset_id="asset_script_001",
        script_text="첫 문장입니다. 둘째 문장입니다.",
    )

    aligned, stale_source_ids = apply_narration_alignment_to_script_draft(
        session=provisional,
        aligned_segments=[
            {"source_script_segment_id": "script:asset_script_001:001", "start_sec": 1.5, "end_sec": 4.0},
            {"source_script_segment_id": "script:asset_script_001:002", "start_sec": 4.0, "end_sec": 7.25},
        ],
    )

    assert aligned["timing_source"] == "narration_alignment"
    assert aligned["narration_alignment_required"] is False
    assert [(item["source_script_segment_id"], item["start_sec"], item["end_sec"]) for item in aligned["segments"]] == [
        ("script:asset_script_001:001", 1.5, 4.0),
        ("script:asset_script_001:002", 4.0, 7.25),
    ]
    assert stale_source_ids == ["script:asset_script_001:001", "script:asset_script_001:002"]
    assert aligned["stale_proposal_source_script_segment_ids"] == stale_source_ids


def test_narration_alignment_stales_every_aligned_source_even_when_bounds_match_provisional() -> None:
    provisional = build_provisional_script_draft_session(
        project_id="project_001",
        script_asset_id="asset_script_001",
        script_text="첫 문장입니다.",
    )
    original = provisional["segments"][0]

    aligned, stale_source_ids = apply_narration_alignment_to_script_draft(
        session=provisional,
        aligned_segments=[
            {
                "source_script_segment_id": original["source_script_segment_id"],
                "start_sec": original["start_sec"],
                "end_sec": original["end_sec"],
            }
        ],
    )

    assert stale_source_ids == [original["source_script_segment_id"]]
    assert aligned["stale_proposal_source_script_segment_ids"] == stale_source_ids


def test_script_draft_rejects_empty_script_and_alignment_identity_mismatch() -> None:
    with pytest.raises(ValueError, match="Script text must not be empty"):
        build_provisional_script_draft_session(project_id="project_001", script_asset_id="asset_script_001", script_text=" \n\t ")

    provisional = build_provisional_script_draft_session(project_id="project_001", script_asset_id="asset_script_001", script_text="첫 문장입니다.")
    with pytest.raises(ValueError, match="unknown source_script_segment_id"):
        apply_narration_alignment_to_script_draft(
            session=provisional,
            aligned_segments=[{"source_script_segment_id": "missing", "start_sec": 0.0, "end_sec": 2.0}],
        )
    with pytest.raises(ValueError, match="finite"):
        apply_narration_alignment_to_script_draft(
            session=provisional,
            aligned_segments=[{"source_script_segment_id": "script:asset_script_001:001", "start_sec": 0.0, "end_sec": float("inf")}],
        )


def test_script_draft_api_persists_provisional_metadata_after_store_reload(tmp_path: Path) -> None:
    script_path = tmp_path / "script.txt"
    script_path.write_text("첫 문장입니다.\n\n둘째 문장입니다.", encoding="utf-8")
    app = create_app(projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Script Draft"}).json()["project_id"]
        asset_response = client.post(
            f"/api/projects/{project_id}/assets/script-document",
            json={"source_path": str(script_path)},
        )
        assert asset_response.status_code == 201
        response = client.post(
            f"/api/projects/{project_id}/editing-sessions/from-script",
            json={"script_asset_id": asset_response.json()["asset_id"]},
        )

    assert response.status_code == 201
    created = response.json()
    assert created["timing_source"] == "provisional_script"
    assert created["narration_alignment_required"] is True
    assert [item["caption_text"] for item in created["segments"]] == ["첫 문장입니다.", "둘째 문장입니다."]
    reloaded = LocalProjectStore(tmp_path / "projects").get_editing_session(project_id=project_id, session_id=created["session_id"])
    assert reloaded["timing_source"] == "provisional_script"
    assert [item["source_script_segment_id"] for item in reloaded["segments"]] == [item["source_script_segment_id"] for item in created["segments"]]


def test_store_does_not_add_script_metadata_to_a_legacy_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Editing Session")

    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_legacy",
        session_payload={"segments": [], "history": []},
    )

    for key in (
        "script_asset_id",
        "timing_source",
        "narration_alignment_required",
        "stale_proposal_source_script_segment_ids",
    ):
        assert key not in saved


def test_script_draft_api_rejects_unknown_or_non_script_asset(tmp_path: Path) -> None:
    source_path = tmp_path / "video.mp4"
    source_path.write_bytes(b"not-a-video")
    empty_script_path = tmp_path / "empty-script.txt"
    empty_script_path.write_text(" \n\t", encoding="utf-8")
    app = create_app(projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Script Draft"}).json()["project_id"]
        missing = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": "missing"})
        non_script_asset = client.post(f"/api/projects/{project_id}/assets/raw-video", json={"source_path": str(source_path)})
        invalid_type = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": non_script_asset.json()["asset_id"]})
        empty_script_asset = client.post(f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(empty_script_path)})
        empty_script = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": empty_script_asset.json()["asset_id"]})

    assert missing.status_code == 404
    assert invalid_type.status_code == 400
    assert invalid_type.json()["detail"] == "script_asset_id must reference a script_document asset."
    assert empty_script.status_code == 400
    assert empty_script.json()["detail"] == "Script text must not be empty."


def test_aligned_script_draft_transition_survives_store_update_and_reload(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Aligned Script Draft")
    provisional = build_provisional_script_draft_session(
        project_id=project.project_id,
        script_asset_id="asset_script_001",
        script_text="첫 문장입니다. 둘째 문장입니다.",
    )
    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=provisional["timeline_id"],
        session_payload=provisional,
    )
    aligned, _ = apply_narration_alignment_to_script_draft(
        session=saved,
        aligned_segments=[
            {"source_script_segment_id": "script:asset_script_001:001", "start_sec": 0.5, "end_sec": 2.6},
            {"source_script_segment_id": "script:asset_script_001:002", "start_sec": 2.6, "end_sec": 5.0},
        ],
    )
    store.update_editing_session(
        project_id=project.project_id,
        session_id=saved["session_id"],
        session_payload=aligned,
        expected_revision=saved["session_revision"],
    )

    reloaded = LocalProjectStore(tmp_path).get_editing_session(project_id=project.project_id, session_id=saved["session_id"])
    assert reloaded["timing_source"] == "narration_alignment"
    assert reloaded["narration_alignment_required"] is False
    assert reloaded["stale_proposal_source_script_segment_ids"] == [
        "script:asset_script_001:001",
        "script:asset_script_001:002",
    ]
    assert [item["source_script_segment_id"] for item in reloaded["segments"]] == [
        "script:asset_script_001:001",
        "script:asset_script_001:002",
    ]


def test_script_draft_alignment_api_updates_persisted_session_and_exposes_stale_source_ids(tmp_path: Path) -> None:
    script_path = tmp_path / "script.txt"
    script_path.write_text("첫 문장입니다. 둘째 문장입니다.", encoding="utf-8")
    app = create_app(projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Script Draft Alignment"}).json()["project_id"]
        asset = client.post(f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script_path)}).json()
        created = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": asset["asset_id"]}).json()
        source_ids = [segment["source_script_segment_id"] for segment in created["segments"]]
        aligned = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={
                "expected_revision": created["session_revision"],
                "aligned_segments": [
                    {"source_script_segment_id": source_ids[0], "start_sec": 1.0, "end_sec": 3.25},
                    {"source_script_segment_id": source_ids[1], "start_sec": 3.25, "end_sec": 6.5},
                ],
            },
        )

    assert aligned.status_code == 200
    assert aligned.json()["timing_source"] == "narration_alignment"
    assert aligned.json()["stale_proposal_source_script_segment_ids"] == source_ids
    reloaded = LocalProjectStore(tmp_path / "projects").get_editing_session(project_id=project_id, session_id=created["session_id"])
    assert reloaded["timing_source"] == "narration_alignment"
    assert [(item["start_sec"], item["end_sec"]) for item in reloaded["segments"]] == [(1.0, 3.25), (3.25, 6.5)]


def test_script_draft_alignment_api_rejects_stale_revision_without_replacing_timing_or_stale_contract(tmp_path: Path) -> None:
    script_path = tmp_path / "script.txt"
    script_path.write_text("첫 문장입니다.", encoding="utf-8")
    app = create_app(projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Script Draft Stale"}).json()["project_id"]
        asset = client.post(f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script_path)}).json()
        created = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": asset["asset_id"]}).json()
        source_id = created["segments"][0]["source_script_segment_id"]
        first = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={"expected_revision": created["session_revision"], "aligned_segments": [{"source_script_segment_id": source_id, "start_sec": 1.0, "end_sec": 3.0}]},
        )
        stale = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={"expected_revision": created["session_revision"], "aligned_segments": [{"source_script_segment_id": source_id, "start_sec": 10.0, "end_sec": 12.0}]},
        )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["latest_session"]["segments"][0]["start_sec"] == 1.0
    assert stale.json()["latest_session"]["stale_proposal_source_script_segment_ids"] == [source_id]


def test_script_draft_alignment_api_rejects_empty_overlap_and_non_positive_bounds(tmp_path: Path) -> None:
    script_path = tmp_path / "script.txt"
    script_path.write_text("첫 문장입니다. 둘째 문장입니다.", encoding="utf-8")
    app = create_app(projects_root=tmp_path / "projects")
    with TestClient(app) as client:
        project_id = client.post("/api/projects", json={"name": "Script Draft Invalid Alignment"}).json()["project_id"]
        asset = client.post(f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script_path)}).json()
        created = client.post(f"/api/projects/{project_id}/editing-sessions/from-script", json={"script_asset_id": asset["asset_id"]}).json()
        source_ids = [segment["source_script_segment_id"] for segment in created["segments"]]
        empty = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={"expected_revision": created["session_revision"], "aligned_segments": []},
        )
        overlap = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={"expected_revision": created["session_revision"], "aligned_segments": [
                {"source_script_segment_id": source_ids[0], "start_sec": 0.0, "end_sec": 3.0},
                {"source_script_segment_id": source_ids[1], "start_sec": 2.5, "end_sec": 4.0},
            ]},
        )
        non_positive = client.post(
            f"/api/projects/{project_id}/editing-sessions/{created['session_id']}/narration-alignment",
            json={"expected_revision": created["session_revision"], "aligned_segments": [
                {"source_script_segment_id": source_ids[0], "start_sec": 0.0, "end_sec": 0.0},
                {"source_script_segment_id": source_ids[1], "start_sec": 1.0, "end_sec": 3.0},
            ]},
        )

    assert empty.status_code == 422
    assert overlap.status_code == 422
    assert non_positive.status_code == 422
