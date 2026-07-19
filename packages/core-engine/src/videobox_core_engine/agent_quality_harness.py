from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import JSONDecodeError, dumps, loads
from math import isfinite, sqrt
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from videobox_core_engine.evaluation_fixture_versions import (
    KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256,
)


_EXACT_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "rawmedia",
        "toolcall",
        "shell",
        "sql",
        "approval",
        "approvalstate",
    }
)
_SENSITIVE_FIELD_SUFFIXES = ("token", "key", "credential", "password", "secret", "path")
_WINDOWS_PATH = re.compile(r"(?:^[A-Za-z]:[\\/]|^\\\\)")
_RELATIVE_MEDIA_PATH = re.compile(r"^(?:~[\\/]|\.\.?[\\/]|[^\s\\/]+[\\/][^\s]+\.(?:mp4|mov|mkv|webm|wav|mp3|m4a))", re.IGNORECASE)
CHECKED_IN_KOREAN_EVALUATION_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "korean_shadow_evaluation_v1.json"
)


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
        if _contains_prohibited_data(self.sanitized_input) or _contains_prohibited_data(self.response_schema):
            raise ValueError("frozen evaluation case contains prohibited sanitized input or response schema data")
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", _deep_freeze(self.output))


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


@dataclass(frozen=True, slots=True)
class FrozenKoreanEvaluationCorpus:
    """An immutable, identity-pinned corpus used for provider comparison only."""

    corpus_id: str
    prompt_schema_version: str
    renderer_version: str
    cases: tuple[FrozenEvaluationCase, ...]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.corpus_id, self.prompt_schema_version, self.renderer_version)
        ):
            raise ValueError("frozen corpus identifiers must be non-empty strings")
        if not self.cases:
            raise ValueError("frozen corpus requires at least one case")
        if not all(isinstance(case, FrozenEvaluationCase) for case in self.cases):
            raise ValueError("frozen corpus cases must be FrozenEvaluationCase values")
        object.__setattr__(self, "cases", tuple(self.cases))
        if any(
            _contains_prohibited_data(case.sanitized_input) or _contains_prohibited_data(case.response_schema)
            for case in self.cases
        ):
            raise ValueError("frozen corpus contains prohibited sanitized input or response schema data")

        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("frozen corpus case ids must be unique")
        if any(
            case.corpus_id != self.corpus_id
            or case.prompt_schema_version != self.prompt_schema_version
            or case.renderer_version != self.renderer_version
            for case in self.cases
        ):
            raise ValueError("frozen corpus case identity must exactly match corpus identity")


@dataclass(frozen=True, slots=True)
class EvaluationMeasurement:
    """One human-scored, offline capture re-evaluated against its frozen case."""

    case: FrozenEvaluationCase
    candidate: CandidateResult
    human_score: float
    correction_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.case, FrozenEvaluationCase):
            raise ValueError("measurement requires a FrozenEvaluationCase")
        if not isinstance(self.candidate, CandidateResult):
            raise ValueError("measurement requires a captured CandidateResult")
        if isinstance(self.human_score, bool) or not isinstance(self.human_score, (int, float)):
            raise ValueError("human_score must be a finite number from 0 through 5")
        if not isfinite(float(self.human_score)) or not 0 <= float(self.human_score) <= 5:
            raise ValueError("human_score must be a finite number from 0 through 5")
        if isinstance(self.correction_seconds, bool) or not isinstance(self.correction_seconds, (int, float)):
            raise ValueError("correction_seconds must be a positive finite number")
        if not isfinite(float(self.correction_seconds)) or float(self.correction_seconds) <= 0:
            raise ValueError("correction_seconds must be a positive finite number")
        object.__setattr__(self, "human_score", float(self.human_score))
        object.__setattr__(self, "correction_seconds", float(self.correction_seconds))


