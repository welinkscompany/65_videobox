"""가드 매핑 표가 낡지 않게 잡아 두는 테스트.

`scripts/guard_router.py`의 표는 "이 경로를 건드리면 이 테스트가 지킨다"는 약속이다.
약속이 조용히 낡는 두 가지 길이 있다.

1.  표가 가리키는 테스트 파일이 이름이 바뀌거나 사라진다 → 라우터가 아무것도 안 돌린다.
2.  지켜야 할 파일이 새로 생겼는데 표에 안 들어간다 → 그 파일은 31분짜리 전체
    pytest 전까지 아무도 안 본다. 이 라우터를 만든 이유가 바로 그것이다.

둘 다 여기서 잡는다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = REPO_ROOT / "scripts" / "guard_router.py"
SOURCE_MAP_PATH = REPO_ROOT / "docs" / "oss" / "editor-ui-source-map.json"
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"


def _load_router():
    spec = importlib.util.spec_from_file_location("videobox_guard_router", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass가 자기 모듈을 sys.modules에서 되찾으므로 exec 전에 등록해 둔다.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


router = _load_router()


def test_every_test_the_table_names_actually_exists() -> None:
    """표가 없는 파일을 가리키면 라우터는 조용히 아무것도 안 지킨다."""

    missing = [
        f"{guard.name} -> {test}"
        for guard in router.GUARDS
        for test in guard.tests
        if not (REPO_ROOT / test).exists()
    ]

    assert missing == []


def test_every_pattern_still_matches_something_in_the_repo() -> None:
    """지키던 파일이 옮겨 갔으면 패턴이 허공을 가리킨다. 그것도 낡은 표다."""

    tracked = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and not {"node_modules", ".git", "__pycache__", "dist", ".venv"}.intersection(
            path.relative_to(REPO_ROOT).parts
        )
    ]

    orphans = [
        f"{guard.name} -> {pattern}"
        for guard in router.GUARDS
        for pattern in guard.patterns
        if not any(router.matches(pattern, path) for path in tracked)
    ]

    assert orphans == []


def test_every_provenance_pinned_file_routes_to_the_provenance_guard() -> None:
    """반입 파일 목록이 늘어나면 표도 같이 늘어야 한다.

    2026-08-20에 놓친 것이 정확히 이 목록의 파일이었다. 새 파일이 핀에 추가됐는데
    표가 안 따라오면, 그 파일은 다시 31분 뒤에나 발각된다.
    """

    source_map = json.loads(SOURCE_MAP_PATH.read_text(encoding="utf-8"))
    pinned: set[str] = set()
    for key in ("materialized_files", "generated_items"):
        for entry in source_map[key]:
            for field in ("path", "test_path"):
                if entry.get(field):
                    pinned.add(entry[field])
    for entry in source_map["reference_only_decisions"]:
        pinned.update(entry.get("local_paths", ()))
        pinned.update(entry.get("materialized_paths", ()))

    guard = next(g for g in router.GUARDS if g.name == "editor-ui-provenance")
    unrouted = sorted(
        path
        for path in pinned
        if not any(router.matches(pattern, path) for pattern in guard.patterns)
    )

    assert unrouted == []


def test_the_two_mistakes_this_router_was_built_for_are_routed() -> None:
    """오늘 실제로 놓친 두 자리."""

    routed = {guard.name for guard, _ in router.route(["apps/web/src/app/ProductShell.tsx"])}
    assert "editor-ui-provenance" in routed

    routed = {guard.name for guard, _ in router.route(["docs/handoffs/2026-08-19-anything.ko.md"])}
    assert "handoff-entry-point" in routed

    routed = {guard.name for guard, _ in router.route(["CLAUDE.md"])}
    assert "handoff-entry-point" in routed
    assert "documentation-contract" in routed


def test_fast_and_slow_are_split_by_the_measured_number_not_by_opinion() -> None:
    """`is_fast`가 실측값과 임계값에서만 나오는지 확인한다."""

    for guard in router.GUARDS:
        assert guard.seconds > 0, f"{guard.name}의 소요가 비어 있습니다 — 실측해서 채우세요"
        assert guard.is_fast == (guard.seconds <= router.FAST_LIMIT_SECONDS)

    fast = [guard.name for guard in router.GUARDS if guard.is_fast]
    slow = [guard.name for guard in router.GUARDS if not guard.is_fast]

    # 편집마다 도는 쪽에는 느린 게 하나도 없어야 한다. 느려지면 사람이 훅을 꺼 버린다.
    assert fast, "빠른 가드가 하나도 없으면 PostToolUse 훅은 아무 일도 안 한다"
    assert "editor-ui-provenance" in slow
    assert "owner-ready-script" in slow


def test_guard_names_are_unique() -> None:
    names = [guard.name for guard in router.GUARDS]

    assert sorted(names) == sorted(set(names))


def test_the_router_guards_itself() -> None:
    """라우터를 고치면 이 표 검사가 바로 돈다."""

    routed = {guard.name for guard, _ in router.route(["scripts/guard_router.py"])}

    assert "guard-router-itself" in routed


def test_paths_outside_the_repository_are_dropped_not_guessed() -> None:
    assert router.normalise("") is None
    assert router.normalise(str(REPO_ROOT / "CLAUDE.md")) == "CLAUDE.md"


def test_a_missing_interpreter_is_reported_as_unknown_not_as_a_pass() -> None:
    """거짓 실패도 거짓 통과도 만들지 않는다 — 못 돌린 것은 '안 돌아감'이다."""

    guard = router.Guard(
        name="fixture",
        what="없는 테스트",
        tests=("tests/test_this_file_does_not_exist.py",),
        patterns=("nothing/at/all",),
        seconds=0.1,
    )

    result = router.run_guard(Path("python"), guard, [])

    assert result.status == router.UNKNOWN
    assert result.status != router.PASS
    assert result.status != router.FAIL


def _command_hooks(event: str, matcher: str | None) -> list[dict]:
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return [
        hook
        for group in settings.get("hooks", {}).get(event, [])
        if matcher is None or group.get("matcher") == matcher
        for hook in group.get("hooks", [])
        if hook.get("type") == "command"
    ]


def test_the_hooks_are_wired_in_the_shape_the_harness_actually_reads() -> None:
    """훅 형식이 틀리면 조용히 아무 일도 안 한다 — 그게 최악이다.

    harness가 훅을 실행하므로 여기서 틀려도 테스트는 초록불이고 화면도 멀쩡하다.
    아무도 안 지키고 있다는 사실만 조용히 유지된다. 그래서 모양을 못박아 둔다.
    """

    post = _command_hooks("PostToolUse", "Edit|Write")
    assert post, "PostToolUse(Edit|Write)에 command 훅이 없습니다"
    assert any("--hook post-tool-use" in hook["command"] for hook in post)
    assert any("scripts/guard_router.py" in hook["command"] for hook in post)

    stop = _command_hooks("Stop", None)
    assert stop, "Stop에 command 훅이 없습니다"
    assert any("--hook stop" in hook["command"] for hook in stop)
    assert any("scripts/guard_router.py" in hook["command"] for hook in stop)

    for hook in post + stop:
        # 시간이 없으면 harness가 훅을 잘라 버리고, 잘린 훅은 아무것도 지키지 않는다.
        assert isinstance(hook.get("timeout"), int) and hook["timeout"] > 0


def test_the_post_tool_use_hook_never_carries_a_slow_guard() -> None:
    """편집마다 느려지면 사람이 훅을 꺼 버린다. 꺼진 훅은 없는 훅이다."""

    slowest_fast = max(
        (guard.seconds for guard in router.GUARDS if guard.is_fast), default=0.0
    )

    assert slowest_fast <= router.FAST_LIMIT_SECONDS


def test_screen_touching_files_are_only_reported_never_claimed_as_verified() -> None:
    """훅은 '화면을 고쳤다'까지만 안다. '화면에서 밟아 봤다'고 말하면 거짓말이다."""

    touched = router.touches_screen(
        ["apps/web/src/features/library/LibraryPanel.tsx", "docs/handoffs/x.md"]
    )

    assert touched == ["apps/web/src/features/library/LibraryPanel.tsx"]

    report = router.summarise([], [], touched)

    assert "확인하지 못합니다" in report
