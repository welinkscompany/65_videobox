"""인포그래픽 한 장을 만들라고 유진에게 시킬 때 **무엇을 시키는지**.

## 왜 지시가 핵심인가

2026-09-07에 이 컴퓨터의 로컬 모델(`qwen3.6-35b-a3b`)로 인포그래픽을 두 번
만들어 보고 나온 결론이다. "인포그래픽 만들어줘"만 준 첫 번째는 밋밋했고,
화면 구성을 구체적으로 준 두 번째는 그대로 쓸 만했다. **모델이 부족한 게
아니라 지시가 부족했다.**

지시의 뼈대는 `github.com/OrRon/EpicInfographics`(MIT)에서 가져왔다. 그쪽 코드를
들여오지는 않았다 -- 그건 Playwright를 새로 지고 오는 일이고, 이 컴퓨터에는
크롬이 이미 있어서 `--headless --screenshot` 한 줄이면 끝난다. 가져온 것은
**규칙**이다.

## 여기서 정하는 것 셋

1. **판(canvas)**: 1920×1080 고정. 영상 한 장면에 그대로 얹히는 크기다.
2. **말투와 색**: VideoBox의 승인된 어두운 팔레트(`ui-system.css`)를 쓴다.
   대표님 영상에 끼워 넣을 그림이니 제품 화면과 같은 색이어야 한다.
3. **거짓말 금지**: 준 숫자만 쓴다. 이건 사람이 안 봐도 기계가 검사한다
   (`check_infographic_html`).

## 검사는 그리기 전과 그린 뒤 두 번이다

여기(`check_infographic_html`)는 **그리기 전**, HTML만 보고 잡을 수 있는 것을
잡는다 -- 지어낸 숫자, 밖으로 나가는 주소, 너무 작은 글씨, 어긋난 판 크기.
글자가 눌리거나 잘리는 것은 여기서 못 잡는다. 그건 그린 뒤 시각 모델이 본다
(`infographic_service`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

#: 영상 한 장면에 그대로 얹히는 크기. 세로 영상은 아직 안 다룬다 --
#: 대표님 채널(`노마드루이스`)은 가로다.
INFOGRAPHIC_WIDTH = 1920
INFOGRAPHIC_HEIGHT = 1080

#: 읽을 수 있는 가장 작은 글씨. 1920 폭에서 20px 아래는 영상으로 나가면 못 읽는다.
#: (유튜브가 1080p를 다시 압축하고, 대표님 시청자 상당수는 휴대폰이다.)
MINIMUM_FONT_PX = 20

#: 승인된 어두운 팔레트. `apps/web/src/ui-system.css`의 값과 **같아야 한다** --
#: `tests/test_infographic_brief.py`가 두 자리를 대조한다. 두 벌을 두면 한 벌이
#: 조용히 낡는다(그 일이 2026-08-20에 팔레트로 이미 한 번 있었다).
PALETTE = {
    "canvas": "#0F0F11",
    "panel": "#18181B",
    "panel_alt": "#202024",
    "border": "#2E2E33",
    "text": "#F2F2F3",
    "muted": "#A3A3AC",
    "accent": "#EA580C",
    "success": "#4ADE80",
}

#: 글꼴은 **이 컴퓨터에 있는 것만** 부른다. 웹폰트를 부르면 그리기가 밖으로
#: 나가고(§아래 검사가 막는다), 인터넷이 없으면 글씨가 통째로 바뀐다.
FONT_STACK = '"Pretendard", "Noto Sans KR", "Malgun Gothic", sans-serif'


@dataclass(frozen=True, slots=True)
class InfographicFact:
    """그림에 들어갈 숫자 하나. **여기 없는 숫자는 그림에 못 들어간다.**"""

    label: str
    value: float
    unit: str = ""
    note: str = ""

    def as_line(self) -> str:
        rendered = f"{self.value:g}{self.unit}"
        return f"- {self.label}: {rendered}" + (f" ({self.note})" if self.note else "")


@dataclass(frozen=True, slots=True)
class InfographicStyle:
    """그림의 결. 아홉 가지를 다 옮기지 않았다 -- 셋을 제대로 하는 편이 낫고,
    나머지는 대표님이 실제로 아쉬워할 때 더한다."""

    key: str
    korean_name: str
    direction: str


#: 셋 다 어두운 판 위에서 성립한다. VideoBox 화면이 어둡고, 대표님 영상도
#: 어두운 배경 위 자막이라 밝은 인포그래픽 한 장이 끼면 눈이 아프다.
INFOGRAPHIC_STYLES: tuple[InfographicStyle, ...] = (
    InfographicStyle(
        key="dark_glass",
        korean_name="어두운 유리",
        direction=(
            "깊은 배경 위에 반투명 유리판을 얹는다. 판 뒤로 은은한 빛 번짐을 두되 "
            "글씨 위에는 두지 않는다. 강조색은 딱 한 곳에만 쓴다."
        ),
    ),
    InfographicStyle(
        key="editorial",
        korean_name="잡지 편집",
        direction=(
            "잡지 특집 기사처럼 짠다. 왼쪽에 아주 큰 숫자 하나, 오른쪽에 설명 단. "
            "가로줄 하나로 위아래를 나눈다. 장식을 빼고 여백으로 말한다."
        ),
    ),
    InfographicStyle(
        key="blueprint",
        korean_name="설계도",
        direction=(
            "청사진 제도처럼 그린다. 가는 격자, 치수선과 화살표, 도장 찍은 듯한 제목. "
            "숫자에는 치수선을 붙여 크기를 눈으로 재게 한다."
        ),
    ),
)

_STYLE_BY_KEY = {style.key: style for style in INFOGRAPHIC_STYLES}


def resolve_style(key: str | None) -> InfographicStyle:
    """이름을 못 알아들으면 조용히 아무거나 고르지 않고 **첫째 결**로 간다."""

    if key and key in _STYLE_BY_KEY:
        return _STYLE_BY_KEY[key]
    return INFOGRAPHIC_STYLES[0]


def build_infographic_prompt(
    *,
    topic: str,
    facts: Sequence[InfographicFact],
    style: str | None = None,
    audience: str = "온라인 셀러를 배우는 사람",
) -> str:
    """유진의 두뇌에 보낼 지시문. **구체적일수록 결과가 좋다**는 것이 실측 결론이다."""

    chosen = resolve_style(style)
    fact_lines = "\n".join(fact.as_line() for fact in facts) or "- (숫자 없음)"
    allowed = ", ".join(f"{fact.value:g}" for fact in facts) or "(없음)"
    return f"""너는 인포그래픽 한 장을 HTML로 만든다. 결과는 HTML **하나만** 낸다.

