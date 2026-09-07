"""설명 카드·표가 자막을 가리지 않는지 **픽셀로** 잰다.

2026-08-20 완성본(`artifacts/dogfood-2026-08-20/완성본-2.mp4`)에서 owner가 눈으로
찾은 결함이다. 설명 카드의 제목이 자막 배경 상자에 절반 가렸고, 표의 한 줄은
자막에 통째로 가렸다.

## 왜 문자열이 아니라 픽셀인가

자막은 **ASS**(libass)로 그리고 오버레이 글줄은 **drawtext**로 그린다. 두 필터
문자열은 서로를 전혀 모른다 -- 한쪽만 읽는 검사는 둘이 같은 자리에 겹쳐 그려도
아무 말도 하지 않는다. 실제로 그랬다: 오버레이 검사도 자막 검사도 각자 초록인
동안 완성본에서는 글자가 서로를 덮고 있었다.

그래서 여기서는 회색 바탕에 **실제로 굽고**, 자막이 건드린 가로줄과 오버레이가
건드린 가로줄을 각각 모아 교집합을 본다. 교집합이 비어 있지 않으면 가린 것이다.

## 재서 알아낸 숫자 (1920x1080, ffmpeg 8.1.1 libass)

- 자막 한 줄(`font_size_px=54`, `position_y_percent=88`, 배경 상자 켬)이 먹는 줄:
  **888..957**. 예측식 `바닥 - 줄수*크기 - 여백` = 889 -- libass 반올림으로 1px
  위로 나가므로 띠에 여유 1px을 둔다.
- 줄 높이는 ASS `Fontsize`와 같았다(54). 번들 글꼴 7종 전부 같은 줄을 먹었다 --
  띠 높이는 글꼴에 흔들리지 않는다.
- 결함이 있던 오버레이 3줄은 **861..1027**을 먹어 자막과 67~70줄이 겹쳤다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from videobox_core_engine.ass_subtitles import render_editing_session_ass
from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_storage.local_project_store import LocalProjectStore


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FONTS = ROOT / "assets/fonts/korean"
OVERLAY_FONT = BUNDLED_FONTS / "NotoSansKR-Variable.ttf"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

_WIDTH, _HEIGHT = 1920, 1080
# 회색 바탕에 굽는다. 자막 상자(빨강)도 오버레이 상자(검정)도 바탕과 다르므로
# 검은 바탕에서는 안 보이던 **상자까지** 잡힌다. 글자만 재면 상자에 가린 것을 놓친다.
_CANVAS = "0x808080"
_CANVAS_LEVEL = 0x80
_INK_THRESHOLD = 12

_CAPTION_TEXT = "이 장면의 자막 한 줄"
_CARD_LINES = ("대본 한 장이면 됩니다", "제목·자막·B-roll까지", "한 번에 붙습니다")
_TABLE_OVERLAY: dict[str, Any] = {
    "overlay_type": "table_overlay",
    "columns": ["항목", "값"],
    "rows": [["글꼴", "도현, 나눔손글씨"], ["길이", "25초"]],
    "start_sec": 1.0,
    "end_sec": 2.0,
}
_CARD_OVERLAY: dict[str, Any] = {
    "overlay_type": "explanation_card",
    "title": _CARD_LINES[0],
    "body": _CARD_LINES[1],
    "text": _CARD_LINES[2],
    "start_sec": 1.0,
    "end_sec": 2.0,
}


def _escape(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def _rows_touched(video_filter: str, tmp_path: Path, tag: str) -> set[int]:
    """이 필터가 회색 바탕에서 실제로 건드린 가로줄 번호."""
    raw_path = tmp_path / f"{tag}.raw"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c={_CANVAS}:s={_WIDTH}x{_HEIGHT}:r=5:d=2",
            "-vf", video_filter, "-ss", "1.2", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw_path),
        ],
        check=True, capture_output=True, timeout=300,
    )
    data = raw_path.read_bytes()
    stride = _WIDTH * 3
    return {
        y for y in range(_HEIGHT)
        if any(abs(value - _CANVAS_LEVEL) > _INK_THRESHOLD for value in data[y * stride : (y + 1) * stride])
    }


def _caption_segments(style: dict[str, Any], text: str = _CAPTION_TEXT) -> list[dict[str, Any]]:
    return [{"caption_text": text, "caption_style": style, "start_sec": 0.0, "end_sec": 2.0}]


def _caption_filter(segments: list[dict[str, Any]], tmp_path: Path, tag: str) -> str:
    ass_path = tmp_path / f"{tag}.ass"
    ass_path.write_text(
        render_editing_session_ass(
            {"caption_style": {}, "segments": segments},
            video_width=_WIDTH, video_height=_HEIGHT,
        ),
        encoding="utf-8",
    )
    return f"subtitles=filename='{_escape(ass_path)}':fontsdir='{_escape(BUNDLED_FONTS)}'"


_LABEL = re.compile(r"^(\[[^\]]+\])+|(\[[^\]]+\])+$")


def _drawtext_only(filter_parts: list[str]) -> list[str]:
    """필터 사슬에서 글줄 drawtext만 뽑는다 (앞뒤 라벨은 떼어낸다)."""
    stripped = [_LABEL.sub("", part) for part in filter_parts]
    return [part for part in stripped if part.startswith("drawtext=")]


def _plan_overlay_filters(
    overlay: dict[str, Any], segments: list[dict[str, Any]], tmp_path: Path
) -> list[str]:
    """그래프 경로(`build_plan_filter_graph`)가 실제로 그리는 글줄 필터."""
    plan = CompositionPlan.from_timeline(
        timeline={"output": {"width": _WIDTH, "height": _HEIGHT}, "tracks": [], "export_overlays": [overlay]},
        captions=segments,
    )
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path), video_width=_WIDTH, video_height=_HEIGHT,
        overlay_font_file=str(OVERLAY_FONT),
    )
    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={})
    return _drawtext_only(graph.split(";"))


def _export_path_overlay_filters(
    overlay: dict[str, Any], segments: list[dict[str, Any]], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """조각 이어붙이기 경로(`_apply_export_overlays`)가 실제로 그리는 글줄 필터."""
    captured: dict[str, list[str]] = {}

    def fake_run(self: FfmpegFinalRenderer, command: list[str]) -> subprocess.CompletedProcess:
        captured["graph"] = command[command.index("-filter_complex") + 1].split(";")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(FfmpegFinalRenderer, "_run", fake_run)
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path), video_width=_WIDTH, video_height=_HEIGHT,
        overlay_font_file=str(OVERLAY_FONT),
    )
    renderer._apply_export_overlays(
        project_id="p", video_path=tmp_path / "in.mp4", overlays=[overlay],
        work_dir=tmp_path, captions=segments,
    )
    return _drawtext_only(captured["graph"])


# ---------------------------------------------------------------------------
# 1. 우리가 계산하는 자막 띠가 실제로 구워진 픽셀을 덮는가
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
@pytest.mark.parametrize(
    ("label", "style", "text"),
    [
        ("기본", {"font_family": "Pretendard"}, _CAPTION_TEXT),
        ("배경 상자", {"font_family": "Pretendard", "background_color": "#FF0000FF"}, _CAPTION_TEXT),
        ("위로 올린 자막", {"font_family": "Pretendard", "position_y_percent": 30}, _CAPTION_TEXT),
        ("큰 글씨", {"font_family": "Pretendard", "font_size_px": 90, "background_color": "#FF0000FF"}, _CAPTION_TEXT),
        (
            "직접 넣은 줄바꿈",
            {"font_family": "Pretendard", "background_color": "#FF0000FF"},
            "자막 첫 줄입니다\n자막 둘째 줄입니다",
        ),
        (
            "libass가 스스로 접는 긴 자막",
            {"font_family": "Pretendard", "background_color": "#FF0000FF"},
            "이 자막은 아주 길어서 한 줄에 다 들어가지 못할 만큼 길게 이어지는 문장입니다 정말로 길어요 계속 이어집니다",
        ),
    ],
)
def test_the_caption_band_we_compute_covers_every_pixel_libass_actually_burns(
    label: str, style: dict[str, Any], text: str, tmp_path: Path
) -> None:
    """띠를 잘못 재면 그 위에 얹는 계산이 전부 틀린다. 실제 픽셀로 못박는다."""
    from videobox_core_engine.ass_subtitles import caption_band_px

    segments = _caption_segments(style, text)
    burned = _rows_touched(_caption_filter(segments, tmp_path, "cap"), tmp_path, "cap")
    band = caption_band_px(segments, video_width=_WIDTH, video_height=_HEIGHT)

    assert band is not None, f"{label}: 자막이 있는데 띠가 없다고 답했다."
    top, bottom = band
    assert burned, f"{label}: 자막이 한 픽셀도 안 구워졌다. 검사 자체가 헛돈다."
    assert top <= min(burned) and max(burned) <= bottom, (
        f"{label}: 계산한 띠 {top}..{bottom} 가 실제로 구워진 줄"
        f" {min(burned)}..{max(burned)} 를 덮지 못한다."
    )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_the_caption_band_is_not_a_lazy_whole_screen_answer(tmp_path: Path) -> None:
    """`화면 전체가 자막 띠`라고 답하면 위 검사는 통과하지만 아무 데도 못 놓는다."""
    from videobox_core_engine.ass_subtitles import caption_band_px

    segments = _caption_segments({"font_family": "Pretendard", "background_color": "#FF0000FF"})
    band = caption_band_px(segments, video_width=_WIDTH, video_height=_HEIGHT)

    assert band is not None
    top, bottom = band
    assert bottom - top < _HEIGHT // 4, f"자막 한 줄이 화면의 {bottom - top}px 을 먹는다고 답했다."


def test_there_is_no_caption_band_when_nothing_is_captioned() -> None:
    from videobox_core_engine.ass_subtitles import caption_band_px

    assert caption_band_px([], video_width=_WIDTH, video_height=_HEIGHT) is None


def test_a_caption_that_is_not_on_screen_yet_does_not_move_the_card() -> None:
    """겹치지도 않는 시간대의 자막 때문에 카드를 밀어 올리지 않는다."""
    from videobox_core_engine.ass_subtitles import caption_band_px

    segments = [{"caption_text": _CAPTION_TEXT, "caption_style": {}, "start_sec": 10.0, "end_sec": 12.0}]

    assert caption_band_px(
        segments, video_width=_WIDTH, video_height=_HEIGHT, start_sec=1.0, end_sec=2.0
    ) is None


# ---------------------------------------------------------------------------
# 2. 본론 -- 구워서 겹치는지 본다
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
@pytest.mark.parametrize(
    ("label", "overlay"), [("설명 카드", _CARD_OVERLAY), ("표", _TABLE_OVERLAY)]
)
def test_the_card_does_not_overlap_the_caption_it_shares_the_screen_with(
    label: str, overlay: dict[str, Any], tmp_path: Path
) -> None:
    """owner가 완성본에서 본 그 결함. 겹친 가로줄이 하나라도 있으면 가린 것이다."""
    segments = _caption_segments({"font_family": "Pretendard", "background_color": "#000000CC"})
    caption_rows = _rows_touched(_caption_filter(segments, tmp_path, "cap"), tmp_path, "cap")
    overlay_rows = _rows_touched(
        ",".join(_plan_overlay_filters(overlay, segments, tmp_path)), tmp_path, "ovl"
    )

    assert caption_rows and overlay_rows, f"{label}: 한쪽이 아예 안 그려졌다."
    shared = caption_rows & overlay_rows
    assert shared == set(), (
        f"{label}가 자막을 {len(shared)}줄 가린다"
        f" (자막 {min(caption_rows)}..{max(caption_rows)},"
        f" 카드 {min(overlay_rows)}..{max(overlay_rows)})."
    )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_the_card_goes_below_the_captions_when_the_captions_sit_high(tmp_path: Path) -> None:
    """자막을 위로 올려 두면 아래가 비어 있다. 무조건 아래를 비워 두는 고정
    예약은 그때 틀린다 -- 카드는 넓은 쪽으로 가야 한다."""
    segments = _caption_segments(
        {"font_family": "Pretendard", "position_y_percent": 22, "background_color": "#000000CC"}
    )
    caption_rows = _rows_touched(_caption_filter(segments, tmp_path, "cap_high"), tmp_path, "cap_high")
    overlay_rows = _rows_touched(
        ",".join(_plan_overlay_filters(_CARD_OVERLAY, segments, tmp_path)), tmp_path, "ovl_high"
    )

    assert caption_rows & overlay_rows == set(), "자막을 위로 올렸는데도 카드가 겹친다."
    assert min(overlay_rows) > max(caption_rows), (
        "자막이 위쪽에 있으면 카드는 그 아래 넓은 자리에 놓여야 한다."
        f" (자막 {min(caption_rows)}..{max(caption_rows)}, 카드 {min(overlay_rows)}..{max(overlay_rows)})"
    )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_a_card_with_no_captions_still_sits_low_and_inside_the_frame(tmp_path: Path) -> None:
    """자막이 없으면 카드는 원래 자리(아래쪽)를 지킨다. 화면 밖으로 나가지도 않는다."""
    overlay_rows = _rows_touched(
        ",".join(_plan_overlay_filters(_CARD_OVERLAY, [], tmp_path)), tmp_path, "ovl_alone"
    )

    assert overlay_rows, "카드가 한 픽셀도 안 그려졌다."
    assert max(overlay_rows) < _HEIGHT, "카드가 화면 아래로 잘려 나간다."
    assert max(overlay_rows) > _HEIGHT * 0.85, "자막이 없는데도 카드가 위로 올라갔다."


# ---------------------------------------------------------------------------
# 3. 두 렌더 경로 -- 같은 계산을 쓰는가
# ---------------------------------------------------------------------------


def test_both_render_paths_put_the_card_on_exactly_the_same_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 저장소는 `렌더 경로가 둘`이라는 함정에 이미 두 번 걸렸다.

    한쪽만 고치면 미리보기와 완성본이 다른 자리에 그린다. 두 경로가 만든
    drawtext 문자열이 **글자까지 같아야** 한다.
    """
    segments = _caption_segments({"font_family": "Pretendard", "background_color": "#000000CC"})
    plan_filters = _plan_overlay_filters(_CARD_OVERLAY, segments, tmp_path)
    export_filters = _export_path_overlay_filters(_CARD_OVERLAY, segments, tmp_path, monkeypatch)

    assert plan_filters == export_filters != []


