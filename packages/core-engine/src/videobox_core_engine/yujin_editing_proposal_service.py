"""Local structured generation for candidate-only editing proposals."""

from __future__ import annotations

from dataclasses import dataclass
import json

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


def _approved_asset_catalogue(context: YujinEditingContext) -> str:
    """`apply_media`가 요구하는 `asset_id`를 모델이 실제로 알 방법이 이것뿐이다.

    코드리뷰(Task 4, 2026-08-26 계획서)로 잡힌 결함 -- 이 목록 없이는 모델이
    `asset_id`를 지어낼 수밖에 없었고, 그 값은 승인된 자산과 우연히 맞을 리
    없어 검증에서 항상 `media_asset_not_approved`로 막혔다. B-roll·음악·
    효과음 교체는 설계상 지원 동작인데도 실제로는 한 번도 성공할 수 없었다.
    """
    asset_types = dict(context.approved_asset_types)
    entries = [f"{asset_id}({asset_types.get(asset_id, '알 수 없음')})" for asset_id in context.approved_asset_ids]
    return f"승인된 자산: {', '.join(entries)}." if entries else "승인된 자산이 없다 -- apply_media를 시도하지 마라."


def _editing_prompt(*, instruction: str, context: YujinEditingContext) -> str:
    example = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "2번 장면을 두 배 빠르게 하는 검토용 편집안을 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": context.session_revision,
            "operations": [{"intent": "set_scene_speed", "segment_id": context.segment_ids[-1], "rate": 2}],
        },
    }
    return (
        "너는 VideoBox의 편집안 작성기다. 이 요청은 저장·실행·적용이 아닌 검토용 후보만 만든다. "
        "반드시 JSON 객체 하나만 출력하고 Markdown, 코드 블록, 설명문을 섞지 마라. "
        "proposal 안에는 현재 장면 ID만 쓰고, base_session_revision은 아래 값과 정확히 같아야 한다. "
        "허용 intent는 set_scene_speed, set_segment_bounds, set_cut_action, reorder_segments, "
        "set_caption_text, apply_media, remove_media뿐이다. 요청이 모호하거나 안전한 후보를 만들 수 없으면 proposal은 null로 둔다. "
        "apply_media의 asset_id는 반드시 아래 승인된 자산 목록에 있는 값만 써야 한다 -- 없는 값을 지어내면 항상 거절된다. "
        f"현재 장면 ID: {', '.join(context.segment_ids)}. 현재 revision: {context.session_revision}. "
        f"{_approved_asset_catalogue(context)} "
        f"정확한 출력 예시: {json.dumps(example, ensure_ascii=False)}. "
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
