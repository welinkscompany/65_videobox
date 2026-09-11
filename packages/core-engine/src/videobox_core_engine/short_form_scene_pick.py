"""숏폼에 넣을 장면을 유진이 고른다.

owner 요청(2026-09-11): "롱폼을 주면 그걸 마케팅용으로 알아서 판단해서 숏폼용으로
자동으로 잘라주는 기능." 대표님이 말하는 마케팅용은 **훅(첫 문장), 결론, 숫자·결과가
나오는 대목**이다.

## 무엇을 근거로 고르는가 (정직하게)

세 단계이고, 그중 **판단은 2단계 하나**다.

1. **추리기** -- 기계가 후보를 좁힌다(`highlight_scoring.shortlist_short_form_candidates`).
   앞뒤와 숫자·결과 장면을 먼저 붙잡고, 남는 자리는 영상을 고르게 나눠 구간마다
   채운다. 이건 판단이 아니라 "유진 눈에서 감추지 않기"다.
2. **고르기** -- 유진이 후보의 자막을 읽고 장면마다 숏폼 가치를 매긴다. **이게
   실제 판단이다.** 글자 수는 여기서 아무 역할도 하지 않는다.
3. **담기** -- 점수 높은 순으로 목표 길이까지 담고 시간 순서로 되돌린다. 기계가 한다.

## 왜 후보를 좁히는가

유진에게 롱폼 장면을 한 번에 다 보낼 수는 없다. 한 요청에 넣으면 로컬 모델이 뒤쪽을
흘리고(자막 번역에서 실측), 장면 수만큼 나눠 부르면 호출이 선형으로 늘어 프록시
330초 벽에 걸린다. `MAX_JUDGED_SCENES`와 `JUDGE_BATCH_SIZE`를 곱하면 **호출 수
상한이 넷**이다(로컬 런타임 기본 상한 30초 x 4 = 120초).

**그래서 장면이 `MAX_JUDGED_SCENES`개를 넘으면 유진은 전부를 보지 않는다.** 그 사실이
`scenes_read_by_yujin`/`scenes_total`로 결과에 실려 화면 문구까지 간다. 다만 추리기가
영상 전체에 고르게 퍼지므로, 유진이 보는 장면이 앞머리에 몰리지는 않는다.

## 유진이 대답을 못 하면

**조용히 글자 수 세기로 내려가지 않는다.** 모델이 꺼져 있거나, 응답이 깨졌거나,
시간이 넘으면 `judged_by="caption_density"`와 그 사실을 말하는 문구를 실어 돌려준다.
멈추는 대신 대비책을 쓰는 이유는 더빙과 상황이 다르기 때문이다 -- 더빙의 기계 목소리는
완성본에 섞여 들어가 대표님이 알아채기 어렵지만, 여기 결과는 장면 목록이라 화면에
바로 보이고 되돌리기가 한 번이다(2026-09-11 결정, `progress.md`). 대신 **유진이 골랐다고
말하지 않는 것**은 지킨다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, Literal

from videobox_core_engine.highlight_scoring import (
    select_highlight_segment_ids,
    shortlist_short_form_candidates,
    target_duration_sec,
)
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType

#: 유진이 읽을 장면 수 상한. 이 값과 아래 묶음 크기가 호출 횟수를 묶는다.
MAX_JUDGED_SCENES = 48
#: 한 번에 보내는 장면 수. 자막 번역(12)과 같은 값에서 출발한다 -- 되받는 양은
#: 여기가 훨씬 적지만(번호·점수·이유), 읽어야 하는 자막 양은 같다.
JUDGE_BATCH_SIZE = 12
#: 숏폼 길이 상한. 20분짜리 롱폼의 40%면 8분이고 그건 숏폼이 아니다.
SHORT_FORM_MAX_TARGET_SEC = 60.0

_SCHEMA_VERSION = "videobox.short-form-scene-pick.v1"
_WHY_VALUES = ("hook", "conclusion", "number_or_result", "other")

JudgedBy = Literal["yujin", "caption_density"]


@dataclass(slots=True, frozen=True)
class ShortFormScenePick:
    """고른 결과와 **누가 골랐는지**. 둘은 항상 같이 다닌다."""

    segment_ids: tuple[str, ...]
    judged_by: JudgedBy
    notice: str
    scenes_total: int
    scenes_read_by_yujin: int
    fallback_reason: str | None = None


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": _SCHEMA_VERSION},
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "scene": {"type": "integer"},
                        "worth": {"type": "integer"},
                        "why": {"type": "string", "enum": list(_WHY_VALUES)},
                    },
                    "required": ["scene", "worth", "why"],
                },
            },
        },
        "required": ["schema_version", "picks"],
    }


def _prompt(*, captions: Sequence[str]) -> str:
    example = {
        "schema_version": _SCHEMA_VERSION,
        "picks": [{"scene": 1, "worth": 5, "why": "hook"}],
    }
    numbered = "\n".join(f"{number}. {text}" for number, text in enumerate(captions, start=1))
    return (
        "너는 긴 영상에서 마케팅용 숏폼에 넣을 대목을 고르는 편집자다. "
        "채널은 셀러 교육이고, 말하는 사람이 1인칭으로 설명하는 영상이다.\n"
        "숏폼에 넣을 만한 장면은 이런 것이다.\n"
        "- 훅: 사람을 붙잡는 첫 문장, 궁금하게 만드는 질문이나 단언\n"
        "- 결론: 그래서 뭘 하라는 것인지 정리되는 대목\n"
        "- 숫자·결과: 구체적인 수치나 실제로 일어난 결과를 말하는 대목\n"
        "**말이 많다고 좋은 장면이 아니다.** 길게 말했지만 알맹이가 없는 대목은 고르지 마라. "
        "짧아도 결론이면 고른다.\n"
        f"`worth`는 1(약함)에서 5(아주 좋음)까지다. `why`는 {', '.join(_WHY_VALUES)} 중 하나다. "
        "넣을 만한 장면이 없으면 빈 목록을 준다. "
        "각 줄은 `번호. 자막`이다. 받은 번호를 그대로 돌려주고(1부터 "
        f"{len(captions)}까지), 없는 번호를 만들지 마라.\n"
        f"출력 예시: {json.dumps(example, ensure_ascii=False)}\n\n"
        f"고를 장면:\n{numbered}"
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


def _density_pick(
    ordered: list[Mapping[str, object]],
    *,
    reason: str,
    notice: str,
) -> ShortFormScenePick:
    segment_ids = select_highlight_segment_ids(
        ordered, max_target_sec=SHORT_FORM_MAX_TARGET_SEC
    )
    if len(segment_ids) >= len(ordered):
        # `select_highlight_segment_ids`는 아무 장면도 점수를 못 받으면(자막이
        # 하나도 없으면) **전체를 그대로** 돌려준다. 선택 = 전부라 하나도
        # 안 짧아지는데 "골랐어요"라고 말하면 거짓이다. 안 골랐으면 골랐다고
        # 말하지 않는다.
        notice = (
            "숏폼에 넣을 장면을 고를 근거가 없어서(읽을 자막이 없어요) "
            "전체 장면을 그대로 뒀어요. 자막을 넣은 뒤 다시 만들어 주세요."
        )
    return ShortFormScenePick(
        segment_ids=segment_ids,
        judged_by="caption_density",
        notice=notice,
        scenes_total=len(ordered),
        scenes_read_by_yujin=0,
        fallback_reason=reason,
    )


def pick_short_form_scenes(
    segments: Sequence[Mapping[str, object]],
    *,
    project_id: str,
    runtime: object | None = None,
    max_judged_scenes: int = MAX_JUDGED_SCENES,
    batch_size: int = JUDGE_BATCH_SIZE,
    max_target_sec: float = SHORT_FORM_MAX_TARGET_SEC,
) -> ShortFormScenePick:
    """숏폼에 넣을 장면을 고르고, **누가 골랐는지**를 같이 돌려준다."""

    # **대표님이 이미 뺀 장면은 후보가 아니다.** 뺀 장면을 고르면 숏폼이 그
    # 길이만큼 자리를 내주는데 `composition_plan`이 그 클립을 버려서, 숏폼
    # 한가운데에 죽은 시간이 생긴다. 안내문의 "전체 N개"도 여기서 함께 줄어든다.
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
            notice=(
                "유진이 지금 도와줄 수 없어서, 자막이 많은 장면 위주로 골랐어요. "
                "마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
            ),
        )

    candidates = shortlist_short_form_candidates(ordered, limit=max_judged_scenes)
    # 점수(worth) -> 후보 위치. 위치는 시간 순서를 되찾는 데 쓴다.
    scored: dict[int, int] = {}
    read = 0
    answered = False
    unusable = False
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        # 프롬프트는 **try 밖에서** 만든다. 안에서 만들면 여기서 난 우리 실수가
        # "유진이 바쁘다"로 둔갑한다(2026-09-02 자막 번역에서 실제로 겪었다).
        prompt = _prompt(
            captions=[str(segment.get("caption_text") or segment.get("text") or "") for segment in batch]
        )
        try:
            response = runtime.generate_structured(  # type: ignore[attr-defined]
                project_id=project_id,
                task_type=LLMTaskType.SHORT_FORM_SCENE_PICK,
                prompt=prompt,
                response_schema=_response_schema(),
            )
        except LLMProviderError:
            # 유진이 못 한 것만 삼킨다. 한 묶음이 빠져도 나머지 판단은 살리되,
            # 읽은 장면 수(`read`)에는 안 더한다 -- 문구가 부풀지 않게.
            continue
        picks = _valid_picks(getattr(response, "output_data", None), batch_size=len(batch))
        if picks is None:
            unusable = True
            continue
        answered = True
        read += len(batch)
        for number, worth in picks:
            index = start + number - 1
            scored[index] = max(scored.get(index, 0), worth)

    if answered and not scored:
        # 유진이 읽긴 읽었는데 넣을 만한 대목이 없다고 한 경우. "못 불렀다"와
        # 다른 상황이니 다르게 말한다.
        return _density_pick(
            ordered,
            reason="yujin_found_nothing",
            notice=(
                "유진이 읽어 봤지만 숏폼에 넣을 만한 대목을 못 찾아서, 자막이 많은 "
                "장면 위주로 골랐어요. 마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
            ),
        )
    if not answered:
        return _density_pick(
            ordered,
            reason="yujin_answer_unusable" if unusable else "yujin_unavailable",
            notice=(
                "유진이 지금 도와줄 수 없어서, 자막이 많은 장면 위주로 골랐어요. "
                "마음에 안 들면 전체 장면으로 되돌릴 수 있어요."
            ),
        )

    target_sec = target_duration_sec(ordered, max_target_sec=max_target_sec)
    picked_positions: set[int] = set()
    filled = 0.0
    # 점수 높은 순, 같으면 앞 장면 먼저. 목표 길이를 넘기기 전까지 담는다.
    for index in sorted(scored, key=lambda index: (-scored[index], index)):
        if filled >= target_sec and picked_positions:
            break
        picked_positions.add(index)
        segment = candidates[index]
        filled += max(
            0.0,
            float(segment.get("end_sec") or 0.0) - float(segment.get("start_sec") or 0.0),
        )

    picked_ids = {str(candidates[index]["segment_id"]) for index in picked_positions}
    # 시간 순서로 되돌린다 -- `materialize_variant`가 이 순서 그대로 이어 붙인다.
    segment_ids = tuple(
        str(segment["segment_id"])
        for segment in ordered
        if str(segment["segment_id"]) in picked_ids
    )
    if read >= len(ordered):
        notice = "유진이 전체 장면을 읽고 숏폼에 넣을 장면을 골랐어요."
    elif len(candidates) >= len(ordered):
        # 추리기를 **안 한** 판이다(장면이 상한 이하). 덜 읽은 이유는 추리기가
        # 아니라 한 묶음이 실패한 것이므로 "추렸다"고 말하면 틀린 문장이다.
        notice = (
            f"유진이 장면 {read}개를 읽고 숏폼에 넣을 장면을 골랐어요"
            f"(전체 {len(ordered)}개). 나머지 장면은 확인하지 못했어요."
        )
    elif read >= len(candidates):
        notice = (
            f"유진이 영상 전체에서 고르게 추린 장면 {read}개를 읽고 숏폼에 넣을 장면을 "
            f"골랐어요(전체 {len(ordered)}개)."
        )
    else:
        # 추리기도 했고 그중 일부 묶음도 실패한 경우. 둘 다 말한다.
        notice = (
            f"유진이 영상 전체에서 고르게 추린 장면 {len(candidates)}개 중 {read}개를 읽고 "
            f"숏폼에 넣을 장면을 골랐어요(전체 {len(ordered)}개). "
            "나머지 장면은 확인하지 못했어요."
        )
    return ShortFormScenePick(
        segment_ids=segment_ids,
        judged_by="yujin",
        notice=notice,
        scenes_total=len(ordered),
        scenes_read_by_yujin=read,
    )
