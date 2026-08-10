"""자산 하나는 임베딩 하나로만 겨뤄야 한다.

분석 프롬프트를 바꾸고 낡은 것을 다시 돌렸더니, 같은 자산이 옛 영어 임베딩과
새 우리말 임베딩을 **둘 다** 갖게 됐다. 검색은 성공한 분석 전부를 가져오므로
한 영상이 두 번 나오고, 그중 낡은 쪽이 이길 수도 있다.
"""

from __future__ import annotations

from pathlib import Path

from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_storage.local_project_store import LocalProjectStore


def _analysis(store, project_id: str, asset_id: str, cache_key: str, embedding: list[float]):
    analysis = store.create_media_analysis(
        project_id=project_id, asset_id=asset_id,
        idempotency_key=f"{asset_id}:{cache_key}", cache_key=cache_key,
    )
    analysis_id = str(analysis["analysis_id"])
    store.claim_media_analysis(project_id=project_id, analysis_id=analysis_id)
    store.record_media_embedding(
        project_id=project_id, analysis_id=analysis_id, source_sha256=asset_id,
        profile_hash=cache_key, embedding=embedding,
    )
    store.complete_media_analysis(
        project_id=project_id, analysis_id=analysis_id, expected_attempt=1,
        result={"cache_key": cache_key}, status=MediaAnalysisStatus.SUCCEEDED,
    )
    return analysis_id


def test_only_the_newest_analysis_of_an_asset_competes(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("임베딩 중복")
    project_id = project.project_id

    old = _analysis(store, project_id, "asset-1", "old-key", [1.0, 0.0])
    new = _analysis(store, project_id, "asset-1", "new-key", [0.0, 1.0])

    matches = store.find_local_media_embedding_matches(
        project_id=project_id, query_embedding=[1.0, 0.0], limit=10
    )

    # 한 자산은 한 번만 나온다.
    assert [match["asset_id"] for match in matches] == ["asset-1"]
    # 그리고 그 하나는 최신 분석이다 -- 낡은 쪽이 점수가 높아도 마찬가지다.
    assert matches[0]["analysis_id"] == new
    assert matches[0]["analysis_id"] != old
