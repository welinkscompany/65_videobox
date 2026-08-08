from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
HANDOFF_ROOT = ROOT / "docs" / "handoffs"
FAST_PATH = ROOT / "docs" / "development-fast-path.ko.md"

_DATED_HANDOFF = re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.md$")
_ENTRY_LINE = re.compile(
    r"^\|\s*\*\*최신 세션 인계\*\*\s*\|\s*`([^`]+)`\s*\|$",
    re.MULTILINE,
)


def _newest_handoff() -> str:
    dated = sorted(
        path.name
        for path in HANDOFF_ROOT.iterdir()
        if path.is_file() and _DATED_HANDOFF.match(path.name)
    )
    assert dated, "날짜가 붙은 인계 문서가 하나도 없다"
    return dated[-1]


def test_entry_map_points_at_the_newest_handoff() -> None:
    """새 세션이 82개 중 어느 것을 읽어야 하는지 확실히 알아야 한다.

    이 표시는 손으로 관리하는 한 줄이라 한 번만 갱신을 잊어도 조용히 낡는다.
    그러면 다음 세션이 옛 상태를 현재로 믿고 그 위에 쌓는다. 그래서 낡는 순간
    테스트가 깨지게 둔다 -- 인계 문서를 새로 쓰면 이 줄도 같이 고쳐야 한다.
    """
    match = _ENTRY_LINE.search(CLAUDE_MD.read_text(encoding="utf-8"))
    assert match is not None, "CLAUDE.md 진입 지도에 최신 세션 인계 줄이 없다"

    pointed = match.group(1)
    assert pointed.startswith("docs/handoffs/"), pointed
    assert (ROOT / pointed).is_file(), f"가리키는 인계 문서가 없다: {pointed}"
    assert Path(pointed).name == _newest_handoff(), (
        "진입 지도가 최신 인계 문서를 가리키지 않는다. "
        f"가리킴={Path(pointed).name} 최신={_newest_handoff()}"
    )


def test_the_rule_says_the_pointer_must_move_with_the_handoff() -> None:
    """규정에 적혀 있지 않으면 다음 세션이 이 줄의 존재를 모른다."""
    fast_path = FAST_PATH.read_text(encoding="utf-8")

    assert "최신 세션 인계" in fast_path
    assert "CLAUDE.md" in fast_path
