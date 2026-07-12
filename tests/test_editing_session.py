from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner as _LocalPipelineRunner
from videobox_domain_models.assets import AssetType
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


def test_editing_session_compare_and_swap_rejects_stale_write_without_replacing_json(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session CAS Project")
    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={"session_revision": 1, "segments": [{"segment_id": "seg_001", "caption_text": "original"}], "history": []},
    )
    updated = {**saved, "session_revision": 2, "segments": [{"segment_id": "seg_001", "caption_text": "fresh"}]}
    store.update_editing_session(
        project_id=project.project_id, session_id=saved["session_id"], session_payload=updated, expected_revision=1
    )

    from videobox_storage.local_project_store import EditingSessionRevisionConflict
    with pytest.raises(EditingSessionRevisionConflict):
        store.update_editing_session(
            project_id=project.project_id,
            session_id=saved["session_id"],
            session_payload={**saved, "session_revision": 2, "segments": [{"segment_id": "seg_001", "caption_text": "stale"}]},
            expected_revision=1,
        )

    assert store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])["segments"][0]["caption_text"] == "fresh"


def test_editing_session_recovers_canonical_db_snapshot_when_json_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session Recovery Project")
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload={"segments": [{"segment_id": "seg_001", "caption_text": "old"}], "history": []})
    import pathlib
    original_replace = pathlib.Path.replace
    monkeypatch.setattr(pathlib.Path, "replace", lambda self, target: (_ for _ in ()).throw(OSError("injected replace failure")))
    with pytest.raises(OSError, match="injected"):
        store.update_editing_session(project_id=project.project_id, session_id=saved["session_id"], expected_revision=saved["session_revision"], session_payload={**saved, "session_revision": saved["session_revision"] + 1, "segments": [{"segment_id": "seg_001", "caption_text": "new"}]})
    monkeypatch.setattr(pathlib.Path, "replace", original_replace)
    recovered = store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])
    assert recovered["session_revision"] == saved["session_revision"] + 1
    assert recovered["segments"][0]["caption_text"] == "new"


def test_generic_editing_session_mutation_increments_revision(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Editing Session Revision Project")
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload={"segments": [], "history": []})
    updated = store.update_editing_session(project_id=project.project_id, session_id=saved["session_id"], session_payload={**saved, "history": [{"mutation_type": "caption_update"}]})
    assert updated["session_revision"] == saved["session_revision"] + 1


def test_caption_style_scope_rules_resolve_snapshots_without_changing_default_for_single_caption() -> None:
    from videobox_core_engine.editing_session import preview_caption_style_scope, update_caption_style
    session = {"caption_style": {"text_color": "#FFFFFFFF"}, "session_revision": 1, "segments": [
        {"segment_id": "a"}, {"segment_id": "b"}, {"segment_id": "c"}
    ], "history": []}
    assert preview_caption_style_scope(session=session, scope="current_caption", segment_ids=["b"]) == ["b"]
    assert preview_caption_style_scope(session=session, scope="selected_captions", segment_ids=["c", "a"]) == ["a", "c"]
    assert preview_caption_style_scope(session=session, scope="from_current", segment_ids=["b"]) == ["b", "c"]
    assert preview_caption_style_scope(session=session, scope="whole_project", segment_ids=[]) == ["a", "b", "c"]
    assert preview_caption_style_scope(session=session, scope="project_default", segment_ids=[]) == []
    with pytest.raises(ValueError, match="whole_project does not accept segment_ids"):
        preview_caption_style_scope(session=session, scope="whole_project", segment_ids=["a"])
    with pytest.raises(ValueError, match="project_default does not accept segment_ids"):
        preview_caption_style_scope(session=session, scope="project_default", segment_ids=["a"])
    changed = update_caption_style(session=session, style={"text_color": "#00FF00FF"}, scope="current_caption", segment_ids=["b"])
    assert changed["caption_style"]["text_color"] == "#FFFFFFFF"
    assert changed["segments"][1]["caption_style"]["text_color"] == "#00FF00FF"


