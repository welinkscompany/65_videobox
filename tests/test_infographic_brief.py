"""인포그래픽 지시문과 **그리기 전 검사**.

여기서 지키는 것은 하나다: **모델이 숫자를 지어내면 잡힌다.** 2026-09-07 실측에서
로컬 모델은 시키지도 않은 `100,000원 판매 시` 예시를 통째로 만들어 냈다. 그림
한 장이 창작자 영상에 들어가면 그 거짓 숫자가 그대로 나간다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from videobox_core_engine.infographic_brief import (
    FONT_STACK,
    INFOGRAPHIC_HEIGHT,
    INFOGRAPHIC_STYLES,
    INFOGRAPHIC_WIDTH,
    MINIMUM_FONT_PX,
    PALETTE,
    InfographicFact,
    build_infographic_prompt,
    check_infographic_html,
    extract_document,
    resolve_style,
)

ROOT = Path(__file__).resolve().parent.parent

FACTS = (
    InfographicFact("네이버 결제 수수료", 3.4, "%"),
    InfographicFact("스마트스토어 연동 수수료", 2.0, "%"),
    InfographicFact("셀러에게 남는 몫", 94.6, "%"),
)


def _page(body: str, *, head: str = "", size: bool = True) -> str:
    canvas = (
        f"body{{margin:0;width:{INFOGRAPHIC_WIDTH}px;height:{INFOGRAPHIC_HEIGHT}px}}"
        if size
        else "body{margin:0}"
    )
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>{head}"
        f"<style>{canvas}</style></head><body>{body}</body></html>"
    )


def test_the_palette_matches_the_approved_one_on_screen() -> None:
    """그림은 대표님 영상에 끼워 넣을 것이라 제품 화면과 **같은 색**이어야 한다.

    팔레트를 두 벌 두면 한 벌이 조용히 낡는다 -- 2026-08-20에 편집기 전용
    팔레트를 따로 뒀다가 정확히 그 이유로 2026-08-21에 되돌렸다
    (`apps/web/src/ui-system.css` 주석). 여기가 그 두 번째 벌이므로 대조한다.
    """
    css = (ROOT / "apps/web/src/ui-system.css").read_text(encoding="utf-8")
    on_screen = {
        name: value
        for name, value in re.findall(r"--vb-([a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;", css)
    }
    for key, value in PALETTE.items():
        token = key.replace("_", "-")
        assert token in on_screen, f"`--vb-{token}`가 ui-system.css에 없다"
        assert on_screen[token].upper() == value.upper(), (
            f"--vb-{token}는 화면에서 {on_screen[token]}인데 지시문은 {value}를 준다"
        )


def test_the_prompt_carries_the_numbers_and_the_canvas() -> None:
    """지시가 구체적일수록 결과가 좋다는 것이 실측 결론이다. 숫자·판 크기·색이
    지시문에 실제로 실려 나가는지 본다 -- 안 실리면 모델은 아무 그림이나 그린다."""

    prompt = build_infographic_prompt(topic="수수료 구조", facts=FACTS, style="editorial")
    assert "수수료 구조" in prompt
    for fact in FACTS:
        assert fact.label in prompt
    assert "94.6" in prompt and "3.4" in prompt
    assert str(INFOGRAPHIC_WIDTH) in prompt and str(INFOGRAPHIC_HEIGHT) in prompt
    assert PALETTE["accent"] in prompt
    assert FONT_STACK in prompt
    assert "잡지 편집" in prompt


def test_an_unknown_style_falls_back_instead_of_picking_at_random() -> None:
    """못 알아들은 이름을 조용히 아무거나로 바꾸면, 창작자는 자기가 고른 결이
    안 나온 이유를 영영 모른다. 정해진 첫째 결로 간다."""

    assert resolve_style("없는결").key == INFOGRAPHIC_STYLES[0].key
    assert resolve_style(None).key == INFOGRAPHIC_STYLES[0].key
    assert resolve_style("blueprint").key == "blueprint"


def test_a_made_up_number_is_caught() -> None:
    """**이 시험이 이 모듈의 존재 이유다.** 2026-09-07에 모델이 시키지도 않은
    `100,000원 판매 시` 예시를 지어냈고, 그 예시에서 나온 `3,400원`·`94,600원`이
    그림에 그대로 찍혔다."""

    html = _page("<p>예시: 100,000원 판매 시 셀러 수령액 94,600원</p>")
    problems = check_infographic_html(html, FACTS)
    assert any("준 적 없는 숫자" in problem for problem in problems)
    # 천 단위 쉼표를 한 덩이로 읽어야 무엇이 문제인지 알아볼 수 있는 말이 된다.
    assert any("100000" in problem for problem in problems)


def test_the_given_numbers_and_what_follows_from_them_are_allowed() -> None:
    """준 숫자에서 계산으로 나오는 것까지 지어냈다고 하면 쓸 수 있는 그림이 없다.
    비율 그림은 100에서 빼거나 합을 내는 일이 잦다."""

    html = _page("<p>3.4% + 2% = 5.4%, 남는 몫 94.6%</p>")
    assert check_infographic_html(html, FACTS) == ()


def test_the_arithmetic_left_in_a_comment_is_not_a_made_up_number() -> None:
    """지시문이 계산 과정을 **주석으로** 남기라고 시킨다. 주석까지 세면 시키는 대로
    한 그림이 전부 거절된다 -- 2026-09-07에 실제로 그렇게 걸렸다.

    주석 안에 `>`를 넣은 것은 일부러다. 태그 지우개(`<[^>]+>`)는 `>` 없는 주석을
    어차피 지워 버려서, `>` 없는 주석으로 시험하면 **주석 처리를 통째로 지워도
    시험이 초록으로 남는다**(2026-09-07에 그렇게 썼다가 빨간불이 안 떴다).
    """

    html = _page("<!-- 몫 94.6 > 수수료 5.4, 계산 360*0.946=340.56 --><p>94.6%</p>")
    assert check_infographic_html(html, FACTS) == ()


def test_numbers_inside_a_script_are_not_made_up_numbers() -> None:
    """`<script>` 안의 숫자는 사람이 읽는 자리가 아니다. 세면 애니메이션 하나에
    그림 전체가 거절된다."""

    html = _page("<p>94.6%</p><script>var frames=[0,17,42,60];</script>")
    assert check_infographic_html(html, FACTS) == ()


def test_a_web_font_is_refused() -> None:
    """이 그림은 인터넷 없이 그려진다. 웹폰트를 부르면 인터넷이 없을 때 글씨가
    통째로 바뀌고, 그리기가 바깥으로 나간다."""

    linked = _page("<p>94.6%</p>", head="<link href='https://fonts.googleapis.com/x' rel='stylesheet'>")
    assert any("바깥 주소" in problem for problem in check_infographic_html(linked, FACTS))
    imported = _page("<p>94.6%</p>", head="<style>@import url(x);</style>")
    assert any("바깥 주소" in problem for problem in check_infographic_html(imported, FACTS))


def test_a_font_smaller_than_the_floor_is_caught() -> None:
    """1920 폭에서 20px 아래는 영상으로 나가면 못 읽는다 -- 유튜브가 다시
    압축하고, 시청자 상당수는 휴대폰이다."""

    html = _page(f"<p style='font-size:{MINIMUM_FONT_PX - 2}px'>94.6%</p>")
    assert any("너무 작다" in problem for problem in check_infographic_html(html, FACTS))


def test_a_canvas_of_the_wrong_size_is_caught() -> None:
    """판 크기가 안 적혀 있으면 브라우저 기본 크기로 그려져 영상에 안 맞는다."""

    html = _page("<p>94.6%</p>", size=False)
    assert any("판 크기" in problem for problem in check_infographic_html(html, FACTS))


@pytest.mark.parametrize(
    "reply",
    [
        "이렇게 만들었습니다:\n```html\n<!DOCTYPE html><html><body>가</body></html>\n```",
        "<!DOCTYPE html><html><body>가</body></html>",
        "설명 없이\n<!DOCTYPE html><html><body>가</body></html>\n끝",
    ],
)
def test_the_document_is_pulled_out_of_whatever_the_model_said(reply: str) -> None:
    """모델은 앞뒤에 말을 붙이는 버릇이 있다. ``` 로 자르는 방법은 ``` 를 안 쓴
    답에서 문서를 통째로 날린다 -- 2026-09-07에 실제로 겪었다."""

    found = extract_document(reply)
    assert found is not None
    assert found.startswith("<!DOCTYPE html") and found.endswith("</html>")


def test_a_reply_with_no_document_is_not_pretended_to_be_one() -> None:
    assert extract_document("HTML을 못 만들겠습니다") is None
