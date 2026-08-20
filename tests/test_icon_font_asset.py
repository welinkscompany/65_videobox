"""아이콘 글꼴을 이미지에 함께 싣는 근거가 서로 어긋나면 잡는다.

글꼴 파일·출처 기록·라이선스 원문·이미지 설치 지시는 서로 떨어져 있어서 한쪽만
고치기 쉽다. 그러면 화면은 아이콘을 내주는데 컨테이너에는 그릴 글꼴이 없고,
렌더가 통째로 막힌다(두부를 그리느니 멈추도록 돼 있다).

자막 글꼴이 `tests/test_caption_fonts.py`에서 받는 검사와 같은 종류다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videobox_core_engine.overlay_shapes import (
    BUNDLED_ICON_FONT_DIRECTORY,
    CONTAINER_ICON_FONT_DIRECTORY,
    ICON_FONT_FILE_NAME,
    SHAPE_OVERLAY_ICON_FONT_SHAPES,
    SHAPE_OVERLAY_ICON_GLYPHS,
    bundled_icon_font_file,
    font_supports_glyph,
)

ROOT = Path(__file__).resolve().parents[1]
FONT_DIRECTORY = ROOT / BUNDLED_ICON_FONT_DIRECTORY
DOCKERFILE = ROOT / "docker/workspace.Dockerfile"


def _provenance() -> dict[str, dict[str, object]]:
    document = json.loads((FONT_DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    return {str(entry["file"]): entry for entry in document["fonts"]}


def test_the_icon_font_file_is_actually_there() -> None:
    assert (FONT_DIRECTORY / ICON_FONT_FILE_NAME).is_file()
    assert bundled_icon_font_file() == str(FONT_DIRECTORY / ICON_FONT_FILE_NAME)


def test_nothing_extra_is_smuggled_into_the_icon_font_directory() -> None:
    """이미지 크기는 이 디렉터리가 결정한다. 목록에 없는 글꼴이 조용히 늘어나면
    재빌드 때마다 이미지가 커지고 아무도 이유를 모른다."""
    on_disk = {
        path.name
        for path in FONT_DIRECTORY.iterdir()
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    }

    assert on_disk == {ICON_FONT_FILE_NAME}


def test_icon_font_bytes_match_the_recorded_provenance() -> None:
    """받아 온 그 파일이 맞는지. 라이선스 근거가 이 해시에 걸려 있다."""
    entry = _provenance()[ICON_FONT_FILE_NAME]
    digest = hashlib.sha256((FONT_DIRECTORY / ICON_FONT_FILE_NAME).read_bytes()).hexdigest()

    assert entry["sha256"] == digest
    assert entry["license"] == "Apache-2.0"


def test_the_icon_font_carries_its_licence_text() -> None:
    """Apache-2.0은 배포본에 라이선스 원문 사본을 같이 두라고 요구한다(§4)."""
    entry = _provenance()[ICON_FONT_FILE_NAME]
    licence_path = FONT_DIRECTORY / str(entry["license_file"])

    assert licence_path.is_file()
    text = " ".join(licence_path.read_text(encoding="utf-8").split())
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    digest = hashlib.sha256(licence_path.read_bytes()).hexdigest()
    assert entry["license_sha256"] == digest


def test_the_image_installs_the_icon_font() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert BUNDLED_ICON_FONT_DIRECTORY in dockerfile
    assert CONTAINER_ICON_FONT_DIRECTORY in dockerfile
    assert "fc-cache" in dockerfile


def test_the_icon_font_is_not_offered_as_a_caption_font() -> None:
    """owner가 자막에 고를 글꼴이 아니다. 여기에 섞이면 자막이 통째로 아이콘이
    되거나 조용히 다른 글꼴로 떨어진다."""
    from videobox_domain_models.caption_fonts import CAPTION_FONTS, is_installed_caption_font

    bundled = {font.bundled_file for font in CAPTION_FONTS if font.bundled_file}
    assert ICON_FONT_FILE_NAME not in bundled
    assert not is_installed_caption_font("Material Symbols Outlined")


def test_every_icon_font_icon_is_drawable_from_the_bundled_file() -> None:
    """목록에 올렸는데 글꼴에 없으면 owner는 고른 뒤 렌더에서 막힌다."""
    font_file = bundled_icon_font_file()
    assert font_file is not None
    for shape in sorted(SHAPE_OVERLAY_ICON_FONT_SHAPES):
        assert font_supports_glyph(font_file, SHAPE_OVERLAY_ICON_GLYPHS[shape]), shape
