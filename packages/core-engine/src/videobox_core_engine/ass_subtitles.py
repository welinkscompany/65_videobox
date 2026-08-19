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


# ASS는 BackColour를 "그림자 색"으로만 쓴다. 그림자 두께가 0인 우리 스타일에서는
# 아무 데도 안 닿으므로, 자리를 채우되 완전 투명으로 못박아 둔다. 여기에 `배경 색`을
# 넣어 두었던 것이 "화면에는 칸이 있는데 완성본은 그대로"의 원인이었다.
_UNUSED_SHADOW_COLOUR = "&HFF000000"
# 상자 층의 글자는 그리지 않는다. 글자는 그 위에 얹는 층이 그린다.
_FULLY_TRANSPARENT = "&HFF000000"
_BORDER_STYLE_OUTLINE = 1
_BORDER_STYLE_OPAQUE_BOX = 3


def _background_is_visible(value: CaptionStyle) -> bool:
    return int(value.background_color[7:9], 16) > 0


def _box_padding_px(value: CaptionStyle, size: int) -> int:
    """BorderStyle=3에서 상자 크기를 정하는 것은 `Outline` 칸이다.

    실측: 이 값이 0이면 상자가 **한 픽셀도** 그려지지 않는다. 그래서 `배경 색`만
    골라도 상자가 보이도록 글자 크기에 비례한 최소 여백을 준다. 외곽선이 그보다
    두꺼우면 외곽선 두께를 쓴다 -- 안 그러면 외곽선이 상자 밖으로 삐져나온다.

    여백을 글자 크기의 1/8로 잡은 것은 화면 크기가 달라져도 상자 비율이 같게
    유지되기 때문이다. 고정 px로 두면 세로 영상에서만 상자가 두꺼워진다.
    """
    return max(value.outline_width_px, max(1, round(size / 8)))


def render_editing_session_ass(editing_session: dict[str, Any], *, video_width: int, video_height: int) -> str:
    raw_style = editing_session.get("caption_style")
    style = CaptionStyle.from_dict(raw_style) if isinstance(raw_style, dict) else CaptionStyle()

    def style_line(name: str, value: CaptionStyle, *, as_box: bool = False) -> str:
        size = max(1, round(value.font_size_px * video_height / 1080))
        alignment = {"left": 1, "center": 2, "right": 3}[value.horizontal_align]
        margin_l = round(video_width * value.position_x_percent / 100) if value.horizontal_align == "left" else 0
        margin_r = round(video_width * (100 - value.position_x_percent) / 100) if value.horizontal_align == "right" else 0
        margin_v = round(video_height * (100 - value.position_y_percent) / 100)
        if as_box:
            # 상자를 칠하는 색은 BackColour가 아니라 **OutlineColour**다.
            # 이걸 놓치면 BorderStyle만 바꿔 놓고 "상자가 안 보인다"로 끝난다.
            primary = _FULLY_TRANSPARENT
            border_colour = _ass_color(value.background_color)
            border_style = _BORDER_STYLE_OPAQUE_BOX
            border_width = _box_padding_px(value, size)
        else:
            primary = _ass_color(value.text_color)
            border_colour = _ass_color(value.outline_color)
            border_style = _BORDER_STYLE_OUTLINE
            border_width = value.outline_width_px
        return (
            f"Style: {name},{value.font_family},{size},{primary},{primary},"
            f"{border_colour},{_UNUSED_SHADOW_COLOUR},0,0,0,0,100,100,0,0,"
            f"{border_style},{border_width},0,{alignment},{margin_l},{margin_r},{margin_v},1"
        )

    style_names: dict[CaptionStyle, str] = {style: "Default"}
    box_style_names: dict[CaptionStyle, str] = {}
    style_lines = [style_line("Default", style)]
    dialogue_lines = []

    def box_style_name_for(value: CaptionStyle, text_style_name: str) -> str:
        name = box_style_names.get(value)
        if name is None:
            name = f"{text_style_name}Box"
            box_style_names[value] = name
            style_lines.append(style_line(name, value, as_box=True))
        return name

    for segment in editing_session.get("segments", []):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("caption_text") or "").strip()
        end_sec = float(segment.get("end_sec") or 0)
        start_sec = float(segment.get("start_sec") or 0)
        if text and end_sec > start_sec:
            raw_segment_style = segment.get("caption_style")
            segment_style = CaptionStyle.from_dict(raw_segment_style) if isinstance(raw_segment_style, dict) else style
            style_name = style_names.get(segment_style)
            if style_name is None:
                style_name = f"Segment{len(style_names)}"
                style_names[segment_style] = style_name
                style_lines.append(style_line(style_name, segment_style))
            timing = f"{_ass_time(start_sec)},{_ass_time(end_sec)}"
            escaped_text = _escape_ass_text(text)
            if _background_is_visible(segment_style):
                # 한 자막을 두 번 그린다. 아래층(0)은 글자 없는 상자, 위층(1)은
                # 외곽선을 살린 글자다. ASS는 BorderStyle을 줄 단위로 바꿀 수 없어서
                # 상자와 외곽선을 **함께** 쓰려면 층을 나누는 수밖에 없다.
                box_name = box_style_name_for(segment_style, style_name)
                dialogue_lines.append(f"Dialogue: 0,{timing},{box_name},,0,0,0,,{escaped_text}")
                dialogue_lines.append(f"Dialogue: 1,{timing},{style_name},,0,0,0,,{escaped_text}")
            else:
                dialogue_lines.append(f"Dialogue: 0,{timing},{style_name},,0,0,0,,{escaped_text}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {video_width}", f"PlayResY: {video_height}", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding", *style_lines, "",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text", *dialogue_lines, "",
    ])
