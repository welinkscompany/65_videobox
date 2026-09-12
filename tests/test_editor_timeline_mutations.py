from __future__ import annotations

from videobox_core_engine.editing_session import apply_yujin_editing_proposal

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


def test_ripple_speed_shortens_one_real_editing_session_scene_and_ripples_later_scenes() -> None:
    """배속은 trim이 아니다. 만든 세션의 원본 말은 남기고 표시 길이만 줄인다."""
    from videobox_core_engine.editing_session import (
        build_editing_session,
        redo,
        set_segment_ripple_playback_rate,
        undo,
    )

    source_timeline = {"timeline_id": "timeline_ripple", "tracks": []}
    session = build_editing_session(
        project_id="project_ripple",
        timeline=source_timeline,
        segments=[
            {"segment_id": "scene-1", "text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0},
            {"segment_id": "scene-2", "text": "둘째 장면", "start_sec": 4.0, "end_sec": 8.0},
            {"segment_id": "scene-3", "text": "셋째 장면", "start_sec": 8.0, "end_sec": 12.0},
        ],
    )

    doubled = set_segment_ripple_playback_rate(
        session=session,
        segment_id="scene-2",
        rate=2.0,
    )

    first, second, third = doubled["segments"]
    assert (first["start_sec"], first["end_sec"]) == (0.0, 4.0)
    assert (second["start_sec"], second["end_sec"]) == (4.0, 6.0)
    assert (third["start_sec"], third["end_sec"]) == (6.0, 10.0)
    assert second["ripple_playback_rate"] == 2.0
    # source_slices는 말과 영상의 원본 4초를 가리킨다. 이걸 2초로 자르면
    # "속도를 올린다"가 아니라 "뒤 절반을 버린다"가 된다.
    assert second["source_slices"] == [{
        "segment_id": "scene-2", "source_offset_sec": 0.0, "duration_sec": 4.0,
    }]
    assert doubled["history"][-1]["mutation_type"] == "segment_ripple_speed_update"

    restored = set_segment_ripple_playback_rate(
        session=doubled,
        segment_id="scene-2",
        rate=1.0,
    )
    assert [(item["start_sec"], item["end_sec"]) for item in restored["segments"]] == [
        (0.0, 4.0), (4.0, 8.0), (8.0, 12.0),
    ]

    undone = undo(session=doubled)
    redone = redo(session=undone)
    assert [(item["start_sec"], item["end_sec"]) for item in undone["segments"]] == [
        (0.0, 4.0), (4.0, 8.0), (8.0, 12.0),
    ]
    assert [(item["start_sec"], item["end_sec"]) for item in redone["segments"]] == [
        (0.0, 4.0), (4.0, 6.0), (6.0, 10.0),
    ]


# **1.25와 3.0은 이제 정상이다(2026-09-04).** owner 지시로 리플 배속을 캡컷처럼
# 숫자칸 범위(0.25~4)로 넓혔다 -- 렌더의 `_atempo_chain`이 처음부터 그 범위를
# 감당했고 검증만 셋으로 좁혀 놨던 것이다. 여기서 지키는 것은 "렌더가 못 내는
# 값은 거부한다"이지 특정 세 값이 아니었으므로, 범위 밖만 남긴다.
# 넓힌 쪽은 `tests/test_ripple_speed_range.py`가 따로 지킨다.
@pytest.mark.parametrize("rate", [0.0, -1.0, 0.1, 5.0, float("nan")])
def test_ripple_speed_refuses_an_unsupported_rate_without_mutating_the_session(rate: float) -> None:
    from videobox_core_engine.editing_session import build_editing_session, set_segment_ripple_playback_rate

    session = build_editing_session(
        project_id="project_ripple",
        timeline={"timeline_id": "timeline_ripple", "tracks": []},
        segments=[{"segment_id": "scene-1", "text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0}],
    )

    with pytest.raises(ValueError, match="segment_ripple_playback_rate_invalid"):
        set_segment_ripple_playback_rate(session=session, segment_id="scene-1", rate=rate)

    assert session["segments"][0].get("ripple_playback_rate") is None
    assert session["history"] == []


def test_splitting_a_scene_moves_the_broll_start_to_the_split_point() -> None:
    """긴 영상 하나를 장면마다 나눠 쓰는 길. **쪼갠 뒤 장면은 자기 순간을 가리켜야 한다.**

    2026-09-12 대표님 실제 영상(494.837초) 실측에서 잡힌 결함이다. 자료실 영상을
    장면에 깔고(`broll_override`) 장면을 94개로 쪼갰더니 **94개 전부가
    `trim_start_sec: 0.0`**이었다 -- 렌더가 b-roll의 시작점으로 읽는 값이 그것이라,
    나온 숏폼은 원본 맨 앞 몇 초를 열 번 반복한 영상이었다(픽셀로 확인).
    `source_slices`·`source_offset_sec`는 정확히 옮겨지는데 렌더는 그것을 안 읽는다.

    직접 선택(`segment["broll_override"]`)과 창(`media_windows`) **둘 다** 봐야
    한다. 렌더는 직접 선택을 먼저 보고, 합치기는 창에 권한을 넘긴다.
    """
    from videobox_core_engine.editing_session import split_segment

    session = {
        "project_id": "project_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [
            {
                "segment_id": "scene-1",
                "caption_text": "",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "cut_action": "keep",
                "review_required": False,
                "broll_override": {
                    "asset_id": "asset_long_video",
                    "media_controls": {"fit": "fit", "loop": True, "trim_start_sec": 0.0},
                },
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
            }
        ],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
    }

    updated = split_segment(session=session, segment_id="scene-1", split_sec=8.0)
    left, right = updated["segments"]

    assert left["broll_override"]["media_controls"]["trim_start_sec"] == 0.0
    assert right["broll_override"]["media_controls"]["trim_start_sec"] == 8.0

    # 두 번째 쪼개기는 앞의 이동 위에 쌓인다.
    again = split_segment(session=updated, segment_id=right["segment_id"], split_sec=14.0)
    assert [item["broll_override"]["media_controls"]["trim_start_sec"] for item in again["segments"]] == [0.0, 8.0, 14.0]

    # 창에 권한이 있는 편집본도 같이 움직인다.
    windowed = split_segment(
        session={
            **session,
            "segments": [
                {
                    **session["segments"][0],
                    "broll_override": None,
                    "media_windows": [
                        {
                            "caption_id": "caption-scene-1",
                            "start_offset_sec": 0.0,
                            "duration_sec": 20.0,
                            "broll_override": {
                                "asset_id": "asset_long_video",
                                "media_controls": {"fit": "fit", "loop": True, "trim_start_sec": 0.0},
                            },
                        }
                    ],
                }
            ],
        },
        segment_id="scene-1",
        split_sec=8.0,
    )
    assert [
        item["media_windows"][0]["broll_override"]["media_controls"]["trim_start_sec"]
        for item in windowed["segments"]
    ] == [0.0, 8.0]


def test_dragging_a_scene_start_later_moves_its_broll_start_by_the_same_amount() -> None:
    """경계 편집도 쪼개기와 같은 규칙을 따른다 -- 같은 논리가 두 자리에 있다."""
    from videobox_core_engine.editing_session import set_segment_bounds

    session = {
        "project_id": "project_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [
            {
                "segment_id": "scene-1",
                "caption_text": "",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "cut_action": "keep",
                "review_required": False,
                "source_slices": [
                    {"segment_id": "scene-1", "source_offset_sec": 0.0, "duration_sec": 20.0}
                ],
                "source_slice_basis": [
                    {"segment_id": "scene-1", "source_offset_sec": 0.0, "duration_sec": 20.0}
                ],
                "source_slice_basis_is_proven": True,
                "source_slice_window_start_sec": 0.0,
                "broll_override": {
                    "asset_id": "asset_long_video",
                    "media_controls": {"fit": "fit", "loop": True, "trim_start_sec": 0.0},
                },
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
            }
        ],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
    }

    updated = set_segment_bounds(session=session, segment_id="scene-1", start_sec=5.0, end_sec=20.0)
    assert updated["segments"][0]["broll_override"]["media_controls"]["trim_start_sec"] == 5.0


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
    for key in ("caption_text", "music_override", "sfx_override", "tts_replacement", "visual_overlays"):
        assert left[key] == session["segments"][0][key]
        assert right[key] == session["segments"][0][key]
    # **b-roll은 "무엇을 쓰는가"만 그대로고 "어디서부터"는 움직인다**(2026-09-12).
    # 오른쪽 조각은 원본의 1초 지점부터 시작해야 한다 -- 예전에는 이 값도 통째로
    # 복사돼서 쪼갠 장면이 전부 b-roll의 맨 앞을 다시 보여 줬다.
    assert left["broll_override"] == session["segments"][0]["broll_override"]
    assert right["broll_override"]["asset_id"] == session["segments"][0]["broll_override"]["asset_id"]
    assert right["broll_override"]["media_controls"]["trim_start_sec"] == 1.0
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


def test_ripple_speed_api_is_revisioned_and_keeps_the_whole_source_scene(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Ripple speed API")
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload=_session())
    client = TestClient(create_app(projects_root=tmp_path))
    root = f"/api/projects/{project.project_id}/editing-sessions/{saved['session_id']}"

    response = client.patch(
        f"{root}/segments/seg_002/ripple-playback-rate",
        json={"rate": 2.0, "expected_revision": saved["session_revision"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_revision"] == saved["session_revision"] + 1
    assert [(item["start_sec"], item["end_sec"]) for item in body["segments"]] == [
        (0.0, 2.0), (2.0, 3.0), (3.0, 5.0),
    ]
    assert body["segments"][1]["ripple_playback_rate"] == 2.0
    stale = client.patch(
        f"{root}/segments/seg_002/ripple-playback-rate",
        json={"rate": 1.5, "expected_revision": saved["session_revision"]},
    )
    assert stale.status_code == 409


def test_ripple_speed_api_takes_any_rate_the_renderer_can_produce(tmp_path: Path) -> None:
    """화면 `속도` 칸은 숫자칸이다 -- API도 셋만 받으면 거기서 막힌다.

    2026-09-05 실기 검증에서 잡았다. 엔진은 0.25~4로 넓혔는데 요청 스키마가
    `Literal[1.0, 1.5, 2.0]`으로 남아 있어서 1.25배가 422로 거절됐다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Ripple speed range API")
    saved = store.save_editing_session(project_id=project.project_id, timeline_id="timeline_001", session_payload=_session())
    client = TestClient(create_app(projects_root=tmp_path))
    root = f"/api/projects/{project.project_id}/editing-sessions/{saved['session_id']}"

    accepted = client.patch(
        f"{root}/segments/seg_002/ripple-playback-rate",
        json={"rate": 1.25, "expected_revision": saved["session_revision"]},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["segments"][1]["ripple_playback_rate"] == 1.25

    # 범위 밖은 여전히 막는다 -- 렌더가 못 내는 값이다.
    refused = client.patch(
        f"{root}/segments/seg_002/ripple-playback-rate",
        json={"rate": 9.0, "expected_revision": accepted.json()["session_revision"]},
    )
    assert refused.status_code == 422, refused.text


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


def test_ai_editing_proposal_is_one_undoable_transaction() -> None:
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal
    from videobox_core_engine.editing_session import undo

    proposal = YujinEditingProposal.model_validate({"proposal_id": "p", "base_session_revision": 1, "operations": [{"intent": "set_scene_speed", "segment_id": "seg_001", "rate": 2}, {"intent": "set_caption_text", "segment_id": "seg_001", "text": "새 자막"}]})
    applied = apply_yujin_editing_proposal(session=_session(), proposal=proposal)

    assert len(applied["undo_stack"]) == 1
    assert applied["segments"][0]["caption_text"] == "새 자막"
    assert undo(session=applied)["redo_stack"]


def test_ai_editing_proposal_projection_changes_speed_without_mutating_session_metadata() -> None:
    from videobox_core_engine.editing_session import project_yujin_editing_proposal
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][0]["end_sec"] = 4.0
    session["segments"][1]["start_sec"] = 4.0
    session["segments"][1]["end_sec"] = 6.0
    session["segments"][2]["start_sec"] = 6.0
    session["segments"][2]["end_sec"] = 8.0
    session["output_freshness"] = {"preview": {"is_current": True}}
    session["undo_stack"] = [{"event": "before"}]
    session["redo_stack"] = [{"event": "after"}]
    before = deepcopy(session)
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "speed-preview",
        "base_session_revision": 1,
        "operations": [{"intent": "set_scene_speed", "segment_id": "seg_001", "rate": 2}],
    })

    projected = project_yujin_editing_proposal(session=session, proposal=proposal)

    assert before["segments"][0]["end_sec"] == 4.0
    assert projected["segments"][0]["end_sec"] == 2.0
    assert projected["segments"][1]["start_sec"] == 2.0
    assert projected["session_revision"] == before["session_revision"]
    assert projected["output_freshness"] == before["output_freshness"]
    assert projected["history"] == before["history"]
    assert projected["undo_stack"] == before["undo_stack"]
    assert projected["redo_stack"] == before["redo_stack"]
    assert session == before


def test_ai_editing_proposal_projection_composes_media_removal_and_reorder_without_metadata_changes() -> None:
    from videobox_core_engine.editing_session import project_yujin_editing_proposal
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["output_freshness"] = {"preview": {"is_current": True}}
    session["undo_stack"] = [{"event": "before"}]
    session["redo_stack"] = [{"event": "after"}]
    before = deepcopy(session)
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "media-reorder-preview",
        "base_session_revision": 1,
        "operations": [
            {"intent": "apply_media", "segment_id": "seg_002", "media_type": "sfx", "asset_id": "sfx_002"},
            {"intent": "remove_media", "segment_id": "seg_001", "media_type": "broll"},
            {"intent": "reorder_segments", "segment_ids": ["seg_003", "seg_001", "seg_002"]},
        ],
    })

    projected = project_yujin_editing_proposal(session=session, proposal=proposal)

    assert [item["segment_id"] for item in projected["segments"]] == ["seg_003", "seg_001", "seg_002"]
    assert projected["segments"][1]["broll_override"] is None
    assert projected["segments"][2]["sfx_override"]["asset_id"] == "sfx_002"
    for field in ("session_revision", "output_freshness", "history", "undo_stack", "redo_stack"):
        assert projected[field] == before[field]
    assert session == before


def test_ai_editing_proposal_composes_every_supported_edit_without_extra_undo_events() -> None:
    """유진의 여러 편집은 중간 상태를 남기지 않고 한 번에 되돌려져야 한다."""
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "all-edits",
        "base_session_revision": 1,
        "operations": [
            {"intent": "set_segment_bounds", "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 1.5},
            {"intent": "set_cut_action", "segment_id": "seg_001", "action": "exclude"},
            {"intent": "set_caption_text", "segment_id": "seg_001", "text": "다듬은 첫 문장"},
            {"intent": "apply_media", "segment_id": "seg_001", "media_type": "bgm", "asset_id": "music_002"},
            {"intent": "remove_media", "segment_id": "seg_001", "media_type": "broll"},
            {"intent": "reorder_segments", "segment_ids": ["seg_003", "seg_001", "seg_002"]},
        ],
    })

    applied = apply_yujin_editing_proposal(session=_session(), proposal=proposal)

    assert [item["segment_id"] for item in applied["segments"]] == ["seg_003", "seg_001", "seg_002"]
    edited = next(item for item in applied["segments"] if item["segment_id"] == "seg_001")
    assert edited["cut_action"] == "remove"
    assert edited["caption_text"] == "다듬은 첫 문장"
    assert edited["music_override"]["asset_id"] == "music_002"
    assert edited["broll_override"] is None
    assert len(applied["undo_stack"]) == 1


def test_ai_scene_look_keeps_the_source_identity_it_paints_over() -> None:
    """말로 색감 바꾸기(2026-09-01). owner가 시켜 본 흐름 중 하나다.

    `update_segment_broll_override`는 덮어쓰기라 지금 값을 통째로 다시 실어야
    한다. 원본 신원(해시·판)을 안 실으면 출력 검증이 그 장면을 "바뀐 원본"으로
    읽어서, 색만 바꿨는데 완성본이 낡았다고 나온다.
    """
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][0]["broll_override"] = {
        "asset_id": "broll_001",
        "expected_content_sha256": "a" * 64,
        "media_revision": "broll-r7",
        "media_controls": {"fit": "crop", "speed": 1.5},
    }
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "look",
        "base_session_revision": 1,
        "operations": [{"intent": "set_scene_look", "segment_id": "seg_001", "look": "warm"}],
    })

    applied = apply_yujin_editing_proposal(session=session, proposal=proposal)
    override = next(item for item in applied["segments"] if item["segment_id"] == "seg_001")["broll_override"]

    assert override["asset_id"] == "broll_001"
    assert override["expected_content_sha256"] == "a" * 64
    assert override["media_revision"] == "broll-r7"
    # 고른 것은 색감뿐이다. 같이 저장돼 있던 값을 조용히 되돌리지 않는다.
    assert override["media_controls"]["fit"] == "crop"
    assert override["media_controls"]["speed"] == 1.5
    # 누가 골랐는지 남는다 -- 유진이 고른 것을 되돌리거나 설명하려면 출처가 있어야 한다.
    assert override["media_controls"]["filter"] == {"type": "warm", "chosen_by": "yujin"}
    assert len(applied["undo_stack"]) == 1


def test_ai_scene_look_refuses_a_scene_with_no_picture_under_it() -> None:
    """검증기가 먼저 막지만(`scene_look_needs_broll`) 여기서도 한 번 더 막는다.

    이 함수는 미리보기 투영에서도 불리고, 그 경로가 검증기를 안 지나는 날이
    올 수 있다. 그때 조용히 아무 일도 안 일어나는 것보다 멈추는 게 낫다.
    """
    import pytest as _pytest

    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][1]["broll_override"] = None
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "look",
        "base_session_revision": 1,
        "operations": [{"intent": "set_scene_look", "segment_id": "seg_002", "look": "mono"}],
    })

    with _pytest.raises(ValueError, match="scene_look_needs_broll"):
        apply_yujin_editing_proposal(session=session, proposal=proposal)


def test_ai_photo_motion_lands_beside_the_look_and_keeps_the_rest() -> None:
    """사진 움직임도 색감과 **같은 자리**다 -- 그 장면 B-roll의 조정값.

    원본 신원(해시·판)을 같이 실어야 출력 검증이 그 장면을 "바뀐 원본"으로 읽지
    않는다. 색감·손떨림·변형이 전부 지나는 함정이라 같은 함수를 쓴다.
    """
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][0]["broll_override"] = {
        "asset_id": "broll_001",
        "expected_content_sha256": "d" * 64,
        "media_revision": "broll-r11",
        "media_controls": {"fit": "crop", "filter": {"type": "warm", "chosen_by": "owner"}},
    }
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "motion", "base_session_revision": 1,
        "operations": [{"intent": "set_photo_motion", "segment_id": "seg_001", "motion": "still"}],
    })

    applied = apply_yujin_editing_proposal(session=session, proposal=proposal)
    override = next(s for s in applied["segments"] if s["segment_id"] == "seg_001")["broll_override"]

    assert override["media_controls"]["photo_motion"] == "still"
    assert override["expected_content_sha256"] == "d" * 64
    assert override["media_revision"] == "broll-r11"
    # 고른 것은 움직임뿐이다. 같이 저장돼 있던 색감을 조용히 되돌리지 않는다.
    assert override["media_controls"]["filter"] == {"type": "warm", "chosen_by": "owner"}
    assert override["media_controls"]["fit"] == "crop"


def test_ai_picture_cleanup_changes_only_what_the_creator_asked_for() -> None:
    """**말한 칸만 바꾼다.** owner가 "흔들림만 잡아 줘"라고 하면 노이즈 설정은
    그대로여야 한다.

    2026-09-02에 음악에서 똑같은 사고를 겪었다 -- 안 물어본 자리를 채우다가
    이미 켜 둔 것을 덮어썼다. 그래서 이 의도들의 칸은 전부 선택이고, 온 것만
    합친다.
    """
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][0]["broll_override"] = {
        "asset_id": "broll_001",
        "expected_content_sha256": "c" * 64,
        "media_revision": "broll-r9",
        "media_controls": {"fit": "crop", "reduce_noise": True, "speed": 1.5},
    }
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "cleanup", "base_session_revision": 1,
        "operations": [{"intent": "set_picture_cleanup", "segment_id": "seg_001", "stabilize": True}],
    })

    applied = apply_yujin_editing_proposal(session=session, proposal=proposal)
    controls = next(s for s in applied["segments"] if s["segment_id"] == "seg_001")["broll_override"]["media_controls"]

    assert controls["stabilize"] is True
    # 안 물어본 칸은 그대로다.
    assert controls["reduce_noise"] is True
    assert controls["fit"] == "crop"
    assert controls["speed"] == 1.5


def test_ai_scene_transform_keeps_the_source_identity_like_the_look_does() -> None:
    """변형도 색감과 **같은 함수**를 지난다 -- 원본 신원을 안 실으면 출력 검증이
    그 장면을 "바뀐 원본"으로 읽는다."""
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    session["segments"][0]["broll_override"] = {
        "asset_id": "broll_001", "expected_content_sha256": "d" * 64,
        "media_revision": "broll-r3", "media_controls": {"fit": "fit"},
    }
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "transform", "base_session_revision": 1,
        "operations": [{"intent": "set_scene_transform", "segment_id": "seg_001", "zoom": 1.4, "rotation_deg": 8.0}],
    })

    applied = apply_yujin_editing_proposal(session=session, proposal=proposal)
    override = next(s for s in applied["segments"] if s["segment_id"] == "seg_001")["broll_override"]

    assert override["expected_content_sha256"] == "d" * 64
    assert override["media_controls"]["zoom"] == 1.4
    assert override["media_controls"]["rotation_deg"] == 8.0
    # 말하지 않은 위치는 기본값 그대로다.
    assert override["media_controls"]["position_x_percent"] == 0.0


def test_ai_sound_cleanup_lands_on_the_media_the_creator_named() -> None:
    """음악과 효과음은 다른 자리다. `media_type`으로 지목한 쪽만 바뀐다."""
    from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal

    session = _session()
    proposal = YujinEditingProposal.model_validate({
        "proposal_id": "sound", "base_session_revision": 1,
        "operations": [{"intent": "set_sound_cleanup", "segment_id": "seg_001", "media_type": "bgm", "normalize_loudness": True}],
    })

    applied = apply_yujin_editing_proposal(session=session, proposal=proposal)
    segment = next(s for s in applied["segments"] if s["segment_id"] == "seg_001")

    assert segment["music_override"]["media_controls"]["normalize_loudness"] is True
    # 효과음은 손대지 않았다.
    assert not (segment["sfx_override"].get("media_controls") or {}).get("normalize_loudness")


def test_a_rebuilt_timeline_does_not_place_two_clips_on_the_same_stretch() -> None:
    """장면을 쪼갠 뒤 편집판을 다시 지으면 4~8초에 조각이 **두 번** 놓였다 — 실측 2026-09-07.

    캡컷 초안이 `New segment overlaps with existing segment
    [start: 4000000, end: 8000000]`으로 죽었다. 편집판 자체는 깨끗했다
    (겹치는 클립 없음) -- 겹침은 세션을 입히는 이 자리에서 생겼다.

    다시 지은 편집판은 **세션 좌표**로 온다: 쪼갠 뒤 생긴 `..__split_2`가
    클립의 `segment_id`로 그대로 박혀 있다. 그런데 그 세션 조각의
    `source_slices`는 쪼개기 **전** 이름(부모)을 가리킨다. 그래서
    부모 클립이 두 자리로 투영되고, 자식 클립은 짝을 못 찾아 원본 그대로
    통과한다 -- 같은 4~8초에 둘.

    한 장면짜리나 쪼개기 없는 시험은 이걸 못 잡는다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import split_segment

    project_id = "project_001"
    session = _session()
    session["project_id"] = project_id
    session["session_id"] = "session_001"
    session["segments"] = [
        {
            "segment_id": "timeline_001:001",
            "caption_text": "",
            "start_sec": 0.0,
            "end_sec": 8.0,
            "cut_action": "keep",
            "review_required": True,
            "broll_override": {"asset_id": "photo_one"},
            "music_override": None,
            "sfx_override": None,
            "visual_overlays": [],
        }
    ]
    session = split_segment(session=session, segment_id="timeline_001:001", split_sec=4.0)
    left_id, right_id = [segment["segment_id"] for segment in session["segments"][:2]]
    session["segments"][1]["broll_override"] = {"asset_id": "photo_two"}

    # 다시 지은 편집판 -- 장면마다 클립이 하나씩, 이름은 **지금** 세션 조각 이름이다.
    timeline = {
        "project_id": project_id,
        "timeline_id": "timeline_002",
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {"clip_id": "clip_narration_001", "segment_id": left_id, "start_sec": 0.0, "end_sec": 4.0},
                    {"clip_id": "clip_narration_002", "segment_id": right_id, "start_sec": 4.0, "end_sec": 8.0},
                ],
            },
            {
                "track_type": "broll",
                "clips": [
                    {"clip_id": "clip_broll_001", "segment_id": left_id, "asset_id": "photo_one", "start_sec": 0.0, "end_sec": 4.0},
                    {"clip_id": "clip_broll_002", "segment_id": right_id, "asset_id": "photo_two", "start_sec": 4.0, "end_sec": 8.0},
                ],
            },
        ],
    }

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=session, project_id=project_id
    )

    for track in materialized["tracks"]:
        placed = sorted(
            ((clip["start_sec"], clip["end_sec"], clip["clip_id"]) for clip in track["clips"]),
        )
        for earlier, later in zip(placed, placed[1:]):
            assert earlier[1] <= later[0], (track["track_type"], placed)


