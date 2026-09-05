"""Pure, fail-closed validation for untrusted Yujin editing candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Literal

from pydantic import ValidationError

from videobox_core_engine.filters import FILTER_TYPES
from videobox_domain_models.caption_fonts import is_installed_caption_font
from videobox_domain_models.yujin_editing_proposals import (
    ApplyMediaOperation,
    ReorderSegmentsOperation,
    SetCaptionFontOperation,
    SetPictureCleanupOperation,
    SetSceneLookOperation,
    SetSceneTransformOperation,
    SetSoundCleanupOperation,
    YujinEditingProposal,
    YujinEditingResponse,
)


_MAX_PAYLOAD_BYTES = 32_768
_UNSAFE_TERMS = (
    "filesystem",
    "file system",
    "network",
    "provider",
    "http://",
    "https://",
    "shell",
    "powershell",
    "curl",
    "api key",
)


@dataclass(frozen=True)
class YujinEditingContext:
    session_id: str
    session_revision: int
    segment_ids: tuple[str, ...]
    approved_asset_ids: tuple[str, ...] = ()
    approved_asset_types: tuple[tuple[str, str], ...] = ()
    #: 자산을 **사람이 아는 말로** 부르는 이름(`01-새벽-바다`, `밝은 인트로 · 22초`).
    #: 없으면 유진은 id만 보고 골라야 하는데, id에는 고를 근거가 하나도 없다.
    approved_asset_labels: tuple[tuple[str, str], ...] = ()
    #: 지금 화면(B-roll)이 깔려 있는 장면들. 색감은 그 위에 얹는 것이라
    #: 화면 없는 장면에는 걸 수 없다 -- 여기서 막지 않으면 적용 단계에서
    #: 터지고, 창작자에게는 "적용하지 못했어요"라는 말만 남는다.
    segment_ids_with_broll: tuple[str, ...] = ()
    #: 지금 음악·효과음이 깔려 있는 장면들. 소리 정리는 깔린 것 위에 거는 것이라
    #: 없는 장면에는 걸 수 없다 -- 색감이 화면을 요구하는 것과 같은 이유다.
    segment_ids_with_bgm: tuple[str, ...] = ()
    segment_ids_with_sfx: tuple[str, ...] = ()
    #: 장면별 **지금 자막 글**. 없으면 유진은 "짧게 다듬어 줘"를 할 수 없다 --
    #: 지금 뭐라고 적혀 있는지 모르는 채로 새 문장을 지어내야 하기 때문이다.
    #: 2026-09-03까지 이 값이 없어서, 자막을 고치라는 요청은 늘 지어낸 문장이었다.
    captions: tuple[tuple[str, str], ...] = ()
    #: 창작자가 **지금 보고 있는** 자막 언어. `None`이면 원본(한국어).
    #: 유진은 이 언어로 보고 이 언어를 고친다 -- 보는 것과 고치는 것이 달라지면
    #: 창작자 눈에는 아무 일도 안 일어난 것처럼 보인다.
    caption_language: str | None = None


@dataclass(frozen=True)
class YujinEditingResult:
    status: Literal["candidate_only", "clarification", "rejected"]
    proposal: YujinEditingProposal | None
    reason: str | None = None
    #: 유진이 실제로 한 말. `clarification`일 때만 채워진다 -- `rejected`는
    #: 우리 쪽 검증(승인 안 된 자산, 낡은 revision 등)이 막은 것이라 모델의
    #: 말이 지금 일어난 일과 안 맞을 수 있다("음악을 골랐어요" 뒤에 그
    #: 자산이 승인 안 돼 거절되는 식) -- 그 경우까지 이 값을 보여주면
    #: 성공한 것처럼 보이는 오해를 만든다(Task 4, 2026-08-26 계획서).
    reply_text: str | None = None


def interpret_yujin_editing_request(
    payload: str | Mapping[str, object], context: YujinEditingContext
) -> YujinEditingResult:
    """Return an unpersisted candidate only when every target is current."""

    raw = _decode_bounded_payload(payload)
    if raw is None or _contains_unsafe_instruction(raw):
        return _rejected("invalid_payload_or_unsafe_instruction")
    if raw.get("proposal") is None and isinstance(raw.get("reply_text"), str):
        return YujinEditingResult(status="clarification", proposal=None, reply_text=raw["reply_text"])
    try:
        response = YujinEditingResponse.model_validate(raw)
    except ValidationError:
        return _rejected("invalid_editing_response")
    if response.proposal is None:
        return YujinEditingResult(status="clarification", proposal=None, reply_text=response.reply_text)
    reason = _validate_current_targets(response.proposal, context)
    return _rejected(reason) if reason is not None else YujinEditingResult(
        status="candidate_only", proposal=response.proposal
    )


def _decode_bounded_payload(payload: str | Mapping[str, object]) -> dict[str, object] | None:
    if isinstance(payload, str):
        if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            return None
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            return None
    elif isinstance(payload, Mapping):
        decoded = dict(payload)
        try:
            if len(json.dumps(decoded, ensure_ascii=False).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
                return None
        except (TypeError, ValueError):
            return None
    else:
        return None
    return decoded if type(decoded) is dict and all(type(key) is str for key in decoded) else None


def _contains_unsafe_instruction(value: object) -> bool:
    if isinstance(value, str):
        folded = value.casefold()
        return any(term in folded for term in _UNSAFE_TERMS)
    if isinstance(value, Mapping):
        return any(_contains_unsafe_instruction(key) or _contains_unsafe_instruction(item) for key, item in value.items())
    if type(value) in (list, tuple):
        return any(_contains_unsafe_instruction(item) for item in value)
    return False


def _validate_current_targets(proposal: YujinEditingProposal, context: YujinEditingContext) -> str | None:
    if proposal.base_session_revision != context.session_revision:
        return "stale_session_revision"
    current_segment_ids = set(context.segment_ids)
    if len(current_segment_ids) != len(context.segment_ids) or not current_segment_ids:
        return "invalid_current_context"
    operation_targets: set[tuple[str, str]] = set()
    for operation in proposal.operations:
        if isinstance(operation, ReorderSegmentsOperation):
            if len(operation.segment_ids) != len(current_segment_ids) or set(operation.segment_ids) != current_segment_ids:
                return "reorder_segments_not_current"
            key = (operation.intent, "all")
        elif isinstance(operation, SetCaptionFontOperation):
            # 자막 글꼴은 **편집본 전체**에 걸린다 -- 장면 번호가 없다.
            # **지어낸 글꼴 이름을 여기서 막는다.** 없는 글꼴은 완성본에서
            # 조용히 다른 글꼴로 떨어진다 -- 화면의 글꼴 칸이 자유 입력이던
            # 시절 실제로 겪은 사고이고, 목록이 아니라 **이 기계에 파일이
            # 있는지**를 보는 것도 같은 이유다(caption_fonts.py 머리말).
            if not is_installed_caption_font(operation.family):
                return "caption_font_not_available"
            key = (operation.intent, "all")
        else:
            if operation.segment_id not in current_segment_ids:
                return "segment_not_current"
            key = (operation.intent, operation.segment_id)
        if key in operation_targets:
            return "duplicate_conflicting_operation"
        operation_targets.add(key)
        if isinstance(operation, SetSceneLookOperation):
            if operation.look not in FILTER_TYPES:
                return "scene_look_not_available"
            if operation.segment_id not in set(context.segment_ids_with_broll):
                return "scene_look_needs_broll"
        if isinstance(operation, (SetPictureCleanupOperation, SetSceneTransformOperation)):
            # 화면 위에 얹는 조정이다. 색감과 같은 자리에서 막는다.
            if operation.segment_id not in set(context.segment_ids_with_broll):
                return "scene_look_needs_broll"
        if isinstance(operation, SetSoundCleanupOperation):
            available = context.segment_ids_with_bgm if operation.media_type == "bgm" else context.segment_ids_with_sfx
            if operation.segment_id not in set(available):
                return "sound_cleanup_needs_media"
        if isinstance(operation, ApplyMediaOperation):
            if operation.asset_id not in set(context.approved_asset_ids):
                return "media_asset_not_approved"
            asset_types = dict(context.approved_asset_types)
            expected_asset_type = {"broll": "broll_video", "bgm": "bgm", "sfx": "sfx"}[operation.media_type]
            if asset_types and asset_types.get(operation.asset_id) != expected_asset_type:
                return "media_asset_type_mismatch"
    return None


def _rejected(reason: str) -> YujinEditingResult:
    return YujinEditingResult(status="rejected", proposal=None, reason=reason)


__all__ = ["YujinEditingContext", "YujinEditingResult", "interpret_yujin_editing_request"]
