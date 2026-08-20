from __future__ import annotations

import logging
import unicodedata
from collections.abc import Iterable
from math import ceil
from typing import Any

from videobox_domain_models.caption_fonts import (
    CAPTION_FONT_DIRECTORIES,
    is_installed_caption_font,
)
from videobox_domain_models.caption_style import CaptionStyle


_logger = logging.getLogger(__name__)


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
# 가로 정렬 → ASS Alignment. 1·2·3은 화면 **아래**에 붙는 줄이고, 그때 MarginV는
# 아래에서 잰 거리다. `caption_band_px`가 이 표를 같이 읽는다 -- 위쪽 정렬을
# 나중에 더하면 띠 계산이 저절로 따라온다.
_ALIGNMENT_BY_HORIZONTAL = {"left": 1, "center": 2, "right": 3}
# libass가 실제로 칠한 줄은 계산값보다 1px 위까지 나갔다(실측: 계산 889, 실측 888).
# 반올림 차이라 띠에 그만큼 여유를 둔다.
_BAND_ROUNDING_SLACK_PX = 1


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


def _caption_font_size_px(value: CaptionStyle, video_height: int) -> int:
    """ASS `Fontsize`. 화면 높이에 비례하므로 세로 영상에서도 비율이 같다."""
    return max(1, round(value.font_size_px * video_height / 1080))


def _wrapped_line_count(text: str, *, size: int, usable_width: int) -> int:
    """libass가 이 문장을 몇 줄로 접을지 어림한다.

    **왜 어림인가:** 실제 줄바꿈 폭은 글꼴 metric을 읽어야 정확한데, 자막 글꼴은
    owner가 고르고 컨테이너에 설치된 것을 libass가 찾아 쓴다. 렌더 그래프를 짓는
    시점에 그 파일을 열어 재는 것은 hot path에 디스크 I/O를 얹는 일이라 하지 않는다.

    대신 글자 종류별 폭을 재서 잡았다(1920px·크기 54 실측): 한글·한자·가나는
    글자 크기와 거의 같은 폭을 먹고, 라틴 문자는 절반쯤, 공백은 그보다 훨씬 좁다.
    33자 문장은 한 줄, 61자 문장은 두 줄로 접혔고 이 가중치가 둘 다 맞혔다.

    틀리는 방향도 적어 둔다: 폭을 낮게 잡으면 띠가 실제보다 짧아지고, 그 위에
    놓는 카드가 자막 윗줄을 물 수 있다. 그래서 애매하면 올려 잡는다.
    """
    if usable_width <= 0:
        return 1
    width = 0.0
    for character in text:
        if character.isspace():
            width += size * 0.3
        elif unicodedata.east_asian_width(character) in {"W", "F"}:
            width += size
        else:
            width += size * 0.55
    return max(1, ceil(width / usable_width))


def caption_band_px(
    captions: Iterable[Any],
    *,
    video_width: int,
    video_height: int,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> tuple[int, int] | None:
    """이 시간대의 자막이 실제로 먹는 세로 띠 `(위, 아래)`. 자막이 없으면 None.

    화면에 무엇을 얹든 **자막을 피하려면 자막이 어디 있는지부터 알아야 한다.**
    그 답을 렌더러가 따로 계산하지 않고 여기서 낸다 -- 자막 자리를 정하는 식
    (`style_line`의 MarginV·Fontsize·상자 여백)이 바로 위에 있고, 두 벌로 나뉘면
    반드시 어긋난다.

    받는 것은 `render_editing_session_ass`가 받는 `segments`와 같은 모양이다:
    `caption_text`, `caption_style`, `start_sec`, `end_sec`. 같은 입력으로 ASS를
    굽고 같은 입력으로 띠를 재므로 둘이 다른 자막을 볼 수 없다.

    `start_sec`/`end_sec`을 주면 그 시간과 겹치는 자막만 센다. 20초에 나오는
    자막 때문에 7초에 나오는 카드를 밀어 올리지 않기 위해서다.

    한계: libass의 자동 줄바꿈은 어림으로 센다(`_wrapped_line_count`).
    """
    usable_width = max(1, int(video_width))
    top: int | None = None
    bottom: int | None = None
    for segment in captions:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("caption_text") or "").strip()
        if not text:
            continue
        cue_start, cue_end = float(segment.get("start_sec") or 0.0), float(segment.get("end_sec") or 0.0)
        if cue_end <= cue_start:
            continue
        if start_sec is not None and end_sec is not None and (cue_end <= start_sec or cue_start >= end_sec):
            continue
        raw_style = segment.get("caption_style")
        style = CaptionStyle.from_dict(raw_style) if isinstance(raw_style, dict) else CaptionStyle()
        size = _caption_font_size_px(style, video_height)
        padding = _box_padding_px(style, size)
        margin_l = round(video_width * style.position_x_percent / 100) if style.horizontal_align == "left" else 0
        margin_r = round(video_width * (100 - style.position_x_percent) / 100) if style.horizontal_align == "right" else 0
        lines = sum(
            _wrapped_line_count(part, size=size, usable_width=usable_width - margin_l - margin_r)
            for part in text.split("\n")
        )
        block = lines * size + 2 * padding
        margin_v = round(video_height * (100 - style.position_y_percent) / 100)
        alignment = _ALIGNMENT_BY_HORIZONTAL[style.horizontal_align]
        if alignment <= 3:
            cue_bottom = video_height - margin_v + padding
            cue_top = cue_bottom - block
        elif alignment <= 6:
            cue_top = round((video_height - block) / 2)
            cue_bottom = cue_top + block
        else:
            cue_top, cue_bottom = margin_v - padding, margin_v - padding + block
        top = cue_top if top is None else min(top, cue_top)
        bottom = cue_bottom if bottom is None else max(bottom, cue_bottom)
    if top is None or bottom is None:
        return None
    return max(0, top - _BAND_ROUNDING_SLACK_PX), min(video_height, bottom + _BAND_ROUNDING_SLACK_PX)


