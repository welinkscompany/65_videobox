"""문구를 바꿨으면 저장된 분석도 다시 만들어야 한다.

프로젝트 분석 프롬프트를 우리말로 바꿨는데 이미 저장된 결과는 영어인 채로
남았다. 편집기에서 같은 영상이 두 언어로 보이고, 대본 문장과 맞추는 의미검색도
언어가 어긋난 채로 돈다.

캐시 열쇠에 `prompt_version`이 이미 들어 있으니, 그것을 올리면 저절로 다시
분석된다 -- 라이브러리 색인이 쓰는 것과 같은 방식이다.
"""

from __future__ import annotations

from videobox_core_engine.media_analysis import (

    TAG_PROMPT_VERSION,
    VISION_ANALYSIS_PROMPT,
    AnalysisProfile,
    MediaAnalysisService,
)

from conftest import wait_for


def test_the_prompt_version_moved_when_the_prompt_did() -> None:
    # 우리말로 바꾼 것이 v1 이후의 변경이므로 v1로 남아 있으면 안 된다.
    assert "한국어" in VISION_ANALYSIS_PROMPT
    assert TAG_PROMPT_VERSION != "v1", "문구를 바꿨는데 버전이 그대로다"


def test_a_new_prompt_version_produces_a_different_cache_key() -> None:
    """열쇠가 같으면 저장된 영어 결과가 그대로 재사용된다."""
    service = MediaAnalysisService.__new__(MediaAnalysisService)
    service.extractor_version = "v1"
    service.media_probe = object()
    profile = AnalysisProfile(vision_model_name="v", embedding_model_name="e")

    current = service.cache_key(source_sha256="a" * 64, profile=profile)

    import videobox_core_engine.media_analysis as module

    original = module.TAG_PROMPT_VERSION
    try:
        module.TAG_PROMPT_VERSION = "different"
        changed = service.cache_key(source_sha256="a" * 64, profile=profile)
    finally:
        module.TAG_PROMPT_VERSION = original

    assert current != changed


def test_assets_analysed_with_an_old_prompt_come_back_for_another_pass(tmp_path) -> None:
    """버전만 올리면 새 분석은 우리말로 나오지만, 이미 저장된 것은 영어인 채로
    남는다. 낡은 것을 다시 걸어 주는 것까지가 이 작업이다."""
    from videobox_core_engine.media_analysis import assets_needing_reanalysis

    class _Store:
        @staticmethod
        def list_media_analysis(*, project_id: str):
            return [
                {"analysis_id": "a-old", "asset_id": "asset-1", "status": "succeeded",
                 "result": {"cache_key": "old-key"}},
                {"analysis_id": "a-new", "asset_id": "asset-2", "status": "succeeded",
                 "result": {"cache_key": "current-key"}},
                {"analysis_id": "a-run", "asset_id": "asset-3", "status": "running",
                 "result": {"cache_key": "old-key"}},
            ]

    stale = assets_needing_reanalysis(
        store=_Store(), project_id="p1", current_cache_keys={"asset-1": "current-key", "asset-2": "current-key"}
    )

    # 낡은 열쇠로 끝난 것만. 아직 도는 것은 건드리지 않는다.
    assert stale == ["asset-1"]


def test_an_asset_with_no_analysis_is_not_treated_as_stale(tmp_path) -> None:
    # 한 번도 분석 안 한 것은 기존 예약 경로가 맡는다. 여기서 또 걸면 중복이다.
    from videobox_core_engine.media_analysis import assets_needing_reanalysis

    class _Store:
        @staticmethod
        def list_media_analysis(*, project_id: str):
            return []

    assert assets_needing_reanalysis(store=_Store(), project_id="p1", current_cache_keys={"asset-1": "k"}) == []


def test_the_running_app_requeues_stale_analyses_without_being_asked(tmp_path, monkeypatch) -> None:
    """owner가 손으로 다시 돌릴 일이 아니다. 라이브러리 색인과 같은 방식으로
    저절로 잡혀야 한다."""
    import time

    from fastapi.testclient import TestClient

    from videobox_api import main as api_main

    calls: list[str] = []
    monkeypatch.setattr(
        api_main, "assets_needing_reanalysis", lambda **kwargs: calls.append(kwargs["project_id"]) or []
    )

    app = api_main.create_app(
        projects_root=tmp_path / "projects", media_analysis_poll_interval_seconds=0.01
    )
    app.state.store.bootstrap_project("재분석")
    # 이 시험용 앱에는 분석 서비스가 붙지 않는다. 패스가 도는지만 본다.
    class _Service:
        profile = None
        def cache_key(self, **_kwargs): return "k"
        def enqueue_analysis(self, **_kwargs): return None
    app.state.media_analysis_service = _Service()
    # 디스패처가 없으면 분석 자체를 돌리지 않으므로 그 앞에서 넘어간다.
    app.state.media_analysis_dispatcher = lambda **_kwargs: None
    with TestClient(app):
        wait_for(lambda: bool(calls))

    assert calls, "낡은 분석을 찾는 패스가 돌지 않았다"


def test_a_reanalysis_pass_is_bounded_like_the_indexers() -> None:
    """낡은 것을 한꺼번에 다 걸었더니 로컬 모델이 동시에 네 건을 받고 전부
    타임아웃했다. 라이브러리 색인처럼 한 번에 몇 개만 걸고 나머지는 다음 차례로
    둔다."""
    from videobox_core_engine.media_analysis import assets_needing_reanalysis

    class _Store:
        @staticmethod
        def list_media_analysis(*, project_id: str):
            return [
                {"analysis_id": f"a{i}", "asset_id": f"asset-{i}", "status": "succeeded",
                 "result": {"cache_key": "old"}}
                for i in range(5)
            ]

    keys = {f"asset-{i}": "current" for i in range(5)}

    assert len(assets_needing_reanalysis(store=_Store(), project_id="p1", current_cache_keys=keys, limit=2)) == 2
    # 한도를 안 주면 예전처럼 전부 -- 호출부가 정한다.
    assert len(assets_needing_reanalysis(store=_Store(), project_id="p1", current_cache_keys=keys)) == 5