def test_partial_regeneration_conflict_returns_latest_manual_caption_and_style_without_stale_timeline_save() -> None:
    from videobox_core_engine.editing_session_and_regeneration import EditingSessionConflict, EditingSessionRegenerationMixin
    from videobox_storage.local_project_store import EditingSessionRevisionConflict

    stale = {"session_id": "session_001", "timeline_id": "timeline_001", "session_revision": 1, "segments": [{"segment_id": "seg_001", "caption_text": "old", "caption_style": {"text_color": "#FFFFFFFF"}}], "history": []}
    latest = {**stale, "session_revision": 2, "segments": [{"segment_id": "seg_001", "caption_text": "manual", "caption_style": {"text_color": "#00FF00FF"}}]}

    class Store:
        def __init__(self) -> None: self.calls = 0; self.persisted = None
        def get_editing_session(self, **_: object) -> dict: return latest if self.calls else stale
        def create_job(self, **_: object) -> dict: return {"job_id": "job_001"}
        def update_editing_session(self, **kwargs: object) -> dict:
            self.calls += 1
            if self.calls == 1: raise EditingSessionRevisionConflict("stale")
            self.persisted = kwargs["session_payload"]
            return {**self.persisted, "updated_at": "now"}
        def save_partial_regeneration_run(self, **kwargs: object) -> dict: return {"partial_regeneration_id": "regen_001"}
        def update_job(self, **_: object) -> None: pass

    class Runner(EditingSessionRegenerationMixin):
        def __init__(self) -> None: self.store = Store()
        def _execute_partial_regeneration(self, **_: object) -> dict: return {"timeline_id": "timeline_002", "timeline": {}, "segment_ids": ["seg_001"], "fields": ["caption"], "downstream_steps": []}

    runner = Runner()
    with pytest.raises(EditingSessionConflict) as exc_info:
        runner.start_editing_session_partial_regeneration(
            project_id="project_001",
            session_id="session_001",
            segment_ids=["seg_001"],
            fields=["caption"],
            expected_revision=stale["session_revision"],
        )

    assert exc_info.value.latest_session["segments"][0]["caption_text"] == "manual"
    assert exc_info.value.latest_session["segments"][0]["caption_style"]["text_color"] == "#00FF00FF"
    assert runner.store.persisted is None


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
    assert request["downstream_steps"] == [
        "broll_refresh",
        "overlay_refresh",
        "timeline_build",
    ]


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


def test_update_segment_sfx_override_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session, update_segment_sfx_override

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[{"segment_id": "seg_001", "text": "Caption", "start_sec": 0.0, "end_sec": 1.0, "review_required": False, "cleanup_decision": "keep"}],
    )

    updated = update_segment_sfx_override(session=session, segment_id="seg_001", asset_id="asset_sfx_001")

    assert updated["segments"][0]["sfx_override"] == {"asset_id": "asset_sfx_001"}
    assert updated["history"][-1]["mutation_type"] == "sfx_override_update"


def test_approved_sfx_recommendation_materializes_target_timeline_track() -> None:
    from videobox_core_engine.review_action_mutations import apply_approved_recommendation_to_timeline

    timeline = {
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
                        "start_sec": 1.0,
                        "end_sec": 3.0,
                        "clip_type": "narration",
                    }
                ],
            }
        ],
    }

    apply_approved_recommendation_to_timeline(
        timeline=timeline,
        decided_recommendation={
            "recommendation_id": "manual_sfx_seg_001",
            "target_segment_id": "seg_001",
            "recommendation_type": "sfx",
            "selected_asset_id": "asset_sfx_001",
        },
    )

    assert timeline["tracks"][-1] == {
        "track_id": "sfx_overlay",
        "track_type": "sfx",
        "clips": [
            {
                "clip_id": "clip_sfx_001",
                "segment_id": "seg_001",
                "asset_uri": "local://projects/project_001/assets/asset_sfx_001",
                "start_sec": 1.0,
                "end_sec": 3.0,
                "clip_type": "sfx",
                "recommendation_id": "manual_sfx_seg_001",
            }
        ],
    }


