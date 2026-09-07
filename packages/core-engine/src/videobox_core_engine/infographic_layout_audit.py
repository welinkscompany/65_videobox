"""**브라우저가 실제로 놓은 자리**를 재서 잡는 문제.

## 앞서 두 번 틀린 방법

1. **가장자리 픽셀 보기.** 잘린 내용은 판 밖에 있어서 애초에 안 그려진다. 못 잡는다.
2. **`overflow:visible`을 덧씌워 높은 창에 다시 그리기.** 이건 더 나빴다 --
   덧씌우는 순간 **재려던 그 배치가 바뀐다.** 2026-09-07에 눈으로 보면 아래가
   통째로 잘린 그림이 이 검사를 통과했다.

그래서 이제 **원본 그대로** 브라우저에 올려 놓고, 그 안에서 자리를 잰다.
크롬의 `--dump-dom`은 스크립트가 다 돈 뒤의 DOM을 찍어 준다. 그래서 잰 값을
`<title>`에 적어 두면 그대로 읽어 올 수 있다.

## 무엇을 재는가

- **판을 넘어간 글자**: 화면 밖으로 나간 것. 사람에게는 잘려 보인다.
- **겹친 글자**: 글자 상자끼리 실제로 겹친 것.
- **너무 작은 글자**: 계산된 크기가 기준 아래인 것. CSS 문자열이 아니라
  **실제 계산값**이라 `rem`·상속·`clamp()`까지 다 반영된다.

## 무엇을 안 재는가

"촌스럽다", "색이 안 어울린다"는 안 잰다. 확실하지 않은 판정으로 되돌이를 돌리면
좋은 그림을 버리고 나쁜 그림을 얻는다.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

#: 잰 값을 실어 나르는 표식. `<title>`에 적는 것은 `--dump-dom`이 그것까지
#: 찍어 주기 때문이다 -- 따로 파일을 쓰거나 포트를 열 필요가 없다.
AUDIT_MARKER = "VBAUDIT:"

#: 상자 두 개가 이만큼 넘게 겹쳐야 겹쳤다고 본다. 테두리·자간 때문에 1~2px은
#: 늘 스친다.
OVERLAP_TOLERANCE_PX = 4
#: 판 밖으로 이만큼 넘어야 나갔다고 본다. 반올림으로 1px씩 삐져나오는 일이 잦다.
OUTSIDE_TOLERANCE_PX = 2
#: 한 번에 몇 개까지 말해 줄지. 스무 개를 늘어놓으면 모델이 무엇부터 고칠지 모른다.
MAXIMUM_REPORTED = 4

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)


def _measure_script(width: int, height: int, minimum_font_px: int) -> str:
    """페이지 안에서 돌 재기 코드. **원본 스타일은 하나도 안 건드린다.**"""

    return f"""<script id="videobox-audit">
