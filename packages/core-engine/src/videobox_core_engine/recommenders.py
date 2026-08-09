from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

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
            # 영어 단어를 한국어 내레이션에서 찾던 규칙이라 사실상 모든 장면이
            # 같은 기본값으로 떨어졌다. 우리말 단서를 함께 본다.
            mood = "차분하게 깔리는 분위기"
            score = 0.66
            if any(marker in text for marker in ("team", "meeting", "함께", "회의", "우리")):
                mood = "함께하는 밝은 분위기"
                score = 0.79
            elif any(marker in text for marker in ("office", "overview", "소개", "정리", "살펴")):
                mood = "담담하게 설명하는 분위기"
                score = 0.74
            elif "restart" in text or "다시" in text or _normalize_boolish(segment.get("review_required")):
                mood = "가볍게 받쳐 주는 분위기"
                score = 0.61
            results.append(
                RecommendationCandidate(
                    target_segment_id=str(segment["segment_id"]),
                    selected_asset_id=None,
                    score=score,
                    reason=f"이 장면에 어울리는 음악 분위기: {mood}.",
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
    # 장면에 맞는 곡을 실제로 고르기 위한 두 갈고리. 저장소와 임베딩 공급자를
    # core-engine이 직접 알 필요는 없어서 호출 가능한 것만 받는다.
    # 없으면 예전처럼 분위기만 말한다 -- 아무 곡이나 고르는 것보다 낫다.
    library_search: Callable[[str, int], list[dict[str, Any]]] | None = None
    resolve_project_asset: Callable[[str, str], str | None] | None = None

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

            mood = music_mood.strip()
            payload: dict[str, Any] = {
                "music_mood": mood,
                "provider_trace": response_provider_trace(response),
            }
            selected_asset_id = fallback_candidate.selected_asset_id
            reason = f"이 장면에 어울리는 음악 분위기: {mood}."

            track = self._pick_track(segment=segment, mood=mood)
            if track is not None:
                words = track.get("words") or {}
                payload["library_asset_id"] = str(track.get("library_asset_id", ""))
                payload["words"] = words
                payload["duration_seconds"] = track.get("duration_seconds")
                project_asset_id = (
                    self.resolve_project_asset(request.project_id, payload["library_asset_id"])
                    if self.resolve_project_asset is not None
                    else None
                )
                selected_asset_id = project_asset_id
                # 아직 프로젝트에 없으면 화면이 가져오기부터 해야 한다.
                payload["needs_import"] = project_asset_id is None
                described = ", ".join(
                    f"{axis} {value}" for axis, value in words.items()
                )
                reason = f"{mood}에 맞춰 고른 음악입니다. {described}."

            candidates.append(
                RecommendationCandidate(
                    target_segment_id=fallback_candidate.target_segment_id,
                    selected_asset_id=selected_asset_id,
                    score=round(float(score), 2),
                    reason=reason,
                    auto_apply_allowed=fallback_candidate.auto_apply_allowed,
                    review_required=fallback_candidate.review_required,
                    payload=payload,
                )
            )
        return candidates

    def _pick_track(self, *, segment: dict[str, Any], mood: str) -> dict[str, Any] | None:
        """장면과 모델이 말한 분위기를 함께 물어 실제 곡을 고른다.

        검색이 없거나 답이 비면 곡을 고르지 않는다. 라이브러리에서 아무거나
        집어 주는 것은 owner에게 도움이 되지 않는다.
        """
        if self.library_search is None:
            return None
        query = f"{mood} {str(segment.get('text', '')).strip()}".strip()
        if not query:
            return None
        try:
            matches = self.library_search(query, 1)
        except Exception:
            # 로컬 모델이나 라이브러리가 잠깐 없는 것뿐이다. 추천 자체를
            # 막지 않고 분위기만 말하는 예전 경로로 돌아간다.
            return None
        return matches[0] if matches else None

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
            # 이 문구는 이유 문장에 그대로 들어가 화면에 보인다. 실제 응답이
            # "corporate upbeat", "focused and professional"로 나와서 영어가
            # 화면까지 새어 나왔다.
            "이 장면에 어울리는 배경 음악 분위기를 짧게 제안해라.\n"
            f"장면: {segment.get('text', '')}\n"
            f"검토 필요: {bool(segment.get('review_required'))}\n"
            "music_mood는 한국어 짧은 구절로만 쓰고, 영어 단어를 쓰지 마라. "
            "score는 0에서 1 사이 확신도로 쓴다."
        )
