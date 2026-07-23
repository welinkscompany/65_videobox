from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore


def _session() -> dict:
    return {
        "project_id": "project_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "caption_style": {"font_family": "Pretendard", "font_size": 42, "font_color": "#ffffff"},
        "segments": [
            {
                "segment_id": "seg_001",
                "caption_text": "첫 문장",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "cut_action": "keep",
                "review_required": False,
                "broll_override": {"asset_id": "broll_001"},
                "music_override": {"asset_id": "music_001"},
                "sfx_override": {"asset_id": "sfx_001"},
                "tts_replacement": {"asset_id": "tts_001"},
                "visual_overlays": [{"overlay_type": "image", "asset_id": "overlay_001"}],
            },
            {
                "segment_id": "seg_002",
                "caption_text": "둘째 문장",
                "start_sec": 2.0,
                "end_sec": 4.0,
                "cut_action": "keep",
                "review_required": False,
                "broll_override": {"asset_id": "broll_002"},
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
                "visual_overlays": [],
            },
            {
                "segment_id": "seg_003",
                "caption_text": "셋째 문장",
                "start_sec": 4.0,
                "end_sec": 6.0,
                "cut_action": "keep",
                "review_required": False,
                "broll_override": None,
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
                "visual_overlays": [],
            },
        ],
        "history": [],
    }


def test_split_enforces_minimum_duration_and_preserves_editable_identity_and_lineage() -> None:
    from videobox_core_engine.editing_session import split_segment

    session = _session()

    with pytest.raises(ValueError, match="0.2"):
        split_segment(session=session, segment_id="seg_001", split_sec=0.19)

    updated = split_segment(session=session, segment_id="seg_001", split_sec=1.0)

    left, right = updated["segments"][:2]
    assert left["segment_id"] == "seg_001"
    assert right["segment_id"] != "seg_001"
    assert (left["start_sec"], left["end_sec"]) == (0.0, 1.0)
    assert (right["start_sec"], right["end_sec"]) == (1.0, 2.0)
    for key in ("caption_text", "broll_override", "music_override", "sfx_override", "tts_replacement", "visual_overlays"):
        assert left[key] == session["segments"][0][key]
        assert right[key] == session["segments"][0][key]
    assert left["lineage"]["root_segment_id"] == "seg_001"
    assert right["lineage"]["parent_segment_id"] == "seg_001"
    assert updated["history"][-1]["mutation_type"] == "segment_split"
    assert "inverse_payload" in updated["history"][-1]


def test_visual_overlay_clear_removes_direct_and_related_windows_from_materialized_manifest() -> None:
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import clear_segment_visual_overlays
    from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

    project_id = "project_001"
    session = {
        "project_id": project_id,
        "session_id": "session_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [{
            "segment_id": "visible-merged",
            "start_sec": 0.0,
            "end_sec": 4.0,
            "visual_overlays": [{"overlay_type": "explanation_card", "text": "direct"}],
            "content_windows": [
                {
                    "source_segment_id": "source-left",
                    "start_offset_sec": 0.0,
                    "duration_sec": 2.0,
                    "visual_overlays": [{"overlay_type": "explanation_card", "text": "left"}],
                },
                {
                    "source_segment_id": "source-right",
                    "start_offset_sec": 2.0,
                    "duration_sec": 2.0,
                    "visual_overlays": [{"overlay_type": "table_overlay", "text": "right"}],
                },
            ],
        }],
        "history": [],
    }
    timeline = {
        "project_id": project_id,
        "timeline_id": "timeline_001",
        "version": "v1",
        "source_session_id": "session_001",
        "source_session_revision": 1,
        "output": {"width": 1080, "height": 1920, "duration_sec": 4.0},
        "tracks": [],
    }

    cleared = clear_segment_visual_overlays(session=session, segment_id="visible-merged")
    materialized = materialize_editing_session_timeline(
        timeline=timeline,
        editing_session=cleared,
        project_id=project_id,
    )
    manifest = build_editor_playback_manifest(
        project_id=project_id,
        session=cleared,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project_id}/assets",
    )

    assert cleared["segments"][0]["visual_overlays"] == []
    assert all(window["visual_overlays"] == [] for window in cleared["segments"][0]["content_windows"])
    assert materialized["export_overlays"] == []
    assert not any(track["track_type"] == "overlay" for track in materialized["tracks"])
    assert not any(track["track_type"] == "overlay" for track in manifest["tracks"])


