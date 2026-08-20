"""글꼴 목록이 실제로 설치되는 것과 어긋나면 잡는다.

목록·글꼴 파일·이미지 설치 지시는 서로 떨어져 있어서 한쪽만 고치기 쉽다.
그러면 화면은 있다고 하는데 완성본은 다른 글꼴로 나온다 -- 이 저장소가
`Pretendard`로 이미 한 번 겪은 일이다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videobox_domain_models.caption_fonts import (
    BUNDLED_FONT_DIRECTORY,
    CAPTION_FONTS,
    CONTAINER_FONT_DIRECTORY,
    DEFAULT_CAPTION_FONT_FAMILY,
    IMAGE_FONT_PACKAGE,
    is_installed_caption_font,
)

ROOT = Path(__file__).resolve().parents[1]
FONT_DIRECTORY = ROOT / BUNDLED_FONT_DIRECTORY
DOCKERFILE = ROOT / "docker/workspace.Dockerfile"


def _provenance() -> dict[str, dict[str, object]]:
    document = json.loads((FONT_DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    return {str(entry["file"]): entry for entry in document["fonts"]}


def test_every_bundled_caption_font_file_is_actually_there() -> None:
    missing = [
        font.bundled_file
        for font in CAPTION_FONTS
        if font.bundled_file and not (FONT_DIRECTORY / font.bundled_file).is_file()
    ]

    assert missing == []


def test_no_bundled_font_file_is_left_out_of_the_list() -> None:
    """넣어 두고 목록에 안 올리면 owner는 그 글꼴을 영영 고를 수 없다."""
    listed = {font.bundled_file for font in CAPTION_FONTS if font.bundled_file}
    on_disk = {
        path.name
        for path in FONT_DIRECTORY.iterdir()
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
    }

    assert on_disk == listed


def test_bundled_font_bytes_match_the_recorded_provenance() -> None:
    """받아 온 그 파일이 맞는지. 라이선스 근거가 이 해시에 걸려 있다."""
    provenance = _provenance()
    mismatched = []
    for font in CAPTION_FONTS:
        if not font.bundled_file:
            continue
        entry = provenance.get(font.bundled_file)
        digest = hashlib.sha256((FONT_DIRECTORY / font.bundled_file).read_bytes()).hexdigest()
        if entry is None or entry["sha256"] != digest:
            mismatched.append(font.bundled_file)

    assert mismatched == []


def test_every_bundled_font_carries_its_licence_text() -> None:
    """OFL은 글꼴을 배포할 때 라이선스 원문을 같이 두라고 요구한다."""
    provenance = _provenance()
    for entry in provenance.values():
        licence_path = FONT_DIRECTORY / str(entry["license_file"])
        assert licence_path.is_file(), entry["license_file"]
        text = " ".join(licence_path.read_text(encoding="utf-8").split())
        assert "SIL Open Font License, Version 1.1" in text
        assert "redistribute" in text


def test_the_image_installs_the_bundled_fonts_and_keeps_the_nanum_package() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert IMAGE_FONT_PACKAGE in dockerfile
    assert BUNDLED_FONT_DIRECTORY in dockerfile
    assert CONTAINER_FONT_DIRECTORY in dockerfile
    assert "fc-cache" in dockerfile


def test_fonts_that_only_the_image_provides_come_from_the_nanum_package() -> None:
    """파일을 함께 넣지 않은 글꼴은 apt 꾸러미가 넣어 주는 것뿐이어야 한다."""
    from_image = [font.family for font in CAPTION_FONTS if font.bundled_file is None]

    assert from_image == ["NanumGothic", "NanumSquare", "NanumMyeongjo"]


def test_the_default_caption_font_is_one_owner_can_actually_get() -> None:
    assert is_installed_caption_font(DEFAULT_CAPTION_FONT_FAMILY)


def test_a_font_nobody_installed_is_not_offered() -> None:
    assert not is_installed_caption_font("Arial")
    assert not is_installed_caption_font("맑은 고딕")
