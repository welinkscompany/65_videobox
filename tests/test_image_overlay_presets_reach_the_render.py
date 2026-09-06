"""사진 오버레이의 자리·크기·움직임이 화면까지 닿는가 — owner 요청 2026-09-06.

> "오버레이 프리셋도 진행해"

세션까지는 `vertical`·`horizontal`·`size`·`motion`이 저장된다. 그런데 **렌더러가
그 넷을 한 번도 읽지 않았다** -- 두 렌더 경로가 모두 `overlay=(W-w)/2:(H-h)/2`로
가운데에 원본 비율 그대로 얹는다. 고른 값이 저장은 되는데 완성본은 그대로다.

이 저장소가 되풀이한 모양이라(`[[videobox-two-render-paths-fix-both]]`) 계산은
함수 하나에 둔다. 값이 없으면 예전 필터와 **글자까지 같아야** 한다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.ffmpeg_final_renderer import export_image_overlay_geometry


def _geometry(**overlay: object):
    return export_image_overlay_geometry(
        dict(overlay), width=1920, height=1080, start_sec=1.0, end_sec=4.0
    )


def test_an_overlay_without_presets_is_unchanged() -> None:
    """안 고른 오버레이는 예전 그대로 -- 가운데, 화면에 맞춘 크기, 움직임 없음."""
    scale, x, y, fade = _geometry(overlay_type="image")

    assert scale == "scale=1920:1080:force_original_aspect_ratio=decrease"
    assert x == "(W-w)/2"
    assert y == "(H-h)/2"
    assert fade == ""


@pytest.mark.parametrize(
    ("horizontal", "vertical"),
    [("left", "top"), ("right", "bottom"), ("center", "middle")],
)
def test_the_nine_stops_move_the_photo(horizontal: str, vertical: str) -> None:
    _, x, y, _ = _geometry(overlay_type="image", horizontal=horizontal, vertical=vertical)

    if horizontal == "left":
        assert x == "115"
    elif horizontal == "right":
        assert x == "W-w-115"
    else:
        assert x == "(W-w)/2"
    if vertical == "top":
        assert y == "86"
    elif vertical == "bottom":
        assert y == "H-h-86"
    else:
        assert y == "(H-h)/2"


def test_size_shrinks_the_photo_but_keeps_its_shape() -> None:
    """사진은 비율이 있다. 칸에 **맞춰 넣되**(`decrease`) 늘려 찌그러뜨리지 않는다."""
    small, _, _, _ = _geometry(overlay_type="image", size="small")
    large, _, _, _ = _geometry(overlay_type="image", size="large")

    assert small == "scale=672:378:force_original_aspect_ratio=decrease"
    assert large == "scale=1536:864:force_original_aspect_ratio=decrease"


def test_fading_needs_an_alpha_channel_first() -> None:
    """`fade=alpha=1`은 알파가 있는 화소 꼴에서만 듣는다. jpg에는 알파가 없어
    `format=yuva420p`를 앞에 안 붙이면 **필터는 성공하는데 화면은 안 흐려진다.**
    """
    _, _, _, fade = _geometry(overlay_type="image", motion="fade_in")

    assert fade.startswith(",format=yuva420p,"), fade
    assert "alpha=1" in fade
    assert "fade=t=in" in fade


def test_sliding_in_moves_along_x_over_time() -> None:
    _, x, _, fade = _geometry(overlay_type="image", motion="slide_in_left", horizontal="left")

    assert "t" in x and "clip(" in x, x
    assert x.startswith("'") and x.endswith("'"), "쉼표가 든 식은 따옴표로 묶어야 한다"
    assert fade == "", "밀려 들어오기는 흐려지지 않는다"


def test_an_unknown_motion_is_read_as_no_motion() -> None:
    """이 기능이 생기기 전 오버레이에는 열쇠가 아예 없다. 모르는 이름도 같게 다룬다."""
    _, x, _, fade = _geometry(overlay_type="image", motion="spin")

    assert x == "(W-w)/2"
    assert fade == ""


def test_a_preset_chosen_in_the_session_survives_all_the_way_to_the_plan() -> None:
    """고른 값이 **세션에서 렌더 계획까지** 살아 오는가.

    이 저장소가 되풀이한 실패가 있다: 층마다 초록인데 사이에서 값이 조용히
    떨어진다. 저장 화이트리스트에 새 칸을 안 넣어 그런 적이 있었고
    (`[[videobox-caption-translation-lives-on-the-session]]`), 부품은 다 있는데
    부르는 자리가 없어 그런 적도 있다. 그래서 층별 시험 말고 **한 줄로 꿰는**
    시험을 따로 둔다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import build_editing_session, update_segment_image_overlay

    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[{"segment_id": "segment_001", "text": "사진 하나", "start_sec": 0.0, "end_sec": 3.0}],
    )
    updated = update_segment_image_overlay(
        session=session, segment_id="segment_001", asset_id="asset_photo", text="",
        vertical="top", horizontal="right", size="small", motion="fade_in",
    )

    # **`project_id`를 반드시 넣는다.** 안 넣으면 자산 주소가 안 만들어져
    # 오버레이가 다른 갈래(글줄용)로 새고, 제품이 실제로 지나는 길을 안 밟는다 --
    # 이 시험이 처음에 그래서 초록이었다(2026-09-06 실측으로 잡음).
    materialized = materialize_editing_session_timeline(
        timeline={"tracks": []}, editing_session=updated, project_id="project_001"
    )
    overlay_clips = [
        clip
        for track in materialized["tracks"] if track.get("track_type") == "overlay"
        for clip in (track.get("clips") or [])
        if str(clip.get("asset_id") or "") == "asset_photo"
    ]

    assert overlay_clips, f"사진 오버레이가 계획에 없다: {materialized['tracks']}"
    overlay = dict(overlay_clips[0].get("overlay_payload") or {})
    assert overlay["vertical"] == "top"
    assert overlay["horizontal"] == "right"
    assert overlay["size"] == "small"
    assert overlay["motion"] == "fade_in"

    # 시각은 클립에, 프리셋은 payload에 있다.
    scale, x, y, fade = export_image_overlay_geometry(
        overlay, width=1920, height=1080,
        start_sec=float(overlay_clips[0]["start_sec"]), end_sec=float(overlay_clips[0]["end_sec"]),
    )
    assert x == "W-w-115" and y == "86", (x, y)
    assert scale.startswith("scale=672:378"), scale
    assert "alpha=1" in fade


