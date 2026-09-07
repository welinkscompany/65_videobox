"""어떤 파일이 사진인가 — 네 군데가 손으로 맞춰져 있다.

**두 벌을 두면 반드시 어긋난다**(전환 목록이 같은 이유로 이 짝 시험을 가졌다).
지금 이미 어긋나 있다: 렌더러와 편집기는 `.bmp`를 사진으로 보는데, 자료실과
업로드 칸은 아니다. bmp를 넣으면 **자료실은 영상으로 분류하고 렌더러는 사진으로
그린다** -- 조용히 갈라지는 종류다.

넷을 한 파일로 합치는 것이 옳지만 파이썬과 타입스크립트를 오가는 자리라 지금
당장은 어렵다. 그래서 **어긋나면 여기서 깨지게** 해 둔다. 이 저장소가 전환·색감
목록에서 이미 쓰는 방식이다.
"""

from __future__ import annotations

import re
from pathlib import Path

from videobox_core_engine.ffmpeg_final_renderer import _IMAGE_SUFFIXES

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"


def _suffixes(text: str) -> set[str]:
    return {f".{name.lower()}" for name in re.findall(r"\.(png|jpe?g|webp|bmp|heic|heif|tiff?|avif)\b", text)}


def test_the_editor_and_the_renderer_agree() -> None:
    """편집기는 사진 클립에만 움직임 칸을 띄운다. 렌더러와 다르면 **고를 수 있는데
    안 움직이거나, 움직이는데 고를 칸이 없다.**
    """
    source = (WEB / "features" / "editor" / "inspector" / "inspectorRegistry.ts").read_text(encoding="utf-8")
    matched = re.search(r"PHOTO_SUFFIXES\s*=\s*\[(.+?)\]", source, re.S)

    assert matched, "편집기에서 사진 확장자 목록을 못 찾았다"
    assert _suffixes(matched.group(1)) == set(_IMAGE_SUFFIXES)


def test_the_library_and_the_renderer_agree() -> None:
    """자료실이 사진으로 안 받는 파일을 렌더러가 사진으로 그리면, 그 파일은
    영상으로 색인되고("가로 영상") 화면에서는 사진처럼 움직인다.
    """
    source = (WEB / "features" / "library" / "LibraryPage.tsx").read_text(encoding="utf-8")
    matched = re.search(r'\.\((png\|[^)]+)\)\$', source)

    assert matched, "자료실에서 사진 확장자 목록을 못 찾았다"
    library = {f".{name.lower()}" for name in matched.group(1).split("|")}
    assert library == set(_IMAGE_SUFFIXES), f"자료실 {sorted(library)} 대 렌더러 {sorted(_IMAGE_SUFFIXES)}"


def test_the_upload_box_accepts_every_photo_the_renderer_can_draw() -> None:
    """업로드 칸이 안 받으면 owner는 그 사진을 **넣을 수조차 없다.**"""
    source = (WEB / "features" / "library" / "AssetIngestDropzone.tsx").read_text(encoding="utf-8")
    matched = re.search(r'const accept = "([^"]+)"', source)

    assert matched, "업로드 칸에서 확장자 목록을 못 찾았다"
    accepted = {value.strip().lower() for value in matched.group(1).split(",")}
    missing = sorted(set(_IMAGE_SUFFIXES) - accepted)
    assert not missing, f"렌더러는 그리는데 업로드가 안 받는다: {missing}"
