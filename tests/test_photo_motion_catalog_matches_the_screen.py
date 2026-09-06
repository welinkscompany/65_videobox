"""화면의 사진 움직임 목록과 엔진의 목록이 한 벌인가.

`test_scene_filter_catalog_matches_the_screen.py`와 같은 이유다 --
**두 벌을 두면 반드시 어긋난다.** 화면에만 있는 이름을 고르면 저장이 422로
거절되고, 엔진에만 있는 이름은 owner가 영영 고를 수 없다. 둘 다 조용히
일어나므로 여기서 잡는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from videobox_core_engine.media_controls import (
    PHOTO_MOTION_LABELS,
    PHOTO_MOTION_STILL,
    PHOTO_MOTIONS,
)


SCREEN_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "apps" / "web" / "src" / "features" / "editor" / "inspector" / "photoMotions.ts"
)


def _screen_choices() -> list[tuple[str, str]]:
    source = SCREEN_CATALOG.read_text(encoding="utf-8")
    block = source.split("PHOTO_MOTION_CHOICES", 1)[1].split("];", 1)[0]
    return re.findall(r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)"\s*\}', block)


def test_the_screen_offers_exactly_what_the_renderer_can_draw() -> None:
    assert [value for value, _ in _screen_choices()] == [*PHOTO_MOTIONS, PHOTO_MOTION_STILL]


def test_the_korean_names_are_the_same_on_both_sides() -> None:
    """같은 것을 두 이름으로 부르면 owner가 두 기능으로 읽는다."""
    assert dict(_screen_choices()) == PHOTO_MOTION_LABELS


def test_the_unset_value_is_not_one_of_the_choices() -> None:
    """**안 고름은 고를 수 있는 값이 아니다.** 화면의 `auto`가 목록에 섞여
    서버로 가면 `photo_motion must be one of ...`로 거절된다 -- 화면에서는
    `알아서 움직이기`로 보이므로 창작자는 왜 안 되는지 알 길이 없다.
    """
    source = SCREEN_CATALOG.read_text(encoding="utf-8")
    unset = re.search(r'PHOTO_MOTION_NONE\s*=\s*"([^"]+)"', source)

    assert unset is not None, "화면에 '안 고름' 값이 없다"
    assert unset.group(1) not in PHOTO_MOTION_LABELS
