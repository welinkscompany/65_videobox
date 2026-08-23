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
    """정규화한 상태를 타임라인 트랙에 실어 준다.

    합성계획(`CompositionPlan.from_timeline`)이 트랙 dict만 보고 판단할 수 있게
    한다 -- 렌더러가 세션을 다시 열지 않도록.
    """
    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        return timeline
    for track in tracks:
        if not isinstance(track, dict):
            continue
        kind = str(track.get("track_type") or "").strip()
        if track_is_hidden(states, kind):
            track["hidden"] = True
        if track_is_muted(states, kind):
            track["muted"] = True
    return timeline