def test_clear_segment_broll_override_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import clear_segment_broll_override
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
    cleared = clear_segment_broll_override(session=updated, segment_id="seg_001")

    assert cleared["segments"][0]["broll_override"] is None
    assert cleared["history"][-1]["mutation_type"] == "broll_override_clear"


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


def test_clear_segment_music_override_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import clear_segment_music_override
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
    cleared = clear_segment_music_override(session=updated, segment_id="seg_001")

    assert cleared["segments"][0]["music_override"] is None
    assert cleared["history"][-1]["mutation_type"] == "music_override_clear"


def test_update_segment_explanation_card_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_explanation_card

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

    updated = update_segment_explanation_card(
        session=session,
        segment_id="seg_001",
        title="Key takeaway",
        body="Show the main explanation point.",
        text="Key takeaway: Show the main explanation point.",
    )

    assert updated["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Show the main explanation point.",
            "text": "Key takeaway: Show the main explanation point.",
        }
    ]
    assert updated["history"][-1]["mutation_type"] == "explanation_card_update"


def test_remove_segment_explanation_card_clears_overlay_and_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import remove_segment_explanation_card
    from videobox_core_engine.editing_session import update_segment_explanation_card

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
    with_card = update_segment_explanation_card(
        session=session,
        segment_id="seg_001",
        title="Key takeaway",
        body="Show the main explanation point.",
        text="Key takeaway: Show the main explanation point.",
    )

    updated = remove_segment_explanation_card(session=with_card, segment_id="seg_001")

    assert updated["segments"][0]["visual_overlays"] == []
    assert updated["history"][-1]["mutation_type"] == "explanation_card_remove"


def test_update_segment_image_overlay_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_image_overlay

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

    updated = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
    )

    assert updated["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
            "text": "Exterior reference image",
        }
    ]
    assert updated["history"][-1]["mutation_type"] == "image_overlay_update"


def test_update_segment_table_overlay_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_table_overlay

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

    updated = update_segment_table_overlay(
        session=session,
        segment_id="seg_001",
        columns=["Metric", "Value"],
        rows=[["CTR", "4.2%"]],
        text="Metric | Value\nCTR | 4.2%",
    )

    assert updated["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "table_card",
            "columns": ["Metric", "Value"],
            "rows": [["CTR", "4.2%"]],
            "text": "Metric | Value\nCTR | 4.2%",
        }
    ]
    assert updated["history"][-1]["mutation_type"] == "table_overlay_update"


def test_remove_segment_image_and_table_overlays_record_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import remove_segment_image_overlay
    from videobox_core_engine.editing_session import remove_segment_table_overlay
    from videobox_core_engine.editing_session import update_segment_image_overlay
    from videobox_core_engine.editing_session import update_segment_table_overlay

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
    with_image = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
    )
    with_table = update_segment_table_overlay(
        session=with_image,
        segment_id="seg_001",
        columns=["Metric", "Value"],
        rows=[["CTR", "4.2%"]],
        text="Metric | Value\nCTR | 4.2%",
    )

    removed_image = remove_segment_image_overlay(session=with_table, segment_id="seg_001")
    removed_table = remove_segment_table_overlay(session=removed_image, segment_id="seg_001")

    assert removed_image["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "table_card",
            "columns": ["Metric", "Value"],
            "rows": [["CTR", "4.2%"]],
            "text": "Metric | Value\nCTR | 4.2%",
        }
    ]
    assert removed_image["history"][-1]["mutation_type"] == "image_overlay_remove"
    assert removed_table["segments"][0]["visual_overlays"] == []
    assert removed_table["history"][-1]["mutation_type"] == "table_overlay_remove"


