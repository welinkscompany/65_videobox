from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_DRAWN_SHAPES,
    SHAPE_OVERLAY_ICON_GLYPHS,
    SHAPE_OVERLAY_ICON_SHAPES,
    SHAPE_OVERLAY_SHAPES,
    font_supports_glyph,
    overlay_icon_glyph,
    resolve_icon_font,
)

# 컨테이너에 실제로 있는 글꼴. 여기서 재지 못하면 이 파일의 글꼴 검사는 건너뛴다.
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    r"C:\Windows\Fonts\seguisym.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
)
GLYPH_FONT = next((path for path in _FONT_CANDIDATES if Path(path).is_file()), None)


def test_icon_shapes_extend_the_existing_shape_vocabulary_without_replacing_it() -> None:
    """아이콘은 기존 정지 도형 레일에 얹힌다. 새 병렬 체계를 만들지 않는다."""
    assert SHAPE_OVERLAY_DRAWN_SHAPES == frozenset({"highlight_box", "underline"})
    assert SHAPE_OVERLAY_SHAPES == SHAPE_OVERLAY_DRAWN_SHAPES | SHAPE_OVERLAY_ICON_SHAPES
    assert not SHAPE_OVERLAY_DRAWN_SHAPES & SHAPE_OVERLAY_ICON_SHAPES


def test_every_icon_is_a_single_character_no_asset_file_involved() -> None:
    """자산 파일 0개, 굽는 단계 0개. 아이콘은 글꼴에 이미 있는 글자 하나다."""
    for shape, glyph in SHAPE_OVERLAY_ICON_GLYPHS.items():
        assert shape.startswith("icon_")
        assert len(glyph) == 1, f"{shape} must be one character: {glyph!r}"
        # 이모지 계열은 컨테이너 글꼴에서 두부(빠진 글자 상자)로 나온다.
        assert ord(glyph) < 0x1F000, f"{shape} uses an emoji codepoint: {glyph!r}"


def test_the_selected_icon_set_is_the_measured_one() -> None:
    """1,500개를 다 넣으면 고르기가 더 어렵다. 실제로 그려지는 것만 엄선한다."""
    assert set(SHAPE_OVERLAY_ICON_SHAPES) == {
        "icon_arrow_up",
        "icon_arrow_down",
        "icon_arrow_left",
        "icon_arrow_right",
        "icon_arrow_up_left",
        "icon_arrow_up_right",
        "icon_arrow_down_left",
        "icon_arrow_down_right",
        "icon_circle",
        "icon_check",
        "icon_x",
        "icon_star",
        "icon_warning",
        "icon_pointer",
        "icon_triangle",
        "icon_diamond",
    }


def test_drawn_shapes_have_no_glyph() -> None:
    assert overlay_icon_glyph("highlight_box") is None
    assert overlay_icon_glyph("underline") is None
    assert overlay_icon_glyph("not_a_shape") is None
    assert overlay_icon_glyph("icon_arrow_right") == "\u2192"


@pytest.mark.skipif(GLYPH_FONT is None, reason="no font available to check glyph coverage")
@pytest.mark.parametrize("shape", sorted(SHAPE_OVERLAY_ICON_SHAPES))
def test_some_available_font_carries_every_icon_glyph(shape: str) -> None:
    """고른 글자를 그릴 글꼴이 이 기계에 하나도 없으면 그 아이콘은 못 쓴다.

    한 글꼴이 전부 가질 필요는 없다 -- 한글 글꼴에 없는 기호는 기호 글꼴이 맡는다.
    여기가 빨개지면 목록에서 그 글자를 빼거나 글꼴을 하나 더 넣어야 한다는 뜻이다.
    """
    glyph = SHAPE_OVERLAY_ICON_GLYPHS[shape]
    available = [path for path in _FONT_CANDIDATES if Path(path).is_file()]
    assert any(font_supports_glyph(path, glyph) for path in available), (
        f"{shape}: none of {available} can draw it"
    )


@pytest.mark.skipif(GLYPH_FONT is None, reason="no font available to check glyph coverage")
def test_glyph_check_reports_a_missing_character_instead_of_guessing() -> None:
    # U+0870 is Arabic Extended-B, which none of the fonts above carry.
    assert not font_supports_glyph(GLYPH_FONT, "\u0870")


@pytest.mark.skipif(GLYPH_FONT is None, reason="no font available to check glyph coverage")
def test_icon_font_resolution_skips_a_font_that_cannot_draw_the_glyph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """\uc9c0\uc815\ub41c \uae00\uaf34\uc5d0 \uae30\ud638\uac00 \uc5c6\uc73c\uba74 \ub450\ubd80\ub97c \uadf8\ub9ac\uc9c0 \uc54a\uace0 \uac00\uc9c4 \uae00\uaf34\ub85c \ub118\uc5b4\uac04\ub2e4."""
    import videobox_core_engine.overlay_shapes as overlay_shapes

    monkeypatch.setattr(overlay_shapes, "ICON_FONT_FALLBACKS", (GLYPH_FONT,))
    empty = tmp_path / "not-a-font.ttf"
    empty.write_bytes(b"nope")

    assert resolve_icon_font("\u2192", preferred=str(empty)) == GLYPH_FONT
    assert resolve_icon_font("\u2192", preferred=GLYPH_FONT) == GLYPH_FONT

    monkeypatch.setattr(overlay_shapes, "ICON_FONT_FALLBACKS", ())
    assert resolve_icon_font("\u2192", preferred=str(empty)) is None


def test_glyph_check_fails_closed_when_the_font_cannot_be_read(tmp_path: Path) -> None:
    """읽지 못한 글꼴을 '있겠지'로 넘기면 두부가 그대로 완성본에 실린다."""
    broken = tmp_path / "not-really-a-font.ttf"
    broken.write_bytes(b"this is not a font")

    assert not font_supports_glyph(str(broken), "\u2192")
    assert not font_supports_glyph(str(tmp_path / "absent.ttf"), "\u2192")


def test_both_overlay_validity_gates_accept_an_icon_shape() -> None:
    """부분 재생성이 보존 대상에서 아이콘을 조용히 지우면 안 된다.

    같은 판정이 core-engine과 API 양쪽에 따로 있다. 한쪽만 고치면 화면과
    렌더 중 한 곳에서만 아이콘이 살아남는다.
    """
    from videobox_api.response_normalizers import _is_valid_preflight_visual_overlay
    from videobox_core_engine._pipeline_shared_helpers import _is_valid_runtime_overlay

    icon_overlay = {"overlay_type": "shape_overlay", "shape": "icon_arrow_right"}
    unknown_overlay = {"overlay_type": "shape_overlay", "shape": "icon_rocket"}

    assert _is_valid_runtime_overlay(icon_overlay)
    assert _is_valid_preflight_visual_overlay(icon_overlay)
    assert not _is_valid_runtime_overlay(unknown_overlay)
    assert not _is_valid_preflight_visual_overlay(unknown_overlay)