(function () {{
  function measure() {{
    var W = {width}, H = {height}, MIN = {minimum_font_px};
    var out = {{ tall: 0, outside: [], overlaps: [], tiny: [] }};
    var root = document.documentElement, body = document.body;
    out.tall = Math.max(0, Math.max(root.scrollHeight, body.scrollHeight) - H);
    var boxes = [];
    var all = body.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {{
      var node = all[i];
      // 글자를 **직접** 들고 있는 잎만 본다. 감싸는 상자까지 세면 부모와 자식이
      // 겹쳤다고 나와서 전부 거짓 신고가 된다.
      if (node.children.length !== 0) continue;
      var text = (node.textContent || '').trim();
      if (!text) continue;
      var style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      if (parseFloat(style.opacity) === 0) continue;
      var rect = node.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      var label = text.slice(0, 20);
      boxes.push({{ rect: rect, label: label }});
      var size = parseFloat(style.fontSize);
      if (size && size < MIN) out.tiny.push({{ text: label, px: Math.round(size) }});
      if (rect.bottom > H + {OUTSIDE_TOLERANCE_PX} || rect.right > W + {OUTSIDE_TOLERANCE_PX}
          || rect.top < -{OUTSIDE_TOLERANCE_PX} || rect.left < -{OUTSIDE_TOLERANCE_PX}) {{
        out.outside.push({{
          text: label, bottom: Math.round(rect.bottom), right: Math.round(rect.right)
        }});
      }}
    }}
    for (var a = 0; a < boxes.length; a++) {{
      for (var b = a + 1; b < boxes.length; b++) {{
        var one = boxes[a].rect, two = boxes[b].rect;
        var across = Math.min(one.right, two.right) - Math.max(one.left, two.left);
        var down = Math.min(one.bottom, two.bottom) - Math.max(one.top, two.top);
        if (across > {OVERLAP_TOLERANCE_PX} && down > {OVERLAP_TOLERANCE_PX}) {{
          out.overlaps.push({{ one: boxes[a].label, two: boxes[b].label }});
        }}
      }}
    }}
    document.title = '{AUDIT_MARKER}' + JSON.stringify(out);
  }}
  // 글꼴이 다 실린 뒤에 재야 한다 -- 대체 글꼴로 재면 폭이 달라져 없는 겹침이
  // 생기거나 있는 겹침이 사라진다.
  if (document.fonts && document.fonts.ready) {{
    document.fonts.ready.then(measure).catch(measure);
  }} else {{
    measure();
  }}
}})();
</script>"""


def apply_layout_audit(html: str, *, width: int, height: int, minimum_font_px: int) -> str:
    """재기 코드를 **끝에** 붙인 사본. 원본은 그대로 둔다 -- owner에게 가는 그림은
    어디까지나 작성된 그대로 그린 것이다.

    `</body>` 앞에 넣는 것은 문서가 다 놓인 뒤에 돌아야 하기 때문이다."""

    script = _measure_script(width, height, minimum_font_px)
    lowered = html.lower()
    marker = lowered.rfind("</body>")
    if marker != -1:
        return html[:marker] + script + html[marker:]
    return html + script


def read_audit(dumped_dom: str) -> dict[str, Any] | None:
    """`--dump-dom` 결과에서 잰 값을 꺼낸다. 못 찾으면 `None` --
    **재지 못한 것을 통과로 다루지 않는다.**"""

    found = _TITLE.search(dumped_dom)
    if not found:
        return None
    title = found.group(1).strip()
    if not title.startswith(AUDIT_MARKER):
        return None
    try:
        decoded = json.loads(title[len(AUDIT_MARKER) :])
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _sample(items: list[Any], render) -> list[str]:
    return [render(item) for item in items[:MAXIMUM_REPORTED]]


def describe_layout_problems(audit: Mapping[str, Any]) -> tuple[str, ...]:
    """잰 값을 **모델이 고칠 수 있는 말**로 옮긴다. "잘못됐다"가 아니라
    무엇이 어디로 나갔는지 적는다 -- 그래야 다음 판이 달라진다."""

    problems: list[str] = []
    tall = int(audit.get("tall") or 0)
    if tall > OUTSIDE_TOLERANCE_PX:
        problems.append(f"내용이 판보다 {tall}px 길다 — 칸을 줄이거나 글자를 줄여라")
    outside = [item for item in audit.get("outside") or [] if isinstance(item, dict)]
    if outside:
        listed = ", ".join(
            _sample(outside, lambda item: f"'{item.get('text')}'(아래끝 {item.get('bottom')}px)")
        )
        problems.append(f"판 밖으로 나간 글자가 {len(outside)}개다: {listed}")
    overlaps = [item for item in audit.get("overlaps") or [] if isinstance(item, dict)]
    if overlaps:
        listed = ", ".join(
            _sample(overlaps, lambda item: f"'{item.get('one')}' ↔ '{item.get('two')}'")
        )
        problems.append(
            f"글자끼리 겹친 자리가 {len(overlaps)}곳이다: {listed} — "
            "`position:absolute` 대신 grid로 자리를 나눠라"
        )
    tiny = [item for item in audit.get("tiny") or [] if isinstance(item, dict)]
    if tiny:
        listed = ", ".join(
            _sample(tiny, lambda item: f"'{item.get('text')}'({item.get('px')}px)")
        )
        problems.append(f"실제로 그려진 글씨가 너무 작다: {listed}")
    return tuple(problems)


__all__ = [
    "AUDIT_MARKER",
    "apply_layout_audit",
    "describe_layout_problems",
    "read_audit",
]
