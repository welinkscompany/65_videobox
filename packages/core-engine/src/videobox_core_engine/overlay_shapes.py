"""정지 도형과 아이콘("여기를 보세요")의 프리셋 어휘. 한 군데서만 정한다.

같은 목록이 core-engine·API·화면에 흩어져 있었고, 한쪽만 고치면 화면과 렌더 중
한 곳에서만 살아남는다. 이 파일이 그 목록의 유일한 출처다.

아이콘은 **글꼴에 있는 글자 하나**다. 굽는 단계도, 아이콘마다 딸린 그림 파일도
없다. 렌더는 이미 있는 `drawtext` 경로를 그대로 쓴다.

아이콘이 오는 글꼴은 두 갈래다.

- **글줄 글꼴에 이미 있는 기호**(화살표·별·체크 등). 어느 글꼴이 가졌는지가
  기계마다 달라서 후보를 훑는다.
- **아이콘 글꼴**(Material Symbols, Apache-2.0). 전구·돋보기처럼 글줄 글꼴에는
  없는 것들이다. 이쪽은 후보를 훑지 **않는다** -- 아래 `resolve_icon_font` 주석에
  적은 이유로, 훑으면 owner가 고른 것과 다른 그림이 나갈 수 있다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import struct


# drawbox로 그리는 도형. ffmpeg의 drawbox는 사각형만 그린다 -- 화살표가 여기
# 없는 이유이고, 그 구멍을 아래 아이콘이 메운다.
SHAPE_OVERLAY_DRAWN_SHAPES = frozenset({"highlight_box", "underline"})

# 글줄 글꼴이 이미 갖고 있는 기호로 그리는 아이콘.
#
# 근거(짐작이 아니라 잰 것):
#  - owner가 2026-08-20에 **실행 중인 컨테이너**에서 drawtext로 그려 픽셀을 셌다.
#    → ➡ ▶ ✔ ★ ⚠ ● ✕ ◆ ☞ 와 대각선 넷(↖↗↙↘)이 전부 그려졌다.
#    상하좌우(← ↑ ↓)는 같은 유니코드 블록이라 된다고 본 것이며 그건 추론이다.
#  - 이 목록 16개를 640x360 화면에 실제 ffmpeg로 그려 강조색 픽셀을 세어
#    빈 것이 없음을 확인했다(다만 잰 글꼴은 Windows의 Segoe UI Symbol이다).
#  - 이모지 계열(전구·돋보기·물음표·느낌표)은 컨테이너 글꼴에서 **전부 같은
#    픽셀 수**로 나왔다 -- 두부(빠진 글자 상자)라는 뜻이라 이 목록에서 뺐다.
#    그 넷은 아래 아이콘 글꼴 목록에서 되살아났다.
#
# 어느 글꼴에 무엇이 있는지는 기계마다 다르므로 그리기 직전에 다시 확인한다
# (`resolve_icon_font`). 이 목록은 "고를 수 있는 것"이지 "항상 그려지는 것"이 아니다.
SHAPE_OVERLAY_TEXT_FONT_ICON_GLYPHS: dict[str, str] = {
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

# 아이콘 글꼴(Material Symbols Outlined)이 넓혀 준 몫.
#
# 위 목록이 글줄 글꼴의 재고에 갇혀 있었기 때문에 정작 자주 쓰는 전구·돋보기·
# 물음표·느낌표가 빠져 있었다. 2026-08-20에 실측한 근거:
#  - `💡 🔍 ❓ ❗`를 컨테이너 글꼴로 그리면 **넷 다 정확히 같은 픽셀 수**가 나왔다.
#    두부(빠진 글자 상자)라는 뜻이다.
#  - 아래 16개를 아이콘 글꼴로 320x240에 실제로 그려 강조색 픽셀을 세었더니
#    전부 서로 다른 그림이 나왔다(오름세·내림세는 좌우 대칭이라 잉크 양이 같다).
#
# **리거처가 아니라 코드포인트로 적는다.** Material Symbols는 `lightbulb` 같은
# 이름을 리거처로도 받지만 drawtext에는 리거처 합성이 없다 -- 이름을 그대로
# 넘기면 `l`,`i`,`g`,... 가 낱낱이 그려진다.
#
# 글꼴에는 4,271개가 들어 있지만 여기 올리는 것은 14개다. 목록이 길수록 고르는
# 값이 비싸지므로, 이미 있는 표시와 **그림이 겹치는 것**은 넣지 않는다. 실제로
# 그려 보고 뺀 둘: `play_arrow`는 기존 `삼각형`(▶)과 같은 그림이고, `stop`은
# 오버레이 크기에서 `강조 상자`와 구별되지 않는 작은 네모로 보였다.
SHAPE_OVERLAY_ICON_FONT_GLYPHS: dict[str, str] = {
    "icon_lightbulb":     "\ue90f",   # lightbulb
    "icon_search":        "\uef7a",   # search
    "icon_question":      "\ueb8b",   # question_mark
    "icon_exclamation":   "\ue645",   # priority_high
    "icon_lock":          "\ue899",   # lock
    "icon_clock":         "\uefd6",   # schedule
    "icon_calendar":      "\uebcc",   # calendar_month
    "icon_location":      "\uf1db",   # location_on
    "icon_heart":         "\ue87e",   # favorite
    "icon_thumb_up":      "\uf577",   # thumb_up
    "icon_money":         "\ue227",   # attach_money
    "icon_trend_up":      "\ue8e5",   # trending_up
    "icon_trend_down":    "\ue8e3",   # trending_down
    "icon_cart":          "\ue8cc",   # shopping_cart
}

SHAPE_OVERLAY_ICON_GLYPHS: dict[str, str] = {
    **SHAPE_OVERLAY_TEXT_FONT_ICON_GLYPHS,
    **SHAPE_OVERLAY_ICON_FONT_GLYPHS,
}
SHAPE_OVERLAY_TEXT_FONT_ICON_SHAPES = frozenset(SHAPE_OVERLAY_TEXT_FONT_ICON_GLYPHS)
SHAPE_OVERLAY_ICON_FONT_SHAPES = frozenset(SHAPE_OVERLAY_ICON_FONT_GLYPHS)
SHAPE_OVERLAY_ICON_SHAPES = frozenset(SHAPE_OVERLAY_ICON_GLYPHS)
SHAPE_OVERLAY_SHAPES = SHAPE_OVERLAY_DRAWN_SHAPES | SHAPE_OVERLAY_ICON_SHAPES

# 아이콘 글꼴 글자만 모아 둔다. 그릴 때 "이 글자는 아이콘 글꼴 것인가"를
# 도형 이름이 아니라 글자로 판단할 수 있어야 `resolve_icon_font`의 서명이
# 그대로 유지된다(부르는 곳이 셋이다).
_ICON_FONT_GLYPH_SET = frozenset(SHAPE_OVERLAY_ICON_FONT_GLYPHS.values())

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

# 아이콘 글꼴. 저장소에 파일로 함께 두고 이미지에도 같은 파일을 싣는다
# (`docker/workspace.Dockerfile`). 근거는 `assets/fonts/icons/provenance.json`과
# `THIRD_PARTY_NOTICES.md`에 있으며, 자막 글꼴 팩과 같은 방식이다.
BUNDLED_ICON_FONT_DIRECTORY = "assets/fonts/icons"
CONTAINER_ICON_FONT_DIRECTORY = "/usr/share/fonts/truetype/videobox-icons"
ICON_FONT_FILE_NAME = "MaterialSymbolsOutlined-Variable.ttf"

# 찾는 순서: 컨테이너에 설치된 자리 → 저장소 안의 원본. 두 번째가 있어야
# 컨테이너 없이 worktree에서 바로 돌릴 때도 아이콘이 그려진다.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ICON_FONT_FILES: tuple[str, ...] = (
    f"{CONTAINER_ICON_FONT_DIRECTORY}/{ICON_FONT_FILE_NAME}",
    str(_REPOSITORY_ROOT / BUNDLED_ICON_FONT_DIRECTORY / ICON_FONT_FILE_NAME),
)


def bundled_icon_font_file() -> str | None:
    """이 기계에서 실제로 읽을 수 있는 아이콘 글꼴 파일. 없으면 None."""
    for candidate in ICON_FONT_FILES:
        if Path(candidate).is_file():
            return candidate
    return None


def resolve_icon_font(glyph: str, *, preferred: object = None) -> str | None:
    """이 글자를 실제로 그릴 수 있는 글꼴. 없으면 None -- 부르는 쪽이 멈춘다.

    아이콘 글꼴 글자는 **후보를 훑지 않는다.** Material Symbols는 아이콘을
    사용자 영역(PUA)에 놓는데, 그 자리의 뜻은 글꼴마다 제각각이라 다른 글꼴이
    같은 자리에 전혀 다른 글자를 갖고 있을 수 있다. 실측: Windows의 Segoe UI
    Symbol은 `돈`(U+E227)·`저금통`(U+E2EB) 자리를 이미 쓰고 있다. 후보를 훑다가
    그런 글꼴에 먼저 걸리면 owner가 고른 것과 다른 그림이 조용히 완성본에
    실린다 -- 두부보다 알아채기 어렵다.
    """
    candidates = (
        ICON_FONT_FILES if glyph in _ICON_FONT_GLYPH_SET else (preferred, *ICON_FONT_FALLBACKS)
    )
    for candidate in candidates:
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
