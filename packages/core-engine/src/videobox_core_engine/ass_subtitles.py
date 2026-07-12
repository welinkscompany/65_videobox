from __future__ import annotations

from typing import Any

from videobox_domain_models.caption_style import CaptionStyle


def _ass_color(rgba: str) -> str:
    red, green, blue, alpha = (rgba[index : index + 2] for index in range(1, 9, 2))
    ass_alpha = 255 - int(alpha, 16)
    return f"&H{ass_alpha:02X}{blue}{green}{red}".upper()


def _ass_time(seconds: float) -> str:
    total_centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(total_centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def render_editing_session_ass(editing_session: dict[str, Any], *, video_width: int, video_height: int) -> str:
    style = CaptionStyle.from_dict(editing_session.get("caption_style"))
    size = max(1, round(style.font_size_px * video_height / 1080))
    alignment = {"left": 1, "center": 2, "right": 3}[style.horizontal_align]
    margin_l = round(video_width * style.position_x_percent / 100) if style.horizontal_align == "left" else 0
    margin_r = round(video_width * (100 - style.position_x_percent) / 100) if style.horizontal_align == "right" else 0
    margin_v = round(video_height * (100 - style.position_y_percent) / 100)
    style_line = (
        f"Style: Default,{style.font_family},{size},{_ass_color(style.text_color)},{_ass_color(style.text_color)},"
        f"{_ass_color(style.outline_color)},{_ass_color(style.background_color)},0,0,0,0,100,100,0,0,"
        f"1,{style.outline_width_px},0,{alignment},{margin_l},{margin_r},{margin_v},1"
    )
    dialogue_lines = []
    for segment in editing_session.get("segments", []):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("caption_text") or "").strip()
        end_sec = float(segment.get("end_sec") or 0)
        start_sec = float(segment.get("start_sec") or 0)
        if text and end_sec > start_sec:
            dialogue_lines.append(
                f"Dialogue: 0,{_ass_time(start_sec)},{_ass_time(end_sec)},Default,,0,0,0,,{_escape_ass_text(text)}"
            )
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {video_width}", f"PlayResY: {video_height}", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding", style_line, "",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text", *dialogue_lines, "",
    ])
