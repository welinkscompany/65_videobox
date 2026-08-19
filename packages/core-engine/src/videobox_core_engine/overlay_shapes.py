"""정지 도형과 아이콘("여기를 보세요")의 프리셋 어휘. 한 군데서만 정한다.

같은 목록이 core-engine·API·화면에 흩어져 있었고, 한쪽만 고치면 화면과 렌더 중
한 곳에서만 살아남는다. 이 파일이 그 목록의 유일한 출처다.

아이콘은 **글꼴에 이미 있는 글자 하나**다. 자산 파일도, 굽는 단계도, 새 라이선스도
없다. 렌더는 이미 있는 `drawtext` 경로를 그대로 쓴다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import struct


# drawbox로 그리는 도형. ffmpeg의 drawbox는 사각형만 그린다 -- 화살표가 여기
# 없는 이유이고, 그 구멍을 아래 아이콘이 메운다.
SHAPE_OVERLAY_DRAWN_SHAPES = frozenset({"highlight_box", "underline"})

# 아이콘 → 실제로 그릴 글자. 컨테이너 글꼴(DejaVu·나눔)에서 **직접 재서** 그려지는
# 것만 넣었다. 이모지 계열(전구·돋보기·물음표·느낌표)은 같은 글꼴에서 전부 두부
# (빠진 글자 상자)로 나와 목록에서 뺐다.
SHAPE_OVERLAY_ICON_GLYPHS: dict[str, str] = {
    "icon_arrow_up": "↑",
    "icon_arrow_down": "↓",
    "icon_arrow_left": "←",
    "icon_arrow_right": "→",
    "icon_arrow_up_left": "↖",
    "icon_arrow_up_right": "↗",
    "icon_arrow_down_left": "↙",
    "icon_arrow_down_right": "↘",
    "icon_circle": "●",
    "icon_check": "✔",
    "icon_x": "✕",
    "icon_star": "★",
    "icon_warning": "⚠",
    "icon_pointer": "☞",
    "icon_triangle": "▶",
    "icon_diamond": "◆",
}
SHAPE_OVERLAY_ICON_SHAPES = frozenset(SHAPE_OVERLAY_ICON_GLYPHS)
SHAPE_OVERLAY_SHAPES = SHAPE_OVERLAY_DRAWN_SHAPES | SHAPE_OVERLAY_ICON_SHAPES

SHAPE_OVERLAY_VERTICALS = frozenset({"top", "middle", "bottom"})
SHAPE_OVERLAY_HORIZONTALS = frozenset({"left", "center", "right"})
SHAPE_OVERLAY_SIZES = frozenset({"small", "medium", "large"})


# 아이콘 글자를 그릴 글꼴 후보. 글줄 오버레이는 한글 글꼴이 필요하지만 아이콘은
# 기호 하나라 어느 글꼴로 그려도 결과가 같다. 지정된 글꼴에 그 기호가 없을 때
# 두부를 그리는 대신 기호를 가진 글꼴로 넘어간다 -- 예를 들어 나눔고딕에는 ✔·✕·⚠가
# 없을 수 있고, 그때 세 아이콘만 못 쓰게 되는 것은 owner에게 설명하기 어렵다.
ICON_FONT_FALLBACKS: tuple[str, ...] = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)


def resolve_icon_font(glyph: str, *, preferred: object = None) -> str | None:
    """이 글자를 실제로 그릴 수 있는 글꼴. 없으면 None -- 부르는 쪽이 멈춘다."""
    for candidate in (preferred, *ICON_FONT_FALLBACKS):
        if candidate and font_supports_glyph(candidate, glyph):
            return str(candidate)
    return None


def canonical_shape_overlay_shape(value: object) -> str:
    return str(value or "").strip().lower()


def overlay_icon_glyph(shape: object) -> str | None:
    """이 도형 이름이 아이콘이면 그릴 글자, 아니면 None."""
    return SHAPE_OVERLAY_ICON_GLYPHS.get(canonical_shape_overlay_shape(shape))


def font_supports_glyph(font_file: object, glyph: str) -> bool:
    """이 글꼴이 그 글자를 실제로 가지고 있는가.

    없는 글자를 그리면 ffmpeg는 실패하지 않고 **빈 상자**를 그린다. 그렇게 나온
    완성본은 성공으로 끝나서 owner가 알아채지 못한다 -- 그래서 그리기 전에
    글꼴의 문자 목록(`cmap`)을 직접 읽어 확인한다.

    확인하지 못한 경우도 `False`다. '모르겠다'를 '있겠지'로 넘기면 두부가 그대로
    완성본에 실린다.
    """
    if not font_file or not glyph:
        return False
    path = Path(str(font_file))
    try:
        stat = path.stat()
    except OSError:
        return False
    return _glyph_is_in_font(str(path), stat.st_mtime_ns, stat.st_size, ord(glyph[0]))


@lru_cache(maxsize=512)
def _glyph_is_in_font(path: str, mtime_ns: int, size: int, codepoint: int) -> bool:
    try:
        data = Path(path).read_bytes()
        for subtable_offset in _cmap_subtable_offsets(data):
            if _glyph_id(data, subtable_offset, codepoint):
                return True
    except (OSError, ValueError, struct.error, IndexError):
        return False
    return False


def _cmap_subtable_offsets(data: bytes) -> list[int]:
    """글꼴의 문자→글리프 표 위치들. 하나라도 그 글자를 알면 그려진다."""
    if len(data) < 12:
        raise ValueError("not a font file")
    font_offset = 0
    if data[:4] == b"ttcf":
        font_offset = struct.unpack_from(">I", data, 12)[0]
    if data[font_offset : font_offset + 4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
        raise ValueError("unrecognized sfnt header")
    table_count = struct.unpack_from(">H", data, font_offset + 4)[0]
    cmap_offset: int | None = None
    for index in range(table_count):
        record = font_offset + 12 + index * 16
        tag, _checksum, offset, _length = struct.unpack_from(">4sIII", data, record)
        if tag == b"cmap":
            cmap_offset = offset
            break
    if cmap_offset is None:
        raise ValueError("font has no character map")
    subtable_count = struct.unpack_from(">H", data, cmap_offset + 2)[0]
    offsets: list[int] = []
    for index in range(subtable_count):
        _platform, _encoding, offset = struct.unpack_from(">HHI", data, cmap_offset + 4 + index * 8)
        offsets.append(cmap_offset + offset)
    return offsets


def _glyph_id(data: bytes, subtable_offset: int, codepoint: int) -> int:
    """0이면 이 표에는 그 글자가 없다는 뜻이다(0번 글리프가 곧 두부다)."""
    subtable_format = struct.unpack_from(">H", data, subtable_offset)[0]
    if subtable_format == 4:
        if codepoint > 0xFFFF:
            return 0
        segment_count = struct.unpack_from(">H", data, subtable_offset + 6)[0] // 2
        end_codes = subtable_offset + 14
        start_codes = end_codes + segment_count * 2 + 2
        deltas = start_codes + segment_count * 2
        range_offsets = deltas + segment_count * 2
        for index in range(segment_count):
            if codepoint > struct.unpack_from(">H", data, end_codes + index * 2)[0]:
                continue
            start = struct.unpack_from(">H", data, start_codes + index * 2)[0]
            if codepoint < start:
                return 0
            delta = struct.unpack_from(">h", data, deltas + index * 2)[0]
            range_offset = struct.unpack_from(">H", data, range_offsets + index * 2)[0]
            if range_offset == 0:
                return (codepoint + delta) & 0xFFFF
            entry = range_offsets + index * 2 + range_offset + (codepoint - start) * 2
            if entry + 2 > len(data):
                return 0
            glyph = struct.unpack_from(">H", data, entry)[0]
            return 0 if glyph == 0 else (glyph + delta) & 0xFFFF
        return 0
    if subtable_format == 12:
        group_count = struct.unpack_from(">I", data, subtable_offset + 12)[0]
        groups = subtable_offset + 16
        for index in range(group_count):
            start, end, glyph = struct.unpack_from(">III", data, groups + index * 12)
            if start <= codepoint <= end:
                return glyph + (codepoint - start)
        return 0
    if subtable_format == 6:
        first, count = struct.unpack_from(">HH", data, subtable_offset + 6)
        if first <= codepoint < first + count:
            return struct.unpack_from(">H", data, subtable_offset + 10 + (codepoint - first) * 2)[0]
        return 0
    if subtable_format == 0 and codepoint < 256:
        return data[subtable_offset + 6 + codepoint]
    return 0
