"""음악 추천이 실제로 곡을 고르게 한다.

지금까지 음악 추천은 곡을 하나도 고르지 않았다. 돌고 있는 컨테이너에서 확인한
실제 응답은 후보 두 개 모두 `selected_asset_id: None`이었고, 이유는 영어로
"corporate upbeat", "professional and focused"였다. 고르는 규칙도 `"team"`,
`"meeting"` 같은 영어 단어를 한국어 내레이션에서 찾는 것이라 사실상 항상 같은
기본값으로 떨어졌다.

이제 라이브러리 의미검색으로 실제 곡을 고른다.
"""

from __future__ import annotations

from videobox_core_engine.recommenders import LocalOnlyMusicRecommender, RuleBasedMusicRecommender
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.recommenders import RecommendationRequest


class _Runtime:
    def __init__(self, *, mood: str = "차분하고 잔잔한 분위기", fail: bool = False) -> None:
        self.mood = mood
        self.fail = fail
        self.prompts: list[str] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.prompts.append(prompt)
        if self.fail:
            from videobox_provider_interfaces.llm import LLMProviderError

            raise LLMProviderError("local model away", "failed")

        class _Response:
            output_data = {"music_mood": self.mood, "score": 0.8}
            provider_name = "test"
            model_name = "test"
            attempts = ()

        return _Response()


def _request() -> RecommendationRequest:
    return RecommendationRequest(
        project_id="p1",
        recommendation_type=RecommendationType.BGM,
        segments=[{"segment_id": "seg-1", "text": "오늘은 조용한 아침 산책 이야기입니다."}],
        assets=[],
    )


def _search(query: str, limit: int) -> list[dict]:
    return [
        {
            "library_asset_id": "pack:starter-v1:music-orien",
            "asset_id": "music-orien",
            "description": "영상 전체에 길게 깔아 두기 좋은 음악.",
            "words": {"세기": "조용함", "밝기": "중간", "빠르기": "느림"},
            "duration_seconds": 143.0,
            "score": 0.71,
        }
    ][:limit]


def test_a_real_track_is_chosen_and_named_in_the_owners_words() -> None:
    recommender = LocalOnlyMusicRecommender(runtime_service=_Runtime(), library_search=_search)

    [candidate] = recommender.recommend(_request())

    assert candidate.payload["library_asset_id"] == "pack:starter-v1:music-orien"
    assert candidate.payload["words"]["세기"] == "조용함"
    # 이유가 실제로 고른 곡을 말해야 한다.
    assert "조용함" in candidate.reason and "느림" in candidate.reason
    for forbidden in ("corporate", "upbeat", "professional", "music_mood"):
        assert forbidden not in candidate.reason.lower()


def test_the_search_uses_both_the_scene_and_the_mood_the_model_suggested() -> None:
    seen: list[str] = []

    def search(query: str, limit: int) -> list[dict]:
        seen.append(query)
        return _search(query, limit)

    LocalOnlyMusicRecommender(
        runtime_service=_Runtime(mood="잔잔한 분위기"), library_search=search
    ).recommend(_request())

    assert seen and "잔잔한" in seen[0]
    assert "산책" in seen[0]


def test_a_track_already_in_the_project_is_referenced_by_its_project_id() -> None:
    # 이미 프로젝트로 가져온 곡이면 화면이 바로 적용할 수 있어야 한다.
    def resolve(project_id: str, library_asset_id: str) -> str | None:
        assert project_id == "p1"
        return "asset_local_music_1" if library_asset_id.endswith("music-orien") else None

    [candidate] = LocalOnlyMusicRecommender(
        runtime_service=_Runtime(), library_search=_search, resolve_project_asset=resolve
    ).recommend(_request())

    assert candidate.selected_asset_id == "asset_local_music_1"


def test_a_track_not_yet_in_the_project_says_so_instead_of_pretending() -> None:
    [candidate] = LocalOnlyMusicRecommender(
        runtime_service=_Runtime(), library_search=_search,
        resolve_project_asset=lambda _project, _library: None,
    ).recommend(_request())

    assert candidate.selected_asset_id is None
    # 화면이 가져오기부터 해야 한다는 것을 알 수 있어야 한다.
    assert candidate.payload["needs_import"] is True


def test_with_no_search_available_it_still_answers_without_inventing_a_track() -> None:
    # 로컬 모델이나 라이브러리가 없을 때. 아무 곡이나 고르는 것보다 낫다.
    [candidate] = LocalOnlyMusicRecommender(runtime_service=_Runtime()).recommend(_request())

    assert candidate.selected_asset_id is None
    assert "library_asset_id" not in candidate.payload


def test_the_rule_based_fallback_speaks_the_owners_language() -> None:
    # 모델이 없을 때 쓰이는 경로. 영어 분위기 문구가 그대로 화면에 나갔다.
    [candidate] = RuleBasedMusicRecommender().recommend(_request())

    for forbidden in ("corporate", "upbeat", "documentary", "neutral bed"):
        assert forbidden not in candidate.reason.lower()
    assert any(marker in candidate.reason for marker in ("분위기", "음악"))


def test_the_model_is_asked_for_a_korean_mood() -> None:
    """실제 응답의 분위기가 "corporate upbeat", "focused and professional"로
    나왔다. 이 문구는 이유 문장에 그대로 들어가 화면에 보인다."""
    runtime = _Runtime()

    LocalOnlyMusicRecommender(runtime_service=runtime, library_search=_search).recommend(_request())

    assert runtime.prompts and "한국어" in runtime.prompts[0]
