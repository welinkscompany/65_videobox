from __future__ import annotations

import logging
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

_logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    return {token.strip(".,!?").lower() for token in text.split() if token.strip(".,!?")}


def _is_hangul(token: str) -> bool:
    return any("가" <= character <= "힣" for character in token)


def _matching_words(segment_tokens: set[str], asset_tokens: set[str]) -> list[str]:
    """대본 낱말과 자산 낱말 중 **뜻이 같은 것**을 고른다.

    똑같은 낱말만 세면 한국어가 거의 안 맞는다 -- 대본은 `바다가`인데 자료실
    설명은 `바다`다. 조사가 붙었을 뿐 같은 말이다. 그래서 한글 낱말은 **한쪽이
    다른 쪽으로 시작하면** 맞은 것으로 센다.

    영어는 예전 그대로 정확히 맞을 때만 센다 -- `in`이 `internal`을 맞히면
    아무 대본이나 아무 자산에 붙는다. 한글은 조사가 뒤에 붙는 구조라 앞쪽이
    같으면 같은 말일 확률이 훨씬 높다.

    돌려주는 것은 **짧은 쪽**이다. 창작자에게 보여 줄 이유는 `바다가`보다
    `바다`가 낫다.
    """
    matched: set[str] = set(segment_tokens & asset_tokens)
    for segment_token in segment_tokens:
        if not _is_hangul(segment_token) or len(segment_token) < 2:
            continue
        for asset_token in asset_tokens:
            if len(asset_token) < 2 or not _is_hangul(asset_token):
                continue
            if segment_token.startswith(asset_token) or asset_token.startswith(segment_token):
                matched.add(min(segment_token, asset_token, key=len))
    return sorted(matched)


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
        # **낱말이 안 맞을 때 장면마다 다른 것을 준다**(2026-09-06 실측). 겹치는
        # 낱말이 없으면 모든 자산이 같은 점수(0.18)를 받는데, 첫 자산이 이긴 뒤로는
        # `0.18 > 0.18`이 거짓이라 그 자리가 영영 안 바뀐다. 장면마다 같은 계산을
        # 하니 **다섯 장면이 전부 같은 촬영본**이 됐다 -- 넷을 넣어 두었는데도.
        # 브이로그에서 같은 화면 11초는 못 쓴다.
        #
        # 낱말이 맞을 때의 선택은 건드리지 않는다. 맞는 것이 있으면 그것이 이긴다.
        fallback_turn = 0
        for segment in request.segments:
            segment_tokens = _tokenize(str(segment.get("text", "")))
            best_asset: dict[str, Any] | None = None
            best_score = 0.15
            best_overlap: list[str] = []
            for asset in request.assets:
                metadata = asset.get("metadata", {}) or {}
                # **태그도 낱말로 쪼갠다.** 예전에는 통째로 집합에 넣어서, 자료실
                # 설명 한 문장을 태그로 실었더니 낱말이 하나도 안 맞았다 --
                # 사진이 뜻이 아니라 돌려쓰기 차례로만 뽑히던 이유다(2026-09-06
                # 코드리뷰). 여러 낱말이 든 태그는 이 쪼개기 전에도 이미 안 맞고
                # 있었다.
                asset_tokens = _tokenize(
                    " ".join(
                        [str(metadata.get("title", ""))]
                        + [str(tag) for tag in metadata.get("tags", [])]
                    )
                )
                overlap = _matching_words(segment_tokens, asset_tokens)
                # **낱말이 하나도 안 맞는 자산은 후보로 세지 않는다.** 예전에는
                # 그런 자산에도 0.18을 줬는데, 초기값 0.15보다 커서 **첫 자산이
                # 곧바로 이기고** 그 뒤로는 `0.18 > 0.18`이 거짓이라 자리가 영영
                # 안 바뀌었다. 아래 돌려쓰기가 한 번도 실행되지 않은 이유다.
                if not overlap:
                    continue
                score = round(min(0.98, 0.3 + len(overlap) * 0.2), 2)
                if score > best_score:
                    best_asset = asset
                    best_score = score
                    best_overlap = overlap
            if best_asset is None and request.assets:
                best_asset = request.assets[fallback_turn % len(request.assets)]
                best_score = 0.18
                fallback_turn += 1
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
            reason = (
                f"이 장면에 어울리는 음악 분위기: {mood}. "
                "지금은 곡을 고르지 못했어요 -- 분위기만 참고해 주세요."
            )

            track = self._pick_track(project_id=request.project_id, segment=segment, mood=mood)
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

    def _pick_track(self, *, project_id: str, segment: dict[str, Any], mood: str) -> dict[str, Any] | None:
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
            # 막지 않고 분위기만 말하는 예전 경로로 돌아간다. 다만 그 사실을
            # 말하지 않으면 owner는 왜 추천이 밋밋해졌는지 알 수 없다.
            _logger.warning(
                "음악 라이브러리를 검색하지 못해 분위기만 제안합니다 (project=%s).",
                project_id,
                exc_info=True,
            )
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