def test_split_overlay_updates_are_visible_segment_scoped_through_materialize_and_manifest() -> None:
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import (
        remove_segment_image_overlay,
        split_segment,
        update_segment_image_overlay,
    )
    from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

    project_id = "project_001"
    session = _session()
    session["project_id"] = project_id
    session["session_id"] = "session_001"
    session["timeline_id"] = "timeline_001"
    session["caption_style"] = {}
    split = split_segment(session=session, segment_id="seg_001", split_sec=1.0)
    left_id, right_id = [segment["segment_id"] for segment in split["segments"][:2]]
    with_left = update_segment_image_overlay(
        session=split,
        segment_id=left_id,
        asset_id="image-left",
        text="left",
    )
    with_right = update_segment_image_overlay(
        session=with_left,
        segment_id=right_id,
        asset_id="image-right",
        text="right",
    )
    right_only = remove_segment_image_overlay(session=with_right, segment_id=left_id)
    timeline = {
        "project_id": project_id,
        "timeline_id": "timeline_001",
        "version": "v1",
        "source_session_id": "session_001",
        "source_session_revision": right_only["session_revision"],
        "output": {"width": 1080, "height": 1920, "duration_sec": 6.0},
        "tracks": [],
    }

    materialized = materialize_editing_session_timeline(
        timeline=timeline,
        editing_session=right_only,
        project_id=project_id,
    )
    manifest = build_editor_playback_manifest(
        project_id=project_id,
        session=right_only,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project_id}/assets",
    )
    materialized_overlays = [
        clip
        for track in materialized["tracks"]
        if track["track_type"] == "overlay"
        for clip in track["clips"]
    ]
    manifest_overlays = [
        clip
        for track in manifest["tracks"]
        if track["track_type"] == "overlay"
        for clip in track["clips"]
    ]

    assert right_only["segments"][0]["visual_overlays"] == []
    assert right_only["segments"][0]["content_windows"][0]["visual_overlays"] == []
    assert right_only["segments"][1]["visual_overlays"][0]["asset_id"] == "image-right"
    assert right_only["segments"][1]["content_windows"][0]["visual_overlays"][0]["asset_id"] == "image-right"
    assert [clip["segment_id"] for clip in materialized_overlays] == [right_id]
    assert materialized_overlays[0]["overlay_payload"]["source_segment_id"] == "seg_001"
    assert [clip["segment_id"] for clip in manifest_overlays] == [right_id]
    assert manifest_overlays[0]["overlay_payload"]["source_segment_id"] == "seg_001"


def test_merge_requires_adjacent_touching_segments_and_keeps_all_source_media_lineage() -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments

    session = _session()

    with pytest.raises(ValueError, match="adjacent"):
        merge_adjacent_segments(session=session, left_segment_id="seg_001", right_segment_id="seg_003")

    updated = merge_adjacent_segments(session=session, left_segment_id="seg_001", right_segment_id="seg_002")

    merged = updated["segments"][0]
    assert merged["segment_id"] == "seg_001"
    assert (merged["start_sec"], merged["end_sec"]) == (0.0, 4.0)
    assert merged["caption_text"] == "첫 문장\n둘째 문장"
    assert merged["lineage"]["source_segment_ids"] == ["seg_001", "seg_002"]
    assert merged["media_lineage"]["broll"] == ["broll_001", "broll_002"]
    assert merged["media_lineage"]["music"] == ["music_001"]
    assert updated["history"][-1]["mutation_type"] == "segment_merge"


