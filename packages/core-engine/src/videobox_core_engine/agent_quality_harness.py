from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal


_EXACT_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "rawmedia",
        "toolcall",
        "shell",
        "sql",
        "approval",
    }
)
_SENSITIVE_FIELD_SUFFIXES = ("token", "key", "credential", "password", "secret", "path")
_WINDOWS_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|^\\\\)")
_RELATIVE_MEDIA_PATH = re.compile(r"^(?:~[\\/]|\.\.?[\\/]|[^\s\\/]+[\\/][^\s]+\.(?:mp4|mov|mkv|webm|wav|mp3|m4a))", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FrozenEvaluationCase:
    """Immutable, provider-neutral, sanitized evaluation fixture for shadow use."""

    case_id: str
    task: str
    sanitized_input: Mapping[str, Any]
    response_schema: Mapping[str, Any]
    required_claims: frozenset[str]
    corpus_id: str
    prompt_schema_version: str
    renderer_version: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.case_id, self.task, self.corpus_id, self.prompt_schema_version, self.renderer_version)
        ):
            raise ValueError("frozen evaluation case identifiers must be non-empty strings")
        if not isinstance(self.sanitized_input, Mapping) or not isinstance(self.response_schema, Mapping):
            raise ValueError("frozen evaluation case input and response_schema must be objects")
        object.__setattr__(self, "sanitized_input", _deep_freeze(self.sanitized_input))
        object.__setattr__(self, "response_schema", _deep_freeze(self.response_schema))
        object.__setattr__(self, "required_claims", frozenset(self.required_claims))


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """One provider result captured against a frozen evaluation case."""

    provider: str
    runtime: str
    model: str
    output: Any
    latency_ms: int | float
    token_count: int


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    """Deterministic result intentionally limited to a non-authorizing state."""

    case_id: str
    task: str
    provider: str
    runtime: str
    model: str
    corpus_id: str
    prompt_schema_version: str
    renderer_version: str
    schema_valid: bool
    grounded: bool
    policy_defect: bool
    route_state: Literal["shadow_only", "needs_human_review"]
    latency_ms: int | float
    token_count: int


def evaluate_candidate(*, case: FrozenEvaluationCase, candidate: CandidateResult) -> CandidateEvaluation:
    """Evaluate captured output without contacting a provider or mutating a route."""
    schema_valid = _is_json_value(candidate.output) and _has_strict_schema_match(candidate.output, case.response_schema)
    grounded = isinstance(candidate.output, Mapping) and _contains_all_required_claims(
        candidate.output, case.required_claims
    )
    policy_defect = _contains_prohibited_data(case.sanitized_input) or _contains_prohibited_data(candidate.output)
    route_state: Literal["shadow_only", "needs_human_review"] = (
        "shadow_only" if schema_valid and grounded and not policy_defect else "needs_human_review"
    )
    return CandidateEvaluation(
        case_id=case.case_id,
        task=case.task,
        provider=candidate.provider,
        runtime=candidate.runtime,
        model=candidate.model,
        corpus_id=case.corpus_id,
        prompt_schema_version=case.prompt_schema_version,
        renderer_version=case.renderer_version,
        schema_valid=schema_valid,
        grounded=grounded,
        policy_defect=policy_defect,
        route_state=route_state,
        latency_ms=candidate.latency_ms,
        token_count=candidate.token_count,
    )


def _has_strict_schema_match(output: Any, response_schema: Mapping[str, Any]) -> bool:
    if not isinstance(output, Mapping):
        return False
    required_fields = response_schema.get("required")
    allowed_fields = response_schema.get("properties")
    if (
        not isinstance(required_fields, tuple)
        or not all(isinstance(field, str) and field for field in required_fields)
        or not isinstance(allowed_fields, Mapping)
        or response_schema.get("additionalProperties") is not False
        or not all(isinstance(field, str) and field for field in allowed_fields)
        or not set(required_fields).issubset(allowed_fields)
        or not all(isinstance(field, str) and field in allowed_fields for field in output)
    ):
        return False
    return all(field in output for field in required_fields)


def _contains_all_required_claims(output: Mapping[str, Any], required_claims: frozenset[str]) -> bool:
    values = set(_iter_text_values(output))
    return all(isinstance(claim, str) and claim in values for claim in required_claims)


def _iter_text_values(value: Any) -> Sequence[str]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(text for nested in value.values() for text in _iter_text_values(nested))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(text for nested in value for text in _iter_text_values(nested))
    return ()


def _contains_prohibited_data(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or _is_forbidden_field_name(key):
                return True
            if _contains_prohibited_data(nested):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_prohibited_data(nested) for nested in value)
    return isinstance(value, str) and _looks_like_raw_path(value)


def _is_forbidden_field_name(name: str) -> bool:
    normalized = "".join(character for character in name.lower() if character.isalnum())
    return normalized in _EXACT_FORBIDDEN_FIELD_NAMES or normalized.endswith(_SENSITIVE_FIELD_SUFFIXES)


def _looks_like_raw_path(value: str) -> bool:
    return (
        bool(_WINDOWS_PATH.match(value))
        or value.startswith("/")
        or value.startswith("\\\\")
        or value.lower().startswith("file:")
        or bool(_RELATIVE_MEDIA_PATH.match(value))
    )


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("frozen evaluation fixtures require string object keys")
        return MappingProxyType({key: _deep_freeze(nested) for key, nested in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_deep_freeze(nested) for nested in value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("frozen evaluation fixtures must contain only JSON-compatible values")


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_value(nested) for key, nested in value.items())
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and all(
        _is_json_value(nested) for nested in value
    )
