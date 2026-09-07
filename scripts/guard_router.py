#!/usr/bin/env python
"""방금 건드린 파일을 지키는 테스트만 골라서 바로 돌린다.

이 저장소에는 이음매를 대조하는 좋은 장치가 이미 여러 개 있다.  문제는 그것들이
31분짜리 전체 pytest에서만 돌아서, 화면 파일의 해시를 잊은 것을 31분 뒤에야
알았다는 것이다.  그 사이에 병합·푸시·배포까지 끝나 있었다.

그래서 이 파일이 하는 일은 새 분석이 아니라 **배차**다.  경로 → 그 경로를 지키는
테스트 표를 들고, 바뀐 파일에 걸린 것만 실행한다.

정직에 관한 경계 (이 저장소가 두 번 비싸게 배운 것):

*   **화면에서 실제로 밟아 봤는지는 이 라우터가 모른다.**  라이브러리 전면 차단도,
    자막 배경색이 죽은 것도, 화면에서 써 봐야만 나왔다.  Stop 훅은 "화면에 닿는
    파일을 고쳤다"는 사실만 알려 주고, 거기서 멈춘다.
*   **거짓 실패를 만들지 않는다.**  못 돌린 것은 `안 돌아감`이지 `실패`가 아니고,
    느려서 건너뛴 것은 `통과`가 아니다.  세 상태를 각각 다른 이름으로 보고한다.

사용법::

    python scripts/guard_router.py --list
    python scripts/guard_router.py --files apps/web/src/app/ProductShell.tsx
    python scripts/guard_router.py --changed --speed all
    python scripts/guard_router.py --hook post-tool-use   # stdin: 훅 JSON
    python scripts/guard_router.py --hook stop            # stdin: 훅 JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# Windows 콘솔 기본 코드페이지가 cp949라 한글·em-dash에서 그냥 죽는다.
# 훅이 UnicodeEncodeError로 죽으면 아무것도 검증하지 않은 채 조용히 지나간다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, OSError, ValueError):
        pass

# 여기를 넘으면 편집마다 돌리기에 너무 느리다고 본다.  사람이 훅을 꺼 버리는
# 지점이 그 다음이라, 임계값은 넉넉하게 잡지 않는다.
FAST_LIMIT_SECONDS = 10.0

# 훅 한 번이 여기서 더 길어지면 판정을 포기하고 "안 돌아감"으로 보고한다.
FAST_TIMEOUT_SECONDS = 300
SLOW_TIMEOUT_SECONDS = 1200

PASS = "통과"
FAIL = "실패"
UNKNOWN = "안 돌아감"


@dataclass(frozen=True)
class Guard:
    """경로 한 묶음과, 그 경로를 지키는 테스트들."""

    name: str
    what: str
    tests: tuple[str, ...]
    patterns: tuple[str, ...]
    seconds: float
    """실측값이다. 짐작해서 채우지 않는다 — `docs/development-fast-path.ko.md` §10.18."""

    notes: str = ""

    command: tuple[str, ...] = ()
    """pytest가 아닌 가드. 비어 있으면 `tests`를 pytest로 돌린다.

    e2e는 Playwright라 pytest로 부를 수 없다. 그렇다고 별도 장치를 하나 더
    만들면 "이 경로를 건드리면 무엇이 지키는가"를 두 곳에서 봐야 한다.
    """

    cwd: str = "."

    @property
    def is_fast(self) -> bool:
        return self.seconds <= FAST_LIMIT_SECONDS


# ---------------------------------------------------------------------------
# 가드 매핑 표
#
# `seconds`는 2026-08-20에 이 저장소에서 직접 잰 값이다(인터프리터 기동 포함,
# 같은 묶음의 테스트를 합산).  테스트를 추가하거나 무거워지면 다시 재서 고친다.
# 표가 낡는 것은 `tests/test_guard_router_table.py`가 잡는다.
# ---------------------------------------------------------------------------
GUARDS: tuple[Guard, ...] = (
    Guard(
        name="editor-e2e",
        what="화면 전체가 브라우저에서 실제로 도는지",
        tests=(
            "apps/web/e2e/editor-workbench.spec.mjs",
            "apps/web/e2e/exact-preview.spec.mjs",
        ),
        patterns=(
            "apps/web/src/features/editor/**",
            "apps/web/src/app/*.tsx",
            "apps/web/src/features/library/**",
            "apps/web/e2e/**",
            "apps/web/playwright.config.mjs",
        ),
        seconds=34.4,
        command=("npx", "playwright", "test"),
        cwd="apps/web",
        notes=(
            "2026-08-20에 돌려 보니 **08-19부터 깨져 있었다.** 스펙은 08-18에 쓰였고"
            " 도크 동작은 그다음 날 바뀌었는데, 그사이 아무도 e2e를 돌리지 않았다."
            " 단위 테스트도 픽셀 테스트도 못 잡은 것을 이 층이 잡았다."
        ),
    ),
    Guard(
        name="editor-ui-provenance",
        what="반입한 화면 파일의 해시가 docs/oss 핀과 맞는지",
        tests=("tests/test_editor_ui_source_provenance.py",),
        patterns=(
            "apps/web/src/app/ProductShell.tsx",
            "apps/web/src/app/ProductShell.test.tsx",
            "apps/web/src/components/ui/*.tsx",
            "apps/web/src/features/editor/timeline/*.ts",
            "apps/web/src/features/editor/workbench/*",
            "apps/web/src/hooks/use-mobile.ts",
            "apps/web/src/lib/utils.ts",
            "apps/web/src/ui-system.test.tsx",
            "apps/web/package.json",
            "apps/web/package-lock.json",
            "docs/oss/editor-ui-source-map.json",
            "docs/oss/shadcn-registry-lock.json",
            "THIRD_PARTY_NOTICES.md",
            "scripts/verify-editor-ui-source-provenance.ps1",
        ),
        seconds=39.7,
        notes="느리다. 편집 직후가 아니라 세션 끝(Stop)에만 돈다.",
    ),
    Guard(
        name="handoff-entry-point",
        what="인계 문서와 CLAUDE.md의 진입 표시가 같은 곳을 가리키는지",
        tests=("tests/test_handoff_entry_point.py",),
        patterns=(
            "CLAUDE.md",
            "docs/handoffs/*",
        ),
        seconds=0.9,
    ),
    Guard(
        name="documentation-contract",
        what="제품 범위 경계가 지침·계획서·승인 기록에서 서로 어긋나지 않는지",
        tests=("tests/test_documentation_contract.py",),
        patterns=(
            "CLAUDE.md",
            "docs/implementation-plan.ko.md",
            "docs/decisions/*",
            "docs/superpowers/specs/*",
        ),
        seconds=0.5,
    ),
    Guard(
        name="dev-fast-path-doc",
        what="운영 규정 SSOT 문서와 그 helper 스크립트가 같이 움직이는지",
        tests=("tests/test_dev_fast_path.py",),
        patterns=(
            "docs/development-fast-path.ko.md",
            "scripts/dev-fast-path.ps1",
            "scripts/review-action-fast-path.ps1",
        ),
        seconds=0.9,
    ),
    Guard(
        name="compose-contract",
        what="compose.yaml과 그것을 검증하는 스크립트·기본값이 맞는지",
        tests=("tests/test_compose_contract.py",),
        patterns=(
            "compose.yaml",
            "docker/*",
            "scripts/verify_container_stack.ps1",
            "scripts/verify-hermes-oauth-bootstrap.ps1",
        ),
        seconds=1.0,
    ),
    Guard(
        name="captions",
        what="자막 스타일·폰트가 렌더까지 같은 값으로 흘러가는지",
        tests=(
            "tests/test_ass_subtitles.py",
            "tests/test_caption_style.py",
            "tests/test_caption_fonts.py",
            "tests/test_api_caption_fonts.py",
        ),
        patterns=(
            "packages/core-engine/src/videobox_core_engine/ass_subtitles.py",
            "packages/domain-models/src/videobox_domain_models/caption_style.py",
            "packages/domain-models/src/videobox_domain_models/caption_fonts.py",
            "services/api/src/videobox_api/routers/caption_fonts.py",
        ),
        seconds=6.3,
    ),
    Guard(
        name="overlays",
        what="도형·아이콘 오버레이와 그것을 굽는 렌더 필터가 맞는지",
        tests=(
            "tests/test_overlay_icons.py",
            "tests/test_overlay_motion.py",
            "tests/test_icon_font_asset.py",
        ),
        patterns=(
            "packages/core-engine/src/videobox_core_engine/overlay_shapes.py",
            "packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py",
            "assets/fonts/icons/*",
            "docker/workspace.Dockerfile",
        ),
        seconds=7.1,
        notes="렌더 경로가 둘이다. 필터를 고쳤으면 두 곳을 같이 봐라.",
    ),
    Guard(
        name="library-assets-store",
        what="자산 보관소가 넣고 꺼내는 계약",
        tests=(
            "tests/test_library_image_assets.py",
            "tests/test_library_user_asset_store.py",
        ),
        patterns=(
            "packages/storage-abstractions/src/videobox_storage/library_user_asset_store.py",
            "packages/storage-abstractions/src/videobox_storage/media_library_store.py",
        ),
        seconds=4.9,
    ),
    Guard(
        name="library-assets-api",
        what="화면이 실제로 부르는 자산 추가·조회 경로",
        tests=("tests/test_api_library_assets.py",),
        patterns=(
            "services/api/src/videobox_api/routers/library_assets.py",
            "services/api/src/videobox_api/routers/editor_library.py",
        ),
        seconds=9.9,
        notes=(
            "2026-08-20에 자산 추가가 전부 500이 됐다. 이 테스트는 배관만 본다 — "
            "라이브러리를 고쳤으면 화면에서 실제로 자산을 넣어 봐라."
        ),
    ),
    Guard(
        name="owner-ready-script",
        what="owner가 스택을 켜고 끄는 단 하나의 스크립트",
        tests=("tests/test_owner_ready_script.py",),
        patterns=("scripts/owner-ready.ps1",),
        seconds=491.7,
        notes="아주 느리다(약 8분). Stop에서만 돈다. PowerShell을 테스트마다 새로 띄운다.",
    ),
    Guard(
        name="hermes-yujin-scripts",
        what="유진 스택을 켜고 보고 끄는 스크립트들",
        tests=(
            "tests/test_start_hermes_yujin_script.py",
            "tests/test_restart_hermes_yujin_script.py",
            "tests/test_get_hermes_yujin_status_script.py",
            "tests/test_new_hermes_yujin_secrets_script.py",
        ),
        patterns=(
            "scripts/start-hermes-yujin.ps1",
            "scripts/restart-hermes-yujin.ps1",
            "scripts/get-hermes-yujin-status.ps1",
            "scripts/new-hermes-yujin-secrets.ps1",
            "compose.hermes-yujin.yaml",
        ),
        seconds=106.7,
        notes="느리다. PowerShell 기동이 테스트마다 붙는다.",
    ),
    Guard(
        name="start-videobox-script",
        what="owner가 더블클릭하는 진입 스크립트",
        tests=("tests/test_start_videobox_script.py",),
        patterns=(
            "scripts/Start-VideoBox.ps1",
            "VideoBox.cmd",
            "scripts/Install-VideoBoxShortcut.ps1",
        ),
        seconds=21.3,
        notes="느리다.",
    ),
    Guard(
        name="retired-vocabulary",
        what="쓰지 않기로 한 provider 이름이 제품 소스에 다시 새어 들어왔는지",
        tests=("tests/test_active_product_vocabulary.py",),
        patterns=(
            "apps/web/src/**",
            "apps/web/e2e/**",
            "packages/**",
            "services/**",
        ),
        seconds=1.1,
        notes="넓게 걸리지만 싸다. 붙여넣기로 들어오는 종류의 실수를 잡는다.",
    ),
    Guard(
        name="guard-router-itself",
        what="이 라우터와 그 매핑 표가 실제 파일을 가리키는지",
        tests=("tests/test_guard_router_table.py",),
        patterns=(
            "scripts/guard_router.py",
            "tests/test_guard_router_table.py",
        ),
        seconds=1.2,
    ),
)


# 화면에 닿는 파일.  훅은 이걸 고쳤다는 **사실**만 알려 준다.
# 실제로 브라우저에서 밟아 봤는지는 훅이 알 수 없다 — 그 선을 넘지 않는다.
SCREEN_PATTERNS: tuple[str, ...] = (
    "apps/web/src/*",
    "services/api/src/videobox_api/routers/*",
)


# ---------------------------------------------------------------------------
# glob 매칭
# ---------------------------------------------------------------------------
def _compile(pattern: str) -> re.Pattern[str]:
    """`*`는 `/`를 넘지 않고, `**`는 넘는다. 디렉터리 패턴은 그 아래 전부를 포함한다."""

    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
            if pattern.startswith("/", index):
                index += 1
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    # `docs/handoffs/*`는 그 아래 하위 디렉터리까지 함께 본다.
    return re.compile("^" + "".join(out) + "(/.*)?$")


_CACHE: dict[str, re.Pattern[str]] = {}


def matches(pattern: str, path: str) -> bool:
    compiled = _CACHE.get(pattern)
    if compiled is None:
        compiled = _CACHE[pattern] = _compile(pattern)
    return compiled.match(path) is not None


def normalise(raw: str) -> str | None:
    """훅이 준 경로를 저장소 기준 posix 경로로 바꾼다. 밖이면 None."""

    if not raw:
        return None
    candidate = Path(raw)
    try:
        if candidate.is_absolute():
            return candidate.resolve().relative_to(REPO_ROOT).as_posix()
        return (REPO_ROOT / candidate).resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return None


def route(paths: list[str]) -> list[tuple[Guard, list[str]]]:
    """각 가드에 대해, 그 가드를 깨울 수 있는 경로들을 모은다."""

    routed: list[tuple[Guard, list[str]]] = []
    for guard in GUARDS:
        hits = sorted(
            {path for path in paths for pattern in guard.patterns if matches(pattern, path)}
        )
        if hits:
            routed.append((guard, hits))
    return routed


def touches_screen(paths: list[str]) -> list[str]:
    return sorted(
        {path for path in paths for pattern in SCREEN_PATTERNS if matches(pattern, path)}
    )


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def find_python() -> tuple[Path | None, str]:
    """backend 검증에 쓸 인터프리터.

    시스템 Python으로 슬쩍 넘어가지 않는다 — `CLAUDE.md` §3이 그 결과를 근거로
    쓰지 말라고 못박았다.  못 찾으면 못 찾았다고 말한다.
    """

    override = os.environ.get("VIDEOBOX_GUARD_PYTHON", "").strip()
    if override:
        path = Path(override)
        if path.exists():
            return path, f"VIDEOBOX_GUARD_PYTHON={path}"
        return None, f"VIDEOBOX_GUARD_PYTHON이 가리키는 {path} 가 없습니다"

    for relative in (".venv/Scripts/python.exe", ".venv/bin/python"):
        path = REPO_ROOT / relative
        if path.exists():
            return path, str(path)

    return None, (
        f"{REPO_ROOT}에 .venv가 없습니다. "
        "venv를 만들거나 VIDEOBOX_GUARD_PYTHON으로 인터프리터를 지정하세요"
    )


@dataclass
class Result:
    guard: Guard
    status: str
    seconds: float
    detail: str = ""
    triggers: list[str] = field(default_factory=list)


def run_guard(python: Path, guard: Guard, triggers: list[str]) -> Result:
    missing = [test for test in guard.tests if not (REPO_ROOT / test).exists()]
    if missing:
        # 표가 낡았다는 뜻이다. 그것을 "실패"라고 부르면 거짓 실패가 된다.
        return Result(
            guard,
            UNKNOWN,
            0.0,
            f"표에 적힌 테스트가 없습니다: {', '.join(missing)}",
            triggers,
        )

    timeout = FAST_TIMEOUT_SECONDS if guard.is_fast else SLOW_TIMEOUT_SECONDS
    started = time.perf_counter()
    if guard.command:
        # Windows에서 `npx`는 `npx.cmd`다. 이름 그대로 부르면 파일을 못 찾고,
        # 그 결과가 "안 돌아감"으로 잡히기는 하지만 **영원히 안 돈다.**
        # 도는 척하는 것보다 낫되, 도는 것보다는 못하다.
        executable = shutil.which(guard.command[0])
        if executable is None:
            return Result(
                guard,
                UNKNOWN,
                0.0,
                f"'{guard.command[0]}'을(를) 찾지 못했습니다. Node가 설치돼 있는지 보세요.",
                triggers,
            )
        argv = [executable, *guard.command[1:]]
    else:
        argv = [str(python), "-m", "pytest", *guard.tests, "-q", "-p", "no:cacheprovider"]
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT / guard.cwd,
            capture_output=True,
            text=True,
            # Playwright는 체크 표시 같은 UTF-8을 찍는다. 이 기계의 기본 인코딩
            # (cp949)으로 읽으면 **출력을 읽다가 죽는다** -- 통과일 때는 티가 안
            # 나지만 실패했을 때 근거가 통째로 사라진다. 오늘 그 종류의 결함을
            # 하나 고쳤으니 여기서 되풀이하지 않는다.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        return Result(
            guard,
            UNKNOWN,
            elapsed,
            f"{timeout}초 안에 끝나지 않아 판정하지 못했습니다",
            triggers,
        )
    except OSError as error:
        return Result(guard, UNKNOWN, time.perf_counter() - started, str(error), triggers)

    elapsed = time.perf_counter() - started
    output = (completed.stdout or "") + (completed.stderr or "")
    tail = "\n".join(line for line in output.splitlines() if line.strip())[-1500:]

    if completed.returncode == 0:
        return Result(guard, PASS, elapsed, "", triggers)
    if completed.returncode == 5:
        return Result(guard, UNKNOWN, elapsed, "테스트가 하나도 수집되지 않았습니다", triggers)
    if completed.returncode == 1:
        return Result(guard, FAIL, elapsed, tail, triggers)
    return Result(
        guard,
        FAIL,
        elapsed,
        f"pytest가 끝맺지 못했습니다 (exit {completed.returncode})\n{tail}",
        triggers,
    )


# ---------------------------------------------------------------------------
# 바뀐 파일 모으기
# ---------------------------------------------------------------------------
def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def changed_paths() -> tuple[list[str], list[str]]:
    """작업 트리 변경 + 이 브랜치가 base 이후로 커밋한 것. (경로들, 설명들)"""

    found: set[str] = set()
    notes: list[str] = []

    status = _git("status", "--porcelain", "-z")
    if status is None:
        notes.append("git status를 읽지 못했습니다")
    else:
        # `-z` 출력에서 rename/copy는 `R  새이름\0옛이름\0`으로 두 칸을 쓴다.
        # 옛이름 칸에는 상태 접두사가 없어서, 그냥 3글자를 자르면 쓰레기 경로가 나온다.
        entries = status.split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if len(entry) < 4:
                continue
            found.add(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                if index < len(entries) and entries[index]:
                    found.add(entries[index])
                    index += 1
        notes.append("작업 트리 변경")

    base = os.environ.get("VIDEOBOX_GUARD_BASE_REF", "").strip()
    candidates = [base] if base else []
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream and upstream.strip():
        candidates.append(upstream.strip())
    candidates += ["codex/videobox-container-compatibility", "main"]

    for ref in candidates:
        if not ref:
            continue
        merge_base = _git("merge-base", "HEAD", ref)
        if not merge_base or not merge_base.strip():
            continue
        diff = _git("diff", "--name-only", merge_base.strip(), "HEAD")
        if diff is None:
            continue
        found.update(line for line in diff.splitlines() if line.strip())
        notes.append(f"{ref} 이후의 커밋")
        break
    else:
        notes.append("비교할 base를 못 찾아 커밋된 변경은 못 봤습니다")

    return sorted(path for path in found if path), notes


# ---------------------------------------------------------------------------
# 보고
# ---------------------------------------------------------------------------
def summarise(results: list[Result], skipped: list[Guard], screen: list[str]) -> str:
    lines: list[str] = []
    for result in results:
        line = f"[{result.status}] {result.guard.name} ({result.seconds:.1f}s) — {result.guard.what}"
        if result.detail:
            line += f"\n    {result.detail.replace(chr(10), chr(10) + '    ')}"
        lines.append(line)
    for guard in skipped:
        lines.append(
            f"[나중에] {guard.name} (약 {guard.seconds:.0f}s) — 느려서 편집 직후엔 안 돌립니다. "
            "세션 끝에 돕니다."
        )
    if screen:
        shown = ", ".join(screen[:5]) + (" 외" if len(screen) > 5 else "")
        lines.append(
            "화면에 닿는 파일을 고쳤습니다: "
            + shown
            + "\n    훅은 여기까지만 압니다. 화면에서 실제로 눌러 봤는지는 확인하지 못합니다 — "
            "브라우저에서 직접 밟아 보세요."
        )
    return "\n".join(lines)


def emit_hook(payload: dict[str, object]) -> None:
    # `ensure_ascii=True`로 내보낸다. 콘솔 코드페이지가 무엇이든 순수 ASCII라
    # 깨지지 않고, 훅을 읽는 쪽은 JSON을 파싱하므로 한글이 그대로 복원된다.
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def execute(
    paths: list[str], include_slow: bool
) -> tuple[list[Result], list[Guard], list[str], str | None]:
    routed = route(paths)
    chosen = [(guard, hits) for guard, hits in routed if include_slow or guard.is_fast]
    skipped = [guard for guard, _ in routed if not include_slow and not guard.is_fast]

    if not chosen:
        return [], skipped, touches_screen(paths), None

    python, why = find_python()
    if python is None:
        return [], skipped, touches_screen(paths), why

    results = [run_guard(python, guard, hits) for guard, hits in chosen]
    return results, skipped, touches_screen(paths), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", default=None, help="이 경로들에 걸린 가드를 돌린다")
    parser.add_argument("--changed", action="store_true", help="git이 본 변경 전체를 훑는다")
    parser.add_argument("--speed", choices=("fast", "all"), default="fast")
    parser.add_argument("--list", action="store_true", help="매핑 표를 출력한다")
    parser.add_argument("--hook", choices=("post-tool-use", "stop"), default=None)
    arguments = parser.parse_args()

    if arguments.list:
        for guard in GUARDS:
            tier = "빠름" if guard.is_fast else "느림"
            print(f"{guard.name}  [{tier} {guard.seconds:.1f}s]  {guard.what}")
            for test in guard.tests:
                print(f"    지킨다: {test}")
            for pattern in guard.patterns:
                print(f"    걸린다: {pattern}")
            if guard.notes:
                print(f"    메모  : {guard.notes}")
            print()
        return 0

    if arguments.hook:
        return run_as_hook(arguments.hook)

    if arguments.changed:
        paths, _ = changed_paths()
    else:
        paths = [
            normalised
            for raw in (arguments.files or [])
            if (normalised := normalise(raw)) is not None
        ]

    results, skipped, screen, blocked = execute(paths, arguments.speed == "all")
    if blocked:
        print(f"가드를 돌리지 못했습니다: {blocked}", file=sys.stderr)
        return 2
    report = summarise(results, skipped, screen)
    print(report if report else "이 경로들에 걸린 가드가 없습니다.")
    return 1 if any(result.status == FAIL for result in results) else 0


def _read_hook_input() -> dict[str, object]:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def run_as_hook(event: str) -> int:
    payload = _read_hook_input()

    if event == "post-tool-use":
        tool_input = payload.get("tool_input")
        raw = ""
        if isinstance(tool_input, dict):
            raw = str(tool_input.get("file_path") or "")
        if not raw:
            response = payload.get("tool_response")
            if isinstance(response, dict):
                raw = str(response.get("filePath") or "")
        normalised = normalise(raw)
        paths = [normalised] if normalised else []
        include_slow = False
    else:
        paths, _ = changed_paths()
        include_slow = True

    results, skipped, screen, blocked = execute(paths, include_slow)

    if blocked:
        emit_hook(
            {
                "systemMessage": f"가드 라우터가 검증용 python을 찾지 못했습니다 — {blocked}. "
                "이번 턴에는 아무것도 검증하지 못했습니다."
            }
        )
        return 0

    failures = [result for result in results if result.status == FAIL]
    unknowns = [result for result in results if result.status == UNKNOWN]

    if not results and not skipped and not screen:
        # 걸린 게 없으면 조용히 있는다.
        emit_hook({"suppressOutput": True})
        return 0

    report = summarise(results, skipped, screen)

    if event == "post-tool-use":
        if failures:
            emit_hook(
                {
                    "systemMessage": "가드가 실패했습니다 — 방금 바꾼 파일이 이음매를 깼습니다.",
                    "decision": "block",
                    "reason": "방금 편집한 파일에 걸린 가드가 실패했습니다. "
                    "이어서 진행하기 전에 고치세요.\n\n" + report,
                }
            )
            return 0
        if unknowns:
            emit_hook({"systemMessage": report})
            return 0
        # 통과했거나, 느려서 미룬 것만 있으면 짧게만 알린다.
        if skipped or screen:
            emit_hook({"systemMessage": report, "suppressOutput": True})
        else:
            emit_hook({"suppressOutput": True})
        return 0

    # Stop: 이번 세션에 바뀐 것 전체를 한 번 훑는 자리다. 오늘 놓친 자리가 여기다.
    already_blocked = bool(payload.get("stop_hook_active"))
    message = "세션 끝 가드 점검\n" + report
    if failures and not already_blocked:
        emit_hook(
            {
                "systemMessage": message,
                "decision": "block",
                "reason": "이번 세션에 바뀐 파일에 걸린 가드가 실패했습니다. "
                "끝내기 전에 고치거나, 왜 그대로 두는지 설명하세요.\n\n" + report,
            }
        )
        return 0
    emit_hook({"systemMessage": message})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
