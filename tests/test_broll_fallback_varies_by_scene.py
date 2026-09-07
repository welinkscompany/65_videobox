"""낱말이 안 맞으면 모든 장면이 같은 영상 하나를 썼다 — 실측 2026-09-06.

owner: "실제로 영상 하나 만들어봐."

대본→내레이션→받아쓰기→장면분석→추천→타임라인→렌더를 처음부터 끝까지 돌려
완성본을 얻었는데, **다섯 장면이 전부 같은 촬영본**이었다. 촬영본은 네 개를
넣어 두었는데도 그랬다.

원인은 점수 비교다. 겹치는 낱말이 없으면 모든 자산이 `0.18`을 받고, `best_score`
초기값이 `0.15`라 **첫 자산이 이긴 뒤로는 `0.18 > 0.18`이 거짓**이라 그 자리가
영영 안 바뀐다. 장면마다 같은 계산을 하니 모든 장면이 같은 자산을 고른다.

owner 지적대로 근본 원인은 **재료가 없는 것**이다(자료실 촬영본 대부분이 시험용
더미였다). 하지만 재료가 넷 있는데 하나만 쓰는 것은 그와 별개다 -- 브이로그에서
같은 화면 11초는 못 쓴다.

**낱말이 맞을 때의 선택은 건드리지 않는다.** 맞는 것이 있으면 그것이 이겨야 한다.
"""

from __future__ import annotations

from videobox_core_engine.recommenders import KeywordBrollRecommender
from videobox_domain_models.recommendations import RecommendationType
from videobox_provider_interfaces.recommenders import RecommendationRequest


def _request(*, segment_texts: list[str], asset_tags: list[list[str]]) -> RecommendationRequest:
    return RecommendationRequest(
        project_id="p",
        recommendation_type=RecommendationType.BROLL,
        segments=[
            {"segment_id": f"seg_{index + 1:03d}", "text": text}
            for index, text in enumerate(segment_texts)
        ],
        assets=[
            {"asset_id": f"asset_{index + 1}", "metadata": {"title": f"촬영본 {index + 1}", "tags": tags}}
            for index, tags in enumerate(asset_tags)
        ],
    )


def test_scenes_that_match_nothing_still_get_different_footage() -> None:
    """겹치는 낱말이 하나도 없어도 장면마다 다른 촬영본이 간다."""
    request = _request(
        segment_texts=["스마트스토어를 시작할 때", "상품을 먼저 고르는 겁니다", "순서가 반대예요", "시장을 먼저 보고"],
        asset_tags=[["broll"], ["broll"], ["broll"], ["broll"]],
    )

    picked = [candidate.selected_asset_id for candidate in KeywordBrollRecommender().recommend(request)]

    assert len(set(picked)) == 4, f"같은 것을 반복했다: {picked}"


def test_more_scenes_than_footage_cycles_instead_of_repeating_one() -> None:
    """촬영본보다 장면이 많으면 돌려 쓴다 -- 하나만 반복하지 않는다."""
    request = _request(
        segment_texts=["가", "나", "다", "라", "마"],
        asset_tags=[["broll"], ["broll"]],
    )

    picked = [candidate.selected_asset_id for candidate in KeywordBrollRecommender().recommend(request)]

    assert set(picked) == {"asset_1", "asset_2"}
    # 이웃한 장면끼리는 달라야 한다 -- 붙어 있는 같은 화면이 가장 눈에 띈다.
    assert all(a != b for a, b in zip(picked, picked[1:], strict=False)), picked


def test_a_real_keyword_match_still_wins() -> None:
    """맞는 것이 있으면 그것이 이긴다 -- 돌려쓰기가 그 판단을 덮지 않는다.

    토큰은 **공백으로만** 나뉜다(`_tokenize`). 한국어 조사가 붙으면
    "사무실에서" != "사무실"이라 안 맞는다 -- 그래서 낱말이 그대로 서는 문장으로
    잰다. 이건 이 시험의 제약이지 제품의 결함이 아니다.
    """
    request = _request(
        segment_texts=["사무실 작업 모습", "아무 말"],
        asset_tags=[["바다"], ["사무실"]],
    )

    picked = [candidate.selected_asset_id for candidate in KeywordBrollRecommender().recommend(request)]

    assert picked[0] == "asset_2", "낱말이 맞는 자산이 이겨야 한다"


def test_one_piece_of_footage_is_still_used() -> None:
    """고를 것이 하나뿐이면 그것을 쓴다 -- 빈손으로 돌려주지 않는다."""
    request = _request(segment_texts=["가", "나"], asset_tags=[["broll"]])

    picked = [candidate.selected_asset_id for candidate in KeywordBrollRecommender().recommend(request)]

    assert picked == ["asset_1", "asset_1"]
