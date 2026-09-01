"""Strict, candidate-only editing proposals returned by Yujin."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator


def _list_to_tuple(value: object) -> object:
    return tuple(value) if type(value) is list else value


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _SegmentOperation(_StrictFrozenModel):
    segment_id: str = Field(min_length=1, max_length=256)


class SetSceneSpeedOperation(_SegmentOperation):
    intent: Literal["set_scene_speed"]
    rate: Literal[1, 1.5, 2]


class SetSegmentBoundsOperation(_SegmentOperation):
    intent: Literal["set_segment_bounds"]
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)

    @field_validator("start_sec", "end_sec")
    @classmethod
    def bounds_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("editing_bound_must_be_finite")
        return value

    @model_validator(mode="after")
    def has_positive_duration(self) -> "SetSegmentBoundsOperation":
        if self.end_sec <= self.start_sec:
            raise ValueError("editing_bounds_invalid")
        return self


class SetCutActionOperation(_SegmentOperation):
    intent: Literal["set_cut_action"]
    action: Literal["exclude", "restore"]


class ReorderSegmentsOperation(_StrictFrozenModel):
    intent: Literal["reorder_segments"]
    segment_ids: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(min_length=1, max_length=256)


class SetCaptionTextOperation(_SegmentOperation):
    intent: Literal["set_caption_text"]
    text: str = Field(min_length=1, max_length=4096)


class SetSceneLookOperation(_SegmentOperation):
    """장면의 색감을 고른다.

    `look`이 `Literal`이 아니라 `str`인 이유: 고를 수 있는 색감 목록은
    `core_engine.filters.FILTER_CATALOG` 하나가 원본이고, 여기 옮겨 적으면
    **두 벌이 갈라진다.** 목록 대조는 어차피 모든 경로가 지나는 검증기
    (`yujin_editing_proposal_adapter`)에서 한다 -- 그쪽은 core-engine이라
    원본 표를 그대로 읽을 수 있다.
    """

    intent: Literal["set_scene_look"]
    look: str = Field(min_length=1, max_length=64)


class ApplyMediaOperation(_SegmentOperation):
    intent: Literal["apply_media"]
    media_type: Literal["broll", "bgm", "sfx"]
    asset_id: str = Field(min_length=1, max_length=256)


class RemoveMediaOperation(_SegmentOperation):
    intent: Literal["remove_media"]
    media_type: Literal["broll", "bgm", "sfx"]


YujinEditingOperation = Annotated[
    SetSceneSpeedOperation
    | SetSegmentBoundsOperation
    | SetCutActionOperation
    | ReorderSegmentsOperation
    | SetCaptionTextOperation
    | SetSceneLookOperation
    | ApplyMediaOperation
    | RemoveMediaOperation,
    Field(discriminator="intent"),
]


class YujinEditingProposal(_StrictFrozenModel):
    proposal_id: str = Field(min_length=1, max_length=256)
    base_session_revision: int = Field(ge=1)
    operations: Annotated[tuple[YujinEditingOperation, ...], BeforeValidator(_list_to_tuple)] = Field(
        min_length=1, max_length=16
    )


class YujinEditingResponse(_StrictFrozenModel):
    schema_version: Literal["videobox.yujin-editing-response.v1"]
    reply_text: str = Field(min_length=1, max_length=8192)
    proposal: YujinEditingProposal | None = None


__all__ = [
    "ApplyMediaOperation",
    "RemoveMediaOperation",
    "ReorderSegmentsOperation",
    "SetCaptionTextOperation",
    "SetCutActionOperation",
    "SetSceneLookOperation",
    "SetSceneSpeedOperation",
    "SetSegmentBoundsOperation",
    "YujinEditingOperation",
    "YujinEditingProposal",
    "YujinEditingResponse",
]
