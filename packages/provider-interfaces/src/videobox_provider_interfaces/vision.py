from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


FIXED_VISION_LAYERS = (
    "place", "action", "time_of_day", "weather", "people_objects", "emotion",
    "mood", "topic_links", "scene", "color_tone", "camera", "season", "country_region",
)

FIXED_VISION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["layers", "summary", "confidence", "review_reasons"],
    "properties": {
        "layers": {
            "type": "object",
            "additionalProperties": False,
            "required": list(FIXED_VISION_LAYERS),
            "properties": {layer: {"type": "array", "items": {"type": "string"}} for layer in FIXED_VISION_LAYERS},
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "review_reasons": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass(slots=True, frozen=True)
class VisionAnalysisRequest:
    model_name: str
    prompt: str
    images: tuple[bytes, ...]
    response_schema: dict[str, Any]
    provider_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class VisionAnalysisResponse:
    provider_name: str
    model_name: str
    output_data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionProvider(Protocol):
    provider_name: str

    def analyze_images(self, request: VisionAnalysisRequest) -> VisionAnalysisResponse:
        """Analyze local image inputs and return validated structured output."""
