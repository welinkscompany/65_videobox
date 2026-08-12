"""Authority checks for the creator workspace scope documents."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _section(text: str, heading: str, next_heading: str) -> str:
    start = text.index(heading)
    end = text.index(next_heading, start + len(heading))
    return text[start:end]


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


def test_implementation_plan_is_mp4_first_with_optional_capcut() -> None:
    text = (ROOT / "docs/implementation-plan.ko.md").read_text(encoding="utf-8")
    sequence = _section(text, "## 6. 권장 개발 순서", "## 7. 기술 선택 초안")
    technology = _section(text, "## 7. 기술 선택 초안", "### 7.1.")
    reuse = _section(text, "## 8. BrollBox 재사용 방침", "## 8.1")

    assert "12. VideoBox 최종 MP4 renderer 구현" in sequence
    assert "15. 선택적 CapCut 호환 경로 보강" in sequence
    assert "creator-complete 경량 편집기" in technology
    assert "export 대상: VideoBox 최종 MP4" in technology
    assert "CapCut 호환은 선택적" in technology
    assert "1. VideoBox 최종 MP4 출력" in reuse
    assert "2. auto cut" in reuse

    for stale_primary_phrase in (
        "12. CapCut export adapter 구현",
        "15. 필요한 경우 CapCut handoff 보강",
        "export 대상: CapCut",
        "1. CapCut export",
    ):
        assert stale_primary_phrase not in text
