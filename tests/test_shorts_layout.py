"""숏폼을 **숏폼처럼** 짠다 -- 제목 띠 + 영상 띠 + 아래 검정.

대표님이 참고 숏폼 넷을 주면서 하신 말(2026-09-12):

> "이런거 보면 상단에 제목이 있네."
> "오히려 위 아래를 어차피 잘 안보니까 이렇게 만드는것도 나을거 같어"
> "유저 입장에서도 상단에 텍스트가 눈에 띄게 만들고, 하단에 영상 보여주고
> 자막을 가운데 달던지, 하위로 넣던지 해도 좋을것 같거든"

참고 넷(1080×1920)을 픽셀로 쟀다(`scratchpad/measure_reference_short.py`).
눈대중이 아니다:

| | ref1 | ref2 | ref3 | ref4 |
|---|---|---|---|---|
| 제목 띠 | 0~21.4% | 0~27.4% | 0~28.6% | 0~20.8% |
| 영상 띠 | 21.4~78.5% | 27.4~66.6% | 28.7~71.3% | 20.9~93.9% |
| 영상 가로:세로 | 0.98:1 | 1.43:1 | 1.32:1 | -- |
| 아래 검정 | 21.5% | 33.4% | 28.7% | 6.1% |

여기서 이 시험이 지키는 것 셋:

1. 제목 띠는 화면 위 **20.8~28.6%** 안에 있다. 줄 수로 커지되 그 범위를 안 넘는다.
2. 영상 띠는 **16:9보다 세로로 길다**(참고 0.98~1.43 : 1, 16:9는 1.78 : 1).
   그래서 1920×1080 원본을 **폭 그대로** 담아도 자를 이유가 없다.
3. 아래는 검정이다. 참고 넷 중 둘이 화면의 29~33%를 그냥 비웠다.

**과제 B(`전체 담기`) 위에 얹는다.** 맞춤 계산은 `_frame_fit_chain` 한 함수이고
이 레이아웃도 그 한 자리를 쓴다 -- 두 벌로 나누지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.ass_subtitles import render_shorts_title_ass
from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer, FinalRenderError
from videobox_core_engine.output_variants import (
    MaterializedVariant,
    build_variant_timeline_payload,
)
from videobox_domain_models.output_variants import OutputVariant, VariantOverride
from videobox_core_engine.shorts_layout import (
    REFERENCE_VIDEO_BAND_ASPECT,
    ShortsTitle,
    shorts_geometry,
    shorts_title_from_override,
)

CANVAS = {"width": 1080, "height": 1920}

# 참고 숏폼 넷에서 실제로 잰 제목 띠의 아래 끝(화면 높이 대비).
MEASURED_TITLE_BAND_RANGE = (0.208, 0.286)


def _lines(count: int) -> tuple[str, ...]:
    """줄 수만 중요한 시험에서 쓰는 제목. **길이는 화면 폭 안**이어야 한다 --
    긴 줄은 글자를 줄이므로 띠 높이가 달라진다(그게 바로 아래 시험들의 전제다)."""
    return tuple(f"{index}번째 줄" for index in range(1, count + 1))


def test_the_title_band_stays_inside_what_the_references_measured() -> None:
    """줄 수로 커지되 참고 넷이 실제로 쓴 범위를 벗어나지 않는다."""
    for line_count in (1, 2, 3):
        geometry = shorts_geometry(**CANVAS, lines=_lines(line_count))
        share = geometry.title_band_height_px / CANVAS["height"]
        assert MEASURED_TITLE_BAND_RANGE[0] <= share <= MEASURED_TITLE_BAND_RANGE[1], (
            f"{line_count}줄 제목 띠가 {share:.1%}다 -- 참고 넷은 20.8~28.6%였다"
        )


def test_more_lines_need_more_band() -> None:
    """고정 퍼센트를 박지 않는다 -- 3줄 제목은 2줄보다 자리를 더 먹는다."""
    two = shorts_geometry(**CANVAS, lines=_lines(2))
    three = shorts_geometry(**CANVAS, lines=_lines(3))
    assert three.title_band_height_px > two.title_band_height_px


def test_the_video_band_is_taller_than_sixteen_by_nine() -> None:
    """**이것이 이 과제의 핵심이다.**

    영상 띠가 16:9(1.78:1)보다 세로로 길어야 1920×1080 원본을 폭 그대로 담을 수
    있다. 참고 넷은 0.98~1.43 : 1이었다.
    """
    _, _, band_width, band_height = shorts_geometry(**CANVAS, lines=_lines(2)).video_box
    aspect = band_width / band_height
    assert aspect < 16 / 9, "영상 띠가 16:9보다 납작하면 좌우를 자르게 된다"
    assert 0.98 <= aspect <= 1.43, f"참고 넷의 범위를 벗어났다: {aspect:.2f}:1"
    assert aspect == pytest.approx(REFERENCE_VIDEO_BAND_ASPECT, abs=0.01)


def test_the_video_band_starts_right_under_the_title_and_leaves_black_below() -> None:
    """제목 바로 아래에 영상, 그 아래는 검정. 참고 넷이 전부 이 모양이다."""
    geometry = shorts_geometry(**CANVAS, lines=_lines(2))
    box_x, box_y, box_width, box_height = geometry.video_box
    assert box_x == 0 and box_width == CANVAS["width"], "폭은 통째로 쓴다"
    assert box_y == geometry.title_band_height_px, "영상은 제목 띠 바로 아래에서 시작한다"
    black_below = CANVAS["height"] - (box_y + box_height)
    assert black_below > 0, "아래를 비우지 않으면 참고 숏폼의 모양이 아니다"
    share = black_below / CANVAS["height"]
    assert 0.25 <= share <= 0.40, f"아래 검정이 {share:.1%}다 -- 참고 둘은 29~33%였다"


def test_the_band_never_runs_off_the_canvas() -> None:
    """제목이 세 줄이어도 영상 띠가 화면 밖으로 나가지 않는다."""
    for line_count in (1, 2, 3):
        geometry = shorts_geometry(**CANVAS, lines=_lines(line_count))
        _, box_y, _, box_height = geometry.video_box
        assert box_y + box_height <= CANVAS["height"]


def test_a_title_with_no_lines_is_no_layout() -> None:
    """제목 띠를 끄면 **과제 B의 동작 그대로**다 -- 화면 전체에 원본을 담는다."""
    assert shorts_title_from_override({"title_lines": []}) is None
    assert shorts_title_from_override(None) is None
    assert shorts_title_from_override({"title_lines": ["훅"], "hidden": True}) is None


def test_the_stored_title_survives_being_turned_off() -> None:
    """끄기가 문구를 지우지 않는다 -- 지우면 다시 켤 때 되돌릴 것이 없다."""
    title = shorts_title_from_override({"title_lines": ["한 줄", "두 줄"], "highlight": "두"})
    assert title == ShortsTitle(lines=("한 줄", "두 줄"), highlight="두")


def test_a_made_up_title_is_refused_rather_than_trimmed_silently() -> None:
    """지어내지 않는다. 줄이 넷이면 조용히 셋으로 자르지 않고 거절한다."""
    with pytest.raises(ValueError, match="title"):
        shorts_title_from_override({"title_lines": ["1", "2", "3", "4"]})


# --- 렌더러: 맞춤 계산은 `_frame_fit_chain` **한 함수**다 -------------------


def _renderer(title: ShortsTitle | None) -> FfmpegFinalRenderer:
    return FfmpegFinalRenderer(
        store=None, video_width=1080, video_height=1920, shorts_title=title
    )


TWO_LINE_TITLE = ShortsTitle(lines=("내과전문의가 말하는", "노안이 되는 이유"), highlight="노안")


def test_without_a_title_nothing_changes() -> None:
    """제목 띠를 안 쓰면 과제 B의 사슬이 **글자 하나도 달라지지 않는다.**"""
    assert _renderer(None)._broll_fit_transform({"fit": "blur"}) == FfmpegFinalRenderer(
        store=None, video_width=1080, video_height=1920
    )._broll_fit_transform({"fit": "blur"})


def test_the_picture_is_fitted_to_the_band_not_the_canvas() -> None:
    """**과제 B의 값(`전체 담기`)을 띠 안에서 그대로 쓴다.**

    띠 크기로 줄여 담고(`decrease`), 남는 자리는 같은 그림의 흐린 확대본으로
    채우고, 마지막에 화면 크기로 `pad`해서 띠를 제 자리에 놓는다.
    """
    geometry = shorts_geometry(**CANVAS, lines=TWO_LINE_TITLE.lines)
    _, band_top, band_width, band_height = geometry.video_box

    chain = _renderer(TWO_LINE_TITLE)._broll_fit_transform({"fit": "blur"}, tag="c0")

    assert f"scale={band_width}:{band_height}:force_original_aspect_ratio=decrease" in chain
    assert "gblur" in chain, "띠 안의 남는 자리를 흐린 배경으로 채우지 않으면 검은 띠가 생긴다"
    assert f"pad=1080:1920:0:{band_top}:black" in chain, "띠를 제 자리에 놓지 않으면 제목과 겹친다"


def test_filling_the_band_still_means_cropping_when_the_creator_asks_for_it() -> None:
    """`꽉 채우기`를 고른 사람에게는 띠를 꽉 채워 준다 -- 조용히 다른 값이 되지 않는다."""
    _, band_top, band_width, band_height = shorts_geometry(**CANVAS, lines=TWO_LINE_TITLE.lines).video_box

    chain = _renderer(TWO_LINE_TITLE)._broll_fit_transform({"fit": "crop"}, tag="c0")

    assert f"crop={band_width}:{band_height}" in chain
    assert f"pad=1080:1920:0:{band_top}:black" in chain


def test_the_legacy_concat_path_refuses_rather_than_dropping_the_title() -> None:
    """제목 글자는 그래프 경로에만 있다. 조각 이어붙이기로는 **안 내보낸다.**

    이 저장소가 가장 비싸게 배운 것이 "화면엔 있는데 완성본엔 없다"이고, 그 사고는
    렌더 경로 둘 중 한 곳만 고쳐서 났다.
    """
    with pytest.raises(FinalRenderError, match="title band"):
        _renderer(TWO_LINE_TITLE).render_timeline_to_mp4(
            project_id="p1", timeline={"tracks": []}, output_path=Path("nope.mp4")
        )


def test_the_title_is_drawn_with_the_word_the_creator_chose_in_green() -> None:
    """핵심어만 색이 바뀐다. 못 고르면 전부 흰색이다 -- **지어내지 않는다.**"""
    geometry = shorts_geometry(**CANVAS, lines=TWO_LINE_TITLE.lines)

    coloured = render_shorts_title_ass(
        TWO_LINE_TITLE, geometry=geometry, video_width=1080, video_height=1920,
        duration_sec=30.0, font_family="Pretendard",
    )
    plain = render_shorts_title_ass(
        ShortsTitle(lines=TWO_LINE_TITLE.lines), geometry=geometry,
        video_width=1080, video_height=1920, duration_sec=30.0, font_family="Pretendard",
    )

    assert "노안" in coloured
    assert coloured.count("\\c&H0066FF33") == 1, "강조는 한 번이다 -- 두 번이면 강조가 아니다"
    assert "\\c&H0066FF33" not in plain, "못 고른 낱말을 지어내서 칠하지 않는다"
    # 두 줄이 **다른 높이**에 놓인다. 한 자리에 겹치면 제목이 안 읽힌다.
    # `Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,...` -- MarginV가 여덟째다.
    margins = [line.split(",")[7] for line in coloured.splitlines() if line.startswith("Dialogue")]
    assert len(margins) == 2 and margins[0] != margins[1]


def test_the_whole_title_block_stays_inside_the_band() -> None:
    """글자가 띠를 넘으면 영상 위에 걸친다."""
    for line_count in (1, 2, 3):
        geometry = shorts_geometry(**CANVAS, lines=_lines(line_count))
        block_bottom = (
            geometry.first_line_top_px
            + line_count * geometry.font_size_px
            + (line_count - 1) * geometry.line_gap_px
        )
        assert geometry.first_line_top_px >= 0
        assert block_bottom <= geometry.title_band_height_px, (
            f"{line_count}줄 제목이 띠({geometry.title_band_height_px}px)를 {block_bottom}px로 넘는다"
        )


# --- 배선: 제목이 저장소에서 렌더까지 실제로 닿는가 ------------------------


def _variant(kind: str, layout: dict | None) -> OutputVariant:
    return OutputVariant(
        variant_id="variant-short",
        kind=kind,
        source_session_id="session-1",
        source_session_revision=3,
        variant_revision=2,
        overrides=VariantOverride(layout=layout),
        selected_segment_ids=("seg-1",) if kind == "vertical_highlight" else None,
    )


def _derived() -> MaterializedVariant:
    return MaterializedVariant(
        source_session_id="session-1",
        source_session_revision=3,
        source_variant_id="variant-short",
        source_variant_revision=2,
        segments=({"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0},),
    )


TITLE_OVERRIDE = {"title_lines": ["훅이 되는 첫 줄", "결과가 되는 둘째 줄"], "highlight": "결과"}


def test_the_title_reaches_the_variant_timeline() -> None:
    """**만든 값을 아무도 안 읽으면 없는 것과 같다.** 배선이 가장 자주 샌다."""
    variant = _variant("vertical_highlight", TITLE_OVERRIDE)

    payload = build_variant_timeline_payload(
        master_timeline={"output": {"width": 1920, "height": 1080}, "tracks": []},
        variant_kind=variant.kind,
        derived=_derived(),
        overrides=variant.overrides,
    )

    assert payload["shorts_layout"] == TITLE_OVERRIDE


def test_only_the_short_form_gets_a_title_band() -> None:
    """가로·세로 전체본은 원본과 같은 이야기를 다른 화면비로 내보내는 것이다."""
    for kind in ("horizontal", "vertical_full"):
        payload = build_variant_timeline_payload(
            master_timeline={"tracks": []},
            variant_kind=kind,
            derived=_derived(),
            overrides=VariantOverride(layout=TITLE_OVERRIDE),
        )
        assert "shorts_layout" not in payload


def test_the_plan_carries_the_title_so_the_cached_preview_cannot_miss_it() -> None:
    """계획에 실려야 지문이 달라진다 -- 아니면 제목 없는 미리보기가 영원히 남는다."""
    plan = CompositionPlan.from_timeline(
        timeline={
            "output": {"width": 1080, "height": 1920},
            "shorts_layout": TITLE_OVERRIDE,
            "tracks": [],
        }
    )

    assert plan.shorts_layout == TITLE_OVERRIDE
    assert plan.canonical_dict()["shorts_layout"] == TITLE_OVERRIDE
    # 제목이 없는 판은 지문 모양이 **하나도 안 바뀐다.** 바뀌면 지금 있는 편집본
    # 전부의 캐시된 미리보기가 무효가 된다.
    assert "shorts_layout" not in CompositionPlan.from_timeline(
        timeline={"output": {"width": 1080, "height": 1920}, "tracks": []}
    ).canonical_dict()


def test_a_range_preview_keeps_the_title_and_the_muted_lanes() -> None:
    """구간 미리보기도 같은 모양이어야 한다.

    자리로 넘기던 때 열째 자리에 `version`이 들어가 `muted_tracks`로 앉았다 --
    구간 미리보기에서 음소거가 조용히 무시되고 있었다. 칸 이름으로 바꾸면서
    그 자리도 같이 지킨다.
    """
    plan = CompositionPlan.from_timeline(
        timeline={
            "output": {"width": 1080, "height": 1920},
            "shorts_layout": TITLE_OVERRIDE,
            "track_states": {"bgm": {"muted": True}},
            "tracks": [{"track_type": "broll", "clips": [
                {"clip_id": "c1", "asset_uri": "local://a", "start_sec": 0.0, "end_sec": 6.0}
            ]}],
        }
    )

    ranged = plan.for_range(start_sec=1.0, end_sec=4.0)

    assert ranged.shorts_layout == TITLE_OVERRIDE
    assert ranged.muted_tracks == plan.muted_tracks == frozenset({"bgm"})
    assert ranged.version == plan.version


def test_the_title_band_turns_the_blurred_backdrop_back_off() -> None:
    """**실물을 보고 정했다**(2026-09-12, 대표님 영상으로 둘 다 구웠다).

    과제 B가 `전체 담기`(흐린 배경)를 기본으로 삼은 이유는 화면 전체를 채우려다
    위아래 68%가 검은 띠가 되기 때문이었다. 제목 띠가 걸리면 그 이유가 사라진다 --
    영상 띠를 1.3:1로 잡아 폭 그대로 담으므로 띠 안에서 남는 자리가 위아래
    111픽셀씩뿐이다. 그 자리를 흐리게 채우면 **흐린 띠 두 줄**이 생겨 결함처럼
    보이고, 검정으로 두면 제목 띠·아래 검정과 이어져 참고 숏폼 넷과 같은 모양이 된다.
    """
    master = {
        "tracks": [{"track_type": "broll", "clips": [{"clip_id": "c1", "media_controls": {}}]}],
    }

    with_title = build_variant_timeline_payload(
        master_timeline=master, variant_kind="vertical_highlight", derived=_derived(),
        overrides=VariantOverride(layout=TITLE_OVERRIDE),
    )
    without_title = build_variant_timeline_payload(
        master_timeline=master, variant_kind="vertical_highlight", derived=_derived(),
        overrides=VariantOverride(),
    )

    assert with_title["tracks"][0]["clips"][0]["media_controls"]["fit"] == "fit"
    # 제목이 없으면 과제 B 그대로다 -- 뒤집지 않는다.
    assert without_title["tracks"][0]["clips"][0]["media_controls"]["fit"] == "blur"


def test_the_screen_picked_broll_follows_the_same_decision() -> None:
    """화면에서 고른 영상(`broll_override`)은 트랙을 안 지나간다 -- 2026-09-12에
    같은 자리에서 검은 띠 68%가 새어 나간 경로다. 여기도 같은 답이어야 한다."""
    from videobox_core_engine.output_variants import variant_render_session

    session = variant_render_session(
        master_session={"segments": [
            {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0,
             "broll_override": {"asset_id": "a1", "media_controls": {}}}
        ]},
        variant_timeline={
            "output": {"width": 1080, "height": 1920},
            "shorts_layout": TITLE_OVERRIDE,
            "segments": [{"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0}],
        },
    )

    assert session["segments"][0]["broll_override"]["media_controls"]["fit"] == "fit"


def test_turning_the_band_off_gives_back_exactly_task_B() -> None:
    """**끈 숏폼은 과제 B 그대로여야 한다.**

    한때 "칸이 있는가"로 물었더니 껐을 때 렌더는 화면 전체에 담는데 맞춤은 검정
    여백을 전제해서, 과제 B가 없앤 **위아래 68% 검은 띠**가 되돌아올 자리가 있었다.
    """
    hidden = {**TITLE_OVERRIDE, "hidden": True}
    payload = build_variant_timeline_payload(
        master_timeline={"tracks": [{"track_type": "broll", "clips": [{"clip_id": "c1"}]}]},
        variant_kind="vertical_highlight", derived=_derived(),
        overrides=VariantOverride(layout=hidden),
    )

    assert payload["tracks"][0]["clips"][0]["media_controls"]["fit"] == "blur"
    # 문구는 그대로 실려 있다 -- 다시 켤 때 되돌릴 것이 있어야 한다.
    assert payload["shorts_layout"] == hidden
