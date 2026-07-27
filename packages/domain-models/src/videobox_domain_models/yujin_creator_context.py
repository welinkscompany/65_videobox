"""Strict read-only DTOs for the bounded Yujin creator context."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SegmentSummary(_StrictReadModel):
    segment_id: str = Field(min_length=1, max_length=256)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    text: str = Field(max_length=256)

    @field_validator("text")
    @classmethod
    def text_fits_utf8_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 256:
            raise ValueError("segment_text_too_large")
        return value


class MediaCandidateSummary(_StrictReadModel):
    asset_id: str = Field(min_length=1, max_length=256)
    kind: Literal[
        "narration_audio",
        "raw_video",
        "broll_video",
        "image",
        "bgm",
        "sfx",
        "script_document",
        "voice_sample_audio",
        "generated_tts_audio",
    ]
    title: str = Field(max_length=128)
    duration_sec: float | None = Field(default=None, ge=0)
    tags: tuple[str, ...] = Field(max_length=8)

    @field_validator("title")
    @classmethod
    def title_fits_utf8_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 128:
            raise ValueError("media_title_too_large")
        return value

    @field_validator("tags")
    @classmethod
    def tags_fit_utf8_limit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(tag.encode("utf-8")) > 64 for tag in value):
            raise ValueError("media_tag_too_large")
        return value


class TimelineSummary(_StrictReadModel):
    duration_sec: float = Field(ge=0)
    track_count: int = Field(ge=0)
    clip_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)


class ApprovedTtsCandidateSummary(_StrictReadModel):
    candidate_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^tts_candidate_[A-Za-z0-9_-]+$",
    )
    asset_id: str = Field(min_length=1, max_length=256)
    segment_id: str = Field(min_length=1, max_length=256)
    source_text: str = Field(max_length=256)
    technical_status: Literal["accepted"]
    operator_review_status: Literal["approved"]
    asset_revision: str = Field(min_length=1, max_length=256)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("source_text")
    @classmethod
    def source_text_fits_utf8_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 256:
            raise ValueError("tts_source_text_too_large")
        return value


class SupportedControl(_StrictReadModel):
    kind: Literal[
        "broll",
        "bgm",
        "sfx",
        "caption",
        "voice",
        "overlay",
        "output_check",
    ]
    mode: Literal["recommendation_only", "read_only"]


class YujinCreatorContext(_StrictReadModel):
    schema_version: Literal["videobox.yujin-context.v1"]
    project_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    session_revision: int = Field(ge=1)
    asset_index_revision: int = Field(ge=0)
    timeline_id: str = Field(min_length=1, max_length=256)
    timeline_version: str = Field(min_length=1, max_length=128)
    selected_script_id: str | None = Field(default=None, max_length=256)
    selected_segment_id: str | None = Field(default=None, max_length=256)
    segment_summaries: tuple[SegmentSummary, ...] = Field(max_length=32)
    media_candidates: tuple[MediaCandidateSummary, ...] = Field(max_length=48)
    approved_tts_candidates: tuple[ApprovedTtsCandidateSummary, ...] = Field(
        default=(),
        max_length=32,
    )
    timeline_summary: TimelineSummary
    supported_controls: tuple[SupportedControl, ...] = Field(max_length=7)
