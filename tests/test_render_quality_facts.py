from __future__ import annotations

from videobox_core_engine.composition_plan import CaptionCue, CompositionItem, CompositionPlan
from videobox_core_engine.render_quality_facts import composition_quality_facts


def _plan(*, items: tuple[CompositionItem, ...] = (), captions: tuple[CaptionCue, ...] = ()) -> CompositionPlan:
    return CompositionPlan(
        width=1920, height=1080, fps_num=30, fps_den=1,
        sample_aspect_ratio="1:1", rotation=0,
        items=items, captions=captions,
    )


def _broll(clip_id: str, start: float, end: float) -> CompositionItem:
    return CompositionItem(
        clip_id=clip_id, track_type="broll", asset_uri=f"local://{clip_id}", asset_id=clip_id,
        start_sec=start, end_sec=end, source_in_sec=0.0, source_out_sec=end - start,
    )


def test_it_counts_the_scenes_and_how_long_they_run() -> None:
    # 자기개선의 재료는 "이 영상이 어땠는가"를 숫자로 남기는 것부터 시작한다.
    facts = composition_quality_facts(_plan(items=(_broll("a", 0.0, 5.0), _broll("b", 5.0, 15.0))))

    assert facts["scene_count"] == 2
    assert facts["average_scene_sec"] == 7.5
    assert facts["duration_sec"] == 15.0


def test_it_reports_captions_that_sit_on_top_of_each_other() -> None:
    # 자막이 겹치면 화면에서 서로를 가린다. 렌더는 성공하므로 재지 않으면 알 수 없다.
    overlapping = _plan(captions=(
        CaptionCue(0.0, 3.0, "첫 줄"),
        CaptionCue(2.0, 5.0, "겹치는 줄"),
        CaptionCue(6.0, 8.0, "안 겹치는 줄"),
    ))

    facts = composition_quality_facts(overlapping)

    assert facts["caption_count"] == 3
    assert facts["caption_overlap_count"] == 1


def test_touching_captions_do_not_count_as_overlapping() -> None:
    # 앞 자막이 끝나는 순간 다음이 시작하는 것은 정상이다. 이걸 겹침으로 세면
    # 멀쩡한 영상이 전부 문제로 보인다.
    facts = composition_quality_facts(_plan(captions=(
        CaptionCue(0.0, 3.0, "앞"),
        CaptionCue(3.0, 6.0, "뒤"),
    )))

    assert facts["caption_overlap_count"] == 0


def test_an_empty_plan_reports_zeroes_rather_than_dividing_by_zero() -> None:
    facts = composition_quality_facts(_plan())

    assert facts["scene_count"] == 0
    assert facts["average_scene_sec"] == 0.0
    assert facts["caption_overlap_count"] == 0


def test_it_only_counts_visual_scenes_not_music_and_effects() -> None:
    # 장면 수는 보이는 것의 수다. 음악 한 곡을 장면으로 세면 숫자가 뜻을 잃는다.
    music = CompositionItem(
        clip_id="m", track_type="bgm", asset_uri="local://m", asset_id="m",
        start_sec=0.0, end_sec=20.0, source_in_sec=0.0, source_out_sec=20.0,
    )
    facts = composition_quality_facts(_plan(items=(_broll("a", 0.0, 10.0), music)))

    assert facts["scene_count"] == 1
