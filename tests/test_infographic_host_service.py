"""이 컴퓨터에서 도는 인포그래픽 다리 자체 — 받은 HTML로 실제로 그림이 나오는가.

`test_infographic_host_bridge.py`는 다리를 **부르는 쪽**을 잰다(가짜 다리를 세워서).
이 파일은 **받는 쪽**을 잰다. 둘을 따로 재면 가운데 이음매가 시험 없이 남는데,
이 저장소는 그 자리에서 여러 번 "부품은 있는데 부르는 자리가 없다"를 겪었다.

**소켓은 안 연다.** 이 저장소의 시험은 연결을 못 열게 막혀 있고
(`tests/conftest.py`), 그 울타리는 옳다. 그래서 다리의 판단을 HTTP 껍데기와
떼어 놓고(`*_payload`) 그 함수를 그대로 부른다. 껍데기가 하는 일은 셋을 실어
나르는 것뿐이다(`/diagnostics`, `/render`, `/measure`).

**브라우저도 안 부른다.** 크롬을 진짜로 띄우면 이 시험은 크롬이 깔린 컴퓨터에서만
뜻이 있다. 대신 `runner`를 손으로 주어 크롬이 어떻게 끝났을 때 무엇이 되는지를
잰다 — 특히 **0으로 끝나고도 파일을 안 쓰는 경우**가 실제로 있다.
"""

from __future__ import annotations

import base64
import importlib.util
import subprocess
from pathlib import Path

import pytest

_SERVICE_PATH = Path(__file__).parents[1] / "scripts" / "host_infographic_service.py"
_spec = importlib.util.spec_from_file_location("videobox_host_infographic_service", _SERVICE_PATH)
assert _spec is not None and _spec.loader is not None
bridge_service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge_service)


@pytest.fixture()
def browser(tmp_path: Path) -> Path:
    """브라우저가 있는 컴퓨터를 흉내 낸다. 파일 하나면 된다 -- 실제로 띄우지 않는다."""
    found = tmp_path / "chrome.exe"
    found.write_bytes(b"chrome")
    return found


class _Completed:
    """`subprocess.run`이 돌려주는 것 중 이 코드가 보는 것만."""

    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _renderer(png: bytes):
    """크롬 대신 정해진 바이트를 돌려주는 그리개."""

    def render(*, html: str, width: int, height: int, browser: Path) -> bytes:  # noqa: ARG001
        return png

    return render


def _failing_renderer(error: BaseException):
    def render(**kwargs: object) -> bytes:  # noqa: ARG001
        raise error

    return render


# --------------------------------------------------------------------------
# 1. 진단 — 브라우저를 찾았는지 정직하게 말하는가
# --------------------------------------------------------------------------


def test_diagnostics_report_this_computers_browser(browser: Path) -> None:
    status, payload = bridge_service.diagnostics_payload(browser=browser)

    assert status == 200
    assert payload["status"] == "ready"
    assert payload["browser_path"] == str(browser)
    assert payload["recovery_message"] is None


def test_diagnostics_say_what_to_do_when_there_is_no_browser() -> None:
    """브라우저가 없으면 **없다고 말한다.** 조용히 딴것으로 대신하지 않는다."""
    status, payload = bridge_service.diagnostics_payload(browser=None)

    assert status == 200
    assert payload["status"] == "browser_not_found"
    assert payload["browser_path"] is None
    assert "크롬" in str(payload["recovery_message"])


# --------------------------------------------------------------------------
# 2. `/render` — 무엇을 거절하고 무엇을 돌려주는가
# --------------------------------------------------------------------------


def test_render_without_html_is_refused_before_the_browser_is_started(browser: Path) -> None:
    """빈 HTML로 크롬을 띄우면 빈 그림이 나오고, 그건 성공처럼 보인다."""
    status, payload = bridge_service.render_request_payload(
        {"html": "   "}, browser=browser, renderer=_renderer(b"never")
    )

    assert status == 400
    assert payload["error"] == "html_is_required"


def test_render_says_the_bridge_has_no_browser_instead_of_failing_quietly() -> None:
    status, payload = bridge_service.render_request_payload(
        {"html": "<p>hi</p>"}, browser=None, renderer=_renderer(b"never")
    )

    assert status == 503
    assert payload["error"] == "browser_not_found"


def test_render_refuses_a_size_that_is_not_a_number(browser: Path) -> None:
    """가로세로는 명령줄에 그대로 실린다. 숫자가 아닌 것을 넘기지 않는다."""
    status, payload = bridge_service.render_request_payload(
        {"html": "<p>hi</p>", "width": "아주 넓게"},
        browser=browser,
        renderer=_renderer(b"never"),
    )

    assert status == 400
    assert payload["error"] == "width_and_height_must_be_numbers"


@pytest.mark.parametrize(
    "body",
    [
        {"html": "<p>hi</p>", "width": 8, "height": 1080},
        {"html": "<p>hi</p>", "width": 1920, "height": 99999},
    ],
)
def test_render_refuses_a_size_outside_what_a_browser_can_draw(
    browser: Path, body: dict
) -> None:
    status, payload = bridge_service.render_request_payload(
        body, browser=browser, renderer=_renderer(b"never")
    )

    assert status == 400
    assert payload["error"] == "width_and_height_out_of_range"


def test_render_that_never_comes_back_is_reported_as_a_timeout(browser: Path) -> None:
    """멈춘 크롬을 500으로 적으면 부르는 쪽이 "다리가 고장"이라고 착각한다."""
    status, payload = bridge_service.render_request_payload(
        {"html": "<p>hi</p>"},
        browser=browser,
        renderer=_failing_renderer(subprocess.TimeoutExpired(cmd="chrome", timeout=60)),
    )

    assert status == 504
    assert payload["error"] == "render_timed_out"


