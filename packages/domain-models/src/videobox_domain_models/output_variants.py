"""Strict, linked output-variant domain models.

Variants keep a master session as their source of truth.  They can carry
render-only overrides, but cannot become a second editable story timeline.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, BaseModel, field_validator, model_validator


VariantKind = Literal["horizontal", "vertical_full", "vertical_highlight"]
VariantField = Literal[
    "crop",
    "focal",
    "caption",
    "safe_area",
    "audio",
    "story",
    "segment_order",
]
OverrideField = Literal["crop", "focal", "caption", "safe_area", "audio"]


def _as_tuple(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError("expected_list_or_tuple")


def _validate_json_values(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non_finite_override_value")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("invalid_override_key")
            _validate_json_values(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _validate_json_values(item)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class VariantOverride(_StrictFrozenModel):
    """Render-only changes allowed on a linked variant."""

    crop: dict[str, object] | None = None
    focal: dict[str, object] | None = None
    caption: dict[str, object] | None = None
    safe_area: dict[str, object] | None = None
    audio: dict[str, object] | None = None

    @model_validator(mode="after")
    def values_are_finite(self) -> VariantOverride:
        for value in self.model_dump(mode="python").values():
            _validate_json_values(value)
        return self

class VariantLock(_StrictFrozenModel):
    field: VariantField
    base_master_revision: int = Field(ge=1)


class VariantConflict(_StrictFrozenModel):
    field: VariantField
    base_master_revision: int = Field(ge=1)
    current_master_revision: int = Field(ge=1)
    reason: Literal["master_changed_while_locked", "master_changed_while_overridden"]


_SegmentIds = Annotated[
    tuple[str, ...],
    BeforeValidator(_as_tuple),
    Field(min_length=1, max_length=4096),
]


class OutputVariant(_StrictFrozenModel):
    """A revisioned view over one master editing session."""

    variant_id: str = Field(min_length=1, max_length=256)
    kind: VariantKind
    source_session_id: str = Field(min_length=1, max_length=256)
    source_session_revision: int = Field(ge=1)
    variant_revision: int = Field(ge=1)
    overrides: VariantOverride = Field(default_factory=VariantOverride)
    locks: Annotated[tuple[VariantLock, ...], BeforeValidator(_as_tuple)] = Field(
        default_factory=tuple, max_length=32
    )
    conflicts: Annotated[tuple[VariantConflict, ...], BeforeValidator(_as_tuple)] = Field(
        default_factory=tuple, max_length=64
    )
    selected_segment_ids: _SegmentIds | None = None
    master_segment_ids: _SegmentIds | None = None

    @field_validator("variant_id", "source_session_id")
    @classmethod
    def identifiers_are_trimmed(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier_required")
        return value

    @model_validator(mode="after")
    def enforce_kind_invariants(self) -> OutputVariant:
        if self.kind != "vertical_highlight" and self.selected_segment_ids is not None:
            raise ValueError("only_vertical_highlight_can_select_segments")
        for field_name, segment_ids in (
            ("selected_segment_ids", self.selected_segment_ids),
            ("master_segment_ids", self.master_segment_ids),
        ):
            if segment_ids is not None and len(set(segment_ids)) != len(segment_ids):
                raise ValueError(f"duplicate_{field_name}")
        return self
