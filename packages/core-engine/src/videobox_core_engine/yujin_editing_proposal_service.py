"""Local structured generation for candidate-only editing proposals."""

from __future__ import annotations

from dataclasses import dataclass

from videobox_core_engine.yujin_editing_proposal_adapter import (
    YujinEditingContext,
    YujinEditingResult,
    interpret_yujin_editing_request,
)
from videobox_provider_interfaces.llm import LLMTaskType


YUJIN_EDITING_RESPONSE_SCHEMA = {"type": "object", "properties": {"schema_version": {"type": "string"}, "reply_text": {"type": "string"}, "proposal": {"type": ["object", "null"]}}, "required": ["schema_version", "reply_text", "proposal"]}


@dataclass(slots=True)
class YujinEditingProposalService:
    runtime: object

    def create(self, *, project_id: str, instruction: str, context: YujinEditingContext) -> YujinEditingResult:
        response = self.runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=("현재 장면 ID만 사용해 검토용 편집안을 JSON으로 제안하세요. 저장하거나 실행하지 마세요. "
                    f"현재 장면: {', '.join(context.segment_ids)}. 요청: {instruction}"),
            response_schema=YUJIN_EDITING_RESPONSE_SCHEMA,
        )
        return interpret_yujin_editing_request(response.output_data, context)