def test_select_and_clear_segment_tts_replacement_records_history() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import clear_segment_tts_replacement
    from videobox_core_engine.editing_session import select_segment_tts_replacement

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

    selected = select_segment_tts_replacement(
        session=session,
        segment_id="seg_001",
        recommendation_id="rec_tts_seg_001",
        asset_id="asset_tts_001",
    )
    cleared = clear_segment_tts_replacement(session=selected, segment_id="seg_001")

    assert selected["segments"][0]["tts_replacement"] == {
        "recommendation_id": "rec_tts_seg_001",
        "asset_id": "asset_tts_001",
    }
    assert selected["history"][-1]["mutation_type"] == "tts_replacement_select"
    assert cleared["segments"][0]["tts_replacement"] is None
    assert cleared["history"][-1]["mutation_type"] == "tts_replacement_clear"


def test_pending_or_rejected_tts_candidate_cannot_replace_narration_until_listening_approved(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="TTS Listening Gate")
    runner = _LocalPipelineRunner(store)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "기존 나레이션을 유지합니다.",
                    "start_sec": 0.0,
                    "end_sec": 3.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )
    candidate = store.save_tts_candidate(
        project_id=project.project_id,
        segment_id="seg_001",
        asset_id="asset_tts_001",
        source_text="생성된 후보입니다.",
        acceptance=SimpleNamespace(
            technical_status="accepted",
            operator_review_status="pending",
            target_duration_sec=3.0,
            actual_duration_sec=3.0,
            failure_code=None,
        ),
    )

    with pytest.raises(ValueError, match="listening approval"):
        runner.select_editing_session_segment_tts_replacement(
            project_id=project.project_id,
            session_id=session["session_id"],
            segment_id="seg_001",
            recommendation_id=candidate["candidate_id"],
            asset_id=candidate["asset_id"],
            expected_revision=session["session_revision"],
        )

    assert store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])["segments"][0]["tts_replacement"] is None

    store.update_tts_candidate_listening_review(
        project_id=project.project_id,
        candidate_id=candidate["candidate_id"],
        decision="approved",
    )
    selected = runner.select_editing_session_segment_tts_replacement(
        project_id=project.project_id,
        session_id=session["session_id"],
        segment_id="seg_001",
        recommendation_id=candidate["candidate_id"],
        asset_id=candidate["asset_id"],
        expected_revision=session["session_revision"],
    )

    assert selected["segments"][0]["tts_replacement"] == {
        "recommendation_id": candidate["candidate_id"],
        "asset_id": candidate["asset_id"],
    }


def test_update_segment_visual_overlay_preserves_other_overlay_types() -> None:
    from videobox_core_engine.editing_session import build_editing_session
    from videobox_core_engine.editing_session import update_segment_explanation_card
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
    with_explanation = update_segment_explanation_card(
        session=session,
        segment_id="seg_001",
        title="Key takeaway",
        body="Show the main explanation point.",
        text="Key takeaway: Show the main explanation point.",
    )

    updated = update_segment_visual_overlay(
        session=with_explanation,
        segment_id="seg_001",
        overlay_type="image_card",
        asset_id="asset_image_001",
    )

    assert updated["segments"][0]["visual_overlays"] == [
        {
            "overlay_type": "explanation_card",
            "title": "Key takeaway",
            "body": "Show the main explanation point.",
            "text": "Key takeaway: Show the main explanation point.",
        },
        {
            "overlay_type": "image_card",
            "asset_id": "asset_image_001",
        },
    ]


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


def test_partial_regeneration_request_deduplicates_step_union_and_keeps_timeline_build_last() -> None:
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

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_001"],
        fields=["caption", "cut_action", "broll"],
    )

    assert request["downstream_steps"] == [
        "segment_refresh",
        "broll_refresh",
        "timeline_build",
    ]


def test_partial_regeneration_request_maps_explanation_and_tts_fields_to_explicit_steps() -> None:
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

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_001"],
        fields=["explanation_card", "tts_replacement"],
    )

    assert request["downstream_steps"] == [
        "overlay_refresh",
        "tts_refresh",
        "timeline_build",
    ]


