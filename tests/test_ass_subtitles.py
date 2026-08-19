from __future__ import annotations

import collections
import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.ass_subtitles import render_editing_session_ass

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _burned_frame_colour_counts(ass_text: str, tmp_path: Path, *, width: int, height: int) -> collections.Counter:
    """자막을 실제로 구워서 프레임의 색을 센다.

    ASS 문자열만 확인하는 검사는 이 저장소를 여러 번 속였다. 상자가 정말
    칠해지는지는 픽셀로만 알 수 있다.
    """
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(ass_text, encoding="utf-8")
    raw_path = tmp_path / "frame.raw"
    escaped = ass_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r=5:d=2",
            "-vf", f"subtitles=filename='{escaped}'",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw_path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    data = raw_path.read_bytes()
    return collections.Counter(tuple(data[index : index + 3]) for index in range(0, len(data), 3))


def test_render_editing_session_ass_uses_default_style_when_session_style_is_null() -> None:
    ass = render_editing_session_ass(
        {"caption_style": None, "segments": [{"caption_text": "기본 자막", "start_sec": 0.0, "end_sec": 1.0}]},
        video_width=320,
        video_height=180,
    )

    assert "기본 자막" in ass


def test_ass_keeps_editing_session_caption_text_timing_and_style() -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {
                "font_family": "Arial",
                "font_size_px": 48,
                "text_color": "#FF0000FF",
                "outline_color": "#000000FF",
                "outline_width_px": 2,
                "position_x_percent": 50,
                "position_y_percent": 88,
                "horizontal_align": "center",
            },
            "segments": [
                {"caption_text": "스타일 보존", "start_sec": 1.25, "end_sec": 3.5},
            ],
        },
        video_width=1280,
        video_height=720,
    )

    assert "Style: Default,Arial,32" in ass
    assert "Style: Default,Arial,32,&H000000FF" in ass
    assert "Dialogue: 0,0:00:01.25,0:00:03.50,Default,,0,0,0,,스타일 보존" in ass


def test_ass_preserves_per_caption_window_style() -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {"text_color": "#FFFFFFFF"},
            "segments": [
                {"caption_text": "left", "start_sec": 0.0, "end_sec": 1.0},
                {
                    "caption_text": "right", "start_sec": 1.0, "end_sec": 2.0,
                    "caption_style": {"text_color": "#FF0000FF"},
                },
            ],
        },
        video_width=320,
        video_height=180,
    )

    assert "Style: Default,Arial,9,&H00FFFFFF" in ass
    assert "Style: Segment1,Arial,9,&H000000FF" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,left" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.00,Segment1,,0,0,0,,right" in ass


# ---------------------------------------------------------------------------
# 자막 배경 상자
#
# `배경 색`은 오랫동안 화면에만 있고 완성본에는 아무 일도 하지 않았다.
# ASS 필드 순서상 그 값은 BackColour로 들어갔는데, BackColour는 BorderStyle=1에서
# 그림자 색으로만 쓰이고 Shadow가 0으로 박혀 있었기 때문이다.
# ---------------------------------------------------------------------------

_TRANSPARENT_BACKGROUND = "#00000000"
_GREEN_BACKGROUND = "#00FF00FF"


def _box_style_names(ass: str) -> list[str]:
    return [
        line.split(",", 1)[0].removeprefix("Style: ")
        for line in ass.splitlines()
        if line.startswith("Style: ") and line.split(",")[15] == "3"
    ]


