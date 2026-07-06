from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

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


def _canonical_review_status(value: object) -> str:
    return str(value or "approved").strip().lower() or "approved"


def _canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


VALID_PROMPT_TRACK_TYPES = {"narration", "broll", "bgm"}
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


class StructuredOutputCopyRuntime(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: Any | None = None,
    ) -> Any:
        """Generate structured output guidance."""


class OutputOperatorCopyBuilder(Protocol):
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> dict[str, Any] | list[str]:
        """Return operator-facing notes and provider trace for preview/export outputs."""


@dataclass(slots=True)
class StaticOutputOperatorCopyBuilder(OutputOperatorCopyBuilder):
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> dict[str, Any]:
        del project_id, timeline, subtitle_file_uri
        if output_target == "capcut_export":
            return {
                "notes": [
                    "CapCut export manifest generated for local post-editing handoff.",
                    "CapCut remains an export target, not the internal source of truth.",
                ],
                "provider_trace": build_provider_trace(final_provider="static_fallback"),
            }
        return {
            "notes": [
                "Playable local HTML preview generated for operator review.",
                "This preview simulates timing and captions instead of final media rendering.",
            ],
            "provider_trace": build_provider_trace(final_provider="static_fallback"),
        }


@dataclass(slots=True)
class LocalFirstOutputOperatorCopyBuilder(OutputOperatorCopyBuilder):
    runtime_service: StructuredOutputCopyRuntime
    fallback_builder: OutputOperatorCopyBuilder = field(default_factory=StaticOutputOperatorCopyBuilder)

    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> dict[str, Any]:
        fallback_payload = self.fallback_builder.build(
            project_id=project_id,
            timeline=timeline,
            output_target=output_target,
            subtitle_file_uri=subtitle_file_uri,
        )
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.OPERATOR_COPY,
                prompt=self._build_prompt(
                    timeline=timeline,
                    output_target=output_target,
                    subtitle_file_uri=subtitle_file_uri,
                ),
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
                fallback_payload["provider_trace"] = with_final_provider(
                    response_provider_trace(response),
                    final_provider="static_fallback",
                    additional_reason="unexpected_runtime_failure",
                )
                return fallback_payload
            if not isinstance(action_items, list):
                fallback_payload["provider_trace"] = with_final_provider(
                    response_provider_trace(response),
                    final_provider="static_fallback",
                    additional_reason="unexpected_runtime_failure",
                )
                return fallback_payload

            cleaned_notes = [summary.strip()]
            cleaned_notes.extend(
                str(item).strip()
                for item in action_items
                if isinstance(item, str) and item.strip()
            )
            cleaned_notes = cleaned_notes[:5]
            if cleaned_notes:
                return {
                    "notes": cleaned_notes,
                    "provider_trace": response_provider_trace(response),
                }
            fallback_payload["provider_trace"] = with_final_provider(
                response_provider_trace(response),
                final_provider="static_fallback",
                additional_reason="unexpected_runtime_failure",
            )
            return fallback_payload
        except Exception as exc:
            fallback_payload["provider_trace"] = with_final_provider(
                getattr(exc, "provider_trace", build_provider_trace(final_provider="static_fallback")),
                final_provider="static_fallback",
                additional_reason="unexpected_runtime_failure" if not isinstance(
                    exc,
                    (GeminiStructuredGenerationError, LLMProviderError, LocalFirstStructuredGenerationError),
                ) else None,
            )
            return fallback_payload

    def _build_prompt(
        self,
        *,
        timeline: dict[str, Any],
        output_target: str,
        subtitle_file_uri: str | None,
    ) -> str:
        tracks = timeline.get("tracks", [])
        review_flags = timeline.get("review_flags", [])
        pending_recommendations = timeline.get("pending_recommendations", [])
        target_label = "preview" if output_target == "preview_render" else "capcut export"
        track_summary = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            track_type = _canonical_track_type(track.get("track_type"))
            if track_type not in VALID_PROMPT_TRACK_TYPES:
                continue
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            valid_clips = [clip for clip in clips if isinstance(clip, dict)]
            track_summary.append(
                {
                    "track_type": track_type,
                    "clip_count": len(valid_clips),
                }
            )
        prompt_review_flags = []
        for flag in review_flags:
            if not isinstance(flag, dict):
                continue
            if not has_canonical_review_flag_identity(
                flag,
                canonical_review_flag_code=_canonical_review_flag_code,
                valid_review_flag_codes=VALID_PROMPT_REVIEW_FLAG_CODES,
            ):
                continue
            prompt_review_flags.append(
                normalize_prompt_review_flag_row(
                    flag,
                    canonical_review_flag_code=_canonical_review_flag_code,
                    canonical_review_flag_message=_canonical_review_flag_message,
                )
            )
        pending_summary = []
        for item in pending_recommendations:
            if not _is_prompt_blocking_pending_recommendation(item):
                continue
            pending_summary.append(
                normalize_prompt_pending_recommendation_row(
                    item,
                    canonical_recommendation_type=_canonical_recommendation_type,
                    canonical_reason=_canonical_review_flag_message,
                    canonical_decision_state=_canonical_decision_state,
                )
            )
        return (
            "Write concise operator-facing output guidance for this approved video timeline.\n"
            f"Output target: {target_label}\n"
            f"Timeline id: {timeline.get('timeline_id')}\n"
            f"Review status: {_canonical_review_status(timeline.get('review_status', 'approved'))}\n"
            f"Subtitle attached: {'yes' if subtitle_file_uri else 'no'}\n"
            f"Track summary: {track_summary}\n"
            f"Review flags: {prompt_review_flags}\n"
            f"Pending recommendations: {pending_summary}\n"
            "Return a short summary and concrete action items for the operator."
        )
