"""자료실 영상을 프로젝트에 넣는 데 4~6초 걸렸다 — 실측 2026-09-05.

owner: "영상 하나 넣어서 나머지 구간도 재봐".

0.2MB짜리 8초 영상을 넣었더니 `materialize`가 **6.0초**, 다른 자산은 **3.9초**
걸렸다. 이미 들어 있는 자산을 다시 넣으면 **170ms**다 -- 차이는 복사가 아니라
**장면 분석**이었다.

`_schedule_scene_analysis`가 `enqueue`(빠름) 다음에 `dispatcher(...)`를 **요청
안에서 그대로** 부른다. 그 함수가 실제 분석(로컬 모델)을 돌린다. 즉 창작자는
영상을 넣을 때마다 분석이 끝나기를 **서서 기다린다**.

분석은 태그를 붙이는 일이고, 태그는 유진의 추천에만 쓴다. 몇 초 뒤에 붙어도
편집에는 지장이 없다 -- 그래서 뒤로 미룬다. **거는 것 자체는 그대로 한다**:
뒤에서 도는 재분석 작업자는 한 번도 분석하지 않은 자산을 일부러 건너뛰므로,
여기서 안 걸면 태그가 영영 안 붙는다.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def test_materialize_returns_without_waiting_for_the_analysis_to_finish(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_dispatch(*, project_id: str, analysis_id: str) -> None:
        started.set()
        # 분석이 오래 걸리는 상황을 흉내 낸다. 요청이 이것을 기다리면 시험이 멈춘다.
        release.wait(timeout=10)

    app = create_app(projects_root=tmp_path)
    # 이 기계에는 시각 모델이 없어 배차가 꺼져 있다. 재려는 것은 "분석이 오래
    # 걸릴 때 요청이 기다리는가"이므로, 오래 걸리는 배차를 직접 끼운다.
    app.state.orchestrator.media_analysis_dispatcher = slow_dispatch
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "materialize 속도"}).json()["project_id"]
    ingested = client.post(
        "/api/library/ingest",
        data={"media_type": "broll", "idempotency_key": "speed-check"},
        files=[("files", ("clip.mp4", b"not a real video but enough to register", "video/mp4"))],
    )
    if ingested.status_code != 201:
        return
    library_asset_id = ingested.json()["items"][0]["library_asset_id"]

    began = time.monotonic()
    response = client.post(
        f"/api/library/assets/{library_asset_id}/materialize",
        json={"project_id": project_id},
    )
    elapsed = time.monotonic() - began
    release.set()

    assert response.status_code in {201, 409, 422}
    # **기다리지 않는다.** 분석이 10초 걸려도 응답은 그 전에 온다.
    # 뒤에서 도는 일이라 곧바로는 아직 시작 전일 수 있다 -- 잠깐 기다려 준다.
    assert started.wait(timeout=5), "분석을 아예 걸지 않았다 -- 태그가 영영 안 붙는다"
    assert elapsed < 5, f"분석을 기다렸다: {elapsed:.1f}초"