def test_merging_two_segments_keeps_the_broll_each_one_had() -> None:
    """장면 둘을 합쳤더니 골라 둔 브롤이 **둘 다 조용히 사라졌다**(2026-09-10
    자유 멀티트랙 Phase 2 작업 중 발견).

    합치기는 직접 선택을 일부러 지우고 창(`media_windows`)에 권한을 넘긴다 --
    주석이 그렇게 말하고, 그래야 한쪽 선택이 다른 쪽 구간까지 늘어나지
    않는다. 그런데 `_media_windows()`는 **이미 있는 창 목록을 그대로**
    돌려주고, 직접 선택을 고르는 순간 그 필드는 창에서 지워져 있다
    (`_clear_windowed_media_override`). 그래서 합칠 때 접어 넣을 것이
    아무 데도 없어 선택이 통째로 없어졌다.

    실제 렌더 경로로 잰다 -- 세션 dict만 보면 "창은 그대로 있다"고 보여서
    사라진 것을 못 본다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import (
        build_editing_session,
        merge_adjacent_segments,
        split_segment,
        update_segment_broll_override,
    )

    def _broll_clips(session: dict) -> list[tuple[str, float, float]]:
        materialized = materialize_editing_session_timeline(
            timeline={"timeline_id": "t", "project_id": "p", "tracks": []},
            editing_session=session,
            project_id="p",
        )
        return sorted(
            (str(clip.get("asset_id")), float(clip["start_sec"]), float(clip["end_sec"]))
            for track in materialized.get("tracks", [])
            if str(track.get("track_type")) == "broll"
            for clip in track.get("clips", [])
        )

    session = build_editing_session(
        project_id="p",
        timeline={"timeline_id": "t", "project_id": "p", "tracks": [], "review_flags": [], "pending_recommendations": []},
        segments=[{
            "segment_id": "seg_001", "text": "한 장면", "start_sec": 0.0, "end_sec": 8.0,
            "review_required": False, "cleanup_decision": "keep",
        }],
    )
    session = split_segment(session=session, segment_id="seg_001", split_sec=4.0)
    left_id, right_id = [segment["segment_id"] for segment in session["segments"]]
    session = update_segment_broll_override(session=session, segment_id=left_id, asset_id="broll-A")
    session = update_segment_broll_override(session=session, segment_id=right_id, asset_id="broll-B")

    before = _broll_clips(session)
    assert before == [("broll-A", 0.0, 4.0), ("broll-B", 4.0, 8.0)]

    merged = merge_adjacent_segments(session=session, left_segment_id=left_id, right_segment_id=right_id)

    # 합쳤다고 고른 것이 없어지면 안 된다. 자리도 그대로여야 한다 --
    # 한쪽이 8초 전체로 늘어나는 것도 똑같이 틀린 답이다.
    assert _broll_clips(merged) == before


def _merge_fixture():
    from videobox_core_engine.editing_session import build_editing_session, split_segment

    session = build_editing_session(
        project_id="p",
        timeline={"timeline_id": "t", "project_id": "p", "tracks": [], "review_flags": [], "pending_recommendations": []},
        segments=[{
            "segment_id": "seg_001", "text": "한 장면", "start_sec": 0.0, "end_sec": 8.0,
            "review_required": False, "cleanup_decision": "keep",
        }],
    )
    return split_segment(session=session, segment_id="seg_001", split_sec=4.0)


def _rendered_clips(session: dict, track_type: str = "broll") -> list[tuple[str, float, float]]:
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline

    materialized = materialize_editing_session_timeline(
        timeline={"timeline_id": "t", "project_id": "p", "tracks": []}, editing_session=session, project_id="p",
    )
    return sorted(
        (str(clip.get("asset_id")), float(clip["start_sec"]), float(clip["end_sec"]))
        for track in materialized.get("tracks", [])
        if str(track.get("track_type")) == track_type
        for clip in track.get("clips", [])
    )


@pytest.mark.parametrize("chosen_side", ["left", "right"])
def test_merging_does_not_stretch_one_sides_broll_over_the_other(chosen_side: str) -> None:
    """한쪽에만 브롤이 있을 때. 잃어버리는 것도 틀렸지만, 남은 하나를 합친
    구간 전체(8초)로 늘리는 것도 똑같이 틀렸다 -- 고르지도 않은 구간에
    영상이 깔린다."""
    from videobox_core_engine.editing_session import merge_adjacent_segments, update_segment_broll_override

    session = _merge_fixture()
    left_id, right_id = [segment["segment_id"] for segment in session["segments"]]
    target = left_id if chosen_side == "left" else right_id
    session = update_segment_broll_override(session=session, segment_id=target, asset_id="broll-1")
    expected = _rendered_clips(session)

    merged = merge_adjacent_segments(session=session, left_segment_id=left_id, right_segment_id=right_id)

    assert expected == [("broll-1", 0.0, 4.0)] if chosen_side == "left" else [("broll-1", 4.0, 8.0)]
    assert _rendered_clips(merged) == expected


def test_merging_twice_keeps_every_choice_at_its_own_place() -> None:
    """합칠 때마다 창 오프셋이 쌓인다. 한 번은 맞고 두 번째에 어긋나는
    실수가 흔해서 세 조각을 두 번 합쳐 본다."""
    from videobox_core_engine.editing_session import (
        merge_adjacent_segments, split_segment, update_segment_broll_override,
    )

    session = _merge_fixture()
    session = split_segment(session=session, segment_id=session["segments"][1]["segment_id"], split_sec=6.0)
    for index, segment in enumerate(list(session["segments"])):
        session = update_segment_broll_override(session=session, segment_id=segment["segment_id"], asset_id=f"broll-{index}")
    expected = _rendered_clips(session)
    assert len(expected) == 3

    ids = [segment["segment_id"] for segment in session["segments"]]
    merged = merge_adjacent_segments(session=session, left_segment_id=ids[0], right_segment_id=ids[1])
    ids = [segment["segment_id"] for segment in merged["segments"]]
    merged = merge_adjacent_segments(session=merged, left_segment_id=ids[0], right_segment_id=ids[1])

    assert _rendered_clips(merged) == expected


def test_manifest_length_follows_the_clips_not_the_blank_boards_five_seconds() -> None:
    """**눈금자 길이는 편집본이 정한다.** 빈 편집판이 적어 둔 5초가 아니다.

    대표님 실제 영상(8분)을 빈 편집판에 깔아 장면 열 개(0~120초)를 만들었는데
    `playback-manifest`의 `output.duration_sec`이 **5.0**으로 왔다. 눈금자가
    0~4초만 그려지고 클립 열 개 중 둘만 보였다 -- 120초 세션의 3.9%다.
    `전체`(맞추기) 단추도 같은 숫자를 쓰므로 **빠져나올 길이 없었다.**

    5.0은 빈 편집판이 타임라인 문서에 적어 둔 값이고(`blank_editing_session.py`),
    장면을 넣고 쪼개고 경계를 옮겨도 **아무도 그 값을 고치지 않는다** --
    타임라인 문서는 처음 한 번만 저장되고 이후 편집은 전부 세션에만 쌓인다.
    그래서 빈 편집판에서 시작한 모든 프로젝트가 5초를 물려받는다.

    길이는 **저장한 값이 아니라 조각에서 잰 값**이어야 한다. 완성본 길이는
    이미 그렇게 잰다(`CompositionPlan.duration_sec`) -- 화면만 저장된 숫자를
    믿고 있었고, 그래서 눈금자와 완성본이 서로 다른 길이를 말했다.
    """
    from videobox_core_engine.blank_editing_session import (
        build_blank_editing_session,
        build_blank_timeline_payload,
    )
    from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

    project_id = "project_001"
    session = build_blank_editing_session(project_id=project_id, timeline_id="timeline_001")
    session["session_id"] = "session_001"
    blank_scene = session["segments"][0]
    # 장면 열 개를 12초씩 -- 대표님이 8분 영상을 깔았을 때 생긴 모양이다.
    session["segments"] = [
        {
            **blank_scene,
            "segment_id": f"timeline_001:{index + 1:03d}",
            "caption_text": f"{index + 1}번째 장면",
            "start_sec": float(index * 12),
            "end_sec": float((index + 1) * 12),
            "review_required": False,
        }
        for index in range(10)
    ]
    timeline = {
        **build_blank_timeline_payload(),
        "project_id": project_id,
        "timeline_id": "timeline_001",
    }

    manifest = build_editor_playback_manifest(
        project_id=project_id,
        session=session,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project_id}/assets",
    )

    assert len(manifest["captions"]) == 10
    assert manifest["output"]["duration_sec"] == 120.0


def test_manifest_length_shrinks_when_the_stored_number_is_longer_than_the_clips() -> None:
    """저장된 숫자가 **더 길 때도** 조각을 따른다.

    빈 편집판만 5.0을 적어 두는 게 아니다. 기획을 통과한 타임라인은 원본
    길이를 적어 두는데, 장면을 빼거나 경계를 줄여도 그 숫자는 그대로다.
    `max(저장값, 잰 값)`으로 고치면 위 시험은 통과하면서 이쪽이 틀린다 --
    빼고 나서도 눈금자가 옛 길이를 그려 빈 자리를 끌고 다닌다.
    """
    from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

    project_id = "project_001"
    session = {
        "project_id": project_id,
        "session_id": "session_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [
            {"segment_id": "seg_001", "caption_text": "남긴 장면", "start_sec": 0.0, "end_sec": 8.0, "cut_action": "keep"},
            {"segment_id": "seg_002", "caption_text": "뺀 장면", "start_sec": 8.0, "end_sec": 300.0, "cut_action": "remove"},
        ],
    }
    timeline = {
        "project_id": project_id,
        "timeline_id": "timeline_001",
        "version": "v001",
        "fps_num": 30,
        "fps_den": 1,
        # 기획이 적어 둔 원본 길이. 장면을 빼도 아무도 이 값을 안 고친다.
        "output": {"width": 1920, "height": 1080, "duration_sec": 300.0},
        "tracks": [],
    }

    manifest = build_editor_playback_manifest(
        project_id=project_id,
        session=session,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project_id}/assets",
    )

    assert [caption["segment_id"] for caption in manifest["captions"]] == ["seg_001"]
    assert manifest["output"]["duration_sec"] == 8.0
    # 화면 크기는 여전히 저장된 값에서 온다 -- 세로 숏폼이 이 칸에 걸려 있다.
    assert (manifest["output"]["width"], manifest["output"]["height"]) == (1920, 1080)


# --- 쓸 자리만 나누기: 여러 자리를 한 번에, 되돌리기는 한 번 ---------------------
#
# 대표님 지시(2026-09-12): "굳이 안쓰는걸 다 쪼갤필요는 없잖아." 숏폼이 쓰는
# 자리에만 경계를 낸다. 그런데 자리가 여러 개이므로 **한 덩이로** 나눠야 한다 --
# 나누기마다 되돌리기 한 칸을 쓰면 대표님이 Ctrl+Z를 열두 번 눌러야 숏폼 하나가
# 취소된다. 유진 편집은 확인 클릭 없이 적용되고 되돌리기가 유일한 안전장치다
# (owner 결정 2026-09-01).


def _one_long_scene(duration_sec: float = 494.837) -> dict:
    """대표님 실제 영상과 같은 길이의 **장면 하나**짜리 판.

    제품의 실제 문(`+ 새로 만들기` -> 영상 깔기 -> 길이 맞추기)이 만드는 모양이다.
    """
    return {
        "project_id": "project_001",
        "session_id": "session_001",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [
            {
                "segment_id": "seg_001",
                "caption_text": "긴 영상 하나",
                "start_sec": 0.0,
                "end_sec": duration_sec,
                "cut_action": "keep",
                "source_offset_sec": 0.0,
                "broll_override": {"asset_id": "asset-video"},
            }
        ],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
    }


def test_cutting_many_places_at_once_is_one_undo_press() -> None:
    """대표님 영상 규모(494.837초)에서 94장면을 **한 덩이로** 낸다.

    93번 따로 부르면 되돌리기가 93칸(실제로는 상한 10칸)이 되어 숏폼 하나를
    취소할 길이 없어진다.
    """
    from videobox_core_engine.editing_session import plan_board_splits, split_segments_at
    from videobox_core_engine.editing_session import undo as undo_session

    session = _one_long_scene()
    # 발화 213개를 4~8초 대목으로 묶었을 때 나오는 경계 수와 같은 규모.
    wanted = [round(index * 494.837 / 94.0, 3) for index in range(1, 94)]

    planned = plan_board_splits(segments=session["segments"], board_secs=wanted)
    assert len(planned) == 93, f"93자리를 다 계획해야 한다: {len(planned)}"

    cut = split_segments_at(session=session, splits=planned, label="숏폼 자리 나누기")

    assert len(cut["segments"]) == 94
    assert len(cut["undo_stack"]) == 1, "여러 자리를 나눠도 되돌리기는 한 칸이다"
    assert int(cut["session_revision"]) == 2, "판 버전은 정확히 한 번 오른다"

    restored = undo_session(session=cut)
    assert [segment["segment_id"] for segment in restored["segments"]] == ["seg_001"]
    assert float(restored["segments"][0]["end_sec"]) == 494.837


def test_a_place_that_is_already_a_boundary_is_not_cut_again() -> None:
    """다시 만들기를 두 번 눌러도 같은 자리를 두 번 나누지 않는다."""
    from videobox_core_engine.editing_session import plan_board_splits, split_segments_at

    session = _one_long_scene(duration_sec=60.0)
    first = plan_board_splits(segments=session["segments"], board_secs=[10.0, 25.0])
    cut = split_segments_at(session=session, splits=first, label="숏폼 자리 나누기")

    again = plan_board_splits(segments=cut["segments"], board_secs=[10.0, 25.0])

    assert again == (), f"이미 경계인 자리는 다시 나누지 않는다: {again}"


def test_a_place_too_close_to_an_existing_boundary_snaps_instead_of_slivering() -> None:
    """최소 길이(0.2초)를 못 채우는 자리는 나누지 않고 옆 경계로 붙인다."""
    from videobox_core_engine.editing_session import plan_board_splits

    session = _one_long_scene(duration_sec=60.0)

    planned = plan_board_splits(segments=session["segments"], board_secs=[0.05, 30.0, 59.95])

    assert planned == (("seg_001", 30.0),), f"조각을 만들지 않아야 한다: {planned}"
