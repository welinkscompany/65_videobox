"""설명 모션 템플릿 -- 저장소에 들어 있는 코드만 돌고, 바깥에 나가지 않는다 (2026-10-08 결정 2단계).

템플릿은 headless 크롬 안에서 도는 HTML+JS다. 그래서 **코드로 다룬다**: 모델이 쓴 코드를
받지 않고(결정 방침 1), 바깥 주소를 부르지 않고(스파이크: 기본 컴포지션은 GSAP를 CDN에서
받았다), 글을 마크업으로 만들지 않는다(`textContent`만). 다리가 넣는 것은 `data.js`의 JSON과
자리표시자 둘(길이·모양)뿐이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = ROOT / "scripts" / "motion-bridge"
TEMPLATES = BRIDGE_ROOT / "templates"
KEYS = ("bar_compare", "money_counter", "step_list")


def _template_files() -> list[Path]:
    return sorted(path for path in TEMPLATES.rglob("*") if path.is_file())


def test_the_motion_engine_is_pinned_exactly() -> None:
    package = json.loads((BRIDGE_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["dependencies"] == {"hyperframes": "0.8.140"}
    lock = json.loads((BRIDGE_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/hyperframes"]["version"] == "0.8.140"


@pytest.mark.parametrize("key", KEYS)
def test_every_template_ships_its_own_files(key: str) -> None:
    for name in ("index.html", "template.js", "hyperframes.json"):
        assert (TEMPLATES / key / name).is_file(), f"{key}/{name}가 없다"
    assert (TEMPLATES / "_shared" / "motion-runtime.js").is_file()


def test_templates_never_reach_the_network() -> None:
    files = _template_files()
    assert files, "템플릿 파일이 하나도 없다"
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for banned in ("http://", "https://", "cdn", "gsap", "@import", "googleapis"):
            assert banned not in text, f"{path.relative_to(ROOT)}에 {banned!r}가 있다"


def test_templates_never_turn_text_into_markup() -> None:
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "fetch(", "XMLHttpRequest", "import("):
            assert banned not in text, f"{path.relative_to(ROOT)}에 {banned!r}가 있다"


@pytest.mark.parametrize("key", KEYS)
def test_each_page_loads_only_its_three_local_scripts_in_order(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    tags = re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.DOTALL)
    assert all(body.strip() == "" for body in tags), "안에 코드를 쓴 script가 있다"
    sources = re.findall(r'<script\s+src="([^"]+)"\s*>', page)
    assert sources == ["data.js", "motion-runtime.js", "template.js"]


@pytest.mark.parametrize("key", KEYS)
def test_each_page_takes_only_its_length_and_look_from_the_bridge(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert page.count('data-mode="__VB_MODE__"') == 1
    assert page.count('data-duration="__VB_DURATION__"') >= 2
    assert set(re.findall(r"__VB_[A-Z]+__", page)) == {"__VB_DURATION__", "__VB_MODE__"}
    assert 'data-composition-id="main"' in page
    assert 'data-width="1920" data-height="1080"' in page


@pytest.mark.parametrize("key", KEYS)
def test_the_overlay_look_keeps_a_card_behind_the_text(key: str) -> None:
    """스파이크 프레임에서 바탕 없는 글자는 무늬 위에서 안 읽혔다(결정 방침 3)."""
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert 'html[data-mode="overlay"],html[data-mode="overlay"] body{background:transparent}' in page
    assert re.search(r'html\[data-mode="overlay"\] #card\{[^}]*background:rgba\(', page)


@pytest.mark.parametrize("key", KEYS)
def test_the_font_is_the_repository_font_loaded_locally(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert 'src:url("assets/NotoSansKR-Variable.ttf")' in page
    assert (ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf").is_file()


def test_the_motion_tools_stay_out_of_the_container_image() -> None:
    """템플릿과 node_modules(약 130MB)는 호스트 다리만 쓴다. 컨테이너는 안 읽는다."""
    patterns = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "scripts/motion-bridge" in patterns


def test_the_engine_install_runs_without_install_scripts() -> None:
    """esbuild에 postinstall이 있다. 설치는 스크립트를 돌리지 않는다(`.npmrc`와 `prepare-motion.ps1` 둘 다)."""
    npmrc = (BRIDGE_ROOT / ".npmrc").read_text(encoding="utf-8")
    assert "ignore-scripts=true" in npmrc.replace(" ", "").splitlines()
    prepare = (ROOT / "scripts" / "prepare-motion.ps1").read_text(encoding="utf-8-sig")
    assert "'ci', '--ignore-scripts'" in prepare


_STRICT_BANS = (
    'url(//', "url('//", 'url("//', 'src="//', "src='//", 'href="//', "href='//",
    'createElement("script")', "createElement('script')", "new WebSocket", "Worker(", "importScripts", "srcdoc",
)


def test_templates_have_no_sneaky_ways_out() -> None:
    """스킴 없는 주소(`//host`)·스크립트 만들기·소켓·워커·iframe srcdoc도 막는다."""
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for banned in _STRICT_BANS:
            assert banned not in text, f"{path.relative_to(ROOT)}에 {banned!r}가 있다"


def test_the_only_css_url_is_the_one_local_font() -> None:
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"url\(([^)]*)\)", text):
            assert match.group(1) == '"assets/NotoSansKR-Variable.ttf"', f"{path.relative_to(ROOT)}: {match.group(0)}"
    assert sum(
        len(re.findall(r"url\(", (TEMPLATES / key / "index.html").read_text(encoding="utf-8"))) for key in KEYS
    ) == len(KEYS)


def test_the_strict_ban_list_actually_catches_each_form() -> None:
    sample = 'a{b:url(//x)} <script src="//x"> <a href="//x"> createElement("script") new WebSocket Worker( importScripts srcdoc'
    for banned in ('url(//', 'src="//', 'href="//', 'createElement("script")', "new WebSocket", "Worker(", "importScripts", "srcdoc"):
        assert banned in sample and banned in _STRICT_BANS
