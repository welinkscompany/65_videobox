"""이 컴퓨터에서 도는 모션 다리 자체 (2026-10-08 결정 2단계).

부르는 쪽(`test_motion_host_bridge.py`)과 따로 잰다. **소켓도, node도 안 부른다** --
판단 함수(`*_payload`, `check_render_request`, `prepare_composition`)와 갈아 끼울 수 있는
`runner`·`renderer`로 잰다. 실물 렌더는 이 Task의 Step 9(손으로)와 Task 7(측정)이다.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PATH = ROOT / "scripts" / "host_motion_service.py"
_spec = importlib.util.spec_from_file_location("videobox_host_motion_service", _PATH)
assert _spec is not None and _spec.loader is not None
motion = importlib.util.module_from_spec(_spec)
# dataclass는 정의한 모듈을 sys.modules에서 찾는다(`test_host_bridge_guard._load`와 같은 이유).
sys.modules["videobox_host_motion_service"] = motion
_spec.loader.exec_module(motion)

BAR = {"title": "월 수익 비교", "subtitle": "", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "스마트스토어", "value": 860}]}


def _body(**overrides):
    body = {"template": "bar_compare", "variables": BAR, "duration_sec": 6, "layout": "full"}
    body.update(overrides)
    return body


@pytest.fixture()
def settings(tmp_path: Path):
    """준비가 끝난 컴퓨터를 흉내 낸다. 파일만 둔다 -- 실제로 띄우지 않는다."""
    node = tmp_path / "node.exe"
    node.write_bytes(b"node")
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"ffmpeg")
    engine = tmp_path / "bridge" / "node_modules" / "hyperframes"
    (engine / "bin").mkdir(parents=True)
    (engine / "bin" / "hyperframes.mjs").write_text("// fake", encoding="utf-8")
    (engine / "package.json").write_text(json.dumps({"name": "hyperframes", "version": "0.8.140"}), encoding="utf-8")
    chrome = tmp_path / "cache" / "chrome" / "chrome-headless-shell" / "win64-152.0.7977.30" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"chrome")
    return motion.BridgeSettings(
        node=node, ffmpeg=ffmpeg, engine_root=engine,
        templates_root=ROOT / "scripts" / "motion-bridge" / "templates",
        font_path=ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf",
        work_root=tmp_path / "work", cache_root=tmp_path / "cache",
    )


def _never(**kwargs):  # noqa: ANN003
    raise AssertionError("여기까지 오면 안 된다 -- 그리기 전에 막혀야 한다")


def _writes(content: bytes, *, mentions: int = 0):
    def renderer(*, settings, order, scratch):  # noqa: ANN001
        out = scratch / f"out.{motion.LAYOUT_FORMATS[order.layout]}"
        out.write_bytes(content)
        return motion.RenderedMotion(path=out, network_mentions=mentions)
    return renderer


# 1. 진단 -- 무엇이 모자란지 차례대로 정직하게 말한다

def test_diagnostics_say_ready_when_everything_is_in_place(settings) -> None:
    status, payload = motion.diagnostics_payload(settings=settings)
    assert status == 200
    assert payload["status"] == "ready"
    assert payload["engine_version"] == "0.8.140"
    assert payload["recovery_message"] is None


def test_readiness_names_the_first_missing_piece(settings) -> None:
    from dataclasses import replace

    assert motion.readiness(replace(settings, node=None)) == "node_not_found"
    assert motion.readiness(replace(settings, ffmpeg=None)) == "ffmpeg_not_found"
    (settings.engine_root / "package.json").write_text(json.dumps({"version": "0.8.139"}), encoding="utf-8")
    assert motion.readiness(settings) == "engine_not_installed"


def test_a_computer_without_the_browser_is_not_ready(settings, tmp_path: Path) -> None:
    from dataclasses import replace

    empty = replace(settings, cache_root=tmp_path / "empty-cache")
    assert motion.find_browser_executable(empty.cache_root) is None
    status, payload = motion.diagnostics_payload(settings=empty)
    assert payload["status"] == "browser_not_prepared"
    assert "prepare-motion.ps1" in payload["recovery_message"]


# 2. 요청 검사 -- 그리기 전에 막는다

@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"template": "free_form"}, "unknown_template"),
        ({"layout": "mov"}, "unknown_layout"),
        ({"duration_sec": "열 초"}, "duration_must_be_a_number"),
        ({"duration_sec": 2.9}, "duration_out_of_range"),
        ({"duration_sec": 30.1}, "duration_out_of_range"),
        ({"duration_sec": float("nan")}, "duration_out_of_range"),
        ({"variables": ["x"]}, "variables_must_be_an_object"),
        ({"variables": {"title": "x" * 20000}}, "variables_too_large"),
        ({"variables": {"a": {"b": {"c": {"d": 1}}}}}, "variables_too_deep"),
        ({"variables": {"title": "<script>alert(1)</script>"}}, "text_not_allowed"),
        ({"variables": {"bars": [{"label": "a\u0000b", "value": 1}]}}, "text_not_allowed"),
        ({"variables": {"amount": float("inf")}}, "number_not_allowed"),
    ],
)
def test_a_bad_request_is_refused_before_anything_runs(settings, overrides, error) -> None:
    status, payload = motion.render_request_payload(_body(**overrides), settings=settings, renderer=_never)
    assert (status, payload["error"]) == (400, error)


def test_an_unprepared_engine_is_said_before_rendering(settings, tmp_path: Path) -> None:
    from dataclasses import replace

    status, payload = motion.render_request_payload(
        _body(), settings=replace(settings, cache_root=tmp_path / "none"), renderer=_never
    )
    assert (status, payload) == (503, {"error": "motion_engine_not_prepared", "detail": "browser_not_prepared"})


def test_a_bridge_without_settings_says_not_prepared() -> None:
    status, payload = motion.render_request_payload(_body(), settings=None, renderer=_never)
    assert (status, payload["error"]) == (503, "motion_engine_not_prepared")


# 3. 한 번에 하나

def test_a_second_render_while_one_is_running_is_told_busy(settings) -> None:
    lock = threading.Lock()
    lock.acquire()
    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=_never, lock=lock)
    assert (status, payload) == (409, {"error": "motion_render_busy"})


def test_the_lock_is_given_back_even_when_a_render_fails(settings) -> None:
    lock = threading.Lock()

    def broken(**kwargs):  # noqa: ANN003
        raise RuntimeError("engine_failed: boom")

    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=broken, lock=lock)
    assert (status, payload["error"]) == (500, "render_failed")
    assert lock.acquire(blocking=False)


# 4. 결과

def test_render_returns_the_exact_bytes_and_leaves_nothing_behind(settings) -> None:
    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=_writes(b"MP4BYTES"), lock=threading.Lock())
    assert status == 200
    assert base64.b64decode(payload["video_base64"]) == b"MP4BYTES"
    assert (payload["format"], payload["byte_size"], payload["width"], payload["height"]) == ("mp4", 8, 1920, 1080)
    assert payload["duration_sec"] == 6
    assert payload["elapsed_sec"] >= 0
    assert list(settings.work_root.iterdir()) == []


def test_overlay_comes_back_as_webm(settings) -> None:
    status, payload = motion.render_request_payload(_body(layout="overlay"), settings=settings, renderer=_writes(b"WEBM"), lock=threading.Lock())
    assert (status, payload["format"]) == (200, "webm")


def test_a_render_that_never_ends_is_reported_as_a_timeout(settings) -> None:
    def slow(**kwargs):  # noqa: ANN003
        raise subprocess.TimeoutExpired(cmd="node", timeout=motion.RENDER_TIMEOUT_SECONDS)

    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=slow, lock=threading.Lock())
    assert (status, payload) == (504, {"error": "render_timed_out"})


# 5. 컴포지션 만들기 -- 넣는 것은 JSON과 자리표시자 둘뿐

def test_prepare_composition_fills_only_the_length_the_look_and_the_data(settings, tmp_path: Path) -> None:
    order = motion.RenderOrder(template="bar_compare", variables=BAR, duration_sec=8.4, layout="overlay")
    comp = motion.prepare_composition(settings=settings, order=order, scratch=tmp_path / "scratch")
    page = (comp / "index.html").read_text(encoding="utf-8")
    assert "__VB_" not in page
    assert 'data-duration="8.4"' in page
    assert 'data-mode="overlay"' in page
    assert (comp / "motion-runtime.js").is_file()
    assert (comp / "assets" / "NotoSansKR-Variable.ttf").stat().st_size == settings.font_path.stat().st_size
    data = (comp / "data.js").read_text(encoding="utf-8")
    assert data.startswith("window.__VB_MOTION__ = ")
    assert json.loads(data[len("window.__VB_MOTION__ = "):].rstrip().rstrip(";")) == {"variables": BAR, "duration": 8.4, "mode": "overlay"}


def test_the_data_file_never_carries_raw_markup_characters() -> None:
    order = motion.RenderOrder(template="step_list", variables={"title": "A & B", "steps": ["1", "2"]}, duration_sec=6, layout="full")
    script = motion.motion_data_script(order)
    for raw in ("<", ">", "&"):
        assert raw not in script
    assert "\\u0026" in script


# 6. 엔진을 부르는 방식 -- 고정 버전·오프라인·텔레메트리 끔·토큰 안 넘김

def test_render_calls_the_pinned_engine_offline_and_quietly(settings, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_BRIDGE_TOKEN", "t" * 43)
    seen: dict = {}

    def runner(arguments, *, timeout, env, cwd):  # noqa: ANN001
        seen.update(arguments=arguments, timeout=timeout, env=env, cwd=cwd)
        output = Path(arguments[arguments.index("-o") + 1])
        output.write_bytes(b"X")
        return subprocess.CompletedProcess(arguments, 0, "Inlined CDN script https://cdn.example/x.js\n", "")

    scratch = settings.work_root / "one"
    scratch.mkdir(parents=True)
    order = motion.RenderOrder(template="bar_compare", variables=BAR, duration_sec=6, layout="overlay")
    rendered = motion.render_motion(settings=settings, order=order, scratch=scratch, runner=runner)

    arguments, env = seen["arguments"], seen["env"]
    assert arguments[:3] == [str(settings.node), str(settings.hyperframes_bin), "render"]
    assert arguments[arguments.index("--format") + 1] == "webm"
    assert arguments[arguments.index("--fps") + 1] == "30"
    assert Path(arguments[arguments.index("-o") + 1]).resolve().is_relative_to(settings.work_root.resolve())
    assert seen["timeout"] == motion.RENDER_TIMEOUT_SECONDS
    for name in ("HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_SKIP_SKILLS", "HYPERFRAMES_NO_UPDATE_CHECK", "HYPERFRAMES_NO_AUTO_INSTALL", "NODE_USE_ENV_PROXY"):
        assert env[name] == "1", name
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert env["HYPERFRAMES_BROWSER_PATH"] == str(motion.find_browser_executable(settings.cache_root))
    assert "VIDEOBOX_BRIDGE_TOKEN" not in env
    assert rendered.network_mentions == 1


def test_an_engine_that_says_ok_but_writes_nothing_is_a_failure(settings) -> None:
    def runner(arguments, *, timeout, env, cwd):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(arguments, 0, "", "")

    scratch = settings.work_root / "two"
    scratch.mkdir(parents=True)
    order = motion.RenderOrder(template="step_list", variables={"title": "x", "steps": ["a", "b"]}, duration_sec=6, layout="full")
    with pytest.raises(RuntimeError, match="engine_wrote_nothing"):
        motion.render_motion(settings=settings, order=order, scratch=scratch, runner=runner)


def test_output_paths_must_stay_under_the_work_root(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    assert motion.confine_to_root(root / "a" / "out.mp4", root) == (root / "a" / "out.mp4").resolve()
    with pytest.raises(ValueError, match="outside_work_root"):
        motion.confine_to_root(root / ".." / "escape.mp4", root)


def test_run_bounded_kills_the_whole_tree_when_time_runs_out() -> None:
    killed: list[int] = []

    class _Slow:
        pid = 4242
        returncode = None
        calls = 0

        def communicate(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(cmd="node", timeout=timeout)
            return ("", "")

    with pytest.raises(subprocess.TimeoutExpired):
        motion.run_bounded(["node"], timeout=1, env={}, cwd=Path("."), popen=lambda *a, **k: _Slow(), killer=killed.append)
    assert killed == [4242]
