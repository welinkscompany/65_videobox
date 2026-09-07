"""인포그래픽을 만드는 일 전체 — **다시 시키기**, 시간 예산, 자료실 등록.

여기서 지키는 것 셋:

1. 문제를 잡으면 **무엇이 틀렸는지 적어** 한 번 더 시킨다. "다시 해"만으로는
   안 고쳐진다.
2. **한 판 더 돌 시간이 없으면 안 돈다.** nginx가 330초에서 끊는데 거기서
   잘리면 창작자는 4분을 기다리고 우리 문구 대신 프록시의 504 HTML을 받는다.
3. 자료실 등록이 실패해도 **그림을 잃지 않는다.**
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from videobox_core_engine.infographic_brief import (
    INFOGRAPHIC_HEIGHT,
    INFOGRAPHIC_WIDTH,
    InfographicFact,
)
from videobox_core_engine.infographic_layout_audit import AUDIT_MARKER
from videobox_core_engine.infographic_service import (
    TOTAL_BUDGET_SECONDS,
    InfographicService,
    InfographicUnavailable,
)

FACTS = (InfographicFact("남는 몫", 94.6, "%"),)
CLEAN_AUDIT = f"<title>{AUDIT_MARKER}" '{"tall":0,"outside":[],"overlaps":[],"tiny":[]}' "</title>"
OVERFLOWING_AUDIT = (
    f"<title>{AUDIT_MARKER}"
    '{"tall":180,"outside":[],"overlaps":[],"tiny":[]}'
    "</title>"
)


def _page(body: str = "<p>94.6%</p>") -> str:
    return (
        "<!DOCTYPE html><html><head><style>"
        f"body{{margin:0;width:{INFOGRAPHIC_WIDTH}px;height:{INFOGRAPHIC_HEIGHT}px}}"
        f"</style></head><body>{body}</body></html>"
    )


class _Reply:
    def __init__(self, html: str) -> None:
        self.output_data = {"html": html}


class _Runtime:
    """유진의 두뇌 대역. 부탁받은 지시문을 그대로 모아 둔다 -- 되돌려 준 문제가
    실제로 다음 지시문에 실려 갔는지 봐야 하기 때문이다."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        del project_id, task_type, response_schema
        self.prompts.append(prompt)
        return _Reply(self._replies[min(len(self.prompts) - 1, len(self._replies) - 1)])


class _Bridge:
    """이 컴퓨터의 크롬 대역. 잰 값을 미리 정해 둔다."""

    def __init__(self, *audits: str) -> None:
        self._audits = list(audits)
        self.rendered: list[str] = []
        self.measured: list[str] = []

    def render(self, *, html, width, height):
        del width, height
        self.rendered.append(html)
        return b"PNG-" + str(len(self.rendered)).encode()

    def measure(self, *, html, width, height):
        del width, height
        self.measured.append(html)
        return self._audits[min(len(self.measured) - 1, len(self._audits) - 1)]


class _Library:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.ingested: list[bytes] = []

    def ingest(self, *, media_type, source, filename, idempotency_key, provenance):
        del media_type, filename, provenance
        if self.fails:
            raise RuntimeError("자리 없음")
        self.ingested.append(Path(source).read_bytes())
        return {"library_asset_id": f"user_{idempotency_key[-8:]}"}


@contextlib.contextmanager
def _scratch(prefix: str, tmp_path: Path = None):  # type: ignore[assignment]
    del prefix
    yield tmp_path


def _service(runtime, bridge, library=None, *, tmp_path=None, clock=None):
    return InfographicService(
        runtime_service=runtime,
        bridge=bridge,
        library_ingest=library,
        _scratch_factory=(lambda prefix: _scratch(prefix, tmp_path)),
        _clock=clock or (lambda: 0.0),
    )


def test_a_clean_first_try_is_not_asked_twice(tmp_path: Path) -> None:
    """한 판이 1~2분이다. 문제가 없는데 또 시키면 창작자는 두 배를 기다린다."""

    runtime = _Runtime(_page())
    bridge = _Bridge(CLEAN_AUDIT)
    made = _service(runtime, bridge, tmp_path=tmp_path).generate(
        project_id="p1", topic="수수료", facts=FACTS
    )
    assert made.attempts == 1
    assert len(runtime.prompts) == 1
    assert made.corrected == ()
    assert made.remaining_problems == ()
    assert made.png_bytes == b"PNG-1"


def test_the_retry_is_told_exactly_what_was_wrong(tmp_path: Path) -> None:
    """**이 시험이 되돌이의 존재 이유다.** "다시 해"만 주면 모델은 같은 실수를
    되풀이한다. 2026-09-07 실측에서 첫 판이 182px 넘쳤고, 그 숫자를 적어 준
    두 번째가 판 안에 들어왔다."""

    runtime = _Runtime(_page("<p>넘침 94.6%</p>"), _page("<p>고침 94.6%</p>"))
    bridge = _Bridge(OVERFLOWING_AUDIT, CLEAN_AUDIT)
    made = _service(runtime, bridge, tmp_path=tmp_path).generate(
        project_id="p1", topic="수수료", facts=FACTS
    )
    assert made.attempts == 2
    assert len(runtime.prompts) == 2
    assert "180px" in runtime.prompts[1], "무엇이 얼마나 틀렸는지 안 알려 줬다"
    assert "고쳐서 다시 내라" in runtime.prompts[1]
    assert made.corrected and "180px" in made.corrected[0]
    # 두 번째 판이 통과했으니 그것이 나가야 한다.
    assert made.png_bytes == b"PNG-2"
    assert made.remaining_problems == ()


