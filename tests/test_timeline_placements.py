from __future__ import annotations

from copy import deepcopy

import pytest

from videobox_core_engine.timeline_placements import apply_placement_changes, collect_timeline_placements


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


def test_collects_each_media_clip_and_caption_by_stable_kind_and_base_identity() -> None:
    placements = collect_timeline_placements(timeline=_timeline())

    assert set(placements) == {"broll:b-1", "bgm:m-1", "sfx:s-1", "overlay:o-1", "caption:c-1"}
    assert placements["overlay:o-1"] == {
        "placement_id": "overlay:o-1", "kind": "overlay", "start_sec": 1.0, "end_sec": 2.0,
    }


def test_normalizes_frame_values_without_mutating_caller_inputs() -> None:
    placements = collect_timeline_placements(timeline=_timeline())
    frozen_placements = deepcopy(placements)
    changes = [
        {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0.01, "end_sec": 1.99},
        {"placement_id": "caption:c-1", "kind": "caption", "start_sec": 0.99, "end_sec": 2.99},
    ]
    frozen_changes = deepcopy(changes)

    result = apply_placement_changes(
        placements=placements, changes=changes, output_duration_sec=3, fps_num=30, fps_den=1,
    )

    assert result == {
        "broll:b-1": {"placement_id": "broll:b-1", "kind": "broll", "start_sec": 0.0, "end_sec": 2.0},
        "caption:c-1": {"placement_id": "caption:c-1", "kind": "caption", "start_sec": 1.0, "end_sec": 3.0},
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


def test_rejects_missing_or_duplicate_caption_identity() -> None:
    missing = _timeline()
    missing["session_captions"] = [{"start_sec": 0.0, "end_sec": 1.0}]
    duplicate = _timeline()
    duplicate["session_captions"] = [
        {"caption_id": "c-1", "start_sec": 0.0, "end_sec": 1.0},
        {"caption_id": "c-1", "start_sec": 1.0, "end_sec": 2.0},
    ]

    with pytest.raises(ValueError, match="timeline_placement_identity_invalid"):
        collect_timeline_placements(timeline=missing)
    with pytest.raises(ValueError, match="timeline_placement_duplicate"):
        collect_timeline_placements(timeline=duplicate)
