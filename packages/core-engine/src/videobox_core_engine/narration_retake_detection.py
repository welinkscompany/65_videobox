"""녹음한 목소리에서 "이 구간은 다시 들어봐야겠다" 싶은 곳을 찾는다.

owner 요청(2026-08-29): "녹음이 끝나면 잘못 발음하는 거 컷 편집으로 날리고."
기존 컷 자동 감지(`auto_cut.py`)는 화면 전환·암전 같은 **영상** 신호만 본다
(`videobox_core_engine.auto_cut.AutoCutPlanner`) -- 목소리만 있는 녹음에는 쓸 게
없다. 여기는 그 반대로 **받아쓰기 결과**(글자·자신도)만 보고 후보를 고른다.

**정직하게 밝혀 둘 것**: 이건 발음을 실제로 채점하는 AI가 아니다. 두 가지
단순한 신호만 쓴다.
1. 받아쓰기 자신도(`confidence`)가 낮은 구간 -- STT가 잘 못 들었다는 뜻이고,
   보통 발음이 뭉개졌거나 말이 꼬였을 때 낮게 나온다.
2. "다시 할게요"류 재시도 표현이 들어간 구간 -- 스스로 다시 말하겠다고 밝힌
   문장은 그 자체가 버릴 말이고, 그 앞 구간은 버려진 시도일 가능성이 높다.

**조용히 지우지 않는다.** 이 함수는 후보만 골라 돌려준다 -- 실제로 뺄지는
화면에서 owner가 하나씩 확인하고 고른다(§10.13, 사람 게이트).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

RetakeReason = Literal["low_confidence", "retry_cue", "retry_cue_precursor"]

#: 자신도가 이 값 미만이면 후보다. STT가 확실히 못 들었다는 뜻 -- 실측
#: 픽스처(`tests/test_narration_retake_detection.py`)의 정상 발화는 대부분
#: 0.9대였고, 뭉개진 말은 0.5 안팎으로 뚝 떨어졌다.
DEFAULT_CONFIDENCE_THRESHOLD = 0.55

#: 스스로 다시 말하겠다고 밝히는 표현들. 문장 **맨 앞**에 오는 것만 본다 --
#: "다시"가 문장 중간에 있으면("이걸 다시 보면") 재시도 표현이 아니라 그냥
#: 낱말이라 오탐이 는다.
_RETRY_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"^\s*(아|어|음)?\s*[,.]?\s*(잠깐|잠시만요?)",
        r"^\s*(아|어)?\s*[,.]?\s*다시\s*(할게요|말할게요|해볼게요|갈게요)?",
        r"^\s*죄송(해요|합니다)?[,.]?\s*다시",
        r"^\s*아니\s*[,.]?\s*(다시)?",
    )
)


@dataclass(slots=True, frozen=True)
class RetakeCandidate:
    segment_index: int
    start_sec: float
    end_sec: float
    text: str
    reason: RetakeReason


def _is_retry_cue(text: str) -> bool:
    stripped = text.strip()
    return any(pattern.match(stripped) for pattern in _RETRY_CUE_PATTERNS)


def detect_retake_candidates(
    segments: Sequence[Mapping[str, Any]],
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> tuple[RetakeCandidate, ...]:
    """받아쓴 구간 목록에서 다시 들어볼 후보를 고른다.

    입력 순서를 그대로 유지한 채(시간순) 후보만 뽑는다. 한 구간이 여러
    이유에 걸려도 하나로만 보고한다 -- 낮은 자신도가 재시도 표현보다 먼저다
    (화면에 이유를 하나만 보여줘야 owner가 "왜"를 한 번에 읽는다).
    """

    candidates: list[RetakeCandidate] = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start_sec = float(segment.get("start_sec") or 0.0)
        end_sec = float(segment.get("end_sec") or 0.0)
        confidence = segment.get("confidence")
        if confidence is not None and float(confidence) < confidence_threshold:
            candidates.append(RetakeCandidate(index, start_sec, end_sec, text, "low_confidence"))
            continue
        if _is_retry_cue(text):
            candidates.append(RetakeCandidate(index, start_sec, end_sec, text, "retry_cue"))
            # 재시도 표현 바로 앞 구간은 버려진 시도였을 가능성이 높다 -- 이미
            # 후보가 아니었을 때만 얹는다(중복 후보를 만들지 않는다).
            if index > 0 and not any(candidate.segment_index == index - 1 for candidate in candidates):
                previous = segments[index - 1]
                previous_text = str(previous.get("text") or "").strip()
                if previous_text:
                    candidates.append(
                        RetakeCandidate(
                            index - 1,
                            float(previous.get("start_sec") or 0.0),
                            float(previous.get("end_sec") or 0.0),
                            previous_text,
                            "retry_cue_precursor",
                        )
                    )
    candidates.sort(key=lambda candidate: candidate.segment_index)
    return tuple(candidates)


__all__ = ["RetakeCandidate", "RetakeReason", "DEFAULT_CONFIDENCE_THRESHOLD", "detect_retake_candidates"]
