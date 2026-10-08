"""세션 투영 클립은 원본이 아니다 (2026-10-08 계획 H Task 4, 점검 §3-3).

0907의 저장된 편집판(`timeline_002.json`)에는 materialize가 만든 `session-overlay-…`·
`session-broll-…` 클립이 박혀 있다(2026-09-20 되돌린 커밋의 흔적). 생성기가 그것을
원본으로 다시 투영해, 부모 장면을 가리키는 모든 조각에 오버레이를 깔고 같은 id를
두 번 붙였다 -> 자르기·옮기기가 전부 `timeline_placement_duplicate` 422.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.output_variants import MaterializedVariant, build_variant_timeline_payload
from videobox_core_engine.timeline_placements import collect_timeline_placements
from videobox_storage.local_project_store import LocalProjectStore

PARENT = "timeline_001:001"
CHILD = f"{PARENT}__split_2"
IMAGE = {"overlay_type": "image_overlay", "asset_id": "asset_img", "asset_uri": "local://projects/p/assets/image/a.png"}


def _session() -> dict:
    return {
        "session_id": "editing_session_001", "project_id": "p", "timeline_id": "timeline_002", "session_revision": 3,
        "segments": [
            {"segment_id": PARENT, "caption_text": "앞", "start_sec": 0.0, "end_sec": 2.0, "cut_action": "keep", "visual_overlays": [dict(IMAGE)],
             "source_slices": [{"segment_id": PARENT, "source_offset_sec": 0.0, "duration_sec": 2.0}]},
            {"segment_id": CHILD, "caption_text": "뒤", "start_sec": 2.0, "end_sec": 4.0, "cut_action": "keep", "visual_overlays": [],
             "source_slices": [{"segment_id": PARENT, "source_offset_sec": 2.0, "duration_sec": 2.0}]},
        ],
    }


def _base(*, with_projection: bool) -> dict:
    tracks = [{"track_id": "narration_primary", "track_type": "narration", "clips": [
        {"clip_id": "clip_narration_001", "segment_id": PARENT, "clip_type": "narration", "asset_uri": "local://n.wav", "start_sec": 0.0, "end_sec": 4.0},
    ]}]
    if with_projection:
        tracks.append({"track_id": "track_overlay", "track_type": "overlay", "clips": [
            {**IMAGE, "clip_id": f"session-overlay-{PARENT}-0-0", "segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0},
        ]})
    return {"timeline_id": "timeline_002", "project_id": "p", "output": {"width": 1280, "height": 720}, "tracks": tracks}


def _overlays(materialized: dict) -> list[tuple[str, str, float, float]]:
    return [
        (clip["clip_id"], clip["segment_id"], clip["start_sec"], clip["end_sec"])
        for track in materialized["tracks"] if track["track_type"] == "overlay" for clip in track["clips"]
    ]


def test_a_baked_session_overlay_is_not_projected_onto_other_scenes_or_duplicated() -> None:
    materialized = materialize_editing_session_timeline(timeline=_base(with_projection=True), editing_session=_session())
    assert _overlays(materialized) == [(f"session-overlay-{PARENT}-0-0", PARENT, 0.0, 2.0)]
    collect_timeline_placements(timeline=materialized)  # 같은 id가 있으면 여기서 ValueError


def test_materializing_its_own_output_again_gives_the_same_overlays() -> None:
    once = materialize_editing_session_timeline(timeline=_base(with_projection=False), editing_session=_session())
    again = materialize_editing_session_timeline(timeline={**_base(with_projection=False), "tracks": deepcopy(once["tracks"])}, editing_session=_session())
    assert _overlays(again) == _overlays(once)


def test_variant_payload_drops_session_projection_clips() -> None:
    payload = build_variant_timeline_payload(
        master_timeline=_base(with_projection=True), variant_kind="horizontal",
        derived=MaterializedVariant(source_session_id="editing_session_001", source_session_revision=3,
                                    source_variant_id="variant-h", source_variant_revision=1,
                                    segments=({"segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0},)),
        overrides=None,
    )
    assert all(not str(clip.get("clip_id")).startswith("session-") for track in payload["tracks"] for clip in track["clips"])


def test_storing_a_timeline_with_session_projection_clips_is_refused(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="문지기")
    with pytest.raises(ValueError, match="timeline_contains_session_projection"):
        store.save_timeline_run(project_id=project.project_id, output_mode="review", timeline_payload=_base(with_projection=True))


def test_an_already_contaminated_timeline_can_still_be_updated_but_cannot_grow(tmp_path) -> None:
    """0907처럼 이미 오염된 파일은 매 편집마다 `update_timeline_run`(판 번호 옮기기)을 탄다.
    그것까지 막으면 0907이 통째로 편집 불가가 된다 -- 늘어나는 것만 막는다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="옛 데이터")
    saved = store.save_timeline_run(project_id=project.project_id, output_mode="review", timeline_payload=_base(with_projection=False))
    contaminated = {**store.get_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"]), "tracks": _base(with_projection=True)["tracks"]}
    contaminated.pop("summary", None)
    path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=str(contaminated["file_uri"]))
    import json
    path.write_text(json.dumps(contaminated), encoding="utf-8")  # 2026-09-20 옛 데이터 흉내
    store.update_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"], timeline_payload={**contaminated, "source_session_revision": 4})
    grown = deepcopy(contaminated)
    grown["tracks"][1]["clips"].append({**IMAGE, "clip_id": f"session-overlay-{CHILD}-0-0", "segment_id": CHILD, "start_sec": 2.0, "end_sec": 4.0})
    with pytest.raises(ValueError, match="timeline_contains_session_projection"):
        store.update_timeline_run(project_id=project.project_id, timeline_id=saved["timeline_id"], timeline_payload=grown)


def test_playback_manifest_opens_a_timeline_whose_baked_projection_clips_are_malformed() -> None:
    """옛 오염 데이터의 투영 클립은 `overlay_payload`가 없을 수 있다. 어차피 건너뛰는 클립이라
    그것 때문에 편집기 재생 목록이 통째로 422가 되면 안 된다."""
    from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest

    base = _base(with_projection=True)
    base["tracks"][1]["clips"].append({"clip_id": f"session-overlay-{PARENT}-0-0", "segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0, "overlay_type": "image_overlay"})
    manifest = build_editor_playback_manifest(project_id="p", session=_session(), timeline=base, asset_content_url_prefix="/api/projects/p/assets")
    ids = [clip["placement_id"] for track in manifest["tracks"] if track["track_type"] == "overlay" for clip in track["clips"]]
    assert len(ids) == len(set(ids)) == 1
