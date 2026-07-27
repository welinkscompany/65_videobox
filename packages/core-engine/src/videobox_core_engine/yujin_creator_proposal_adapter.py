"""Parse one trailing Yujin payload and project it to existing Director DTOs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from videobox_domain_models.director_proposals import (
    DirectorCandidate,
    DirectorProposal,
)
from videobox_domain_models.yujin_creator_context import YujinCreatorContext
from videobox_domain_models.yujin_creator_proposals import (
    UNSAFE_CREDENTIAL_LABEL_PATTERN,
    UNSAFE_CREDENTIAL_LABELS,
    YujinCreatorResponse,
    validate_yujin_creator_response,
)


MACHINE_FENCE = "```videobox-yujin-response"
MANUAL_FALLBACK = (
    "제안 형식을 확인하지 못했습니다. 수동 편집은 계속 사용할 수 있습니다."
)
_FRAME = re.compile(
    r"^(?P<reply>.*?)\s*```videobox-yujin-response[ \t]*\r?\n"
    r"(?P<payload>\{.*\})\r?\n```[ \t]*$",
    re.DOTALL,
)
_JSON_CUE = re.compile(
    r"(?i)\bjson(?:\s+(?:object|array|payload|response|envelope))?"
    r"\s*:\s*(?P<payload>[\{\[])"
)
_ENVELOPE_MARKER = re.compile(
    r'(?i)(?:"(?:schema_version|reply_text|proposal|operations)"\s*:|'
    r"\b(?:schema_version|reply_text|proposal|operations)\s*:|"
    r"videobox\.yujin-response\.v[0-9]+)"
)
_JSON_TOKEN_START = re.compile(
    r'^(?:"|\{|\[|[0-9]|-(?=[0-9])|'
    r"true(?:\b|$)|false(?:\b|$)|null(?:\b|$))"
)
_MACHINE_FIELDS = ("schema_version", "reply_text", "proposal", "operations")
_STRUCTURAL_MACHINE_ASSIGNMENT = re.compile(
    rf"(?i)^(?:{'|'.join(_MACHINE_FIELDS)}|{UNSAFE_CREDENTIAL_LABEL_PATTERN})\s*[=:]"
)
_LINE_MACHINE_ASSIGNMENT = re.compile(
    rf"(?im)^[ \t]*(?:\{{[ \t]*)?"
    rf"(?:{'|'.join(_MACHINE_FIELDS)}|{UNSAFE_CREDENTIAL_LABEL_PATTERN})\s*[=:]"
)


@dataclass(frozen=True)
class YujinCreatorProjection:
    reply_text: str
    proposal: DirectorProposal | None
    schema_version: str | None
    operation_count: int
    validation_outcome: str
    manual_fallback: bool


def parse_and_project_yujin_creator_output(
    raw_text: str,
    context: YujinCreatorContext,
    *,
    revision: int = 0,
    trusted_project_id: str | None = None,
    trusted_run_id: str | None = None,
) -> YujinCreatorProjection:
    """Return visible conversation text and an immutable candidate-only proposal."""

    match = _FRAME.fullmatch(raw_text)
    if match is None:
        if "```" not in raw_text:
            machine_boundary = _machine_like_boundary(raw_text)
            if machine_boundary is not None:
                return _invalid(raw_text[:machine_boundary])
            return YujinCreatorProjection(
                reply_text=raw_text,
                proposal=None,
                schema_version=None,
                operation_count=0,
                validation_outcome="legacy_text",
                manual_fallback=False,
            )
        return _invalid(_visible_prefix(raw_text))

    visible_reply = match.group("reply").strip()
    try:
        payload = json.loads(match.group("payload"))
        response = validate_yujin_creator_response(payload, context)
        if response.reply_text.strip() != visible_reply:
            return _invalid(visible_reply)
        if response.proposal is not None and (
            trusted_project_id is None or trusted_run_id is None
        ):
            return _invalid(visible_reply)
        proposal = (
            _project(
                response,
                context,
                revision=revision,
                trusted_proposal_id=derive_yujin_persisted_proposal_id(
                    project_id=trusted_project_id,
                    run_id=trusted_run_id,
                ),
            )
            if response.proposal is not None
            else None
        )
    except (TypeError, ValueError):
        return _invalid(visible_reply)
    return YujinCreatorProjection(
        reply_text=visible_reply,
        proposal=proposal,
        schema_version=response.schema_version,
        operation_count=(
            len(response.proposal.operations) if response.proposal is not None else 0
        ),
        validation_outcome="valid",
        manual_fallback=False,
    )


def derive_yujin_persisted_proposal_id(*, project_id: str, run_id: str) -> str:
    """Derive an opaque DB identity from the trusted run namespace."""

    namespace = json.dumps(
        ["videobox.yujin-proposal.v1", project_id, run_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"yujin-proposal-{hashlib.sha256(namespace).hexdigest()}"


def _derive_candidate_id(*, proposal_id: str, operation_index: int) -> str:
    namespace = f"{proposal_id}:{operation_index}".encode("ascii")
    return f"yujin-candidate-{hashlib.sha256(namespace).hexdigest()}"


def _visible_prefix(raw_text: str) -> str:
    return raw_text.split("```", 1)[0].strip()


def safe_yujin_stream_visible_prefix(raw_text: str) -> str:
    """Return only the monotonic human-visible prefix safe for live SSE."""

    fence_boundary = raw_text.find("```")
    machine_boundary = _machine_like_boundary(raw_text)
    boundaries = [
        boundary
        for boundary in (fence_boundary, machine_boundary)
        if boundary is not None and boundary >= 0
    ]
    if boundaries:
        return raw_text[: min(boundaries)].rstrip()

    possible_assignment = _possible_assignment_line_start(raw_text)
    if possible_assignment is not None:
        return raw_text[:possible_assignment].rstrip()

    lowered = raw_text.lower()
    markers = (
        "```",
        *_MACHINE_FIELDS,
        *UNSAFE_CREDENTIAL_LABELS,
        "videobox.yujin-response.v",
    )
    holdback = 0
    for marker in markers:
        for length in range(1, min(len(marker), len(lowered) + 1)):
            if lowered.endswith(marker[:length]):
                holdback = max(holdback, length)
    target = raw_text[:-holdback] if holdback else raw_text
    return target.rstrip()


def _machine_like_boundary(raw_text: str) -> int | None:
    assignment = _LINE_MACHINE_ASSIGNMENT.search(raw_text)
    if assignment is not None:
        return assignment.start()
    first_non_whitespace = len(raw_text) - len(raw_text.lstrip())
    if (
        first_non_whitespace < len(raw_text)
        and raw_text[first_non_whitespace] in "{["
    ):
        return first_non_whitespace

    cue = _JSON_CUE.search(raw_text)
    if cue is not None:
        return cue.start("payload")

    for index, character in enumerate(raw_text):
        if character not in "{[":
            continue
        if not _is_structural_payload_position(raw_text, index):
            continue
        container_suffix = raw_text[index + 1 :].lstrip()
        try:
            candidate, candidate_end = json.JSONDecoder().raw_decode(
                raw_text,
                index,
            )
        except (TypeError, ValueError):
            if _STRUCTURAL_MACHINE_ASSIGNMENT.match(container_suffix):
                return index
            if character == "{" and not container_suffix.startswith('"'):
                if not container_suffix or any(
                    literal.startswith(container_suffix)
                    for literal in ("true", "false", "null")
                ):
                    return index
                continue
            if not container_suffix or any(
                literal.startswith(container_suffix)
                for literal in ("true", "false", "null")
            ):
                return index
            if _JSON_TOKEN_START.match(container_suffix) is not None:
                return index
            continue
        if not isinstance(candidate, (dict, list)):
            continue
        trailing = raw_text[candidate_end:].strip()
        if trailing:
            if _has_human_trailing_prose(trailing):
                continue
            return index
        if _is_flat_scalar_list(candidate):
            continue
        return index

    marker = _ENVELOPE_MARKER.search(raw_text)
    if marker is None:
        return None
    object_start = max(
        raw_text.rfind("{", 0, marker.start() + 1),
        raw_text.rfind("[", 0, marker.start() + 1),
    )
    return object_start if object_start >= 0 else marker.start()


def _possible_assignment_line_start(raw_text: str) -> int | None:
    line_start = max(raw_text.rfind("\n"), raw_text.rfind("\r")) + 1
    raw_line = raw_text[line_start:]
    leading = len(raw_line) - len(raw_line.lstrip(" \t{"))
    line = raw_line[leading:]
    normalized = line.lower().replace("-", "_")
    keys = (*_MACHINE_FIELDS, *UNSAFE_CREDENTIAL_LABELS)
    for key in keys:
        if key.startswith(normalized):
            return line_start
        if normalized.startswith(key):
            remainder = normalized[len(key):]
            if not remainder or remainder.isspace() or re.fullmatch(r"\s*[=:]?\s*", remainder):
                return line_start
    return None


def _is_structural_payload_position(raw_text: str, index: int) -> bool:
    prefix = raw_text[:index]
    if not prefix.strip():
        return True
    line_start = max(prefix.rfind("\n"), prefix.rfind("\r")) + 1
    if not raw_text[line_start:index].strip():
        return True
    return prefix.rstrip().endswith(":")


def _has_human_trailing_prose(trailing: str) -> bool:
    if trailing.startswith(("{", "[", "```", ",")):
        return False
    return any(character.isalpha() for character in trailing)


def _is_flat_scalar_list(candidate: object) -> bool:
    return isinstance(candidate, list) and all(
        item is None or isinstance(item, (str, int, float, bool))
        for item in candidate
    )


def _invalid(reply_text: str) -> YujinCreatorProjection:
    visible = reply_text.strip()
    combined = f"{visible}\n\n{MANUAL_FALLBACK}" if visible else MANUAL_FALLBACK
    return YujinCreatorProjection(
        reply_text=combined,
        proposal=None,
        schema_version=None,
        operation_count=0,
        validation_outcome="invalid",
        manual_fallback=True,
    )


def _project(
    response: YujinCreatorResponse,
    context: YujinCreatorContext,
    *,
    revision: int,
    trusted_proposal_id: str,
) -> DirectorProposal:
    source = response.proposal
    assert source is not None
    candidates: list[DirectorCandidate] = []
    for index, operation in enumerate(source.operations, start=1):
        candidate_id = _derive_candidate_id(
            proposal_id=trusted_proposal_id,
            operation_index=index,
        )
        operation_data = operation.model_dump(mode="json", exclude={"operation_id"})
        candidates.append(
            DirectorCandidate(
            candidate_id=candidate_id,
            visible_reference_code=f"P{revision:02d}-{index:02d}",
            media_type=operation.kind,
            asset_id=getattr(operation.parameters, "asset_id", None) or candidate_id,
            library_asset_id=None,
            reason_chips=(operation.preview_summary,),
            scores={},
            availability="candidate_only",
            review_status="pending",
            preview_uri=None,
            controls=operation_data,
            expected_content_sha256=None,
            media_revision=source.base_revision,
            canonical_metadata={
                "schema_version": response.schema_version,
                "proposal_kind": operation.kind,
            },
        )
        )
    target_segments = tuple(
        dict.fromkeys(
            getattr(operation.target, "segment_id", None)
            for operation in source.operations
            if getattr(operation.target, "segment_id", None) is not None
        )
    )
    return DirectorProposal(
        proposal_id=trusted_proposal_id,
        revision_code=f"P{revision:02d}",
        revision=revision,
        base_session_revision=context.session_revision,
        asset_index_revision=context.asset_index_revision,
        source_session_id=context.session_id,
        target_segment_ids=target_segments,
        source_script_segment_ids=target_segments,
        status="candidate_only",
        diff={
            "proposal_mode": "candidate_only",
            "title": source.title,
            "rationale": source.rationale,
            "operations": [
                operation.model_dump(mode="json", exclude={"operation_id"})
                for operation in source.operations
            ],
        },
        expires_at=None,
        candidates=tuple(candidates),
    )
