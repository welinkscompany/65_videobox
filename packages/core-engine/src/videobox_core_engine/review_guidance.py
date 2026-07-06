from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from videobox_core_engine.canonical_review_status import (
    canonical_review_status as _canonical_review_status,
)
from videobox_core_engine.gemini_runtime import GeminiStructuredGenerationError
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_core_engine.prompt_pending_recommendation import (
    canonical_prompt_decision_state as _canonical_decision_state,
    canonical_prompt_recommendation_type as _canonical_recommendation_type,
    canonical_prompt_review_flag_code as _canonical_review_flag_code,
    canonical_prompt_review_flag_message as _canonical_review_flag_message,
    has_canonical_review_flag_identity,
    has_canonical_pending_recommendation_identity,
    normalize_prompt_review_flag_row,
    normalize_prompt_pending_recommendation_row,
    VALID_PROMPT_RECOMMENDATION_TYPES,
    VALID_PROMPT_REVIEW_FLAG_CODES,
)
from videobox_core_engine.provider_trace import build_provider_trace, response_provider_trace, with_final_provider
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


def _is_prompt_blocking_pending_recommendation(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if not has_canonical_pending_recommendation_identity(
        item,
        canonical_recommendation_type=_canonical_recommendation_type,
        valid_recommendation_types=VALID_PROMPT_RECOMMENDATION_TYPES,
    ):
        return False
    decision_state = _canonical_decision_state(item.get("decision_state"))
    if decision_state and decision_state != "pending":
        return False
    if _normalize_boolish(item.get("auto_apply_allowed", False)) and not _normalize_boolish(
        item.get("review_required", False)
    ):
        return False
    return True

class StructuredReviewGuidanceRuntime(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: Any | None = None,
    ) -> Any:
        """Generate structured operator guidance."""


class ReviewGuidanceBuilder(Protocol):
    def build(
        self,
        *,
        project_id: str,
        review_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """Return operator-facing review guidance for a snapshot."""


@dataclass(slots=True)
class HeuristicReviewGuidanceBuilder(ReviewGuidanceBuilder):
    def build(
        self,
        *,
        project_id: str,
        review_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        del project_id
        review_flags = [
            flag
            for flag in review_snapshot.get("review_flags", [])
            if isinstance(flag, dict)
            and has_canonical_review_flag_identity(
                flag,
                canonical_review_flag_code=_canonical_review_flag_code,
                valid_review_flag_codes=VALID_PROMPT_REVIEW_FLAG_CODES,
            )
        ]
        pending_recommendations = [
            item
            for item in review_snapshot.get("pending_recommendations", [])
            if _is_prompt_blocking_pending_recommendation(item)
        ]
        review_status = _canonical_review_status(review_snapshot.get("review_status"), default="draft")

        if review_flags or pending_recommendations:
            action_items: list[str] = []
            for flag in review_flags:
                message = str(flag.get("message", "")).strip()
                if message:
                    action_items.append(message)
                    continue
                if _canonical_review_flag_code(flag.get("code")) and str(flag.get("segment_id") or "").strip():
                    action_items.append(_canonical_review_flag_message(flag.get("message")))
            for item in pending_recommendations:
                reason = str(item.get("reason", "")).strip()
                if reason:
                    action_items.append(reason)
                    continue
                if (
                    str(item.get("recommendation_id") or "").strip()
                    and str(item.get("target_segment_id") or "").strip()
                    and _canonical_recommendation_type(item.get("recommendation_type"))
                ):
                    action_items.append("Operator review required before approval or output.")
            if not action_items:
                action_items.append("Resolve review blockers before approval.")
            return {
                "summary": "Review is blocked until the flagged items are resolved.",
                "action_items": action_items[:5],
                "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
            }

        if review_status == "approved":
            return {
                "summary": "Timeline review is approved and outputs can be generated.",
                "action_items": ["Generate subtitles, preview, or export from the approved timeline."],
                "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
            }

        return {
            "summary": "Timeline is ready for approval before output generation.",
            "action_items": ["Approve the timeline review to unlock subtitles, preview, and export."],
            "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
        }


@dataclass(slots=True)
class LocalFirstReviewGuidanceBuilder(ReviewGuidanceBuilder):
    runtime_service: StructuredReviewGuidanceRuntime
    fallback_builder: ReviewGuidanceBuilder = field(default_factory=HeuristicReviewGuidanceBuilder)

    def build(
        self,
        *,
        project_id: str,
        review_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        fallback_guidance = self.fallback_builder.build(
            project_id=project_id,
            review_snapshot=review_snapshot,
        )
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.OPERATOR_COPY,
                prompt=self._build_prompt(review_snapshot=review_snapshot),
                response_schema={
                    "type": "object",
                    "required": ["summary", "action_items"],
                    "properties": {
                        "summary": {"type": "string"},
                        "action_items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )
            summary = response.output_data.get("summary")
            action_items = response.output_data.get("action_items")
            if not isinstance(summary, str) or not summary.strip():
                fallback_guidance["provider_trace"] = with_final_provider(
                    response_provider_trace(response),
                    final_provider="heuristic_fallback",
                    additional_reason="unexpected_runtime_failure",
                )
                return fallback_guidance
            if not isinstance(action_items, list):
                fallback_guidance["provider_trace"] = with_final_provider(
                    response_provider_trace(response),
                    final_provider="heuristic_fallback",
                    additional_reason="unexpected_runtime_failure",
                )
                return fallback_guidance

            cleaned_action_items = [
                str(item).strip()
                for item in action_items
                if isinstance(item, str) and item.strip()
            ]
            if not cleaned_action_items:
                fallback_guidance["provider_trace"] = with_final_provider(
                    response_provider_trace(response),
                    final_provider="heuristic_fallback",
                    additional_reason="unexpected_runtime_failure",
                )
                return fallback_guidance

            return {
                "summary": summary.strip(),
                "action_items": cleaned_action_items[:5],
                "provider_trace": response_provider_trace(response),
            }
        except Exception as exc:
            fallback_guidance["provider_trace"] = with_final_provider(
                getattr(exc, "provider_trace", build_provider_trace(final_provider="heuristic_fallback")),
                final_provider="heuristic_fallback",
                additional_reason="unexpected_runtime_failure" if not isinstance(
                    exc,
                    (GeminiStructuredGenerationError, LLMProviderError, LocalFirstStructuredGenerationError),
                ) else None,
            )
            return fallback_guidance

    def _build_prompt(self, *, review_snapshot: dict[str, Any]) -> str:
        review_status = _canonical_review_status(review_snapshot.get("review_status"), default="draft")
        review_flags = self._prompt_review_flags(review_snapshot.get("review_flags", []))
        pending_recommendations = self._prompt_pending_recommendations(
            review_snapshot.get("pending_recommendations", [])
        )
        segments = review_snapshot.get("segments", [])
        return (
            "Write concise operator-facing review guidance for this video timeline.\n"
            f"Review status: {review_status}\n"
            f"Flag count: {len(review_flags)}\n"
            f"Pending recommendation count: {len(pending_recommendations)}\n"
            f"Segments needing attention: {self._segments_needing_attention(segments)}\n"
            f"Review flags: {review_flags}\n"
            f"Pending recommendations: {pending_recommendations}\n"
            "Return a short summary and a list of concrete next action items."
        )

    def _segments_needing_attention(self, segments: list[dict[str, Any]]) -> list[str]:
        return [
            str(segment.get("segment_id") or "").strip()
            for segment in segments
            if isinstance(segment, dict)
            if _normalize_boolish(segment.get("review_required"))
            and str(segment.get("segment_id") or "").strip()
        ]

    def _prompt_review_flags(
        self,
        review_flags: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prompt_rows: list[dict[str, Any]] = []
        for flag in review_flags:
            if not isinstance(flag, dict):
                continue
            if not has_canonical_review_flag_identity(
                flag,
                canonical_review_flag_code=_canonical_review_flag_code,
                valid_review_flag_codes=VALID_PROMPT_REVIEW_FLAG_CODES,
            ):
                continue
            prompt_rows.append(
                normalize_prompt_review_flag_row(
                    flag,
                    canonical_review_flag_code=_canonical_review_flag_code,
                    canonical_review_flag_message=_canonical_review_flag_message,
                )
            )
        return prompt_rows

    def _prompt_pending_recommendations(
        self,
        pending_recommendations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prompt_rows: list[dict[str, Any]] = []
        for item in pending_recommendations:
            if not _is_prompt_blocking_pending_recommendation(item):
                continue
            prompt_rows.append(
                normalize_prompt_pending_recommendation_row(
                    item,
                    canonical_recommendation_type=_canonical_recommendation_type,
                    canonical_reason=_canonical_review_flag_message,
                    canonical_decision_state=_canonical_decision_state,
                )
            )
        return prompt_rows
