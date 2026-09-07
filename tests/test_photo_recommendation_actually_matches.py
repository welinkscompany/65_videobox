"""추천기를 **실제로 돌려** 사진이 뜻으로 뽑히는지 본다 — 코드리뷰 2026-09-06.

앞선 커밋(`378bb3214`)이 자료실 설명을 후보에 실었지만, 그 시험은 자기가 넣은
문자열에 낱말이 있는지만 봤고 **추천기를 한 번도 안 돌렸다.** 초록인데 안 도는
시험이었다.

돌려 보니 두 겹이 막고 있었다.

1. **태그는 쪼개지지 않는다.** `title`만 낱말로 나뉘고 `tags`는 통째로 집합에
   들어간다. 설명 한 문장을 태그 한 칸에 넣었으니 낱말이 맞을 수가 없었다.
2. **한국어는 조사가 붙는다.** 쪼개도 대본의 `바다가`와 설명의 `바다`는 다른
   낱말이다. 문장 끝에 홑 낱말로 나온 것만 우연히 맞았다.

둘 다 막히면 결과는 `Fallback candidate` -- 뜻과 상관없는 돌려쓰기 차례다.
"""

from __future__ import annotations

from videobox_domain_models.recommendations import RecommendationType
from videobox_core_engine.recommenders import KeywordBrollRecommender, RecommendationRequest


def _asset(asset_id: str, description: str) -> dict:
    """자료실 설명이 실린 후보. `broll_scene_candidates`가 만드는 모양 그대로다."""
    return {"asset_id": asset_id, "metadata": {"tags": [description]}}


def _recommend(segments: list[dict], assets: list[dict]):
    return KeywordBrollRecommender().recommend(
        RecommendationRequest(project_id="p1", recommendation_type=RecommendationType.BROLL, segments=segments, assets=assets)
    )


def test_the_sea_scene_gets_the_sea_photo() -> None:
    segments = [
        {"segment_id": "s1", "text": "바다가 보이는 창가에서 커피를 마셨다."},
        {"segment_id": "s2", "text": "도시의 밤거리를 걸었다."},
    ]
    assets = [
        _asset("photo_city", "가로 사진. 도시 야경, 밤거리, 네온."),
        _asset("photo_sea", "가로 사진. 바다가 보이는 창가, 노을, 바다."),
    ]

    picks = {item.target_segment_id: item.selected_asset_id for item in _recommend(segments, assets)}

    assert picks["s1"] == "photo_sea", picks
    assert picks["s2"] == "photo_city", picks


def test_the_order_of_the_assets_does_not_decide_it() -> None:
    """자산 순서를 뒤집어도 같은 답이 나와야 뜻으로 고른 것이다.

    돌려쓰기는 순서에 끌려간다 -- 이 시험이 그 둘을 가른다.
    """
    segments = [{"segment_id": "s1", "text": "바다가 보이는 창가."}]
    sea = _asset("photo_sea", "가로 사진. 바다, 노을.")
    city = _asset("photo_city", "가로 사진. 도시 야경.")

    forward = _recommend(segments, [city, sea])[0]
    backward = _recommend(segments, [sea, city])[0]

    assert forward.selected_asset_id == backward.selected_asset_id == "photo_sea"


def test_the_reason_says_which_words_matched() -> None:
    """왜 골랐는지 창작자가 볼 수 있어야 한다. `Fallback`은 이유가 아니다."""
    result = _recommend(
        [{"segment_id": "s1", "text": "바다가 보이는 창가."}],
        [_asset("photo_sea", "가로 사진. 바다, 노을.")],
    )[0]

    assert "바다" in (result.reason or ""), result.reason


def test_a_photo_with_nothing_in_common_is_not_claimed_as_a_match() -> None:
    """안 맞는 것을 맞다고 하면 안 된다 -- 돌려쓰기로 뽑히더라도 점수가 낮아야 한다."""
    result = _recommend(
        [{"segment_id": "s1", "text": "세금 신고 절차를 설명한다."}],
        [_asset("photo_sea", "가로 사진. 바다, 노을.")],
    )[0]

    assert result.score <= 0.2, result