# 주제
{topic}

# 읽는 사람
{audience}

# 쓸 수 있는 숫자 (이것 말고는 **어떤 숫자도 새로 만들지 마라**)
{fact_lines}

허용된 숫자 목록: {allowed}
(색 값·좌표·글자 크기 같은 CSS 숫자는 여기 해당하지 않는다. 합계와 비율은 위
숫자에서 **계산해서** 쓰면 된다.)

**예시를 지어내지 마라.** `100,000원 판매 시`, `평균 316,000원` 같은 문장은 위
목록에 없는 숫자를 새로 만드는 일이다. 그런 그림은 통째로 버려진다 --
2026-09-07에 실제로 두 번 그렇게 버렸다.

# 판
- 정확히 {INFOGRAPHIC_WIDTH}×{INFOGRAPHIC_HEIGHT}px.
  `body {{ margin:0; width:{INFOGRAPHIC_WIDTH}px; height:{INFOGRAPHIC_HEIGHT}px; overflow:hidden; }}`
- **아래가 잘리면 실패다.** 스크롤은 없다 -- 영상 한 장면으로 들어가는 그림이다.
  세로 여유가 걱정되면 칸 수를 줄여라. 넣을 것을 다 넣는 것보다 다 보이는 게 낫다.
- 안쪽 여백은 사방 80px. 그러니 **그리는 자리는 1760×920px뿐이다.**
  제목·본문·요약을 다 합친 높이가 920px를 넘으면 안 된다. 여유를 두고 짜라 --
  2026-09-07 실측에서 두 판 연속으로 28px씩 넘겨 아래가 잘렸다.
