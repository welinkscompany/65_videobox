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

**목록에 있다는 것과 이 기계에 있다는 것은 다르다.** 목록에만 기대면 같은 문이
다시 열린다 -- 목록에 올려 둔 글꼴을 이미지에서 빼거나 이름을 잘못 적으면,
화면은 고를 수 있다고 하고 완성본은 조용히 다른 글꼴로 나온다. 그래서 고를 수
있다고 말하기 전에 **글꼴 파일 안에 적힌 이름을 직접 읽는다**. 아이콘 글꼴이
그리기 전에 글자를 확인하는 것(`overlay_shapes.font_supports_glyph`)과 같은
방식이고, 이제 자막 글꼴만 정적 목록을 믿는 비대칭이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO
import struct

# 글꼴 파일을 함께 넣어 둔 자리. 저장소 루트 기준이다.
BUNDLED_FONT_DIRECTORY = "assets/fonts/korean"
# 컨테이너 안에서 위 파일들이 놓이는 자리.
CONTAINER_FONT_DIRECTORY = "/usr/share/fonts/truetype/videobox-korean"
# 이미지가 apt로 이미 넣고 있는 글꼴 꾸러미와, 그 꾸러미가 파일을 놓는 자리.
IMAGE_FONT_PACKAGE = "fonts-nanum"
IMAGE_FONT_DIRECTORY = "/usr/share/fonts/truetype/nanum"


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

# 저장소 루트. 컨테이너 없이 worktree에서 바로 돌릴 때 여기서 글꼴을 찾는다.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

# 자막 글꼴이 올 수 있는 자리 전부. 아이콘 글꼴이 두 자리를 차례로 보는 것
# (`overlay_shapes.ICON_FONT_FILES`)과 같은 방식이고, apt 꾸러미 자리가 하나 더 있다.
CAPTION_FONT_DIRECTORIES: tuple[str, ...] = (
    CONTAINER_FONT_DIRECTORY,
    IMAGE_FONT_DIRECTORY,
    str(_REPOSITORY_ROOT / BUNDLED_FONT_DIRECTORY),
)

# 우리가 내주는 이름 전부. **이 기계에 있다는 뜻이 아니다** -- 그것은
# `is_installed_caption_font()`가 답한다. 자를 둘로 나눠 둔 이유는, 소스에 박힌
# 이름이 오타인지 묻는 것과 이 기계가 그릴 수 있는지 묻는 것이 다른 질문이고,
# 뒤쪽 답은 기계마다 다르기 때문이다.
CAPTION_FONT_FAMILIES: frozenset[str] = frozenset(font.family for font in CAPTION_FONTS)

_FONT_FILE_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".otc"})
# 글꼴 안의 이름표 중 fontconfig가 갈래 이름으로 쓰는 둘. 16번이 있으면 그것이
# 갈래 이름이고(`Noto Sans KR`), 1번은 굵기까지 붙은 이름일 수 있다
# (`Noto Sans KR Thin`). 둘 다 모아 두면 어느 쪽으로 적혀 있어도 찾는다.
_FAMILY_NAME_IDS = frozenset({1, 16})


def installed_caption_fonts(directories: tuple[str, ...] | None = None) -> tuple[CaptionFont, ...]:
    """이 기계에서 **실제로 그려질** 글꼴만."""
    return _installed_caption_fonts(directories if directories is not None else CAPTION_FONT_DIRECTORIES)


def is_installed_caption_font(family: str, *, directories: tuple[str, ...] | None = None) -> bool:
    return any(font.family == family for font in installed_caption_fonts(directories))


def caption_font_catalog(directories: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    """화면에 넘길 모양. 파일 이름 같은 내부 사정은 빼고 보낸다."""
    return [
        {"family": font.family, "label": font.label, "group": font.group}
        for font in installed_caption_fonts(directories)
    ]


def default_caption_font_family(directories: tuple[str, ...] | None = None) -> str:
    """처음 잡아 줄 글꼴. 기본값이 이 기계에 없으면 있는 것 중 첫째를 준다.

    없는 기본값을 그대로 내주면 owner는 아무것도 고르지 않은 첫 화면부터
    조용히 대체된 글꼴로 만들게 된다.
    """
    fonts = installed_caption_fonts(directories)
    if any(font.family == DEFAULT_CAPTION_FONT_FAMILY for font in fonts):
        return DEFAULT_CAPTION_FONT_FAMILY
    return fonts[0].family


@lru_cache(maxsize=8)
def _installed_caption_fonts(directories: tuple[str, ...]) -> tuple[CaptionFont, ...]:
    """한 번만 재고 기억해 둔다. 글꼴은 도는 중에 늘거나 줄지 않는다."""
    families = _families_on_disk(directories)
    present = tuple(font for font in CAPTION_FONTS if font.family in families)
    # 하나도 확인하지 못했으면 '없다'가 아니라 '확인할 자리가 없었다'는 뜻이다.
    # 그때까지 목록을 비우면 owner는 글꼴을 하나도 못 고른다 -- 조용히 대체되는
    # 것보다 나쁘다. 그래서 이때만 목록을 그대로 내준다.
    return present or CAPTION_FONTS


def _families_on_disk(directories: tuple[str, ...]) -> frozenset[str]:
    families: set[str] = set()
    for directory in directories:
        try:
            entries = sorted(Path(directory).iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix.lower() in _FONT_FILE_SUFFIXES:
                families.update(_families_in_font_file(path))
    return frozenset(families)


def _families_in_font_file(path: Path) -> frozenset[str]:
    """글꼴 파일이 스스로 밝히는 이름들. 읽지 못하면 빈 값이다.

    파일 이름으로 짐작하지 않는다 -- apt가 넣어 주는 `NanumSquareR.ttf`의 이름은
    `NanumSquare`다. 파일을 통째로 읽지도 않는다. 이름표(`name`)만 찾아서 읽는다.
    """
    try:
        with path.open("rb") as handle:
            offset = _name_table_offset(handle)
            handle.seek(offset)
            count, storage = struct.unpack_from(">HH", handle.read(6), 2)
            records = handle.read(count * 12)
            names: set[str] = set()
            for index in range(count):
                platform, _encoding, _language, name_id, length, string_offset = struct.unpack_from(
                    ">HHHHHH", records, index * 12
                )
                # 플랫폼 0·3의 이름표만 읽는다. 둘 다 UTF-16BE이고, 잰 글꼴
                # 24개에서 이 둘만으로 `fc-list`와 같은 이름이 전부 나왔다.
                if name_id not in _FAMILY_NAME_IDS or platform not in (0, 3):
                    continue
                handle.seek(offset + storage + string_offset)
                name = handle.read(length).decode("utf-16-be", "ignore").strip()
                if name:
                    names.add(name)
            return frozenset(names)
    except (OSError, ValueError, struct.error, IndexError):
        return frozenset()


def _name_table_offset(handle: BinaryIO) -> int:
    """글꼴 파일 안에서 이름표가 시작하는 자리."""
    handle.seek(0)
    header = handle.read(16)
    base = 0
    if header[:4] == b"ttcf":
        base = struct.unpack_from(">I", header, 12)[0]
        handle.seek(base)
        header = handle.read(16)
    if header[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
        raise ValueError("unrecognized sfnt header")
    table_count = struct.unpack_from(">H", header, 4)[0]
    handle.seek(base + 12)
    records = handle.read(table_count * 16)
    for index in range(table_count):
        tag, _checksum, offset, _length = struct.unpack_from(">4sIII", records, index * 16)
        if tag == b"name":
            return offset
    raise ValueError("font has no name table")
