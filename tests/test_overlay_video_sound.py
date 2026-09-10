"""얹은 영상(PIP)의 원본 소리가 완성본까지 오는가 -- Task 1, 2026-09-11.

지금 오버레이 트랙(`overlay_type=image_overlay`, `사진`도 되고 `영상`도 되는 자리)은
그림만 얹고 **소리는 통째로 버린다**. b-roll에는 이미 `preserve_source_audio`가
있다(`media_controls.py`) -- 이름을 그대로 빌려 쓴다, 새로 짓지 않는다.

세 자리를 잇는다: 세션(`update_segment_image_overlay`의 `visual_overlays` payload)이
값을 보관하고 -> `composition_plan.materialize_editing_session_timeline`이 그 값을
클립의 `media_controls`로 옮겨 싣고(b-roll이 읽는 것과 같은 자리) -> 렌더러가 오디오
루프에서 읽는다.

지킨다.

1. `preserve_source_audio=True`인 오버레이 클립의 소리가 오디오 그래프에 섞인다.
2. **꺼져 있으면(기본값) 그래프가 예전과 한 글자도 같다** -- 이게 제일 중요하다.
   기본값이 움직이면 지금 있는 완성본이 전부 바뀐다.
3. 얹은 것이 **사진**이면(소리 스트림 없음) 켜져 있어도 `[N:a]`가 그래프에
   안 들어간다 -- 넣으면 ffmpeg가 통째로 죽는다.
4. 세션에서 렌더 계획까지 한 줄로 꿰인다 -- 층마다 초록인데 사이에서 값이
   조용히 떨어지는 사고가 이 저장소에 되풀이됐다
   (`[[videobox-parts-exist-but-nothing-calls-them]]`).

지문 보호(`fingerprint_exact_preview`)도 하나 더 잰다: 기본값일 때
`CompositionPlan.canonical_dict()`에 `preserve_source_audio` 열쇠가 아예 안 생겨야
한다. 실으면 지금 있는 편집본(전부 기본값)의 지문이 전부 바뀌어 캐시된 미리보기가
통째로 무효가 된다 -- `_canonical_item`이 `track_order`를 0일 때 빼는 것과 같은
걱정이다.
"""

from __future__ import annotations

from videobox_core_engine.composition_plan import (
    CompositionItem,
    CompositionPlan,
    materialize_editing_session_timeline,
)
from videobox_core_engine.editing_session import build_editing_session, update_segment_image_overlay
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer


def _overlay_item(*, clip_id: str = "o1", preserve_source_audio: bool | None = None) -> CompositionItem:
    media_controls: dict[str, object] = {}
    if preserve_source_audio is not None:
        media_controls["preserve_source_audio"] = preserve_source_audio
    return CompositionItem(
        clip_id=clip_id, track_type="overlay",
        asset_uri=f"local://{clip_id}", asset_id="asset_overlay",
        start_sec=1.0, end_sec=4.0, source_in_sec=0.0, source_out_sec=3.0,
        overlay_type="image_overlay",
        overlay_payload={"overlay_type": "image_overlay", "asset_id": "asset_overlay"},
        media_controls=media_controls,
    )


def _plan_with(item: CompositionItem) -> CompositionPlan:
    narration = CompositionItem(
        clip_id="n1", track_type="narration", asset_uri="local://n1", asset_id="asset_narration",
        start_sec=0.0, end_sec=4.0, source_in_sec=0.0, source_out_sec=4.0,
    )
    return CompositionPlan(
        width=1920, height=1080, fps_num=30, fps_den=1,
        sample_aspect_ratio="1:1", rotation=0, items=(narration, item),
    )


def test_preserved_overlay_audio_is_mixed_into_the_graph() -> None:
    """`preserve_source_audio=True`면 오버레이 클립의 소리가 그래프에 실린다."""
    item = _overlay_item(preserve_source_audio=True)
    plan = _plan_with(item)
    renderer = FfmpegFinalRenderer(store=None)

    graph = renderer.build_plan_audio_filter_graph(
        composition_plan=plan, source_indices={"n1": 0, "o1": 1},
    )

    assert "[1:a]" in graph, graph
    assert "atrim=start=0.0:end=3.0" in graph, graph


def test_default_overlay_audio_graph_is_unchanged() -> None:
    """기본값(꺼짐)이면 오버레이가 있든 없든 오디오 그래프가 **한 글자까지 같다**.

    이게 제일 중요한 시험이다 -- 기본값이 움직이면 지금 있는 완성본 전부의
    소리가 바뀐다. `preserve_source_audio`를 아예 안 준 오버레이와,
    오버레이 자체가 없는 계획을 나란히 만들어 그래프 문자열을 통째로 비교한다.
    """
    renderer = FfmpegFinalRenderer(store=None)

    with_off_overlay = renderer.build_plan_audio_filter_graph(
        composition_plan=_plan_with(_overlay_item(preserve_source_audio=None)),
        source_indices={"n1": 0, "o1": 1},
    )

    narration_only_plan = CompositionPlan(
        width=1920, height=1080, fps_num=30, fps_den=1,
        sample_aspect_ratio="1:1", rotation=0,
        items=(CompositionItem(
            clip_id="n1", track_type="narration", asset_uri="local://n1", asset_id="asset_narration",
            start_sec=0.0, end_sec=4.0, source_in_sec=0.0, source_out_sec=4.0,
        ),),
    )
    narration_only = renderer.build_plan_audio_filter_graph(
        composition_plan=narration_only_plan, source_indices={"n1": 0},
    )

    assert with_off_overlay == narration_only, (with_off_overlay, narration_only)
    assert "[1:a]" not in with_off_overlay


