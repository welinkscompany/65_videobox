"""자동 하이라이트 선택 -- 세로 하이라이트 변형을 만들 때 어느 장면을 넣을지 고른다.

owner 요청(2026-08-28): "하이라이트 변형 만들기 - 이것도 자동으로 만들도록 해줘."
그 전에는 `create_output_variant`가 `selected_segment_ids`를 비워 뒀고, 그 결과
`materialize_variant`가 전체 장면을 그대로 썼다(§output_variants.py) -- "하이라이트"라는
이름과 달리 실제로는 원본 전체였다.

**정직하게 밝혀 둘 것**: 여기 점수는 AI 참여도 예측이 아니다. 자막 밀도(글자 수)만으로
장면을 고르는 단순 휴리스틱이다 -- 말이 많은 장면일수록 내용이 진행되고 있을 가능성이
높다는 가정 하나뿐이다. 무음/정적 장면(자막 없음)은 낮은 점수를 받아 자연히 빠진다.

**2026-09-11부터 이 파일은 "고르는 사람"이 아니다.** 마케팅용 숏폼을 고르는 판단은
`short_form_scene_pick.py`에서 유진이 한다. 여기 남은 두 가지 몫은 이것뿐이다.

1. `shortlist_short_form_candidates` -- 유진에게 보여줄 후보를 **추린다**(판단 아님).
2. `select_highlight_segment_ids` -- 유진이 대답을 못 할 때의 **대비책**. 이때는
   결과에 "자막 밀도로 골랐다"는 꼬리표가 붙어 화면까지 간다. 유진의 판단인 척하지
   않는다(`short_form_scene_pick.ShortFormScenePick.judged_by`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: 하이라이트가 원본의 몇 %를 넘지 않게 할지. 너무 크면 "하이라이트"가 아니라
#: 원본 재탕이 된다.
_DEFAULT_TARGET_RATIO = 0.4
#: 아무리 짧은 원본이어도 최소 이만큼은 하이라이트가 남게 한다.
_MIN_TARGET_SEC = 8.0
#: 훅으로 쓸 앞쪽 장면 수. 첫 문장이 훅이라는 것은 owner의 기준이다(2026-09-11).
_HOOK_SCENES = 3
#: 결론으로 쓸 뒤쪽 장면 수. 밀도만 보면 마무리 멘트는 거의 항상 탈락한다.
_CONCLUSION_SCENES = 3
#: "숫자·결과"로 볼 낱말. 여기서 잡는 것은 **판단이 아니라 후보 보존**이다 --
#: 틀려서 더 담는 것은 싸고, 빠뜨리면 유진이 그 장면을 아예 못 본다.
_RESULT_WORDS = ("배", "%", "퍼센트", "만원", "원", "개월", "억", "만 원", "결론", "정리하면", "핵심은")


def _has_number_or_result(text: str) -> bool:
    return any(character.isdigit() for character in text) or any(
        word in text for word in _RESULT_WORDS
    )


def _segment_duration(segment: Mapping[str, object]) -> float:
    start = float(segment.get("start_sec") or 0.0)
    end = float(segment.get("end_sec") or 0.0)
    return max(0.0, end - start)


def _segment_score(segment: Mapping[str, object]) -> float:
    text = str(segment.get("caption_text") or "").strip()
    duration = _segment_duration(segment)
    if not text or duration <= 0:
        return 0.0
    # 글자 수를 길이로 나눠 "밀도"를 본다 -- 같은 자막을 오래 띄워 둔 느린 장면보다
    # 짧은 시간에 말이 많은 장면을 우선한다.
    return len(text) / duration


def target_duration_sec(
    segments: Sequence[Mapping[str, object]],
    *,
    target_ratio: float = _DEFAULT_TARGET_RATIO,
    min_target_sec: float = _MIN_TARGET_SEC,
    max_target_sec: float | None = None,
) -> float:
    """골라낸 장면을 얼마나 담을지. 상한은 부르는 쪽이 정한다."""

    total_duration = sum(_segment_duration(segment) for segment in segments)
    target = total_duration * target_ratio
    if max_target_sec is not None:
        target = min(target, max_target_sec)
    return max(min_target_sec, target)


def shortlist_short_form_candidates(
    segments: Sequence[Mapping[str, object]],
    *,
    limit: int,
) -> tuple[Mapping[str, object], ...]:
    """유진에게 **보여줄** 장면을 추린다. 고르는 것이 아니라 버리지 않는 일이다.

    유진에게 롱폼 장면을 전부 보낼 수는 없다. 한 번에 보내면 로컬 모델이 뒤쪽을
    흘리고(자막 번역에서 실측), 나눠 보내면 부르는 횟수가 장면 수에 비례해 늘어
    프록시 330초 벽에 걸린다. 그래서 **부르는 횟수에 상한이 생기도록** 후보를 먼저
    좁힌다.

    좁힐 때 지키는 것 셋. 전부 "무엇이 좋은 장면인가"가 아니라 "무엇을 유진 눈에서
    감추면 안 되는가"에 대한 답이다.

    1. **앞과 뒤는 무조건 넣는다.** 훅과 결론은 owner가 말한 기준인데 둘 다 밀도로는
       거의 항상 진다(마무리 멘트는 짧다).
    2. **숫자·결과가 든 장면은 먼저 넣는다.** 셀러 교육 영상에서 마케팅이 되는
       대목은 대개 여기다.
    3. **남는 자리는 영상을 고르게 나눠 구간마다 하나씩 채운다.** 밀도 순으로만
       채우면 말이 빠른 앞부분이 자리를 다 먹고, 숏폼이 늘 영상 앞머리에서만
       나오게 된다 -- 이 기능이 고치려던 바로 그 결함이다.
    """

    ordered = [segment for segment in segments if str(segment.get("segment_id") or "").strip()]
    if limit <= 0:
        return ()
    if len(ordered) <= limit:
        return tuple(ordered)

    picked: set[int] = set()

    def _add(index: int) -> None:
        if len(picked) < limit:
            picked.add(index)

    for index in range(min(_HOOK_SCENES, len(ordered))):
        _add(index)
    for index in range(max(0, len(ordered) - _CONCLUSION_SCENES), len(ordered)):
        _add(index)

    # 숫자·결과 장면이 아주 많은 원본도 있다. 절반까지만 여기에 쓰고 나머지
    # 자리는 3번(고른 분포)에 남긴다 -- 안 그러면 한쪽에 몰릴 수 있다.
    result_budget = limit // 2
    result_scenes = sorted(
        (
            index
            for index, segment in enumerate(ordered)
            if index not in picked
            and _has_number_or_result(str(segment.get("caption_text") or ""))
        ),
        key=lambda index: _segment_score(ordered[index]),
        reverse=True,
    )
    for index in result_scenes[: max(0, result_budget - len(picked))]:
        _add(index)

    # 남은 자리 수만큼 구간을 나누고, 구간마다 자막이 가장 빽빽한 장면 하나씩.
    remaining = limit - len(picked)
    if remaining > 0:
        span = len(ordered) / remaining
        for slot in range(remaining):
            window = range(int(slot * span), max(int(slot * span) + 1, int((slot + 1) * span)))
            candidates = [index for index in window if index not in picked]
            if not candidates:
                continue
            _add(max(candidates, key=lambda index: _segment_score(ordered[index])))
    # 구간이 이미 차 있어 못 채운 자리는 밀도 순으로 마저 메운다.
    if len(picked) < limit:
        for index in sorted(
            (index for index in range(len(ordered)) if index not in picked),
            key=lambda index: _segment_score(ordered[index]),
            reverse=True,
        ):
            _add(index)
            if len(picked) >= limit:
                break

    return tuple(ordered[index] for index in sorted(picked))


def select_highlight_segment_ids(
    segments: Sequence[Mapping[str, object]],
    *,
    target_ratio: float = _DEFAULT_TARGET_RATIO,
    min_target_sec: float = _MIN_TARGET_SEC,
    max_target_sec: float | None = None,
) -> tuple[str, ...]:
    """자막 밀도가 높은 장면부터 목표 길이를 채울 때까지 고르고, 시간순으로 돌려준다.

    빈 입력이거나 아무 장면도 점수를 받지 못하면(자막이 하나도 없으면) 원본 순서
    그대로 전부 돌려준다 -- "하이라이트를 못 골랐다"고 조용히 빈 목록을 주면
    `OutputVariant`가 `min_length=1` 제약에 걸려 깨진다.
    """

    ordered = [segment for segment in segments if str(segment.get("segment_id") or "").strip()]
    if not ordered:
        return ()

    target_sec = target_duration_sec(
        ordered,
        target_ratio=target_ratio,
        min_target_sec=min_target_sec,
        max_target_sec=max_target_sec,
    )

    # 점수가 0인(자막이 없거나 무음인) 장면은 애초에 후보에서 뺀다 -- 그대로 두면
    # 목표 길이를 채우려고 정적 구간까지 끌어와 "하이라이트"의 뜻이 없어진다.
    scored = sorted(
        (segment for segment in ordered if _segment_score(segment) > 0),
        key=lambda segment: _segment_score(segment),
        reverse=True,
    )

    picked_ids: set[str] = set()
    picked_sec = 0.0
    for segment in scored:
        if picked_sec >= target_sec:
            break
        segment_id = str(segment["segment_id"])
        picked_ids.add(segment_id)
        picked_sec += _segment_duration(segment)

    if not picked_ids:
        # 전부 무음/무자막이라 아무 장면도 점수를 못 받은 경우 -- 통째로 준다.
        return tuple(str(segment["segment_id"]) for segment in ordered)

    # 고른 것을 원래 시간 순서로 되돌린다 -- `materialize_variant`가 이 순서 그대로
    # 이어 붙이므로, 점수 순서로 두면 장면이 뒤죽박죽 재생된다.
    return tuple(
        str(segment["segment_id"]) for segment in ordered if str(segment["segment_id"]) in picked_ids
    )
