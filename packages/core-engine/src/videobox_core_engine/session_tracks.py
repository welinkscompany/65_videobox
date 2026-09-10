"""자유 멀티트랙 Phase 5 -- 세션에 트랙 목록을 두고 실제로 고친다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 5.

Phase 1(`track_registry.py`)과 Phase 2(`clip_placement.py`)는 **읽기만** 하는
모델이라 아무것도 안 깨뜨리고 덧붙일 수 있었다. 여기는 **처음으로 쓰는
문**이라 지켜야 할 것이 둘 더 있다.

## 옛 세션을 안 깨뜨린다

트랙 목록을 저장한 적 없는 세션(지금 있는 편집본 전부)은 `session_tracks()`가
고정 다섯 역할로 읽어 준다(`migrate_legacy_tracks_to_registry`). 저장은
**실제로 고칠 때만** 생긴다 -- 열기만 해도 세션이 커지지 않는다.

## 되돌리기가 같이 돈다

`editing_transactions._snapshot()`은 담을 최상위 열쇠를 **이름으로 적어**
둔다. 새 열쇠를 넣고 그 자리를 안 넓히면 트랙 추가가 조용히 안 되돌려진다.
그래서 이 파일이 쓰는 열쇠 이름을 그쪽이 가져다 쓰도록 여기서 내보낸다.

## 이번 조각이 안 여는 것

**내레이션·자막 트랙은 못 늘린다.** 내레이션이 여럿이 되면 "무엇이 세그먼트
시간을 정하는가"가 흔들리고(Phase 3 타이밍 기준 결정), 자막은 어느
내레이션을 옮기는지가 걸린다. 조용히 받아 두면 그 결정을 몰래 전제하게
되므로 아예 거절한다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from videobox_core_engine.editing_session import FIXED_TIMELINE_TRACK_ROLES
from videobox_core_engine.editing_transactions import SESSION_TRACKS_KEY, apply_user_transaction
from videobox_core_engine.track_registry import (
    Track,
    migrate_legacy_tracks_to_registry,
    validate_tracks,
)

#: 이번 조각에서 늘릴 수 있는 종류. 내레이션·자막은 위 모듈 주석 참고.
ADDABLE_TRACK_KINDS = frozenset({"broll", "bgm", "sfx"})

#: 종류당 상한. 화면 세로 공간이 유한하고, 상한은 **나중에 넓히기는 쉬워도
#: 좁히기는 어렵다**(이미 여섯 줄을 만든 owner에게 "다섯까지"라고 말할 수 없다).
MAX_TRACKS_PER_KIND = 5


class SessionTrackError(ValueError):
    """트랙을 고칠 수 없는 요청(없는 트랙·상한 초과·마지막 줄 삭제 등)."""


def _track_from_payload(payload: dict[str, Any]) -> Track:
    return Track(
        track_id=str(payload.get("track_id") or ""),
        label=str(payload.get("label") or ""),
        kind=str(payload.get("kind") or ""),
        order=int(payload.get("order") or 0),
        is_timing_anchor=bool(payload.get("is_timing_anchor")),
        source_track_id=(str(payload["source_track_id"]) if payload.get("source_track_id") else None),
    )


def _payload_from_track(track: Track) -> dict[str, Any]:
    return {
        "track_id": track.track_id,
        "label": track.label,
        "kind": track.kind,
        "order": track.order,
        "is_timing_anchor": track.is_timing_anchor,
        "source_track_id": track.source_track_id,
    }


def session_tracks(session: dict[str, Any]) -> list[Track]:
    """세션의 트랙 목록. **저장된 적 없으면 옛 고정 다섯 역할로 읽는다.**

    지금 있는 편집본은 전부 이 길로 온다 -- 열기만 해서는 세션에 아무것도
    안 쓴다.
    """
    raw = session.get(SESSION_TRACKS_KEY)
    if not isinstance(raw, list) or not raw:
        return migrate_legacy_tracks_to_registry(FIXED_TIMELINE_TRACK_ROLES)
    tracks = [_track_from_payload(item) for item in raw if isinstance(item, dict)]
    validate_tracks(tracks)
    # **아래에서 위 순서로 돌려준다.** Phase 4에서 "나중 = 위"로 정했으므로
    # 목록 순서가 곧 화면의 아래→위다. 저장 순서에 기대면 순서를 바꾼 뒤
    # 목록만 보고는 위아래를 알 수 없다.
    return sorted(tracks, key=lambda track: track.order)


def _store(*, session: dict[str, Any], tracks: list[Track], label: str) -> dict[str, Any]:
    """트랙 목록을 세션에 쓴다. **반드시 되돌릴 수 있는 한 걸음으로 쓴다.**

    그냥 dict를 고치면 `undo_stack`에 안 남아서 owner가 실수로 지운 트랙을
    되돌릴 수 없다.
    """
    validate_tracks(tracks)
    payload = [_payload_from_track(track) for track in tracks]

    def mutate(draft: dict[str, Any]) -> None:
        draft[SESSION_TRACKS_KEY] = deepcopy(payload)

    return apply_user_transaction(
        session=session, label=label, affected_segment_ids=[],
        mutate=mutate, mutation_type="session_tracks_update",
    )


def _next_order(tracks: list[Track]) -> int:
    return max((track.order for track in tracks), default=-1) + 1


def add_session_track(*, session: dict[str, Any], kind: str, label: str) -> dict[str, Any]:
    """같은 종류의 **맨 위**에 트랙 하나를 얹는다.

    맨 위인 이유: Phase 4에서 "나중 = 위"로 정했고, 새로 만든 줄이 기존
    영상 **아래**로 숨어 버리면 owner가 만든 것을 못 찾는다.
    """
    if kind not in ADDABLE_TRACK_KINDS:
        raise SessionTrackError("session_track_kind_not_addable")
    if not isinstance(label, str) or not label.strip():
        raise SessionTrackError("session_track_label_required")
    tracks = session_tracks(session)
    same_kind = [track for track in tracks if track.kind == kind]
    if len(same_kind) >= MAX_TRACKS_PER_KIND:
        raise SessionTrackError("session_track_limit_reached")
    existing_ids = {track.track_id for track in tracks}
    suffix = len(same_kind) + 1
    track_id = f"track-{kind}-{suffix}"
    while track_id in existing_ids:
        suffix += 1
        track_id = f"track-{kind}-{suffix}"
    tracks.append(Track(
        track_id=track_id, label=label.strip(), kind=kind, order=_next_order(tracks),
    ))
    return _store(session=session, tracks=tracks, label="트랙 추가")


def remove_session_track(*, session: dict[str, Any], track_id: str) -> dict[str, Any]:
    """트랙 하나를 뺀다. **그 종류의 마지막 줄은 못 뺀다.**

    마지막 줄까지 빠지면 그 종류를 놓을 자리가 사라져, 되돌리기로만 복구되는
    상태가 조용히 생긴다.
    """
    tracks = session_tracks(session)
    target = next((track for track in tracks if track.track_id == track_id), None)
    if target is None:
        raise SessionTrackError("session_track_missing")
    if target.kind not in ADDABLE_TRACK_KINDS:
        raise SessionTrackError("session_track_kind_not_removable")
    if len([track for track in tracks if track.kind == target.kind]) <= 1:
        raise SessionTrackError("session_track_last_of_kind")
    return _store(session=session, tracks=[track for track in tracks if track.track_id != track_id], label="트랙 삭제")


def reorder_session_tracks(*, session: dict[str, Any], kind: str, track_ids: list[str]) -> dict[str, Any]:
    """한 종류 안에서 위아래 순서를 바꾼다(앞이 아래, 뒤가 위).

    **같은 트랙들이 빠짐없이 그대로 와야 한다.** 빠뜨린 목록을 받아 주면
    트랙이 조용히 사라지고, 없는 것이 섞이면 무엇을 만들지 알 수 없다.
    """
    tracks = session_tracks(session)
    same_kind = [track for track in tracks if track.kind == kind]
    if not same_kind:
        raise SessionTrackError("session_track_kind_missing")
    if sorted(track_ids) != sorted(track.track_id for track in same_kind):
        raise SessionTrackError("session_track_reorder_mismatch")

    by_id = {track.track_id: track for track in same_kind}
    slots = sorted(track.order for track in same_kind)
    reordered = {
        track_id: Track(
            track_id=by_id[track_id].track_id, label=by_id[track_id].label, kind=by_id[track_id].kind,
            order=slot, is_timing_anchor=by_id[track_id].is_timing_anchor,
            source_track_id=by_id[track_id].source_track_id,
        )
        for slot, track_id in zip(slots, track_ids)
    }
    return _store(session=session, tracks=[reordered.get(track.track_id, track) for track in tracks], label="트랙 순서 변경")


__all__ = [
    "ADDABLE_TRACK_KINDS",
    "MAX_TRACKS_PER_KIND",
    "SESSION_TRACKS_KEY",
    "SessionTrackError",
    "add_session_track",
    "remove_session_track",
    "reorder_session_tracks",
    "session_tracks",
]
