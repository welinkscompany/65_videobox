"""Pure, fail-closed adapter for Yujin footage proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
import unicodedata
from typing import Literal

from pydantic import ValidationError

from videobox_domain_models.yujin_footage_proposals import (
    CombineSimilarOperation,
    ExcludeQualityOperation,
    SelectProcessOperation,
    SelectVerticalOperation,
    SplitBySceneOperation,
    TargetDurationOperation,
    YujinFootageCandidateProposal,
    YujinFootageContext,
    YujinFootageOperation,
    YujinFootageProposalInput,
    YujinFootageResponse,
)


_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_OBJECT_NODES = 256
_MAX_OBJECT_DEPTH = 12
# 키워드 경계는 숫자·밑줄도 단어 문자로 취급한다.  세그먼트/제안 id가
# uuid4·sha256 hex라서 "db" 같은 철자가 hex 안에 약 5% 확률로 나타나는데,
# `(?<![A-Za-z])`만 쓰면 `pseg_4db2...` 같은 시스템 식별자를 운영 명령으로
# 오인해 유효한 요청을 거부한다 (2026-08-19 전체 pytest 간헐 실패의 원인).
_UNSAFE_TEXT = re.compile(
    r"(?ix)"
    r"(?:"
    r"file[ _-]*(?:system|path)|filesystem|파일[ _-]*(?:시스템|경로)|"
    r"(?:file|directory)\s+path|"
    r"(?:[a-z]:[\\/]|\\\\|\.\.[\\/]|\.[\\/]|/(?:[^/\s]+/)*[^/\s]+)|"
    r"(?<![A-Za-z0-9_])(?:shell|powershell|bash|terminal|cmd|command[ _-]*line|command|"
    r"명령줄|명령어|renderer|렌더러|ffmpeg|database|데이터베이스|sql|db|셸|쉘|"
    r"http|https|web[ _-]*request|network[ _-]*request|웹[ _-]*요청|네트워크|"
    r"credential|자격증명|token|api[ _-]*key|secret|password|비밀번호|oauth)(?![A-Za-z0-9_])|"
    r"\b[a-z][a-z0-9+.-]*://"
    r")"
)


@dataclass(frozen=True, slots=True)
class YujinFootageResult:
    status: Literal["candidate_only", "clarification", "rejected"]
    proposal: YujinFootageCandidateProposal | None = None
    reply_text: str | None = None
    clarification: str | None = None
    rejection_reason: str | None = None


class _DuplicateKey(ValueError):
    pass


def interpret_yujin_footage_request(
    payload: str | Mapping[str, object],
    context: YujinFootageContext,
) -> YujinFootageResult:
    """Interpret one bounded response without executing or persisting anything."""

    if not isinstance(context, YujinFootageContext):
        return _rejected("invalid_context")

    raw = _decode_payload(payload)
    if raw is None:
        return _rejected("invalid_payload")
    if _contains_unsafe_instruction(raw):
        return _rejected("unsafe_instruction")

    if "proposal" not in raw or raw.get("proposal") is None:
        return _clarification(raw)

    try:
        response = YujinFootageResponse.model_validate(raw)
    except (TypeError, ValidationError):
        return _rejected("invalid_response")

    proposal = response.proposal
    reason = _validate_against_context(proposal, context)
    if reason is not None:
        return _rejected(reason)

    candidate = YujinFootageCandidateProposal(
        source_id=context.source_id,
        source_sha256=context.source_sha256,
        proposal_id=context.proposal_id,
        base_revision=context.proposal_revision,
        requires_approval=True,
        operations=proposal.operations,
    )
    return YujinFootageResult(
        status="candidate_only",
        proposal=candidate,
        reply_text=response.reply_text,
    )


def _decode_payload(payload: str | Mapping[str, object]) -> dict[str, object] | None:
    try:
        if isinstance(payload, str):
            if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
                return None
            value = json.loads(
                payload,
                object_pairs_hook=_reject_duplicate_keys,
            )
        elif isinstance(payload, Mapping):
            value = dict(payload)
        else:
            return None
        if not isinstance(value, dict) or not _bounded_object(value):
            return None
        return value
    except (UnicodeEncodeError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
        return None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate_json_key")
        result[key] = value
    return result


def _bounded_object(
    value: object,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
    byte_budget: list[int] | None = None,
    node_count: list[int] | None = None,
) -> bool:
    if depth > _MAX_OBJECT_DEPTH:
        return False
    if seen is None:
        seen = set()
    if byte_budget is None:
        byte_budget = [0]
    if node_count is None:
        node_count = [0]
    node_count[0] += 1
    if node_count[0] > _MAX_OBJECT_NODES:
        return False
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            return False
        seen.add(identity)
        if len(value) > _MAX_OBJECT_NODES:
            seen.remove(identity)
            return False
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    return False
                if not _bounded_object(
                    key,
                    depth=depth,
                    seen=seen,
                    byte_budget=byte_budget,
                    node_count=node_count,
                ) or not _bounded_object(
                    item,
                    depth=depth + 1,
                    seen=seen,
                    byte_budget=byte_budget,
                    node_count=node_count,
                ):
                    return False
            return True
        finally:
            seen.remove(identity)
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in seen:
            return False
        seen.add(identity)
        if len(value) > _MAX_OBJECT_NODES:
            seen.remove(identity)
            return False
        try:
            return all(
                _bounded_object(
                    item,
                    depth=depth + 1,
                    seen=seen,
                    byte_budget=byte_budget,
                    node_count=node_count,
                )
                for item in value
            )
        finally:
            seen.remove(identity)
    if isinstance(value, str):
        try:
            byte_budget[0] += len(value.encode("utf-8"))
            return byte_budget[0] <= _MAX_PAYLOAD_BYTES
        except UnicodeEncodeError:
            return False
    return value is None or isinstance(value, (bool, int, float))


def _contains_unsafe_instruction(value: object) -> bool:
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value)
        normalized = "".join(
            character
            for character in normalized
            if unicodedata.category(character) not in {"Cc", "Cf"}
        )
        return _UNSAFE_TEXT.search(normalized) is not None
    if isinstance(value, Mapping):
        return any(
            _contains_unsafe_instruction(key) or _contains_unsafe_instruction(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_unsafe_instruction(item) for item in value)
    return False


def is_unsafe_yujin_footage_instruction(value: object) -> bool:
    """Expose the same fail-closed instruction scan for the API request boundary."""

    return _contains_unsafe_instruction(value)


def _clarification(raw: dict[str, object]) -> YujinFootageResult:
    allowed = {"schema_version", "reply_text", "proposal"}
    if set(raw) - allowed:
        return _rejected("invalid_response")
    schema_version = raw.get("schema_version")
    if schema_version is not None and schema_version != "videobox.yujin-footage-response.v1":
        return _rejected("invalid_response")
    reply_text = raw.get("reply_text")
    if not isinstance(reply_text, str) or not reply_text.strip():
        return _rejected("invalid_response")
    try:
        if len(reply_text) > 8_192 or len(reply_text.encode("utf-8")) > 16_384:
            return _rejected("invalid_response")
    except UnicodeEncodeError:
        return _rejected("invalid_response")
    return YujinFootageResult(
        status="clarification",
        clarification="원하는 장면, 작업, 품질 기준 또는 목표 길이를 구체적으로 알려주세요.",
    )


def _validate_against_context(
    proposal: YujinFootageProposalInput,
    context: YujinFootageContext,
) -> str | None:
    if proposal.source_id != context.source_id:
        return "source_not_current"
    if proposal.proposal_id != context.proposal_id:
        return "proposal_not_current"
    if proposal.base_revision != context.proposal_revision:
        return "proposal_revision_not_current"

    segments = {segment.segment_id: segment for segment in context.segments}
    ordered_ids = [segment.segment_id for segment in context.segments]
    for operation in proposal.operations:
        if isinstance(operation, _SEGMENT_OPERATIONS):
            if len(operation.segment_ids) != len(set(operation.segment_ids)):
                return "duplicate_segment_id"
            selected = []
            for segment_id in operation.segment_ids:
                segment = segments.get(segment_id)
                if segment is None:
                    return "segment_not_current"
                selected.append(segment)
            if operation.ranges and any(
                not any(
                    item.start_sec >= segment.start_sec
                    and item.end_sec <= segment.end_sec
                    for segment in selected
                )
                for item in operation.ranges
            ):
                return "range_out_of_segment"
            if isinstance(operation, CombineSimilarOperation):
                positions = [ordered_ids.index(item) for item in operation.segment_ids]
                if positions != list(range(positions[0], positions[0] + len(positions))):
                    return "segments_not_adjacent"
            if isinstance(operation, SelectVerticalOperation) and not context.is_vertical:
                return "source_not_vertical"
            if isinstance(operation, ExcludeQualityOperation):
                if not operation.quality_evidence:
                    return "quality_evidence_required"
                verified = {
                    flag
                    for segment in selected
                    for flag in segment.quality_flags
                }
                if not set(operation.quality_evidence).issubset(verified):
                    return "quality_evidence_unverified"
        else:
            if operation.target_duration_sec > context.duration_sec:
                return "target_duration_out_of_range"
    return None


_SEGMENT_OPERATIONS = (
    SplitBySceneOperation,
    SelectProcessOperation,
    ExcludeQualityOperation,
    CombineSimilarOperation,
    SelectVerticalOperation,
)


def _rejected(reason: str) -> YujinFootageResult:
    return YujinFootageResult(status="rejected", rejection_reason=reason)


def preview_ranges_for_yujin_candidate(
    candidate: YujinFootageCandidateProposal,
    context: YujinFootageContext,
) -> tuple[tuple[float, float], ...]:
    """Project a candidate to read-only source ranges for the existing preview path."""

    segments = {segment.segment_id: segment for segment in context.segments}
    ranges: list[tuple[float, float]] = []
    for operation in candidate.operations:
        if isinstance(operation, TargetDurationOperation):
            remaining = operation.target_duration_sec
            for segment in context.segments:
                if remaining <= 0:
                    break
                end = min(segment.end_sec, segment.start_sec + remaining)
                if end > segment.start_sec:
                    ranges.append((segment.start_sec, end))
                    remaining -= end - segment.start_sec
            continue
        if isinstance(operation, ExcludeQualityOperation):
            excluded = set(operation.segment_ids)
            ranges.extend(
                (segment.start_sec, segment.end_sec)
                for segment in context.segments
                if segment.segment_id not in excluded
            )
            continue
        selected = [segments[segment_id] for segment_id in operation.segment_ids]
        if operation.ranges:
            ranges.extend((item.start_sec, item.end_sec) for item in operation.ranges)
        else:
            ranges.extend((segment.start_sec, segment.end_sec) for segment in selected)

    if not ranges:
        ranges = [(segment.start_sec, segment.end_sec) for segment in context.segments]
    return _merge_preview_ranges(ranges)


def _merge_preview_ranges(ranges: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    ordered = sorted(set(ranges))
    merged: list[list[float]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + 1e-6:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return tuple((start, end) for start, end in merged)


__all__ = [
    "YujinFootageResult",
    "interpret_yujin_footage_request",
    "is_unsafe_yujin_footage_instruction",
    "preview_ranges_for_yujin_candidate",
]
