from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify-hermes-yujin-plan-state.ps1"
PLAN_PATHS = (
    Path("docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md"),
    Path(
        "docs/superpowers/plans/"
        "2026-07-26-videobox-hermes-yujin-runtime-chat-vertical-slice.md"
    ),
    Path("docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-creator-tools.md"),
    Path(
        "docs/superpowers/plans/"
        "2026-07-26-videobox-hermes-yujin-realtime-reliability.md"
    ),
    Path("docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md"),
)


def _run_verifier(repository_root: Path) -> subprocess.CompletedProcess[str]:
    assert VERIFIER.is_file(), f"missing verifier: {VERIFIER}"
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VERIFIER),
            "-RepositoryRoot",
            str(repository_root),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_verifier_with_default_root() -> subprocess.CompletedProcess[str]:
    assert VERIFIER.is_file(), f"missing verifier: {VERIFIER}"
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(VERIFIER),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _plan_fixture(tmp_path: Path) -> Path:
    for relative_path in PLAN_PATHS:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
    return tmp_path


def _replace_once(path: Path, old: str, new: str) -> None:
    original = path.read_text(encoding="utf-8")
    assert original.count(old) == 1, f"expected one occurrence of {old!r}"
    path.write_text(original.replace(old, new, 1), encoding="utf-8")


def _unique_matching_line(path: Path, pattern: str) -> str:
    matches = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(pattern, line)
    ]
    assert len(matches) == 1, f"expected one line matching {pattern!r}"
    return matches[0]


