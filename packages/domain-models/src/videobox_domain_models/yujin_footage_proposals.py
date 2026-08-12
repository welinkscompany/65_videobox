"""Strict, candidate-only DTOs for Yujin footage organization proposals."""

from __future__ import annotations

from typing import Annotated, Literal
import math
import re

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_BYTES = 256
_MAX_TEXT_BYTES = 2_048


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _bounded_text(value: str, *, label: str, limit: int) -> str:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label}_invalid_unicode") from exc
    if size > limit:
        raise ValueError(f"{label}_too_large")
    return value


def _finite(value: float, *, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label}_must_be_finite")
    return value


def _id(value: str, *, label: str) -> str:
    value = _bounded_text(value, label=label, limit=_MAX_ID_BYTES)
    if not value.strip():
        raise ValueError(f"{label}_required")
    return value


def _list_to_tuple(value: object) -> object:
    if type(value) is list:
        return tuple(value)
    return value


class YujinFootageSegment(_StrictFrozenModel):
    segment_id: str = Field(min_length=1, max_length=256)
    source_segment_id: str = Field(min_length=1, max_length=256)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    quality_flags: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(
        default=(), max_length=32
    )

    @field_validator("segment_id", "source_segment_id")
    @classmethod
    def ids_are_bounded(cls, value: str, info) -> str:
        return _id(value, label=info.field_name)

    @field_validator("start_sec", "end_sec")
    @classmethod
    def boundaries_are_finite(cls, value: float, info) -> float:
        return _finite(value, label=info.field_name)

    @field_validator("quality_flags")
    @classmethod
    def flags_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for flag in value:
            _bounded_text(flag, label="quality_flag", limit=256)
            if not flag.strip():
                raise ValueError("quality_flag_required")
        return value

    @model_validator(mode="after")
    def has_positive_bounds(self) -> "YujinFootageSegment":
        if self.end_sec <= self.start_sec:
            raise ValueError("segment_bounds_invalid")
        return self


class YujinFootageContext(_StrictFrozenModel):
    schema_version: Literal["videobox.yujin-footage-context.v1"]
    source_id: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1, max_length=256)
    proposal_revision: int = Field(ge=1)
    duration_sec: float = Field(gt=0)
    is_vertical: bool
    segments: Annotated[tuple[YujinFootageSegment, ...], BeforeValidator(_list_to_tuple)] = Field(
        min_length=1, max_length=128
    )

    @field_validator("source_id", "proposal_id")
    @classmethod
    def identity_is_bounded(cls, value: str, info) -> str:
        return _id(value, label=info.field_name)

    @field_validator("source_sha256")
    @classmethod
    def source_hash_is_canonical(cls, value: str) -> str:
        if _SHA256.fullmatch(value) is None:
            raise ValueError("source_sha256_invalid")
        return value

    @field_validator("duration_sec")
    @classmethod
    def duration_is_finite(cls, value: float) -> float:
        return _finite(value, label="duration_sec")

    @model_validator(mode="after")
    def segments_are_current_and_bounded(self) -> "YujinFootageContext":
        ids = [segment.segment_id for segment in self.segments]
        source_ids = [segment.source_segment_id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_segment_id")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate_source_segment_id")
        previous_end = 0.0
        for segment in self.segments:
            if segment.end_sec > self.duration_sec:
                raise ValueError("segment_out_of_source_range")
            if segment.start_sec < previous_end:
                raise ValueError("segments_overlap_or_out_of_order")
            previous_end = segment.end_sec
        return self


