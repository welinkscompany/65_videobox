"""Pure, fail-closed validation for untrusted Yujin editing candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Literal

from pydantic import ValidationError

from videobox_domain_models.yujin_editing_proposals import (
    ApplyMediaOperation,
    ReorderSegmentsOperation,
    YujinEditingProposal,
    YujinEditingResponse,
)


_MAX_PAYLOAD_BYTES = 32_768
_UNSAFE_TERMS = (
    "filesystem",
    "file system",
    "network",
    "provider",
    "http://",
    "https://",
    "shell",
    "powershell",
    "curl",
    "api key",
)


@dataclass(frozen=True)
class YujinEditingContext:
    session_id: str
    session_revision: int
    segment_ids: tuple[str, ...]
    approved_asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class YujinEditingResult:
    status: Literal["candidate_only", "clarification", "rejected"]
    proposal: YujinEditingProposal | None
    reason: str | None = None


def interpret_yujin_editing_request(
    payload: str | Mapping[str, object], context: YujinEditingContext
) -> YujinEditingResult:
    """Return an unpersisted candidate only when every target is current."""

    raw = _decode_bounded_payload(payload)
    if raw is None or _contains_unsafe_instruction(raw):
        return _rejected("invalid_payload_or_unsafe_instruction")
    if raw.get("proposal") is None and isinstance(raw.get("reply_text"), str):
        return YujinEditingResult(status="clarification", proposal=None)
    try:
        response = YujinEditingResponse.model_validate(raw)
    except ValidationError:
        return _rejected("invalid_editing_response")
    if response.proposal is None:
        return YujinEditingResult(status="clarification", proposal=None)
    reason = _validate_current_targets(response.proposal, context)
    return _rejected(reason) if reason is not None else YujinEditingResult(
        status="candidate_only", proposal=response.proposal
    )


def _decode_bounded_payload(payload: str | Mapping[str, object]) -> dict[str, object] | None:
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            return None
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            return None
    elif isinstance(payload, Mapping):
        decoded = dict(payload)
        try:
            if len(json.dumps(decoded, ensure_ascii=False).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
                return None
        except (TypeError, ValueError):
            return None
    else:
        return None
    return decoded if type(decoded) is dict and all(type(key) is str for key in decoded) else None


def _contains_unsafe_instruction(value: object) -> bool:
    if isinstance(value, str):
        folded = value.casefold()
        return any(term in folded for term in _UNSAFE_TERMS)
    if isinstance(value, Mapping):
        return any(_contains_unsafe_instruction(key) or _contains_unsafe_instruction(item) for key, item in value.items())
    if type(value) in (list, tuple):
        return any(_contains_unsafe_instruction(item) for item in value)
    return False


def _validate_current_targets(proposal: YujinEditingProposal, context: YujinEditingContext) -> str | None:
    if proposal.base_session_revision != context.session_revision:
        return "stale_session_revision"
    current_segment_ids = set(context.segment_ids)
    if len(current_segment_ids) != len(context.segment_ids) or not current_segment_ids:
        return "invalid_current_context"
    operation_targets: set[tuple[str, str]] = set()
    for operation in proposal.operations:
        if isinstance(operation, ReorderSegmentsOperation):
            if len(operation.segment_ids) != len(current_segment_ids) or set(operation.segment_ids) != current_segment_ids:
                return "reorder_segments_not_current"
            key = (operation.intent, "all")
        else:
            if operation.segment_id not in current_segment_ids:
                return "segment_not_current"
            key = (operation.intent, operation.segment_id)
        if key in operation_targets:
            return "duplicate_conflicting_operation"
        operation_targets.add(key)
        if isinstance(operation, ApplyMediaOperation) and operation.asset_id not in set(context.approved_asset_ids):
            return "media_asset_not_approved"
    return None


def _rejected(reason: str) -> YujinEditingResult:
    return YujinEditingResult(status="rejected", proposal=None, reason=reason)


__all__ = ["YujinEditingContext", "YujinEditingResult", "interpret_yujin_editing_request"]