@dataclass(frozen=True, slots=True)
class QualificationThresholds:
    """Explicit, non-authorizing quality thresholds from the VideoBox plan."""

    minimum_sample_size: int = 20
    minimum_schema_valid_rate: float = 0.98
    minimum_grounded_claim_rate: float = 0.95
    maximum_critical_policy_defect_count: int = 0
    minimum_human_score_delta: float = -0.5
    maximum_correction_time_delta_ratio: float = 0.10

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_sample_size, int) or isinstance(self.minimum_sample_size, bool) or self.minimum_sample_size < 1:
            raise ValueError("minimum_sample_size must be a positive integer")
        if not 0 <= self.minimum_schema_valid_rate <= 1:
            raise ValueError("minimum_schema_valid_rate must be between 0 and 1")
        if not 0 <= self.minimum_grounded_claim_rate <= 1:
            raise ValueError("minimum_grounded_claim_rate must be between 0 and 1")
        if (
            not isinstance(self.maximum_critical_policy_defect_count, int)
            or isinstance(self.maximum_critical_policy_defect_count, bool)
            or self.maximum_critical_policy_defect_count < 0
        ):
            raise ValueError("maximum_critical_policy_defect_count must be a non-negative integer")
        if not isfinite(self.minimum_human_score_delta):
            raise ValueError("minimum_human_score_delta must be finite")
        if not isfinite(self.maximum_correction_time_delta_ratio):
            raise ValueError("maximum_correction_time_delta_ratio must be finite")


@dataclass(frozen=True, slots=True)
class QualificationReport:
    """A deterministic report. It never changes an execution route or provider state."""

    corpus_id: str
    prompt_schema_version: str
    renderer_version: str
    baseline_provider: str
    candidate_provider: str
    sample_size: int
    schema_valid_rate: float
    grounded_claim_rate: float
    critical_policy_defect_count: int
    human_score_delta: float
    correction_time_delta_ratio: float
    schema_valid_ci_95: tuple[float, float]
    grounded_claim_rate_ci_95: tuple[float, float]
    human_score_delta_ci_95: tuple[float, float]
    correction_time_delta_ratio_ci_95: tuple[float, float]
    thresholds_passed: bool
    route_state: Literal["needs_human_review"]

    @property
    def grounded_ci_95(self) -> tuple[float, float]:
        """Short alias retained for consumers that do not use the full metric name."""
        return self.grounded_claim_rate_ci_95


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


