"""Strict candidate-only response models for Yujin creator recommendations."""

from __future__ import annotations

from typing import Annotated, Literal
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from videobox_domain_models.yujin_creator_context import YujinCreatorContext


_ID_BYTES = 256
_TEXT_BYTES = 1024
#: "숏폼 만들어줘"의 target `variant_id`. **아직 없는 변형본**을 가리키는 자리라
#: 진짜 id를 넣을 수 없다 -- 그래서 값 하나로 고정한다. `validate_yujin_creator_response`가
#: 정확히 이 값일 때만 만들기로 받는다(다른 값이면 존재하지 않는 진짜 변형본을
#: 가리키려는 것으로 보고 거절한다).
PENDING_SHORT_FORM_TARGET_ID = "pending-short-form"
UNSAFE_CREDENTIAL_LABELS = (
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "bearer",
    "credential",
    "secret",
    "password",
    "token",
    "aws_access_key_id",
    "aws_secret_access_key",
    "openai_api_key",
    "github_token",
    "slack_token",
    "huggingface_token",
    "google_api_key",
)
UNSAFE_CREDENTIAL_LABEL_PATTERN = (
    r"(?:"
    + "|".join(re.escape(label).replace("_", r"[_-]?") for label in UNSAFE_CREDENTIAL_LABELS)
    + r")"
)
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$")
_UNSAFE_ID_PREFIX = re.compile(
    rf"(?i)^{UNSAFE_CREDENTIAL_LABEL_PATTERN}(?:$|[_-])"
)
_UNSAFE_ID_TOKEN = re.compile(
    r"(?i)^(?:sk-(?:proj-)?[a-z0-9_-]{16,}|gh[pousr]_[a-z0-9]{20,}|"
    r"xox[a-z]-[a-z0-9-]{16,}|hf_[a-z0-9]{16,}|"
    r"(?:akia|asia)[a-z0-9]{16}|aiza[a-z0-9_-]{20,})$"
)
_URI_SCHEME = re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:(?!\s)")
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|//[^/\s]+/|/(?:[^/\s]+/)*[^/\s]+)"
)
_LABELED_CREDENTIAL = re.compile(
    rf"(?i)\b{UNSAFE_CREDENTIAL_LABEL_PATTERN}\s*[:=]\s*\S+"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+\S{8,}")
_JWT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
_PROVIDER_TOKEN = re.compile(
    r"(?:\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bxox[a-z]-[A-Za-z0-9-]{16,}\b|"
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b|"
    r"\bAIza[A-Za-z0-9_-]{20,}\b|"
    r"\bya29\.[A-Za-z0-9_-]{16,}\b|"
    r"\bhf_[A-Za-z0-9]{16,}\b)"
)
_PRIVATE_KEY_PEM = re.compile(
    r"-----BEGIN (?:[A-Z0-9][A-Z0-9 -]* )?PRIVATE KEY-----",
    re.IGNORECASE,
)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, allow_inf_nan=False
    )


def _bounded_utf8(value: str, *, limit: int, label: str) -> str:
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{label}_too_large")
    return value


def _validate_table_item(value: str, *, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label}_required")
    if len(value) > 256:
        raise ValueError(f"{label}_too_many_code_points")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label}_invalid_unicode") from exc
    if size > 1_024:
        raise ValueError(f"{label}_too_large")


def _validated_model_id(value: str, *, label: str) -> str:
    _bounded_utf8(value, limit=_ID_BYTES, label=label)
    if (
        _SAFE_MODEL_ID.fullmatch(value) is None
        or _UNSAFE_ID_PREFIX.search(value) is not None
        or _UNSAFE_ID_TOKEN.fullmatch(value) is not None
    ):
        raise ValueError(f"{label}_unsafe")
    return value


def _is_unsafe_parameter_value(value: str) -> bool:
    candidate = value.strip()
    return bool(
        _URI_SCHEME.search(candidate)
        or _ABSOLUTE_PATH.search(candidate)
        or _PRIVATE_KEY_PEM.search(candidate)
        or _LABELED_CREDENTIAL.search(candidate)
        or _BEARER_TOKEN.search(candidate)
        or _JWT_TOKEN.search(candidate)
        or _PROVIDER_TOKEN.search(candidate)
    )