- 짜임새는 이렇게 간다: **맨 위 제목 한 줄**, 그 아래 **본문 한 판**, 맨 아래
  **한 줄 요약**. 본문을 좌우로 나눌 거면 `grid-template-columns`로 나눈다.
- 바깥 판에 `display:grid; grid-template-rows: auto 1fr auto; height:920px`를 주면
  본문이 남는 자리를 알아서 채운다. 칸마다 높이를 손으로 더하지 마라 -- 그러다 넘친다.

# 결
{chosen.korean_name} — {chosen.direction}

# 색 (이 값만 쓴다)
- 바탕 {PALETTE["canvas"]}, 판 {PALETTE["panel"]}, 판(밝은) {PALETTE["panel_alt"]}
- 선 {PALETTE["border"]}, 글씨 {PALETTE["text"]}, 흐린 글씨 {PALETTE["muted"]}
- 강조 {PALETTE["accent"]}, 좋은 신호 {PALETTE["success"]}

# 글꼴
`font-family: {FONT_STACK}` 만 쓴다. **웹폰트를 불러오지 마라** —
`@import`, `<link>`, 바깥 주소(http/https)가 하나라도 있으면 거절한다.
이 그림은 인터넷 없이 그려진다.

# 지켜야 할 것
1. **가장 큰 숫자 하나**를 300px 이상으로 크게 둔다. 멀리서도 그것만은 읽힌다.
2. 어떤 글씨도 {MINIMUM_FONT_PX}px 아래로 내려가지 않는다. 작은 이름표도 마찬가지다.
3. 막대·원호의 길이는 **숫자에서 계산해서** 적는다. 눈대중으로 정하지 마라.
   계산 과정은 HTML 주석(`<!-- 94.6/100*360=340.6도 -->`)에만 남긴다.
   **계산식을 화면에 찍지 마라.** 보는 사람에게는 뜻 없는 글자다.
4. 좁은 조각에는 이름표를 안에 넣지 마라 — 눌려서 잘린다. 밖에 붙이고 선으로 잇는다.
5. 글자끼리, 글자와 그림이 겹치지 않게 한다.
6. 제목은 한 줄, 열 자 안팎. 설명은 짧게.
7. 강조색({PALETTE["accent"]})은 **가장 중요한 것 하나**에만. 다 강조하면 아무것도 안 남는다.
   좋은 신호 색({PALETTE["success"]})도 마찬가지다 -- 화면을 그 색으로 덮지 마라.
8. **자리 잡기는 `grid`나 `flex`로만 한다. `position:absolute`를 쓰지 마라.**
   장식 한 점을 놓을 때가 아니면 절대 위치는 글자 위에 글자를 겹치게 만든다 --
   2026-09-07에 실제로 제목이 오른쪽 칸에 덮였다.
9. **설명 문장에 새 사실을 쓰지 마라.** 위에 준 이름과 숫자만 가지고 말한다.
   "연동은 무료입니다", "결제 시 추가 수수료 발생" 같은 문장은 지어낸 주장이고,
   준 숫자와 정면으로 어긋나기도 한다 -- 2026-09-07에 실제로 그랬다.
10. 큰 숫자는 **자기 자리를 다 차지하게** 둔다. 원형 그래프 한가운데에 얹을 거면
   그 안에 들어갈 크기로 줄여라. 삐져나오면 그래프가 숫자를 덮는다.
11. 한국어로 쓴다.

