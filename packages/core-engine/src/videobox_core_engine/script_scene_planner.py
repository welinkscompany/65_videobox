from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Protocol

from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_core_engine.provider_trace import build_provider_trace, response_provider_trace, with_final_provider
from videobox_core_engine.transcript_alignment import split_script_units
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType

# A gap this long between two consecutive narration segments is treated as
# dead air/silence worth flagging for operator review rather than assuming
# it's an intentional pause.
NARRATION_SILENCE_GAP_SECONDS = 2.0
# Consecutive segments whose text similarity meets this ratio are treated as
# a retake (the narrator re-recorded the same line) rather than two distinct
# sentences that happen to share vocabulary.
NARRATION_RETAKE_SIMILARITY_RATIO = 0.82


def _is_likely_retake(previous_text: str, current_text: str) -> bool:
    previous_normalized = previous_text.strip().lower()
    current_normalized = current_text.strip().lower()
    if len(previous_normalized) < 4 or len(current_normalized) < 4:
        return False
    return SequenceMatcher(None, previous_normalized, current_normalized).ratio() >= (
        NARRATION_RETAKE_SIMILARITY_RATIO
    )


class StructuredScenePlanningRuntime(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: Any | None = None,
    ) -> Any:
        """Generate structured scene-planning output."""


class SegmentAnalyzer(Protocol):
    def analyze(
        self,
        *,
        project_id: str,
        transcript_segments: list[dict[str, Any]],
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        """Analyze transcript segments into persisted segment-analysis rows."""


@dataclass(slots=True)
class HeuristicSegmentAnalyzer(SegmentAnalyzer):
    def analyze(
        self,
        *,
        project_id: str,
        transcript_segments: list[dict[str, Any]],
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        del project_id
        script_lines = split_script_units(script_text) if script_text else []
        analyzed_segments: list[dict[str, Any]] = []
        previous_segment: dict[str, Any] | None = None
        for index, segment in enumerate(transcript_segments):
            transcript_text = str(segment["text"]).strip()
            script_reference = script_lines[index] if index < len(script_lines) else None
            start_sec = float(segment["start_sec"])

            reasons: list[str] = []
            if "restart" in transcript_text.lower():
                reasons.append("restart_keyword")
            if float(segment.get("confidence", 1.0)) < 0.85:
                reasons.append("low_confidence")
            if script_reference is not None and transcript_text.rstrip(".") != script_reference.rstrip("."):
                reasons.append("script_mismatch")
            if previous_segment is not None:
                gap_sec = start_sec - float(previous_segment["end_sec"])
                if gap_sec > NARRATION_SILENCE_GAP_SECONDS:
                    reasons.append("narration_silence_gap")
                if _is_likely_retake(str(previous_segment["text"]).strip(), transcript_text):
                    reasons.append("narration_retake_duplicate")

            review_required = bool(reasons)
            analyzed_segments.append(
                {
                    "segment_id": f"seg_{index + 1:03d}",
                    "text": transcript_text,
                    "start_sec": start_sec,
                    "end_sec": float(segment["end_sec"]),
                    "confidence": float(segment.get("confidence", 1.0)),
                    "review_required": review_required,
                    "cleanup_decision": "review" if review_required else "keep",
                    "review_reasons": reasons,
                    "provider_trace": build_provider_trace(final_provider="heuristic_fallback"),
                }
            )
            previous_segment = {
                "text": transcript_text,
                "start_sec": start_sec,
                "end_sec": float(segment["end_sec"]),
            }
        return analyzed_segments


@dataclass(slots=True)
class LocalFirstSegmentAnalyzer(SegmentAnalyzer):
    runtime_service: StructuredScenePlanningRuntime
    fallback_analyzer: SegmentAnalyzer = field(default_factory=HeuristicSegmentAnalyzer)

    def analyze(
        self,
        *,
        project_id: str,
        transcript_segments: list[dict[str, Any]],
        script_text: str | None,
    ) -> list[dict[str, Any]]:
        fallback_segments = self.fallback_analyzer.analyze(
            project_id=project_id,
            transcript_segments=transcript_segments,
            script_text=script_text,
        )
        script_lines = split_script_units(script_text) if script_text else []
        analyzed_segments: list[dict[str, Any]] = []

        for index, fallback_segment in enumerate(fallback_segments):
            script_reference = script_lines[index] if index < len(script_lines) else None
            try:
                response = self.runtime_service.generate_structured(
                    project_id=project_id,
                    task_type=LLMTaskType.SCENE_PLANNING,
                    prompt=self._build_prompt(
                        transcript_text=str(fallback_segment["text"]),
                        confidence=float(fallback_segment["confidence"]),
                        script_reference=script_reference,
                    ),
                    response_schema={
                        "type": "object",
                        "required": ["review_required", "cleanup_decision"],
                        "properties": {
                            "review_required": {"type": "boolean"},
                            "cleanup_decision": {"type": "string"},
                        },
                    },
                )
            except (LLMProviderError, LocalFirstStructuredGenerationError) as exc:
                analyzed_segments.append(
                    {
                        **fallback_segment,
                        "provider_trace": with_final_provider(
                            getattr(exc, "provider_trace", build_provider_trace(final_provider="heuristic_fallback")),
                            final_provider="heuristic_fallback",
                        ),
                    }
                )
                continue

            review_required = response.output_data.get("review_required")
            cleanup_decision = response.output_data.get("cleanup_decision")
            if not isinstance(review_required, bool):
                analyzed_segments.append(
                    {
                        **fallback_segment,
                        "provider_trace": with_final_provider(
                            response_provider_trace(response),
                            final_provider="heuristic_fallback",
                            additional_reason="unexpected_runtime_failure",
                        ),
                    }
                )
                continue
            if cleanup_decision not in {"keep", "review"}:
                analyzed_segments.append(
                    {
                        **fallback_segment,
                        "provider_trace": with_final_provider(
                            response_provider_trace(response),
                            final_provider="heuristic_fallback",
                            additional_reason="unexpected_runtime_failure",
                        ),
                    }
                )
                continue

            fallback_review_required = bool(fallback_segment.get("review_required"))
            ai_review_required = bool(review_required or cleanup_decision == "review")
            final_review_required = fallback_review_required or ai_review_required
            analyzed_segments.append(
                {
                    **fallback_segment,
                    "review_required": final_review_required,
                    "cleanup_decision": "review" if final_review_required else "keep",
                    "provider_trace": response_provider_trace(response),
                }
            )
        return analyzed_segments

    def _build_prompt(
        self,
        *,
        transcript_text: str,
        confidence: float,
        script_reference: str | None,
    ) -> str:
        script_line = script_reference or "(no script reference)"
        return (
            "Review this narration segment and decide if manual review is needed.\n"
            f"Transcript segment: {transcript_text}\n"
            f"Transcript confidence: {confidence:.2f}\n"
            f"Script reference: {script_line}\n"
            "Return cleanup_decision as 'keep' or 'review'. "
            "Set review_required true only when the segment likely needs manual cleanup or script review."
        )