@pytest.mark.parametrize(("left_action", "right_action"), [("remove", "keep"), ("keep", "remove"), ("keep", "review")])
def test_merge_rejects_removed_or_different_cut_actions(left_action: str, right_action: str) -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments

    session = _session()
    session["segments"][0]["cut_action"] = left_action
    session["segments"][1]["cut_action"] = right_action

    with pytest.raises(ValueError, match="same non-remove"):
        merge_adjacent_segments(session=session, left_segment_id="seg_001", right_segment_id="seg_002")


def test_reorder_and_bounds_reject_overlap_but_allow_a_complete_non_overlapping_relayout() -> None:
    from videobox_core_engine.editing_session import reorder_segments, set_segment_bounds

    session = _session()

    with pytest.raises(ValueError, match="overlap"):
        set_segment_bounds(session=session, segment_id="seg_002", start_sec=1.5, end_sec=3.5)
    with pytest.raises(ValueError, match="complete permutation"):
        reorder_segments(session=session, segment_ids=["seg_002", "seg_001"])

    updated = reorder_segments(
        session=session,
        segment_ids=["seg_002", "seg_001", "seg_003"],
        bounds_by_id={
            "seg_002": {"start_sec": 0.0, "end_sec": 2.0},
            "seg_001": {"start_sec": 2.0, "end_sec": 4.0},
            "seg_003": {"start_sec": 4.0, "end_sec": 6.0},
        },
    )

    assert [segment["segment_id"] for segment in updated["segments"]] == ["seg_002", "seg_001", "seg_003"]
    assert [segment["start_sec"] for segment in updated["segments"]] == [0.0, 2.0, 4.0]


def test_undo_redo_keeps_last_100_edit_events_and_ignores_non_edit_operations() -> None:
    from videobox_core_engine.editing_session import record_non_undoable_operation, redo, set_segment_bounds, undo

    session = _session()
    for index in range(101):
        session = set_segment_bounds(
            session=session,
            segment_id="seg_003",
            start_sec=4.0,
            end_sec=6.0 + (index + 1) * 0.001,
        )
    session = record_non_undoable_operation(session=session, operation_type="render")
    session = record_non_undoable_operation(session=session, operation_type="import")

    assert len(session["undo_stack"]) == 10
    assert session["history"][-2:][0]["mutation_type"] == "render"
    assert session["history"][-1]["mutation_type"] == "import"

    undone = undo(session=session)
    redone = redo(session=undone)

    assert len(undone["redo_stack"]) == 1
    assert redone["segments"] == session["segments"]
    assert len(redone["undo_stack"]) == 10


def test_fixed_track_read_model_and_selected_range_preview_include_only_selected_caption_style_and_overlay() -> None:
    from videobox_core_engine.editing_session import build_fixed_track_timeline, build_selected_range_preview

    session = _session()
    session["segments"][0]["caption_style"] = {"font_family": "Noto Sans KR", "font_size": 56, "font_color": "#00ff00"}

    timeline = build_fixed_track_timeline(session=session)
    preview = build_selected_range_preview(session=session, start_sec=0.5, end_sec=1.5)

    assert [track["role"] for track in timeline["tracks"]] == ["narration", "broll", "bgm", "sfx", "overlay"]
    assert preview["start_sec"] == 0.5
    assert preview["end_sec"] == 1.5
    assert [caption["segment_id"] for caption in preview["captions"]] == ["seg_001"]
    assert preview["captions"][0]["caption_style"]["font_color"] == "#00ff00"
    assert preview["overlays"] == [{"segment_id": "seg_001", "overlay_type": "image", "asset_id": "overlay_001"}]
    assert "seg_002" not in str(preview)


