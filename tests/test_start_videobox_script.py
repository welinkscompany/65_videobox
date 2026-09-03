"""아이콘 하나로 켜는 경로를 지킨다.

owner가 손으로 하던 세 단계 -- Docker Desktop 켜기, `owner-ready.ps1 -Mode Start`,
주소 치기 -- 를 하나로 묶은 것이 `scripts/Start-VideoBox.ps1`이다. 여기서 지키는 것은
그 순서와 **경계** 둘이다. 경계란: 컨테이너는 이 스크립트가 직접 다루지 않고
`owner-ready.ps1`에 넘긴다(`CLAUDE.md` §3). 시작 방법이 두 벌이 되면 그중 하나가
조용히 낡는다.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "Start-VideoBox.ps1"
SHORTCUT_SCRIPT = ROOT / "scripts" / "Install-VideoBoxShortcut.ps1"
CMD = ROOT / "VideoBox.cmd"


@contextmanager
def _answering_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib callback
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _unused_loopback_uri() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}/"


def _fake_tool(path: Path, *, exit_code: int = 0) -> Path:
    """호출된 사실을 남기고 정해진 코드로 끝나는 가짜 실행 파일."""
    path.write_text(
        "@echo off\r\n"
        'echo %~n0 %* >> "%FAKE_LAUNCH_LOG%"\r\n'
        f"exit /b {exit_code}\r\n",
        encoding="ascii",
    )
    return path


def _fake_owner_ready(path: Path, *, exit_code: int = 0) -> Path:
    path.write_text(
        "param([string]$Mode, [switch]$Json, [int]$TimeoutSec)\n"
        'Add-Content -LiteralPath $env:FAKE_LAUNCH_LOG -Value "owner-ready $Mode"\n'
        f"exit {exit_code}\n",
        encoding="utf-8-sig",
    )
    return path


def _run(tmp_path: Path, *, uri: str, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    log = tmp_path / "launch.log"
    log.touch()
    command = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(LAUNCHER),
        "-Json",
        "-VideoBoxUri", uri,
        "-TimeoutSec", "5",
    ]
    command.extend(extra or [])
    return subprocess.run(
        command,
        cwd=str(ROOT),
        env={**os.environ, "FAKE_LAUNCH_LOG": str(log)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def _wait_for_log(log: Path, *, seconds: float = 15) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            return text
        time.sleep(0.2)
    return log.read_text(encoding="utf-8", errors="replace")


def _payload(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def _step(payload: dict, step_id: str) -> dict | None:
    return next((step for step in payload["steps"] if step["id"] == step_id), None)


def test_launcher_and_shortcut_scripts_carry_a_utf8_bom() -> None:
    # Windows PowerShell 5.1은 BOM이 없으면 파일을 ANSI로 읽는다. owner에게 보이는
    # 안내가 전부 깨진 글자로 나가고, 그건 막힌 지점을 못 읽는다는 뜻이다.
    for script in (LAUNCHER, SHORTCUT_SCRIPT):
        assert script.read_bytes()[:3] == b"\xef\xbb\xbf", script.name


def _without_comments(script: Path) -> str:
    """주석을 걷어낸 본문. 주석에 적힌 낱말을 호출로 오해하지 않기 위해서다."""
    text = re.sub(r"<#.*?#>", "", script.read_text(encoding="utf-8-sig"), flags=re.DOTALL)
    return "\n".join(re.sub(r"(?<!`)#.*$", "", line) for line in text.splitlines())


def test_launcher_never_drives_containers_itself() -> None:
    # `CLAUDE.md` §3: 컨테이너 스택은 `owner-ready.ps1`로만 다룬다. 여기서 직접 몰면
    # 시작 방법이 두 벌이 되고, 그중 하나가 조용히 낡는다.
    body = _without_comments(LAUNCHER)
    assert "compose" not in body
    assert "owner-ready.ps1" in body


def test_what_if_plans_without_starting_anything(tmp_path: Path) -> None:
    result = _run(tmp_path, uri=_unused_loopback_uri(), extra=["-WhatIf"])

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["overall"] == "ready"
    assert _step(payload, "plan")["evidence"]["what_if"] is True
    assert _step(payload, "start") is None


def test_an_already_running_videobox_is_not_started_again(tmp_path: Path) -> None:
    log = tmp_path / "launch.log"
    log.touch()
    owner_ready = _fake_owner_ready(tmp_path / "owner-ready.ps1")
    docker = _fake_tool(tmp_path / "docker.cmd", exit_code=1)

    with _answering_server() as uri:
        result = _run(tmp_path, uri=uri, extra=[
            "-SkipBrowser",
            "-OwnerReadyScript", str(owner_ready),
            "-DockerExecutable", str(docker),
        ])

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    assert payload["overall"] == "ready"
    assert _step(payload, "already_running")["status"] == "pass"
    # 두 번 눌러도 두 번 켜지지 않는다. 이미 응답하면 시작도 실행 환경 확인도 건너뛴다.
    assert _step(payload, "start") is None
    assert "owner-ready" not in log.read_text(encoding="utf-8", errors="replace")


def test_a_missing_owner_ready_script_blocks_instead_of_guessing(tmp_path: Path) -> None:
    result = _run(tmp_path, uri=_unused_loopback_uri(), extra=[
        "-SkipBrowser",
        "-OwnerReadyScript", str(tmp_path / "does-not-exist.ps1"),
    ])

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["overall"] == "blocked"
    assert _step(payload, "owner_ready")["status"] == "fail"


def test_a_failed_start_is_reported_as_blocked_not_ready(tmp_path: Path) -> None:
    owner_ready = _fake_owner_ready(tmp_path / "owner-ready.ps1", exit_code=3)
    docker = _fake_tool(tmp_path / "docker.cmd")

    result = _run(tmp_path, uri=_unused_loopback_uri(), extra=[
        "-SkipBrowser",
        "-OwnerReadyScript", str(owner_ready),
        "-DockerExecutable", str(docker),
    ])

    payload = _payload(result)
    assert result.returncode == 2
    assert payload["overall"] == "blocked"
    assert _step(payload, "start")["status"] == "fail"
    # 안 켜졌는데 브라우저를 여는 것이 가장 나쁘다 -- "연결할 수 없음"만 보여 준다.
    assert _step(payload, "open") is None


def test_a_started_stack_that_never_answers_does_not_open_a_dead_window(tmp_path: Path) -> None:
    owner_ready = _fake_owner_ready(tmp_path / "owner-ready.ps1")
    docker = _fake_tool(tmp_path / "docker.cmd")

    result = _run(tmp_path, uri=_unused_loopback_uri(), extra=[
        "-SkipBrowser",
        "-OwnerReadyScript", str(owner_ready),
        "-DockerExecutable", str(docker),
    ])

    payload = _payload(result)
    assert result.returncode == 2
    assert _step(payload, "start")["status"] == "pass"
    assert _step(payload, "ready")["status"] == "fail"
    assert _step(payload, "open") is None


def test_the_screen_opens_as_an_app_window_not_a_browser_tab(tmp_path: Path) -> None:
    log = tmp_path / "launch.log"
    log.touch()
    browser = _fake_tool(tmp_path / "browser.cmd")

    with _answering_server() as uri:
        result = _run(tmp_path, uri=uri, extra=["-BrowserExecutable", str(browser)])

    payload = _payload(result)
    assert result.returncode == 0, result.stderr
    opened = _step(payload, "open")
    assert opened["status"] == "pass"
    # 주소창과 탭이 있는 창은 "프로그램"으로 안 보인다 -- 첫 사용 점검에서 owner가
    # "웹페이지 한 장 같다"고 한 지점이다. `--app=`이 그 껍데기를 없앤다.
    assert opened["evidence"]["window"] == "app"
    # 창을 띄우고 기다리지 않는 것이 맞다 -- 켜는 창이 브라우저가 닫힐 때까지
    # 살아 있으면 안 된다. 그래서 기록이 남을 때까지 여기서 기다린다.
    assert f"--app={uri}" in _wait_for_log(log)


def test_the_desktop_icon_points_at_the_launcher() -> None:
    assert CMD.exists()
    text = CMD.read_text(encoding="utf-8", errors="replace")
    assert "Start-VideoBox.ps1" in text


def test_the_shortcut_installer_targets_the_desktop_without_creating_it(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SHORTCUT_SCRIPT),
            "-Json", "-WhatIf",
            "-ShortcutDirectory", str(tmp_path),
        ],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["status"] == "pass"
    assert payload["evidence"]["created"] is False
    assert payload["target"] == str(CMD)
    assert not any(tmp_path.glob("*.lnk"))


def test_the_shortcut_installer_creates_a_working_shortcut(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SHORTCUT_SCRIPT),
            "-Json",
            "-ShortcutDirectory", str(tmp_path),
        ],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    shortcut = tmp_path / "VideoBox.lnk"
    assert shortcut.exists()
    assert payload["evidence"]["created"] is True
    target = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "(New-Object -ComObject WScript.Shell).CreateShortcut("
            f"'{shortcut}').TargetPath",
        ],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert target.stdout.strip() == str(CMD)


def _voice_step(result: subprocess.CompletedProcess[str]) -> dict:
    payload = json.loads(result.stdout[result.stdout.index("{"):])
    return next((step for step in payload["steps"] if step["id"] == "voice"), {})


def test_the_icon_also_starts_the_voice_program(tmp_path: Path) -> None:
    """아이콘 하나로 켜는 것에 **내 목소리 더빙**도 포함된다(owner 요청 2026-09-03).

    안 켜면 창작자는 더빙을 누른 뒤에야 "켜 주세요"를 보고, 그제서야 다른
    창을 찾아 켜야 한다.
    """
    with _answering_server() as uri:
        result = _run(tmp_path, uri=uri, extra=[
            "-SkipBrowser", "-VoiceTimeoutSec", "0",
            "-VoiceUri", "http://127.0.0.1:9/health",
        ])

    assert result.returncode == 0, result.stderr
    assert _voice_step(result), "목소리 단계가 아예 없다"


def test_a_missing_voice_program_does_not_block_videobox(tmp_path: Path) -> None:
    """**목소리가 없어도 VideoBox는 켠다.**

    자막·편집·완성본은 목소리 없이도 다 된다. 그것 하나 때문에 아이콘이
    아무것도 안 켜 주면 훨씬 나쁘다.
    """
    with _answering_server() as uri:
        # 아무도 안 듣는 주소를 준다. 안 그러면 **이 기계에 진짜로 켜져 있는**
        # 목소리 프로그램을 찾아서 "이미 켜져 있다"로 새어 나간다.
        result = _run(tmp_path, uri=uri, extra=[
            "-SkipBrowser",
            "-VoiceScript", str(tmp_path / "없는파일.ps1"),
            "-VoiceUri", "http://127.0.0.1:9/health",
        ])

    payload = json.loads(result.stdout[result.stdout.index("{"):])
    assert payload["overall"] == "ready", payload
    assert _voice_step(result)["status"] == "skipped"


def test_the_launcher_parses_under_windows_powershell_5(tmp_path: Path) -> None:
    """**아이콘은 Windows PowerShell 5.1로 켜진다.** 거기서 못 읽는 문법을 쓰면 안 된다.

    5.1에는 `?.`(null-conditional)나 `??` 같은 PowerShell 7 문법이 없다. 하나만
    써도 **파일 전체가 파싱 단계에서 죽어** 스크립트가 한 줄도 안 돈다. 실제로
    한 번 그렇게 됐는데, 다른 시험들은 "출력이 비었다"로만 나와서 원인을
    안 짚어 줬다. 그래서 파싱만 따로 본다 -- 실패하면 원인이 이름에 적혀 있다.
    """
    for script in (LAUNCHER, SHORTCUT_SCRIPT):
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                "$e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile("
                f"'{script}', [ref]$null, [ref]$e); "
                "if ($e.Count) { $e | ForEach-Object { $_.Message }; exit 1 }",
            ],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        assert result.returncode == 0, f"{script.name}: {result.stdout}{result.stderr}"


def test_a_voice_program_that_cannot_be_started_does_not_block_videobox(tmp_path: Path) -> None:
    """**켜다 실패해도 아이콘은 VideoBox를 켠다.**

    이 스크립트는 `ErrorActionPreference = Stop`이라, 목소리 켜는 줄을 감싸지
    않으면 거기서 난 오류가 **아이콘 전체를 죽인다** -- 화면도 안 열린다.
    실패를 만들려고 실행 파일 이름을 없는 것으로 준다.
    """
    voice_script = tmp_path / "목소리.ps1"
    voice_script.write_text("exit 0", encoding="utf-8-sig")

    with _answering_server() as uri:
        result = _run(tmp_path, uri=uri, extra=[
            "-SkipBrowser",
            "-VoiceScript", str(voice_script),
            "-VoiceUri", "http://127.0.0.1:9/health",
            "-VoiceHostExecutable", "이런실행파일은없다.exe",
        ])

    payload = json.loads(result.stdout[result.stdout.index("{"):])
    assert payload["overall"] == "ready", payload
    assert _voice_step(result)["status"] == "skipped", payload


def test_the_voice_program_is_not_started_twice(tmp_path: Path) -> None:
    """이미 켜져 있으면 또 켜지 않는다 -- 두 번 켜면 같은 포트를 다투다 죽는다."""
    with _answering_server() as uri:
        # 목소리 확인 주소를 살아 있는 주소로 준다 = 이미 켜져 있는 상황.
        result = _run(tmp_path, uri=uri, extra=["-SkipBrowser", "-VoiceUri", uri])

    step = _voice_step(result)
    assert step["status"] == "pass"
    assert step["evidence"]["started_by_us"] is False


def test_the_voice_program_can_be_skipped(tmp_path: Path) -> None:
    with _answering_server() as uri:
        result = _run(tmp_path, uri=uri, extra=["-SkipBrowser", "-SkipVoice"])

    assert _voice_step(result)["status"] == "skipped"
