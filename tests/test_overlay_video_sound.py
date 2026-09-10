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

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import (
    CompositionItem,
    CompositionPlan,
    materialize_editing_session_timeline,
)
from videobox_core_engine.editing_session import build_editing_session, update_segment_image_overlay
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


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


def test_an_explicit_false_leaves_the_same_fingerprint_as_never_touching_the_switch() -> None:
    """리뷰 발견사항 3: 화면은 저장할 때마다 `preserve_source_audio`에 명시적
    `True`/`False`를 싣는다. 소리를 만진 적 없는 오버레이를 그냥 다시
    저장해도(즉 `False`가 찍혀도) `CompositionPlan.canonical_dict()`가
    **한 글자도 다르지 않아야** 한다 -- 다르면 `fingerprint_exact_preview`가
    움직여 캐시된 정확 미리보기가 전부 무효가 되는데, 완성본은 바이트 하나도
    안 바뀐다.
    """
    session = build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[{"segment_id": "segment_001", "text": "얹을 사진", "start_sec": 0.0, "end_sec": 3.0}],
    )
    never_touched = update_segment_image_overlay(
        session=session, segment_id="segment_001", asset_id="asset_overlay", text="",
    )
    explicit_false = update_segment_image_overlay(
        session=session, segment_id="segment_001", asset_id="asset_overlay", text="",
        preserve_source_audio=False,
    )

    def _canonical(updated_session: dict) -> dict:
        materialized = materialize_editing_session_timeline(
            timeline={"tracks": []}, editing_session=updated_session, project_id="project_001"
        )
        return CompositionPlan.from_timeline(timeline=materialized).canonical_dict()

    assert _canonical(never_touched) == _canonical(explicit_false)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_plan_render_survives_a_soundless_photo_overlay_with_source_audio_kept(tmp_path: Path) -> None:
    """리뷰 발견사항 1: `:1573`(오버레이 입력 등록 시점의 무음 판정)을 실제 렌더로 지킨다.

    기존 `test_a_photo_overlay_never_reaches_into_a_missing_audio_stream`은
    `soundless_source_clip_ids={"o1"}`를 손으로 넣어 **소비자**(`:1390`
    부근, `build_plan_audio_filter_graph`)만 잰다. 이 집합을 실제로 채우는
    등록 코드(`:1573`)는 아무 시험도 안 지나간다 -- 지워도 전체 스위트가
    초록이다.

    b-roll의 실제 렌더 시험(`test_plan_render_survives_a_soundless_broll_with_source_audio_kept`,
    `test_ffmpeg_final_renderer.py:1105`)과 같은 모양으로, **사진** 오버레이에
    `preserve_source_audio=True`를 걸고 계획 기반 경로
    (`composition_plan`을 넘겨 `_render_composition_plan_to_mp4`로 들어가는 길)로
    끝까지 태운다. `:1573`이 없으면 오디오 그래프에 존재하지 않는 스트림
    `[N:a]`가 실려 ffmpeg가 렌더 전체를 실패시킨다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="photo overlay sound must not crash render")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_file)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll_file = tmp_path / "black_broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=4", str(broll_file)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    image_file = tmp_path / "yellow_overlay.png"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=yellow:s=80x60", "-frames:v", "1", str(image_file)])
    image_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=image_file)
    source_timeline = {
        "project_id": project.project_id,
        "timeline_id": "timeline_photo_overlay_sound",
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [
                {"segment_id": "scene-before", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 0.0, "end_sec": 1.0},
                {"segment_id": "scene-overlay", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 1.0, "end_sec": 3.0},
                {"segment_id": "scene-after", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 3.0, "end_sec": 4.0},
            ]},
            {"track_type": "broll", "clips": [
                {"segment_id": "scene-before", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 1.0},
                {"segment_id": "scene-overlay", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 1.0, "end_sec": 3.0},
                {"segment_id": "scene-after", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 3.0, "end_sec": 4.0},
            ]},
        ],
    }
    editing_session = build_editing_session(
        project_id=project.project_id,
        timeline=source_timeline,
        segments=[
            {"segment_id": "scene-before", "text": "앞", "start_sec": 0.0, "end_sec": 1.0},
            {"segment_id": "scene-overlay", "text": "오버레이", "start_sec": 1.0, "end_sec": 3.0},
            {"segment_id": "scene-after", "text": "뒤", "start_sec": 3.0, "end_sec": 4.0},
        ],
    )
    # 얹은 것은 사진이다 -- 소리 스트림이 아예 없다. 그런데도 원본 소리
    # 살리기를 켠다(owner가 화면 없이 유진에게만 부탁했을 때 실제로 생기는
    # 조합, Finding 2 참고).
    editing_session = update_segment_image_overlay(
        session=editing_session,
        segment_id="scene-overlay",
        asset_id=image_asset.asset_id,
        text="Overlay proof",
        preserve_source_audio=True,
    )
    timeline = materialize_editing_session_timeline(
        timeline=source_timeline,
        editing_session=editing_session,
        project_id=project.project_id,
    )
    output_path = tmp_path / "photo_overlay_sound.mp4"
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15)

    # 실패하면(즉 ffmpeg가 존재하지 않는 오디오 스트림 참조로 죽으면) 여기서
    # 예외가 난다. 렌더 전체가 살아 있어야 한다는 것이 이 시험의 요지다.
    renderer.render_timeline_to_mp4(
        project_id=project.project_id,
        timeline=timeline,
        output_path=output_path,
        composition_plan=renderer.extract_composition_plan(timeline=timeline),
    )

    assert output_path.is_file()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
        capture_output=True, text=True, check=True,
    )
    assert float(probe.stdout.strip()) == pytest.approx(4.0, abs=0.6)