def test_timeline_undo_state_and_lineage_survive_editing_session_reload(tmp_path: Path) -> None:
    from videobox_core_engine.editing_session import split_segment
    from videobox_storage.local_project_store import LocalProjectStore

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline persistence")
    updated = split_segment(session=_session(), segment_id="seg_001", split_sec=1.0)
    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload=updated,
    )

    reloaded = store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])

    assert len(reloaded["undo_stack"]) == 1
    assert reloaded["undo_stack"][0]["inverse_payload"]["segments"][0]["segment_id"] == "seg_001"
    assert reloaded["segments"][1]["lineage"]["parent_segment_id"] == "seg_001"


def test_timeline_mutation_api_is_revisioned_and_selected_preview_returns_only_fixed_tracks(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline API")
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload=_session())
    client = TestClient(create_app(projects_root=tmp_path))
    root = f"/api/projects/{project.project_id}/editing-sessions/{saved['session_id']}"

    split = client.post(f"{root}/segments/seg_001/split", json={"split_sec": 1.0, "expected_revision": 1})

    assert split.status_code == 200, split.text
    body = split.json()
    assert body["session_revision"] == 2
    assert len(body["segments"]) == 4
    stale = client.post(f"{root}/undo", json={"expected_revision": 1})
    assert stale.status_code == 409
    preview = client.post(f"{root}/selected-range-preview", json={"start_sec": 0.5, "end_sec": 1.5})
    assert preview.status_code == 200, preview.text
    assert [track["role"] for track in preview.json()["timeline"]["tracks"]] == ["narration", "broll", "bgm", "sfx", "overlay"]
    assert preview.json()["captions"][0]["segment_id"] == "seg_001"


def test_merge_api_rejects_removed_child_without_mutating_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Removed child merge")
    session_payload = _session()
    session_payload["segments"][1]["cut_action"] = "remove"
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload=session_payload)
    client = TestClient(create_app(projects_root=tmp_path))
    root = f"/api/projects/{project.project_id}/editing-sessions/{saved['session_id']}"

    response = client.post(
        f"{root}/segments/merge",
        json={"left_segment_id": "seg_001", "right_segment_id": "seg_002", "expected_revision": 1},
    )

    assert response.status_code == 422
    reloaded = store.get_editing_session(project_id=project.project_id, session_id=saved["session_id"])
    assert reloaded["session_revision"] == 1
    assert [segment["segment_id"] for segment in reloaded["segments"]] == ["seg_001", "seg_002", "seg_003"]


def test_manual_caption_api_increments_revision_and_rejects_a_stale_expected_revision(tmp_path: Path) -> None:
    """A manual API mutation must use the same durable CAS boundary as Task 11 apply."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Manual API CAS")
    saved = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload=_session(),
    )
    client = TestClient(create_app(projects_root=tmp_path))
    root = f"/api/projects/{project.project_id}/editing-sessions/{saved['session_id']}"

    first = client.patch(
        f"{root}/segments/seg_001/caption",
        json={"caption_text": "Fresh manual caption", "expected_revision": saved["session_revision"]},
    )

    assert first.status_code == 200, first.text
    assert first.json()["session_revision"] == saved["session_revision"] + 1
    assert first.json()["segments"][0]["caption_text"] == "Fresh manual caption"
    stale = client.patch(
        f"{root}/segments/seg_001/caption",
        json={"caption_text": "Lost stale caption", "expected_revision": saved["session_revision"]},
    )
    assert stale.status_code == 409
    assert store.get_editing_session(
        project_id=project.project_id,
        session_id=saved["session_id"],
    )["segments"][0]["caption_text"] == "Fresh manual caption"


def test_structural_timeline_regeneration_is_an_explicit_supported_output_step() -> None:
    from videobox_core_engine.editing_session import build_partial_regeneration_request, split_segment

    session = split_segment(session=_session(), segment_id="seg_001", split_sec=1.0)

    request = build_partial_regeneration_request(
        session=session,
        segment_ids=["seg_001"],
        fields=["timeline_structure"],
    )

    assert request["fields"] == ["timeline_structure"]
    assert request["downstream_steps"] == ["timeline_build"]
