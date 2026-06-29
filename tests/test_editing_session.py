from __future__ import annotations

import sqlite3
from pathlib import Path

from videobox_core_engine.local_pipeline import LocalPipelineRunner as _LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


def test_build_editing_session_from_review_timeline_creates_editable_segment_state() -> None:
    from videobox_core_engine.editing_session import build_editing_session

    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "project_001",
        "tracks": [
            {
                "track_id": "narration_primary",
                "track_type": "narration",
                "clips": [
                    {
                        "clip_id": "clip_narration_001",
                        "segment_id": "seg_001",
                        "asset_uri": "local://projects/project_001/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                        "clip_type": "narration",
                    }
                ],
            }
        ],
        "review_flags": [],
        "pending_recommendations": [],
    }
    segments = [
        {
            "segment_id": "seg_001",
            "text": "Office overview intro.",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "review_required": False,
            "cleanup_decision": "keep",
        }
    ]

    session = build_editing_session(
        project_id="project_001",
        timeline=timeline,
        segments=segments,
    )

    assert session["project_id"] == "project_001"
    assert session["timeline_id"] == "timeline_001"
    assert session["segments"][0]["segment_id"] == "seg_001"
    assert session["segments"][0]["caption_text"] == "Office overview intro."
    assert session["segments"][0]["cut_action"] == "keep"
    assert session["history"] == []


def test_save_editing_session_persists_current_state_and_history(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session Project")

    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Updated caption",
                    "start_sec": 0.0,
                    "end_sec": 2.5,
                    "cut_action": "trim",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_010"},
                    "visual_overlays": [{"overlay_type": "image_card", "asset_id": "asset_020"}],
                    "music_override": None,
                }
            ],
            "history": [
                {
                    "mutation_type": "caption_update",
                    "segment_id": "seg_001",
                }
            ],
        },
    )

    loaded = store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])

    assert loaded["timeline_id"] == "timeline_001"
    assert loaded["segments"][0]["caption_text"] == "Updated caption"
    assert loaded["history"][0]["mutation_type"] == "caption_update"


def test_save_editing_session_recovers_when_table_is_missing_on_existing_project(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session Migration Project")
    connection = sqlite3.connect(store.database_path(project.project_id))
    try:
        connection.execute("DROP TABLE editing_sessions")
        connection.commit()
    finally:
        connection.close()

    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={"segments": [], "history": []},
    )

    assert saved["session_id"] == "editing_session_001"
    assert saved["timeline_id"] == "timeline_001"


def test_partial_regeneration_request_scopes_only_targeted_segments() -> None:
    from videobox_core_engine.editing_session import build_partial_regeneration_request
    from videobox_core_engine.editing_session import build_editing_session

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            },
            {
                "segment_id": "seg_002",
                "text": "Regenerate this",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "review_required": False,
                "cleanup_decision": "keep",
            },
        ],
    )

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_002"],
        fields=["broll", "visual_overlay"],
    )

    assert request["session_id"] is None
    assert request["segment_ids"] == ["seg_002"]
    assert request["fields"] == ["broll", "visual_overlay"]


def test_update_segment_cut_action_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_cut_action

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )

    updated = update_segment_cut_action(
        session=session,
        segment_id="seg_001",
        cut_action="remove",
    )

    assert updated["segments"][0]["cut_action"] == "remove"
    assert updated["history"][-1]["mutation_type"] == "cut_action_update"


def test_update_segment_broll_override_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_broll_override

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )

    updated = update_segment_broll_override(
        session=session,
        segment_id="seg_001",
        asset_id="asset_manual_001",
    )

    assert updated["segments"][0]["broll_override"] == {"asset_id": "asset_manual_001"}
    assert updated["history"][-1]["mutation_type"] == "broll_override_update"


def test_update_segment_visual_overlay_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_visual_overlay

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )

    updated = update_segment_visual_overlay(
        session=session,
        segment_id="seg_001",
        overlay_type="image_card",
        asset_id="asset_image_001",
    )

    assert updated["segments"][0]["visual_overlays"] == [
        {"overlay_type": "image_card", "asset_id": "asset_image_001"}
    ]
    assert updated["history"][-1]["mutation_type"] == "visual_overlay_update"


def test_update_segment_music_override_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_music_override

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )

    updated = update_segment_music_override(
        session=session,
        segment_id="seg_001",
        asset_id="music_manual_001",
    )

    assert updated["segments"][0]["music_override"] == {"asset_id": "music_manual_001"}
    assert updated["history"][-1]["mutation_type"] == "music_override_update"


def test_partial_regeneration_request_rejects_unknown_segment_and_field() -> None:
    import pytest

    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import build_partial_regeneration_request

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {
                "segment_id": "seg_001",
                "text": "Keep this",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }
        ],
    )

    with pytest.raises(ValueError):
        build_partial_regeneration_request(
            session=session,
            segment_ids=["does_not_exist"],
            fields=["not_a_real_field"],
        )