class _TargetWithSegment(_StrictFrozenModel):
    segment_id: str = Field(min_length=1, max_length=256)

    @field_validator("segment_id")
    @classmethod
    def segment_id_fits_utf8(cls, value: str) -> str:
        return _bounded_utf8(value, limit=_ID_BYTES, label="target_id")


class _TargetWithScriptAndSegment(_TargetWithSegment):
    script_id: str = Field(min_length=1, max_length=256)

    @field_validator("script_id")
    @classmethod
    def script_id_fits_utf8(cls, value: str) -> str:
        return _bounded_utf8(value, limit=_ID_BYTES, label="target_id")


class BrollTarget(_TargetWithSegment):
    track_id: Literal["video-primary"]


class BgmTarget(_StrictFrozenModel):
    track_id: Literal["audio-bgm"]


class SfxTarget(_TargetWithSegment):
    track_id: Literal["audio-sfx"]


class CaptionTarget(_TargetWithScriptAndSegment):
    track_id: Literal["caption-primary"]


class VoiceTarget(_TargetWithScriptAndSegment):
    track_id: Literal["voice-primary"]


class OverlayTarget(_TargetWithSegment):
    track_id: Literal["video-overlay"]


class OutputCheckTarget(_StrictFrozenModel):
    track_id: Literal["output-primary"]


class OutputVariantTarget(_StrictFrozenModel):
    variant_id: str = Field(min_length=1, max_length=256)
    track_id: Literal["output-variant"]

    @field_validator("variant_id")
    @classmethod
    def variant_id_fits_utf8(cls, value: str) -> str:
        return _validated_model_id(value, label="variant_id")


class _Parameters(_StrictFrozenModel):
    @model_validator(mode="after")
    def reject_unsafe_values(self):
        def walk(value: object) -> None:
            if isinstance(value, str) and _is_unsafe_parameter_value(value):
                raise ValueError("unsafe_parameter_value")
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, (tuple, list)):
                for item in value:
                    walk(item)

        walk(self.model_dump(mode="python"))
        for name, value in self.model_dump(mode="python").items():
            if name.endswith("_id") and isinstance(value, str):
                _bounded_utf8(value, limit=_ID_BYTES, label=name)
        return self


class BrollParameters(_Parameters):
    asset_id: str = Field(min_length=1, max_length=256)
    start_sec: float = Field(ge=0, le=86_400)
    duration_sec: float = Field(gt=0, le=3_600)
    #: 원본을 화면에 앉히는 방법. `contain_blur`는 2026-09-12에 들어왔다 --
    #: 원본 전체를 담고 남는 자리를 같은 그림의 흐린 확대본으로 채운다(엔진의
    #: `blur`). 세로 숏폼에서 구워진 자막이 양쪽에서 잘리는 것을 막는 값이다.
    #: 이름 대응은 `yujin_creator_proposal_adapter._BROLL_FIT_BY_PROPOSAL_VALUE`.
    fit: Literal["contain", "cover", "contain_blur"] = "cover"


class BgmParameters(_Parameters):
    asset_id: str = Field(min_length=1, max_length=256)
    start_sec: float = Field(ge=0, le=86_400)
    duration_sec: float | None = Field(default=None, gt=0, le=86_400)
    volume: float = Field(default=1.0, ge=0, le=2)
    fade_in_sec: float = Field(default=0.0, ge=0, le=30)
    fade_out_sec: float = Field(default=0.0, ge=0, le=30)


class SfxParameters(_Parameters):
    asset_id: str = Field(min_length=1, max_length=256)
    start_sec: float = Field(ge=0, le=86_400)
    volume: float = Field(default=1.0, ge=0, le=2)


class CaptionTextParameters(_Parameters):
    action: Literal["set_text"]
    text: str = Field(min_length=1, max_length=1024)

    @field_validator("text")
    @classmethod
    def text_fits_utf8(cls, value: str) -> str:
        return _bounded_utf8(value, limit=2_048, label="caption_text")


