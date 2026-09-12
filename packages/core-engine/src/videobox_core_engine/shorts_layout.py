"""숏폼을 **숏폼처럼** 앉히는 자리 하나 -- 제목 띠 + 영상 띠 + 아래 검정.

## 왜 이 모양인가

대표님이 참고 숏폼 넷을 주면서 말한 것(2026-09-12):

> "이런거 보면 상단에 제목이 있네."
> "오히려 위 아래를 어차피 잘 안보니까 이렇게 만드는것도 나을거 같어"

그 넷(전부 1080×1920)을 **픽셀로 쟀다**(`scratchpad/measure_reference_short.py`).
눈대중이 아니다:

| | ref1 | ref2 | ref3 | ref4 |
|---|---|---|---|---|
| 제목 띠 | 0~21.4% | 0~27.4% | 0~28.6% | 0~20.8% |
| 제목 줄 수 | 3줄 | 2줄 | 2줄 | 2줄 |
| 영상 띠 | 21.4~78.5% | 27.4~66.6% | 28.7~71.3% | 20.9~93.9% |
| 영상 가로:세로 | 0.98:1 | 1.43:1 | 1.32:1 | -- |
| 아래 검정 | 21.5% | 33.4% | 28.7% | 6.1% |

**여기서 나온 것이 이 파일의 상수 전부다.**

## 이것이 우리 문제를 같이 푸는 이유

영상 띠가 9:16이 아니라 1.3:1이면, 1920×1080 원본을 **폭 그대로** 담아도
(1080×831 띠 안에 1080×608) 그 띠에서 남는 것이 위아래 111픽셀씩뿐이다. 화면
전체를 채우려다 가로 31.6%만 남기는 것(2026-09-12 대표님 실물 신고: "배경 좌우가
짤려서 글자가 양쪽 사이드가 안보여")과 비교가 안 된다 -- **잘라낼 필요 자체가
사라진다.** 대표님 원본에 구워진 자막이 그대로 살아난다.

## 자막은 새 길을 안 만든다 -- 아래 검정이 곧 자막 자리다

자막은 그대로 `ass_subtitles.render_editing_session_ass`가 굽는다. 기본 세로 위치가
88%라, 이 레이아웃에서는 그 글자가 **영상 띠 아래 검정**에 놓인다 -- 참고 숏폼의
"자막을 하위로"와 같은 자리다. 대표님 실제 영상으로 구워서 눈으로 확인했다.

대표님 원본에는 **자막이 이미 그림에 구워져 있다.** 그 자막은 영상 띠 안에 있고
우리 자막은 아래 검정에 있어 **겹치지 않는다**(실물 프레임으로 확인). 다만 같은
말이 두 번 보이므로, 그런 원본에서는 편집기에서 자막 레인의 눈을 끈다
(`track_states`) -- 이미 있는 문이고 새로 만들지 않는다. 여기서 자막을 강제로
끄지 않는 이유는, 구워진 자막이 없는 보통 편집본에서는 이 자리가 정확히 맞기
때문이다.

## 주의: 줄 수만으로 띠 높이가 정해지지는 않는다

참고 넷에서 줄 수와 띠 높이는 **깔끔하게 비례하지 않는다** -- 3줄인 ref1이 21.4%로
가장 작고, 2줄인 ref3이 28.6%로 가장 크다. 글자 높이가 72~121픽셀로 서로 달랐기
때문이다. 그래서 여기서는 줄 수로 **키우되**, 참고 넷이 실제로 쓴 범위
(`_MEASURED_BAND_SHARE_RANGE`)를 아래·위 한계로 둔다. 고정 퍼센트를 박지 않는
이유는 3줄 제목이 2줄과 같은 자리에 들어갈 수 없기 때문이고, 범위를 두는 이유는
줄 수만 믿으면 실측 밖으로 나가기 때문이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil, floor

from videobox_core_engine.ass_subtitles import text_width_px

#: 줄 사이(1920 기준 px).
_TITLE_LINE_GAP_PX_AT_1920 = 16
#: 글자 크기(1920 기준 px). **실측으로 정했다**: 이 크기에서 libass가 실제로 칠한
#: 글자 높이가 약 80px이고(대표님 영상으로 구워 픽셀로 쟀다 -- 크기 76에서 56px),
#: 참고 넷의 글자 높이가 72~121px이었다. 처음에 76으로 잡았더니 56px이 나와 참고
#: 넷보다 작았다 -- **ASS의 `Fontsize`는 글자 높이가 아니라 em 크기다.**
_TITLE_FONT_PX_AT_1920 = 108
#: 줄이 길어 화면 폭을 넘을 때 줄여 나갈 **하한**(1920 기준 px). 이 값이면
#: 30자(유진 스키마의 한 줄 상한)도 한 줄에 들어간다 -- 그래서 libass가 줄을
#: 접는 일이 없고, 줄마다 자리를 우리가 정하는 셈이 어긋나지 않는다.
_TITLE_MIN_FONT_PX_AT_1920 = 32
#: 제목 좌우 여백(1920 기준 px). 글자가 화면 가장자리에 붙지 않게.
_TITLE_SIDE_MARGIN_PX_AT_1920 = 48
#: 제목 띠의 위·아래 여백(1920 기준 px). **참고 넷에서 거꾸로 풀었다**: 2줄 제목의
#: 띠가 21.4%(411px)였고 글자 크기 108 두 줄 + 줄 사이 16이 232px이므로 남는
#: 179px이 위아래 여백(약 90px씩)이다.
_TITLE_BAND_PADDING_PX_AT_1920 = 90

#: 제목은 **세 줄까지**다. 참고 넷은 2~3줄이었고, 넷째 줄을 받으면 띠가 실측 범위
#: (아래)를 넘는다. 넘는 값은 **조용히 자르지 않고 거절한다** -- 자르면 대표님이
#: 적은 말의 끝이 말없이 사라진다.
MAX_TITLE_LINES = 3

#: 참고 넷이 실제로 쓴 제목 띠의 범위(화면 높이 대비). 줄 수 계산이 이 밖으로
#: 나가면 여기로 당긴다.
_MEASURED_BAND_SHARE_RANGE = (0.208, 0.286)

#: 영상 띠의 가로:세로. 참고 넷이 0.98·1.43·1.32였고 그 가운데를 쓴다.
#: **16:9(1.78)보다 반드시 작아야 한다** -- 이 숫자가 1.78에 가까워지는 순간
#: 1920×1080 원본을 담을 자리가 없어져 좌우를 자르게 된다.
REFERENCE_VIDEO_BAND_ASPECT = 1.3


@dataclass(frozen=True, slots=True)
class ShortsTitle:
    """첫 화면에 띄울 제목. **캔버스와 무관한 값만** 들고 있다.

    `spread_reason`과 다르다 -- 그쪽은 "왜 퍼질까"(대표님이 읽는 판단 근거)이고
    이것은 **화면에 그려질 글자**다. 둘을 한 칸에 담으면 300자짜리 설명이 제목
    띠에 들어간다.
    """

    lines: tuple[str, ...]
    #: 초록으로 칠할 낱말 하나. 유진이 못 고르면 `None`이고 전부 흰색이다.
    #: **지어내지 않는다.**
    highlight: str | None = None


@dataclass(frozen=True, slots=True)
class ShortsGeometry:
    """이 캔버스에서 제목 띠와 영상 띠가 실제로 놓이는 자리(px)."""

    title_band_height_px: int
    #: `(x, y, 가로, 세로)`. 렌더러가 원본을 이 네모 안에 담고 나머지는 검게 둔다.
    video_box: tuple[int, int, int, int]
    font_size_px: int
    line_gap_px: int
    #: 첫 줄의 **위 변**이 놓이는 자리(화면 위에서 잰 px).
    first_line_top_px: int
    #: 좌우 여백(px). 제목이 화면 가장자리에 붙지 않게.
    side_margin_px: int


def shorts_geometry(*, width: int, height: int, lines: Sequence[str]) -> ShortsGeometry:
    """제목에서 띠를 계산한다. **이 함수가 유일한 자리다.**

    줄 수가 아니라 **줄 자체**를 받는 이유: 긴 줄은 글자를 줄여야 화면 폭에
    들어간다. 안 줄이면 libass가 줄을 접고, 접힌 줄은 우리가 정한 자리 셈을
    어긋나게 해서 제목이 영상 위로 흘러내린다.

    비율로 셈하는 이유: 미리보기(프록시)는 완성본보다 작은 캔버스로 나가는데,
    픽셀을 박아 두면 같은 편집본이 미리보기와 완성본에서 다른 모양이 된다 --
    이 저장소가 이미 여러 번 걸린 함정이다.
    """
    line_count = len(lines)
    if line_count < 1:
        raise ValueError("shorts_title_needs_a_line")
    if line_count > MAX_TITLE_LINES:
        raise ValueError(f"shorts_title_takes_at_most_{MAX_TITLE_LINES}_lines")
    gap = max(1, round(height * _TITLE_LINE_GAP_PX_AT_1920 / 1920))
    padding = max(1, round(height * _TITLE_BAND_PADDING_PX_AT_1920 / 1920))
    side_margin = max(0, round(height * _TITLE_SIDE_MARGIN_PX_AT_1920 / 1920))
    font = _fitted_font_size_px(lines, height=height, usable_width=width - 2 * side_margin)
    block = line_count * font + (line_count - 1) * gap
    band = block + 2 * padding
    # 실측 범위로 당긴다 -- 위 머리말의 "줄 수만으로 정해지지 않는다" 참고.
    # 올림·내림 방향이 중요하다. 반올림하면 아래 한계가 실측값보다 **0.02%포인트
    # 낮은** 띠를 통과시킨다 -- 범위를 지키려고 둔 한계가 범위를 넘는다.
    lower = ceil(height * _MEASURED_BAND_SHARE_RANGE[0])
    upper = floor(height * _MEASURED_BAND_SHARE_RANGE[1])
    band = max(lower, min(upper, band))
    # 글자 뭉치는 띠의 가운데에 놓는다. 띠를 당겼을 때도 가운데가 유지된다.
    first_line_top = band // 2 - block // 2
    box_height = min(round(width / REFERENCE_VIDEO_BAND_ASPECT), height - band)
    return ShortsGeometry(
        title_band_height_px=band,
        video_box=(0, band, width, box_height),
        font_size_px=font,
        line_gap_px=gap,
        first_line_top_px=first_line_top,
        side_margin_px=side_margin,
    )


def _fitted_font_size_px(lines: Sequence[str], *, height: int, usable_width: int) -> int:
    """제일 긴 줄이 **한 줄에 들어가는** 글자 크기.

    폭 모형은 자막과 같은 함수(`ass_subtitles.text_width_px`)를 쓴다 -- 두 벌로
    적으면 한쪽만 고쳐진다. 그 함수는 실측으로 잡은 어림이고, 애매하면 올려
    잡는 쪽이라 여기서도 안전한 방향(글자를 더 줄이는 쪽)으로 틀린다.
    """
    base = max(1, round(height * _TITLE_FONT_PX_AT_1920 / 1920))
    floor_size = max(1, round(height * _TITLE_MIN_FONT_PX_AT_1920 / 1920))
    if usable_width <= 0:
        return floor_size
    widest = max((text_width_px(line, size=base) for line in lines), default=0.0)
    if widest <= usable_width:
        return base
    return max(floor_size, int(base * usable_width / widest))


def shorts_title_from_override(value: object) -> ShortsTitle | None:
    """변형본의 `overrides.layout`을 제목으로 읽는다. 없으면 `None`.

    `None`이 뜻하는 것은 **과제 B의 동작 그대로**다 -- 화면 전체에 원본을 담고
    제목 띠를 안 만든다. 그래서 "제목 띠 끄기"는 새 경로가 아니라 이 함수가
    `None`을 돌려주는 것 하나로 끝난다.

    `hidden`이 문구를 **지우지 않고** 끄는 이유: 지우면 다시 켤 때 되돌릴 것이
    없다. 목록과 "지금 걸린 값"은 한 쌍이다(owner 지시 2026-09-06).
    """
    if not isinstance(value, Mapping):
        return None
    if bool(value.get("hidden")):
        return None
    raw_lines = value.get("title_lines")
    if not isinstance(raw_lines, (list, tuple)):
        return None
    lines = tuple(str(line).strip() for line in raw_lines if str(line).strip())
    if not lines:
        return None
    if len(lines) > MAX_TITLE_LINES:
        raise ValueError(f"shorts_title_takes_at_most_{MAX_TITLE_LINES}_lines")
    raw_highlight = value.get("highlight")
    highlight = str(raw_highlight).strip() if raw_highlight is not None else ""
    return ShortsTitle(lines=lines, highlight=highlight or None)


__all__ = [
    "MAX_TITLE_LINES",
    "REFERENCE_VIDEO_BAND_ASPECT",
    "ShortsGeometry",
    "ShortsTitle",
    "shorts_geometry",
    "shorts_title_from_override",
]
