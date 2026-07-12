from __future__ import annotations

from videobox_core_engine.ass_subtitles import render_editing_session_ass


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
