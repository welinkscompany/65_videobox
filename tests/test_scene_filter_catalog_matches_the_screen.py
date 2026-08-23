"""화면의 색감 목록과 렌더러의 색감 목록이 한 벌인가.

`test_scene_transition_catalog_matches_the_screen.py`와 같은 이유다 --
**두 벌을 두면 반드시 어긋난다.** 화면에만 있는 이름을 고르면 저장이 422로
거절되고, 렌더러에만 있는 이름은 owner가 영영 고를 수 없다. 둘 다 조용히
일어나므로 여기서 잡는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from videobox_core_engine.filters import FILTER_CATALOG


SCREEN_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "apps" / "web" / "src" / "features" / "editor" / "inspector" / "sceneFilters.ts"
)


def _screen_choices() -> list[tuple[str, str]]:
    source = SCREEN_CATALOG.read_text(encoding="utf-8")
    block = source.split("SCENE_FILTER_CHOICES", 1)[1].split("];", 1)[0]
    return re.findall(r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)"\s*\}', block)


def test_the_screen_offers_exactly_what_the_renderer_can_draw() -> None:
    assert [value for value, _ in _screen_choices()] == list(FILTER_CATALOG)


def test_the_korean_names_are_the_same_on_both_sides() -> None:
    """같은 것을 두 이름으로 부르면 owner가 두 기능으로 읽는다."""
    assert {value: label for value, label in _screen_choices()} == {
        value: entry["label"] for value, entry in FILTER_CATALOG.items()
    }