def _dialogue_lines(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue: ")]


def test_transparent_caption_background_keeps_the_single_plain_caption_layer() -> None:
    """기본값(투명)은 예전 그대로여야 한다. 상자 스타일도, 덧그리는 층도 없다."""
    ass = render_editing_session_ass(
        {
            "caption_style": {"background_color": _TRANSPARENT_BACKGROUND, "outline_width_px": 3},
            "segments": [{"caption_text": "투명 배경", "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=640,
        video_height=360,
    )

    assert _box_style_names(ass) == []
    assert _dialogue_lines(ass) == ["Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,투명 배경"]


def test_opaque_caption_background_adds_a_box_layer_under_the_same_caption_text() -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {"background_color": _GREEN_BACKGROUND, "outline_width_px": 3},
            "segments": [{"caption_text": "상자 배경", "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=640,
        video_height=360,
    )

    assert _box_style_names(ass) == ["DefaultBox"]
    assert _dialogue_lines(ass) == [
        "Dialogue: 0,0:00:00.00,0:00:01.00,DefaultBox,,0,0,0,,상자 배경",
        "Dialogue: 1,0:00:00.00,0:00:01.00,Default,,0,0,0,,상자 배경",
    ]


def test_caption_background_box_is_painted_with_the_background_colour_not_backcolour() -> None:
    """상자를 칠하는 것은 BackColour가 아니라 OutlineColour다. 이 함정을 놓치면 상자가 안 보인다."""
    ass = render_editing_session_ass(
        {
            "caption_style": {"background_color": _GREEN_BACKGROUND},
            "segments": [{"caption_text": "상자 배경", "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=640,
        video_height=360,
    )
    box_line = next(line for line in ass.splitlines() if line.startswith("Style: DefaultBox,"))
    fields = box_line.split(",")

    assert fields[5] == "&H0000FF00"  # OutlineColour = 배경 색
    assert fields[3] == "&HFF000000"  # PrimaryColour = 완전 투명. 글자는 위층이 그린다
    assert int(fields[16]) > 0  # 여백이 0이면 상자가 아예 안 그려진다


def test_per_caption_background_gets_its_own_box_style() -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {"background_color": _TRANSPARENT_BACKGROUND},
            "segments": [
                {"caption_text": "맨몸", "start_sec": 0.0, "end_sec": 1.0},
                {
                    "caption_text": "상자", "start_sec": 1.0, "end_sec": 2.0,
                    "caption_style": {"background_color": _GREEN_BACKGROUND},
                },
            ],
        },
        video_width=640,
        video_height=360,
    )

    assert _box_style_names(ass) == ["Segment1Box"]
    assert _dialogue_lines(ass) == [
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,맨몸",
        "Dialogue: 0,0:00:01.00,0:00:02.00,Segment1Box,,0,0,0,,상자",
        "Dialogue: 1,0:00:01.00,0:00:02.00,Segment1,,0,0,0,,상자",
    ]


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_burned_caption_shows_no_background_pixels_when_the_background_is_transparent(tmp_path: Path) -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {
                "background_color": "#00FF0000",  # 같은 초록이지만 완전 투명
                "font_size_px": 120, "outline_width_px": 3,
            },
            "segments": [{"caption_text": "no box", "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=640,
        video_height=360,
    )

    counts = _burned_frame_colour_counts(ass, tmp_path, width=640, height=360)
    green = sum(count for (red, green_, blue), count in counts.items() if green_ > 120 and red < 80 and blue < 80)

    assert green == 0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_burned_caption_paints_both_the_background_box_and_the_outline(tmp_path: Path) -> None:
    ass = render_editing_session_ass(
        {
            "caption_style": {
                "background_color": _GREEN_BACKGROUND,
                "outline_color": "#FF0000FF",
                "outline_width_px": 3,
                "font_size_px": 120,
            },
            "segments": [{"caption_text": "box and outline", "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=640,
        video_height=360,
    )

    counts = _burned_frame_colour_counts(ass, tmp_path, width=640, height=360)
    green = sum(count for (red, green_, blue), count in counts.items() if green_ > 120 and red < 80 and blue < 80)
    red_outline = sum(count for (red, green_, blue), count in counts.items() if red > 120 and green_ < 80 and blue < 80)

    assert green > 2000, f"배경 상자가 칠해지지 않았다: {counts.most_common(6)}"
    assert red_outline > 200, f"외곽선이 상자에 먹혔다: {counts.most_common(6)}"