class EditorCaptionStyle(_StrictFrozenModel):
    font_family: str = Field(min_length=1, max_length=128)
    font_size_px: int = Field(ge=12, le=160)
    text_color: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")
    outline_color: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")
    outline_width_px: int = Field(ge=0, le=12)
    background_color: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")
    position_x_percent: int = Field(ge=0, le=100)
    position_y_percent: int = Field(ge=0, le=100)
    horizontal_align: Literal["left", "center", "right"]
    safe_area_enabled: bool
    shadow_blur_px: int = Field(ge=0)

    @model_validator(mode="after")
    def clamp_position_to_backend_safe_area(self):
        if self.safe_area_enabled and self.position_y_percent > 94:
            object.__setattr__(self, "position_y_percent", 94)
        return self


class CaptionStyleParameters(_Parameters):
    action: Literal["set_style"]
    style: EditorCaptionStyle


CaptionParameters = Annotated[
    CaptionTextParameters | CaptionStyleParameters,
    Field(discriminator="action"),
]


class VoiceParameters(_Parameters):
    candidate_id: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^tts_candidate_[A-Za-z0-9_-]+$",
    )
    asset_id: str = Field(min_length=1, max_length=256)


class ExplanationCardParameters(_Parameters):
    overlay_kind: Literal["explanation_card"]
    title: str = Field(max_length=256)
    body: str = Field(max_length=1024)
    text: str = Field(min_length=1, max_length=1024)


class ImageOverlayParameters(_Parameters):
    overlay_kind: Literal["image"]
    asset_id: str = Field(min_length=1, max_length=256)
    text: str = Field(max_length=1024)


