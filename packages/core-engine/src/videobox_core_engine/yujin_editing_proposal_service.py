"""Local structured generation for candidate-only editing proposals."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES
from videobox_core_engine.transitions import TRANSITION_CATALOG
from videobox_core_engine.filters import FILTER_CATALOG
from videobox_domain_models.caption_fonts import caption_font_catalog
from videobox_domain_models.caption_style import (
    DEFAULT_CAPTION_FONT_SIZE_PX,
    MAX_CAPTION_FONT_SIZE_PX,
    MIN_CAPTION_FONT_SIZE_PX,
)
from videobox_core_engine.yujin_editing_proposal_adapter import (
    YujinEditingContext,
    YujinEditingResult,
    interpret_yujin_editing_request,
)
from videobox_provider_interfaces.llm import LLMTaskType


_EDITING_OPERATION_SCHEMA = {
    "oneOf": [
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_scene_speed"}, "segment_id": {"type": "string"}, "rate": {"enum": [1, 1.5, 2]}}, "required": ["intent", "segment_id", "rate"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_segment_bounds"}, "segment_id": {"type": "string"}, "start_sec": {"type": "number"}, "end_sec": {"type": "number"}}, "required": ["intent", "segment_id", "start_sec", "end_sec"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_cut_action"}, "segment_id": {"type": "string"}, "action": {"enum": ["exclude", "restore"]}}, "required": ["intent", "segment_id", "action"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "reorder_segments"}, "segment_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["intent", "segment_ids"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_caption_text"}, "segment_id": {"type": "string"}, "text": {"type": "string"}}, "required": ["intent", "segment_id", "text"]},
        # 글꼴은 **편집본 전체**에 걸리므로 segment_id를 받지 않는다.
        # 글꼴 이름과 크기는 **각각 따로** 실을 수 있다 -- "더 큰 걸로"라고만 하면
        # 크기만 싣는다. 둘 다 안 실으면 검증이 막는다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_caption_font"}, "family": {"type": "string"}, "size_px": {"type": "integer", "minimum": MIN_CAPTION_FONT_SIZE_PX, "maximum": MAX_CAPTION_FONT_SIZE_PX}}, "required": ["intent"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_scene_look"}, "segment_id": {"type": "string"}, "look": {"enum": sorted(FILTER_CATALOG)}}, "required": ["intent", "segment_id", "look"]},
        # 전환은 **이 장면으로 넘어올 때** 쓴다. `transition_type: null`이면 뺀다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_scene_transition"}, "segment_id": {"type": "string"}, "transition_type": {"type": ["string", "null"], "enum": [*sorted(TRANSITION_CATALOG), None]}, "duration_sec": {"type": "number", "minimum": 0.1, "maximum": 5}}, "required": ["intent", "segment_id"]},
        # 켜고 끄는 것들. **말한 것만 실으라고** 하려고 required를 최소로 둔다 --
        # "흔들림만 잡아 줘"에 노이즈 값까지 채우게 하면 이미 켜 둔 것을 끈다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_picture_cleanup"}, "segment_id": {"type": "string"}, "stabilize": {"type": "boolean"}, "reduce_noise": {"type": "boolean"}}, "required": ["intent", "segment_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_sound_cleanup"}, "segment_id": {"type": "string"}, "media_type": {"enum": ["bgm", "sfx"]}, "normalize_loudness": {"type": "boolean"}, "denoise": {"type": "boolean"}}, "required": ["intent", "segment_id", "media_type"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_scene_transform"}, "segment_id": {"type": "string"}, "zoom": {"type": "number"}, "position_x_percent": {"type": "number"}, "position_y_percent": {"type": "number"}, "rotation_deg": {"type": "number"}}, "required": ["intent", "segment_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "apply_media"}, "segment_id": {"type": "string"}, "media_type": {"enum": ["broll", "bgm", "sfx"]}, "asset_id": {"type": "string"}}, "required": ["intent", "segment_id", "media_type", "asset_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "remove_media"}, "segment_id": {"type": "string"}, "media_type": {"enum": ["broll", "bgm", "sfx"]}}, "required": ["intent", "segment_id", "media_type"]},
    ]
}


def _editing_response_schema(session_revision: int) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": "videobox.yujin-editing-response.v1"},
            "reply_text": {"type": "string"},
            "proposal": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": {
                    "proposal_id": {"type": "string"},
                    "base_session_revision": {"const": session_revision},
                    "operations": {"type": "array", "minItems": 1, "maxItems": 16, "items": _EDITING_OPERATION_SCHEMA},
                },
                "required": ["proposal_id", "base_session_revision", "operations"],
            },
        },
        "required": ["schema_version", "reply_text", "proposal"],
    }


#: 목록이 길어지면 프롬프트가 커지고 모델이 뒤쪽을 안 본다. 자산이 아주 많은
#: 프로젝트에서도 프롬프트가 감당할 크기로 남게 상한을 둔다.
_ASSET_CATALOGUE_LIMIT = 40


def _scene_look_catalogue(context: YujinEditingContext) -> str:
    """모델이 `look` 값을 알 방법이 이것뿐이다.

    `apply_media`의 자산 목록과 같은 이유다(아래 함수 주석 참고) -- 목록 없이는
    코드를 지어낼 수밖에 없고, 지어낸 값은 검증에서 항상 막힌다. 화면에 보이는
    한국어 이름표를 같이 줘야 "따뜻하게 해 줘"를 `warm`으로 옮길 수 있다.
    """
    looks = ", ".join(f"{key}({value['label']})" for key, value in sorted(FILTER_CATALOG.items()))
    if not context.segment_ids_with_broll:
        return f"고를 수 있는 색감: {looks}. 다만 지금은 화면이 깔린 장면이 없어 색감을 걸 수 없다."
    return (
        f"고를 수 있는 색감: {looks}. "
        f"색감은 화면이 깔린 장면에만 걸 수 있다 -- 그런 장면: {', '.join(context.segment_ids_with_broll)}. "
        # **지금 걸린 것도 준다.** 고를 수 있는 목록만 주면 "원래대로 돌려줘"에
        # "색감이 걸려 있지 않습니다"라고 답한다 -- 걸려 있는데도(2026-09-06 실측).
        f"지금 색감이 걸린 장면: {', '.join(f'{sid}({look})' for sid, look in context.looks_by_segment) or '없음'}."
    )


def _scene_transition_catalogue() -> str:
    """고를 수 있는 전환. **이름을 지어내지 못하게** 표를 그대로 준다.

    색감과 같은 이유다 -- 표에 없는 이름은 렌더러가 조용히 넘기고, 창작자는
    "골랐는데 아무 일도 안 일어났다"를 본다.
    """
    names = ", ".join(f"{key}({value['label']})" for key, value in sorted(TRANSITION_CATALOG.items()))
    return (
        f"고를 수 있는 전환: {names}. "
        "전환은 **그 장면으로 넘어올 때** 걸리므로 뒤쪽 장면의 segment_id를 쓴다. "
        "빼려면 transition_type을 null로 둔다."
    )


def _caption_font_catalogue(context: YujinEditingContext | None = None) -> str:
    """모델이 고를 수 있는 글꼴 이름을 알 방법이 이것뿐이다.

    색감·자산 목록과 같은 이유다 -- 목록 없이는 이름을 지어낼 수밖에 없고,
    지어낸 이름은 `caption_font_not_available`로 항상 막힌다. 화면에 보이는
    한국어 이름표를 같이 줘야 "손글씨로 바꿔 줘"를 옮길 수 있다.

    목록은 **이 기계에 파일이 있는 글꼴만**이다(`caption_font_catalog`).
    """
    fonts = caption_font_catalog()
    if not fonts:
        return "이 기계에 쓸 수 있는 자막 글꼴이 없어 글꼴은 바꿀 수 없다."
    names = ", ".join(f"{item['family']}({item['label']}, {item['group']})" for item in fonts)
    return (
        f"고를 수 있는 자막 글꼴: {names}. "
        "글꼴은 편집본 전체에 걸린다 -- set_caption_font에는 장면 번호를 싣지 않는다. "
        # **크기만 바꾸는 길을 열어 둔다**(2026-09-06). 이 말이 없으면 "글꼴 좀 더
        # 큰 걸로"에 유진이 되묻는다 -- 화면에서는 되는 일인데도.
        f"지금 자막 글자 크기는 {(context.caption_font_size_px if context and context.caption_font_size_px else DEFAULT_CAPTION_FONT_SIZE_PX)}px이고 "
        f"size_px로 바꾼다({MIN_CAPTION_FONT_SIZE_PX}~{MAX_CAPTION_FONT_SIZE_PX}). "
        # **되묻지 말라고 못박는다.** 창작자는 px 숫자를 모른다 -- "더 크게"에
        # "크기를 알려주세요"라고 답하면 말로 고치는 길이 막힌 것과 같다
        # (2026-09-06 실측).
        "\"더 크게\"·\"작게\"처럼 정도만 말하면 **되묻지 말고** 지금 값에서 한 단계 "
        "옮겨라(대략 1.25배, 범위 밖으로 나가면 끝값으로). "
        "\"더 크게\"처럼 크기만 말하면 size_px만 싣고 family는 비운다 -- 이름을 채우면 "
        "창작자가 맞춰 둔 글꼴이 조용히 바뀐다."
    )


def _approved_asset_catalogue(context: YujinEditingContext) -> str:
    """`apply_media`가 요구하는 `asset_id`를 모델이 실제로 알 방법이 이것뿐이다.

    코드리뷰(Task 4, 2026-08-26 계획서)로 잡힌 결함 -- 이 목록 없이는 모델이
    `asset_id`를 지어낼 수밖에 없었고, 그 값은 승인된 자산과 우연히 맞을 리
    없어 검증에서 항상 `media_asset_not_approved`로 막혔다. B-roll·음악·
    효과음 교체는 설계상 지원 동작인데도 실제로는 한 번도 성공할 수 없었다.
    """
    asset_types = dict(context.approved_asset_types)
    labels = dict(context.approved_asset_labels)
    entries = []
    for asset_id in context.approved_asset_ids[:_ASSET_CATALOGUE_LIMIT]:
        label = labels.get(asset_id, "").strip()
        # **목록에 적는 종류는 `apply_media`의 `media_type`에 그대로 쓸 이름이어야
        # 한다.** 음악(bgm)과 효과음(sfx)은 둘이 같아서 여태 드러나지 않았는데,
        # 영상만 저장 이름이 `broll_video`고 써야 할 이름은 `broll`이다. 다른
        # 이름을 보여 주면 모델이 그대로 쓰고 스키마에서 막힌다 -- 2026-09-05에
        # 자료실 영상 후보 8개를 보내 주고도 유진이 "승인된 자산 목록에 없다"고
        # 답한 마지막 겹이 이것이었다.
        kind = {"broll_video": "broll"}.get(str(asset_types.get(asset_id, "")), asset_types.get(asset_id, "알 수 없음"))
        entries.append(f"{asset_id}({kind}, {label})" if label else f"{asset_id}({kind})")
    if not entries:
        return "승인된 자산이 없다 -- apply_media를 시도하지 마라."
    return (
        f"승인된 자산: {', '.join(entries)}. "
        "괄호 안의 이름과 태그를 보고 **장면에 어울리는 것**을 골라라 -- 목록의 첫 번째를 기계적으로 집지 마라."
    )


#: 프롬프트에 보여 줄 자막 수의 상한. 자산 목록(40)과 같은 이유다 -- 목록이
#: 길어지면 모델이 뒤쪽을 안 본다. 실측(2026-09-03): 창작자의 실제 대본은
#: 243문단이고 그대로 실으면 자막만 11,000자가 넘는다.
_CAPTION_CATALOGUE_LIMIT = 40


def _mentioned_scene_numbers(instruction: str) -> list[int]:
    """창작자가 말한 장면 번호. `3번 장면`, `12번 자막` 같은 말에서 뽑는다.

    **말한 장면은 상한과 상관없이 반드시 보여 준다.** 안 그러면 백 장면짜리
    영상에서 "200번 장면 자막 줄여 줘"가 통하지 않는다 -- 목록에 없는 장면을
    다듬으라고 하면 유진은 지어낼 수밖에 없고, 그게 바로 방금 고친 결함이다.
    """
    return [int(found) for found in re.findall(r"(\d{1,4})\s*번", instruction)]


def _caption_catalogue(context: YujinEditingContext, instruction: str) -> str:
    """장면별 지금 자막. **보여 주지 않으면 다듬을 수 없다.**

    2026-09-03까지 이걸 안 줬다. 그래서 "3번 장면 자막을 짧게 다듬어 줘"라는
    요청에 유진은 지금 뭐라고 적혀 있는지 모르는 채로 새 문장을 지어냈다.

    창작자가 보고 있는 언어로 보여 준다 -- 영어를 보고 있으면 영어를 보여 주고
    영어를 고친다. 보는 것과 고치는 것이 다르면 창작자 눈에는 아무 일도 안
    일어난 것처럼 보인다.
    """
    if not context.captions:
        return "자막이 있는 장면이 없다."
    numbers = {segment_id: index for index, segment_id in enumerate(context.segment_ids, start=1)}
    mentioned = set(_mentioned_scene_numbers(instruction))
    # 말한 장면을 먼저 넣고, 남는 자리를 앞에서부터 채운다.
    ordered = sorted(
        context.captions,
        key=lambda item: (numbers.get(item[0], 10**6) not in mentioned, numbers.get(item[0], 10**6)),
    )
    shown_pairs = ordered[:_CAPTION_CATALOGUE_LIMIT]
    shown = ", ".join(
        f"{numbers.get(segment_id, '?')}번 자막=\"{text}\""
        for segment_id, text in sorted(shown_pairs, key=lambda item: numbers.get(item[0], 10**6))
    )
    language = SUPPORTED_CAPTION_LANGUAGES.get(context.caption_language or "", "원본")
    hidden = len(context.captions) - len(shown_pairs)
    # 안 보여 준 장면이 있으면 **그렇게 말한다.** 모르는 자막을 지어내는 것보다
    # "그 장면은 안 보인다"고 말하는 편이 낫다.
    tail = (
        f" 자막이 많아 {hidden}개 장면은 여기 없다 -- 목록에 없는 장면을 다듬으라고 하면"
        " 지어내지 말고 그 번호를 말해 달라고 답하라."
        if hidden > 0 else ""
    )
    return (
        f"지금 자막({language}): {shown}.{tail} "
        "자막을 다듬으라고 하면 **이 글을 고쳐서** set_caption_text로 낸다 -- "
        f"새로 지어내지 말고 {language} 그대로 다듬는다."
    )


def _editing_prompt(*, instruction: str, context: YujinEditingContext) -> str:
    success_example = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "2번 장면을 두 배 빠르게 하는 검토용 편집안을 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": context.session_revision,
            "operations": [{"intent": "set_scene_speed", "segment_id": context.segment_ids[-1], "rate": 2}],
        },
    }
    # 실측(2026-08-30)으로 잡힌 결함: 허용 intent 밖의 요청에 proposal을 null로
    # 정확히 뒀으면서도, reply_text는 예시 문장의 "만들었어요" 어투를 그대로 베껴
    # 편집이 이미 성공한 것처럼 말했다. `interpret_yujin_editing_request`는 이
    # reply_text를 그대로 화면에 보여준다(§ clarification) -- 예시가 성공 케이스
    # 하나뿐이라 모델이 null일 때도 같은 어투를 흉내 낼 근거가 있었다. 실패
    # 케이스 예시를 나란히 보여줘 모델이 베낄 어투를 분리한다.
    #
    # **예시를 갈아 끼웠다(2026-09-01).** 예전 예시는 "색감 보정을 지원하지
    # 않아요"였는데 그날 색감(`set_scene_look`)을 지원 목록에 넣었다 -- 그대로
    # 두면 방금 만든 기능을 거절하라고 가르치는 예시가 된다.
    #
    # **또 갈아 끼웠다(2026-09-06).** 그때 고른 예시가 "자막 글꼴은 못 바꾼다"
    # 였는데 2026-09-05에 글꼴을, 2026-09-06에 크기를 지원 목록에 넣었다 --
    # **같은 함정에 두 번 걸렸다.** 주석에 "앞으로도 그럴 것"이라고 적어 둔 것이
    # 무색해졌다. 그래서 이번에는 **안 만들기로 명시 결정된 것**을 고른다
    # (`decisions/2026-09-01-capcut-ai-feature-triage.ko.md`: 전문 색보정 넷은
    # 만들지 않는다). 이 예시를 바꿀 일이 생기면 그 결정부터 다시 봐라.
    no_proposal_example = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "지금 대화 편집으로는 밝기·대비 같은 전문 색보정을 할 수 없어요. 장면 색감은 골라 드릴 수 있어요.",
        "proposal": None,
    }
    return (
        "너는 VideoBox의 편집안 작성기다. 이 요청은 저장·실행·적용이 아닌 검토용 후보만 만든다. "
        "반드시 JSON 객체 하나만 출력하고 Markdown, 코드 블록, 설명문을 섞지 마라. "
        "proposal 안에는 현재 장면 ID만 쓰고, base_session_revision은 아래 값과 정확히 같아야 한다. "
        # **이름만 늘어놓으면 무엇을 하는 항목인지 모른다.** "이 장면 앞부분 3초
        # 잘라줘"에 유진이 `set_scene_speed`(배속)를 골랐다 -- 자르기는
        # `set_segment_bounds`인데 이름에서 그것을 읽어 내지 못한 것이다
        # (2026-09-06 실측). 헷갈리기 쉬운 것에만 뜻을 붙인다.
        "허용 intent는 set_scene_speed(배속), "
        "set_segment_bounds(장면의 시작·끝 시각을 옮긴다 -- \"앞부분 3초 잘라줘\"가 이것이다), "
        "set_cut_action(장면을 쓸지 뺄지), reorder_segments(장면 순서), "
        "set_caption_font(자막 글꼴·크기), "
        "set_caption_text(자막 글), set_scene_look(색감), set_picture_cleanup(손떨림·화면 노이즈), "
        "set_sound_cleanup(소리 크기 맞추기·잡음 줄이기), set_scene_transform(확대·위치·기울이기), "
        "set_scene_transition(장면이 넘어올 때의 전환 -- \"전환 넣어줘\"가 이것이다), "
        "apply_media(영상·음악·효과음을 깐다), "
        "remove_media(깔아 둔 영상·음악·효과음을 뺀다 -- \"음악 빼줘\"가 이것이다)뿐이다. 요청이 모호하거나 안전한 후보를 만들 수 없으면 proposal은 null로 둔다. "
        # 실사용(2026-09-01)으로 잡힌 결함: "3번째 장면을 빼줘"를 `remove_media`로
        # 읽어 그 장면에 깔아 둔 B-roll만 지웠다. 창작자가 뜻한 것은 장면 자체를
        # 완성본에서 빼는 것이었다. 한국어 "빼다"는 둘 다 되므로 어느 쪽인지를
        # 여기서 못박는다 -- 대화 편집이 곧바로 적용되는 지금은 잘못 읽으면
        # 되돌리기까지 가야 한다.
        "'장면을 빼줘/지워줘/없애줘'처럼 **장면 자체**를 빼라는 말은 set_cut_action(action=exclude)이다. "
        "remove_media는 '이 장면의 영상만 빼줘', '배경 음악만 빼줘'처럼 **그 장면에 깔아 둔 미디어**를 지목했을 때만 쓴다. "
        "proposal이 null이면 reply_text에 '만들었다/적용했다/바꿨다'처럼 편집이 이미 일어난 것으로 쓰지 않는다 -- "
        "왜 후보를 못 만드는지 설명하거나 필요한 정보를 되묻는 문장만 쓴다. "
        "apply_media의 asset_id는 반드시 아래 승인된 자산 목록에 있는 값만 써야 한다 -- 없는 값을 지어내면 항상 거절된다. "
        # **번호를 세어 주지 않으면 유진이 센다. 그리고 틀린다.**
        # 실측(2026-09-02): id를 나열만 하고 "2번 장면에 음악을 넣어 줘"라고 했더니
        # 3번 장면에 넣었다. 창작자는 늘 번호로 부르고(화면도 `2번 장면`으로 쓴다)
        # 자리를 세는 일을 모델에게 시킬 이유가 없다. 짝을 지어 준다.
        f"현재 장면: {', '.join(f'{index}번 장면={segment_id}' for index, segment_id in enumerate(context.segment_ids, start=1))}. "
        f"창작자가 말하는 번호는 이 표로 옮긴다 -- 자리를 세지 마라. "
        f"현재 revision: {context.session_revision}. "
        f"{_caption_catalogue(context, instruction)} "
        f"{_approved_asset_catalogue(context)} "
        f"{_scene_look_catalogue(context)} "
        f"{_scene_transition_catalogue()} "
        f"{_caption_font_catalogue(context)} "
        # 이 셋도 화면이 깔린 장면에만 걸 수 있다(색감과 같은 이유). 소리 정리는
        # 그 장면에 음악·효과음이 있어야 한다.
        "손떨림 보정·화면 노이즈는 set_picture_cleanup, 확대·위치·기울이기는 set_scene_transform이고 "
        "둘 다 화면이 깔린 장면에만 걸 수 있다. 소리 크기 맞추기·잡음 줄이기는 set_sound_cleanup이며 "
        "그 장면에 깔린 음악(bgm)이나 효과음(sfx)을 media_type으로 지목해야 한다 -- "
        # **asset_id를 찾아 헤매지 않게 못박는다**(2026-09-06 실측). "음악 소리
        # 크기 좀 맞춰줘"에 유진이 "깔린 음악의 asset_id를 모른다"며 되물었다.
        # 소리 정리는 이미 깔린 것에 거는 일이라 무엇이 깔렸는지 알 필요가 없다.
        "**asset_id는 싣지 않는다**(무엇이 깔렸는지 몰라도 된다). "
        # **켜고 끄는 칸을 하나도 안 실으면 거절된다**(2026-09-06 실측:
        # "음악 소리 크기 좀 맞춰줘"가 `invalid_editing_response`였다). JSON
        # 스키마는 required에 못 적는 조건이라 -- 둘 중 하나만 있으면 되므로 --
        # 말로 못박는다. 안 적으면 모델이 둘 다 빼고 보내고, 창작자에게는
        # "안 됐어요"만 남는다.
        "이 셋(set_picture_cleanup, set_sound_cleanup, set_scene_transform)은 **바꿀 칸을 "
        "적어도 하나 실어야 한다** -- set_picture_cleanup은 stabilize나 reduce_noise, "
        "set_sound_cleanup은 normalize_loudness나 denoise, set_scene_transform은 "
        "scale·offset·rotation 중 하나. 하나도 없으면 아무것도 안 바뀌므로 거절된다. "
        # **어느 장면에 걸 수 있는지 목록으로 준다.** 색감에서 세운 규칙이고,
        # 규칙만 글로 적고 목록을 빼먹으면 모델이 지어내거나 아예 포기한다 --
        # 2026-09-02 실측에서 소리 정리가 그렇게 거절됐다.
        f"지금 전환이 걸린 장면: {', '.join(f'{sid}({kind})' for sid, kind in context.transitions_by_segment) or '없음'}. "
        f"음악이 깔린 장면: {', '.join(context.segment_ids_with_bgm) or '없음'}. "
        f"효과음이 깔린 장면: {', '.join(context.segment_ids_with_sfx) or '없음'}. "
        # **이 두 줄은 소리 정리에만 쓰는 목록이다.** 그 말을 안 적었더니 모델이
        # 일반 규칙으로 읽었다 -- 2026-09-05 실측에서 빈 장면에 "휙 하는 효과음
        # 넣어줘"라고 하면 "먼저 영상이나 배경음악이 깔려 있어야 한다"며 되물었다.
        # 새 프로젝트의 장면은 대부분 비어 있으므로 사실상 효과음을 못 넣는다.
        "위 두 줄은 **소리 정리에만** 쓰는 목록이다. 음악이나 효과음을 새로 까는 "
        "apply_media는 **빈 장면에도 그냥 된다** -- 화면이나 다른 소리가 먼저 있을 필요가 없다. "
        "**창작자가 말한 칸만 싣는다** -- 안 물어본 칸을 채우면 이미 켜 둔 것을 끄게 된다. "
        f"proposal이 있을 때 출력 예시: {json.dumps(success_example, ensure_ascii=False)}. "
        f"proposal이 없을 때 출력 예시: {json.dumps(no_proposal_example, ensure_ascii=False)}. "
        f"창작자 요청: {instruction}"
    )


@dataclass(slots=True)
class YujinEditingProposalService:
    runtime: object

    def create(self, *, project_id: str, instruction: str, context: YujinEditingContext) -> YujinEditingResult:
        response = self.runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=_editing_prompt(instruction=instruction, context=context),
            response_schema=_editing_response_schema(context.session_revision),
        )
        return interpret_yujin_editing_request(response.output_data, context)
