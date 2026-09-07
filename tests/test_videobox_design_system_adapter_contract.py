"""Read-only contract checks for the VideoBox design-system adapter spec."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-08-13-videobox-design-system-adapter.ko.md"
pytestmark = pytest.mark.docs_only


def test_adapter_spec_exists_and_carries_the_inheritance_boundary() -> None:
    text = SPEC.read_text(encoding="utf-8")

    assert "인트라넷 스타일 상속" in text
    assert "VideoBox 오버라이드" in text
    assert "h-8" in text and "전역 강제" in text
    assert "채워진 입력" in text
    assert "ring-1 ring-foreground/5" in text
    assert "[&>*]:min-w-0" in text


def test_adapter_spec_carries_role_heights_and_state_contract() -> None:
    text = SPEC.read_text(encoding="utf-8")

    for height in ("셸 40px", "32–36px", "에디터 컨트롤 40px"):
        assert height in text
    for state in ("빈 상태", "로딩", "오류", "재시도"):
        assert state in text
    for qa_term in ("ui-inspector", "브라우저", "시각 QA", "자동화 계약"):
        assert qa_term in text