class YujinFootageRange(_StrictFrozenModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

    @field_validator("start_sec", "end_sec")
    @classmethod
    def range_is_finite(cls, value: float, info) -> float:
        return _finite(value, label=info.field_name)

    @model_validator(mode="after")
    def has_positive_bounds(self) -> "YujinFootageRange":
        if self.end_sec <= self.start_sec:
            raise ValueError("range_invalid")
        return self


class _SegmentOperation(_StrictFrozenModel):
    segment_ids: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(
        min_length=1, max_length=64
    )
    ranges: Annotated[tuple[YujinFootageRange, ...], BeforeValidator(_list_to_tuple)] = Field(
        default=(), max_length=64
    )

    @field_validator("segment_ids")
    @classmethod
    def segment_ids_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for segment_id in value:
            _id(segment_id, label="segment_id")
        return value


class SplitBySceneOperation(_SegmentOperation):
    intent: Literal["split_by_scene"]


class SelectProcessOperation(_SegmentOperation):
    intent: Literal["select_process"]
    process_label: str = Field(min_length=1, max_length=256)

    @field_validator("process_label")
    @classmethod
    def process_label_is_bounded(cls, value: str) -> str:
        return _bounded_text(value, label="process_label", limit=_MAX_TEXT_BYTES)


class ExcludeQualityOperation(_SegmentOperation):
    intent: Literal["exclude_quality"]
    quality_evidence: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(
        default=(), max_length=32
    )

    @field_validator("quality_evidence")
    @classmethod
    def quality_evidence_is_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            _bounded_text(item, label="quality_evidence", limit=256)
            if not item.strip():
                raise ValueError("quality_evidence_required")
        return value


class CombineSimilarOperation(_SegmentOperation):
    intent: Literal["combine_similar"]


class SelectVerticalOperation(_SegmentOperation):
    intent: Literal["select_vertical"]


class TargetDurationOperation(_StrictFrozenModel):
    intent: Literal["target_duration"]
    target_duration_sec: float = Field(gt=0)

    @field_validator("target_duration_sec")
    @classmethod
    def target_duration_is_finite(cls, value: float) -> float:
        return _finite(value, label="target_duration_sec")


YujinFootageOperation = Annotated[
    SplitBySceneOperation
    | SelectProcessOperation
    | ExcludeQualityOperation
    | CombineSimilarOperation
    | SelectVerticalOperation
    | TargetDurationOperation,
    Field(discriminator="intent"),
]


class YujinFootageProposalInput(_StrictFrozenModel):
    source_id: str = Field(min_length=1, max_length=256)
    proposal_id: str = Field(min_length=1, max_length=256)
    base_revision: int = Field(ge=1)
    operations: Annotated[tuple[YujinFootageOperation, ...], BeforeValidator(_list_to_tuple)] = Field(
        min_length=1, max_length=16
    )

    @field_validator("source_id", "proposal_id")
    @classmethod
    def proposal_ids_are_bounded(cls, value: str, info) -> str:
        return _id(value, label=info.field_name)


class YujinFootageResponse(_StrictFrozenModel):
    schema_version: Literal["videobox.yujin-footage-response.v1"]
    reply_text: str = Field(min_length=1, max_length=8192)
    proposal: YujinFootageProposalInput

    @field_validator("reply_text")
    @classmethod
    def reply_text_is_bounded(cls, value: str) -> str:
        return _bounded_text(value, label="reply_text", limit=16_384)


class YujinFootageCandidateProposal(_StrictFrozenModel):
    source_id: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_id: str = Field(min_length=1, max_length=256)
    base_revision: int = Field(ge=1)
    requires_approval: Literal[True]
    operations: Annotated[tuple[YujinFootageOperation, ...], BeforeValidator(_list_to_tuple)] = Field(
        min_length=1, max_length=16
    )


__all__ = [
    "CombineSimilarOperation",
    "ExcludeQualityOperation",
    "SelectProcessOperation",
    "SelectVerticalOperation",
    "SplitBySceneOperation",
    "TargetDurationOperation",
    "YujinFootageCandidateProposal",
    "YujinFootageContext",
    "YujinFootageOperation",
    "YujinFootageProposalInput",
    "YujinFootageRange",
    "YujinFootageResponse",
    "YujinFootageSegment",
]
