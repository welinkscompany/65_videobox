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
        f"현재 장면 ID: {', '.join(context.segment_ids)}. 현재 revision: {context.session_revision}. "
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
