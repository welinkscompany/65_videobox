"""자막에 쓸 수 있는 글꼴 목록 -- **하나뿐인 정본**.

화면의 `글꼴` 칸은 오랫동안 자유 입력이었다. 그래서 owner가 아무 이름이나 칠 수
있었고, 없는 글꼴이면 아무 말 없이 다른 글꼴로 떨어졌다. 실제로 화면 기본값이
`Pretendard`인데 컨테이너에는 그 글꼴이 **없었다** -- 모든 자막이 기본적으로
없는 글꼴을 요청하고 조용히 대체되고 있었다.

그래서 목록을 여기 한 곳에만 둔다. 화면은 이 목록을 받아 쓰고, 목록을 따로
들고 있지 않는다. 두 벌을 두면 반드시 어긋난다.

`family`는 컨테이너의 fontconfig가 실제로 돌려준 이름이다(`fc-list`로 확인).
그 문자열이 그대로 ASS `Fontname`으로 나가므로 임의로 예쁘게 고치면 안 된다 --
`Nanum Pen Script`가 아니라 `Nanum Pen`인 것이 그 예다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 글꼴 파일을 함께 넣어 둔 자리. 저장소 루트 기준이다.
BUNDLED_FONT_DIRECTORY = "assets/fonts/korean"
# 컨테이너 안에서 위 파일들이 놓이는 자리.
CONTAINER_FONT_DIRECTORY = "/usr/share/fonts/truetype/videobox-korean"
# 이미지가 apt로 이미 넣고 있는 글꼴 꾸러미.
IMAGE_FONT_PACKAGE = "fonts-nanum"


@dataclass(frozen=True, slots=True)
class CaptionFont:
    """고를 수 있는 글꼴 하나."""

    family: str
    """fontconfig가 아는 이름. ASS `Fontname`으로 그대로 나간다."""
    label: str
    """화면에 보이는 이름."""
    group: str
    """갈래. 목록을 묶어 보여 주는 데 쓴다."""
    bundled_file: str | None
    """`assets/fonts/korean` 에 함께 넣은 파일. `None`이면 이미지가 이미 갖고 있다."""


BODY = "본문"
SERIF = "명조"
DISPLAY = "제목"
HANDWRITING = "손글씨"


CAPTION_FONTS: tuple[CaptionFont, ...] = (
    CaptionFont("Pretendard", "프리텐다드", BODY, "Pretendard-Regular.otf"),
    CaptionFont("Noto Sans KR", "본고딕", BODY, "NotoSansKR-Variable.ttf"),
    CaptionFont("Gothic A1", "고딕 A1", BODY, "GothicA1-Regular.ttf"),
    CaptionFont("IBM Plex Sans KR", "IBM 플렉스 산스", BODY, "IBMPlexSansKR-Regular.ttf"),
    CaptionFont("NanumGothic", "나눔고딕", BODY, None),
    CaptionFont("NanumSquare", "나눔스퀘어", BODY, None),
    CaptionFont("NanumMyeongjo", "나눔명조", SERIF, None),
    CaptionFont("Song Myung", "송명", SERIF, "SongMyung-Regular.ttf"),
    CaptionFont("Black Han Sans", "검은고딕", DISPLAY, "BlackHanSans-Regular.ttf"),
    CaptionFont("Do Hyeon", "도현", DISPLAY, "DoHyeon-Regular.ttf"),
    CaptionFont("Jua", "주아", DISPLAY, "Jua-Regular.ttf"),
    CaptionFont("Gugi", "구기", DISPLAY, "Gugi-Regular.ttf"),
    CaptionFont("Nanum Pen", "나눔손글씨 펜", HANDWRITING, "NanumPenScript-Regular.ttf"),
    CaptionFont("Nanum Brush Script", "나눔손글씨 붓", HANDWRITING, "NanumBrushScript-Regular.ttf"),
    CaptionFont("Gaegu", "개구쟁이", HANDWRITING, "Gaegu-Regular.ttf"),
)

# 화면 기본값이자 저장 기본값. 예전 기본값 `Arial`과 `Pretendard`는 둘 다
# 컨테이너에 없어서 조용히 대체되고 있었다. 이제 실제로 들어 있는 글꼴을 쓴다.
DEFAULT_CAPTION_FONT_FAMILY = "Pretendard"

CAPTION_FONT_FAMILIES: frozenset[str] = frozenset(font.family for font in CAPTION_FONTS)


def is_installed_caption_font(family: str) -> bool:
    return family in CAPTION_FONT_FAMILIES


def caption_font_catalog() -> list[dict[str, str]]:
    """화면에 넘길 모양. 파일 이름 같은 내부 사정은 빼고 보낸다."""
    return [{"family": font.family, "label": font.label, "group": font.group} for font in CAPTION_FONTS]