def _warn_about_fonts_this_machine_does_not_have(styles: Iterable[CaptionStyle]) -> None:
    """이 자막이 요청하는 글꼴 중 여기서 못 찾은 것을 적어 둔다.

    libass는 없는 글꼴을 요청받아도 **실패하지 않는다.** 조용히 다른 글꼴로
    바꿔 그리고 렌더는 성공으로 끝난다. 그래서 "완성본 글꼴이 왜 이래?"에 답할
    근거가 어디에도 남지 않았다 -- ASS 파일에는 owner가 고른 이름이 그대로
    적혀 있기 때문이다.

    **멈추지 않고, 이름을 바꾸지도 않는다.**

    - 멈추지 않는 이유: 아이콘은 없으면 두부라서 완성본이 못 쓰게 되지만
      (`ffmpeg_final_renderer._icon_overlay_filter`가 그래서 멈춘다), 자막은
      글꼴이 바뀌어도 글은 읽힌다. 옛 편집본이 들고 있는 이름 때문에 렌더가
      막히면 손해가 훨씬 크다.
    - 이름을 바꾸지 않는 이유: 우리가 보는 자리는 세 곳뿐이다. 글꼴은 그 밖에도
      설치될 수 있고, 그때 libass는 멀쩡히 그린다. 넘겨짚어 바꾸면 잘 나오던
      글꼴을 우리가 망가뜨린다. 못 찾은 것과 없는 것은 다르다.

    한계도 분명히 해 둔다: 이건 **로그**다. owner 화면에 닿지 않는다. owner에게
    말하는 몫은 글꼴 고르기 화면이 이미 맡고 있다(`CaptionFontPicker`가 지금
    쓰는 글꼴이 목록에 없으면 한 줄로 알린다). 여기 남는 것은 그 화면을 지나쳐
    구웠을 때 나중에 되짚을 근거다.
    """
    missing = sorted(
        {style.font_family for style in styles if not is_installed_caption_font(style.font_family)}
    )
    if not missing:
        return
    _logger.warning(
        "Caption fonts not found on this machine: %s. libass will silently substitute another "
        "font, so the finished video will not use them. Looked in: %s.",
        ", ".join(missing),
        ", ".join(CAPTION_FONT_DIRECTORIES),
    )


def render_editing_session_ass(editing_session: dict[str, Any], *, video_width: int, video_height: int) -> str:
    raw_style = editing_session.get("caption_style")
    style = CaptionStyle.from_dict(raw_style) if isinstance(raw_style, dict) else CaptionStyle()

    def style_line(name: str, value: CaptionStyle, *, as_box: bool = False) -> str:
        size = _caption_font_size_px(value, video_height)
        alignment = _ALIGNMENT_BY_HORIZONTAL[value.horizontal_align]
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
    _warn_about_fonts_this_machine_does_not_have(style_names)
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {video_width}", f"PlayResY: {video_height}", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding", *style_lines, "",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text", *dialogue_lines, "",
    ])
