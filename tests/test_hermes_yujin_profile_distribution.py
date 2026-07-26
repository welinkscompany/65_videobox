from __future__ import annotations

import os
import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
PROFILE_ROOT = ROOT / "config" / "hermes" / "yujin"
VERIFY_SCRIPT = ROOT / "scripts" / "verify-hermes-yujin-profile.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install-hermes-yujin-profile.ps1"
START_SCRIPT = ROOT / "scripts" / "start-hermes-yujin.ps1"
CONTENT_HELPER = ROOT / "scripts" / "verify_hermes_yujin_profile_content.py"
REQUIREMENTS_DEV = ROOT / "requirements-dev.txt"
STATUS_DOC = ROOT / "docs" / "development-status-2026-06-29.ko.md"
HANDOFF_DOC = (
    ROOT
    / "docs"
    / "handoffs"
    / "2026-07-26-videobox-hermes-yujin-planning-closeout.ko.md"
)
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
PARTIAL_PROFILE_STATE = (
    "Profile install may have left a partial profile in the "
    "videobox_hermes_oauth_state named volume at /opt/data; "
    "recovery is service-only; do not delete that volume. "
    "Rerun uses --force idempotently."
)
SAFE_RERUN_RECOVERY = (
    "Recovery: powershell -NoProfile -ExecutionPolicy Bypass "
    "-File scripts/start-hermes-yujin.ps1 -EnvFile <approved-env-file>"
)


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


def _runtime_sensitive_cases() -> tuple[tuple[str, str], ...]:
    github_token = "ghp_" + ("x" * 36)
    api_token = "sk-" + ("a" * 24)
    bearer_token = "Bearer " + ("b" * 32)
    return (
        ("SOUL.md", "(C:\\Users\\runtime-user\\profile)"),
        ("SOUL.md", "`D:\\Users\\runtime-user\\profile`"),
        ("SOUL.md", "(/home/runtime-user/profile)"),
        ("SOUL.md", "(/Users/runtime-user/profile)"),
        ("config.yaml", f"github_token: {github_token}"),
        ("config.yaml", f"api_key: {api_token}"),
        ("config.yaml", f"authorization: {bearer_token}"),
        ("config.yaml", "oauth_token: runtime-oauth-value"),
        ("config.yaml", "password = runtime-value"),
        ("config.yaml", "MEM0_API_KEY: runtime-mem0-value"),
    )


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


def test_profile_content_verifier_declares_the_exact_installed_pyyaml_runtime() -> None:
    requirement_lines = REQUIREMENTS_DEV.read_text(encoding="utf-8").splitlines()

    assert requirement_lines.count("PyYAML==6.0.3") == 1
    assert metadata.version("PyYAML") == "6.0.3"


