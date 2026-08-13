"""Parse one trailing Yujin payload and project it to existing Director DTOs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import re

from videobox_storage.local_project_store import sha256_file
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


_ACTIONABLE_MEDIA_KINDS = frozenset({"broll", "bgm", "sfx"})
_BROLL_SOURCE_KINDS = frozenset({"raw_video", "broll_video"})
_ACTIONABLE_B4_KINDS = frozenset({"caption", "voice", "overlay"})


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


def activate_yujin_media_projection(
    *,
    store: object,
    project_id: str,
    context: YujinCreatorContext,
    projection: YujinCreatorProjection,
) -> YujinCreatorProjection:
    """Read-only attest actionable B3 media while preserving deferred candidates."""

    proposal = projection.proposal
    if proposal is None:
        return projection
    try:
        session = store.get_editing_session(  # type: ignore[attr-defined]
            project_id=project_id,
            session_id=context.session_id,
        )
        if (
            str(session.get("project_id") or "") != project_id
            or str(session.get("session_id") or "") != context.session_id
            or int(session.get("session_revision") or 0)
            != context.session_revision
            or int(store.get_asset_index_revision(project_id))  # type: ignore[attr-defined]
            != context.asset_index_revision
        ):
            return projection
    except (AttributeError, KeyError, TypeError, ValueError):
        return projection

    operations = tuple(proposal.diff.get("operations", ()))
    media_by_id = {item.asset_id: item for item in context.media_candidates}
    segments_by_id = {item.segment_id: item for item in context.segment_summaries}
    activated: list[DirectorCandidate] = []
    actionable_count = 0
    for index, candidate in enumerate(proposal.candidates):
        operation = operations[index] if index < len(operations) else None
        replacement = (
            _attest_media_candidate(
                store=store,
                project_id=project_id,
                context=context,
                candidate=candidate,
                operation=operation,
                media_by_id=media_by_id,
                segments_by_id=segments_by_id,
            )
            if candidate.media_type in _ACTIONABLE_MEDIA_KINDS
            else _attest_b4_candidate(
                store=store,
                project_id=project_id,
                context=context,
                candidate=candidate,
                operation=operation,
                media_by_id=media_by_id,
                segments_by_id=segments_by_id,
            )
        )
        activated.append(replacement)
        if replacement.availability == "actionable":
            actionable_count += 1
    try:
        session_after = store.get_editing_session(  # type: ignore[attr-defined]
            project_id=project_id,
            session_id=context.session_id,
        )
        if (
            int(session_after.get("session_revision") or 0)
            != context.session_revision
            or int(store.get_asset_index_revision(project_id))  # type: ignore[attr-defined]
            != context.asset_index_revision
        ):
            return projection
    except (AttributeError, KeyError, TypeError, ValueError):
        return projection

    has_b4_actionable = any(
        item.availability == "actionable"
        and item.media_type in _ACTIONABLE_B4_KINDS
        for item in activated
    )
    mode = (
        "yujin_actionable_v1"
        if has_b4_actionable
        else "yujin_actionable_media_v1"
        if actionable_count
        else "candidate_only"
    )
    updated_proposal = replace(
        proposal,
        status="ready" if actionable_count else "candidate_only",
        candidates=tuple(activated),
        diff={**dict(proposal.diff), "proposal_mode": mode},
    )
    return replace(projection, proposal=updated_proposal)


def _attest_b4_candidate(
    *,
    store: object,
    project_id: str,
    context: YujinCreatorContext,
    candidate: DirectorCandidate,
    operation: object,
    media_by_id: dict[str, object],
    segments_by_id: dict[str, object],
) -> DirectorCandidate:
    if not isinstance(operation, Mapping) or operation.get("kind") != candidate.media_type:
        return candidate
    parameters = operation.get("parameters")
    target = operation.get("target")
    if not isinstance(parameters, Mapping) or not isinstance(target, Mapping):
        return candidate
    parameters = dict(parameters)
    target = dict(target)

    if candidate.media_type == "output_check":
        if parameters != {"check": "timeline_gaps"}:
            return candidate
        gap_count = context.timeline_summary.gap_count
        finding_summary = f"타임라인 빈 구간 검사 결과: {gap_count}개"
        return replace(
            candidate,
            availability="read_only",
            review_status="not_applicable",
            reason_chips=(finding_summary,),
            controls={
                "check": "timeline_gaps",
                "gap_count": gap_count,
            },
            canonical_metadata={
                **dict(candidate.canonical_metadata),
                "yujin_read_only_finding": True,
                "selectable": False,
                "render_calls": 0,
                "preview_summary": finding_summary,
            },
        )

    if candidate.media_type not in _ACTIONABLE_B4_KINDS:
        return candidate
    segment_id = str(target.get("segment_id") or "")
    if segment_id not in segments_by_id:
        return candidate
    preview_summary = str(operation.get("preview_summary") or "")
    metadata: dict[str, object] = {
        **dict(candidate.canonical_metadata),
        "yujin_actionable_operation": True,
        "target_segment_id": segment_id,
        "preview_summary": preview_summary,
        "base_session_revision": context.session_revision,
        "asset_index_revision": context.asset_index_revision,
        "requires_materialization": False,
    }
    expected_sha256: str | None = None
    media_revision = candidate.media_revision

    if candidate.media_type == "caption":
        action = parameters.get("action")
        if action == "set_text":
            controls = {"text": parameters.get("text")}
            metadata["command_kind"] = "set_caption_text"
        elif action == "set_style" and isinstance(parameters.get("style"), Mapping):
            controls = {
                "scope": "current_caption",
                "style": dict(parameters["style"]),
            }
            metadata["command_kind"] = "set_caption_style"
        else:
            return candidate
    elif candidate.media_type == "voice":
        candidate_id = str(parameters.get("candidate_id") or "")
        asset_id = str(parameters.get("asset_id") or "")
        approved = next(
            (
                item
                for item in context.approved_tts_candidates
                if item.candidate_id == candidate_id
                and item.asset_id == asset_id
                and item.segment_id == segment_id
            ),
            None,
        )
        if approved is None or not candidate_id.startswith("tts_candidate_"):
            return candidate
        try:
            persisted = store.get_tts_candidate(  # type: ignore[attr-defined]
                project_id=project_id,
                candidate_id=candidate_id,
            )
            asset = store.get_asset(  # type: ignore[attr-defined]
                project_id=project_id,
                asset_id=asset_id,
            )
            source = store.resolve_storage_uri(  # type: ignore[attr-defined]
                project_id=project_id,
                storage_uri=str(asset["storage_uri"]),
            )
            digest = sha256_file(source) if source.is_file() else ""
            actual_revision = str(asset.get("created_at") or "").strip()
            if (
                str(persisted.get("project_id") or "") != project_id
                or str(persisted.get("candidate_id") or "") != candidate_id
                or str(persisted.get("asset_id") or "") != asset_id
                or str(persisted.get("segment_id") or "") != segment_id
                or persisted.get("technical_status") != "accepted"
                or persisted.get("operator_review_status") != "approved"
                or str(asset.get("project_id") or "") != project_id
                or str(asset.get("asset_type") or "") != "generated_tts_audio"
                or actual_revision != approved.asset_revision
                or digest != approved.expected_content_sha256
            ):
                return candidate
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            return candidate
        controls = {
            "candidate_id": candidate_id,
            "asset_id": asset_id,
        }
        metadata.update(
            {
                "command_kind": "apply_tts_candidate",
                "candidate_id": candidate_id,
                "source_media_kind": "generated_tts_audio",
            }
        )
        expected_sha256 = digest
        media_revision = actual_revision
    else:
        overlay_kind = str(parameters.get("overlay_kind") or "")
        if overlay_kind == "explanation_card":
            controls = {
                "overlay_kind": "explanation-card",
                "title": parameters.get("title"),
                "body": parameters.get("body"),
                "text": parameters.get("text"),
            }
        elif overlay_kind == "table":
            controls = {
                "overlay_kind": "table",
                "columns": list(parameters.get("columns") or ()),
                "rows": [list(row) for row in parameters.get("rows") or ()],
                "text": parameters.get("text"),
            }
        elif overlay_kind == "image":
            asset_id = str(parameters.get("asset_id") or "")
            context_asset = media_by_id.get(asset_id)
            if getattr(context_asset, "kind", None) != "image":
                return candidate
            try:
                asset = store.get_asset(  # type: ignore[attr-defined]
                    project_id=project_id,
                    asset_id=asset_id,
                )
                source = store.resolve_storage_uri(  # type: ignore[attr-defined]
                    project_id=project_id,
                    storage_uri=str(asset["storage_uri"]),
                )
                digest = sha256_file(source) if source.is_file() else ""
                actual_revision = str(asset.get("created_at") or "").strip()
                if (
                    str(asset.get("project_id") or "") != project_id
                    or str(asset.get("asset_type") or "") != "image"
                    or not digest
                    or not actual_revision
                ):
                    return candidate
            except (AttributeError, KeyError, OSError, TypeError, ValueError):
                return candidate
            controls = {
                "overlay_kind": "image",
                "asset_id": asset_id,
                "text": parameters.get("text"),
            }
            metadata["source_media_kind"] = "image"
            expected_sha256 = digest
            media_revision = actual_revision
        else:
            return candidate
        metadata["command_kind"] = "apply_overlay"

    return replace(
        candidate,
        availability="actionable",
        review_status="approved",
        controls=controls,
        expected_content_sha256=expected_sha256,
        media_revision=media_revision,
        canonical_metadata=metadata,
    )


def _attest_media_candidate(
    *,
    store: object,
    project_id: str,
    context: YujinCreatorContext,
    candidate: DirectorCandidate,
    operation: object,
    media_by_id: dict[str, object],
    segments_by_id: dict[str, object],
) -> DirectorCandidate:
    if (
        candidate.media_type not in _ACTIONABLE_MEDIA_KINDS
        or not isinstance(operation, Mapping)
        or operation.get("kind") != candidate.media_type
    ):
        return candidate
    parameters = operation.get("parameters")
    target = operation.get("target")
    if not isinstance(parameters, Mapping) or not isinstance(target, Mapping):
        return candidate
    parameters = dict(parameters)
    target = dict(target)
    asset_id = parameters.get("asset_id")
    if asset_id != candidate.asset_id or not isinstance(asset_id, str):
        return candidate
    context_media = media_by_id.get(asset_id)
    source_media_kind = getattr(context_media, "kind", None)
    target_segment_id = _aligned_target_segment_id(
        kind=candidate.media_type,
        target=target,
        parameters=parameters,
        segments_by_id=segments_by_id,
    )
    expected_source_kinds = (
        _BROLL_SOURCE_KINDS
        if candidate.media_type == "broll"
        else frozenset({candidate.media_type})
    )
    if target_segment_id is None or source_media_kind not in expected_source_kinds:
        return candidate
    try:
        asset = store.get_asset(  # type: ignore[attr-defined]
            project_id=project_id,
            asset_id=asset_id,
        )
        if str(asset.get("asset_type") or "") != source_media_kind:
            return candidate
        source = store.resolve_storage_uri(  # type: ignore[attr-defined]
            project_id=project_id,
            storage_uri=str(asset["storage_uri"]),
        )
        if not source.is_file():
            return candidate
        digest = sha256_file(source)
        media_revision = str(asset.get("created_at") or "").strip()
        if not digest or not media_revision:
            return candidate
        if not _eligible_media_asset(
            store=store,
            project_id=project_id,
            asset=asset,
            candidate=candidate,
        ):
            return candidate
        if not source.is_file() or sha256_file(source) != digest:
            return candidate
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return candidate

    controls = _supported_media_controls(
        kind=candidate.media_type,
        parameters=parameters,
    )
    return replace(
        candidate,
        availability="actionable",
        review_status="approved",
        controls=controls,
        expected_content_sha256=digest,
        media_revision=media_revision,
        canonical_metadata={
            **dict(candidate.canonical_metadata),
            "yujin_actionable_media": True,
            "source_media_kind": source_media_kind,
            "target_segment_id": target_segment_id,
            "preview_summary": str(operation.get("preview_summary") or ""),
            "base_session_revision": context.session_revision,
            "asset_index_revision": context.asset_index_revision,
        },
    )


def _aligned_target_segment_id(
    *,
    kind: str,
    target: dict[str, object],
    parameters: dict[str, object],
    segments_by_id: dict[str, object],
) -> str | None:
    if kind == "bgm":
        start_sec = parameters.get("start_sec")
        matching = [
            segment
            for segment in segments_by_id.values()
            if getattr(segment, "start_sec", None) == start_sec
        ]
        if len(matching) != 1:
            return None
        segment = matching[0]
    else:
        segment = segments_by_id.get(str(target.get("segment_id") or ""))
        if segment is None or getattr(segment, "start_sec", None) != parameters.get(
            "start_sec"
        ):
            return None
    duration = float(getattr(segment, "end_sec")) - float(
        getattr(segment, "start_sec")
    )
    proposed_duration = parameters.get("duration_sec")
    if kind == "broll" and proposed_duration != duration:
        return None
    if kind == "bgm" and proposed_duration is not None and proposed_duration != duration:
        return None
    return str(getattr(segment, "segment_id"))


def _eligible_media_asset(
    *,
    store: object,
    project_id: str,
    asset: dict[str, object],
    candidate: DirectorCandidate,
) -> bool:
    metadata = dict(asset.get("metadata") or {})
    if candidate.media_type in {"bgm", "sfx"}:
        required = (
            ("mood", "energy", "genre", "recommended_use")
            if candidate.media_type == "bgm"
            else ("action_event", "intensity", "recommended_use")
        )
        return metadata.get("canonical_metadata_indexed") is True and all(
            metadata.get(field) not in (None, "") for field in required
        )
    analyses = store.list_media_analysis(project_id=project_id)  # type: ignore[attr-defined]
    return any(
        str(item.get("asset_id") or "") == candidate.asset_id
        and item.get("status") == "succeeded"
        and bool(item.get("result"))
        and store.can_apply_media_analysis(  # type: ignore[attr-defined]
            project_id=project_id,
            analysis_id=str(item["analysis_id"]),
        )
        for item in analyses
    )


def _supported_media_controls(
    *,
    kind: str,
    parameters: dict[str, object],
) -> dict[str, object]:
    if kind == "broll":
        return {"fit": "fit" if parameters.get("fit") == "contain" else "crop"}
    if kind == "bgm":
        return {
            "volume": parameters["volume"],
            "fade_in_sec": parameters["fade_in_sec"],
            "fade_out_sec": parameters["fade_out_sec"],
        }
    return {"volume": parameters["volume"]}


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
                    **(
                        {
                            "variant_id": source.variant_id,
                            "base_variant_revision": source.base_variant_revision,
                            "variant_kind": context.variant_kind,
                        }
                        if operation.kind == "output_variant"
                        else {}
                    ),
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
            "variant_id": source.variant_id,
            "base_variant_revision": source.base_variant_revision,
            "variant_kind": context.variant_kind,
            "operations": [
                operation.model_dump(mode="json", exclude={"operation_id"})
                for operation in source.operations
            ],
        },
        expires_at=None,
        candidates=tuple(candidates),
    )