def test_a_made_up_number_is_caught_before_the_browser_is_bothered(tmp_path: Path) -> None:
    """글로 잡을 수 있는 것은 그리기 **전에** 잡는다 -- 그려 봐야 알 수 있는 것만
    브라우저를 부른다."""

    runtime = _Runtime(_page("<p>예시 100,000원</p>"), _page())
    bridge = _Bridge(CLEAN_AUDIT)
    _service(runtime, bridge, tmp_path=tmp_path).generate(
        project_id="p1", topic="수수료", facts=FACTS
    )
    # 첫 판은 글 검사에서 막혔으므로 그린 것은 두 번째 판 하나뿐이다.
    assert len(bridge.rendered) == 1
    assert "준 적 없는 숫자" in runtime.prompts[1]


def test_the_second_try_is_skipped_when_there_is_no_time_for_it(tmp_path: Path) -> None:
    """**nginx가 330초에서 끊는다.** 첫 판이 예산의 절반을 넘게 썼으면 한 판 더
    돌 수 없다 -- 돌면 창작자는 우리 문구 대신 프록시의 504 HTML을 본다."""

    ticks = iter([0.0, TOTAL_BUDGET_SECONDS * 0.75])
    runtime = _Runtime(_page("<p>넘침</p>"), _page())
    bridge = _Bridge(OVERFLOWING_AUDIT)
    made = _service(
        runtime, bridge, tmp_path=tmp_path, clock=lambda: next(ticks)
    ).generate(project_id="p1", topic="수수료", facts=FACTS)
    assert made.attempts == 1
    assert len(runtime.prompts) == 1, "시간이 없는데 한 판 더 돌았다"
    # **그래도 그림은 준다.** 4분 기다리고 아무것도 못 받는 것이 가장 나쁘다.
    assert made.png_bytes == b"PNG-1"
    assert made.remaining_problems and "180px" in made.remaining_problems[0]


def test_a_library_failure_does_not_lose_the_picture(tmp_path: Path) -> None:
    """자료실 등록이 실패했다고 방금 2분 걸려 만든 그림을 버리면 안 된다
    (`SceneVideoService._ingest_into_library`와 같은 관례). 왜 실패했는지는
    값으로 돌려준다 -- 삼키면 나중에 알 방법이 없다."""

    made = _service(
        _Runtime(_page()), _Bridge(CLEAN_AUDIT), _Library(fails=True), tmp_path=tmp_path
    ).generate(project_id="p1", topic="수수료", facts=FACTS)
    assert made.png_bytes == b"PNG-1"
    assert made.library_asset_id is None
    assert made.library_error == "RuntimeError"


def test_the_picture_goes_into_the_library_as_itself(tmp_path: Path) -> None:
    """자료실에 들어가야 편집기 `그림` 목록에 뜨고, 60초 뒤 의미검색 색인에도
    들어간다. 안 들어가면 만든 적 없는 것과 같다."""

    library = _Library()
    made = _service(
        _Runtime(_page()), _Bridge(CLEAN_AUDIT), library, tmp_path=tmp_path
    ).generate(project_id="p1", topic="수수료", facts=FACTS)
    assert library.ingested == [b"PNG-1"], "자료실에 들어간 것이 그 그림이 아니다"
    assert made.library_asset_id


def test_no_bridge_says_so_instead_of_asking_for_a_retry() -> None:
    """**꺼진 것과 고장난 것은 다르다.** 다리가 없으면 아무리 다시 눌러도 안 되는데
    "잠시 뒤 다시"라고 말하면 창작자는 계속 누른다."""

    service = InfographicService(runtime_service=_Runtime(_page()), bridge=None)
    with pytest.raises(InfographicUnavailable) as caught:
        service.generate(project_id="p1", topic="수수료", facts=FACTS)
    assert caught.value.reason == "infographic_bridge_not_configured"


def test_a_measurement_we_could_not_read_is_not_treated_as_a_pass(tmp_path: Path) -> None:
    """다리가 답을 안 주는 것과 배치가 멀쩡한 것은 다른 말이다. 못 잰 것을
    통과로 다루면 잘린 그림이 그대로 나간다."""

    made = _service(
        _Runtime(_page(), _page()), _Bridge("<title>재지 못함</title>"), tmp_path=tmp_path
    ).generate(project_id="p1", topic="수수료", facts=FACTS)
    assert made.remaining_problems and "눈으로" in made.remaining_problems[0]


def test_an_empty_topic_is_refused_before_anything_is_asked() -> None:
    runtime = _Runtime(_page())
    with pytest.raises(InfographicUnavailable) as caught:
        InfographicService(runtime_service=runtime, bridge=_Bridge(CLEAN_AUDIT)).generate(
            project_id="p1", topic="   ", facts=FACTS
        )
    assert caught.value.reason == "infographic_topic_empty"
    assert runtime.prompts == []