def test_the_overlay_track_honours_the_presets_too(tmp_path) -> None:
    """**제품이 실제로 지나는 길은 오버레이 트랙이다** — 실측 2026-09-06.

    세션에 얹은 사진은 자산 주소가 있으면 `export_overlays`가 아니라 **오버레이
    트랙**으로 간다. 그 트랙을 그리는 자리는 프리셋을 안 보고 화면 크기로
    가운데에 얹는다 -- 고른 자리·크기·움직임이 완성본에서 통째로 무시됐다.

    이 저장소가 되풀이한 "렌더 경로가 둘"이다. 앞 시험이 `project_id`를 빼서
    다른 갈래로 새는 바람에 초록이었다.
    """
    from videobox_core_engine.composition_plan import CompositionItem, CompositionPlan
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer

    item = CompositionItem(
        clip_id="session-overlay-s1-0-0", track_type="overlay",
        start_sec=1.0, end_sec=4.0, source_in_sec=0.0, source_out_sec=3.0,
        asset_uri="local://projects/p1/assets/asset_photo", asset_id="asset_photo",
        overlay_type="image_overlay",
        overlay_payload={
            "overlay_type": "image_overlay", "asset_id": "asset_photo",
            "vertical": "top", "horizontal": "right", "size": "small", "motion": "fade_in",
        },
    )
    plan = CompositionPlan(
        width=1920, height=1080, fps_num=30, fps_den=1,
        sample_aspect_ratio="1:1", rotation=0, items=(item,),
    )

    renderer = FfmpegFinalRenderer(store=None)
    graph = renderer.build_plan_filter_graph(
        composition_plan=plan, source_indices={"session-overlay-s1-0-0": 1},
        track_overlay_indices={"session-overlay-s1-0-0": 1},
    )

    # 기대값은 렌더러가 쓰는 화면 크기에서 뽑는다 -- 숫자를 손으로 박으면
    # 기본 해상도가 바뀔 때 멀쩡한 코드가 빨개진다.
    expected_scale, expected_x, expected_y, expected_fade = export_image_overlay_geometry(
        dict(item.overlay_payload), width=renderer.video_width, height=renderer.video_height,
        start_sec=item.start_sec, end_sec=item.end_sec,
    )
    assert expected_scale in graph, graph
    assert f"overlay=x={expected_x}:y={expected_y}" in graph, graph
    assert "alpha=1" in expected_fade and "alpha=1" in graph, graph
    assert "overlay=(W-w)/2:(H-h)/2" not in graph, "가운데 고정이 그대로 남아 있다"
