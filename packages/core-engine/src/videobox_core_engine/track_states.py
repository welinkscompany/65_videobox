"""트랙을 통째로 숨기거나 소리를 끄는 값. 캡컷 타임라인의 눈·음소거다.

`capcut-observed` 기록 §2: "트랙마다 왼쪽에 잠금 · 눈 · 음소거 · `···`".
잠금은 화면 안에서만 쓰는 것이라 `TimelineDock`이 혼자 들고 있지만(끌다가
실수로 미는 것을 막는 용도), **눈과 음소거는 결과물이 달라지는 편집**이라
세션에 남고 렌더까지 흘러야 한다.

**트랙마다 뜻이 있는 것만 둔다.** 자막 트랙에 음소거를 달면 눌러도 아무 일도
일어나지 않는 단추가 된다 -- 캡컷이 모든 트랙에 아이콘 셋을 다 그린다고 해서
우리도 그럴 이유는 없다(`docs/reference/capcut-observed-2026-08-22.ko.md` §4:
"띠에 없는 기능의 자리를 만들지 않는다").

| 트랙 | 숨김 | 음소거 | 왜 |
|---|---|---|---|
| `narration` | ✗ | ✓ | 소리뿐이다 |
| `broll` | ✓ | ✓ | 그림이고, 원본 소리를 실을 수도 있다 |
| `bgm` | ✗ | ✓ | 소리뿐이다 |
| `sfx` | ✗ | ✓ | 소리뿐이다 |
| `overlay` | ✓ | ✗ | 그림뿐이다 |
| `caption` | ✓ | ✗ | 글자뿐이다 |
"""
from __future__ import annotations

from typing import Any


HIDEABLE_TRACKS = frozenset({"broll", "overlay", "caption"})
MUTABLE_TRACKS = frozenset({"narration", "broll", "bgm", "sfx"})
TRACK_STATE_KINDS = HIDEABLE_TRACKS | MUTABLE_TRACKS


def normalize_track_states(value: object) -> dict[str, dict[str, bool]]:
    """세션에 저장된 트랙 상태를 검증해 정규화한다.

    없는 값(`None`, 빈 dict)은 "전부 기본"이라 빈 dict를 돌려준다. 기본값만
    담긴 항목은 아예 빼서, 아무것도 안 건드린 세션과 눈·음소거를 켰다 끈
    세션이 같은 모양으로 남게 한다 -- 그래야 저장분이 쓸데없이 커지지 않는다.

    뜻이 없는 조합(자막 트랙의 음소거 등)은 **조용히 버리지 않고 거절한다.**
    조용히 버리면 화면에서 켠 것이 저장은 성공했는데 결과가 그대로인, 이
    저장소가 이미 한 번 겪은 일이 된다(`media_controls.py`의 배속·음량 주석).
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("track_states_invalid")
    normalized: dict[str, dict[str, bool]] = {}
    for raw_kind, raw_state in value.items():
        kind = str(raw_kind or "").strip()
        if kind not in TRACK_STATE_KINDS:
            raise ValueError("track_states_unknown_track")
        if not isinstance(raw_state, dict):
            raise ValueError("track_states_invalid")
        state: dict[str, bool] = {}
        for field, allowed in (("hidden", HIDEABLE_TRACKS), ("muted", MUTABLE_TRACKS)):
            if field not in raw_state:
                continue
            flag = raw_state[field]
            if not isinstance(flag, bool):
                raise ValueError("track_states_invalid")
            if kind not in allowed:
                raise ValueError(f"track_states_{field}_unsupported")
            if flag:
                state[field] = True
        if set(raw_state) - {"hidden", "muted"}:
            raise ValueError("track_states_invalid")
        if state:
            normalized[kind] = state
    return dict(sorted(normalized.items()))


def track_is_hidden(states: dict[str, dict[str, bool]], kind: str) -> bool:
    return bool(states.get(kind, {}).get("hidden"))


def track_is_muted(states: dict[str, dict[str, bool]], kind: str) -> bool:
    return bool(states.get(kind, {}).get("muted"))


def apply_track_states_to_timeline(
    *, timeline: dict[str, Any], states: dict[str, dict[str, bool]]
) -> dict[str, Any]:
    """정규화한 상태를 타임라인에 **맨 위 한 칸으로** 실어 준다.

    합성계획(`CompositionPlan.from_timeline`)이 세션을 다시 열지 않고 판단할 수
    있게 하는 것이 목적이다.

    **트랙마다 표시하지 않는다.** 처음엔 그렇게 했는데 두 가지가 새어 나갔다
    (2026-08-23 코드리뷰에서 발견):

    - `materialize_editing_session_timeline`은 **지원 트랙만, 클립이 있을 때만**
      낸다. 자막 트랙은 아예 안 만들고, 빈 오버레이 트랙도 안 만든다. 표시할
      트랙이 없으니 자막·오버레이 숨김이 렌더까지 닿지 못했다.
    - 글자 오버레이는 `tracks`가 아니라 `export_overlays`에 있다.

    맨 위 한 칸이면 트랙이 살아남았는지와 무관하게 읽힌다.
    """
    timeline["track_states"] = {kind: dict(state) for kind, state in states.items()}
    return timeline


def hidden_lanes(timeline: dict[str, Any]) -> frozenset[str]:
    """이 타임라인에서 꺼진(눈) 레인. 없으면 빈 집합."""
    states = timeline.get("track_states")
    if not isinstance(states, dict):
        return frozenset()
    return frozenset(
        kind for kind, state in states.items()
        if isinstance(state, dict) and state.get("hidden")
    )


def muted_lanes(timeline: dict[str, Any]) -> frozenset[str]:
    """이 타임라인에서 소리를 끈 레인. 없으면 빈 집합.

    **음소거는 트랙마다 쓰는 제어가 다르다** -- 내레이션은 `media_controls`를
    아예 안 읽고, `bgm`·`sfx`는 `gain_db`, `broll`만 `volume`이다. 그래서
    합성계획에서 값 하나를 덮어쓰는 방식으로는 넷 중 하나밖에 못 껐다.
    어느 레인이 꺼졌는지를 렌더러까지 들고 가서, 렌더러가 그 레인의 소리를
    **아예 섞지 않는** 쪽이 넷 모두에 통한다.
    """
    states = timeline.get("track_states")
    if not isinstance(states, dict):
        return frozenset()
    return frozenset(
        kind for kind, state in states.items()
        if isinstance(state, dict) and state.get("muted")
    )
