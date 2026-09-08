"""기억 사서가 대화 기록을 증류하기 전에 정형구를 거른다.

**고정 이름 목록이 아니라 반복 패턴으로 학습한다.** 사람이 한 말과 시스템이
낸 고정 문구(참조 선택 안내, 범위 밖 요청 안내 같은 것)를 코드 이름으로
구분하지 않는다 -- VideoBox는 이런 문구가 바뀔 때마다 이 파일을 고쳐야 하는
게 아니라, "여러 번 그대로 반복되면 정형구"라는 성질 하나로 판정한다.

임계값은 참고 구현(louis-personal-hermes의 Rumi Wiki Librarian,
`scripts/consolidate-rumi-conversation-notes-runtime.py`)에서 그대로 가져왔다
-- 그쪽은 이미 실패를 겪고 고친 값이다(짧은 문단이 3회 미만 기준으로는
새어 나갔다). VideoBox 쪽 실측(2026-09-08, `director_proposals.py`의
"어느 참조인지 선택해주세요."·"참조를 확인했습니다." 같은 15자 안팎 고정
응답과 "이 요청은 유진이 직접 할 수 없어요..." 같은 80자 이상 고정 응답)도
이 값이 40자 경계 양쪽에 자연스럽게 걸리는 것을 확인했다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

#: 이 글자 수 이상이면 "긴 문단" -- 2번만 반복돼도 정형구로 본다.
BOILERPLATE_MIN_CHARS = 40

#: 반복을 세는 창. 너무 좁으면 스킬 문서처럼 드물게(한 번만) 등장하는 긴
#: 시스템 문서가 "새 지식"으로 오분류된다(Rumi가 실제로 겪은 사고).
BOILERPLATE_LOOKBACK_DAYS = 90

#: 대괄호로 시작하는 문단은 반복 여부와 상관없이 시스템 주입으로 본다.
_INJECTED_PARAGRAPH_PREFIX = "["


@dataclass(frozen=True, slots=True)
class TimestampedParagraph:
    text: str
    occurred_at: datetime


def _boilerplate_threshold(text: str) -> int:
    return 2 if len(text) >= BOILERPLATE_MIN_CHARS else 3


def find_boilerplate(
    paragraphs: list[TimestampedParagraph],
    *,
    as_of: datetime,
    lookback_days: int = BOILERPLATE_LOOKBACK_DAYS,
) -> frozenset[str]:
    """`lookback_days` 창 안에서 임계값 이상 그대로 반복된 문단 텍스트 집합.

    반복 판정은 **정확히 같은 문자열**만 센다 -- 비슷한 문장을 같은 것으로
    묶으면(의미 기반 군집화) 진짜 반복 정형구와 "우연히 비슷한 진짜 발언"을
    못 가른다. 이 저장소는 기억 판단에서 항상 정확히 일치하는 것만 채택하는
    원칙을 쓴다(`yujin_memory_service.py`의 로컬 대조와 같다).
    """
    window_start = as_of - timedelta(days=lookback_days)
    counts: dict[str, int] = {}
    for paragraph in paragraphs:
        if paragraph.occurred_at < window_start or paragraph.occurred_at > as_of:
            continue
        stripped = paragraph.text.strip()
        if not stripped:
            continue
        counts[stripped] = counts.get(stripped, 0) + 1
    return frozenset(
        text for text, count in counts.items() if count >= _boilerplate_threshold(text)
    )


def is_injected_paragraph(text: str) -> bool:
    """대괄호로 시작하는 문단은 반복 여부와 무관하게 시스템 주입으로 본다."""
    return text.strip().startswith(_INJECTED_PARAGRAPH_PREFIX)


def strip_boilerplate(
    paragraphs: list[TimestampedParagraph],
    *,
    as_of: datetime,
    lookback_days: int = BOILERPLATE_LOOKBACK_DAYS,
    max_user_paragraph_chars: int | None = None,
) -> list[TimestampedParagraph]:
    """정형구·대괄호 주입 문단·(선택) 지나치게 긴 문단을 뺀 나머지를 순서대로 돌려준다.

    `max_user_paragraph_chars`는 사용자 발화에만 적용하는 안전장치다 --
    실제로는 이 함수가 화자를 구분하지 않으므로, 호출하는 쪽이 사용자 발화만
    모아서 넘길 때만 뜻이 있다.
    """
    boilerplate = find_boilerplate(paragraphs, as_of=as_of, lookback_days=lookback_days)
    kept: list[TimestampedParagraph] = []
    for paragraph in paragraphs:
        stripped = paragraph.text.strip()
        if not stripped or is_injected_paragraph(stripped):
            continue
        if stripped in boilerplate:
            continue
        if max_user_paragraph_chars is not None and len(stripped) > max_user_paragraph_chars:
            continue
        kept.append(paragraph)
    return kept
