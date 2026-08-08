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


# 진입점 문서가 커지면 정말 중요한 규칙이 덜 중요한 것들 사이에 묻힌다.
# 이 선을 넘으면 세부는 `docs/development-fast-path.ko.md` `## 11`로 내리고
# 여기에는 판단에 필요한 것만 남긴다.
#
# 여유를 둔 값이다. 잡으려는 것은 "조금씩 불어나는 표류"이지 정상적인 한 줄 추가가
# 아니다. 2026-08-08 정리 직후 기준은 219줄 / 6,960자였다.
_CLAUDE_MD_MAX_LINES = 260
_CLAUDE_MD_MAX_CHARS = 8_000


def test_entry_point_stays_short_enough_to_actually_carry_weight() -> None:
    text = CLAUDE_MD.read_text(encoding="utf-8")

    assert len(text.splitlines()) <= _CLAUDE_MD_MAX_LINES, (
        f"CLAUDE.md 가 {len(text.splitlines())}줄이다. "
        "세부 운영 규정은 development-fast-path 로 내린다."
    )
    assert len(text) <= _CLAUDE_MD_MAX_CHARS, (
        f"CLAUDE.md 가 {len(text)}자다. "
        "세부 운영 규정은 development-fast-path 로 내린다."
    )


def test_the_hardest_earned_rules_are_not_buried_in_an_environment_section() -> None:
    """"완료의 정의"와 "화면 검증" 은 이 저장소가 가장 비싸게 배운 규칙이다.

    "개발 환경" 같은 제목 아래 있으면 훑는 사람도 훑는 도구도 건너뛴다.
    자기 제목을 가진 최상위 절이어야 한다.
    """
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
    tops = [line for line in lines if line.startswith("## ")]

    assert any("완료" in line for line in tops), tops
    for required in (
        "owner가 화면에서 그 기능을 실제로 쓸 수 있는가",
        "API 단건 확인은 화면 확인을 대체하지 못한다",
    ):
        assert any(required in line for line in lines), required


def test_the_two_data_roots_hazard_is_written_down() -> None:
    """컨테이너와 로컬은 서로 다른 데이터 폴더를 본다.

    2026-08-08 확인: 두 곳 모두에 `b-roll-smoke-test` 가 있었고 크기가
    달랐다(92MB 대 123MB). 어느 쪽으로 띄웠는지 모르면 "어제 만든 프로젝트가
    사라졌다"로 보인다. 이 위험이 문서에 적혀 있지 않으면 다음 사람이 똑같이 겪는다.
    """
    fast_path = FAST_PATH.read_text(encoding="utf-8")

    assert "65_videobox-container-data-v2" in fast_path
    assert "65_videobox-project" in fast_path
    # 어느 쪽을 보고 있는지 확인하는 방법도 함께 적혀 있어야 한다.
    assert "projects_root" in fast_path