def test_a_browser_that_failed_is_reported_as_a_failure_not_as_a_picture(browser: Path) -> None:
    status, payload = bridge_service.render_request_payload(
        {"html": "<p>hi</p>"},
        browser=browser,
        renderer=_failing_renderer(RuntimeError("browser_wrote_nothing")),
    )

    assert status == 500
    assert payload["error"] == "render_failed"
    assert "browser_wrote_nothing" in str(payload["detail"])


def test_render_returns_the_exact_bytes_the_browser_drew(browser: Path) -> None:
    """base64를 되돌리면 **그리개가 준 바이트 그대로**여야 한다. 한 바이트라도
    달라지면 컨테이너 쪽에서 PNG가 안 열린다."""
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256))

    status, payload = bridge_service.render_request_payload(
        {"html": "<p>hi</p>", "width": 640, "height": 360},
        browser=browser,
        renderer=_renderer(png),
    )

    assert status == 200
    assert base64.b64decode(str(payload["png_base64"])) == png
    assert payload["byte_size"] == len(png)
    assert (payload["width"], payload["height"]) == (640, 360)


# --------------------------------------------------------------------------
# 3. `/measure` — 문서 전체가 아니라 잰 값 한 줄만
# --------------------------------------------------------------------------


def test_measure_sends_back_only_the_title_not_the_whole_document(browser: Path) -> None:
    """재는 쪽이 필요로 하는 것은 `<title>` 한 줄이다. DOM 전체를 컨테이너까지
    실어 나르면 큰 인포그래픽에서 응답이 통째로 무거워진다."""

    def dumper(**kwargs: object) -> str:  # noqa: ARG001
        return (
            "<html><head><title>overflow=0 collisions=0</title></head>"
            "<body><div class='card'>본문은 오지 않아야 한다</div></body></html>"
        )

    status, payload = bridge_service.measure_request_payload(
        {"html": "<p>hi</p>"}, browser=browser, dumper=dumper
    )

    assert status == 200
    assert payload["title"] == "<title>overflow=0 collisions=0</title>"
    assert "본문은 오지 않아야 한다" not in str(payload["title"])


def test_measure_without_html_is_refused(browser: Path) -> None:
    def dumper(**kwargs: object) -> str:  # noqa: ARG001
        raise AssertionError("빈 HTML로 브라우저를 띄우면 안 된다")

    status, payload = bridge_service.measure_request_payload(
        {"html": ""}, browser=browser, dumper=dumper
    )

    assert status == 400
    assert payload["error"] == "html_is_required"


# --------------------------------------------------------------------------
# 4. 실제로 크롬을 부르는 자리 — 실패를 성공으로 적지 않는가
# --------------------------------------------------------------------------


def test_render_png_raises_when_the_browser_exits_with_an_error(browser: Path) -> None:
    def runner(arguments, **kwargs):  # noqa: ANN001, ARG001
        return _Completed(returncode=1, stderr="cannot create user data dir")

    with pytest.raises(RuntimeError) as failure:
        bridge_service.render_png(
            html="<p>hi</p>", width=640, height=360, browser=browser, runner=runner
        )

    assert "browser_failed" in str(failure.value)
    assert "cannot create user data dir" in str(failure.value)


def test_render_png_raises_when_the_browser_says_ok_but_writes_nothing(browser: Path) -> None:
    """크롬은 그림을 못 그려도 0으로 끝나는 일이 있다. 종료 코드만 보면 **빈
    바이트를 성공이라고 돌려주게 된다.** 파일을 보고 판단해야 한다."""

    def runner(arguments, **kwargs):  # noqa: ANN001, ARG001
        return _Completed(returncode=0)

    with pytest.raises(RuntimeError) as failure:
        bridge_service.render_png(
            html="<p>hi</p>", width=640, height=360, browser=browser, runner=runner
        )

    assert str(failure.value) == "browser_wrote_nothing"


def test_render_png_returns_what_the_browser_actually_wrote(browser: Path) -> None:
    """위 두 시험이 "언제나 예외"로도 통과하지 않게, 성공하는 길도 함께 잰다."""
    drawn = b"\x89PNG\r\n\x1a\ndrawn"

    def runner(arguments, **kwargs):  # noqa: ANN001, ARG001
        screenshot = [a for a in arguments if str(a).startswith("--screenshot=")][0]
        Path(str(screenshot).split("=", 1)[1]).write_bytes(drawn)
        return _Completed(returncode=0)

    result = bridge_service.render_png(
        html="<p>hi</p>", width=640, height=360, browser=browser, runner=runner
    )

    assert result == drawn


# --------------------------------------------------------------------------
# 5. 브라우저 찾기 — 없으면 없다고 한다
# --------------------------------------------------------------------------


def test_find_browser_returns_nothing_when_this_computer_has_none(monkeypatch) -> None:
    """못 찾았는데 아무 경로나 돌려주면, 그 경로로 크롬을 부르다 엉뚱한 곳에서
    실패한다. `/diagnostics`가 `browser_not_found`를 말할 수 있어야 한다."""
    monkeypatch.setattr(bridge_service, "_BROWSER_CANDIDATES", ())
    monkeypatch.setattr(bridge_service.shutil, "which", lambda name: None)

    assert bridge_service.find_browser() is None


def test_find_browser_uses_the_path_the_owner_gave(browser: Path, monkeypatch) -> None:
    monkeypatch.setattr(bridge_service, "_BROWSER_CANDIDATES", ())
    monkeypatch.setattr(bridge_service.shutil, "which", lambda name: None)

    assert bridge_service.find_browser(str(browser)) == browser
    assert bridge_service.find_browser(str(browser.parent / "nothing-here.exe")) is None
