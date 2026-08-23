"""장면과 장면 사이를 넘기는 방법 -- 전환.

**왜 여섯 개뿐인가.** `pycapcut`에는 전환 이름표가 1,137개 들어 있다
(`docs/implementation-plan.ko.md` §4.1.1). 그 중 985개는 캡컷 유료 항목이고,
무엇보다 **그건 효과가 아니라 캡컷 서버 자원을 가리키는 이름표다** -- 픽셀도
셰이더도 없어서 우리 ffmpeg 렌더러는 그것으로 아무것도 그릴 수 없다.

그래서 목록을 옮겨 오지 않고, ffmpeg `xfade`가 **직접 그려 주는 것** 중에서
서로 생김새가 겹치지 않는 여섯 갈래를 골랐다. 갈래가 겹치면 고르는 사람에게
선택지가 늘어나는 게 아니라 고민만 는다.

`key`를 `xfade`의 이름과 **같게** 두었다. 다만 그 이름을 그대로 믿고 넘기지
않는다 -- 아래 allowlist에 있는 것만 통과한다. 이 값은 결국 필터 문자열로
들어가므로, 모르는 값이 그대로 흘러가면 안 된다.

**추가하려면** `TRANSITION_CATALOG`에 한 줄 넣으면 된다. 렌더러는 이 표만 본다.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


# 고른 갈래와 그 이유. **방향이 있는 것은 짝을 이룬다.**
#
# 2026-08-23 갱신: 처음에는 방향 변종을 통째로 뺐다("갈래가 겹치면 고르는
# 사람에게 선택지가 늘어나는 게 아니라 고민만 는다"). 그 판단을 좁혀서 되돌린다
# -- **반대 방향은 겹치는 게 아니라 반대다.** 인물이 오른쪽으로 걸어 나가는
# 장면에 왼쪽으로 쓸어내면 전환이 움직임과 싸운다. 되돌릴 길이 없으면 그
# 장면에서는 쓸기를 아예 못 쓴다.
#
# 다만 **네 방향까지 벌리지는 않는다**(`wipeup`·`slideleft` 등). 여덟이 열둘이
# 되면 그때는 원래 뺐던 이유에 그대로 걸린다. 짝 하나씩만이다.
TRANSITION_CATALOG: dict[str, dict[str, str]] = {
    # 가장 많이 쓰는 것. 두 장면이 서로 비치며 겹친다.
    "fade": {"label": "서서히 겹치기", "family": "겹침"},
    # 시간이 흘렀다는 표시. 인터뷰·해설 영상에서 장 구분에 쓴다.
    "fadeblack": {"label": "검게 저물기", "family": "겹침"},
    # `fade`와 결과가 비슷해 보이지만 알갱이가 흩어지듯 넘어간다.
    "dissolve": {"label": "흩어지며 넘기기", "family": "겹침"},
    # 경계선이 화면을 쓸고 지나간다.
    "wipeleft": {"label": "왼쪽으로 쓸어내기", "family": "쓸기"},
    # 같은 쓸기를 반대로. 화면 속 움직임이 오른쪽일 때 쓴다.
    "wiperight": {"label": "오른쪽으로 쓸어내기", "family": "쓸기"},
    # 다음 장면이 아래에서 올라와 앞 장면을 밀어낸다.
    "slideup": {"label": "위로 밀어올리기", "family": "밀기"},
    # 같은 밀기를 반대로. 되짚어 가는 느낌이 필요할 때.
    "slidedown": {"label": "아래로 밀어내리기", "family": "밀기"},
    # 원이 열리며 다음 장면이 나온다.
    "circleopen": {"label": "원으로 열기", "family": "모양"},
}

TRANSITION_TYPES = frozenset(TRANSITION_CATALOG)

# 화면 입력이 허용할 범위와 **같은** 경계다. `media_controls`의 SPEED_RANGE가
# 같은 이유로 그렇게 되어 있다 -- 여기를 넓게 열면 화면에서 만들 수 없는 값이
# 저장되고, 그 값은 결국 렌더러에서 터진다.
#
# 위 경계 2.0초는 임의로 정한 것이 아니다. 전환은 **앞 장면의 남은 원본**을
# 빌려 쓰는데(아래 참고), 길수록 빌릴 것이 모자라 마지막 프레임이 멎는다.
TRANSITION_DURATION_RANGE = (0.1, 2.0)
DEFAULT_TRANSITION_DURATION_SEC = 0.5

# 누가 골랐는가. **지금은 owner뿐이지만** 자리를 미리 만들어 둔다 --
# 이 제품의 값어치는 유진이 골라 주는 데 있고(`implementation-plan.ko.md` §4.2),
# 그때 "이건 유진이 고른 것"이라고 말할 수 없으면 추천을 되돌릴 수도,
# 왜 이렇게 됐는지 설명할 수도 없다.
TRANSITION_CHOOSERS = frozenset({"owner", "yujin"})
DEFAULT_TRANSITION_CHOOSER = "owner"


def _finite_number(value: object) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("transition_invalid_number") from exc
    if not isfinite(parsed):
        raise ValueError("transition_invalid_number")
    return parsed


def normalize_transition(transition: object) -> dict[str, Any] | None:
    """전환 값 하나를 정규화한다. 전환이 없으면 ``None``.

    ``None``과 ``{"type": "none"}``을 **둘 다** "전환 없음"으로 받는다.
    화면에서 골랐다가 다시 끄는 길이 있어야 하는데, 그때 보내는 값이 무엇이든
    같은 뜻이어야 한다.
    """
    if transition is None:
        return None
    if not isinstance(transition, dict):
        raise ValueError("transition_must_be_an_object")
    raw_type = str(transition.get("type") or "").strip().lower()
    if not raw_type or raw_type == "none":
        return None
    if raw_type not in TRANSITION_TYPES:
        raise ValueError(
            "transition type must be one of: " + ", ".join(sorted(TRANSITION_TYPES))
        )
    duration_sec = _finite_number(
        transition.get("duration_sec", DEFAULT_TRANSITION_DURATION_SEC)
    )
    low, high = TRANSITION_DURATION_RANGE
    if not low <= duration_sec <= high:
        raise ValueError(f"transition duration_sec must be between {low} and {high}.")
    chosen_by = str(
        transition.get("chosen_by") or DEFAULT_TRANSITION_CHOOSER
    ).strip().lower()
    if chosen_by not in TRANSITION_CHOOSERS:
        raise ValueError(
            "transition chosen_by must be one of: " + ", ".join(sorted(TRANSITION_CHOOSERS))
        )
    return {"type": raw_type, "duration_sec": duration_sec, "chosen_by": chosen_by}
