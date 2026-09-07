"""HTML 한 장을 **이 컴퓨터의 크롬**으로 그려 PNG로 내는 다리.

컨테이너 안에는 브라우저가 없다(`docker/api.Dockerfile`에 크로미움이 없고, 넣으면
이미지가 수백 MB 무거워진다). 그런데 이 컴퓨터에는 크롬이 **이미 깔려 있다.**
그래서 목소리(8199)·캡컷(8200)과 같은 방식으로 작은 서비스를 둔다.
인포그래픽은 **8201**이다.

    pwsh -File scripts/start-infographic.ps1

## 하는 일은 셋뿐이다

    GET  /diagnostics  브라우저를 찾았는지, 어디서 찾았는지
    POST /render       HTML을 받아 PNG를 그린다
    POST /measure      HTML을 올려 놓고 **다 놓인 뒤의 DOM**을 찍어 돌려준다

`/measure`가 있는 것은, 글자가 판을 넘었는지·겹쳤는지를 **그림으로는 못 재기**
때문이다. 픽셀만 보면 잘린 내용은 애초에 안 그려져 있어 안 보인다. 브라우저
안에서 자리를 재고 그 값을 `<title>`에 적어 두면 `--dump-dom`으로 그대로 읽힌다
(`infographic_layout_audit`).

## 왜 Playwright가 아닌가

`--headless --screenshot`이면 끝난다(실측 0.6초). Playwright는 크로미움을 **또**
받아 오는데(약 150MB), 있는 크롬으로 되는 일에 그걸 지고 올 이유가 없다.

## 그림은 **내용으로** 돌려준다 (캡컷 다리와 다른 점)

캡컷 다리는 호스트 경로를 받아 그 폴더를 다룬다. 여기는 그럴 이유가 없다 --
PNG 한 장은 크지 않아서 base64로 실어 보내면 그만이다. 그래서 이 서비스는
**이 컴퓨터에 아무것도 남기지 않는다.** 임시 폴더에 그리고, 읽고, 지운다.
받아 줄 폴더도 경로 대응표도 필요 없다. 목소리 다리(8199)와 같은 방식이다.

## HTML은 인터넷에 못 나간다

크롬에 `--disable-network`는 없다. 대신 프로필을 빈 임시 폴더로 격리하고 이름
풀이를 통째로 막는다(`--host-resolver-rules`). 1차 방어는 그리기 전 검사
(`infographic_brief.check_infographic_html`)이고 여기는 2차다.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 8201
#: 이 컴퓨터 밖으로는 열지 않는다.
BIND_HOST = "127.0.0.1"
#: 한 장 그리는 데 이보다 오래 걸리면 뭔가 잘못된 것이다(실측 0.6초).
RENDER_TIMEOUT_SECONDS = 60
#: 그림 한 장의 크기 한계. 1920x1080 PNG는 보통 40KB~2MB다.
MAXIMUM_PNG_BYTES = 32 * 1024 * 1024

#: 찾는 차례. 크롬이 먼저인 것은 이 컴퓨터에 있는 것이 크롬이기 때문이고,
#: 엣지를 남겨 둔 것은 윈도우라면 거의 언제나 있기 때문이다.
_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def find_browser(explicit: str | None = None) -> Path | None:
    """그림을 그릴 브라우저. 못 찾으면 `None` -- 조용히 딴것으로 대신하지 않는다."""

    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    for raw in _BROWSER_CANDIDATES:
        candidate = Path(raw)
        if candidate.is_file():
            return candidate
    for name in ("chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def render_png(
    *,
    html: str,
    width: int,
    height: int,
    browser: Path,
    runner=subprocess.run,
) -> bytes:
    """HTML을 PNG 바이트로.

    **임시 파일에 쓰고 부른다** -- `data:` 주소로 넘기면 윈도우 명령줄 길이
    제한(32767자)에 걸린다. 인포그래픽 HTML은 그걸 쉽게 넘는다.

    실패하면 예외를 던진다. 빈 그림을 돌려주고 성공했다고 하지 않는다.
    """

    with tempfile.TemporaryDirectory(prefix="videobox-infographic-") as scratch:
        page = Path(scratch) / "page.html"
        page.write_text(html, encoding="utf-8")
        output_path = Path(scratch) / "out.png"
        profile = Path(scratch) / "profile"
        arguments = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            # 이 컴퓨터의 크롬 프로필(로그인·쿠키·확장)을 건드리지 않는다.
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            # 2차 방어: 그리는 동안 바깥으로 못 나간다.
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost",
            f"--window-size={width},{height}",
            f"--screenshot={output_path}",
            page.as_uri(),
        ]
        completed = runner(
            arguments,
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-400:]
            raise RuntimeError(f"browser_failed: {detail}")
        # 크롬은 그림을 못 그려도 0으로 끝나는 일이 있다. **파일을 보고 판단한다.**
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("browser_wrote_nothing")
        return output_path.read_bytes()


def dump_dom(
    *,
    html: str,
    width: int,
    height: int,
    browser: Path,
    runner=subprocess.run,
) -> str:
    """페이지를 올려 놓고 **다 놓인 뒤의 DOM**을 글로 받는다.

    `--virtual-time-budget`을 주는 것은 글꼴이 실리기를 기다려야 하기 때문이다 --
    대체 글꼴로 재면 폭이 달라져 없는 겹침이 생긴다.
    """

    with tempfile.TemporaryDirectory(prefix="videobox-infographic-") as scratch:
        page = Path(scratch) / "page.html"
        page.write_text(html, encoding="utf-8")
        profile = Path(scratch) / "profile"
        arguments = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost",
            f"--window-size={width},{height}",
            "--virtual-time-budget=3000",
            "--dump-dom",
            page.as_uri(),
        ]
        completed = runner(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RENDER_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()[-400:]
            raise RuntimeError(f"browser_failed: {detail}")
        return completed.stdout or ""


def diagnostics_payload(*, browser: Path | None) -> tuple[int, dict[str, object]]:
    """`GET /diagnostics`가 돌려줄 것. **소켓과 떼어 놓았다** -- 이 저장소의 시험은
    연결을 못 열게 막혀 있고(`tests/conftest.py`), 그 울타리는 옳다."""

    return 200, {
        "status": "ready" if browser else "browser_not_found",
        "browser_path": str(browser) if browser else None,
        "recovery_message": (
            None
            if browser
            else "크롬이나 엣지를 찾지 못했습니다. 크롬을 설치하거나 --browser로 경로를 주세요."
        ),
    }


def render_request_payload(
    body: dict[str, object],
    *,
    browser: Path | None,
    renderer=render_png,
) -> tuple[int, dict[str, object]]:
    """`POST /render`가 돌려줄 것."""

    if browser is None:
        return 503, {"error": "browser_not_found"}
    html = str(body.get("html") or "")
    if not html.strip():
        return 400, {"error": "html_is_required"}
    try:
        width = int(body.get("width") or 1920)
        height = int(body.get("height") or 1080)
    except (TypeError, ValueError):
        return 400, {"error": "width_and_height_must_be_numbers"}
    if not (16 <= width <= 8192 and 16 <= height <= 8192):
        return 400, {"error": "width_and_height_out_of_range"}
    try:
        png = renderer(html=html, width=width, height=height, browser=browser)
    except subprocess.TimeoutExpired:
        return 504, {"error": "render_timed_out"}
    except (RuntimeError, OSError) as exc:
        return 500, {"error": "render_failed", "detail": str(exc)}
    if len(png) > MAXIMUM_PNG_BYTES:
        return 500, {"error": "render_too_large", "detail": str(len(png))}
    return 200, {
        "png_base64": base64.b64encode(png).decode("ascii"),
        "byte_size": len(png),
        "width": width,
        "height": height,
    }


def measure_request_payload(
    body: dict[str, object],
    *,
    browser: Path | None,
    dumper=dump_dom,
) -> tuple[int, dict[str, object]]:
    """`POST /measure`가 돌려줄 것."""

    if browser is None:
        return 503, {"error": "browser_not_found"}
    html = str(body.get("html") or "")
    if not html.strip():
        return 400, {"error": "html_is_required"}
    try:
        width = int(body.get("width") or 1920)
        height = int(body.get("height") or 1080)
    except (TypeError, ValueError):
        return 400, {"error": "width_and_height_must_be_numbers"}
    if not (16 <= width <= 8192 and 16 <= height <= 8192):
        return 400, {"error": "width_and_height_out_of_range"}
    try:
        dumped = dumper(html=html, width=width, height=height, browser=browser)
    except subprocess.TimeoutExpired:
        return 504, {"error": "measure_timed_out"}
    except (RuntimeError, OSError) as exc:
        return 500, {"error": "measure_failed", "detail": str(exc)}
    # DOM 전체를 돌려주지 않는다 -- 재는 쪽이 필요로 하는 것은 `<title>` 한 줄이고,
    # 문서 전체는 컨테이너까지 실어 나를 이유가 없다.
    found = re.search(r"<title[^>]*>.*?</title>", dumped, re.IGNORECASE | re.DOTALL)
    return 200, {"title": found.group(0) if found else ""}


class _Handler(BaseHTTPRequestHandler):
    server_version = "VideoBoxInfographicBridge/1.0"
    browser: Path | None = None

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write("[infographic-bridge] " + (format % args) + "\n")

    def _reply(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        decoded = json.loads(self.rfile.read(length).decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/diagnostics":
            self._reply(404, {"error": "unknown_path"})
            return
        self._reply(*diagnostics_payload(browser=self.browser))

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/render", "/measure"):
            self._reply(404, {"error": "unknown_path"})
            return
        try:
            payload = self._payload()
        except (ValueError, OSError):
            self._reply(400, {"error": "unreadable_request"})
            return
        if self.path == "/render":
            self._reply(*render_request_payload(payload, browser=self.browser))
        else:
            self._reply(*measure_request_payload(payload, browser=self.browser))


def build_server(*, port: int, browser: Path | None) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"browser": browser})
    return ThreadingHTTPServer((BIND_HOST, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VideoBox infographic render bridge (host side).")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("VIDEOBOX_INFOGRAPHIC_BRIDGE_PORT") or DEFAULT_PORT),
    )
    parser.add_argument("--browser", default=None, help="크롬/엣지 실행 파일 경로.")
    arguments = parser.parse_args(argv)
    browser = find_browser(arguments.browser)
    server = build_server(port=arguments.port, browser=browser)
    print(f"[infographic-bridge] listening on http://{BIND_HOST}:{arguments.port}", flush=True)
    print(f"[infographic-bridge] browser: {browser or '(못 찾음)'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
