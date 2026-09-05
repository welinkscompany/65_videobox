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


class SetCaptionFontOperation(_StrictFrozenModel):
    """자막 글꼴 바꾸기 -- **편집본 전체**에 걸린다(owner 지시 2026-09-05).

    장면 번호를 받지 않는 이유: 자막 모양은 원래 편집본 단위로 걸린다
    (`update_caption_style`의 `whole_project`). 장면마다 글꼴이 달라지면 한
    영상 안에서 자막이 춤춘다 -- 그걸 원하는 창작자는 화면에서 직접 고른다.

    `family`가 이 기계에 실제로 있는 글꼴인지는 스키마가 아니라 해석 단계에서
    본다(`yujin_editing_proposal_service`) -- 목록이 기계마다 다르기 때문이다.
    """

    intent: Literal["set_caption_font"]
    #: 글꼴 이름. **크기만 바꿀 때는 비운다** -- "글꼴 더 큰 걸로"라고만 하면
    #: 창작자는 지금 글꼴이 무엇인지 말하지 않았고, 여기에 아무 이름이나 채우면
    #: 맞춰 둔 글꼴이 조용히 바뀐다.
    family: str | None = Field(default=None, min_length=1, max_length=128)
    #: 자막 글자 크기(px). 화면이 쓰는 것과 같은 범위다(`CaptionStyle`).
    #: 2026-09-06까지는 이 칸이 없어서 "글꼴 좀 더 큰 걸로 바꿔줘"에 유진이
    #: 되물을 수밖에 없었다 -- 화면에서는 되는 일이었다.
    size_px: int | None = Field(default=None, ge=12, le=160)

    @model_validator(mode="after")
    def _at_least_one(self) -> "SetCaptionFontOperation":
        if self.family is None and self.size_px is None:
            raise ValueError("set_caption_font needs a family, a size_px, or both.")
        return self


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


class SetPictureCleanupOperation(_SegmentOperation):
    """흔들림 보정·화면 노이즈 줄이기. 켜고 끄는 것뿐이다.

    **둘 다 `None`을 허용하는 이유**: 창작자가 "흔들림만 잡아 줘"라고 하면 노이즈
    설정은 손대지 않아야 한다. 필수로 두면 모델이 안 물어본 칸까지 값을 채워야
    하고, 그러면 이미 켜 둔 것을 끄는 일이 생긴다 -- 2026-09-02에 음악에서
    똑같은 사고(옆 장면을 덮어씀)를 겪었다.
    """

    intent: Literal["set_picture_cleanup"]
    stabilize: bool | None = None
    reduce_noise: bool | None = None

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetPictureCleanupOperation":
        if self.stabilize is None and self.reduce_noise is None:
            raise ValueError("picture_cleanup_needs_a_change")
        return self


class SetSoundCleanupOperation(_SegmentOperation):
    """소리 크기 고르게 맞추기·잡음 줄이기. 위와 같은 이유로 둘 다 선택이다."""

    intent: Literal["set_sound_cleanup"]
    media_type: Literal["bgm", "sfx"]
    normalize_loudness: bool | None = None
    denoise: bool | None = None

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetSoundCleanupOperation":
        if self.normalize_loudness is None and self.denoise is None:
            raise ValueError("sound_cleanup_needs_a_change")
        return self


class SetSceneTransformOperation(_SegmentOperation):
    """확대·위치·기울이기. 말한 것만 바꾸고 나머지는 그대로 둔다.

    경계는 `media_controls.py`가 정한 것과 **같은 값**이다 -- 화면 입력이 만들 수
    없는 값을 말로는 만들 수 있게 두면, 그 값이 결국 렌더러에서 터진다.
    """

    intent: Literal["set_scene_transform"]
    zoom: float | None = Field(default=None, ge=0.5, le=4.0)
    position_x_percent: float | None = Field(default=None, ge=-100.0, le=100.0)
    position_y_percent: float | None = Field(default=None, ge=-100.0, le=100.0)
    rotation_deg: float | None = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetSceneTransformOperation":
        if all(value is None for value in (self.zoom, self.position_x_percent, self.position_y_percent, self.rotation_deg)):
            raise ValueError("scene_transform_needs_a_change")
        return self


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
    | SetCaptionFontOperation
    | SetSceneLookOperation
    | SetPictureCleanupOperation
    | SetSoundCleanupOperation
    | SetSceneTransformOperation
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
    "SetCaptionFontOperation",
    "SetPictureCleanupOperation",
    "SetSceneLookOperation",
    "SetSceneTransformOperation",
    "SetSoundCleanupOperation",
    "SetSceneSpeedOperation",
    "SetSegmentBoundsOperation",
    "YujinEditingOperation",
    "YujinEditingProposal",
    "YujinEditingResponse",
]
