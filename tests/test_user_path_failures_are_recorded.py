"""실패를 삼킬 때 왜 삼켰는지는 남겨야 한다.

파이썬 158개 파일 중 로깅을 쓰는 것이 3개고, `except Exception`이 347곳인데 기록을
남기는 것은 1곳이다. 이번 세션에 찾은 문제들 -- 15시간 굳은 작업, 폰트 오타, 초당
180건 DB 폴링, 204를 실패로 읽던 버그 -- 가 하나도 로그에 없었다. 전부 소스를 읽거나
직접 눌러 봐서 찾았다. owner는 그렇게 할 수 없다.

동작은 바꾸지 않는다. fail-open은 그대로 두고 기록만 더한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


def test_a_memory_lookup_failure_says_why_instead_of_looking_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """게이트웨이 장애가 "기억이 원래 없음"과 구분되지 않았다."""
    from videobox_api.yujin_memory_service import YujinMemoryService

    class _ExplodingStore:
        def list_yujin_memory_retrieval_rows(self, **_kwargs):
            raise RuntimeError("memory store refused the connection")

    import asyncio

    service = YujinMemoryService(store=_ExplodingStore(), gateway=object())

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            service.retrieve_approved_memories(
                project_id="p1", conversation_id="c1", query="지난번 편집 어떻게 했지"
            )
        )

    # 빈 결과를 돌려주는 동작은 그대로다.
    assert result == ()
    assert any("memory store refused the connection" in record.getMessage()
               or "memory store refused the connection" in str(record.exc_info)
               for record in caplog.records), "기억 조회 실패가 기록되지 않았다"


def test_a_memory_row_that_will_not_parse_says_so_instead_of_vanishing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """저장된 기억이 스키마와 어긋나면 조용히 후보에서 빠졌다.

    조회 자체는 성공하므로 위의 `:172` 기록은 이 경우를 절대 볼 수 없다.
    필드 하나만 어긋나도 기억 전부가 사라지고 화면에는 "기억이 없음"으로 보인다.
    """
    import asyncio

    from videobox_api.yujin_memory_service import YujinMemoryService

    good = {
        "memory_ref": "m1",
        "external_ref": "ext-" + "a" * 64,
        "text": "컷을 짧게 가는 걸 좋아해요",
        "category": "pacing",
        "project_id": "p1",
        "conversation_id": "c1",
        "status": "approved",
        "storage_status": "stored",
    }
    # 이 프로젝트·대화의 승인·저장된 기억인데 분류만 어긋난다.
    drifted = {**good, "memory_ref": "m2", "category": "새로운분류"}

    class _Store:
        def list_yujin_memory_retrieval_rows(self, **_kwargs):
            return [good, drifted]

    class _Gateway:
        async def search_memory(self, request):
            return {
                "memories": [
                    {
                        "memory_ref": good["memory_ref"],
                        "text": good["text"],
                        "category": good["category"],
                        "external_ref": good["external_ref"],
                    }
                ]
            }

    service = YujinMemoryService(store=_Store(), gateway=_Gateway())

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            service.retrieve_approved_memories(
                project_id="p1", conversation_id="c1", query="지난번 편집 어떻게 했지"
            )
        )

    # 어긋난 줄을 빼는 동작은 그대로다 -- 멀쩡한 기억은 계속 나온다.
    assert [item.text for item in result] == [good["text"]]
    dropped = [
        record
        for record in caplog.records
        if "기억" in record.getMessage() and "m2" in record.getMessage()
    ]
    assert dropped, "읽지 못한 기억 줄이 기록되지 않았다"


def test_the_dropped_memory_report_does_not_repeat_per_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """대화마다 부르는 경로라 줄마다 한 줄씩 찍으면 로그가 못 쓰게 된다."""
    import asyncio

    from videobox_api.yujin_memory_service import YujinMemoryService

    base = {
        "external_ref": "ext-" + "b" * 64,
        "text": "자막은 두 줄까지",
        "category": "없는분류",
        "project_id": "p1",
        "conversation_id": "c1",
        "status": "approved",
        "storage_status": "stored",
    }
    rows = [{**base, "memory_ref": f"m{index}"} for index in range(7)]

    class _Store:
        def list_yujin_memory_retrieval_rows(self, **_kwargs):
            return rows

    service = YujinMemoryService(store=_Store(), gateway=object())

    with caplog.at_level(logging.WARNING):
        assert asyncio.run(
            service.retrieve_approved_memories(
                project_id="p1", conversation_id="c1", query="지난번에 뭐라고 했지"
            )
        ) == ()

    assert len([r for r in caplog.records if "기억" in r.getMessage()]) == 1


def test_a_dropped_clip_that_cannot_be_queued_is_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """드롭 폴더 영상의 분석 예약이 실패하면 태그가 영원히 안 붙는다.
    매일 쓰는 경로인데 화면에도 로그에도 흔적이 없었다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from videobox_api.routers.media_inbox import build_media_inbox_router

    library = tmp_path / "library"
    library.mkdir()
    (library / "clip.mp4").write_bytes(b"video")

    class _ExplodingService:
        def enqueue_analysis(self, **_kwargs):
            raise RuntimeError("analysis store unavailable")

    class _Orchestrator:
        media_analysis_service = _ExplodingService()
        media_analysis_dispatcher = None

        class pipeline:  # noqa: N801 - 실제 orchestrator의 속성 이름을 흉내낸다
            @staticmethod
            def register_broll_asset(**_kwargs):
                return {"asset_id": "a1"}

            class store:
                @staticmethod
                def update_asset_metadata(**_kwargs):
                    return None

    app = FastAPI()
    app.include_router(build_media_inbox_router(_Orchestrator(), library))

    with caplog.at_level(logging.WARNING):
        response = TestClient(app).post(
            "/api/projects/p1/media-inbox/import", json={"filename": "clip.mp4"}
        )

    # 가져오기 자체는 성공해야 한다 -- 분석 실패가 durable import를 되돌리지 않는다.
    assert response.status_code in (200, 201)
    assert any("analysis store unavailable" in record.getMessage()
               or "analysis store unavailable" in str(record.exc_info)
               for record in caplog.records), "분석 예약 실패가 기록되지 않았다"


