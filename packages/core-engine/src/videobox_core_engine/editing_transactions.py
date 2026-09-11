"""Named, bounded editing-session transactions shared by director and manual edits."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable
import uuid

MAX_USER_UNDO_ACTIONS = 10
MAX_AUDIT_HISTORY = 100

#: 세션에서 트랙 목록이 사는 자리(자유 멀티트랙 Phase 5). **여기에 둔다** --
#: `session_tracks.py`에 두면 그쪽이 `editing_session`을 부르고 그쪽이 다시
#: 이 파일을 불러 순환이 된다. 되돌리기가 담을 열쇠를 이름으로 적는 구조라
#: 이름이 두 곳에 흩어지면 한쪽만 고쳤을 때 조용히 안 담긴다.
SESSION_TRACKS_KEY = "tracks"

#: 트랙 눈·음소거 상태가 사는 자리(`set_track_states`, `editing_session.py:765`).
#: 그 함수의 docstring이 "되돌리기 대상"이라고 명시하는데 정작 이 스냅샷에
#: 이름이 빠져 있었다 -- 트랙을 숨기고 Ctrl+Z를 눌러도 숨김이 그대로 남는
#: 결함이었다. `SESSION_TRACKS_KEY`와 같은 이유로 이름을 상수로 뽑아 둔다.
SESSION_TRACK_STATES_KEY = "track_states"


def _snapshot(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "segments": deepcopy(session.get("segments", [])),
        "caption_style": deepcopy(session.get("caption_style")),
        "timeline_placement_overrides": deepcopy(session.get("timeline_placement_overrides")),
        # 트랙 목록(자유 멀티트랙 Phase 5). **여기에 이름을 안 적으면 트랙
        # 추가·삭제가 조용히 안 되돌려진다** -- 담을 열쇠를 이름으로 적는
        # 구조라, 새 열쇠를 넣을 때마다 이 자리를 같이 넓혀야 한다
        # (`timeline_placement_overrides`를 넣을 때 이미 한 번 그랬다).
        SESSION_TRACKS_KEY: deepcopy(session.get(SESSION_TRACKS_KEY)),
        # 트랙 눈·음소거 상태. 위와 같은 이유로 이름을 적어야 담긴다.
        SESSION_TRACK_STATES_KEY: deepcopy(session.get(SESSION_TRACK_STATES_KEY)),
    }


def apply_user_transaction(
    *, session: dict[str, Any], label: str, affected_segment_ids: list[str],
    mutate: Callable[[dict[str, Any]], object], reversible: bool = True,
    blocked_reason: str | None = None, mutation_type: str = "user_transaction",
) -> dict[str, Any]:
    """Apply all changes to a detached draft before adding a single named action."""
    before = deepcopy(session)
    draft = deepcopy(session)
    mutate(draft)
    draft["session_revision"] = int(before.get("session_revision") or 1) + 1
    event = {
        "action_id": f"action:{uuid.uuid4().hex}", "label": label,
        "created_at": datetime.now(UTC).isoformat(), "reversible": reversible,
        "blocked_reason": blocked_reason, "affected_segment_ids": list(affected_segment_ids),
        "mutation_type": mutation_type, "segment_id": affected_segment_ids[0] if affected_segment_ids else "",
        "inverse_payload": _snapshot(before), "forward_payload": _snapshot(draft),
    }
    history = list(deepcopy(before.get("history", []))) + [deepcopy(event)]
    draft["history"] = history[-MAX_AUDIT_HISTORY:]
    undo = list(deepcopy(before.get("undo_stack", [])))
    if reversible:
        undo.append(event)
    draft["undo_stack"] = undo[-MAX_USER_UNDO_ACTIONS:]
    draft["redo_stack"] = []
    revision = int(before.get("session_revision") or 1) + 1
    draft["output_freshness"] = {
        kind: {"source_session_revision": revision, "is_current": False,
               "invalidated_at": event["created_at"], "invalidated_reason": label}
        for kind in ("review", "subtitle", "preview", "final", "capcut")
    }
    return draft
