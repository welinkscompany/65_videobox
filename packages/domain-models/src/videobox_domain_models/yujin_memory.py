"""Typed, non-provider Yujin memory approval workflow records."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryCategory = Literal["pacing", "caption", "audio", "tone", "workflow"]
MemoryScope = Literal["creator"]


class MemoryCandidateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STORED = "stored"
    FAILED = "failed"
    DELETED = "deleted"


class YujinMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=128)
    client_request_id: str = Field(min_length=1, max_length=128)
    source_message_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    memory_scope: MemoryScope
    category: MemoryCategory
    proposed_text: str = Field(min_length=1, max_length=280)
    status: MemoryCandidateStatus
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_frozen_contract(self) -> "YujinMemoryCandidate":
        if len(set(self.source_message_ids)) != len(self.source_message_ids):
            raise ValueError("memory_candidate_source_ids_invalid")
        timestamps = (self.created_at, self.updated_at)
        if any(
            value.tzinfo is None
            or value.utcoffset() is None
            or value.utcoffset() != timedelta(0)
            for value in timestamps
        ) or self.updated_at < self.created_at:
            raise ValueError("memory_candidate_timestamp_invalid")
        return self


__all__ = [
    "MemoryCandidateStatus",
    "MemoryCategory",
    "MemoryScope",
    "YujinMemoryCandidate",
]