def test_profile_content_helper_reports_missing_pyyaml_without_sensitive_context(
    tmp_path: Path,
) -> None:
    sensitive_root = tmp_path / "generated-secret-profile-root"
    sensitive_root.mkdir()

    result = subprocess.run(
        [
            str(ROOT / ".venv" / "Scripts" / "python.exe"),
            "-S",
            str(CONTENT_HELPER),
            str(sensitive_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "Yujin profile content verification is unavailable." in output
    assert "Traceback" not in output
    assert str(ROOT) not in output
    assert str(sensitive_root) not in output
    assert "generated-secret-profile-root" not in output


def test_a2_closeout_docs_explain_persistent_profile_recovery() -> None:
    for document in (STATUS_DOC, HANDOFF_DOC):
        content = document.read_text(encoding="utf-8")
        assert "videobox_hermes_oauth_state named volume" in content
        assert "/opt/data" in content
        assert "rerun uses --force idempotently" in content
        assert "service cleanup only; the named volume is not deleted" in content


@pytest.mark.parametrize(
    ("relative_path", "unsafe_text"),
    _runtime_sensitive_cases(),
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
        "skills/videobox-editor/run.PSM1",
        "skills/videobox-editor/run.mjs",
        "skills/videobox-editor/run.hta",
        "skills/videobox-editor/run.rb",
        "skills/videobox-editor/run.pl",
        "skills/videobox-editor/run.php",
        "skills/videobox-editor/notes.txt",
        "skills/videobox-editor/data.json",
    ),
)
def test_static_verifier_rejects_outside_ownership_or_disallowed_content_types(
    tmp_path: Path,
    relative_path: str,
) -> None:
    copied = _copy_profile(tmp_path)
    target = copied / Path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fixture_content = {
        ".rb": "#!/usr/bin/env ruby\nputs 'fixture'\n",
        ".pl": "#!/usr/bin/env perl\nprint 'fixture';\n",
        ".php": "<?php echo 'fixture'; ?>\n",
    }.get(target.suffix.lower(), "safe placeholder")
    target.write_text(fixture_content, encoding="utf-8")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


def test_static_verifier_rejects_an_extensionless_shebang_file(
    tmp_path: Path,
) -> None:
    copied = _copy_profile(tmp_path)
    executable = copied / "skills" / "videobox-editor" / "run"
    executable.write_text("#!/usr/bin/env python\nprint('fixture')\n", encoding="utf-8")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


def test_static_verifier_rejects_a_shebang_in_an_allowed_markdown_file(
    tmp_path: Path,
) -> None:
    copied = _copy_profile(tmp_path)
    executable = copied / "skills" / "videobox-editor" / "payload.md"
    executable.write_text("#!/usr/bin/env ruby\nputs 'fixture'\n", encoding="utf-8")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


@pytest.mark.parametrize("magic", (b"MZ", b"\x7fELF"))
def test_static_verifier_rejects_binary_magic_even_with_a_markdown_name(
    tmp_path: Path,
    magic: bytes,
) -> None:
    copied = _copy_profile(tmp_path)
    disguised = copied / "skills" / "videobox-editor" / "payload.md"
    disguised.write_bytes(magic + (b"\x00" * 32))

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


@pytest.mark.parametrize(
    "payload",
    (
        b"\xff\xfeinvalid-utf8",
        b"ordinary text\x00with nul",
        b"ordinary text\x01with control",
        b"PK\x03\x04renamed zip payload",
    ),
)
def test_static_verifier_rejects_nontext_payloads_with_markdown_names(
    tmp_path: Path,
    payload: bytes,
) -> None:
    copied = _copy_profile(tmp_path)
    disguised = copied / "skills" / "videobox-editor" / "payload.md"
    disguised.write_bytes(payload)

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0


def test_static_verifier_accepts_utf8_bom_text(tmp_path: Path) -> None:
    copied = _copy_profile(tmp_path)
    soul = copied / "SOUL.md"
    soul.write_bytes(b"\xef\xbb\xbf" + soul.read_bytes())

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "yaml_text",
    (
        "password: |\n  generated-runtime-value\n",
        "outer:\n  client_secret: generated-runtime-value\n",
        "items:\n  - api_key: generated-runtime-value\n",
        (
            "defaults: &defaults\n"
            "  oauth_token: generated-runtime-value\n"
            "copy: *defaults\n"
        ),
        "outer: [unterminated\n",
        "password: one\npassword: two\n",
        "name: one\nname: two\n",
        "value: !!python/object/apply:os.system []\n",
    ),
)
def test_static_verifier_fails_closed_on_unsafe_yaml_shapes(
    tmp_path: Path,
    yaml_text: str,
) -> None:
    copied = _copy_profile(tmp_path)
    (copied / "config.yaml").write_text(yaml_text, encoding="utf-8")

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode != 0
    assert "generated-runtime-value" not in f"{result.stdout}\n{result.stderr}"


def test_static_verifier_accepts_safe_nested_yaml_aliases(tmp_path: Path) -> None:
    copied = _copy_profile(tmp_path)
    (copied / "config.yaml").write_text(
        "defaults: &defaults\n  language: ko\nitems:\n  - *defaults\n",
        encoding="utf-8",
    )

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode == 0, result.stderr


def test_static_verifier_allows_ordinary_security_policy_prose(
    tmp_path: Path,
) -> None:
    copied = _copy_profile(tmp_path)
    soul = copied / "SOUL.md"
    soul.write_text(
        soul.read_text(encoding="utf-8")
        + "\nAPI key, OAuth token, password, Mem0 credential은 문서에 넣지 않습니다.\n"
        + "\n```sh\n#!/usr/bin/env bash\necho documentation-example\n```\n",
        encoding="utf-8",
    )

    result = _run_powershell(
        VERIFY_SCRIPT,
        "-StaticOnly",
        "-ProfileRoot",
        str(copied),
    )

    assert result.returncode == 0


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
    output = f"{result.stdout}\n{result.stderr}"
    compact_output = re.sub(r"\s+", "", output)
    assert "do-not-leak" not in output
    assert str(tmp_path) not in output
    assert re.sub(r"\s+", "", PARTIAL_PROFILE_STATE) in compact_output
    assert re.sub(r"\s+", "", SAFE_RERUN_RECOVERY) in compact_output
    assert '"run"' in source
    assert "profile install" in source
    assert "Start-Process" not in source
    invocations = log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 2
    generated_name = re.search(
        r"--name (videobox-hermes-yujin-profile-installer-[a-f0-9]{32})",
        invocations[0],
    ).group(1)
    assert invocations[1] == f"rm -f {generated_name}"
    assert all(" down " not in f" {call} " for call in invocations)
    assert all(" volume " not in f" {call} " for call in invocations)
    assert all(" -v " not in f" {call} " for call in invocations)


def test_installer_uses_a_unique_one_off_name_when_name_is_omitted(
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
    names = [
        re.search(
            r"--name (videobox-hermes-yujin-profile-installer-[a-f0-9]{32})",
            invocation,
        ).group(1)
        for invocation in invocations
    ]
    assert len(set(names)) == 2


def test_start_verifies_before_validate_only_exit_and_installs_before_gateway() -> None:
    source = START_SCRIPT.read_text(encoding="utf-8")

    validate_exit = source.index("if ($ValidateOnly)")
    verifier = source.index("verify-hermes-yujin-profile.ps1")
    recovery_message = source.index("$persistentProfileState")
    installer = source.index("install-hermes-yujin-profile.ps1")
    hermes_start = source.index('"videobox-hermes-yujin"', installer)
    gateway_start = source.index('"videobox-agent-gateway"', installer)

    assert (
        verifier
        < validate_exit
        < recovery_message
        < installer
        < hermes_start
        < gateway_start
    )
    assert "compose.yaml" in source
    assert "compose.hermes-yujin.yaml" in source
