"""글꼴 목록이 실제로 설치되는 것과 어긋나면 잡는다.

목록·글꼴 파일·이미지 설치 지시는 서로 떨어져 있어서 한쪽만 고치기 쉽다.
그러면 화면은 있다고 하는데 완성본은 다른 글꼴로 나온다 -- 이 저장소가
`Pretendard`로 이미 한 번 겪은 일이다.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from videobox_domain_models import caption_fonts
from videobox_domain_models.caption_fonts import (
    BUNDLED_FONT_DIRECTORY,
    CAPTION_FONTS,
    CAPTION_FONT_DIRECTORIES,
    CAPTION_FONT_FAMILIES,
    CONTAINER_FONT_DIRECTORY,
    DEFAULT_CAPTION_FONT_FAMILY,
    IMAGE_FONT_DIRECTORY,
    IMAGE_FONT_PACKAGE,
    default_caption_font_family,
    installed_caption_fonts,
    is_installed_caption_font,
)
from videobox_domain_models.caption_style import CaptionStyle
from videobox_storage.user_library_store import _BUILT_IN_CAPTION_PRESETS

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


def test_we_look_in_all_three_places_a_caption_font_can_come_from() -> None:
    """저장소 안의 원본, 컨테이너에 실은 자리, apt 꾸러미가 넣어 준 자리."""
    assert CONTAINER_FONT_DIRECTORY in CAPTION_FONT_DIRECTORIES
    assert IMAGE_FONT_DIRECTORY in CAPTION_FONT_DIRECTORIES
    assert str(ROOT / BUNDLED_FONT_DIRECTORY) in CAPTION_FONT_DIRECTORIES


def test_only_fonts_whose_file_is_on_this_machine_are_offered(tmp_path: Path) -> None:
    """목록에 있다는 것만으로는 그려진다는 뜻이 아니다.

    없는 글꼴을 요청하면 libass는 실패하지 않고 **다른 글꼴로 바꿔** 그린다.
    완성본은 성공으로 끝나서 owner는 알아채지 못한다 -- `Pretendard`가 실제로
    그랬다. 그래서 고를 수 있다고 말하기 전에 파일이 있는지 본다.
    """
    here = tmp_path / "fonts"
    here.mkdir()
    shutil.copy(FONT_DIRECTORY / "Gaegu-Regular.ttf", here / "Gaegu-Regular.ttf")
    shutil.copy(FONT_DIRECTORY / "Jua-Regular.ttf", here / "Jua-Regular.ttf")

    offered = [font.family for font in installed_caption_fonts((str(here),))]

    assert offered == ["Jua", "Gaegu"]
    assert is_installed_caption_font("Gaegu", directories=(str(here),))
    assert not is_installed_caption_font("Pretendard", directories=(str(here),))


def test_the_name_comes_from_inside_the_file_not_from_the_file_name(tmp_path: Path) -> None:
    """파일 이름이 바뀌어도 글꼴 이름은 그대로다.

    apt가 넣어 주는 글꼴은 파일 이름을 우리가 정하지 않는다(`NanumSquareR.ttf`가
    `NanumSquare`다). 파일 이름을 짐작하는 대신 글꼴 안에 적힌 이름을 읽는다.
    """
    here = tmp_path / "fonts"
    here.mkdir()
    shutil.copy(FONT_DIRECTORY / "NanumPenScript-Regular.ttf", here / "whatever-R.ttf")

    assert [font.family for font in installed_caption_fonts((str(here),))] == ["Nanum Pen"]


def test_nothing_is_dropped_when_there_is_nowhere_to_look(tmp_path: Path) -> None:
    """확인할 자리가 아예 없으면 '없다'가 아니라 '모르겠다'다.

    글꼴 자리를 하나도 못 찾은 곳에서 목록을 통째로 비우면 owner는 글꼴을
    하나도 못 고른다 -- 조용히 대체되는 것보다 나쁘다. 그래서 하나도 확인하지
    못했을 때만 목록을 그대로 내준다.

    (Windows 개발기는 여기 해당하지 않는다. 저장소 안의 글꼴 자리가 있어서
    함께 넣어 둔 12개는 확인되고, apt가 넣어 주는 셋만 빠진다.)
    """
    assert installed_caption_fonts((str(tmp_path / "nowhere"),)) == CAPTION_FONTS


def test_the_default_falls_back_to_a_font_that_is_actually_there(tmp_path: Path) -> None:
    """기본값이 없는 글꼴이면 화면이 첫 화면부터 대체된 글꼴을 보여 준다."""
    here = tmp_path / "fonts"
    here.mkdir()
    shutil.copy(FONT_DIRECTORY / "Gaegu-Regular.ttf", here / "Gaegu-Regular.ttf")

    assert default_caption_font_family((str(here),)) == "Gaegu"
    assert default_caption_font_family() == DEFAULT_CAPTION_FONT_FAMILY


# ---------------------------------------------------------------------------
# 기본값이 가리키는 이름이 실제로 목록에 있는가
#
# 2026-08-20에 기본 글꼴 이름이 저장소 안 **세 곳**에 따로 박혀 있었고 셋 다
# 목록 밖 이름이었다 -- 모델은 `Arial`, 화면은 `Pretendard`, 내장 프리셋은
# `Noto Sans KR`. 각 자리는 저마다 초록이었다. 아무도 "이 이름이 실제로 있나"를
# 묻지 않았기 때문이다.
#
# 아래 둘은 정본 자리를 직접 확인하고, 마지막 하나는 **저장소 전체를 훑어서**
# 다음에 어디에 새로 박히든 잡는다. 기본값을 새로 적는 자리가 생기면 그때
# 목록과 대조된다.
# ---------------------------------------------------------------------------

# `font_family` / `fontFamily` 에 글자 그대로 적힌 값을 찾는다.
_FONT_LITERAL = re.compile(r"""["']?(?:font_family|fontFamily)["']?\s*[:=]\s*["']([^"']+)["']""")
_SCANNED_TREES = ("packages", "services", "apps/web/src", "scripts")
_SCANNED_SUFFIXES = {".py", ".ts", ".tsx"}

# 글꼴 이름이 아닌 값. 자리와 값을 함께 적어 두어 다른 자리에서 같은 값이
# 나오면 그대로 걸리게 한다.
_NOT_A_FONT_NAME: dict[tuple[str, str], str] = {
    ("apps/web/src/features/editor/inspector/CaptionPresetPicker.tsx", "fontFamily"): (
        "저장된 모양의 정본 이름을 화면 값 이름으로 옮기는 표다. 값이 글꼴이 아니라 화면 쪽 칸 이름이다."
    ),
}

# 훑기가 아무것도 못 찾는 채로 초록이 되지 않게, 이미 아는 자리는 반드시 나와야 한다.
_KNOWN_DEFAULT_SITES = (
    "apps/web/src/features/editor/inspector/InspectorControls.tsx",
    "packages/storage-abstractions/src/videobox_storage/user_library_store.py",
)


def _is_test_source(path: Path) -> bool:
    return ".test." in path.name or path.name.startswith("test_") or "tests" in path.parts


def _font_literals_in_source() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for tree in _SCANNED_TREES:
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file() or path.suffix not in _SCANNED_SUFFIXES:
                continue
            if "node_modules" in path.parts or _is_test_source(path):
                continue
            relative = path.relative_to(ROOT).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for value in _FONT_LITERAL.findall(line):
                    found.append((relative, number, value))
    return found


def test_the_saved_default_caption_font_is_one_owner_can_actually_get() -> None:
    """모양을 따로 고르지 않은 자막이 전부 이 이름으로 나간다."""
    assert is_installed_caption_font(CaptionStyle().font_family)


def test_the_saved_default_follows_the_machine_instead_of_a_frozen_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CaptionStyle()`을 직접 만드는 자리도 **이 기계에 있는** 글꼴을 받아야 한다.

    2026-08-20에 기계에게 묻는 자를 만들었지만 쓰는 곳이 한 군데뿐이었다 --
    API가 내주는 기본값만 그 자를 썼고, 모델의 기본값은 박힌 이름 그대로였다.
    그래서 두 자리가 서로 다른 답을 할 수 있었다.

    위 시험(`..._is_one_owner_can_actually_get`)은 **이 기계에서만** 재므로 그
    어긋남을 못 잡는다. 여기서는 글꼴이 하나뿐인 자리를 만들어 놓고 물어서,
    기본값이 목록을 따라오는지 자체를 잰다.

    이 자리가 왜 실제 경로인가: 자막 모양을 한 번도 고치지 않은 편집본은
    `caption_style`이 비어 있고, 렌더는 그때 `CaptionStyle.from_dict({})`로
    기본값을 만들어 그 이름을 그대로 ASS `Fontname`에 적는다.
    """
    here = tmp_path / "fonts"
    here.mkdir()
    shutil.copy(FONT_DIRECTORY / "Gaegu-Regular.ttf", here / "Gaegu-Regular.ttf")
    monkeypatch.setattr(caption_fonts, "CAPTION_FONT_DIRECTORIES", (str(here),))

    assert CaptionStyle().font_family == "Gaegu"
    assert CaptionStyle.from_dict({}).font_family == "Gaegu"
    # 고른 이름은 그대로 둔다. 기본값을 정하는 것과 남이 고른 것을 고쳐 주는 것은
    # 다른 일이고, 뒤쪽은 옛 편집본을 못 열게 만든다.
    assert CaptionStyle.from_dict({"font_family": "Arial"}).font_family == "Arial"


def test_every_built_in_caption_preset_names_a_font_that_exists() -> None:
    """내장 프리셋은 owner가 가장 먼저 눌러 보는 것이다. 여기가 없는 글꼴이면 첫인상부터 거짓이다."""
    offenders = [
        (preset["preset_id"], preset["style"]["font_family"])
        for preset in _BUILT_IN_CAPTION_PRESETS
        if not is_installed_caption_font(str(preset["style"]["font_family"]))
    ]

    assert offenders == [], f"목록에 없는 글꼴을 쓰는 내장 프리셋: {offenders}"


def test_no_source_file_hard_codes_a_caption_font_outside_the_catalogue() -> None:
    literals = _font_literals_in_source()
    seen_sites = {relative for relative, _, _ in literals}

    # 훑는 그물이 찢어졌는지부터 본다. 아무것도 안 걸리면 이 시험은 지키는 게 없다.
    for site in _KNOWN_DEFAULT_SITES:
        assert site in seen_sites, f"{site} 의 기본 글꼴이 더는 안 잡힌다. 훑는 규칙이 낡았다."

    # 여기서 묻는 것은 "우리가 내주는 이름인가"이지 "이 기계에 있는가"가 아니다.
    # 뒤쪽 자(`is_installed_caption_font`)를 쓰면 apt가 넣어 주는 셋을 박은 소스가
    # 컨테이너에서는 초록인데 Windows 개발기에서만 빨개진다 -- 그 이름은 잘못이
    # 아니므로 거짓 경보다. 기계에 실제로 있는지는 위쪽 시험들이 따로 잰다.
    offenders = [
        f"{relative}:{number} -> {value!r}"
        for relative, number, value in literals
        if value not in CAPTION_FONT_FAMILIES and (relative, value) not in _NOT_A_FONT_NAME
    ]

    assert offenders == [], (
        "글꼴 목록(`videobox_domain_models.caption_fonts`)에 없는 이름이 소스에 박혀 있다."
        f" 화면은 그 이름을 보여 주지만 완성본은 조용히 다른 글꼴로 나간다: {offenders}"
    )


def test_the_not_a_font_name_list_still_points_at_something_real() -> None:
    """면제 목록이 썩지 않게 한다. 그 줄이 사라졌으면 면제도 지워야 한다."""
    literals = {(relative, value) for relative, _, value in _font_literals_in_source()}
    stale = sorted(entry for entry in _NOT_A_FONT_NAME if entry not in literals)

    assert stale == [], f"이제 없는 자리를 면제하고 있다: {stale}"
