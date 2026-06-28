from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from videobox_core_engine.local_first_runtime import LocalFirstStructuredGenerationError
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType
from videobox_provider_interfaces.recommendation_policies import get_recommendation_guardrail
from videobox_provider_interfaces.recommenders import (
    RecommendationCandidate,
    RecommendationProvider,
    RecommendationRequest,
)


def _tokenize(text: str) -> set[str]:
    return {token.strip(".,!?").lower() for token in text.split() if token.strip(".,!?")}


class StructuredRecommendationRuntime(Protocol):
    def generate_structured(
        self,
        *,
        project_id: str,
        task_type: LLMTaskType,
        prompt: str,
        response_schema: dict[str, Any],
        now: Any | None = None,
    ) -> Any:
        """Generate structured recommendation assistance."""


class KeywordBrollRecommender(RecommendationProvider):
    provider_name = "keyword-broll"

    def recommend(self, request: RecommendationRequest) -> list[RecommendationCandidate]:
        guardrail = get_recommendation_guardrail(request.recommendation_type.value)
        results: list[RecommendationCandidate] = []
        for segment in request.segments:
            segment_tokens = _tokenize(str(segment.get("text", "")))
            best_asset: dict[str, Any] | None = None
            best_score = 0.15
            best_overlap: list[str] = []
            for asset in request.assets:
                metadata = asset.get("metadata", {}) or {}
                asset_tokens = (
                    _tokenize(str(metadata.get("title", "")))
                    | {str(tag).lower() for tag in metadata.get("tags", [])}
                )
                overlap = sorted(segment_tokens & asset_tokens)
                score = round(min(0.98, 0.3 + len(overlap) * 0.2), 2) if overlap else 0.18
                if score > best_score:
                    best_asset = asset
                    best_score = score
                    best_overlap = overlap
            if best_asset is None and request.assets:
                best_asset = request.assets[0]
                best_score = 0.22
            results.append(
                RecommendationCandidate(
                    target_segment_id=str(segment["segment_id"]),
                    selected_asset_id=best_asset["asset_id"] if best_asset else None,
                    score=best_score,
                    reason=(
                        f"Matched keywords: {', '.join(best_overlap)}"
                        if best_overlap
                        else "Fallback candidate from available B-roll assets."
                    ),
                    auto_apply_allowed=guardrail.auto_apply_allowed,
                    review_required=guardrail.review_required,
                    payload={"matched_tags": best_overlap},
                )
            )
        return results


@dataclass(slots=True)
class LocalFirstKeywordBrollRecommender(RecommendationProvider):
    runtime_service: StructuredRecommendationRuntime
    fallback_recommender: RecommendationProvider = field(default_factory=KeywordBrollRecommender)
    provider_name: str = "local-first-keyword-broll"

    def recommend(self, request: RecommendationRequest) -> list[RecommendationCandidate]:
        enriched_segments = [
            self._enrich_segment(
                project_id=request.project_id,
                segment=segment,
                assets=request.assets,
            )
            for segment in request.segments
        ]
        return self.fallback_recommender.recommend(
            RecommendationRequest(
                project_id=request.project_id,
                recommendation_type=request.recommendation_type,
                segments=enriched_segments,
                assets=request.assets,
            )
        )

    def _enrich_segment(
        self,
        *,
        project_id: str,
        segment: dict[str, Any],
        assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.KEYWORD_EXPANSION,
                prompt=self._build_prompt(segment=segment),
                response_schema={
                    "type": "object",
                    "required": ["keywords"],
                    "properties": {
                        "keywords": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )
        except (LLMProviderError, LocalFirstStructuredGenerationError):
            # Recommendation generation must degrade to the existing heuristic path.
            return dict(segment)

        keywords = [
            str(item).strip().lower()
            for item in response.output_data.get("keywords", [])
            if isinstance(item, str) and item.strip()
        ]
        if not keywords:
            return dict(segment)
        enriched = dict(segment)
        enriched["text"] = f"{segment.get('text', '')} {' '.join(keywords)}".strip()
        enriched["expanded_keywords"] = keywords
        return enriched

    def _build_prompt(self, *, segment: dict[str, Any]) -> str:
        return (
            "Expand concise B-roll search keywords for this transcript segment.\n"
            f"Segment: {segment.get('text', '')}\n"
            "Return only short transcript-derived keywords that improve B-roll search."
        )


class RuleBasedMusicRecommender(RecommendationProvider):
    provider_name = "rule-based-music"

    def recommend(self, request: RecommendationRequest) -> list[RecommendationCandidate]:
        guardrail = get_recommendation_guardrail(request.recommendation_type.value)
        results: list[RecommendationCandidate] = []
        for segment in request.segments:
            text = str(segment.get("text", "")).lower()
            mood = "focused corporate"
            score = 0.66
            if "team" in text or "meeting" in text:
                mood = "collaborative upbeat"
                score = 0.79
            elif "office" in text or "overview" in text:
                mood = "clean documentary pulse"
                score = 0.74
            elif "restart" in text or bool(segment.get("review_required")):
                mood = "light neutral bed"
                score = 0.61
            results.append(
                RecommendationCandidate(
                    target_segment_id=str(segment["segment_id"]),
                    selected_asset_id=None,
                    score=score,
                    reason=f"Suggested music mood for this segment: {mood}.",
                    auto_apply_allowed=guardrail.auto_apply_allowed,
                    review_required=guardrail.review_required,
                    payload={"music_mood": mood},
                )
            )
        return results
