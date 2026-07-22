from __future__ import annotations

from copy import deepcopy

import pytest

from videobox_core_engine.editing_session import redo, set_timeline_placement_overrides, undo
from videobox_core_engine.timeline_placements import apply_placement_changes, apply_timeline_placement_overrides, collect_timeline_placements, placement_id


def _timeline() -> dict[str, object]:
    return {
        "tracks": [
            {"track_type": "broll", "clips": [{"clip_id": "b-1", "start_sec": 0.0, "end_sec": 2.0}]},
            {"track_type": "bgm", "clips": [{"clip_id": "m-1", "start_sec": 0.0, "end_sec": 3.0}]},
            {"track_type": "sfx", "clips": [{"clip_id": "s-1", "start_sec": 1.0, "end_sec": 2.0}]},
            {"track_type": "overlay", "clips": [{"clip_id": "o-1", "start_sec": 1.0, "end_sec": 2.0}]},
        ],
        "session_captions": [{"caption_id": "c-1", "start_sec": 0.0, "end_sec": 2.0}],
    }


def test_collects_each_mutable_media_clip_but_not_narration_linked_captions() -> None:
    placements = collect_timeline_placements(timeline=_timeline())

    assert set(placements) == {"broll:b-1", "bgm:m-1", "sfx:s-1", "overlay:o-1"}
    assert placements["overlay:o-1"] == {
        "placement_id": "overlay:o-1", "kind": "overlay", "start_sec": 1.0, "end_sec": 2.0,
    }


def test_normalizes_frame_values_without_mutating_caller_inputs() -> None:
    placements = collect_timeline_placements(timeline=_timeline())
    frozen_placements = deepcopy(placements)
    changes = [
        {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0.01, "end_sec": 1.99},
    ]
    frozen_changes = deepcopy(changes)

    result = apply_placement_changes(
        placements=placements, changes=changes, output_duration_sec=3, fps_num=30, fps_den=1,
    )

    assert result == {
        "broll:b-1": {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0.0, "end_sec": 2.0},
    }
    assert placements == frozen_placements
    assert changes == frozen_changes


@pytest.mark.parametrize(
    "changes, error",
    [
        ([], "timeline_placement_changes_required"),
        ([{"placement_id": "missing", "kind": "broll", "start_sec": 0, "end_sec": 1}], "timeline_placement_unknown"),
        ([{"placement_id": "broll:b-1", "kind": "sfx", "start_sec": 0, "end_sec": 1}], "timeline_placement_kind_mismatch"),
        ([{"placement_id": "broll:b-1", "kind": "broll", "start_sec": -1, "end_sec": 1}], "timeline_placement_out_of_range"),
        ([{"placement_id": "broll:b-1", "kind": "broll", "start_sec": -0.01, "end_sec": 1}], "timeline_placement_out_of_range"),
        ([{"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0, "end_sec": 0.01}], "timeline_placement_frame_span_invalid"),
        ([{"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0, "end_sec": float("inf")}], "timeline_placement_not_finite"),
        ([{"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0, "end_sec": 1}] * 2, "timeline_placement_duplicate"),
    ],
)
def test_rejects_invalid_batch_without_normalizing_it(changes: list[dict[str, object]], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        apply_placement_changes(
            placements=collect_timeline_placements(timeline=_timeline()), changes=changes,
            output_duration_sec=3, fps_num=30, fps_den=1,
        )


def test_caption_placement_identity_remains_valid_for_editor_manifests() -> None:
    assert placement_id(kind="caption", base_id="c-1") == "caption:c-1"


def test_rejects_new_caption_placement_change_as_unknown() -> None:
    with pytest.raises(ValueError, match="timeline_placement_unknown"):
        apply_placement_changes(
            placements=collect_timeline_placements(timeline=_timeline()),
            changes=[{"placement_id": "caption:c-1", "kind": "caption", "start_sec": 1.0, "end_sec": 2.0}],
            output_duration_sec=3, fps_num=30, fps_den=1,
        )


def test_placement_overrides_are_one_undoable_session_change() -> None:
    session = {"session_revision": 1, "segments": [{"segment_id": "n-1", "start_sec": 0.0, "end_sec": 2.0}], "history": [], "undo_stack": [], "redo_stack": []}
    overrides = {"broll:b-1": {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 2.0, "end_sec": 4.0}}

    updated = set_timeline_placement_overrides(session=session, overrides=overrides)

    assert updated["session_revision"] == 2
    assert updated["segments"] == session["segments"]
    assert updated["timeline_placement_overrides"] == overrides
    assert undo(session=updated).get("timeline_placement_overrides") is None
    assert redo(session=undo(session=updated))["timeline_placement_overrides"] == overrides


def test_legacy_caption_override_is_inert_while_broll_override_materializes() -> None:
    timeline = _timeline()
    timeline["tracks"] = list(timeline["tracks"]) + [{"track_type": "narration", "clips": [{"clip_id": "n-1", "start_sec": 0.0, "end_sec": 3.0}]}]
    timeline["session_captions"] = [{"caption_id": "c-1", "text": "자막", "start_sec": 0.0, "end_sec": 2.0, "style": {"font": "x"}}]

    result = apply_timeline_placement_overrides(timeline=timeline, overrides={
        "broll:b-1": {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 1.0, "end_sec": 3.0},
        "caption:c-1": {"placement_id": "caption:c-1", "kind": "caption", "start_sec": 1.0, "end_sec": 2.0},
    })

    broll = next(track for track in result["tracks"] if track["track_type"] == "broll")["clips"][0]
    assert (broll["start_sec"], broll["end_sec"]) == (1.0, 3.0)
    assert result["session_captions"][0] == {"caption_id": "c-1", "text": "자막", "start_sec": 0.0, "end_sec": 2.0, "style": {"font": "x"}}


def test_rejects_unknown_non_caption_override_during_materialization() -> None:
    with pytest.raises(ValueError, match="timeline_placement_unknown"):
        apply_timeline_placement_overrides(timeline=_timeline(), overrides={
            "broll:missing": {"placement_id": "broll:missing", "kind": "broll", "start_sec": 0.0, "end_sec": 1.0},
        })


def test_applies_overrides_to_non_asset_export_overlays() -> None:
    timeline = _timeline()
    timeline["export_overlays"] = [{"clip_id": "card-1", "segment_id": "seg-1", "start_sec": 0.0, "end_sec": 2.0, "overlay_type": "explanation_card"}]

    placements = collect_timeline_placements(timeline=timeline)
    result = apply_timeline_placement_overrides(timeline=timeline, overrides={
        "overlay:card-1": {"placement_id": "overlay:card-1", "kind": "overlay", "start_sec": 1.0, "end_sec": 2.0},
    })

    assert placements["overlay:card-1"]["kind"] == "overlay"
    assert result["export_overlays"][0]["start_sec"] == 1.0
