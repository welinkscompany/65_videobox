from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from videobox_core_engine.gemini_runtime import GeminiStructuredGenerationError
from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType


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
    ) -> list[str]:
        """Return operator-facing notes for preview/export outputs."""


@dataclass(slots=True)
class StaticOutputOperatorCopyBuilder(OutputOperatorCopyBuilder):
    def build(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_target: str,
        subtitle_file_uri: str | None = None,
    ) -> list[str]:
        del project_id, timeline, subtitle_file_uri
        if output_target == "capcut_export":
            return [
                "Mock CapCut payload for local post-editing handoff.",
                "CapCut remains an export target, not the internal source of truth.",
            ]
        return [
            "Playable local HTML preview generated for operator review.",
            "This preview simulates timing and captions instead of final media rendering.",
        ]


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
    ) -> list[str]:
        fallback_notes = self.fallback_builder.build(
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
                return fallback_notes
            if not isinstance(action_items, list):
                return fallback_notes

            cleaned_notes = [summary.strip()]
            cleaned_notes.extend(
                str(item).strip()
                for item in action_items
                if isinstance(item, str) and item.strip()
            )
            cleaned_notes = cleaned_notes[:5]
            return cleaned_notes or fallback_notes
        except (
            GeminiStructuredGenerationError,
            LLMProviderError,
            LocalFirstStructuredGenerationError,
            Exception,
        ):
            return fallback_notes

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
        track_summary = [
            {
                "track_type": track.get("track_type"),
                "clip_count": len(track.get("clips", [])),
            }
            for track in tracks
        ]
        return (
            "Write concise operator-facing output guidance for this approved video timeline.\n"
            f"Output target: {target_label}\n"
            f"Timeline id: {timeline.get('timeline_id')}\n"
            f"Review status: {timeline.get('review_status', 'approved')}\n"
            f"Subtitle attached: {'yes' if subtitle_file_uri else 'no'}\n"
            f"Track summary: {track_summary}\n"
            f"Review flags: {review_flags}\n"
            f"Pending recommendations: {pending_recommendations}\n"
            "Return a short summary and concrete action items for the operator."
        )
