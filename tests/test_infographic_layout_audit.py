"""브라우저가 실제로 놓은 자리를 재는 일.

**앞서 두 방법이 틀렸다.** 가장자리 픽셀 보기는 잘린 내용이 애초에 안 그려져서
못 잡았고, `overflow:visible`을 덧씌워 다시 그리는 방법은 **재려던 배치 자체를
바꿔** 눈으로 보면 통째로 잘린 그림을 통과시켰다(2026-09-07, 둘 다 실측).

지금 방법은 원본 그대로 올려 놓고 그 안에서 재는 것이다. 그래서 이 시험들이
지키는 것은 하나다: **재기 코드가 원본 배치를 안 건드린다.**
"""

from __future__ import annotations

import json
import re

from videobox_core_engine.infographic_layout_audit import (
    AUDIT_MARKER,
    apply_layout_audit,
    describe_layout_problems,
    read_audit,
)

PAGE = "<!DOCTYPE html><html><head><style>body{margin:0}</style></head><body><p>가</p></body></html>"


def _audited() -> str:
    return apply_layout_audit(PAGE, width=1920, height=1080, minimum_font_px=20)


def test_the_measuring_code_does_not_touch_the_original_layout() -> None:
    """**이 시험이 앞 두 방법이 실패한 이유다.** 스타일을 덧씌우면 재려던 그
    배치가 바뀐다. 붙이는 것은 스크립트 하나뿐이고, 원래 있던 글자는 그대로다."""

    audited = _audited()
    without_script = re.sub(r"<script id=\"videobox-audit\">.*?</script>", "", audited, flags=re.S)
    assert without_script == PAGE, "재기 코드가 원본을 고쳤다"
    assert "!important" not in audited, "덧씌우는 스타일이 들어갔다"


def test_the_measuring_code_runs_after_the_page_is_laid_out() -> None:
    """`</body>` 앞에 있어야 문서가 다 놓인 뒤에 돈다. 머리에 넣으면 아무것도
    없는 상태를 재고 늘 통과한다."""

    audited = _audited()
    assert audited.index("videobox-audit") < audited.index("</body>")
    assert "<p>가</p>" in audited
    assert audited.index("<p>가</p>") < audited.index("videobox-audit")


def test_the_font_floor_travels_into_the_measuring_code() -> None:
    """기준을 코드에 박으면 `infographic_brief`의 기준과 조용히 갈라진다."""

    assert "MIN = 33" in apply_layout_audit(PAGE, width=1, height=2, minimum_font_px=33)
    assert "W = 1, H = 2" in apply_layout_audit(PAGE, width=1, height=2, minimum_font_px=33)


def test_a_measurement_we_cannot_read_is_not_an_empty_measurement() -> None:
    """**못 잰 것을 통과로 다루면 안 된다.** 빈 딕셔너리를 돌려주면 부르는 쪽이
    "문제 없음"으로 읽는다."""

    assert read_audit("<title>보통 제목</title>") is None
    assert read_audit("제목이 아예 없다") is None
    assert read_audit(f"<title>{AUDIT_MARKER}이건 JSON이 아니다</title>") is None


def test_a_real_measurement_is_read_back() -> None:
    payload = {"tall": 12, "outside": [], "overlaps": [], "tiny": []}
    assert read_audit(f"<title>{AUDIT_MARKER}{json.dumps(payload)}</title>") == payload


def test_the_problems_say_what_to_change_not_just_that_it_is_wrong() -> None:
    """"잘못됐다"만 돌려주면 다음 판이 똑같이 나온다. 얼마나 넘쳤는지·무엇이
    겹쳤는지를 적어야 모델이 고칠 수 있다 -- 실측에서 182px을 적어 주니 두 번째
    판이 판 안에 들어왔다."""

    problems = describe_layout_problems(
        {
            "tall": 182,
            "outside": [{"text": "94.6원", "bottom": 1230, "right": 900}],
            "overlaps": [{"one": "제목", "two": "오른쪽 칸"}],
            "tiny": [{"text": "총 수수료", "px": 16}],
        }
    )
    joined = " / ".join(problems)
    assert "182px" in joined
    assert "94.6원" in joined and "1230" in joined
    assert "제목" in joined and "오른쪽 칸" in joined
    assert "grid" in joined, "겹칠 때 무엇으로 바꾸라는 말이 없다"
    assert "총 수수료" in joined and "16px" in joined


def test_a_page_that_fits_reports_nothing() -> None:
    """한두 픽셀 삐져나온 것을 문제로 삼으면 멀쩡한 그림이 전부 다시 만들어진다.
    그림 한 판이 1~2분이다."""

    assert describe_layout_problems(
        {"tall": 1, "outside": [], "overlaps": [], "tiny": []}
    ) == ()
    assert describe_layout_problems({}) == ()


def test_only_a_handful_of_problems_are_listed() -> None:
    """스무 개를 늘어놓으면 모델이 무엇부터 고칠지 모른다. 갯수는 다 세되
    보기는 몇 개만 든다."""

    audit = {
        "tall": 0,
        "outside": [],
        "overlaps": [{"one": f"가{n}", "two": f"나{n}"} for n in range(12)],
        "tiny": [],
    }
    (problem,) = describe_layout_problems(audit)
    assert "12곳" in problem
    assert "가9" not in problem
