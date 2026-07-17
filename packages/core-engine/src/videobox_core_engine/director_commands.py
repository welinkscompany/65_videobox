from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


DirectorImmutableId = str | dict[str, str]


@dataclass(frozen=True)
class DirectorReference:
    reference_code: str
    immutable_id: DirectorImmutableId
    source: str


@dataclass(frozen=True)
class DirectorActionIntent:
    """A non-mutating, explicit next action guarded by proposal preflight."""
    action: str
    target: DirectorReference
    proposal_preflight: dict[str, str | int] | None


@dataclass(frozen=True)
class DirectorCommandResult:
    status: str
    reference: DirectorReference | None = None
    options: tuple[DirectorReference, ...] = ()
    action_intent: DirectorActionIntent | None = None


def director_timeline_references(timeline: dict[str, Any]) -> dict[str, Any]:
    """Derive durable visible B/M/S placements from persisted override truth."""
    counters = {"broll": 0, "bgm": 0, "sfx": 0}
    fields = (("broll", "broll_override", "B"), ("bgm", "music_override", "M"), ("sfx", "sfx_override", "S"))
    placements: list[dict[str, Any]] = []
    for segment in timeline.get("segments", []):
        if not isinstance(segment, dict) or not segment.get("segment_id"):
            continue
        for kind, field, prefix in fields:
            if not isinstance(segment.get(field), dict):
                continue
            counters[kind] += 1
            placements.append({"segment_id": str(segment["segment_id"]), "reference_code": f"{prefix}-{counters[kind]:02d}", "track_type": kind})
    return {**timeline, "segments": placements}


def resolve_director_command(command: str, *, open_proposal: dict[str, Any] | None, timeline: dict[str, Any] | None) -> DirectorCommandResult:
    """Resolve only to stable IDs; display codes are used solely for disambiguation."""
    text = command.upper()
    candidates = (open_proposal or {}).get("candidates", [])
    segments = (timeline or {}).get("segments", [])
    explicit = re.search(r"\b(P\d{1,3}-[BMS]-\d{1,3})\b", text)
    if explicit:
        code = explicit.group(1)
        for candidate in candidates:
            if str(candidate.get("visible_reference_code", "")).upper() == code:
                return _resolved(DirectorReference(code, str(candidate["candidate_id"]), "proposal"), open_proposal, timeline)
        return DirectorCommandResult("unresolved")
    placement = re.search(r"\b([BMS]-\d{1,3})\b", text)
    if placement:
        code = placement.group(1)
        for segment in segments:
            if str(segment.get("reference_code", "")).upper() == code:
                return _resolved(
                    DirectorReference(code, {"segment_id": str(segment["segment_id"]), "track_type": str(segment["track_type"])}, "timeline"),
                    open_proposal, timeline,
                )
        return DirectorCommandResult("unresolved")
    number = re.search(r"(\d+)", text)
    if not number:
        return DirectorCommandResult("unresolved")
    suffix = f"-{int(number.group(1)):02d}"
    options: list[DirectorReference] = []
    for candidate in candidates:
        code = str(candidate.get("visible_reference_code", "")).upper()
        if code.endswith(suffix):
            options.append(DirectorReference(code, str(candidate["candidate_id"]), "proposal"))
    for segment in segments:
        code = str(segment.get("reference_code", "")).upper()
        if code.endswith(suffix):
            options.append(
                DirectorReference(
                    code,
                    {"segment_id": str(segment["segment_id"]), "track_type": str(segment["track_type"])},
                    "timeline",
                )
            )
    if len(options) == 1:
        return _resolved(options[0], open_proposal, timeline)
    if options:
        return DirectorCommandResult("needs_disambiguation", options=tuple(options))
    return DirectorCommandResult("unresolved")


def _resolved(
    reference: DirectorReference, open_proposal: dict[str, Any] | None, timeline: dict[str, Any] | None,
) -> DirectorCommandResult:
    """Bind an intent to the immutable proposal revision that must be preflighted before apply."""
    binding: dict[str, str | int] | None = None
    if open_proposal and open_proposal.get("proposal_id"):
        binding = {"proposal_id": str(open_proposal["proposal_id"])}
        for field in ("base_session_revision", "asset_index_revision"):
            if isinstance(open_proposal.get(field), int):
                binding[field] = open_proposal[field]
    elif reference.source == "timeline" and timeline and timeline.get("session_id"):
        binding = {"session_id": str(timeline["session_id"])}
        if isinstance(timeline.get("session_revision"), int):
            binding["session_revision"] = timeline["session_revision"]
    intent = DirectorActionIntent(action="replace_media", target=reference, proposal_preflight=binding)
    return DirectorCommandResult("resolved", reference, action_intent=intent)