def build_qualification_report(
    *,
    corpus: FrozenKoreanEvaluationCorpus,
    measurements: Sequence[EvaluationMeasurement],
    baseline_provider: str,
    candidate_provider: str,
    thresholds: QualificationThresholds | None = None,
) -> QualificationReport:
    """Compare two captured providers against one frozen corpus without side effects.

    The input must have precisely one baseline and one candidate measurement for
    every corpus case.  Rejecting malformed batches is intentional: accepting a
    partial or mixed-identity benchmark could make a weaker provider look safe.
    """
    if not isinstance(corpus, FrozenKoreanEvaluationCorpus):
        raise ValueError("qualification report requires a frozen Korean evaluation corpus")
    if not _is_provider_name(baseline_provider) or not _is_provider_name(candidate_provider):
        raise ValueError("baseline_provider and candidate_provider must be non-empty strings")
    if baseline_provider == candidate_provider:
        raise ValueError("baseline_provider and candidate_provider must differ")
    if thresholds is None:
        thresholds = QualificationThresholds()
    if not isinstance(thresholds, QualificationThresholds):
        raise ValueError("thresholds must be QualificationThresholds")
    if any(
        _contains_prohibited_data(case.sanitized_input) or _contains_prohibited_data(case.response_schema)
        for case in corpus.cases
    ):
        raise ValueError("qualification corpus contains prohibited sanitized input or response schema data")

    paired = _validate_and_pair_measurements(
        corpus=corpus,
        measurements=measurements,
        baseline_provider=baseline_provider,
        candidate_provider=candidate_provider,
    )
    candidate_measurements = tuple((candidate_measurement, candidate_evaluation) for _, _, candidate_measurement, candidate_evaluation in paired)
    baseline_measurements = tuple((baseline_measurement, baseline_evaluation) for baseline_measurement, baseline_evaluation, _, _ in paired)
    sample_size = len(candidate_measurements)

    schema_valid_count = sum(evaluation.schema_valid for _, evaluation in candidate_measurements)
    grounded_count = sum(evaluation.grounded for _, evaluation in candidate_measurements)
    policy_defect_count = sum(evaluation.policy_defect for _, evaluation in candidate_measurements)
    human_score_deltas = tuple(
        candidate_measurement.human_score - baseline_measurement.human_score
        for (baseline_measurement, _), (candidate_measurement, _) in zip(
            baseline_measurements, candidate_measurements, strict=True
        )
    )
    correction_time_deltas = tuple(
        (candidate_measurement.correction_seconds - baseline_measurement.correction_seconds)
        / baseline_measurement.correction_seconds
        for (baseline_measurement, _), (candidate_measurement, _) in zip(
            baseline_measurements, candidate_measurements, strict=True
        )
    )
    schema_valid_rate = schema_valid_count / sample_size
    grounded_claim_rate = grounded_count / sample_size
    human_score_delta = _mean(human_score_deltas)
    correction_time_delta_ratio = _mean(correction_time_deltas)
    # §23.3A records 95% CIs as evidence; its qualification thresholds are point metrics.
    thresholds_passed = (
        sample_size >= thresholds.minimum_sample_size
        and schema_valid_rate >= thresholds.minimum_schema_valid_rate
        and grounded_claim_rate >= thresholds.minimum_grounded_claim_rate
        and policy_defect_count <= thresholds.maximum_critical_policy_defect_count
        and human_score_delta >= thresholds.minimum_human_score_delta
        and correction_time_delta_ratio <= thresholds.maximum_correction_time_delta_ratio
    )
    return QualificationReport(
        corpus_id=corpus.corpus_id,
        prompt_schema_version=corpus.prompt_schema_version,
        renderer_version=corpus.renderer_version,
        baseline_provider=baseline_provider,
        candidate_provider=candidate_provider,
        sample_size=sample_size,
        schema_valid_rate=schema_valid_rate,
        grounded_claim_rate=grounded_claim_rate,
        critical_policy_defect_count=policy_defect_count,
        human_score_delta=human_score_delta,
        correction_time_delta_ratio=correction_time_delta_ratio,
        schema_valid_ci_95=_wilson_interval(schema_valid_count, sample_size),
        grounded_claim_rate_ci_95=_wilson_interval(grounded_count, sample_size),
        human_score_delta_ci_95=_paired_mean_ci_95(human_score_deltas),
        correction_time_delta_ratio_ci_95=_paired_mean_ci_95(correction_time_deltas),
        thresholds_passed=thresholds_passed,
        route_state="needs_human_review",
    )


def load_checked_in_korean_evaluation_corpus(
    fixture_path: Path = CHECKED_IN_KOREAN_EVALUATION_FIXTURE_PATH,
) -> FrozenKoreanEvaluationCorpus:
    """Load the small checked-in shadow corpus after a canonical-digest check.

    This corpus is an offline regression fixture, not qualification or activation
    evidence.  Its fixed three cases are deliberately smaller than the minimum
    qualification sample size.
    """
    if not isinstance(fixture_path, Path):
        raise ValueError("fixture_path must be a Path")
    try:
        raw = loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise ValueError("checked-in Korean evaluation fixture cannot be read") from error
    if not isinstance(raw, Mapping) or set(raw) != {"canonical_sha256", "corpus"}:
        raise ValueError("checked-in Korean evaluation fixture has an invalid envelope")
    declared_digest = raw["canonical_sha256"]
    payload = raw["corpus"]
    if not isinstance(declared_digest, str) or re.fullmatch(r"[0-9a-f]{64}", declared_digest) is None:
        raise ValueError("checked-in Korean evaluation fixture has an invalid digest")
    if not isinstance(payload, Mapping):
        raise ValueError("checked-in Korean evaluation fixture corpus must be an object")
    canonical_bytes = dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    actual_digest = sha256(canonical_bytes).hexdigest()
    if declared_digest != KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256:
        raise ValueError("checked-in Korean evaluation fixture declared digest is not the pinned version digest")
    if actual_digest != declared_digest or actual_digest != KOREAN_SHADOW_EVALUATION_V1_CANONICAL_SHA256:
        raise ValueError("checked-in Korean evaluation fixture digest does not match payload")
    return _corpus_from_checked_in_payload(payload)


