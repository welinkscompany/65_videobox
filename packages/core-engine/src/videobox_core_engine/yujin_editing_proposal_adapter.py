"""Pure, fail-closed validation for untrusted Yujin editing candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Literal

from pydantic import ValidationError

from videobox_core_engine.filters import FILTER_TYPES
from videobox_core_engine.media_controls import PHOTO_MOTION_CHOICES
from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_HORIZONTALS,
    SHAPE_OVERLAY_MOTION_SET,
    SHAPE_OVERLAY_SIZES,
    SHAPE_OVERLAY_VERTICALS,
)
from videobox_core_engine.transitions import TRANSITION_CATALOG
from videobox_domain_models.caption_fonts import is_installed_caption_font
from videobox_domain_models.yujin_editing_proposals import (
    ApplyMediaOperation,
    ReorderSegmentsOperation,
    SetCaptionFontOperation,
    SetImageOverlayOperation,
    SetPhotoMotionOperation,
    SetPictureCleanupOperation,
    SetSceneLookOperation,
    SetSceneTransitionOperation,
    SetSceneTransformOperation,
    SetSoundCleanupOperation,
    YujinEditingProposal,
    YujinEditingResponse,
)


#: 사진 오버레이가 고를 수 있는 값. **여기에 사본을 두지 않는다** --
#: `overlay_shapes`가 유일한 출처이고, 편집 세션(`_IMAGE_OVERLAY_PRESET_VALUES`)과
#: 화면(`ImageOverlayRequest`)도 같은 표를 본다. 한 벌이 갈라지면 유진이 고른
#: 값이 렌더에서 조용히 사라진다.
_IMAGE_OVERLAY_PRESETS: dict[str, frozenset[str]] = {
    "vertical": SHAPE_OVERLAY_VERTICALS,
    "horizontal": SHAPE_OVERLAY_HORIZONTALS,
    "size": SHAPE_OVERLAY_SIZES,
    "motion": SHAPE_OVERLAY_MOTION_SET,
}

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
    #: 지금 전환이 걸린 장면과 그 종류. **이걸 안 주면 유진이 "전환이 적용되어
    #: 있지 않습니다"라고 답한다** -- 걸려 있는데도(2026-09-06 실측). 음악·
    #: 효과음·화면과 같은 이유로 목록을 준다: 규칙만 글로 적고 목록을 빼면
    #: 모델이 지어내거나 아예 포기한다.
    transitions_by_segment: tuple[tuple[str, str], ...] = ()
    #: 지금 색감이 걸린 장면과 그 종류. 전환과 **똑같은 빈틈**이 있었다
    #: (2026-09-06 실측): `warm`이 걸린 장면을 두고 "색감이 걸려 있지
    #: 않습니다"라고 답했다. 고를 수 있는 목록만 주고 **지금 걸린 것**은
    #: 안 줬기 때문이다.
    looks_by_segment: tuple[tuple[str, str], ...] = ()
    #: 지금 사진 움직임이 걸린 장면과 그 종류. 색감·전환과 **같은 이유**로 준다 --
    #: 목록과 지금 걸린 값은 한 쌍이고, 한쪽만 주면 "원래대로 돌려줘"가 막힌다.
    #: 여기 없는 장면은 "안 고름"이며, 그건 클립마다 알아서 움직인다는 뜻이다.
    photo_motions_by_segment: tuple[tuple[str, str], ...] = ()
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
    #: 지금 자막 글자 크기(px). **이걸 안 알려 주면 "더 크게"에 되묻는다** --
    #: 창작자는 px 숫자를 모르는데 유진이 "크기를 알려주세요"라고 답했다
    #: (2026-09-06 실측). 어디서 출발해 올릴지 알아야 알아서 올릴 수 있다.
    caption_font_size_px: int | None = None
    #: 지금 영상 **위에 얹혀 있는** 사진과 그 프리셋. 전환·색감과 **똑같은
    #: 빈틈**을 막는다: 고를 수 있는 목록만 주고 지금 걸린 것을 안 주면
    #: "사진 좀 위로 올려줘"·"사진 빼줘"에 유진이 "얹은 사진이 없습니다"라고
    #: 답한다 -- 얹혀 있는데도. 값은 사람이 읽는 한 줄이다
    #: (`asset-1(bottom/right/small/fade_in)`).
    image_overlays_by_segment: tuple[tuple[str, str], ...] = ()


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
    operation_targets: set[tuple[str, ...]] = set()
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
            if operation.family is not None and not is_installed_caption_font(operation.family):
                return "caption_font_not_available"
            key = (operation.intent, "all")
        else:
            if operation.segment_id not in current_segment_ids:
                return "segment_not_current"
            key = (operation.intent, operation.segment_id)
            # **한 장면의 음악과 효과음은 서로 다른 칸이다.** 장면만 보고
            # 중복으로 막으면 "이 장면에 잔잔한 음악이랑 종이 넘기는 효과음
            # 같이 넣어줘"가 통째로 거절된다 -- 2026-09-05에 실제로 그랬고,
            # 창작자가 자연스럽게 할 말이다. 같은 칸을 두 번 거는 것은 여전히
            # 막는다(무엇이 남는지 알 수 없어진다).
            media_type = getattr(operation, "media_type", None)
            if media_type is not None:
                key = (operation.intent, operation.segment_id, str(media_type))
        if key in operation_targets:
            return "duplicate_conflicting_operation"
        operation_targets.add(key)
        if isinstance(operation, SetSceneTransitionOperation):
            # 지어낸 전환 이름은 여기서 막는다 -- 색감과 같은 이유다. 렌더러는
            # 표에 없는 이름을 조용히 넘기고, 창작자는 "골랐는데 아무 일도 안
            # 일어났다"를 본다.
            if operation.transition_type is not None and operation.transition_type not in TRANSITION_CATALOG:
                return "scene_transition_not_available"
        if isinstance(operation, SetSceneLookOperation):
            if operation.look not in FILTER_TYPES:
                return "scene_look_not_available"
            if operation.segment_id not in set(context.segment_ids_with_broll):
                return "scene_look_needs_broll"
        if isinstance(operation, SetPhotoMotionOperation):
            # 지어낸 움직임 이름은 여기서 막는다 -- 색감·전환과 같은 이유다.
            # `normalize_media_controls`도 막지만 거기까지 가면 창작자는
            # "적용하지 못했어요"만 본다.
            if operation.motion not in PHOTO_MOTION_CHOICES:
                return "photo_motion_not_available"
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
        if isinstance(operation, SetImageOverlayOperation):
            # **지어낸 프리셋 이름은 여기서 막는다** -- 전환·색감과 같은 자리다.
            # 조용히 기본값으로 좁히면 창작자는 고른 것이 왜 안 되는지 모른다.
            for field_name, allowed in _IMAGE_OVERLAY_PRESETS.items():
                chosen = getattr(operation, field_name)
                if chosen is not None and str(chosen).strip().lower() not in allowed:
                    return "image_overlay_preset_not_available"
            if operation.asset_id not in set(context.approved_asset_ids):
                return "media_asset_not_approved"
            asset_types = dict(context.approved_asset_types)
            # **사진만 얹는다.** 영상·음악을 이 자리에 실으면 렌더러가 한 장짜리
            # 그림으로 읽어 아무것도 안 그린다 -- `apply_media`가 종류를 가리는
            # 것과 같은 이유다.
            if asset_types and asset_types.get(operation.asset_id) != "image":
                return "media_asset_type_mismatch"
        if isinstance(operation, ApplyMediaOperation):
            if operation.asset_id not in set(context.approved_asset_ids):
                return "media_asset_not_approved"
            asset_types = dict(context.approved_asset_types)
            # **사진도 화면 자리에 놓인다**(owner 요청 2026-09-06). 영상과 같은
            # `broll_override`에 실리고, 다른 점은 렌더러가 `-loop 1`로 늘리고
            # 움직임을 얹는다는 것뿐이다. 그래서 새 낱말을 만들지 않는다 --
            # 창작자가 "이 사진 깔아줘"라고 할 때 유진이 굳이 다른 말을 골라야
            # 할 이유가 없다.
            #
            # **느슨하게 푸는 것이 아니다.** 음악을 화면 자리에 놓는 것은 여전히
            # 막힌다(그 반대도).
            expected_asset_types = {
                "broll": {"broll_video", "image"}, "bgm": {"bgm"}, "sfx": {"sfx"},
            }[operation.media_type]
            if asset_types and asset_types.get(operation.asset_id) not in expected_asset_types:
                return "media_asset_type_mismatch"
    return None


def _rejected(reason: str) -> YujinEditingResult:
    return YujinEditingResult(status="rejected", proposal=None, reason=reason)


__all__ = ["YujinEditingContext", "YujinEditingResult", "interpret_yujin_editing_request"]