def _invalid_progress_line(current: str, *, fault: str, child: bool) -> str:
    pattern = (
        r"^Child progress: \*\*(\d+)/(\d+) tasks \((\d+\.\d)%\), "
        r"remaining (\d+\.\d)%\*\*\."
        if child
        else (
            r"^Current initiative progress: \*\*(\d+)/(\d+) \((\d+\.\d)%\), "
            r"remaining (\d+\.\d)%\*\*\."
        )
    )
    match = re.match(pattern, current)
    assert match is not None, f"unexpected progress line: {current!r}"
    numerator, denominator, percent, remaining = match.groups()
    if fault == "numerator":
        numerator = str(int(numerator) + 1)
    elif fault == "denominator":
        denominator = str(int(denominator) + 1)
    elif fault == "remaining":
        remaining = f"{float(remaining) + 0.1:.1f}"
    else:
        raise AssertionError(f"unknown progress fault: {fault}")
    if child:
        return (
            f"Child progress: **{numerator}/{denominator} tasks ({percent}%), "
            f"remaining {remaining}%**."
        )
    return (
        f"Current initiative progress: **{numerator}/{denominator} ({percent}%), "
        f"remaining {remaining}%**."
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"


def test_verifier_accepts_the_current_five_consistent_plans() -> None:
    result = _run_verifier(REPOSITORY_ROOT)

    assert result.returncode == 0, _combined_output(result)
    assert "20 unique master task IDs" in result.stdout


def test_verifier_defaults_to_the_actual_repository_root() -> None:
    result = _run_verifier_with_default_root()

    assert result.returncode == 0, _combined_output(result)


def test_verifier_rejects_a_duplicate_master_task_id(tmp_path: Path) -> None:
    fixture = _plan_fixture(tmp_path)
    master = fixture / PLAN_PATHS[0]
    master.write_text(
        master.read_text(encoding="utf-8")
        + "\n- [ ] **A1** duplicate task fixture\n",
        encoding="utf-8",
    )

    result = _run_verifier(fixture)

    assert result.returncode != 0
    assert "duplicate" in _combined_output(result).lower()
    assert "A1" in _combined_output(result)


def test_verifier_rejects_missing_and_unexpected_master_task_ids(
    tmp_path: Path,
) -> None:
    fixture = _plan_fixture(tmp_path)
    master = fixture / PLAN_PATHS[0]
    a1_line = _unique_matching_line(
        master,
        r"^- \[(?: |~|x|!)\] \*\*A1\*\* Add the isolated official Hermes Yujin runtime topology",
    )
    _replace_once(
        master,
        a1_line,
        a1_line.replace("**A1**", "**A5**", 1),
    )

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0
    assert "missing" in output.lower()
    assert "A1" in output
    assert "unexpected" in output.lower()
    assert "A5" in output


def test_verifier_requires_every_task_exactly_once_across_children(
    tmp_path: Path,
) -> None:
    fixture = _plan_fixture(tmp_path)
    runtime_child = fixture / PLAN_PATHS[1]
    a1_line = _unique_matching_line(
        runtime_child,
        r"^- \[(?: |~|x|!)\] \*\*A1\*\* Add the isolated official Hermes Yujin runtime topology",
    )
    _replace_once(
        runtime_child,
        a1_line,
        a1_line.replace("**A1**", "**A2**", 1),
    )

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0
    assert "A1" in output
    assert "A2" in output
    assert "child" in output.lower()


def test_verifier_rejects_a_task_moved_between_fixed_child_partitions(
    tmp_path: Path,
) -> None:
    fixture = _plan_fixture(tmp_path)
    creator_child = fixture / PLAN_PATHS[2]
    reliability_child = fixture / PLAN_PATHS[3]
    moved_task = _unique_matching_line(
        creator_child,
        r"^- \[(?: |~|x|!)\] \*\*B1\*\* Build the allowlisted current-revision creator context "
        r"and typed read DTOs\.",
    )
    creator_text = creator_child.read_text(encoding="utf-8")
    assert creator_text.count(moved_task) == 1
    creator_child.write_text(
        creator_text.replace(f"{moved_task}\n", "", 1).replace(
            "Child progress: **0/5 tasks (0.0%), remaining 100.0%**.",
            "Child progress: **0/4 tasks (0.0%), remaining 100.0%**.",
            1,
        ),
        encoding="utf-8",
    )
    reliability_child.write_text(
        reliability_child.read_text(encoding="utf-8").replace(
            "Child progress: **0/4 tasks (0.0%), remaining 100.0%**.",
            "Child progress: **0/5 tasks (0.0%), remaining 100.0%**.",
            1,
        )
        + f"\n{moved_task}\n",
        encoding="utf-8",
    )

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0, "verifier accepted an invalid fixed child partition"
    assert "creator-tools" in output
    assert "expected 5" in output
    assert "realtime-reliability" in output
    assert "expected 4" in output


def test_verifier_rejects_equal_cardinality_task_swaps_between_children(
    tmp_path: Path,
) -> None:
    fixture = _plan_fixture(tmp_path)
    creator_child = fixture / PLAN_PATHS[2]
    reliability_child = fixture / PLAN_PATHS[3]
    creator_task = _unique_matching_line(
        creator_child,
        r"^- \[(?: |~|x|!)\] \*\*B1\*\* Build the allowlisted current-revision creator context "
        r"and typed read DTOs\.",
    )
    reliability_task = (
        "- [ ] **C1** Persist run/event cursors and restore final or interrupted "
        "conversation state."
    )
    _replace_once(creator_child, creator_task, reliability_task)
    _replace_once(reliability_child, reliability_task, creator_task)

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0, "verifier accepted swapped child task ownership"
    assert "creator-tools" in output
    assert "missing task IDs: B1" in output
    assert "unexpected task IDs: C1" in output
    assert "realtime-reliability" in output
    assert "missing task IDs: C1" in output
    assert "unexpected task IDs: B1" in output


def test_status_mismatch_names_task_and_both_statuses(tmp_path: Path) -> None:
    fixture = _plan_fixture(tmp_path)
    runtime_child = fixture / PLAN_PATHS[1]
    _replace_once(
        runtime_child,
        "- [x] **P0-1**",
        "- [ ] **P0-1**",
    )

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0
    assert "P0-1" in output
    assert "master=[x]" in output
    assert "child=[ ]" in output


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("numerator", "completed numerator"),
        ("denominator", "denominator"),
        ("remaining", "remaining"),
    ),
)
def test_verifier_rejects_invalid_master_progress(
    tmp_path: Path,
    fault: str,
    expected: str,
) -> None:
    fixture = _plan_fixture(tmp_path)
    master = fixture / PLAN_PATHS[0]
    current = _unique_matching_line(master, r"^Current initiative progress:")
    _replace_once(
        master,
        current,
        _invalid_progress_line(current, fault=fault, child=False),
    )

    result = _run_verifier(fixture)

    assert result.returncode != 0
    assert expected in _combined_output(result).lower()


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("numerator", "completed numerator"),
        ("denominator", "denominator"),
        ("remaining", "remaining"),
    ),
)
def test_verifier_rejects_invalid_child_progress(
    tmp_path: Path,
    fault: str,
    expected: str,
) -> None:
    fixture = _plan_fixture(tmp_path)
    runtime_child = fixture / PLAN_PATHS[1]
    current = _unique_matching_line(runtime_child, r"^Child progress:")
    _replace_once(
        runtime_child,
        current,
        _invalid_progress_line(current, fault=fault, child=True),
    )

    result = _run_verifier(fixture)

    assert result.returncode != 0
    assert expected in _combined_output(result).lower()


def test_verifier_rejects_unfinished_placeholder_markers(tmp_path: Path) -> None:
    fixture = _plan_fixture(tmp_path)
    child = fixture / PLAN_PATHS[2]
    child.write_text(
        child.read_text(encoding="utf-8") + "\nTODO: unfinished plan text\n",
        encoding="utf-8",
    )

    result = _run_verifier(fixture)
    output = _combined_output(result)

    assert result.returncode != 0
    assert "placeholder" in output.lower()
    assert "TODO" in output