def test_a_batch_import_that_analyses_fewer_files_than_it_registered_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """한 번에 가져오기에서 분석 예약이 실패한 파일은 `failures`에도 안 들어가
    화면상 성공과 구분되지 않았다. 태그가 안 붙은 촬영본은 검색에서 없는 것이 된다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from videobox_api.routers.assets import build_assets_router

    def _asset(asset_id: str) -> dict:
        return {
            "asset_id": asset_id,
            "asset_type": "broll_video",
            "storage_uri": f"local://projects/p1/assets/imported/{asset_id}.mp4",
            "created_at": "2026-08-10T00:00:00Z",
        }

    class _ExplodingAnalysis:
        def enqueue_analysis(self, **_kwargs):
            raise RuntimeError("analysis store unavailable")

    class _Orchestrator:
        media_analysis_service = _ExplodingAnalysis()
        media_analysis_dispatcher = None

        def register_broll_assets_batch(self, **_kwargs):
            return {"assets": [_asset("a1"), _asset("a2")], "failures": []}

    app = FastAPI()
    app.include_router(build_assets_router(_Orchestrator(), object()))

    with caplog.at_level(logging.WARNING):
        response = TestClient(app).post(
            "/api/projects/p1/assets/broll-video/batch",
            json={"source_paths": ["one.mp4", "two.mp4"]},
        )

    # 등록은 그대로 성공이고 `failures`도 늘어나지 않는다 -- 자산은 실제로 들어왔다.
    assert response.status_code == 201
    body = response.json()
    assert [asset["asset_id"] for asset in body["assets"]] == ["a1", "a2"]
    assert body["failures"] == []
    assert body["analysis_jobs"] == []
    queued = [
        record
        for record in caplog.records
        if "analysis store unavailable" in str(record.exc_info)
    ]
    # 파일마다 한 줄이 아니라 한 번에 모아 남긴다.
    assert len(queued) == 1, "분석 예약 실패가 한 줄로 기록되지 않았다"
    assert "a1" in queued[0].getMessage() and "a2" in queued[0].getMessage()


def _home_summary_client(store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from videobox_api.routers.projects import build_projects_router

    app = FastAPI()
    app.include_router(build_projects_router(store))
    return TestClient(app)


class _HomeStore:
    """홈 카드가 부르는 두 가지만 흉내낸다."""

    def __init__(self, session_error: Exception | None) -> None:
        self._session_error = session_error

    def list_jobs(self, *, project_id: str):
        return []

    def get_latest_editing_session(self, *, project_id: str):
        raise self._session_error


def test_a_home_summary_that_cannot_read_the_draft_says_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """데이터베이스 장애가 화면에서는 "아직 시작한 작업이 없어요"가 됐다."""
    store = _HomeStore(RuntimeError("editing session table is locked"))

    with caplog.at_level(logging.WARNING):
        response = _home_summary_client(store).get("/api/projects/p1/home-summary")

    # 홈이 열리는 동작은 그대로다 -- 초안을 못 읽어도 화면은 뜬다.
    assert response.status_code == 200
    assert response.json()["has_draft"] is False
    assert any(
        "editing session table is locked" in str(record.exc_info)
        for record in caplog.records
    ), "초안 조회 실패가 기록되지 않았다"


def test_a_project_with_no_draft_yet_stays_quiet() -> None:
    """초안이 아직 없는 것은 장애가 아니다. 새 프로젝트를 열 때마다
    경고가 찍히면 진짜 장애가 묻힌다."""
    store = _HomeStore(KeyError("Editing session not found for project: p1"))

    import logging as _logging

    records: list[_logging.LogRecord] = []

    class _Collect(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect(level=_logging.WARNING)
    logger = _logging.getLogger("videobox_api.routers.projects")
    logger.addHandler(handler)
    try:
        response = _home_summary_client(store).get("/api/projects/p1/home-summary")
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    assert response.json()["has_draft"] is False
    assert records == []


def test_every_user_path_swallow_point_carries_a_logger() -> None:
    """네 지점이 로거를 갖고 있는지 파일 단위로 잠근다. 하나가 조용히 빠지면
    다시 "왜 안 되는지 모르겠다"로 돌아간다."""
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "services/api/src/videobox_api/yujin_memory_service.py",
        "services/api/src/videobox_api/routers/media_inbox.py",
        "services/api/src/videobox_api/agent_gateway_client.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "logging.getLogger" in source, f"{relative} 에 로거가 없다"


def test_the_app_configures_logging_so_records_are_attributable() -> None:
    """호출부에 로거를 다는 것만으로는 부족하다. 설정이 없으면 파이썬의 최후
    수단 핸들러가 **메시지만** 찍는다 -- 어느 모듈에서 언제 났는지가 없다.
    컨테이너에서 확인한 실제 상태가 그랬다: `root handlers: []`."""
    import logging

    from videobox_api.main import configure_logging

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        root.handlers.clear()
        configure_logging()

        assert root.handlers, "루트에 핸들러가 붙지 않았다"
        formatter = root.handlers[0].formatter
        assert formatter is not None
        rendered = formatter.format(
            logging.LogRecord(
                name="videobox_api.example", level=logging.WARNING, pathname=__file__,
                lineno=1, msg="무슨 일이 있었는지", args=(), exc_info=None,
            )
        )
        # 어느 모듈에서 났는지와 심각도가 보여야 추적할 수 있다.
        assert "videobox_api.example" in rendered
        assert "WARNING" in rendered
        assert "무슨 일이 있었는지" in rendered
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_creating_the_app_turns_logging_on() -> None:
    # 설정 함수가 있어도 아무도 부르지 않으면 소용이 없다 -- 이 저장소가
    # 여러 번 겪은 패턴이다.
    import inspect

    from videobox_api import main as api_main

    source = inspect.getsource(api_main.create_app)
    assert "configure_logging()" in source


def test_startup_announces_itself_so_the_pipeline_is_provable() -> None:
    """설정이 살아 있다는 것을 로그만 보고 알 수 있어야 한다.

    호출부에 로거를 달아도, 그 경로가 실패해야만 확인이 된다. 시작할 때 한 줄을
    남기면 형식과 핸들러가 실제로 붙었는지를 컨테이너 로그에서 바로 볼 수 있다.
    """
    import inspect

    from videobox_api import main as api_main

    source = inspect.getsource(api_main.create_app)
    assert "_LOGGER.info" in source, "시작 로그가 없다"


def test_configuring_logging_does_not_seize_a_setup_someone_else_owns() -> None:
    """이미 핸들러가 있으면 형식만 남겨 두는 게 아니라 **수준도** 건드리지
    않아야 한다. pytest는 자기 핸들러를 붙이는데, 우리가 수준을 덮어쓰면
    DEBUG를 보려는 테스트가 조용히 아무것도 못 보게 된다."""
    import logging

    from videobox_api.main import configure_logging

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        root.handlers[:] = [logging.NullHandler()]
        root.setLevel(logging.DEBUG)

        configure_logging()

        assert root.level == logging.DEBUG, "남의 로그 수준을 빼앗았다"
        assert len(root.handlers) == 1, "이미 있는 설정에 핸들러를 더했다"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_a_nonsense_log_level_falls_back_instead_of_crashing_startup() -> None:
    """`getattr(logging, name)`은 `FileHandler` 같은 것도 돌려준다. 그것을
    `setLevel`에 넘기면 시작이 통째로 죽는다 -- 오타 하나로 앱이 안 뜬다."""
    import logging
    import os
    from unittest.mock import patch

    from videobox_api.main import configure_logging

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        for bad in ("FileHandler", "BANANA", ""):
            root.handlers.clear()
            with patch.dict(os.environ, {"VIDEOBOX_LOG_LEVEL": bad}):
                configure_logging()
            assert root.level == logging.INFO, f"{bad!r} 에서 기본값으로 떨어지지 않았다"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
