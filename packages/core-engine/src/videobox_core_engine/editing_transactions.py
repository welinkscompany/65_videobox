"""Named, bounded editing-session transactions shared by director and manual edits."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable
import uuid

MAX_USER_UNDO_ACTIONS = 10
MAX_AUDIT_HISTORY = 100


def _snapshot(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "segments": deepcopy(session.get("segments", [])),
        "caption_style": deepcopy(session.get("caption_style")),
        "timeline_placement_overrides": deepcopy(session.get("timeline_placement_overrides")),
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