def _corpus_from_checked_in_payload(payload: Mapping[str, Any]) -> FrozenKoreanEvaluationCorpus:
    if set(payload) != {"corpus_id", "prompt_schema_version", "renderer_version", "cases"}:
        raise ValueError("checked-in Korean evaluation fixture corpus shape is invalid")
    cases_value = payload["cases"]
    if not isinstance(cases_value, list):
        raise ValueError("checked-in Korean evaluation fixture cases must be an array")
    cases: list[FrozenEvaluationCase] = []
    for raw_case in cases_value:
        if not isinstance(raw_case, Mapping) or set(raw_case) != {
            "case_id",
            "task",
            "sanitized_input",
            "response_schema",
            "required_claims",
        }:
            raise ValueError("checked-in Korean evaluation fixture case shape is invalid")
        required_claims = raw_case["required_claims"]
        if not isinstance(required_claims, list) or not all(isinstance(claim, str) for claim in required_claims):
            raise ValueError("checked-in Korean evaluation fixture required_claims must be strings")
        cases.append(
            FrozenEvaluationCase(
                case_id=raw_case["case_id"],
                task=raw_case["task"],
                sanitized_input=raw_case["sanitized_input"],
                response_schema=raw_case["response_schema"],
                required_claims=frozenset(required_claims),
                corpus_id=payload["corpus_id"],
                prompt_schema_version=payload["prompt_schema_version"],
                renderer_version=payload["renderer_version"],
            )
        )
    return FrozenKoreanEvaluationCorpus(
        corpus_id=payload["corpus_id"],
        prompt_schema_version=payload["prompt_schema_version"],
        renderer_version=payload["renderer_version"],
        cases=tuple(cases),
    )


def _validate_and_pair_measurements(
    *,
    corpus: FrozenKoreanEvaluationCorpus,
    measurements: Sequence[EvaluationMeasurement],
    baseline_provider: str,
    candidate_provider: str,
) -> tuple[tuple[EvaluationMeasurement, CandidateEvaluation, EvaluationMeasurement, CandidateEvaluation], ...]:
    case_by_id = {case.case_id: case for case in corpus.cases}
    expected_providers = frozenset((baseline_provider, candidate_provider))
    by_case_and_provider: dict[tuple[str, str], tuple[EvaluationMeasurement, CandidateEvaluation]] = {}
    provider_runtime_models: dict[str, tuple[str, str]] = {}
    for measurement in measurements:
        if not isinstance(measurement, EvaluationMeasurement):
            raise ValueError("qualification measurements must be EvaluationMeasurement values")
        case = case_by_id.get(measurement.case.case_id)
        if case is None:
            raise ValueError("measurement case is not part of the frozen corpus")
        if measurement.case is not case:
            raise ValueError("measurement case identity does not exactly match its frozen corpus case")
        evaluation = evaluate_candidate(case=case, candidate=measurement.candidate)
        if evaluation.provider not in expected_providers:
            raise ValueError("qualification measurements may contain only the named baseline and candidate providers")
        provider_identity = (evaluation.runtime, evaluation.model)
        previous_identity = provider_runtime_models.setdefault(evaluation.provider, provider_identity)
        if previous_identity != provider_identity:
            raise ValueError("each named provider must use one runtime and model identity across the corpus")
        key = (evaluation.case_id, evaluation.provider)
        if key in by_case_and_provider:
            raise ValueError("qualification measurements must contain exactly one measurement per case and provider")
        by_case_and_provider[key] = (measurement, evaluation)

    expected_measurement_count = len(corpus.cases) * 2
    if len(by_case_and_provider) != expected_measurement_count:
        raise ValueError("qualification measurements are missing a named baseline or candidate case")
    if set(provider_runtime_models) != expected_providers:
        raise ValueError("qualification measurements are missing a named provider identity")
    return tuple(
        (
            *by_case_and_provider[(case.case_id, baseline_provider)],
            *by_case_and_provider[(case.case_id, candidate_provider)],
        )
        for case in corpus.cases
    )