# 내는 것
`<!DOCTYPE html>`로 시작해 `</html>`로 끝나는 파일 하나. 설명하지 마라. 코드만 낸다."""


# `<!DOCTYPE html>`부터 `</html>`까지. 모델은 앞뒤에 말을 붙이는 버릇이 있고,
# ``` 로 자르면 ``` 를 안 쓴 답에서 통째로 날아간다(2026-09-07에 겪었다).
_DOCUMENT = re.compile(r"<!DOCTYPE html.*?</html>", re.IGNORECASE | re.DOTALL)
_EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)
_FONT_SIZE = re.compile(r"font-size\s*:\s*([0-9]*\.?[0-9]+)\s*px", re.IGNORECASE)
#: 사람이 안 읽는 자리. `<style>`·`<script>`는 물론 **주석**도 뺀다 -- 브리핑이
#: 계산 과정을 주석으로 남기라고 시키므로, 안 빼면 그 계산이 전부 "지어낸 숫자"로 걸린다.
_HIDDEN_BLOCK = re.compile(
    r"<style[^>]*>.*?</style>|<script[^>]*>.*?</script>|<!--.*?-->",
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>", re.DOTALL)
#: 천 단위 쉼표를 **한 덩이로** 읽는다. 안 그러면 모델이 지어낸 `100,000원`이
#: `100`과 `000`으로 쪼개져 무엇이 문제인지 알아볼 수 없는 말이 된다(2026-09-07 실측).
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def extract_document(text: str) -> str | None:
    """모델의 답에서 HTML 문서만 꺼낸다. 못 찾으면 `None`."""

    found = _DOCUMENT.search(text)
    return found.group(0) if found else None


def _visible_numbers(html: str) -> list[str]:
    """**사람이 읽는 자리**에 나오는 숫자만. CSS와 태그 속성은 뺀다 -- 거기 숫자는
    색·좌표·크기라서 세면 전부 "지어낸 숫자"로 걸린다."""

    body = _HIDDEN_BLOCK.sub(" ", html)
    body = _TAG.sub(" ", body)
    return [found.replace(",", "") for found in _NUMBER.findall(body)]


def _allowed_numbers(facts: Sequence[InfographicFact]) -> set[str]:
    """준 숫자와, 그 숫자에서 **계산으로 나오는** 것들. 비율 그림은 100에서 빼거나
    합을 내는 일이 잦은데, 그걸 전부 지어낸 숫자로 몰면 쓸 수 있는 그림이 없다."""

    values = [fact.value for fact in facts]
    derived: set[float] = set(values)
    total = sum(values)
    derived.add(total)
    derived.add(100.0)
    for value in values:
        # 비율 그림은 100에서 빼는 일이 잦다. 다만 **음수는 안 넣는다** --
        # 금액을 다루면 `100 - 150000 = -149900`처럼 나올 수 없는 값이 쌓인다.
        if value <= 100.0:
            derived.add(100.0 - value)
        derived.add(round(value))
    if total:
        for value in values:
            derived.add(round(value / total * 100.0, 1))
            derived.add(float(round(value / total * 100.0)))
    allowed = set()
    for number in derived:
        allowed.add(f"{number:g}")
        allowed.add(f"{round(number)}")
        allowed.add(f"{number:.1f}")
    return allowed


def check_infographic_html(html: str, facts: Sequence[InfographicFact]) -> tuple[str, ...]:
    """**그리기 전에** 잡을 수 있는 문제. 빈 튜플이면 그려도 된다.

    잡지 못하는 것을 분명히 해 둔다: 글자가 눌리거나 잘리는 것, 겹치는 것,
    막대 길이가 숫자와 안 맞는 것. 저건 그린 그림을 봐야 안다.
    """

    problems: list[str] = []
    if not _DOCUMENT.search(html):
        problems.append("문서가 <!DOCTYPE html> ... </html> 모양이 아니다")
    if _EXTERNAL.search(html) or _CSS_IMPORT.search(html):
        problems.append("바깥 주소를 부른다 — 인터넷 없이 그려야 한다")
    for raw in _FONT_SIZE.findall(html):
        if float(raw) < MINIMUM_FONT_PX:
            problems.append(f"글씨가 너무 작다: {raw}px (가장 작은 값 {MINIMUM_FONT_PX}px)")
            break
    if str(INFOGRAPHIC_WIDTH) not in html or str(INFOGRAPHIC_HEIGHT) not in html:
        problems.append(f"판 크기 {INFOGRAPHIC_WIDTH}×{INFOGRAPHIC_HEIGHT}가 문서에 없다")
    allowed = _allowed_numbers(facts)
    invented = [number for number in _visible_numbers(html) if number not in allowed]
    if invented:
        shown = ", ".join(dict.fromkeys(invented))
        problems.append(f"준 적 없는 숫자가 그림에 있다: {shown}")
    return tuple(problems)