def test_partial_regeneration_request_maps_image_and_table_fields_to_overlay_refresh() -> None:
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

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_001"],
        fields=["image_overlay", "table_overlay"],
    )

    assert request["downstream_steps"] == [
        "overlay_refresh",
        "timeline_build",
    ]


def test_partial_regeneration_pipeline_keeps_scope_limited_to_selected_segments(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Scope Project")
    runner = _LocalPipelineRunner(store)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "caption_segments": [
                {
                    "segment_id": "seg_001",
                    "text": "Original caption one",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "review_required": False,
                    "cleanup_decision": "keep",
                },
                {
                    "segment_id": "seg_002",
                    "text": "Original caption two",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "review_required": False,
                    "cleanup_decision": "keep",
                },
            ],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_broll_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "broll",
                    "selected_asset_id": "asset_original_001",
                    "score": 0.91,
                    "reason": "Original B-roll",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": ["broll_recommendation_job_001"],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Manual caption one",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Manual caption two",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": {"asset_id": "asset_manual_002"},
                    "visual_overlays": [],
                    "music_override": None,
                },
            ],
            "history": [
                {"mutation_type": "caption_update", "segment_id": "seg_001", "caption_text": "Manual caption one"},
                {"mutation_type": "caption_update", "segment_id": "seg_002", "caption_text": "Manual caption two"},
                {"mutation_type": "broll_override_update", "segment_id": "seg_002", "asset_id": "asset_manual_002"},
            ],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_002"],
        fields=["caption", "broll"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(
        project_id=project.project_id,
        job_id=started["job_id"],
    )

    assert result["segment_ids"] == ["seg_002"]
    assert result["fields"] == ["caption", "broll"]
    assert result["downstream_steps"] == [
        "segment_refresh",
        "broll_refresh",
        "timeline_build",
    ]
    assert result["regenerated_segments"] == [
        {
            "segment_id": "seg_002",
            "caption_text": "Manual caption two",
            "cut_action": "keep",
        }
    ]
    broll_track = next(track for track in result["timeline"]["tracks"] if track["track_type"] == "broll")
    assert [clip["segment_id"] for clip in broll_track["clips"]] == ["seg_001", "seg_002"]
    manual_clip = next(clip for clip in broll_track["clips"] if clip["segment_id"] == "seg_002")
    assert manual_clip["asset_uri"].endswith("/assets/asset_manual_002")
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=started["job_id"])
    subtitle_job = runner.start_subtitle_render(
        project_id=project.project_id,
        timeline_job_id=started["job_id"],
    )
    subtitle = runner.get_subtitle_result(project_id=project.project_id, job_id=subtitle_job["job_id"])
    subtitle_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=subtitle["subtitle"]["file_uri"],
    )
    subtitle_text = subtitle_path.read_text(encoding="utf-8")

    assert "Manual caption two" in subtitle_text
    assert "Original caption two" not in subtitle_text


