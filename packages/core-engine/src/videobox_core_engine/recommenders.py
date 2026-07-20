from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from videobox_core_engine.provider_trace import build_provider_trace, response_provider_trace, with_final_provider
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType
from videobox_provider_interfaces.recommendation_policies import get_recommendation_guardrail
from videobox_provider_interfaces.recommenders import (
    RecommendationCandidate,
    RecommendationProvider,
    RecommendationRequest,
)


def _tokenize(text: str) -> set[str]:
    return {token.strip(".,!?").lower() for token in text.split() if token.strip(".,!?")}


def _normalize_boolish(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


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
                    payload={
                        "matched_tags": best_overlap,
                        "provider_trace": segment.get("provider_trace", build_provider_trace(final_provider="heuristic_fallback")),
                    },
                )
            )
        return results


@dataclass(slots=True)
class LocalOnlyKeywordBrollRecommender(RecommendationProvider):
    runtime_service: StructuredRecommendationRuntime
    fallback_recommender: RecommendationProvider = field(default_factory=KeywordBrollRecommender)
    provider_name: str = "local-only-keyword-broll"

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
        except LLMProviderError as exc:
            # Recommendation generation must degrade to the existing heuristic path.
            enriched = dict(segment)
            enriched["provider_trace"] = with_final_provider(
                getattr(exc, "provider_trace", build_provider_trace(final_provider="heuristic_fallback")),
                final_provider="heuristic_fallback",
            )
            return enriched
        except Exception:
            enriched = dict(segment)
            enriched["provider_trace"] = with_final_provider(
                build_provider_trace(final_provider="heuristic_fallback"),
                final_provider="heuristic_fallback",
                additional_reason="unexpected_runtime_failure",
            )
            return enriched

        keywords = [
            str(item).strip().lower()
            for item in response.output_data.get("keywords", [])
            if isinstance(item, str) and item.strip()
        ]
        if not keywords:
            enriched = dict(segment)
            enriched["provider_trace"] = with_final_provider(
                response_provider_trace(response),
                final_provider="heuristic_fallback",
                additional_reason="unexpected_runtime_failure",
            )
            return enriched
        enriched = dict(segment)
        enriched["text"] = f"{segment.get('text', '')} {' '.join(keywords)}".strip()
        enriched["expanded_keywords"] = keywords
        enriched["provider_trace"] = response_provider_trace(response)
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
            elif "restart" in text or _normalize_boolish(segment.get("review_required")):
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


@dataclass(slots=True)
class LocalOnlyMusicRecommender(RecommendationProvider):
    runtime_service: StructuredRecommendationRuntime
    fallback_recommender: RecommendationProvider = field(default_factory=RuleBasedMusicRecommender)
    provider_name: str = "local-only-music"

    def recommend(self, request: RecommendationRequest) -> list[RecommendationCandidate]:
        fallback_candidates = self.fallback_recommender.recommend(request)
        candidates: list[RecommendationCandidate] = []
        for segment, fallback_candidate in zip(request.segments, fallback_candidates, strict=False):
            try:
                response = self.runtime_service.generate_structured(
                    project_id=request.project_id,
                    task_type=LLMTaskType.MUSIC_RECOMMENDATION,
                    prompt=self._build_prompt(segment=segment),
                    response_schema={
                        "type": "object",
                        "required": ["music_mood", "score"],
                        "properties": {
                            "music_mood": {"type": "string"},
                            "score": {"type": "number"},
                        },
                    },
                )
            except (
                LLMProviderError,
            ) as exc:
                candidates.append(self._fallback_candidate(fallback_candidate, exc=exc))
                continue

            music_mood = response.output_data.get("music_mood")
            score = response.output_data.get("score")
            if not isinstance(music_mood, str) or not music_mood.strip():
                candidates.append(
                    self._fallback_candidate(
                        fallback_candidate,
                        trace=with_final_provider(
                            response_provider_trace(response),
                            final_provider="rule_based_fallback",
                            additional_reason="unexpected_runtime_failure",
                        ),
                    )
                )
                continue
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                candidates.append(
                    self._fallback_candidate(
                        fallback_candidate,
                        trace=with_final_provider(
                            response_provider_trace(response),
                            final_provider="rule_based_fallback",
                            additional_reason="unexpected_runtime_failure",
                        ),
                    )
                )
                continue

            candidates.append(
                RecommendationCandidate(
                    target_segment_id=fallback_candidate.target_segment_id,
                    selected_asset_id=fallback_candidate.selected_asset_id,
                    score=round(float(score), 2),
                    reason=f"Suggested music mood for this segment: {music_mood.strip()}.",
                    auto_apply_allowed=fallback_candidate.auto_apply_allowed,
                    review_required=fallback_candidate.review_required,
                    payload={
                        "music_mood": music_mood.strip(),
                        "provider_trace": response_provider_trace(response),
                    },
                )
            )
        return candidates

    def _fallback_candidate(
        self,
        fallback_candidate: RecommendationCandidate,
        *,
        exc: Exception | None = None,
        trace: dict[str, Any] | None = None,
    ) -> RecommendationCandidate:
        fallback_trace = trace or with_final_provider(
            getattr(exc, "provider_trace", build_provider_trace(final_provider="rule_based_fallback")),
            final_provider="rule_based_fallback",
        )
        return RecommendationCandidate(
            target_segment_id=fallback_candidate.target_segment_id,
            selected_asset_id=fallback_candidate.selected_asset_id,
            score=fallback_candidate.score,
            reason=fallback_candidate.reason,
            auto_apply_allowed=fallback_candidate.auto_apply_allowed,
            review_required=fallback_candidate.review_required,
            payload={
                **fallback_candidate.payload,
                "provider_trace": fallback_trace,
            },
        )

    def _build_prompt(self, *, segment: dict[str, Any]) -> str:
        return (
            "Suggest a concise background music mood for this video segment.\n"
            f"Segment: {segment.get('text', '')}\n"
            f"Review required: {bool(segment.get('review_required'))}\n"
            "Return music_mood as a short phrase and score as a 0-1 confidence value."
        )