def test_only_one_place_in_the_renderer_builds_an_overlay_text_line() -> None:
    """글줄 drawtext를 짓는 자리가 둘로 갈라지는 순간 같은 함정이 다시 열린다.
    ffmpeg 없는 기계에서도 도는 가드다."""
    import inspect

    from videobox_core_engine import ffmpeg_final_renderer as module

    builders = [
        line.strip()
        for line in inspect.getsource(module).splitlines()
        if "boxcolor=black@0.65" in line
    ]

    assert len(builders) == 1, f"글줄 drawtext를 짓는 자리가 {len(builders)}곳이다: {builders}"


def test_the_card_leaves_a_real_gap_above_the_caption_band() -> None:
    """겹치지만 않으면 된다가 아니다. 글자 높이 추정에는 오차가 있어서
    (실측 32~36px) 그보다 좁은 틈은 틈이라고 부를 수 없다."""
    from videobox_core_engine.ass_subtitles import caption_band_px
    from videobox_core_engine.ffmpeg_final_renderer import (
        _OVERLAY_LINE_PITCH_PX,
        _overlay_block_bottom_px,
    )

    segments = _caption_segments({"font_family": "Pretendard", "background_color": "#000000CC"})
    band = caption_band_px(segments, video_width=_WIDTH, video_height=_HEIGHT)
    assert band is not None

    # 돌려주는 값은 글줄 뭉치의 **상자 아래 변**이다 (상자 두께는 이미 들어 있다).
    bottom = _overlay_block_bottom_px(line_count=3, video_height=_HEIGHT, caption_band=band)

    assert bottom <= band[0] - 20
    # 화면 밖으로 밀어내는 식으로 "피하지" 않는다.
    assert bottom - 2 * _OVERLAY_LINE_PITCH_PX > 0


def test_the_wrapped_line_estimate_matches_what_libass_actually_did() -> None:
    """1920px·크기 54에서 실측한 세 문장. 이 숫자가 틀리면 긴 자막에서 띠가 짧아진다."""
    from videobox_core_engine.ass_subtitles import _wrapped_line_count

    assert _wrapped_line_count("짧은 자막", size=54, usable_width=_WIDTH) == 1
    assert _wrapped_line_count(
        "이 자막은 조금 길어서 화면 너비를 거의 다 씁니다 그렇지만", size=54, usable_width=_WIDTH
    ) == 1
    assert _wrapped_line_count(
        "이 자막은 아주 길어서 한 줄에 다 들어가지 못할 만큼 길게 이어지는 문장입니다 정말로 길어요 계속 이어집니다",
        size=54, usable_width=_WIDTH,
    ) == 2
