from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-hermes-yujin-zero-tools.ps1"
MARKER = "hermes_yujin_zero_tools=verified"


def _powershell(*arguments: str, env: dict[str, str] | None = None, timeout=60):
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _pwsh(*arguments: str, env: dict[str, str] | None = None, timeout=60):
    return subprocess.run(
        ["pwsh", "-NoProfile", *arguments],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def test_zero_tool_verifier_uses_argument_list_and_python_stdin() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "ProcessStartInfo" in source
    assert ".ArgumentList.Add(" in source
    assert "RedirectStandardInput" in source
    assert ".StandardInput.Write($proof)" in source
    assert '"-c"' not in source
    assert '"-"' in source
    assert "--network" in source
    assert "none" in source
    assert '[string]$DockerExecutable = "docker"' in source


def test_zero_tool_verifier_preserves_fake_docker_argv_and_stdin(
    tmp_path: Path,
) -> None:
    fake_source = tmp_path / "fake_docker.py"
    log = tmp_path / "docker"
    fake_source.write_text(
        """
import os
from pathlib import Path
import sys

log = Path(os.environ["FAKE_DOCKER_LOG"])
log.with_suffix(".args").write_text("\\n".join(sys.argv[1:]), encoding="utf-8")
proof = sys.stdin.read()
log.with_suffix(".stdin").write_text(proof, encoding="utf-8")
if "-c" in sys.argv[1:] or sys.argv[-1] != "-":
    raise SystemExit(31)
if "get_tool_definitions" not in proof or "hermes_yujin_zero_tools=verified" not in proof:
    raise SystemExit(33)
print("hermes_yujin_zero_tools=verified")
""".strip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["FAKE_DOCKER_LOG"] = str(log)
    result = _pwsh(
        "-File",
        str(SCRIPT),
        "-DockerExecutable",
        sys.executable,
        "-DockerPrefixArguments",
        str(fake_source),
        env=env,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert MARKER in result.stdout
    args = (tmp_path / "docker.args").read_text(encoding="utf-8").splitlines()
    assert args == [
        "run",
        "--rm",
        "--interactive",
        "--network",
        "none",
        "--env",
        "HERMES_TUI_TOOLSETS=context_engine",
        "--entrypoint",
        "python",
        (
            "nousresearch/hermes-agent@sha256:"
            "ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
        ),
        "-",
    ]
    proof = (tmp_path / "docker.stdin").read_text(encoding="utf-8")
    assert "get_tool_definitions" in proof
    assert MARKER in proof


def test_zero_tool_verifier_runs_against_pinned_local_image_without_network() -> None:
    result = _powershell("-File", str(SCRIPT), timeout=90)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert result.stdout.splitlines() == [MARKER]