def test_a_photo_overlay_never_reaches_into_a_missing_audio_stream() -> None:
    """얹은 것이 **사진**이면(소리 스트림 없음) 켜져 있어도 `[N:a]`를 안 만든다.

    없는 스트림을 그래프에 넣으면 ffmpeg가 통째로 실패한다. 이 정보는 렌더
    준비 단계에서 ffprobe로 재서 `soundless_source_clip_ids`에 담기고,
    b-roll과 같은 방식으로 오디오 그래프가 그 집합을 보고 건너뛴다.
    """
    item = _overlay_item(preserve_source_audio=True)
    plan = _plan_with(item)
    renderer = FfmpegFinalRenderer(store=None)

    graph = renderer.build_plan_audio_filter_graph(
        composition_plan=plan, source_indices={"n1": 0, "o1": 1},
        soundless_source_clip_ids={"o1"},
    )

    assert "[1:a]" not in graph, graph


def test_default_overlay_leaves_no_new_key_in_the_exact_preview_fingerprint() -> None:
    """`preserve_source_audio`를 안 고른 오버레이는 `canonical_dict()`에 그 열쇠가
    (`overlay_payload`에도 `media_controls`에도) 아예 없어야 한다 -- 실으면
    `fingerprint_exact_preview`가 바뀌어 지금 있는 편집본의 캐시된 미리보기가
    통째로 무효가 된다.
    """
    plan = _plan_with(_overlay_item(preserve_source_audio=None))

    canonical = plan.canonical_dict()

    overlay_items = [item for item in canonical["items"] if item["track_type"] == "overlay"]
    assert overlay_items, canonical
    for item in overlay_items:
        assert "preserve_source_audio" not in item["overlay_payload"], item
        assert item["media_controls"] == {}, item


def test_a_choice_made_on_the_session_survives_all_the_way_to_the_audio_graph() -> None:
    """세션에서 고른 값이 **세션 -> 합성 계획 -> 오디오 그래프**까지 한 줄로 꿰이는가.

    이 저장소가 되풀이한 실패다: 층마다 시험이 초록인데 층 사이에서 값이 조용히
    떨어진다. 그래서 사진 오버레이 프리셋 때처럼(`test_image_overlay_presets_reach_the_render.py`)
    층별 시험 말고 한 줄로 꿰는 시험을 따로 둔다.
    """
    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[{"segment_id": "segment_001", "text": "얹을 영상", "start_sec": 0.0, "end_sec": 3.0}],
    )
    updated = update_segment_image_overlay(
        session=session, segment_id="segment_001", asset_id="asset_overlay_video",
        text="", preserve_source_audio=True,
    )

    materialized = materialize_editing_session_timeline(
        timeline={"tracks": []}, editing_session=updated, project_id="project_001"
    )
    plan = CompositionPlan.from_timeline(timeline=materialized)

    overlay_items = [item for item in plan.items if item.track_type == "overlay"]
    assert overlay_items, materialized["tracks"]
    assert overlay_items[0].media_controls.get("preserve_source_audio") is True

    graph = FfmpegFinalRenderer(store=None).build_plan_audio_filter_graph(
        composition_plan=plan, source_indices={overlay_items[0].clip_id: 0},
    )
    assert "[0:a]" in graph, graph


def test_session_layer_only_writes_the_key_when_explicitly_chosen() -> None:
    """`update_segment_image_overlay`도 같은 규칙 -- 안 주면 열쇠 자체가 없다.

    프리셋 넷(`vertical`·`horizontal`·`size`·`motion`)이 이미 이 규칙을 따르고
    있고, `preserve_source_audio`도 같은 이름을 b-roll에서 그대로 빌려 온
    개념이니 같은 규칙을 따라야 한다.
    """
    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[{"segment_id": "seg_001", "text": "얹을 영상", "start_sec": 0.0, "end_sec": 3.0}],
    )

    without_choice = update_segment_image_overlay(
        session=session, segment_id="seg_001", asset_id="asset_video_001", text="",
    )
    assert "preserve_source_audio" not in without_choice["segments"][0]["visual_overlays"][0]

    with_choice = update_segment_image_overlay(
        session=session, segment_id="seg_001", asset_id="asset_video_001", text="",
        preserve_source_audio=True,
    )
    assert with_choice["segments"][0]["visual_overlays"][0]["preserve_source_audio"] is True