def test_partial_regeneration_pipeline_runs_broll_refresh_when_no_manual_override_exists(tmp_path: Path) -> None:
    class RecordingBrollRecommender:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def recommend(self, request):  # noqa: ANN001
            self.calls.append(request)
            return [
                SimpleNamespace(
                    target_segment_id="seg_002",
                    selected_asset_id="asset_regenerated_002",
                    score=0.88,
                    reason="Regenerated B-roll",
                    auto_apply_allowed=True,
                    review_required=False,
                    payload={},
                )
            ]

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Refresh Project")
    broll_recommender = RecordingBrollRecommender()
    runner = _LocalPipelineRunner(store, broll_recommender=broll_recommender)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_broll_seg_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "broll",
                    "selected_asset_id": "asset_original_001",
                    "score": 0.91,
                    "reason": "Original B-roll",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "payload": {},
                    "created_at": "2026-06-29T00:00:00+00:00",
                }
            ],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": ["broll_recommendation_job_001"],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                },
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_002"],
        fields=["broll"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(
        project_id=project.project_id,
        job_id=started["job_id"],
    )

    assert len(broll_recommender.calls) == 1
    request = broll_recommender.calls[0]
    assert [segment["segment_id"] for segment in request.segments] == ["seg_002"]
    broll_track = next(track for track in result["timeline"]["tracks"] if track["track_type"] == "broll")
    assert [clip["segment_id"] for clip in broll_track["clips"]] == ["seg_001", "seg_002"]
    regenerated_clip = next(clip for clip in broll_track["clips"] if clip["segment_id"] == "seg_002")
    assert regenerated_clip["asset_uri"].endswith("/assets/asset_regenerated_002")


def test_partial_regeneration_pipeline_marks_job_failed_when_refresh_step_errors(tmp_path: Path) -> None:
    class FailingBrollRecommender:
        def recommend(self, request):  # noqa: ANN001
            del request
            raise RuntimeError("broll refresh exploded")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Failure Project")
    runner = _LocalPipelineRunner(store, broll_recommender=FailingBrollRecommender())

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": ["broll_recommendation_job_001"],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                }
            ],
            "history": [],
        },
    )

    import pytest

    with pytest.raises(RuntimeError, match="broll refresh exploded"):
        runner.start_editing_session_partial_regeneration(
            project_id=project.project_id,
            session_id=saved_session["session_id"],
            segment_ids=["seg_001"],
            fields=["broll"],
            expected_revision=saved_session["session_revision"],
        )

    failed_job = store.list_jobs(project_id=project.project_id)[0]
    assert failed_job["job_type"] == "partial_regeneration"
    assert failed_job["status"] == "failed"
    assert failed_job["error_message"] == "broll refresh exploded"


def test_partial_regeneration_pipeline_carries_forward_previous_regeneration_results(tmp_path: Path) -> None:
    class RecordingBrollRecommender:
        def recommend(self, request):  # noqa: ANN001
            del request
            return [
                SimpleNamespace(
                    target_segment_id="seg_002",
                    selected_asset_id="asset_regenerated_002",
                    score=0.88,
                    reason="Regenerated B-roll",
                    auto_apply_allowed=True,
                    review_required=False,
                    payload={},
                )
            ]

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Chaining Project")
    runner = _LocalPipelineRunner(store, broll_recommender=RecordingBrollRecommender())

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": ["broll_recommendation_job_001"],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                },
            ],
            "history": [],
        },
    )

    first = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_002"],
        fields=["broll"],
        expected_revision=saved_session["session_revision"],
    )
    after_first = runner.get_editing_session(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
    )
    updated_session = runner.update_editing_session_segment_caption(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_id="seg_002",
        caption_text="Caption two updated",
        expected_revision=after_first["session_revision"],
    )
    second = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_002"],
        fields=["caption"],
        expected_revision=updated_session["session_revision"],
    )
    first_result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=first["job_id"])
    second_result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=second["job_id"])

    first_broll = next(track for track in first_result["timeline"]["tracks"] if track["track_type"] == "broll")
    second_broll = next(track for track in second_result["timeline"]["tracks"] if track["track_type"] == "broll")

    assert first_broll["clips"][0]["asset_uri"].endswith("/assets/asset_regenerated_002")
    assert second_broll["clips"][0]["asset_uri"].endswith("/assets/asset_regenerated_002")


