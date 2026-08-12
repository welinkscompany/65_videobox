"""Authority checks for the creator workspace scope documents."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative_path",
    ("CLAUDE.md", "docs/implementation-plan.ko.md"),
)
def test_creator_complete_scope_is_authoritative(relative_path: str) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "creator-complete" in text
    assert "경량 편집기" in text
    assert "CapCut" in text and "선택적 호환" in text
    for finished_scope in ("컷", "자막", "B-roll", "음악", "효과음", "가로", "세로", "검토", "MP4"):
        assert finished_scope in text
    for excluded_scope in ("색보정", "마스크", "키프레임", "멀티캠"):
        assert excluded_scope in text
