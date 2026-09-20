"""세션이 제품 코드를 고쳤는데 인계 문서를 하나도 안 남기면 알려 주는 장치.

`docs/handoffs/2026-09-20-*.md`류 인계 문서는 CLAUDE.md §7이 요구하는데,
쓰는 걸 잊어도 아무 것도 안 걸린다 -- `handoff-entry-point` 가드는 인계
문서끼리의 내부 정합성(최신 문서를 CLAUDE.md가 가리키는지)만 보고, "애초에
하나라도 썼는지"는 안 본다. 이 파일은 그 빈자리를 채운다.

**막지 않는다.** `guard_router.py`의 `needs_handoff_reminder` 참고 -- 이
저장소는 turn마다 커밋하는 게 기본값이라, 소스를 고칠 때마다 막으면 정상
흐름 자체가 막힌다. Stop 이벤트의 안내문에만 얹는 정보성 알림이다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = REPO_ROOT / "scripts" / "guard_router.py"


def _load_router():
    spec = importlib.util.spec_from_file_location("videobox_guard_router", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


router = _load_router()


def test_source_change_without_a_handoff_doc_needs_a_reminder() -> None:
    paths = ["packages/core-engine/src/videobox_core_engine/media_analysis.py"]

    assert router.needs_handoff_reminder(paths) is True


def test_source_change_with_a_handoff_doc_in_the_same_session_needs_nothing() -> None:
    paths = [
        "packages/core-engine/src/videobox_core_engine/media_analysis.py",
        "docs/handoffs/2026-09-20-full-feature-qa-sweep.ko.md",
    ]

    assert router.needs_handoff_reminder(paths) is False


def test_a_decisions_record_counts_as_product_code_for_this_purpose() -> None:
    """디자인 승인 기록도 인계 없이 조용히 지나가면 같은 문제다."""

    assert router.needs_handoff_reminder(["docs/decisions/2026-09-20-example.ko.md"]) is True


def test_docs_only_changes_never_need_a_reminder() -> None:
    """인계 문서 자체를 정리하는 turn까지 스스로에게 알림을 내지 않는다."""

    paths = ["docs/handoffs/2026-09-20-full-feature-qa-sweep.ko.md", "CLAUDE.md"]

    assert router.needs_handoff_reminder(paths) is False


def test_no_changes_at_all_needs_nothing() -> None:
    assert router.needs_handoff_reminder([]) is False


def test_the_source_and_doc_patterns_still_match_real_files_in_the_repo() -> None:
    """패턴이 옮겨 간 디렉터리를 가리키면 이 알림은 영원히 조용하다."""

    tracked = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and not {"node_modules", ".git", "__pycache__", "dist", ".venv"}.intersection(
            path.relative_to(REPO_ROOT).parts
        )
    ]

    for pattern in (*router.HANDOFF_SOURCE_PATTERNS, router.HANDOFF_DOC_PATTERN):
        assert any(router.matches(pattern, path) for path in tracked), (
            f"{pattern}에 걸리는 실제 파일이 없습니다 -- 패턴이 낡았습니다"
        )


def test_this_reminder_never_sets_a_blocking_decision() -> None:
    """알림 문구 자체에 이 세션이 절대 걸 수 없는 값(`decision`)이 안 섞여 있는지.

    막는 자리는 오직 `failures`(가드 FAIL)뿐이어야 한다 -- 소스코드 안에서
    `needs_handoff_reminder`가 붙는 자리를 확인해 "block"과 같은 줄에 있지
    않은지를 잰다.
    """

    source = ROUTER_PATH.read_text(encoding="utf-8")
    reminder_line = next(
        line for line in source.splitlines() if "needs_handoff_reminder(paths)" in line and "def " not in line
    )
    reminder_index = source.splitlines().index(reminder_line)
    # 알림이 붙는 바로 다음 블록(메시지 문자열 조립)에는 "decision"이 없어야
    # 한다 -- 있다면 정보성 알림이 아니라 실수로 막는 코드가 됐다는 뜻이다.
    following_block = "\n".join(source.splitlines()[reminder_index:reminder_index + 6])
    assert '"decision"' not in following_block
