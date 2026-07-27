"""Strict candidate-only response models for Yujin creator recommendations."""

from __future__ import annotations

from typing import Annotated, Literal
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from videobox_domain_models.yujin_creator_context import YujinCreatorContext


_ID_BYTES = 256
_TEXT_BYTES = 1024
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
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _bounded_utf8(value: str, *, limit: int, label: str) -> str:
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{label}_too_large")
    return value


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
    fit: Literal["contain", "cover"] = "cover"


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
    position_y_percent: int = Field(ge=0, le=94)
    horizontal_align: Literal["left", "center", "right"]
    safe_area_enabled: bool
    shadow_blur_px: int = Field(ge=0)


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


YujinOperation = Annotated[
    BrollOperation
    | BgmOperation
    | SfxOperation
    | CaptionOperation
    | VoiceOperation
    | OverlayOperation
    | OutputCheckOperation,
    Field(discriminator="kind"),
]


class YujinProposal(_StrictFrozenModel):
    proposal_id: str = Field(min_length=1, max_length=256)
    base_revision: str = Field(min_length=1, max_length=768)
    title: str = Field(min_length=1, max_length=256)
    rationale: str = Field(min_length=1, max_length=1024)
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

    @model_validator(mode="after")
    def unique_operation_ids(self):
        operation_ids = [operation.operation_id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("duplicate_operation_id")
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
    }
    expected_tracks = {
        "broll": "video-primary",
        "bgm": "audio-bgm",
        "sfx": "audio-sfx",
        "caption": "caption-primary",
        "voice": "voice-primary",
        "overlay": "video-overlay",
        "output_check": "output-primary",
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
