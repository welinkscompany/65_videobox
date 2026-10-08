"""설명 모션(막대 비교·금액 카운터·단계 목록)을 **이 컴퓨터의 하이퍼프레임**으로 그려 영상으로 내는 다리.

컨테이너 안에는 node도, 헤드리스 브라우저도 없다. 그래서 목소리(8199)·캡컷(8200)·그림(8201)과
같은 방식으로 작은 서비스를 둔다. 모션은 **8202**다.

    pwsh -File scripts/start-motion.ps1

## 하는 일은 둘뿐이다

    GET  /diagnostics  준비가 됐는지, 안 됐다면 무엇이 모자란지
    POST /render       템플릿 이름·변수·길이·모양을 받아 영상(mp4 또는 webm)을 그린다

## 템플릿만 돈다

모델이 쓴 HTML·JS·CSS를 받는 자리는 없다. 저장소에 들어 있는 템플릿(`scripts/motion-bridge/templates`)을
빈 임시 폴더로 복사하고, 검증된 JSON만 `data.js`로 적고, 길이·모양 자리표시자 둘만 바꾼다.
렌더는 죽은 프록시 + 텔레메트리 끔으로 부르고, 네트워크를 언급한 줄이 있으면 세어서 알린다.

## 한 번에 하나, 시간 상한

렌더 하나가 CPU와 크롬을 오래 쓴다. 잠금으로 한 번에 하나만 돌리고(바쁘면 409),
180초를 넘으면 자식(크롬)까지 끊는다. 렌더 요청 안에서는 브라우저를 받지 않는다 --
준비 전이면 503으로 말한다(`prepare-motion.ps1`이 따로 준비한다).

## 결과는 내용으로 돌려준다

영상은 base64로 돌려주고 이 컴퓨터에 남기지 않는다(임시 폴더에 그리고, 읽고, 지운다).
요청은 `scripts/host_bridge_guard.py`가 먼저 본다(Host·토큰·JSON). 읽기도 토큰이 필요하다.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bridge_guard import BridgeTokenMissing, check_request, load_bridge_token  # noqa: E402

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_BRIDGE_ROOT = _REPOSITORY_ROOT / "scripts" / "motion-bridge"

DEFAULT_PORT = 8202
BIND_HOST = "127.0.0.1"
RENDER_TIMEOUT_SECONDS = 180
MAXIMUM_VIDEO_BYTES = 64 * 1024 * 1024
MAXIMUM_VARIABLES_BYTES = 16384
TEMPLATE_KEYS = ("bar_compare", "money_counter", "step_list")
MIN_DURATION_SEC = 3.0
MAX_DURATION_SEC = 30.0
LAYOUT_FORMATS = {"full": "mp4", "overlay": "webm"}
PINNED_ENGINE_VERSION = "0.8.140"
FPS = 30
_MAXIMUM_DEPTH = 3

_RENDER_LOCK = threading.Lock()
_NETWORK_MENTION = re.compile(r"(?i)\bcdn\b|googleapis|jsdelivr|unpkg|https://")

_RECOVERY = {
    "node_not_found": "node를 찾지 못했습니다. Node.js 24를 설치한 뒤 VideoBox를 다시 켜세요.",
    "ffmpeg_not_found": "ffmpeg를 찾지 못했습니다. ffmpeg를 설치한 뒤 VideoBox를 다시 켜세요.",
    "engine_not_installed": "모션 도구를 처음 한 번 준비해야 합니다. PowerShell에서 .\\scripts\\prepare-motion.ps1 을 실행하거나 VideoBox를 다시 켜세요(약 400MB, 몇 분).",
    "browser_not_prepared": "모션 도구를 처음 한 번 준비해야 합니다. PowerShell에서 .\\scripts\\prepare-motion.ps1 을 실행하거나 VideoBox를 다시 켜세요(약 400MB, 몇 분).",
}


@dataclass(frozen=True)
class BridgeSettings:
    node: Path | None
    ffmpeg: Path | None
    engine_root: Path
    templates_root: Path
    font_path: Path
    work_root: Path
    cache_root: Path

    @property
    def hyperframes_bin(self) -> Path:
        return self.engine_root / "bin" / "hyperframes.mjs"

    @classmethod
    def discover(cls, *, node: str | None = None, work_root: Path | None = None) -> BridgeSettings:
        found_node = shutil.which("node")
        found_ffmpeg = shutil.which("ffmpeg")
        return cls(
            node=Path(node) if node else (Path(found_node) if found_node else None),
            ffmpeg=Path(found_ffmpeg) if found_ffmpeg else None,
            engine_root=_BRIDGE_ROOT / "node_modules" / "hyperframes",
            templates_root=_BRIDGE_ROOT / "templates",
            font_path=_REPOSITORY_ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf",
            work_root=work_root or Path(tempfile.gettempdir()) / "videobox-motion",
            cache_root=Path.home() / ".cache" / "hyperframes",
        )


@dataclass(frozen=True)
class RenderOrder:
    template: str
    variables: dict
    duration_sec: float
    layout: str


@dataclass(frozen=True)
class RenderedMotion:
    path: Path
    network_mentions: int


def find_browser_executable(cache_root: Path) -> Path | None:
    found = sorted((cache_root / "chrome" / "chrome-headless-shell").glob("*/chrome-headless-shell-win64/chrome-headless-shell.exe"))
    return found[-1] if found else None


def _engine_version(settings: BridgeSettings) -> str | None:
    try:
        data = json.loads((settings.engine_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def readiness(settings: BridgeSettings) -> str:
    if settings.node is None or not settings.node.is_file():
        return "node_not_found"
    if settings.ffmpeg is None or not settings.ffmpeg.is_file():
        return "ffmpeg_not_found"
    if _engine_version(settings) != PINNED_ENGINE_VERSION or not settings.hyperframes_bin.is_file():
        return "engine_not_installed"
    if find_browser_executable(settings.cache_root) is None:
        return "browser_not_prepared"
    return "ready"


def diagnostics_payload(*, settings: BridgeSettings | None) -> tuple[int, dict]:
    if settings is None:
        return 200, {
            "status": "engine_not_installed",
            "node_path": None,
            "engine_version": None,
            "browser_path": None,
            "recovery_message": _RECOVERY["engine_not_installed"],
        }
    status = readiness(settings)
    browser = find_browser_executable(settings.cache_root)
    return 200, {
        "status": status,
        "node_path": str(settings.node) if settings.node else None,
        "engine_version": _engine_version(settings),
        "browser_path": str(browser) if browser else None,
        "recovery_message": _RECOVERY.get(status),
    }


def _inspect(value: object, depth: int) -> str | None:
    """오류 이름 하나 또는 `None`. 맨 위 변수 dict가 깊이 1이다."""
    if isinstance(value, dict):
        if depth > _MAXIMUM_DEPTH:
            return "variables_too_deep"
        for key, item in value.items():
            problem = _inspect(key, depth) or _inspect(item, depth + 1)
            if problem:
                return problem
        return None
    if isinstance(value, list):
        if depth > _MAXIMUM_DEPTH:
            return "variables_too_deep"
        for item in value:
            problem = _inspect(item, depth + 1)
            if problem:
                return problem
        return None
    if isinstance(value, str):
        for char in value:
            if char in "<>" or ord(char) < 32 or ord(char) == 127:
                return "text_not_allowed"
        return None
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return None
    if isinstance(value, float):
        return None if math.isfinite(value) else "number_not_allowed"
    return "text_not_allowed"


def check_render_request(body: dict) -> RenderOrder | tuple[int, dict]:
    template = body.get("template")
    if template not in TEMPLATE_KEYS:
        return 400, {"error": "unknown_template"}
    layout = body.get("layout") or "full"
    if layout not in LAYOUT_FORMATS:
        return 400, {"error": "unknown_layout"}
    try:
        duration = float(body.get("duration_sec"))
    except (TypeError, ValueError):
        return 400, {"error": "duration_must_be_a_number"}
    if not math.isfinite(duration) or not (MIN_DURATION_SEC <= duration <= MAX_DURATION_SEC):
        return 400, {"error": "duration_out_of_range"}
    variables = body.get("variables")
    if not isinstance(variables, dict):
        return 400, {"error": "variables_must_be_an_object"}
    try:
        encoded = json.dumps(variables, ensure_ascii=False, allow_nan=True).encode("utf-8")
    except (TypeError, ValueError):
        return 400, {"error": "text_not_allowed"}
    if len(encoded) > MAXIMUM_VARIABLES_BYTES:
        return 400, {"error": "variables_too_large"}
    problem = _inspect(variables, 1)
    if problem:
        return 400, {"error": problem}
    return RenderOrder(template, variables, round(duration, 3), layout)


def motion_data_script(order: RenderOrder) -> str:
    """`data.js` 한 줄. ensure_ascii로 한글·U+2028까지 \\u로 바꾸고, 마크업 글자 셋도 바꾼다 --
    다리가 이미 `<`·`>`를 거절하지만 여기서 한 번 더 닫는다(2차 방어)."""
    payload = {"variables": order.variables, "duration": order.duration_sec, "mode": order.layout}
    encoded = (
        json.dumps(payload, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f"window.__VB_MOTION__ = {encoded};\n"


def _duration_text(seconds: float) -> str:
    return f"{seconds:.3f}".rstrip("0").rstrip(".")


def prepare_composition(*, settings: BridgeSettings, order: RenderOrder, scratch: Path) -> Path:
    scratch.mkdir(parents=True, exist_ok=True)
    comp = scratch / "comp"
    shutil.copytree(settings.templates_root / order.template, comp)
    shutil.copyfile(settings.templates_root / "_shared" / "motion-runtime.js", comp / "motion-runtime.js")
    (comp / "assets").mkdir(exist_ok=True)
    shutil.copyfile(settings.font_path, comp / "assets" / "NotoSansKR-Variable.ttf")
    page_path = comp / "index.html"
    page = page_path.read_text(encoding="utf-8")
    page = page.replace("__VB_DURATION__", _duration_text(order.duration_sec)).replace("__VB_MODE__", order.layout)
    if "__VB_" in page:
        raise RuntimeError("template_placeholder_left")
    page_path.write_text(page, encoding="utf-8")
    (comp / "data.js").write_text(motion_data_script(order), encoding="utf-8")
    return comp


def engine_environment(base: Mapping[str, str], *, browser: Path) -> dict[str, str]:
    env = dict(base)
    env.pop("VIDEOBOX_BRIDGE_TOKEN", None)
    env.update(
        {
            "HYPERFRAMES_NO_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "HYPERFRAMES_SKIP_SKILLS": "1",
            "HYPERFRAMES_NO_UPDATE_CHECK": "1",
            "HYPERFRAMES_NO_AUTO_INSTALL": "1",
            "NODE_USE_ENV_PROXY": "1",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
            "HYPERFRAMES_BROWSER_PATH": str(browser),
        }
    )
    return env


def confine_to_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("outside_work_root")
    return resolved


def _kill_tree(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.kill(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass


def run_bounded(arguments, *, timeout, env, cwd, popen=subprocess.Popen, killer=None) -> subprocess.CompletedProcess:
    process = popen(
        arguments,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        (killer or _kill_tree)(process.pid)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def render_motion(*, settings: BridgeSettings, order: RenderOrder, scratch: Path, runner=run_bounded) -> RenderedMotion:
    comp = prepare_composition(settings=settings, order=order, scratch=scratch)
    fmt = LAYOUT_FORMATS[order.layout]
    out = confine_to_root(scratch / f"out.{fmt}", settings.work_root)
    browser = find_browser_executable(settings.cache_root)
    if browser is None:
        raise RuntimeError("browser_not_prepared")
    arguments = [
        str(settings.node), str(settings.hyperframes_bin), "render", str(comp),
        "-o", str(out), "--format", fmt, "--fps", str(FPS),
        "--frames-cache-dir", str(scratch / "frames"),
    ]
    completed = runner(arguments, timeout=RENDER_TIMEOUT_SECONDS, env=engine_environment(os.environ, browser=browser), cwd=scratch)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        tail = (stderr.strip() or stdout.strip())[-400:]
        raise RuntimeError(f"engine_failed: {tail}")
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("engine_wrote_nothing")
    mentions = sum(1 for line in (stdout + "\n" + stderr).splitlines() if _NETWORK_MENTION.search(line))
    if mentions > 0:
        print(f"[motion-bridge] 경고: 바깥 주소를 언급한 줄 {mentions}개", file=sys.stderr, flush=True)
    return RenderedMotion(out, mentions)


def render_request_payload(body: dict, *, settings: BridgeSettings | None, renderer=render_motion, lock=_RENDER_LOCK) -> tuple[int, dict]:
    if settings is None:
        return 503, {"error": "motion_engine_not_prepared"}
    checked = check_render_request(body)
    if isinstance(checked, tuple):
        return checked
    state = readiness(settings)
    if state != "ready":
        return 503, {"error": "motion_engine_not_prepared", "detail": state}
    if not lock.acquire(blocking=False):
        return 409, {"error": "motion_render_busy"}
    try:
        settings.work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="render-", dir=settings.work_root, ignore_cleanup_errors=True) as directory:
            started = time.monotonic()
            try:
                rendered = renderer(settings=settings, order=checked, scratch=Path(directory))
                video = rendered.path.read_bytes()
            except subprocess.TimeoutExpired:
                return 504, {"error": "render_timed_out"}
            except (RuntimeError, OSError, ValueError) as exc:
                return 500, {"error": "render_failed", "detail": str(exc)}
            elapsed = round(time.monotonic() - started, 2)
    finally:
        lock.release()
    if len(video) > MAXIMUM_VIDEO_BYTES:
        return 500, {"error": "render_too_large", "detail": str(len(video))}
    return 200, {
        "video_base64": base64.b64encode(video).decode("ascii"),
        "format": LAYOUT_FORMATS[checked.layout],
        "byte_size": len(video),
        "width": 1920,
        "height": 1080,
        "duration_sec": checked.duration_sec,
        "elapsed_sec": elapsed,
        "network_mentions": rendered.network_mentions,
    }


SAMPLE_VARIABLES = {
    "bar_compare": {"title": "월 수익 비교: 쿠팡 vs 스마트스토어", "subtitle": "2026년 9월 · 단위 만 원 · 예시", "unit": "만", "bars": [{"label": "쿠팡 로켓그로스", "value": 1280}, {"label": "스마트스토어", "value": 860}, {"label": "자사몰", "value": 430}]},
    "money_counter": {"lead": "첫 달 순매출", "amount": 12345678, "prefix": "₩", "suffix": "", "caption": "광고비 · 수수료 제외 후"},
    "step_list": {"title": "처음 시작하는 3단계", "steps": ["상품 소싱하고 가격 정하기", "상세페이지 올리기", "첫 주문 처리하고 정산받기"]},
}
LONGEST_VARIABLES = {
    "bar_compare": {"title": "가" * 24, "subtitle": "나" * 40, "unit": "만원까지", "bars": [{"label": "다" * 10, "value": 1_000_000_000_000}] + [{"label": "라" * 10, "value": 999_999_999_999.9}] * 4},
    "money_counter": {"lead": "마" * 20, "amount": 1_000_000_000_000, "prefix": "₩", "suffix": "원까지요", "caption": "바" * 30},
    "step_list": {"title": "사" * 24, "steps": ["아" * 24] * 5},
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "VideoBoxMotionBridge/1.0"
    settings: BridgeSettings | None = None
    bridge_token: str = ""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write("[motion-bridge] " + (format % args) + "\n")

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        decoded = json.loads(self.rfile.read(length).decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {}

    def _refused(self) -> bool:
        refusal = check_request(
            method=self.command,
            headers=self.headers,
            port=self.server.server_address[1],
            expected_token=self.bridge_token,
        )
        if refusal is None:
            return False
        self._reply(*refusal)
        return True

    def do_GET(self) -> None:  # noqa: N802
        if self._refused():
            return
        if self.path != "/diagnostics":
            self._reply(404, {"error": "unknown_path"})
            return
        self._reply(*diagnostics_payload(settings=self.settings))

    def do_POST(self) -> None:  # noqa: N802
        if self._refused():
            return
        if self.path != "/render":
            self._reply(404, {"error": "unknown_path"})
            return
        try:
            payload = self._payload()
        except (ValueError, OSError):
            self._reply(400, {"error": "unreadable_request"})
            return
        self._reply(*render_request_payload(payload, settings=self.settings))


def build_server(*, port: int, settings: BridgeSettings | None, bridge_token: str) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"settings": settings, "bridge_token": bridge_token})
    return ThreadingHTTPServer((BIND_HOST, port), handler)


def _render_sample(arguments: argparse.Namespace, settings: BridgeSettings) -> int:
    state = readiness(settings)
    if state != "ready":
        print(json.dumps(diagnostics_payload(settings=settings)[1], ensure_ascii=False), flush=True)
        return 3
    key = arguments.render_sample
    variables = (LONGEST_VARIABLES if arguments.longest else SAMPLE_VARIABLES)[key]
    checked = check_render_request(
        {"template": key, "variables": variables, "duration_sec": arguments.duration, "layout": arguments.layout}
    )
    if isinstance(checked, tuple):
        print(json.dumps(checked[1], ensure_ascii=False), flush=True)
        return 4
    settings.work_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sample-", dir=settings.work_root, ignore_cleanup_errors=True) as directory:
        rendered = render_motion(settings=settings, order=checked, scratch=Path(directory))
        elapsed = round(time.monotonic() - started, 2)
        out = Path(arguments.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rendered.path, out)
        size = out.stat().st_size
    print(
        json.dumps(
            {
                "template": key, "layout": checked.layout, "duration_sec": checked.duration_sec,
                "elapsed_sec": elapsed, "byte_size": size,
                "network_mentions": rendered.network_mentions, "out": str(out),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VideoBox motion render bridge (host side).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VIDEOBOX_MOTION_BRIDGE_PORT") or DEFAULT_PORT))
    parser.add_argument("--node", default=None, help="node 실행 파일 경로.")
    parser.add_argument("--work-root", default=None, help="임시 렌더 폴더의 뿌리.")
    parser.add_argument("--render-sample", choices=TEMPLATE_KEYS, default=None, help="서버 없이 표본 하나를 그린다(측정용).")
    parser.add_argument("--layout", choices=tuple(LAYOUT_FORMATS), default="full")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--longest", action="store_true")
    parser.add_argument("--out", default=None)
    arguments = parser.parse_args(argv)
    settings = BridgeSettings.discover(node=arguments.node, work_root=Path(arguments.work_root) if arguments.work_root else None)
    if arguments.render_sample:
        if not arguments.out:
            parser.error("--render-sample에는 --out이 필요합니다.")
        return _render_sample(arguments, settings)
    try:
        token = load_bridge_token(os.environ, _REPOSITORY_ROOT / ".env.container")
    except BridgeTokenMissing as exc:
        print(f"[motion-bridge] {exc}", file=sys.stderr, flush=True)
        return 2
    server = build_server(port=arguments.port, settings=settings, bridge_token=token)
    print(f"[motion-bridge] listening on http://{BIND_HOST}:{arguments.port}", flush=True)
    print(f"[motion-bridge] node: {settings.node or '(못 찾음)'}", flush=True)
    print(f"[motion-bridge] 준비 상태: {readiness(settings)}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
