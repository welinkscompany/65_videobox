from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
PROFILE_ROOT = ROOT / "config" / "hermes" / "yujin"
VERIFY_SCRIPT = ROOT / "scripts" / "verify-hermes-yujin-profile.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install-hermes-yujin-profile.ps1"
START_SCRIPT = ROOT / "scripts" / "start-hermes-yujin.ps1"
OVERLAY_PATH = ROOT / "compose.hermes-yujin.yaml"

EXPECTED_MANIFEST = {
    "name": "videobox-yujin",
    "version": "1.0.0",
    "hermes_requires": ">=0.18.0",
    "distribution_owned": ["SOUL.md", "config.yaml", "skills/"],
}
EXPECTED_FILES = {
    "distribution.yaml",
    "SOUL.md",
    "config.yaml",
    "skills/videobox-editor/SKILL.md",
}


def _run_powershell(
    script: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        cwd=ROOT,
        env={**os.environ, **(environment or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def _copy_profile(tmp_path: Path) -> Path:
    copied = tmp_path / "yujin"
    shutil.copytree(PROFILE_ROOT, copied)
    return copied


def test_distribution_manifest_and_real_file_ownership_are_exact() -> None:
    manifest = yaml.safe_load(
        (PROFILE_ROOT / "distribution.yaml").read_text(encoding="utf-8")
    )
    actual_files = {
        path.relative_to(PROFILE_ROOT).as_posix()
        for path in PROFILE_ROOT.rglob("*")
        if path.is_file()
    }

    assert manifest == EXPECTED_MANIFEST
    assert actual_files == EXPECTED_FILES


def test_soul_is_korean_first_non_authorizing_and_evidence_honest() -> None:
    soul = (PROFILE_ROOT / "SOUL.md").read_text(encoding="utf-8")

    for required in (
        "한국어를 우선",
        "자동 적용하지",
        "VideoBox가 남긴 근거",
        "미리보기",
        "내보내기",
        "성공했다고 말하지",
        "지원되지 않는 효과",
        "실행 가능한 조절 기능으로 제안하지",
        "수동 대체 절차",
    ):
        assert required in soul


def test_first_skill_is_only_conversation_clarification_and_manual_fallback() -> None:
    skill = (
        PROFILE_ROOT / "skills" / "videobox-editor" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "대화" in skill
    assert "확인 질문" in skill
    assert "수동 대체 절차" in skill
    for forbidden in (
        "자동 적용",
        "creator proposal",
        "콘텐츠 후보",
        "도구를 실행",
        "렌더를 실행",
        "내보내기를 실행",
    ):
        assert forbidden not in skill


def test_profile_is_mounted_read_only_only_in_the_opt_in_overlay() -> None:
    overlay = yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))
    hermes = overlay["services"]["videobox-hermes-yujin"]
    mount = "./config/hermes/yujin:/opt/videobox-yujin-profile:ro"

    assert hermes["container_name"] == "videobox-hermes-yujin"
    assert hermes["command"] == [
        "-p",
        "videobox-yujin",
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "9120",
    ]
    assert mount in hermes["volumes"]
    assert mount not in (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ports" not in hermes
    assert "provider" not in str(hermes.get("environment", {})).lower()
    assert all("secret" not in item.lower() for item in hermes["volumes"])


def test_static_verifier_accepts_the_canonical_package() -> None:
    result = _run_powershell(VERIFY_SCRIPT, "-StaticOnly")

    assert result.returncode == 0, result.stderr
    assert "ownership and secret-free contents verified" in result.stdout


@pytest.mark.parametrize(
    ("relative_path", "unsafe_text"),
    (
        ("SOUL.md", "api_key: sk-test-1234567890"),
        ("SOUL.md", "oauth_token: bearer-value"),
        ("SOUL.md", "password: local-value"),
        ("config.yaml", "source: C:\\Users\\example\\profile"),
        ("config.yaml", "source: /home/example/profile"),
        ("config.yaml", "MEM0_API_KEY: mem0-value"),
    ),
)
def test_static_verifier_rejects_secrets_and_local_absolute_user_paths(
    tmp_path: Path,
    relative_path: str,
    unsafe_text: str,
) -> None:
    copied = _copy_profile(tmp_path)
    target = copied / Path(relative_path)
    target.write_text(
        target.read_text(encoding="utf-8") + f"\n{unsafe_text}\n",
        encoding="utf-8",
    )

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0
    assert unsafe_text not in f"{result.stdout}\n{result.stderr}"


@pytest.mark.parametrize(
    "relative_path",
    (
        "undeclared.txt",
        "skills/videobox-editor/run.ps1",
        "skills/videobox-editor/run.PS1",
    ),
)
def test_static_verifier_rejects_undeclared_or_executable_files(
    tmp_path: Path,
    relative_path: str,
) -> None:
    copied = _copy_profile(tmp_path)
    target = copied / Path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("safe placeholder", encoding="utf-8")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


def test_static_verifier_rejects_a_reparse_point_when_supported(
    tmp_path: Path,
) -> None:
    copied = _copy_profile(tmp_path)
    link = copied / "skills" / "linked-skill"
    try:
        link.symlink_to(copied / "skills" / "videobox-editor", target_is_directory=True)
    except OSError:
        pytest.skip("This Windows account cannot create a symbolic link.")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


def _write_fake_docker(tmp_path: Path, *, exit_code: int = 0) -> tuple[Path, Path]:
    executable = tmp_path / "docker.cmd"
    log = tmp_path / "docker.log"
    executable.write_text(
        "@echo off\r\n"
        'echo %*>>"%FAKE_DOCKER_LOG%"\r\n'
        f"exit /b {exit_code}\r\n",
        encoding="utf-8",
    )
    return executable, log


def test_installer_runs_the_exact_idempotent_install_inside_the_named_container(
    tmp_path: Path,
) -> None:
    fake_docker, log = _write_fake_docker(tmp_path)
    env_file = tmp_path / "container.env"
    env_file.write_text("SAFE=value\n", encoding="utf-8")
    arguments = (
        "-DockerExecutable",
        str(fake_docker),
        "-EnvFile",
        str(env_file),
        "-InstallerContainerName",
        "videobox-hermes-yujin-profile-installer",
    )

    first = _run_powershell(
        INSTALL_SCRIPT,
        *arguments,
        environment={"FAKE_DOCKER_LOG": str(log)},
    )
    second = _run_powershell(
        INSTALL_SCRIPT,
        *arguments,
        environment={"FAKE_DOCKER_LOG": str(log)},
    )

    assert first.returncode == 0
    assert second.returncode == 0
    invocations = log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2
    for invocation in invocations:
        assert "compose" in invocation
        assert "run --rm --no-deps" in invocation
        assert "--name videobox-hermes-yujin-profile-installer" in invocation
        assert "--entrypoint hermes videobox-hermes-yujin profile install" in invocation
        assert (
            "/opt/videobox-yujin-profile --name videobox-yujin --force -y"
            in invocation
        )


def test_installer_fails_closed_without_host_install_or_secret_output(
    tmp_path: Path,
) -> None:
    fake_docker, log = _write_fake_docker(tmp_path, exit_code=31)
    env_file = tmp_path / "container.env"
    env_file.write_text("SAFE=value\n", encoding="utf-8")
    result = _run_powershell(
        INSTALL_SCRIPT,
        "-DockerExecutable",
        str(fake_docker),
        "-EnvFile",
        str(env_file),
        environment={"FAKE_DOCKER_LOG": str(log), "PRIVATE_SENTINEL": "do-not-leak"},
    )
    source = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert result.returncode != 0
    assert "do-not-leak" not in f"{result.stdout}\n{result.stderr}"
    assert '"run"' in source
    assert "profile install" in source
    assert "Start-Process" not in source


def test_start_verifies_and_installs_before_gateway_and_validate_only_exits_first() -> None:
    source = START_SCRIPT.read_text(encoding="utf-8")

    validate_exit = source.index("if ($ValidateOnly)")
    verifier = source.index("verify-hermes-yujin-profile.ps1")
    installer = source.index("install-hermes-yujin-profile.ps1")
    hermes_start = source.index('"videobox-hermes-yujin"', installer)
    gateway_start = source.index('"videobox-agent-gateway"', installer)

    assert validate_exit < verifier < installer < hermes_start < gateway_start
    assert "compose.yaml" in source
    assert "compose.hermes-yujin.yaml" in source
