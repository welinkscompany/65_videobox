"""의미로 찾았는지 단어로만 찾았는지가 밖으로 나와야 한다.

임베딩 조회가 실패하면 `except Exception`으로 단어 매칭에 조용히 떨어진다.
추천이 갑자기 나빠져도 owner는 원인을 알 수 없고, 결과만 보고는 지금 어느 쪽이
돌았는지 구분할 방법이 없다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.director_proposal_service import (
    SEMANTIC_MATCH,
    WORD_MATCH,
    describe_match_mode,
)


class _Embeddings:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, request):
        if self.fail:
            raise RuntimeError("local model unreachable")

        class _Response:
            vectors = tuple([1.0, 0.0] for _ in request.inputs)

        return _Response()


def test_the_two_modes_are_named_in_the_owners_words() -> None:
    # 화면에 그대로 보일 수 있어야 한다.
    assert describe_match_mode(SEMANTIC_MATCH) == "뜻으로 찾음"
    assert describe_match_mode(WORD_MATCH) == "단어로만 찾음"
    # 모르는 값이 와도 영어 원값을 내보내지 않는다.
    assert describe_match_mode("something_new") == "찾은 방식 확인 중"


def test_a_working_lookup_reports_semantic_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    from videobox_core_engine import director_proposal_service as module

    service = module.DirectorProposalService.__new__(module.DirectorProposalService)
    service.embedding_provider = _Embeddings()
    service.embedding_model_name = "bge-m3"

    class _Store:
        @staticmethod
        def find_local_media_embedding_matches(**_kwargs):
            return [{"asset_id": "asset-1", "score": 0.8}]

    service.store = _Store()

    assets, mode = service._apply_semantic_scores(
        project_id="p1", segment_text="조용한 아침 산책", assets=[{"asset_id": "asset-1"}]
    )

    assert mode == SEMANTIC_MATCH
    assert assets[0]["semantic_score"] == 0.8


def test_a_failed_lookup_reports_that_it_fell_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """로컬 모델이 없을 때. 추천을 막지는 않지만 어느 쪽으로 찾았는지는 말한다."""
    from videobox_core_engine import director_proposal_service as module

    service = module.DirectorProposalService.__new__(module.DirectorProposalService)
    service.embedding_provider = _Embeddings(fail=True)
    service.embedding_model_name = "bge-m3"
    service.store = object()

    assets, mode = service._apply_semantic_scores(
        project_id="p1", segment_text="조용한 아침 산책", assets=[{"asset_id": "asset-1"}]
    )

    assert mode == WORD_MATCH
    # 자산 자체는 그대로 흘려보낸다 -- 추천을 막지 않는다.
    assert assets == [{"asset_id": "asset-1"}]


def test_an_empty_lookup_result_is_word_matching_not_a_semantic_success() -> None:
    """색인이 비어 0건이 돌아오면 의미 점수는 하나도 안 붙는다. 그래 놓고
    `뜻으로 찾음`이라고 말하면 화면이 거짓말을 한다 -- 실제 순위는 전부
    단어 매칭이 정했다."""
    from videobox_core_engine import director_proposal_service as module

    service = module.DirectorProposalService.__new__(module.DirectorProposalService)
    service.embedding_provider = _Embeddings()
    service.embedding_model_name = "bge-m3"

    class _Store:
        @staticmethod
        def find_local_media_embedding_matches(**_kwargs):
            return []

    service.store = _Store()

    assets, mode = service._apply_semantic_scores(
        project_id="p1", segment_text="조용한 아침 산책", assets=[{"asset_id": "asset-1"}]
    )

    assert mode == WORD_MATCH
    assert assets == [{"asset_id": "asset-1"}]


def test_scores_for_other_assets_are_not_a_semantic_success_either() -> None:
    """돌아온 점수가 지금 순위에 올릴 자산과 하나도 겹치지 않으면, 의미 점수는
    하나도 안 붙고 순위는 전부 단어 매칭이 정한다."""
    from videobox_core_engine import director_proposal_service as module

    service = module.DirectorProposalService.__new__(module.DirectorProposalService)
    service.embedding_provider = _Embeddings()
    service.embedding_model_name = "bge-m3"

    class _Store:
        @staticmethod
        def find_local_media_embedding_matches(**_kwargs):
            return [{"asset_id": "somebody-else", "score": 0.9}]

    service.store = _Store()

    assets, mode = service._apply_semantic_scores(
        project_id="p1", segment_text="조용한 아침 산책", assets=[{"asset_id": "asset-1"}]
    )

    assert mode == WORD_MATCH
    assert assets == [{"asset_id": "asset-1"}]


def test_no_embedding_provider_at_all_is_also_word_matching() -> None:
    from videobox_core_engine import director_proposal_service as module

    service = module.DirectorProposalService.__new__(module.DirectorProposalService)
    service.embedding_provider = None
    service.embedding_model_name = None
    service.store = object()

    _assets, mode = service._apply_semantic_scores(
        project_id="p1", segment_text="조용한 아침 산책", assets=[{"asset_id": "asset-1"}]
    )

    assert mode == WORD_MATCH


def test_the_proposal_carries_how_it_matched_so_the_screen_can_say_it() -> None:
    """추천 결과에 실려야 화면이 말할 수 있다. 서비스 안에서만 알고 있으면
    owner에게는 여전히 조용히 나빠지는 것으로 보인다."""
    import inspect

    from videobox_core_engine import director_proposal_service as module

    source = inspect.getsource(module.DirectorProposalService.create)
    assert '"match_mode"' in source, "제안에 찾은 방식이 실리지 않는다"
