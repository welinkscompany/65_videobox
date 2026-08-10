from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


FIXED_VISION_LAYERS = (
    "place", "action", "time_of_day", "weather", "people_objects", "emotion",
    "mood", "topic_links", "scene", "color_tone", "camera", "season", "country_region",
)

# 갈래 수가 곧 시간이다. 이 기기에서 재보니 3개 68초, 6개 132초, 9개 121초,
# 13개는 200초에도 못 끝냈다 -- 그래서 분석이 통째로 실패하고 있었다.
#
# 검색 문장이 실제로 쓰는 것은 아래 아홉이다. 나머지 넷(color_tone, camera,
# season, country_region)은 저장만 된다. 빼는 게 아니라 **필수에서 내린다** --
# 모델이 채우면 그대로 태그로 남는다.
REQUIRED_VISION_LAYERS = (
    "place", "scene", "action", "people_objects", "weather",
    "time_of_day", "season", "mood", "emotion",
)

FIXED_VISION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["layers", "summary", "confidence", "review_reasons"],
    "properties": {
        "layers": {
            "type": "object",
            "additionalProperties": False,
            "required": list(REQUIRED_VISION_LAYERS),
            # 상한이 없으면 모델이 얼마든지 길게 쓴다 -- 실제로 한 항목이 문장
            # 두 개짜리로 나왔고, 13갈래를 그렇게 채우느라 180~300초가 걸려
            # 120초 타임아웃을 넘겼다. 태그는 짧은 말이어야 검색에도 화면에도
            # 쓸 수 있다.
            "properties": {
                layer: {
                    "type": "array",
                    "maxItems": 6,
                    "items": {"type": "string", "maxLength": 40},
                }
                for layer in FIXED_VISION_LAYERS
            },
        },
        "summary": {"type": "string", "maxLength": 200},
        "confidence": {"type": "number"},
        # 마지막 구멍이었다. 갈래와 요약을 묶고도 360초에 실패했는데
        # 여기까지 묶으니 252~280초로 통과했다.
        "review_reasons": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 100},
        },
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
