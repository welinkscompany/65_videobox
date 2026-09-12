"""숏폼을 **퍼질까로** 고른다. 자르는 것이 아니라 판단이다.

owner 지시(2026-09-12): "단순히 자르는것보다 자극적으로 숏폼이 확산할수 있을정도로
llm 이 구분 하도록 생각하면서 만들어야지."

그리고 "숏폼을 저렇게 많이 쪼개는게 필요해? 시간을 정하는게 나을까? 유진이 알아서
쪼개는게 좋을까?"에 대한 답: **유진이 정한다. 다만 쪼갠 장면이 아니라 전사의 발화를
읽고 정한다.**

## 무엇이 2026-09-11 판과 다른가

| | 전(2026-09-11) | 지금 |
|---|---|---|
| 기준 | 훅·결론·숫자 -- **형식** | **이게 퍼질까** |
| 후보 좁히기 | 숫자·결과 **낱말**로 먼저 걸렀다 | **안 거른다.** 전 구간이 유진에게 간다 |
| 읽는 재료 | 장면 자막 요약 | **전사의 발화**(글 + 시각) |
| 조립 | 낱개 점수의 합집합 | 유진이 **이어진 숏폼 후보 둘·셋을 짜고 하나를 고른다** |
| 길이 | 60초 "상한"인데 넘길 수 있었다 | **20~60초 범위**, 넘으면 뒤에서 덜어낸다 |

### 왜 형식이 아니라 확산인가

"훅·결론·숫자"는 *생김새*다. 대표님이 묻는 것은 **"이게 퍼질까"**다. 둘은 겹치지만
같지 않다 -- 결론이라고 다 퍼지지 않고(평평한 요약이 제일 흔하다), 퍼지는 한마디는
대개 중간에 있다. 대표님 실제 영상에서 가장 퍼질 한마디는
`"그걸 알면 제가 팔지 뭐하러 알려 줄까요?"`(55~60초)인데 **숫자도 결과 낱말도 없어서**
옛 추리기가 유진 눈에서 감출 수 있었다.

### 왜 낱말로 안 거르는가

거르면 판단할 것이 손에 오지 않는다. 대신 **발화를 묶어서** 부르는 횟수를 묶는다 --
`MAX_JUDGED_PASSAGES`개를 넘으면 짧은 대목끼리 합쳐 줄인다. 버리지 않고 굵게 만든다.
그래서 **영상의 어느 구간도 유진 눈에서 빠지지 않는다.**

### 기다리기 -- 30초 상한이 이 기능을 통째로 못 쓰게 만들고 있었다 (2026-09-12 정정)

**첫 판(같은 날 아침)의 예산 계산이 틀렸다.** "훑기 6회 + 짜기 1회, 한 호출 30초
상한이니 벽시계 210초"는 산수로는 맞지만, **30초 안에 답이 오지 않는다**는 것을
안 재고 세운 계산이었다. 대표님 실제 영상(94장면·발화 213개)으로 컨테이너에서
호출마다 재 보니 이렇다.

| 무엇 | 실측 |
|---|---|
| 훑기 한 호출 (차례로, 상한 30초) | 여섯 중 **넷이 30.0초에 끊겼다.** 30초 안에 온 둘은 고른 대목이 1개·0개 |
| 훑기 한 호출 (넉넉한 상한) | 34.8 / 56.9 / 79.3 / 105.2 / 111.8 / 129.8초 -- **여섯 다 답하고** 대목마다 4~5점 |
| 짜기 한 호출 (넉넉한 상한) | **266.8초.** 후보 3개와 이유 셋이 제대로 왔다 |

왜 이렇게 느린가: 대표님 기계에 다른 프로젝트의 모델이 같이 올라가 있어 32GB 카드에
45GB를 올리려 하고, 그래서 초당 1~2낱말로 떨어진다. owner 결정(2026-09-12)은
**"다른모댈 쓸데는 잠시 기다리자"** -- 기다린다.

그런데 상한만 올리면 프록시가 끊는다(`docker/workspace-nginx.conf` 330초). 그래서 둘이다.

1. **묶음을 동시에 묻는다.** 차례로 부르면 여섯 묶음이 최악 1800초지만, 동시에
   부르면 벽시계가 **가장 느린 한 호출**이 된다(실측 129.8~221.5초, 여섯 다 답함).
2. **예산을 시계로 지킨다.** 한 호출을 얼마나 기다릴지도 예산이 정한다
   (`scan_wait_seconds`·`compose_wait_seconds`). 같은 요청 안에서 도는 부르는 쪽
   (유진 채팅·처음 만들기)은 `SYNCHRONOUS_BUDGET_SECONDS`를 넘지 않는다 -- 짜기를
   시작할 시간이 없으면 시작하지 않고 그 사실을 문구로 말한다(인포그래픽의
   `TOTAL_BUDGET_SECONDS`와 같은 방식). 화면의 `다시 만들기`는 **뒤에서 돌기**
   때문에 벽이 없어 `BACKGROUND_BUDGET_SECONDS`까지 기다린다.

**실물로 잰 것(2026-09-12, 화면과 같은 HTTP 길로):** 훑기 여섯 묶음 동시에
221.5초에 **94장면 전부** 읽고, 짜기까지 합쳐 445~558초. 상한을 150초로 두었을
때는 여섯 중 셋이 끊겨 **94장면 중 44개**만 읽혔다 -- 그래서 상한을 예산에서
끌어내게 바꿨다. 상한을 올리는 것은 **빠른 날에는 공짜다**: 묶음이 동시에 도니까
훑기 단계는 상한만큼 걸리는 게 아니라 가장 느린 한 호출이 끝나면 끝난다.

### 로그 -- "못 찾았다"와 "못 물어봤다"는 다른 원인이다

첫 판은 시간 초과한 묶음을 조용히 넘겼다. 그래서 여섯 중 넷이 끊겼는데도 화면
문구는 "유진이 읽어 봤지만 못 찾아서"라고 말했다. 기록된 사고와 같은 자리다 --
유진이 "없다"고 할 때 **무엇을 받고 무엇을 돌려줬는지**를 남겨야 한다. 이제 묶음
하나하나가 로그에 남는다(몇 초 걸렸는지·무엇을 골랐는지·왜 못 받았는지).

### 생각할 여지

`response_format`이 json_schema라 LM Studio가 문법을 강제하고, 그래서 모델은
`<think>` 덩이를 **낼 수 없다**(2026-09-12 실측: 같은 모델이 스키마 없이는
`<think>`를 내고 스키마를 주면 안 낸다). 그러니 생각할 자리를 **스키마 안에** 둔다 --
짜기 응답의 첫 칸이 `thinking`이고, 그 다음이 후보들이다. 대가는 출력 토큰이고
이득은 후보를 짜기 전에 무엇이 사람을 멈추게 하는지 먼저 쓰게 되는 것이다.

## 유진이 대답을 못 하면

**조용히 글자 수 세기로 내려가지 않는다.** `judged_by="caption_density"`와 사유를
실어 화면 문구까지 보낸다(2026-09-11 결정, 그대로 유지). 짜기만 실패했으면 고르기
결과는 살리되 `spread_reason`을 비우고 문구로 밝힌다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Literal

from videobox_core_engine.highlight_scoring import (
    select_highlight_segment_ids,
    target_duration_sec,
)
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType

_LOGGER = logging.getLogger(__name__)

#: 한 번에 보내는 대목 수. **12가 아니라 8인 것은 실측 때문이다**(2026-09-12).
#: 옛 값 12는 장면 자막 12개(대표님 판에서 약 64초 분량의 말)를 기준으로 정해졌는데,
#: 대목은 발화를 묶어 하나가 10초쯤 되므로 12개면 말이 약 120초 분량이 된다.
#: 대표님 실제 영상으로 재 보니 그 크기에서는 호출이 30초 상한을 넘겨 4묶음 중
#: 3개가 통째로 실패했다. 8개면 약 80초 분량이고, 같은 조건에서 6묶음이 다 답했다.
SCAN_BATCH_SIZE = 8
#: 훑기 호출 상한. 아래 짜기 1회를 더해 **최대 7회**다.
MAX_SCAN_CALLS = 6
#: 유진이 읽는 대목 수 상한. 넘으면 대목을 **합쳐서** 줄인다(버리지 않는다).
MAX_JUDGED_PASSAGES = SCAN_BATCH_SIZE * MAX_SCAN_CALLS
#: 한 대목의 최소 길이. 이보다 짧게 쪼개면 문장 조각이 되어 판단할 거리가 없다.
PASSAGE_MIN_SEC = 8.0
#: 숏폼 길이 **범위**. 목표 하나를 정하면 말 중간에서 잘리고, 상한만 두면
#: 8초짜리가 나온다. 플랫폼(쇼츠·릴스·틱톡)이 다 받는 구간이 20~60초다.
SHORT_FORM_MIN_TARGET_SEC = 20.0
SHORT_FORM_MAX_TARGET_SEC = 60.0
#: 유진에게 짜 보라고 할 후보 숏폼 수.
COMPOSE_CANDIDATES = 3

#: 훑기 한 호출을 기다리는 **최대** 상한. 실제로 쓰는 값은 예산이 정한다
#: (`scan_wait_seconds`). **실측으로 정했다**(2026-09-12, 대표님 영상): 묶음이
#: 34.8~143초에 답하고, 150초 상한에서는 여섯 중 셋이 끊겨 94장면 중 44개만
#: 읽혔다. 30초로는 여섯 중 넷이 끊겼다.
SCAN_WAIT_CEILING_SECONDS = 300
#: 짜기 한 호출을 기다리는 **최대** 상한. 실제로 쓰는 값은 남은 예산이 정한다
#: (`compose_wait_seconds`). 실측(2026-09-12)으로 266.8초·295.0초에 답했고, 다른
#: 작업이 같은 모델을 쓰는 동안에는 **330초에서 끊겼다** -- 그때 화면에 나갈
#: "왜 퍼질까"가 사라진다. 그래서 벽이 없는 자리에서는 프록시가 줄 수 있는
#: 것보다 더 준다.
COMPOSE_WAIT_CEILING_SECONDS = 600
#: 짜기를 아예 시작해 볼 최소 남은 시간. 이보다 적으면 시작하지 않는다 -- 시작해서
#: 끊기면 기다린 시간만 버리고 결과는 같다.
COMPOSE_MIN_WAIT_SECONDS = 30
#: **같은 요청 안에서** 끝내야 하는 부르는 쪽의 예산(유진 채팅·처음 만들기).
#: nginx가 330초에 끊는다(`docker/workspace-nginx.conf`) -- 넘기면 대표님은 우리
#: 한국말 대신 프록시의 504 HTML을 본다. 인포그래픽의 `TOTAL_BUDGET_SECONDS`와
#: 같은 자리이고 `tests/test_compose_contract.py`가 두 값을 맞대 본다.
SYNCHRONOUS_BUDGET_SECONDS = 300
#: 화면의 `다시 만들기`는 뒤에서 돌기 때문에 프록시 벽이 없다. 실측(훑기 130 +
#: 짜기 267 = 약 400초)이 이 값을 요구한다 -- 한 요청 안에서는 못 끝내는 일이다.
BACKGROUND_BUDGET_SECONDS = 900


def scan_wait_seconds(budget_seconds: float) -> int:
    """훑기 한 호출을 기다릴 시간. **예산의 절반까지**, 상한 안에서.

    절반인 이유: 나머지 절반은 짜기 몫이다. 한 호출에 예산을 다 주면 짜기가 아예
    못 돌아 화면에 나갈 "왜 퍼질까"가 사라진다.

    **상한을 올리는 것은 빠른 날에는 공짜다.** 묶음이 동시에 도니까 훑기 단계는
    상한만큼 걸리는 게 아니라 가장 느린 한 호출이 끝나면 끝난다(실측 129.8초).
    올린 값은 느린 날에만 쓰이고, 그때 기다리는 것이 owner 결정이다.
    """
    return int(max(1.0, min(float(SCAN_WAIT_CEILING_SECONDS), budget_seconds / 2.0)))


def compose_wait_seconds(budget_seconds: float, spent_seconds: float) -> int:
    """짜기 한 호출을 기다릴 시간. **남은 예산 전부**, 상한 안에서.

    훑기와 달리 절반으로 나누지 않는다 -- 짜기는 마지막 호출이라 남은 것을 다 써도
    뒤에 밀릴 일이 없다. 실측 266.8~295.0초이고 바쁠 때는 330초도 부족했다.
    """
    return int(min(float(COMPOSE_WAIT_CEILING_SECONDS), budget_seconds - spent_seconds))

#: 예전 이름. 부르는 자리와 시험이 쓰고 있어 남겨 둔다.
MAX_JUDGED_SCENES = MAX_JUDGED_PASSAGES
JUDGE_BATCH_SIZE = SCAN_BATCH_SIZE

_SCAN_SCHEMA_VERSION = "videobox.short-form-spread-scan.v1"
_COMPOSE_SCHEMA_VERSION = "videobox.short-form-compose.v1"
#: 훑기 프롬프트에서 대목 목록이 시작하는 자리. 시험 대역이 이 표시로 자른다.
_SCAN_MARKER = "고를 장면:"
_COMPOSE_MARKER = "고를 대목:"

JudgedBy = Literal["yujin", "caption_density"]


@dataclass(slots=True, frozen=True)
class ShortFormScenePick:
    """고른 결과와 **누가 골랐는지**, 그리고 **왜 퍼질지**. 셋은 항상 같이 다닌다."""

    segment_ids: tuple[str, ...]
    judged_by: JudgedBy
    notice: str
    scenes_total: int
    scenes_read_by_yujin: int
    fallback_reason: str | None = None
    #: 유진이 댄 "이 숏폼이 왜 퍼질지" 한 줄. **화면까지 간다**
    #: (`scene_pick_payload` -> `api.ts` -> `shortFormNotice.ts`).
    #: 유진이 짜기를 못 했으면 `None`이고, 그때 문구가 그 사실을 말한다.
    spread_reason: str | None = None


@dataclass(slots=True, frozen=True)
class _Passage:
    """유진이 읽고 판단하는 한 덩이. 전사의 발화 여럿을 묶은 것이다.

    `start_sec`/`end_sec`는 **원본 소재 안의 시각**이다. 판 위의 자리가 아니다 --
    대표님이 장면을 끌어 옮겼어도 전사와 맞물리게 하려면 원본 좌표여야 한다.
    """

    start_sec: float
    end_sec: float
    text: str

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _segment_source_bounds(segment: Mapping[str, object]) -> tuple[float, float]:
    """장면이 원본 소재의 어느 구간을 쓰는가.

    `source_offset_sec`이 원본 안의 시작점이고 길이는 판 위 길이와 같다. 이 칸이
    없는 옛 장면·시험 입력은 판 위 자리를 그대로 쓴다 -- 둘이 같은 판이 흔하다.
    """
    board_duration = max(0.0, _number(segment.get("end_sec")) - _number(segment.get("start_sec")))
    if "source_offset_sec" in segment and segment.get("source_offset_sec") is not None:
        start = _number(segment.get("source_offset_sec"))
    else:
        start = _number(segment.get("start_sec"))
    return start, start + board_duration


def _passages_from_utterances(
    utterances: Sequence[Mapping[str, object]],
    *,
    board_bounds: Sequence[tuple[float, float]],
    limit: int,
) -> tuple[_Passage, ...]:
    """전사의 발화를 **문장 끝에서** 묶어 판단할 덩이로 만든다.

    셋을 지킨다.

    1. **판에 없는 말은 안 묶는다.** 판이 원본의 앞 2분만 쓰고 있으면 5분짜리
       전사의 뒤쪽은 고를 수 없다 -- 골라 봐야 이을 장면이 없다.
    2. **말 중간에서 끊지 않는다.** 경계는 늘 발화의 끝이다.
    3. **상한을 넘으면 버리지 않고 합친다.** 가장 짧은 것부터 옆과 붙인다.
       그래서 영상의 어느 구간도 유진 눈에서 빠지지 않는다.
    """
    rows: list[tuple[float, float, str]] = []
    for utterance in utterances:
        if not isinstance(utterance, Mapping):
            continue
        text = str(utterance.get("text") or "").strip()
        start = _number(utterance.get("start_sec"))
        end = _number(utterance.get("end_sec"))
        if not text or end <= start:
            continue
        if board_bounds and not any(
            start < bound_end and end > bound_start for bound_start, bound_end in board_bounds
        ):
            continue
        rows.append((start, end, text))
    if not rows:
        return ()
    rows.sort(key=lambda row: row[0])

    groups: list[list[tuple[float, float, str]]] = []
    current: list[tuple[float, float, str]] = []
    for row in rows:
        current.append(row)
        if current[-1][1] - current[0][0] >= PASSAGE_MIN_SEC:
            groups.append(current)
            current = []
    if current:
        if groups:
            groups[-1].extend(current)
        else:
            groups.append(current)

    # 상한을 넘으면 **가장 짧은 덩이를 옆에 붙여** 줄인다. 잘라 버리면 그 구간이
    # 유진 눈에서 사라지고, 그게 이 조각이 고치려는 결함이다.
    while limit > 0 and len(groups) > limit:
        shortest = min(
            range(len(groups)),
            key=lambda index: groups[index][-1][1] - groups[index][0][0],
        )
        if shortest == 0:
            target = 1
        elif shortest == len(groups) - 1:
            target = len(groups) - 2
        else:
            before = groups[shortest - 1][-1][1] - groups[shortest - 1][0][0]
            after = groups[shortest + 1][-1][1] - groups[shortest + 1][0][0]
            target = shortest - 1 if before <= after else shortest + 1
        low, high = sorted((shortest, target))
        merged = groups[low] + groups[high]
        groups[low : high + 1] = [merged]

    return tuple(
        _Passage(
            start_sec=group[0][0],
            end_sec=group[-1][1],
            text=" ".join(row[2] for row in group),
        )
        for group in groups
    )


def _passages_from_segments(
    segments: Sequence[Mapping[str, object]], *, limit: int
) -> tuple[_Passage, ...]:
    """전사가 없을 때. 장면 하나가 대목 하나다.

    **같은 흐름을 두 벌 만들지 않기 위해서** 장면도 같은 `_Passage`로 바꾼다.
    이 저장소는 같은 로직이 두 자리로 갈라져 한쪽만 고쳐지는 함정에 여러 번
    걸렸다. 재료가 둘이고 판단 흐름은 하나다.
    """
    rows = [
        _Passage(
            start_sec=_segment_source_bounds(segment)[0],
            end_sec=_segment_source_bounds(segment)[1],
            text=str(segment.get("caption_text") or segment.get("text") or "").strip(),
        )
        for segment in segments
    ]
    if limit <= 0 or len(rows) <= limit:
        return tuple(rows)
    # 장면이 상한보다 많으면 이웃끼리 묶는다. 여기서도 버리지 않는다.
    per = -(-len(rows) // limit)
    merged: list[_Passage] = []
    for start in range(0, len(rows), per):
        chunk = rows[start : start + per]
        merged.append(
            _Passage(
                start_sec=chunk[0].start_sec,
                end_sec=chunk[-1].end_sec,
                text=" ".join(item.text for item in chunk if item.text),
            )
        )
    return tuple(merged)


def _segment_ids_for_passages(
    segments: Sequence[Mapping[str, object]], passages: Sequence[_Passage]
) -> tuple[str, ...]:
    """고른 대목이 걸치는 장면들. **판 위 시간 순서**로 돌려준다.

    자르는 경계는 여전히 장면 경계다(계약은 `selected_segment_ids` 그대로).
    대표님 판처럼 장면이 발화 끝점에서 쪼개져 있으면 둘이 사실상 같고, 장면이
    굵으면 유진이 고른 것보다 굵게 잘린다 -- 그 사실은 보고서에 적혀 있다.
    """
    wanted: set[str] = set()
    for segment in segments:
        segment_id = str(segment.get("segment_id") or "")
        if not segment_id:
            continue
        start, end = _segment_source_bounds(segment)
        for passage in passages:
            if start < passage.end_sec and end > passage.start_sec:
                wanted.add(segment_id)
                break
    return tuple(
        str(segment["segment_id"]) for segment in segments if str(segment["segment_id"]) in wanted
    )


def _clamp_to_max_sec(
    segments: Sequence[Mapping[str, object]],
    segment_ids: Sequence[str],
    *,
    max_target_sec: float,
) -> tuple[str, ...]:
    """길이 상한을 **실제로** 지킨다 -- 넘긴 뒤에 멈추지 않는다.

    2026-09-12 리뷰가 잡은 것: 옛 코드는 담고 나서 넘었는지 봤기 때문에 60초
    "상한"이 실은 목표였고 실물에서 61.48초가 나왔다. 여기서는 담기 전에 보고,
    넘치면 **뒤에서** 덜어낸다 -- 앞이 훅이라 앞을 지켜야 한다.
    """
    duration_by_id = {
        str(segment.get("segment_id") or ""): max(
            0.0, _number(segment.get("end_sec")) - _number(segment.get("start_sec"))
        )
        for segment in segments
    }
    kept: list[str] = []
    filled = 0.0
    for segment_id in segment_ids:
        duration = duration_by_id.get(segment_id, 0.0)
        if kept and filled + duration > max_target_sec:
            break
        kept.append(segment_id)
        filled += duration
    return tuple(kept)


def _assemble_within_ceiling(
    segments: Sequence[Mapping[str, object]],
    passages: Sequence[_Passage],
    priority: Sequence[int],
    *,
    max_target_sec: float,
) -> tuple[str, ...]:
    """중요한 대목부터 담되 **상한을 넘기지 않는다**. 결과는 판 위 시간 순서.

    두 가지를 일부러 이렇게 했다.

    1. **담기 전에 본다.** 담고 나서 "넘었나"를 보면 상한이 목표가 된다 --
       2026-09-12 실물에서 60초 "상한"이 61.48초로 나온 이유다.
    2. **안 맞는 대목은 건너뛰고 계속 본다**(`break`가 아니라 `continue`).
       긴 대목 하나가 자리를 못 찾아도 뒤의 짧은 알맹이는 들어갈 수 있다.

    그리고 덜어낼 때는 **뒤가 아니라 점수 낮은 것**부터다. 뒤에서 자르면 남에게
    보낼 이유가 되는 마지막 한마디가 제일 먼저 사라진다.
    """
    duration_by_id = {
        str(segment.get("segment_id") or ""): max(
            0.0, _number(segment.get("end_sec")) - _number(segment.get("start_sec"))
        )
        for segment in segments
    }
    selected: set[str] = set()
    filled = 0.0
    for index in priority:
        if not 0 <= index < len(passages):
            continue
        extra = [
            segment_id
            for segment_id in _segment_ids_for_passages(segments, [passages[index]])
            if segment_id not in selected
        ]
        if not extra:
            continue
        added = sum(duration_by_id.get(segment_id, 0.0) for segment_id in extra)
        if selected and filled + added > max_target_sec:
            continue
        selected.update(extra)
        filled += added
    return tuple(
        str(segment["segment_id"]) for segment in segments if str(segment["segment_id"]) in selected
    )


def _scan_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": _SCAN_SCHEMA_VERSION},
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "scene": {"type": "integer"},
                        "worth": {"type": "integer"},
                    },
                    "required": ["scene", "worth"],
                },
            },
        },
        "required": ["schema_version", "picks"],
    }


def _compose_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            # **`thinking`이 첫 칸인 것은 일부러다.** 스키마가 문법을 강제해
            # `<think>`를 못 내므로, 생각할 자리를 스키마 안 맨 앞에 둔다.
            #
            # **길이를 묶는 것도 일부러다.** 2026-09-12 실측: 이 칸을 안 묶으면
            # 짜기 호출이 요청 상한을 넘겨 통째로 실패했고(같은 프롬프트를 이 칸
            # 없이 보내면 답이 왔다), 그러면 화면에 나갈 "왜 퍼질까"가 사라진다.
            # 생각할 여지를 주는 것과 호출이 살아 있는 것 사이의 교환이고,
            # 두세 줄이면 후보를 짜기 전에 기준을 세우기에 충분하다.
            "thinking": {"type": "string", "maxLength": 300},
            "candidates": {
                "type": "array",
                "maxItems": COMPOSE_CANDIDATES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "lines": {"type": "array", "maxItems": 12, "items": {"type": "integer"}},
                        # 화면 문구에 그대로 붙는 한 줄이다. 길면 대표님이 못 읽는다.
                        "reason": {"type": "string", "maxLength": 300},
                    },
                    "required": ["lines", "reason"],
                },
            },
            "chosen": {"type": "integer"},
            "schema_version": {"const": _COMPOSE_SCHEMA_VERSION},
        },
        "required": ["thinking", "candidates", "chosen", "schema_version"],
    }


#: 훑기 프롬프트의 기준. **이 문단이 이 기능의 차별점이다** -- 형식이 아니라 확산을
#: 묻는다. 대표님 실제 영상에서 읽어 왔다(보고서 §손으로 먼저 적은 후보).
_SPREAD_CRITERION = (
    "묻는 것은 하나다: **이 대목이 실제로 퍼질까?**\n"
    "퍼지는 것은 이런 것이다.\n"
    "- 넘기려던 손을 1~2초 안에 멈추게 한다 (통념을 뒤집는 단언, 대놓고 솔직한 말, 의외의 사실)\n"
    "- 듣고 나서 남에게 보내고 싶어진다 (인용하고 싶은 한마디, 구체적인 실패·성공 이야기)\n"
    "- 구체적이다 (실제 숫자, 실제로 일어난 일, 고객이 실제로 한 말)\n"
    "퍼지지 않는 것은 이런 것이다.\n"
    "- 목차·뼈대 설명 (\"오늘은 세 가지를 알려드릴게요\")\n"
    "- 평평한 요약 (\"정리하면 이렇습니다\")\n"
    "- 인사·구독 요청·더보기란 안내\n"
    "**형식이 아니라 확산으로 판단하라.** '결론'이라서 좋은 것이 아니다 -- 평평한 결론은 "
    "버리고, 퍼지는 한마디가 영상 중간에 있으면 그것을 골라라. 숫자가 없어도 퍼질 수 있다.\n"
)


def _scan_prompt(passages: Sequence[_Passage]) -> str:
    example = {"schema_version": _SCAN_SCHEMA_VERSION, "picks": [{"scene": 1, "worth": 5}]}
    numbered = "\n".join(
        f"{number}. ({passage.start_sec:.0f}초) {passage.text}"
        for number, passage in enumerate(passages, start=1)
    )
    return (
        "너는 긴 영상에서 숏폼으로 잘라 낼 대목을 찾는 마케터다. "
        "채널은 셀러 교육이고, 말하는 사람이 1인칭으로 설명하는 영상이다.\n"
        + _SPREAD_CRITERION
        + "`worth`는 1(안 퍼진다)에서 5(확실히 퍼진다)까지다. "
        "퍼질 만한 대목이 없으면 빈 목록을 준다 -- 억지로 채우지 마라.\n"
        f"받은 번호를 그대로 돌려주고(1부터 {len(passages)}까지), 없는 번호를 만들지 마라.\n"
        f"출력 예시: {json.dumps(example, ensure_ascii=False)}\n\n"
        f"{_SCAN_MARKER}\n{numbered}"
    )


def _compose_prompt(
    passages: Sequence[_Passage], *, min_target_sec: float, max_target_sec: float
) -> str:
    numbered = "\n".join(
        f"{number}. ({passage.duration_sec:.0f}초) {passage.text}"
        for number, passage in enumerate(passages, start=1)
    )
    example = {
        "thinking": "무엇이 손을 멈추게 하는지 먼저 적는다",
        "candidates": [{"lines": [1, 3], "reason": "첫마디가 통념을 뒤집고 끝이 결과로 닫힌다"}],
        "chosen": 1,
        "schema_version": _COMPOSE_SCHEMA_VERSION,
    }
    return (
        "아래는 한 영상에서 퍼질 만하다고 이미 골라 둔 대목들이다. "
        f"이것으로 **이어진 숏폼 후보를 {COMPOSE_CANDIDATES}개까지 짜라.**\n"
        "퍼지는 숏폼은 낱개 점수의 합이 아니다. 이런 것이다.\n"
        "- 첫 1~2초에 붙잡는다 (첫 대목이 훅이어야 한다)\n"
        "- 끝까지 보게 한다 (중간이 늘어지지 않는다)\n"
        "- 남에게 보낼 이유를 준다 (마지막이 인용하고 싶은 한마디거나 분명한 결과다)\n"
        f"각 후보는 **{min_target_sec:.0f}초에서 {max_target_sec:.0f}초 사이**여야 한다. "
        "길이가 옆에 적혀 있으니 더해서 맞춰라. 넘기지 마라.\n"
        "`thinking`에는 후보를 짜기 **전에** 무엇이 사람을 멈추게 하는지 두세 줄로 먼저 적어라.\n"
        "`lines`는 재생 순서대로 적는다. "
        "`reason`은 **이 숏폼이 왜 퍼질지** 한 줄로, 대표님이 읽을 한국말로 적어라 -- "
        "이 문장은 화면에 그대로 나간다.\n"
        "`chosen`은 후보 중 **가장 퍼질 것 하나**의 번호(1부터)다.\n"
        f"출력 예시: {json.dumps(example, ensure_ascii=False)}\n\n"
        f"{_COMPOSE_MARKER}\n{numbered}"
    )


def _valid_picks(output: object, *, batch_size: int) -> list[tuple[int, int]] | None:
    """`(묶음 안 번호, 점수)` 목록. 모양이 아니면 `None` -- 반쯤 믿지 않는다."""

    if not isinstance(output, Mapping):
        return None
    picks = output.get("picks")
    if not isinstance(picks, (list, tuple)):
        return None
    result: list[tuple[int, int]] = []
    for item in picks:
        if not isinstance(item, Mapping):
            continue
        try:
            number = int(item["scene"])  # type: ignore[index]
            worth = int(item.get("worth") or 1)
        except (KeyError, TypeError, ValueError):
            continue
        # 범위 밖 번호는 그 줄만 버린다(자막 번역과 같은 태도).
        if not 1 <= number <= batch_size:
            continue
        result.append((number, max(1, min(5, worth))))
    return result


def _valid_candidates(
    output: object, *, shortlist_size: int
) -> tuple[list[tuple[tuple[int, ...], str]], int] | None:
    """`([(줄 번호들, 이유)], 고른 후보 번호)`. 모양이 아니면 `None`."""

    if not isinstance(output, Mapping):
        return None
    raw = output.get("candidates")
    if not isinstance(raw, (list, tuple)):
        return None
    candidates: list[tuple[tuple[int, ...], str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        lines = item.get("lines")
        if not isinstance(lines, (list, tuple)):
            continue
        numbers: list[int] = []
        for value in lines:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= shortlist_size and number not in numbers:
                numbers.append(number)
        if not numbers:
            continue
        candidates.append((tuple(numbers), str(item.get("reason") or "").strip()))
    if not candidates:
        return None
    try:
        chosen = int(output.get("chosen") or 1)
    except (TypeError, ValueError):
        chosen = 1
    if not 1 <= chosen <= len(candidates):
        chosen = 1
    return candidates, chosen


def _density_pick(
    ordered: list[Mapping[str, object]],
    *,
    reason: str,
    notice: str,
    max_target_sec: float,
    scenes_read: int = 0,
) -> ShortFormScenePick:
    """자막 밀도로 내려간 결과.

    `scenes_read`가 **0으로 박혀 있었던 것이 2026-09-12 실물 결함이다** -- 문구는
    "유진이 읽어 봤지만 못 찾아서"라고 말하는데 `scenes_read_by_yujin`은 0이어서
    둘이 서로를 부정했다. 읽은 만큼을 받아서 문구와 숫자를 한 쌍으로 맞춘다.
    """
    segment_ids = _clamp_to_max_sec(
        ordered,
        select_highlight_segment_ids(ordered, max_target_sec=max_target_sec),
        max_target_sec=max_target_sec,
    )
    if len(segment_ids) >= len(ordered):
        # `select_highlight_segment_ids`는 아무 장면도 점수를 못 받으면(자막이
        # 하나도 없으면) **전체를 그대로** 돌려준다. 선택 = 전부라 하나도
        # 안 짧아지는데 "골랐어요"라고 말하면 거짓이다.
        notice = (
            "숏폼에 넣을 장면을 고를 근거가 없어서(읽을 자막이 없어요) "
            "전체 장면을 그대로 뒀어요. 자막을 넣은 뒤 다시 만들어 주세요."
        )
    return ShortFormScenePick(
        segment_ids=segment_ids,
        judged_by="caption_density",
        notice=notice,
        scenes_total=len(ordered),
        scenes_read_by_yujin=scenes_read,
        fallback_reason=reason,
    )


_YUJIN_OFF_NOTICE = (
    "유진이 지금 도와줄 수 없어서, 자막이 많은 장면 위주로 골랐어요. "
    "마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
)


def _found_nothing_notice(*, scenes_total: int, scenes_read: int) -> str:
    """읽고 못 찾았을 때의 문구. **읽은 숫자가 문구 안에 들어간다.**

    읽은 것이 0이면 "읽어 봤지만"이라고 쓰지 않는다 -- 그건 거짓이고, 실물에서
    실제로 그렇게 나갔다(2026-09-12).
    """
    if scenes_read <= 0:
        return _YUJIN_OFF_NOTICE
    return (
        f"유진이 장면 {scenes_total}개 중 {scenes_read}개를 읽어 봤지만 숏폼에 넣을 만한 "
        "대목을 못 찾아서, 자막이 많은 장면 위주로 골랐어요. "
        "마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
    )


@dataclass(slots=True, frozen=True)
class _ScanOutcome:
    """훑기 묶음 하나의 결과. **답했는지와 무엇을 골랐는지를 따로 들고 다닌다** --
    둘을 하나로 뭉개면 "못 찾았다"와 "못 물어봤다"가 구분되지 않는다."""

    start: int
    picks: tuple[tuple[int, int], ...] = ()
    answered: bool = False
    unusable: bool = False


def _scan_one_batch(
    runtime: object,
    *,
    project_id: str,
    batch: Sequence[_Passage],
    start: int,
    number: int,
    total: int,
    wait_seconds: int,
    clock: Callable[[], float],
) -> _ScanOutcome:
    """묶음 하나를 유진에게 묻고 **무슨 일이 있었는지 로그에 남긴다.**"""

    # 프롬프트는 **try 밖에서** 만든다. 안에서 만들면 여기서 난 우리 실수가
    # "유진이 바쁘다"로 둔갑한다(2026-09-02 자막 번역에서 실제로 겪었다).
    prompt = _scan_prompt(batch)
    started = clock()
    try:
        response = runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.SHORT_FORM_SCENE_PICK,
            prompt=prompt,
            response_schema=_scan_schema(),
            wait_seconds=wait_seconds,
        )
    except LLMProviderError as error:
        _LOGGER.warning(
            "숏폼 훑기 묶음 %d/%d 답을 못 받았어요: 대목 %d개, %.1f초, 상한 %d초, %s (%s)",
            number, total, len(batch), clock() - started, wait_seconds,
            error.error_code or "unknown", error.message,
        )
        return _ScanOutcome(start=start)
    picks = _valid_picks(getattr(response, "output_data", None), batch_size=len(batch))
    if picks is None:
        raw = str(getattr(response, "raw_text", "") or "")[:200]
        _LOGGER.warning(
            "숏폼 훑기 묶음 %d/%d 답을 못 읽었어요: %.1f초, 받은 것 %r",
            number, total, clock() - started, raw,
        )
        return _ScanOutcome(start=start, unusable=True)
    _LOGGER.info(
        "숏폼 훑기 묶음 %d/%d: 대목 %d개, %.1f초, 고른 대목 %d개 %s",
        number, total, len(batch), clock() - started, len(picks),
        [number_ for number_, _ in picks],
    )
    return _ScanOutcome(start=start, picks=tuple(picks), answered=True)


def pick_short_form_scenes(
    segments: Sequence[Mapping[str, object]],
    *,
    project_id: str,
    runtime: object | None = None,
    utterances: Sequence[Mapping[str, object]] | None = None,
    max_judged_passages: int = MAX_JUDGED_PASSAGES,
    batch_size: int = SCAN_BATCH_SIZE,
    max_scan_calls: int = MAX_SCAN_CALLS,
    min_target_sec: float = SHORT_FORM_MIN_TARGET_SEC,
    max_target_sec: float = SHORT_FORM_MAX_TARGET_SEC,
    budget_seconds: float = SYNCHRONOUS_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> ShortFormScenePick:
    """숏폼을 고르고, **누가 골랐는지**와 **왜 퍼질지**를 같이 돌려준다.

    `utterances`는 전사의 발화(`start_sec`·`end_sec`·`text`)다. 주면 그것을 읽고
    판단하고, 없으면 장면 자막을 읽는다. 어느 쪽이든 판단 흐름은 하나다.

    `budget_seconds`는 **벽시계 예산**이다. 기본값은 같은 요청 안에서 도는 쪽
    (유진 채팅·처음 만들기)의 값이라 프록시 벽 아래에 머문다. 뒤에서 도는 쪽은
    `BACKGROUND_BUDGET_SECONDS`를 준다 -- 실측으로 약 400초가 걸리는 일이다.
    """

    # **대표님이 이미 뺀 장면은 후보가 아니다.** 뺀 장면을 고르면 숏폼이 그
    # 길이만큼 자리를 내주는데 `composition_plan`이 그 클립을 버려서, 숏폼
    # 한가운데에 죽은 시간이 생긴다.
    ordered = [
        segment
        for segment in segments
        if str(segment.get("segment_id") or "").strip()
        and str(segment.get("cut_action") or "keep") != "remove"
    ]
    if not ordered:
        return ShortFormScenePick(
            segment_ids=(),
            judged_by="caption_density",
            notice="고를 장면이 없어요.",
            scenes_total=0,
            scenes_read_by_yujin=0,
            fallback_reason="no_segments",
        )
    if runtime is None:
        return _density_pick(
            ordered,
            reason="yujin_engine_off",
            notice=_YUJIN_OFF_NOTICE,
            max_target_sec=max_target_sec,
        )

    passages: tuple[_Passage, ...] = ()
    read_from_transcript = False
    if utterances:
        passages = _passages_from_utterances(
            utterances,
            board_bounds=[_segment_source_bounds(segment) for segment in ordered],
            limit=max_judged_passages,
        )
        read_from_transcript = bool(passages)
    if not passages:
        passages = _passages_from_segments(ordered, limit=max_judged_passages)
    if not passages:
        return _density_pick(
            ordered,
            reason="yujin_found_nothing",
            notice=_YUJIN_OFF_NOTICE,
            max_target_sec=max_target_sec,
        )

    started = clock()
    batches = [
        (start, passages[start : start + batch_size])
        for start in range(0, len(passages), batch_size)
    ][:max_scan_calls]
    # **한 호출을 얼마나 기다릴지는 예산이 정한다**(절반까지). 뒤에서 도는 쪽이
    # 더 기다리는 이유는 실물에 있다 -- 150초 상한에서 여섯 중 셋이 끊겨 94장면
    # 중 44개만 읽혔다(2026-09-12).
    scan_wait = scan_wait_seconds(budget_seconds)

    def scan(job: tuple[int, tuple[_Passage, ...]], number: int) -> _ScanOutcome:
        start, batch = job
        return _scan_one_batch(
            runtime,
            project_id=project_id,
            batch=batch,
            start=start,
            number=number,
            total=len(batches),
            wait_seconds=scan_wait,
            clock=clock,
        )

    # **동시에 묻는다.** 차례로 부르면 여섯 묶음이 최악 780초(실측 기준)가 되어
    # 프록시 벽을 넘는다. 동시에 부르면 벽시계가 가장 느린 한 호출이 된다
    # (2026-09-12 실측: 여섯 묶음 동시에 129.8초, 여섯 다 답함).
    if len(batches) <= 1:
        outcomes = [scan(job, index + 1) for index, job in enumerate(batches)]
    else:
        with ThreadPoolExecutor(max_workers=len(batches)) as pool:
            outcomes = list(
                pool.map(lambda pair: scan(pair[1], pair[0] + 1), list(enumerate(batches)))
            )

    scored: dict[int, int] = {}
    read_passages: list[int] = []
    answered = False
    unusable = False
    for outcome, (_, batch) in zip(outcomes, batches, strict=True):
        if outcome.unusable:
            unusable = True
        if not outcome.answered:
            # 유진이 못 한 것만 삼킨다. 한 묶음이 빠져도 나머지 판단은 살리되
            # 읽은 것으로 세지 않는다 -- 문구가 부풀지 않게.
            continue
        answered = True
        read_passages.extend(range(outcome.start, outcome.start + len(batch)))
        for number, worth in outcome.picks:
            index = outcome.start + number - 1
            scored[index] = max(scored.get(index, 0), worth)

    answered_batches = sum(1 for outcome in outcomes if outcome.answered)
    _LOGGER.info(
        "숏폼 훑기 끝: 묶음 %d/%d 답함, 점수 받은 대목 %d개, %.1f초 / 예산 %.0f초",
        answered_batches, len(batches), len(scored), clock() - started, budget_seconds,
    )

    read_scene_ids = set(
        _segment_ids_for_passages(ordered, [passages[index] for index in read_passages])
    )
    if answered and not scored:
        read_count = len(read_scene_ids)
        return _density_pick(
            ordered,
            reason="yujin_found_nothing",
            notice=_found_nothing_notice(scenes_total=len(ordered), scenes_read=read_count),
            max_target_sec=max_target_sec,
            scenes_read=read_count,
        )
    if not answered:
        return _density_pick(
            ordered,
            reason="yujin_answer_unusable" if unusable else "yujin_unavailable",
            notice=_YUJIN_OFF_NOTICE,
            max_target_sec=max_target_sec,
        )

    # 점수 높은 순으로 짜기에 넘길 대목을 추린다. 한 묶음과 같은 크기로 두는
    # 이유는 짜기 호출도 같은 예산 안에 있기 때문이다.
    shortlist_indexes = sorted(
        sorted(scored, key=lambda index: (-scored[index], index))[:batch_size]
    )
    shortlist = [passages[index] for index in shortlist_indexes]

    spread_reason: str | None = None
    composed: tuple[int, ...] | None = None
    compose_failed = False
    # **대목이 하나여도 짜기를 부른다.** 짤 것이 없어 보이지만, 이 호출이
    # 화면에 나갈 "왜 퍼질까" 한 줄을 만드는 유일한 자리다. 빼면 숏폼 하나짜리
    # 결과에서 이유가 조용히 사라진다.
    # **남은 예산을 먼저 본다.** 짜기는 실측 266.8초짜리라, 남은 시간이 없으면
    # 시작해도 끊길 뿐이고 그러면 기다린 시간만 버린다. 인포그래픽이 "한 판 더
    # 돌 시간이 없으면 안 돈다"로 같은 자리를 지킨다.
    compose_wait = compose_wait_seconds(budget_seconds, clock() - started)
    if shortlist and compose_wait < COMPOSE_MIN_WAIT_SECONDS:
        compose_failed = True
        _LOGGER.info(
            "숏폼 짜기를 시작하지 않았어요: 남은 예산 %d초 (최소 %d초 필요)",
            compose_wait, COMPOSE_MIN_WAIT_SECONDS,
        )
    elif shortlist:
        compose_prompt = _compose_prompt(
            shortlist, min_target_sec=min_target_sec, max_target_sec=max_target_sec
        )
        compose_started = clock()
        try:
            response = runtime.generate_structured(  # type: ignore[attr-defined]
                project_id=project_id,
                task_type=LLMTaskType.SHORT_FORM_SCENE_PICK,
                prompt=compose_prompt,
                response_schema=_compose_schema(),
                wait_seconds=compose_wait,
            )
        except LLMProviderError as error:
            compose_failed = True
            _LOGGER.warning(
                "숏폼 짜기 답을 못 받았어요: 대목 %d개, %.1f초, 상한 %d초, %s (%s)",
                len(shortlist), clock() - compose_started, compose_wait,
                error.error_code or "unknown", error.message,
            )
        else:
            parsed = _valid_candidates(
                getattr(response, "output_data", None), shortlist_size=len(shortlist)
            )
            if parsed is None:
                compose_failed = True
                _LOGGER.warning(
                    "숏폼 짜기 답을 못 읽었어요: %.1f초, 받은 것 %r",
                    clock() - compose_started,
                    str(getattr(response, "raw_text", "") or "")[:200],
                )
            else:
                candidates, chosen = parsed
                lines, reason = candidates[chosen - 1]
                composed = tuple(shortlist_indexes[number - 1] for number in lines)
                spread_reason = reason or None
                _LOGGER.info(
                    "숏폼 짜기: 후보 %d개 중 %d번, 대목 %d개, %.1f초, 퍼질 이유 %s",
                    len(candidates), chosen, len(composed), clock() - compose_started,
                    "있음" if spread_reason else "없음",
                )

    if composed:
        # 유진이 짠 순서를 **중요도의 단서로** 쓴다 -- 훅을 앞에 놓으라고 했으므로
        # 앞자리가 덜 버려져야 한다. 점수가 같으면 유진이 먼저 적은 것을 남긴다.
        position = {index: order for order, index in enumerate(composed)}
        priority = sorted(
            dict.fromkeys(composed),
            key=lambda index: (-scored.get(index, 0), position[index]),
        )
    else:
        priority = sorted(scored, key=lambda index: (-scored[index], index))

    segment_ids = _assemble_within_ceiling(
        ordered, passages, priority, max_target_sec=max_target_sec
    )
    if not segment_ids:
        # 고른 대목에 걸치는 장면이 하나도 없다 -- 전사와 판이 어긋난 경우다.
        return _density_pick(
            ordered,
            reason="yujin_pick_had_no_scene",
            notice=(
                "유진이 고른 대목에 맞는 장면을 판에서 찾지 못해서, 자막이 많은 "
                "장면 위주로 골랐어요. 마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
            ),
            max_target_sec=max_target_sec,
            scenes_read=len(read_scene_ids),
        )

    read_count = len(read_scene_ids)
    material = "전사의 말" if read_from_transcript else "장면 자막"
    if read_count >= len(ordered):
        notice = f"유진이 {material}을 전 구간 읽고 퍼질 만한 대목으로 숏폼을 골랐어요."
    else:
        notice = (
            f"유진이 {material}을 읽고 퍼질 만한 대목으로 숏폼을 골랐어요"
            f"(장면 {len(ordered)}개 중 {read_count}개를 읽었어요). "
            "나머지 장면은 확인하지 못했어요."
        )
    if composed is None:
        notice += (
            " 후보를 여러 개 짜 보지는 못해서 퍼질 이유는 남기지 못했어요."
            if compose_failed
            else ""
        )
    _LOGGER.info(
        "숏폼 판단 끝: 장면 %d개 중 %d개 읽음, 고른 장면 %d개, 퍼질 이유 %s, %.1f초 / 예산 %.0f초",
        len(ordered), read_count, len(segment_ids),
        "있음" if spread_reason else "없음", clock() - started, budget_seconds,
    )
    return ShortFormScenePick(
        segment_ids=segment_ids,
        judged_by="yujin",
        notice=notice,
        scenes_total=len(ordered),
        scenes_read_by_yujin=read_count,
        spread_reason=spread_reason,
    )
