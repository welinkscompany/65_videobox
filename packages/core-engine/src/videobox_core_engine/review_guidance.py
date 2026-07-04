from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from videobox_core_engine.gemini_runtime import GeminiStructuredGenerationError
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_core_engine.provider_trace import build_provider_trace, response_provider_trace, with_final_provider
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    if isinstance(value, bool):
        return value
    return False


def _canonical_review_status(value: object) -> str:
    return str(value or "draft").strip().lower() or "draft"


def _canonical_recommendation_type(value: object) -> str:
    return str(value or "").strip().lower()


def _canonical_review_flag_code(value: object) -> str:
    return str(value or "").strip().lower()


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
        review_flags = review_snapshot.get("review_flags", [])
        pending_recommendations = review_snapshot.get("pending_recommendations", [])
        review_status = _canonical_review_status(review_snapshot.get("review_status"))

        if review_flags or pending_recommendations:
            action_items = [
                str(flag.get("message", "")).strip()
                for flag in review_flags
                if str(flag.get("message", "")).strip()
            ]
            action_items.extend(
                str(item.get("reason", "")).strip()
                for item in pending_recommendations
                if str(item.get("reason", "")).strip()
            )
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
        review_status = _canonical_review_status(review_snapshot.get("review_status"))
        review_flags = review_snapshot.get("review_flags", [])
        pending_recommendations = review_snapshot.get("pending_recommendations", [])
        segments = review_snapshot.get("segments", [])
        return (
            "Write concise operator-facing review guidance for this video timeline.\n"
            f"Review status: {review_status}\n"
            f"Flag count: {len(review_flags)}\n"
            f"Pending recommendation count: {len(pending_recommendations)}\n"
            f"Segments needing attention: {self._segments_needing_attention(segments)}\n"
            f"Review flags: {self._prompt_review_flags(review_flags)}\n"
            f"Pending recommendations: {self._prompt_pending_recommendations(pending_recommendations)}\n"
            "Return a short summary and a list of concrete next action items."
        )

    def _segments_needing_attention(self, segments: list[dict[str, Any]]) -> list[str]:
        return [
            str(segment.get("segment_id") or "").strip()
            for segment in segments
            if _normalize_boolish(segment.get("review_required"))
            and str(segment.get("segment_id") or "").strip()
        ]

    def _prompt_review_flags(
        self,
        review_flags: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prompt_rows: list[dict[str, Any]] = []
        for flag in review_flags:
            prompt_row = dict(flag)
            prompt_row["code"] = _canonical_review_flag_code(prompt_row.get("code"))
            if "segment_id" in prompt_row:
                prompt_row["segment_id"] = str(prompt_row.get("segment_id") or "").strip()
            if "message" in prompt_row:
                prompt_row["message"] = str(prompt_row.get("message") or "").strip()
            prompt_rows.append(prompt_row)
        return prompt_rows

    def _prompt_pending_recommendations(
        self,
        pending_recommendations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prompt_rows: list[dict[str, Any]] = []
        for item in pending_recommendations:
            prompt_row = dict(item)
            prompt_row["recommendation_type"] = _canonical_recommendation_type(
                prompt_row.get("recommendation_type")
            )
            if "target_segment_id" in prompt_row:
                prompt_row["target_segment_id"] = str(prompt_row.get("target_segment_id") or "").strip()
            prompt_rows.append(prompt_row)
        return prompt_rows
