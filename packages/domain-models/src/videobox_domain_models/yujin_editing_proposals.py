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


class SetPhotoMotionOperation(_SegmentOperation):
    """사진 한 장이 **어떻게** 움직일지 고른다.

    `motion`이 `Literal`이 아닌 이유는 색감(`set_scene_look`)과 같다 -- 고를 수
    있는 표(`media_controls.PHOTO_MOTION_CHOICES`)는 core-engine에 있고,
    domain-models가 그것을 베끼면 두 벌이 갈라진다. 목록 대조는 검증기에서 한다.

    `still`("움직이지 않기")도 고르는 값이다 -- **안 고른 것과 다르다.** 안 고르면
    클립마다 알아서 정해지고, `still`은 멈춘다. 그래서 "가만히 둬"를 "안 고름"으로
    옮기지 않는다.
    """

    intent: Literal["set_photo_motion"]
    motion: str = Field(min_length=1, max_length=64)


class SetSceneTransitionOperation(_SegmentOperation):
    """이 장면으로 **넘어올 때** 쓸 전환.

    `type`이 `Literal`이 아닌 이유는 색감(`set_scene_look`)과 같다 -- 고를 수
    있는 표(`TRANSITION_CATALOG`)는 core-engine에 있고, domain-models가 그것을
    베끼면 두 벌이 갈라진다. 목록 대조는 검증기에서 한다.

    `None`은 "전환을 뺀다"는 뜻이다.
    """

    intent: Literal["set_scene_transition"]
    transition_type: str | None = Field(default=None, min_length=1, max_length=64)
    duration_sec: float | None = Field(default=None, gt=0, le=5)


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
    """화면 맞춤·확대·위치·기울이기. 말한 것만 바꾸고 나머지는 그대로 둔다.

    경계는 `media_controls.py`가 정한 것과 **같은 값**이다 -- 화면 입력이 만들 수
    없는 값을 말로는 만들 수 있게 두면, 그 값이 결국 렌더러에서 터진다.

    `fit`(화면 맞춤)이 여기 붙은 이유: 적용기가 이 명령의 칸을 그대로 그 장면
    B-roll의 조정값에 얹는데(`editing_session._merge_broll_media_controls`),
    화면 맞춤도 **같은 자리에 사는 같은 종류의 값**이다. 명령을 하나 더 만들면
    적용기·검증기·요약 문구가 한 벌씩 더 생긴다. 편집기 화면도 `화면 맞춤`을
    변형 넷 바로 위에 두고 있다.
    """

    intent: Literal["set_scene_transform"]
    #: 원본을 화면에 어떻게 앉힐까. 셋뿐이고 뜻은 `media_controls.BROLL_FIT_LABELS`
    #: 에 있다 -- `blur`(전체 담기)가 좌우를 안 자르는 값이다.
    fit: Literal["fit", "crop", "blur"] | None = None
    zoom: float | None = Field(default=None, ge=0.5, le=4.0)
    position_x_percent: float | None = Field(default=None, ge=-100.0, le=100.0)
    position_y_percent: float | None = Field(default=None, ge=-100.0, le=100.0)
    rotation_deg: float | None = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetSceneTransformOperation":
        if all(
            value is None
            for value in (self.fit, self.zoom, self.position_x_percent, self.position_y_percent, self.rotation_deg)
        ):
            raise ValueError("scene_transform_needs_a_change")
        return self


class SetImageOverlayOperation(_SegmentOperation):
    """사진을 영상 **위에** 얹는다. 자리·크기·움직임은 이름 붙은 프리셋만이다.

    `apply_media`(사진을 장면 화면으로 *깐다*)와 다른 일이다 -- 이건 이미 있는
    화면 위에 작게 얹는 것이고, 화면이 쓰는 `ImageOverlayRequest`와 같은 자리로
    간다(`update_segment_image_overlay`).

    넷이 `Literal`이 아니라 `str | None`인 이유는 색감·전환과 같다: 고를 수 있는
    목록의 원본은 core-engine(`overlay_shapes`)에 있고, domain-models가 그것을
    베끼면 두 벌이 갈라진다. 목록 대조는 검증기에서 한다.

    **넷 다 선택이고, 세 상태다**(최종 검토 2026-09-11 정정 -- 예전 문구는
    "안 준 값은 열쇠 자체를 안 적는다"까지만 말해서 지움과 유지를 구분하지
    못했다): 인자를 아예 안 주면 지금 저장된 값을 그대로 두고(유지), 명시적
    `None`을 주면 지워서 "안 고름"으로 되돌리고, 값을 주면 그 값으로 바꾼다
    (`update_segment_image_overlay` 머리말). 프리셋 없이 얹어 둔 옛 오버레이는
    처음부터 열쇠 자체가 없는 것과 자국이 같다.

    승인 범위는 도형과 같다(2026-08-20 승인 5항): 좌표(px/%)·초 단위·키프레임은
    밖이다. 그래서 여기에 그런 칸을 더하지 않는다.

    `preserve_source_audio`(Task 4, 2026-09-11)는 얹은 영상의 원본 소리를 켤지다 --
    프리셋 넷과 같은 선택 규칙을 따른다.
    """

    intent: Literal["set_image_overlay"]
    asset_id: str = Field(min_length=1, max_length=256)
    vertical: str | None = Field(default=None, min_length=1, max_length=32)
    horizontal: str | None = Field(default=None, min_length=1, max_length=32)
    size: str | None = Field(default=None, min_length=1, max_length=32)
    motion: str | None = Field(default=None, min_length=1, max_length=32)
    #: 얹은 영상의 원본 소리를 완성본에 실을지(Task 4, 2026-09-11). 이름은
    #: b-roll과 같은 칸을 그대로 빌린다(`editing_session.py:1582`) -- 같은
    #: 개념을 두 벌로 만들지 않는다. 프리셋 넷과 같은 규칙: `None`은 '고르지
    #: 않음'이라 저장된 값을 안 건드리고, 렌더러는 없는 열쇠를 `False`로 읽는다.
    preserve_source_audio: bool | None = None


class RemoveImageOverlayOperation(_SegmentOperation):
    """얹어 둔 사진을 뺀다. 거는 말만 있으면 되돌리는 길이 막힌다."""

    intent: Literal["remove_image_overlay"]


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
    | SetPhotoMotionOperation
    | SetSceneTransitionOperation
    | SetPictureCleanupOperation
    | SetSoundCleanupOperation
    | SetSceneTransformOperation
    | SetImageOverlayOperation
    | RemoveImageOverlayOperation
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
    "RemoveImageOverlayOperation",
    "RemoveMediaOperation",
    "ReorderSegmentsOperation",
    "SetCaptionTextOperation",
    "SetCutActionOperation",
    "SetCaptionFontOperation",
    "SetImageOverlayOperation",
    "SetPhotoMotionOperation",
    "SetPictureCleanupOperation",
    "SetSceneLookOperation",
    "SetSceneTransformOperation",
    "SetSceneTransitionOperation",
    "SetSoundCleanupOperation",
    "SetSceneSpeedOperation",
    "SetSegmentBoundsOperation",
    "YujinEditingOperation",
    "YujinEditingProposal",
    "YujinEditingResponse",
]
