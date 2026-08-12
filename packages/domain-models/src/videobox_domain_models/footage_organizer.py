"""Non-destructive footage organization vocabulary.

These records describe references into an immutable source file.  They are
intentionally separate from editing-session segments: organizing footage may
be re-analysed without changing any project timeline or source bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Any, Mapping
from uuid import uuid4


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _now() -> datetime:
    return datetime.now(UTC)


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _hash(value: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    return value.lower()


def _boundary(start_sec: float, end_sec: float) -> tuple[float, float]:
    start, end = float(start_sec), float(end_sec)
    if start < 0 or end <= start:
        raise ValueError("source boundaries must satisfy 0 <= start_sec < end_sec")
    return start, end


class FootageProposalStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class FootageSource:
    source_id: str
    source_sha256: str
    filename: str = ""
    library_asset_id: str | None = None
    created_at: datetime = field(default_factory=_now)

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_sha256: str,
        filename: str = "",
        library_asset_id: str | None = None,
        created_at: datetime | None = None,
    ) -> "FootageSource":
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is required")
        return cls(source_id.strip(), _hash(source_sha256), str(filename), library_asset_id, created_at or _now())


@dataclass(frozen=True, slots=True)
class FootageSourceSegment:
    segment_id: str
    source_id: str
    source_sha256: str
    start_sec: float
    end_sec: float
    label: str = ""
    machine_fields: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)

    @property
    def source_asset_id(self) -> str:
        return self.source_id

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_sha256: str | None = None,
        start_sec: float,
        end_sec: float,
        label: str = "",
        machine_fields: Mapping[str, Any] | None = None,
        segment_id: str | None = None,
        created_at: datetime | None = None,
    ) -> "FootageSourceSegment":
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is required")
        start, end = _boundary(start_sec, end_sec)
        return cls(
            segment_id or f"fseg_{uuid4().hex}",
            source_id.strip(),
            _hash(source_sha256) if source_sha256 is not None else "",
            start,
            end,
            str(label),
            _mapping(machine_fields),
            created_at or _now(),
        )


@dataclass(frozen=True, slots=True)
class FootageProposalSegment:
    segment_id: str
    source_segment_id: str
    source_sha256: str
    start_sec: float
    end_sec: float
    machine_fields: dict[str, Any] = field(default_factory=dict)
    confirmed_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def user_confirmed_fields(self) -> dict[str, Any]:
        return self.confirmed_fields

    @classmethod
    def create(
        cls,
        *,
        source_segment_id: str,
        source_sha256: str,
        start_sec: float,
        end_sec: float,
        machine_fields: Mapping[str, Any] | None = None,
        confirmed_fields: Mapping[str, Any] | None = None,
        segment_id: str | None = None,
    ) -> "FootageProposalSegment":
        start, end = _boundary(start_sec, end_sec)
        return cls(
            segment_id or f"pseg_{uuid4().hex}",
            str(source_segment_id),
            _hash(source_sha256),
            start,
            end,
            _mapping(machine_fields),
            _mapping(confirmed_fields),
        )


@dataclass(frozen=True, slots=True)
class FootageProposal:
    proposal_id: str
    source_id: str
    source_sha256: str
    status: FootageProposalStatus
    revision: int
    segments: tuple[FootageProposalSegment, ...]
    confirmed_fields: dict[str, Any] = field(default_factory=dict)
    machine_fields: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    @property
    def source_asset_id(self) -> str:
        return self.source_id

    @property
    def user_confirmed_fields(self) -> dict[str, Any]:
        return self.confirmed_fields

    @classmethod
    def create(
        cls,
        *,
        proposal_id: str,
        source_id: str,
        source_sha256: str,
        segments: tuple[FootageProposalSegment, ...] | list[FootageProposalSegment] = (),
        status: FootageProposalStatus | str = FootageProposalStatus.DRAFT,
        revision: int = 1,
        confirmed_fields: Mapping[str, Any] | None = None,
        machine_fields: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> "FootageProposal":
        if type(revision) is not int or revision < 1:
            raise ValueError("revision must be a positive integer")
        return cls(
            proposal_id, source_id, _hash(source_sha256), FootageProposalStatus(status),
            revision, tuple(segments), _mapping(confirmed_fields), _mapping(machine_fields),
            created_at or _now(), updated_at or created_at or _now(),
        )


@dataclass(frozen=True, slots=True)
class VirtualSequenceItem:
    item_id: str
    source_segment_id: str
    item_order: int
    start_sec: float | None = None
    end_sec: float | None = None

    @classmethod
    def create(
        cls,
        *,
        source_segment_id: str,
        item_order: int,
        start_sec: float | None = None,
        end_sec: float | None = None,
        item_id: str | None = None,
    ) -> "VirtualSequenceItem":
        if type(item_order) is not int or item_order < 1:
            raise ValueError("item_order must be a positive integer")
        if (start_sec is None) != (end_sec is None):
            raise ValueError("sequence item boundaries must be provided together")
        start = end = None
        if start_sec is not None and end_sec is not None:
            start, end = _boundary(start_sec, end_sec)
        return cls(item_id or f"vitem_{uuid4().hex}", str(source_segment_id), item_order, start, end)


@dataclass(frozen=True, slots=True)
class VirtualSequence:
    sequence_id: str
    source_id: str
    source_sha256: str
    items: tuple[VirtualSequenceItem, ...]
    name: str = ""
    revision: int = 1