def _is_provider_name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Two-sided 95% Wilson interval using the standard normal 1.96 constant."""
    if total < 1:
        raise ValueError("confidence interval requires at least one measurement")
    z = 1.96
    proportion = successes / total
    denominator = 1 + (z * z) / total
    center = (proportion + (z * z) / (2 * total)) / denominator
    margin = (z / denominator) * sqrt((proportion * (1 - proportion) + (z * z) / (4 * total)) / total)
    return (max(0.0, center - margin), min(1.0, center + margin))


def _paired_mean_ci_95(values: Sequence[float]) -> tuple[float, float]:
    """Normal-approximation paired 95% interval, deterministic without SciPy."""
    mean = _mean(values)
    if len(values) == 1:
        return (mean, mean)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 1.96 * sqrt(variance / len(values))
    return (mean - margin, mean + margin)


def _has_strict_schema_match(output: Any, response_schema: Mapping[str, Any]) -> bool:
    return _matches_schema(output, response_schema)


def _matches_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    """Validate the deliberately small, fail-closed response-schema subset."""
    if not isinstance(schema, Mapping):
        return False
    if not schema:
        return _is_json_value(value)

    schema_keys = set(schema)
    schema_type = schema.get("type")
    # Existing frozen cases use this strict object shorthand; keep it equivalent
    # to the explicit object form while rejecting every other omitted-type shape.
    if schema_type is None and schema_keys == {"properties", "required", "additionalProperties"}:
        return _matches_object_schema(value, schema, allow_implicit_type=True)
    if not isinstance(schema_type, str):
        return False
    if schema_type == "object":
        return schema_keys == {"type", "properties", "required", "additionalProperties"} and _matches_object_schema(
            value, schema, allow_implicit_type=False
        )
    if schema_type == "array":
        if schema_keys != {"type", "items"} or not isinstance(schema.get("items"), Mapping):
            return False
        return (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
            and all(_matches_schema(item, schema["items"]) for item in value)
        )
    if schema_keys != {"type"}:
        return False
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return False


def _matches_object_schema(value: Any, schema: Mapping[str, Any], *, allow_implicit_type: bool) -> bool:
    if not isinstance(value, Mapping):
        return False
    required_fields = schema.get("required")
    allowed_fields = schema.get("properties")
    if (
        not isinstance(required_fields, Sequence)
        or isinstance(required_fields, (str, bytes, bytearray))
        or not all(isinstance(field, str) and field for field in required_fields)
        or len(set(required_fields)) != len(required_fields)
        or not isinstance(allowed_fields, Mapping)
        or schema.get("additionalProperties") is not False
        or not all(isinstance(field, str) and field and isinstance(field_schema, Mapping) for field, field_schema in allowed_fields.items())
        or not set(required_fields).issubset(allowed_fields)
        or not all(isinstance(field, str) and field in allowed_fields for field in value)
    ):
        return False
    return all(field in value for field in required_fields) and all(
        _matches_schema(field_value, allowed_fields[field]) for field, field_value in value.items()
    )


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
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_value(nested) for key, nested in value.items())
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and all(
        _is_json_value(nested) for nested in value
    )
