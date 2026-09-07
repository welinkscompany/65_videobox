"""자동 하이라이트 선택 -- 세로 하이라이트 변형을 만들 때 어느 장면을 넣을지 고른다.

owner 요청(2026-08-28): "하이라이트 변형 만들기 - 이것도 자동으로 만들도록 해줘."
그 전에는 `create_output_variant`가 `selected_segment_ids`를 비워 뒀고, 그 결과
`materialize_variant`가 전체 장면을 그대로 썼다(§output_variants.py) -- "하이라이트"라는
이름과 달리 실제로는 원본 전체였다.

**정직하게 밝혀 둘 것**: 여기 점수는 AI 참여도 예측이 아니다. 로컬에 그런 모델이
없다(§조사, 2026-08-28). 자막 밀도(글자 수)만으로 장면을 고르는 단순 휴리스틱이다 --
말이 많은 장면일수록 내용이 진행되고 있을 가능성이 높다는 가정 하나뿐이다. 무음/정적
장면(자막 없음)은 낮은 점수를 받아 자연히 빠진다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: 하이라이트가 원본의 몇 %를 넘지 않게 할지. 너무 크면 "하이라이트"가 아니라
#: 원본 재탕이 된다.
_DEFAULT_TARGET_RATIO = 0.4
#: 아무리 짧은 원본이어도 최소 이만큼은 하이라이트가 남게 한다.
_MIN_TARGET_SEC = 8.0


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


def select_highlight_segment_ids(
    segments: Sequence[Mapping[str, object]],
    *,
    target_ratio: float = _DEFAULT_TARGET_RATIO,
    min_target_sec: float = _MIN_TARGET_SEC,
) -> tuple[str, ...]:
    """자막 밀도가 높은 장면부터 목표 길이를 채울 때까지 고르고, 시간순으로 돌려준다.

    빈 입력이거나 아무 장면도 점수를 받지 못하면(자막이 하나도 없으면) 원본 순서
    그대로 전부 돌려준다 -- "하이라이트를 못 골랐다"고 조용히 빈 목록을 주면
    `OutputVariant`가 `min_length=1` 제약에 걸려 깨진다.
    """

    ordered = [segment for segment in segments if str(segment.get("segment_id") or "").strip()]
    if not ordered:
        return ()

    total_duration = sum(_segment_duration(segment) for segment in ordered)
    target_sec = max(min_target_sec, total_duration * target_ratio)

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