def test_partial_regeneration_pipeline_preserves_overlay_shape_when_refreshing_visual_overlay(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Overlay Project")
    runner = _LocalPipelineRunner(store)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "export_overlays": [
                {
                    "segment_id": "seg_001",
                    "overlay_type": "hook_title",
                    "text": "Start strong",
                    "start_sec": 0.0,
                    "end_sec": 1.5,
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [{"overlay_type": "hook_title", "asset_id": "asset_image_001"}],
                    "music_override": None,
                }
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["visual_overlay"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["timeline"]["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "hook_title",
            "text": "Start strong",
            "start_sec": 0.0,
            "end_sec": 1.5,
            "asset_id": "asset_image_001",
        }
    ]


def test_partial_regeneration_pipeline_clears_target_visual_overlays_when_session_state_is_empty(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Visual Clear Project")
    runner = _LocalPipelineRunner(store)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "export_overlays": [
                {
                    "segment_id": "seg_001",
                    "overlay_type": "hook_title",
                    "text": "Remove me",
                    "start_sec": 0.0,
                    "end_sec": 1.5,
                },
                {
                    "segment_id": "seg_002",
                    "overlay_type": "hook_title",
                    "text": "Keep me",
                    "start_sec": 2.0,
                    "end_sec": 3.0,
                },
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["visual_overlay"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["timeline"]["export_overlays"] == [
        {
            "segment_id": "seg_002",
            "overlay_type": "hook_title",
            "text": "Keep me",
            "start_sec": 2.0,
            "end_sec": 3.0,
        }
    ]


def test_partial_regeneration_pipeline_preserves_explanation_overlay_shape(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Explanation Project")
    runner = _LocalPipelineRunner(store)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "export_overlays": [
                {
                    "segment_id": "seg_001",
                    "overlay_type": "explanation_card",
                    "title": "Legacy title",
                    "body": "Legacy body",
                    "text": "Legacy title: Legacy body",
                    "start_sec": 0.0,
                    "end_sec": 1.5,
                },
                {
                    "segment_id": "seg_002",
                    "overlay_type": "hook_title",
                    "text": "Keep me",
                    "start_sec": 2.0,
                    "end_sec": 3.0,
                },
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "explanation_card",
                            "title": "Fresh title",
                            "body": "Fresh body",
                            "text": "Fresh title: Fresh body",
                        }
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["explanation_card"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["timeline"]["export_overlays"] == [
        {
            "segment_id": "seg_002",
            "overlay_type": "hook_title",
            "text": "Keep me",
            "start_sec": 2.0,
            "end_sec": 3.0,
        },
        {
            "segment_id": "seg_001",
            "overlay_type": "explanation_card",
            "title": "Fresh title",
            "body": "Fresh body",
            "text": "Fresh title: Fresh body",
            "start_sec": 0.0,
            "end_sec": 1.5,
        },
    ]


def test_partial_regeneration_pipeline_preserves_image_and_table_overlay_shapes(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Rich Overlay Project")
    runner = _LocalPipelineRunner(store)

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        }
                    ],
                }
            ],
            "export_overlays": [
                {
                    "segment_id": "seg_001",
                    "overlay_type": "image_card",
                    "asset_id": "asset_image_old",
                    "text": "Old image",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                },
                {
                    "segment_id": "seg_001",
                    "overlay_type": "table_card",
                    "columns": ["Old"],
                    "rows": [["1"]],
                    "text": "Old table",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                },
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [
                        {
                            "overlay_type": "image_card",
                            "asset_id": "asset_image_new",
                            "text": "Fresh image",
                        },
                        {
                            "overlay_type": "table_card",
                            "columns": ["Metric", "Value"],
                            "rows": [["CTR", "4.2%"]],
                            "text": "Metric | Value\nCTR | 4.2%",
                        },
                    ],
                    "music_override": None,
                    "tts_replacement": None,
                }
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["image_overlay", "table_overlay"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["timeline"]["export_overlays"] == [
        {
            "segment_id": "seg_001",
            "overlay_type": "image_card",
            "asset_id": "asset_image_new",
            "text": "Fresh image",
            "start_sec": 0.0,
            "end_sec": 1.0,
        },
        {
            "segment_id": "seg_001",
            "overlay_type": "table_card",
            "columns": ["Metric", "Value"],
            "rows": [["CTR", "4.2%"]],
            "text": "Metric | Value\nCTR | 4.2%",
            "start_sec": 1.0,
            "end_sec": 2.0,
        },
    ]


def test_partial_regeneration_pipeline_applies_tts_replacement_as_review_blocked_narration_change(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration TTS Project")
    runner = _LocalPipelineRunner(store)
    tts_audio = tmp_path / "tts-approved-001.wav"
    tts_audio.write_bytes(b"tts wav data")
    tts_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.GENERATED_TTS_AUDIO,
        source_path=tts_audio,
    )

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": {
                        "recommendation_id": "rec_tts_seg_001",
                        "asset_id": tts_asset.asset_id,
                    },
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["tts_replacement"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["downstream_steps"] == ["tts_refresh", "timeline_build"]
    assert result["timeline"]["pending_recommendations"] == []
    assert result["timeline"]["applied_recommendations"] == [
        {
            "recommendation_id": "rec_tts_seg_001",
            "target_segment_id": "seg_001",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": tts_asset.asset_id,
            "score": 1.0,
            "reason": "Manual TTS replacement selection from editing session.",
            "auto_apply_allowed": True,
            "review_required": False,
                "payload": {
                    "selection_source": "editing_session",
                    "selected_asset_uri": tts_asset.storage_uri,
                    "provider_trace": {
                        "routing_mode": "single_provider",
                        "final_provider": "editing_session_manual",
                    "fallback_reasons": [],
                },
            },
            "provider_trace": {
                "routing_mode": "single_provider",
                "final_provider": "editing_session_manual",
                "fallback_reasons": [],
            },
            "created_at": result["timeline"]["applied_recommendations"][0]["created_at"],
        }
    ]
    assert result["timeline"]["tracks"][0]["track_type"] == "narration"
    assert result["timeline"]["tracks"][0]["clips"][0]["asset_uri"] == tts_asset.storage_uri


def test_partial_regeneration_pipeline_applies_approved_tts_replacement_to_target_narration_only(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Partial Regeneration Approved TTS Project")
    runner = _LocalPipelineRunner(store)
    tts_audio = tmp_path / "tts-approved-002.wav"
    tts_audio.write_bytes(b"tts wav data 2")
    tts_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.GENERATED_TTS_AUDIO,
        source_path=tts_audio,
    )

    store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "narration_source_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
            "export_overlays": [],
            "lineage": {
                "segment_analysis_job_id": "segment_analysis_job_001",
                "recommendation_job_ids": [],
            },
        },
    )
    saved_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "Caption one",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": {
                        "recommendation_id": "rec_tts_seg_001",
                        "asset_id": tts_asset.asset_id,
                    },
                },
                {
                    "segment_id": "seg_002",
                    "caption_text": "Caption two",
                    "start_sec": 2.0,
                    "end_sec": 4.0,
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "tts_replacement": None,
                },
            ],
            "history": [],
        },
    )

    started = runner.start_editing_session_partial_regeneration(
        project_id=project.project_id,
        session_id=saved_session["session_id"],
        segment_ids=["seg_001"],
        fields=["tts_replacement"],
        expected_revision=saved_session["session_revision"],
    )
    result = runner.get_partial_regeneration_result(project_id=project.project_id, job_id=started["job_id"])

    assert result["timeline"]["pending_recommendations"] == []
    assert result["timeline"]["applied_recommendations"] == [
        {
            "recommendation_id": "rec_tts_seg_001",
            "target_segment_id": "seg_001",
            "recommendation_type": "tts_replacement",
            "selected_asset_id": tts_asset.asset_id,
            "score": 1.0,
            "reason": "Manual TTS replacement selection from editing session.",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {
                "selection_source": "editing_session",
                "selected_asset_uri": tts_asset.storage_uri,
                "provider_trace": {
                    "routing_mode": "single_provider",
                    "final_provider": "editing_session_manual",
                    "fallback_reasons": [],
                },
            },
            "provider_trace": {
                "routing_mode": "single_provider",
                "final_provider": "editing_session_manual",
                "fallback_reasons": [],
            },
            "created_at": result["timeline"]["applied_recommendations"][0]["created_at"],
        }
    ]
    assert [clip["asset_uri"] for clip in result["timeline"]["tracks"][0]["clips"]] == [
        tts_asset.storage_uri,
        f"local://projects/{project.project_id}/segments/seg_002",
    ]
