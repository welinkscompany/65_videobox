"""확정된 대본에서 유튜브 제목 후보 여러 개를 뽑는다.

**제목 선택**은 `decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`가
못박은 사람 게이트 셋 중 하나다. `script_draft_writer.py`가 대본 확정 게이트를
채우는 것과 같은 자리에서, 대본이 확정된 순간 제목 후보도 함께 대표님 결재함에
올린다(AK-System Hermes 결재함 큐, W1015).

**같은 세 가지를 지킨다** (`script_draft_writer.py`와 같은 이유):

1. 구조화 출력으로만 묻는다 -- 자유형으로 물으면 생각 과정이 새어 나온다.
2. 못 하면 거절한다 -- 빈 제목이나 영어 제목을 그대로 넘기지 않는다.
3. 이미 확정된 대본 전문을 그대로 싣는다 -- 새로 요약해 묻지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from videobox_provider_interfaces.llm import LLMTaskType

_HANGUL = re.compile(r"[가-힣]")

DEFAULT_CANDIDATE_COUNT = 3

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["titles"],
    "properties": {
        "titles": {"type": "array", "items": {"type": "string"}},
    },
}

_INSTRUCTION = """당신은 유튜브 제목을 짓는 카피라이터입니다.

아래 확정된 대본을 읽고, 이 영상에 어울리는 제목 후보를 {count}개 씁니다.

지켜야 할 것:
- 반드시 한국어로만 답합니다. 영어 문장을 섞지 않습니다.
- 제목마다 서로 다른 각도(궁금증·숫자·직설 등)를 씁니다. 비슷한 제목을 반복하지
  않습니다.
- 각 제목은 한 줄, 40자 이내로 씁니다.
- 생각 과정을 적지 않습니다. 결과만 적습니다.

대본:
{script_text}
"""


@dataclass(slots=True, frozen=True)
class TitleCandidatesUnavailable(Exception):
    """유진이 쓸 수 있는 제목 후보를 돌려주지 못했다. **조용히 넘기지 않는다.**"""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class TitleCandidateWriter:
    runtime_service: Any

    def write(
        self,
        *,
        project_id: str,
        script_text: str,
        count: int = DEFAULT_CANDIDATE_COUNT,
    ) -> tuple[str, ...]:
        script = (script_text or "").strip()
        if not script:
            raise TitleCandidatesUnavailable("title_candidates_script_empty")
        asked = max(2, int(count))
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.TITLE_CANDIDATES,
                prompt=_INSTRUCTION.format(count=asked, script_text=script),
                response_schema=_RESPONSE_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 - 로컬 런타임 경계
            raise TitleCandidatesUnavailable(
                "title_candidate_writer_unavailable"
            ) from exc

        output = getattr(response, "output_data", None) or {}
        titles = _read_titles(output.get("titles"))
        if not titles:
            raise TitleCandidatesUnavailable("title_candidates_empty")
        if any(not _HANGUL.search(title) for title in titles):
            raise TitleCandidatesUnavailable("title_candidates_not_korean")
        return titles


def _read_titles(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    seen: set[str] = set()
    titles: list[str] = []
    for item in raw:
        title = str(item or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        titles.append(title)
    return tuple(titles)


__all__ = [
    "DEFAULT_CANDIDATE_COUNT",
    "TitleCandidatesUnavailable",
    "TitleCandidateWriter",
]