class TableOverlayParameters(_Parameters):
    overlay_kind: Literal["table"]
    columns: tuple[str, ...] = Field(max_length=32)
    rows: tuple[tuple[str, ...], ...] = Field(max_length=128)
    text: str = Field(min_length=1, max_length=1024)

    @field_validator("columns")
    @classmethod
    def columns_are_bounded(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        for item in value:
            _validate_table_item(item, label="overlay_table_column")
        return value

    @field_validator("rows")
    @classmethod
    def cells_are_bounded(
        cls,
        value: tuple[tuple[str, ...], ...],
    ) -> tuple[tuple[str, ...], ...]:
        for row in value:
            for cell in row:
                _validate_table_item(cell, label="overlay_table_cell")
        return value

    @model_validator(mode="after")
    def table_shape_matches_columns(self):
        if not self.columns or any(not item.strip() for item in self.columns):
            raise ValueError("overlay_table_columns_required")
        if any(
            len(row) != len(self.columns) or any(not cell.strip() for cell in row)
            for row in self.rows
        ):
            raise ValueError("overlay_table_rows_malformed")
        return self


OverlayParameters = Annotated[
    ExplanationCardParameters | ImageOverlayParameters | TableOverlayParameters,
    Field(discriminator="overlay_kind"),
]


class OutputCheckParameters(_Parameters):
    check: Literal["timeline_gaps"]


class VariantCropParameters(_Parameters):
    action: Literal["set_crop"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def crop_stays_in_frame(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("variant_crop_out_of_bounds")
        return self


class VariantFocalParameters(_Parameters):
    action: Literal["set_focal"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class VariantCaptionLayoutParameters(_Parameters):
    action: Literal["set_caption_layout"]
    layout: Literal["top", "center", "bottom"]
    max_lines: int = Field(ge=1, le=3)
    font_scale: float = Field(ge=0.75, le=1.5)


class VariantSafeAreaParameters(_Parameters):
    action: Literal["set_safe_area"]
    top_percent: int = Field(ge=0, le=40)
    right_percent: int = Field(ge=0, le=40)
    bottom_percent: int = Field(ge=0, le=40)
    left_percent: int = Field(ge=0, le=40)

    @model_validator(mode="after")
    def safe_area_leaves_renderable_frame(self):
        if self.left_percent + self.right_percent >= 100:
            raise ValueError("variant_safe_area_horizontal_empty")
        if self.top_percent + self.bottom_percent >= 100:
            raise ValueError("variant_safe_area_vertical_empty")
        return self


class VariantAudioCorrectionParameters(_Parameters):
    action: Literal["correct_audio"]
    gain_db: float = Field(ge=-12, le=12)
    fade_in_sec: float = Field(ge=0, le=10)
    fade_out_sec: float = Field(ge=0, le=10)


class VariantShortsTitleParameters(_Parameters):
    """숏폼 **첫 화면 제목 띠**(`videobox_core_engine.shorts_layout`).

    왜 모양 조정 다섯 옆에 있는가. 제목 띠는 이야기가 아니라 화면이다 -- 장면
    목록도 순서도 안 바꾸고, 픽셀만 달라진다. 그래서 `select_segments`가 아니라
    덮어쓰기이고 `overrides.layout` 한 칸에 들어간다.

    **문구를 지우는 길을 따로 두지 않는다.** 끄기는 `hidden: true`이고 문구는 그대로
    남는다 -- 지우면 다시 켤 때 되돌릴 것이 없다(유진 편집은 확인 클릭 없이 바로
    적용되고 안전장치가 되돌리기 하나다, 2026-09-01 결정). 그래서 켜고 끌 때도
    `title_lines`를 **같이 적어야 한다**: 덮어쓰기는 필드를 통째로 갈아 끼운다.
    """

    action: Literal["set_shorts_title"]
    #: 위에서 아래로 읽는 순서. 참고 숏폼 넷은 2~3줄이었고(2026-09-12 실측)
    #: 1행이 대상·미끼, 2행이 결과·질문이었다.
    title_lines: tuple[str, ...] = Field(min_length=1, max_length=3)
    #: 초록으로 칠할 낱말 하나. 제목 안에 실제로 있어야 한다 -- 없으면 거절한다.
    #: 안 고르면 `None`이고 전부 흰색이다.
    highlight: str | None = Field(default=None, max_length=20)
    #: 문구는 남기고 띠만 끈다.
    hidden: bool = False

    @field_validator("title_lines")
    @classmethod
    def lines_are_bounded_and_present(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not item.strip():
                raise ValueError("shorts_title_line_required")
            _bounded_utf8(item, limit=_TITLE_LINE_BYTES, label="shorts_title_line")
        return value

    @model_validator(mode="after")
    def highlight_is_in_the_title(self):
        # **지어내지 않는다.** 제목에 없는 낱말을 강조로 받으면 렌더러가 조용히
        # 무시하는데, 그러면 "골랐다"는 기록과 결과가 어긋난다.
        if self.highlight is not None and not self.highlight.strip():
            raise ValueError("shorts_title_highlight_empty")
        if self.highlight and not any(self.highlight in line for line in self.title_lines):
            raise ValueError("shorts_title_highlight_not_in_title")
        return self


#: 제목 한 줄의 상한(UTF-8 바이트). 한글 열다섯 자가 45바이트라 넉넉한 쪽으로
#: 잡는다 -- 화면에 큰 글씨로 그려지므로 이보다 길면 줄이 넘친다.
_TITLE_LINE_BYTES = 120


class VariantSegmentSelectionParameters(_Parameters):
    """숏폼에 넣을 장면을 **통째 목록으로** 받는다.

    앞의 다섯은 전부 모양 조정(크롭·초점·자막배치·안전영역·소리)이라 숏폼의
    본질인 "어느 장면을 넣을지"를 못 정했다.

    "이 장면 빼/넣어"라는 델타가 아니라 통째 목록인 이유는 **되돌리기**다.
    유진 편집은 확인 클릭 없이 바로 적용되고(2026-09-01 결정) 안전장치가
    되돌리기 하나뿐인데, 이 목록은 장면 구성뿐 아니라 **순서**까지 정한다
    (`materialize_variant`가 이 순서대로 장면을 늘어놓는다). 델타에는 뺀
    장면을 나중에 **몇 번째 자리로** 되돌릴지가 남지 않는다. 통째 목록은
    이전 목록을 그대로 다시 보내는 것 하나로 원래대로 돌아간다.
    """

    action: Literal["select_segments"]
    segment_ids: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator("segment_ids")
    @classmethod
    def segment_ids_are_bounded_and_distinct(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        for item in value:
            if not item.strip():
                raise ValueError("selected_segment_id_required")
            _bounded_utf8(item, limit=_ID_BYTES, label="target_id")
        if len(set(value)) != len(value):
            raise ValueError("duplicate_selected_segment_ids")
        return value


class VariantShortFormRemakeParameters(_Parameters):
    """숏폼을 **다시 만든다.** 장면 목록을 유진이 적지 않는다.

    `select_segments`와 왜 따로 있는가. 채팅으로 장면을 직접 고를 때 유진이 보는
    것은 창작 맥락의 `segment_summaries`이고 그건 32개에서 잘린다 -- 243장면짜리
    롱폼에서는 단추 경로(영상 전 구간의 말을 묶어 전부 읽고 "이게 퍼질까"로
    판단하는 `short_form_scene_pick`)보다 못한 판단이다. 그래서 프로필은 그럴 때 단추를
    쓰라고 안내해 왔는데, "단추를 쓰세요"는 **말로 시킬 수 있어야 한다**는
    대표님 상시 지시를 못 지킨다.

    이 action은 그 쓸기를 **서버에서** 돌리게 한다. 유진은 "다시 판단해"라고만
    말하고, 판을 전부 읽는 일은 단추와 똑같은 코드가 한다. 읽기 전용 검사
    (`output_check: timeline_gaps`)와 같은 모양이다 -- 결과를 backend가 만든다.

    파라미터가 없는 이유: 목록을 직접 주는 길은 이미 `select_segments`에 있다.
    둘을 겹치게 하면 "다시 만들기"가 사실은 유진이 눈대중으로 고른 목록인
    경우가 생기고, 그건 대표님이 구분할 수 없다.
    """

    action: Literal["remake_short_form"]


class VariantShortFormCreateParameters(_Parameters):
    """숏폼을 **처음** 만든다. 지금 걸린 변형본이 없을 때만 쓴다.

    `remake_short_form`과 왜 따로 있는가. 그쪽은 이미 있는 숏폼의 장면을 다시
    고르는 일이라 `proposal.variant_id`·`base_variant_revision`이 지금 걸린
    변형본을 가리켜야 한다(`unique_operation_ids`). 만들기는 그 반대다 --
    가리킬 변형본이 아직 없다. 그래서 이 action이 실린 proposal은 둘 다
    `None`이어야 하고, target에는 진짜 id 대신 `PENDING_SHORT_FORM_TARGET_ID`를
    쓴다.

    파라미터가 없는 이유는 `remake_short_form`과 같다 -- 장면 고르기는 서버가
    화면 단추와 같은 코드로 하고(`short_form_scenes.short_form_scene_pick`),
    유진은 "만들어 줘"라고만 말한다.
    """

    action: Literal["create_short_form"]


class VariantShortFormUnfoldParameters(_Parameters):
    """숏폼을 **따로 편집할 수 있는 판으로 펼친다.**

    왜 이 action이 있어야 하는가. 숏폼이 담을 수 있는 것은 장면 목록과 화면 전체
    설정 다섯뿐이라, 장면별 편집은 전부 마스터 세션으로 간다 -- 숏폼의 한 장면을
    확대하면 원본 영상의 그 장면도 확대된다. 펼치면 그 뒤로는 **이미 있는 편집
    의도 16개 전부**가 그 판에서 그대로 돈다(자막·확대·전환·효과음·오버레이·
    되돌리기). 새 배선이 필요한 것은 이 문 하나다.

    파라미터가 없는 이유는 `remake_short_form`과 같다 -- 펼치기는 편집이 아니라
    **그릇을 옮기는 일**이고, 옮긴 뒤의 편집은 원래 있던 문들이 받는다. 여기에
    편집 내용을 같이 실으면 "펼치기"가 사실은 편집인 경우가 생긴다.

    **대가는 원본과의 줄이 끊기는 것이다**
    (`videobox_core_engine.output_variants.UNFOLD_INDEPENDENCE_RULE`). 유진
    안내문이 그 문장을 그대로 말해야 한다 -- 되돌릴 수 없는 일을 말없이 하면
    안 된다.
    """

    action: Literal["unfold_to_editing_board"]


VariantParameters = Annotated[
    VariantCropParameters
    | VariantFocalParameters
    | VariantCaptionLayoutParameters
    | VariantSafeAreaParameters
    | VariantAudioCorrectionParameters
    | VariantShortsTitleParameters
    | VariantSegmentSelectionParameters
    | VariantShortFormCreateParameters
    | VariantShortFormRemakeParameters
    | VariantShortFormUnfoldParameters,
    Field(discriminator="action"),
]


class _Operation(_StrictFrozenModel):
    operation_id: str = Field(min_length=1, max_length=256)
    preview_summary: str = Field(min_length=1, max_length=512)

    @field_validator("operation_id")
    @classmethod
    def operation_id_fits_utf8(cls, value: str) -> str:
        return _validated_model_id(value, label="operation_id")

    @field_validator("preview_summary")
    @classmethod
    def preview_fits_utf8(cls, value: str) -> str:
        bounded = _bounded_utf8(value, limit=_TEXT_BYTES, label="preview_summary")
        if _is_unsafe_parameter_value(bounded):
            raise ValueError("unsafe_preview_summary")
        return bounded


class BrollOperation(_Operation):
    kind: Literal["broll"]
    target: BrollTarget
    parameters: BrollParameters
    requires_materialization: Literal[True]


class BgmOperation(_Operation):
    kind: Literal["bgm"]
    target: BgmTarget
    parameters: BgmParameters
    requires_materialization: Literal[True]


class SfxOperation(_Operation):
    kind: Literal["sfx"]
    target: SfxTarget
    parameters: SfxParameters
    requires_materialization: Literal[True]


class CaptionOperation(_Operation):
    kind: Literal["caption"]
    target: CaptionTarget
    parameters: CaptionParameters
    requires_materialization: Literal[False]


class VoiceOperation(_Operation):
    kind: Literal["voice"]
    target: VoiceTarget
    parameters: VoiceParameters
    requires_materialization: Literal[False]


class OverlayOperation(_Operation):
    kind: Literal["overlay"]
    target: OverlayTarget
    parameters: OverlayParameters
    requires_materialization: Literal[False]


class OutputCheckOperation(_Operation):
    kind: Literal["output_check"]
    target: OutputCheckTarget
    parameters: OutputCheckParameters
    requires_materialization: Literal[False]


class OutputVariantOperation(_Operation):
    kind: Literal["output_variant"]
    target: OutputVariantTarget
    parameters: VariantParameters
    requires_materialization: Literal[False]


YujinOperation = Annotated[
    BrollOperation
    | BgmOperation
    | SfxOperation
    | CaptionOperation
    | VoiceOperation
    | OverlayOperation
    | OutputCheckOperation
    | OutputVariantOperation,
    Field(discriminator="kind"),
]


class YujinProposal(_StrictFrozenModel):
    proposal_id: str = Field(min_length=1, max_length=256)
    base_revision: str = Field(min_length=1, max_length=768)
    title: str = Field(min_length=1, max_length=256)
    rationale: str = Field(min_length=1, max_length=1024)
    variant_id: str | None = Field(default=None, min_length=1, max_length=256)
    base_variant_revision: int | None = Field(default=None, ge=1)
    operations: tuple[YujinOperation, ...] = Field(min_length=1, max_length=16)

    @field_validator("proposal_id")
    @classmethod
    def proposal_id_fits_utf8(cls, value: str) -> str:
        return _validated_model_id(value, label="proposal_id")

    @field_validator("title")
    @classmethod
    def title_fits_utf8(cls, value: str) -> str:
        bounded = _bounded_utf8(value, limit=512, label="proposal_title")
        if _is_unsafe_parameter_value(bounded):
            raise ValueError("unsafe_proposal_title")
        return bounded

    @field_validator("rationale")
    @classmethod
    def rationale_fits_utf8(cls, value: str) -> str:
        bounded = _bounded_utf8(value, limit=2_048, label="proposal_rationale")
        if _is_unsafe_parameter_value(bounded):
            raise ValueError("unsafe_proposal_rationale")
        return bounded

    @field_validator("variant_id")
    @classmethod
    def variant_id_fits_utf8(cls, value: str | None) -> str | None:
        return (
            _validated_model_id(value, label="variant_id")
            if value is not None
            else None
        )

    @model_validator(mode="after")
    def unique_operation_ids(self):
        operation_ids = [operation.operation_id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("duplicate_operation_id")
        has_variant_operation = any(
            operation.kind == "output_variant" for operation in self.operations
        )
        # **만들기는 정체성이 거꾸로다.** 나머지 여덟 action은 "지금 걸린 것과
        # 정확히 같은가"를 요구하는데(그래서 `variant_id`·`base_variant_revision`이
        # 있어야 한다), 만들기는 가리킬 변형본이 아직 없다 -- 있으면 그건 이미
        # 만들어졌다는 뜻이라 오히려 잘못이다.
        is_create_variant_operation = any(
            operation.kind == "output_variant"
            and operation.parameters.action == "create_short_form"
            for operation in self.operations
        )
        if is_create_variant_operation:
            if len(self.operations) != 1:
                raise ValueError("variant_short_form_create_must_be_alone")
            if self.variant_id is not None or self.base_variant_revision is not None:
                raise ValueError("variant_short_form_create_has_no_identity_yet")
        elif has_variant_operation and (
            self.variant_id is None or self.base_variant_revision is None
        ):
            raise ValueError("variant_identity_required")
        elif not has_variant_operation and (
            self.variant_id is not None or self.base_variant_revision is not None
        ):
            raise ValueError("variant_identity_without_variant_operation")
        return self


class YujinCreatorResponse(_StrictFrozenModel):
    schema_version: Literal["videobox.yujin-response.v1"]
    reply_text: str = Field(min_length=1, max_length=8192)
    proposal: YujinProposal | None = None

    @field_validator("reply_text")
    @classmethod
    def reply_fits_utf8(cls, value: str) -> str:
        return _bounded_utf8(value, limit=16_384, label="reply_text")


def canonical_yujin_base_revision(context: YujinCreatorContext) -> str:
    return (
        f"session:{context.session_id}:revision:{context.session_revision}:"
        f"assets:{context.asset_index_revision}"
    )


def validate_yujin_creator_response(
    payload: dict[str, object] | str,
    context: YujinCreatorContext,
) -> YujinCreatorResponse:
    """Parse JSON strictly and attest every proposal reference to the context."""

    json_text = (
        payload
        if isinstance(payload, str)
        else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    response = YujinCreatorResponse.model_validate_json(json_text)
    proposal = response.proposal
    if proposal is None:
        return response
    if proposal.base_revision != canonical_yujin_base_revision(context):
        raise ValueError("proposal_base_revision_not_current")

    controls = {control.kind: control.mode for control in context.supported_controls}
    segment_ids = {item.segment_id for item in context.segment_summaries}
    media = {item.asset_id: item.kind for item in context.media_candidates}
    expected_modes = {
        "broll": "recommendation_only",
        "bgm": "recommendation_only",
        "sfx": "recommendation_only",
        "caption": "recommendation_only",
        "voice": "recommendation_only",
        "overlay": "recommendation_only",
        "output_check": "read_only",
        "output_variant": "recommendation_only",
    }
    expected_tracks = {
        "broll": "video-primary",
        "bgm": "audio-bgm",
        "sfx": "audio-sfx",
        "caption": "caption-primary",
        "voice": "voice-primary",
        "overlay": "video-overlay",
        "output_check": "output-primary",
        "output_variant": "output-variant",
    }
    compatible_media = {
        "broll": {"raw_video", "broll_video", "image"},
        "bgm": {"bgm"},
        "sfx": {"sfx"},
    }
    approved_tts = {
        (item.candidate_id, item.asset_id, item.segment_id)
        for item in context.approved_tts_candidates
    }
    segment_required = {"broll", "sfx", "caption", "voice", "overlay"}
    script_required = {"caption", "voice"}

    for operation in proposal.operations:
        if controls.get(operation.kind) != expected_modes[operation.kind]:
            raise ValueError("proposal_operation_unsupported")
        target = operation.target
        if operation.kind == "output_variant":
            if operation.parameters.action == "create_short_form":
                # **만들기는 지금 걸린 변형본이 없어야 한다.** 위(아래) 얼개는
                # "지금 걸린 것과 똑같은가"를 묻는데 이건 그 반대다 -- 이미 있으면
                # (`context.has_short_form_variant`) 유진은 화면이 세션당
                # 하나만 만들게 막는 규칙을 두 번째로 어기려는 것이다(그 경우도
                # 서버가 `sqlite3.IntegrityError`로 다시 막지만, 여기서 먼저
                # 거절해 헛되이 판을 읽지 않는다).
                if (
                    context.current_surface not in {"edit", "review", "output"}
                    or context.master_session_id != context.session_id
                    or context.master_session_revision != context.session_revision
                    or context.has_short_form_variant
                    or proposal.variant_id is not None
                    or proposal.base_variant_revision is not None
                    or target.variant_id != PENDING_SHORT_FORM_TARGET_ID
                ):
                    raise ValueError("proposal_variant_identity_not_current")
                continue
            if (
                context.current_surface not in {"edit", "review", "output"}
                or context.selection_kind != "variant"
                or context.master_session_id != context.session_id
                or context.master_session_revision != context.session_revision
                or context.variant_id is None
                or context.variant_kind is None
                or context.variant_revision is None
                or proposal.variant_id != context.variant_id
                or proposal.base_variant_revision != context.variant_revision
                or target.variant_id != context.variant_id
            ):
                raise ValueError("proposal_variant_identity_not_current")
            if operation.parameters.action in {
                "select_segments",
                # 첫 화면 제목 띠도 숏폼에만 있다. 가로·세로 전체본은 원본과 같은
                # 이야기를 다른 화면비로 내보내는 것이라 제목을 붙일 자리가 없고,
                # `build_variant_timeline_payload`가 그쪽에는 안 싣는다 -- 유진이
                # 그 자리까지 가지 않게 여기서 먼저 막는다.
                "set_shorts_title",
                "remake_short_form",
                # 펼치기도 같은 경계다 -- 장면 목록이 마스터와 다른 모양은
                # 숏폼뿐이고, 전체본을 펼치면 원본을 한 벌 더 만드는 일이 된다.
                "unfold_to_editing_board",
            }:
                # 장면 구성을 바꿀 수 있는 모양은 **숏폼(세로 하이라이트)뿐이다.**
                # 세로 전체본은 `materialize_variant`가
                # `vertical_full_segment_order_or_membership_changed`로,
                # `apply_variant_patch`는 `only_vertical_highlight_can_select_segments`로
                # 거부한다 -- 유진이 그 자리까지 가지 않게 여기서 먼저 막는다.
                # 다시 만들기(`remake_short_form`)도 결국 같은 목록을 갈아 끼우므로
                # 같은 경계를 받는다.
                if context.variant_kind != "vertical_highlight":
                    raise ValueError("proposal_variant_kind_cannot_select_segments")
            if operation.parameters.action == "select_segments" and any(
                item not in segment_ids for item in operation.parameters.segment_ids
            ):
                raise ValueError("proposal_target_segment_not_current")
            continue
        if operation.kind in segment_required and target.segment_id not in segment_ids:
            raise ValueError("proposal_target_segment_not_current")
        if operation.kind in script_required and (
            context.selected_script_id is None
            or target.script_id != context.selected_script_id
        ):
            raise ValueError("proposal_target_script_not_current")
        if target.track_id != expected_tracks[operation.kind]:
            raise ValueError("proposal_target_track_missing_or_unsupported")
        parameters = operation.parameters
        asset_id = getattr(parameters, "asset_id", None)
        if operation.kind in compatible_media and (
            media.get(asset_id) not in compatible_media[operation.kind]
        ):
            raise ValueError("proposal_media_incompatible")
        if operation.kind == "voice" and (
            parameters.candidate_id,
            parameters.asset_id,
            target.segment_id,
        ) not in approved_tts:
            raise ValueError("proposal_tts_candidate_not_current")
        if (
            operation.kind == "overlay"
            and parameters.overlay_kind == "image"
            and media.get(parameters.asset_id) != "image"
        ):
            raise ValueError("proposal_media_incompatible")
    return response
