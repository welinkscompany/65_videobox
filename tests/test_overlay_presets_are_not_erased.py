"""사진 오버레이 프리셋 넷(자리·크기·움직임)은 안 준다고 지워지면 안 된다.

owner가 유진에게 "오른쪽 아래로" 한 다음 "좀 작게"라고만 하면, 지금까지는
`update_segment_image_overlay`가 크기만 새로 받고 자리(vertical/horizontal)는
"안 줌"으로 받아서 -- 그런데 `_upsert_segment_overlay`가 옛 오버레이를 통째로
버리고 새 payload만 남기므로 -- 앞서 정한 자리가 조용히 사라진다. 이 시험은 그
결함을 고정한다.

동시에 화면의 `안 고름`(`InspectorControls.tsx`의 `IMAGE_PRESET_UNSET`) 선택지가
쓰는 길(`None`을 명시적으로 줌 = 지움)이 막히지 않는지도 지킨다. 세 상태:

| 부르는 쪽이 하는 것 | 뜻 |
|---|---|
| 인자를 아예 안 준다 | 지금 값을 그대로 둔다 |
| `None`을 준다 | 지워서 "안 고름"으로 |
| 값을 준다 | 그 값으로 |
"""
from __future__ import annotations

from videobox_core_engine.editing_session import build_editing_session
from videobox_core_engine.editing_session import update_segment_image_overlay


def _session_with_one_segment() -> dict:
    return build_editing_session(
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


def test_resizing_alone_keeps_the_position_owner_set_earlier() -> None:
    """대표님이 실제로 겪은 결함: 자리를 정한 뒤 크기만 다시 주면 자리가 남는다."""
    session = _session_with_one_segment()

    placed = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical="bottom",
        horizontal="right",
        size="medium",
        motion="fade_in",
    )

    # 크기만 다시 준다 -- vertical/horizontal/motion은 인자 자체를 안 준다.
    resized = update_segment_image_overlay(
        session=placed,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        size="small",
    )

    overlay = resized["segments"][0]["visual_overlays"][0]
    assert overlay["size"] == "small"
    assert overlay["vertical"] == "bottom"
    assert overlay["horizontal"] == "right"
    assert overlay["motion"] == "fade_in"


def test_omitting_all_four_preset_arguments_keeps_all_four() -> None:
    """넷을 아무것도 안 주면(예: text만 바꾸는 호출) 넷 다 그대로 남는다."""
    session = _session_with_one_segment()

    placed = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical="top",
        horizontal="left",
        size="large",
        motion="slide_in_left",
    )

    untouched = update_segment_image_overlay(
        session=placed,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image (renamed)",
    )

    overlay = untouched["segments"][0]["visual_overlays"][0]
    assert overlay["vertical"] == "top"
    assert overlay["horizontal"] == "left"
    assert overlay["size"] == "large"
    assert overlay["motion"] == "slide_in_left"
    assert overlay["text"] == "Exterior reference image (renamed)"


def test_explicit_none_clears_the_field_back_to_unset() -> None:
    """`None`을 명시적으로 주면 그 칸이 지워진다 -- 화면의 `안 고름`이 이 길로 온다."""
    session = _session_with_one_segment()

    placed = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical="top",
        horizontal="right",
        size="small",
        motion="fade_in",
    )

    cleared_vertical = update_segment_image_overlay(
        session=placed,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical=None,
        horizontal="right",
        size="small",
        motion="fade_in",
    )

    overlay = cleared_vertical["segments"][0]["visual_overlays"][0]
    assert "vertical" not in overlay
    assert overlay["horizontal"] == "right"
    assert overlay["size"] == "small"
    assert overlay["motion"] == "fade_in"


def test_giving_a_value_changes_it() -> None:
    """값을 주면 그 값으로 바뀐다 -- 세 상태 중 세 번째, 지금까지도 되던 길이다."""
    session = _session_with_one_segment()

    placed = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical="top",
        horizontal="left",
        size="small",
        motion="none",
    )

    changed = update_segment_image_overlay(
        session=placed,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
        vertical="bottom",
        horizontal="right",
        size="large",
        motion="fade_in_out",
    )

    overlay = changed["segments"][0]["visual_overlays"][0]
    assert overlay["vertical"] == "bottom"
    assert overlay["horizontal"] == "right"
    assert overlay["size"] == "large"
    assert overlay["motion"] == "fade_in_out"


def test_overlay_that_never_chose_a_preset_gets_no_keys() -> None:
    """프리셋을 한 번도 안 고른 오버레이는 열쇠가 안 생긴다(기본값으로 안 채운다).

    이 기능이 생기기 전에 저장된 오버레이, 또는 프리셋 없이 얹은 오버레이와
    자국이 같아야 한다 -- 없는 열쇠를 '정중앙·안 움직임'으로 읽는 것은 렌더
    쪽 몫이다.
    """
    session = _session_with_one_segment()

    updated = update_segment_image_overlay(
        session=session,
        segment_id="seg_001",
        asset_id="asset_image_001",
        text="Exterior reference image",
    )

    overlay = updated["segments"][0]["visual_overlays"][0]
    assert overlay == {
        "overlay_type": "image_overlay",
        "asset_id": "asset_image_001",
        "text": "Exterior reference image",
    }
    for field_name in ("vertical", "horizontal", "size", "motion"):
        assert field_name not in overlay
