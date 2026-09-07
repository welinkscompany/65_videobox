"""다시 만든 타임라인이 화면 크기를 잃는다 — 실측 2026-09-06.

빈 편집판은 가로(1920x1080)로 열린다. 그런데 소재를 넣고 부분 재생성을 돌리면
새 타임라인에 `output`이 안 실리고, 완성본 계획이 **세로 기본값(1080x1920)**으로
떨어진다. 실기에서 가로로 시작한 편집본이 세로 mp4로 나왔다.

대표님은 가로 영상을 만든다(`노마드루이스`). 이건 실제로 걸리는 자리다.
"""

from __future__ import annotations

import json

from videobox_core_engine._pipeline_private_helpers import _timeline_output_settings


def test_the_frame_size_survives_a_rebuild() -> None:
    source = {"output": {"width": 1920, "height": 1080, "duration_sec": 5.0}}

    assert _timeline_output_settings(source) == {"output": {"width": 1920, "height": 1080, "duration_sec": 5.0}}


def test_an_old_timeline_that_says_it_another_way_still_counts() -> None:
    """옛 타임라인은 `output` 대신 낱개 칸으로 적었다. 둘 다 읽는다."""
    source = {"video_width": 1920, "video_height": 1080}

    assert _timeline_output_settings(source) == {"output": {"width": 1920, "height": 1080}}


def test_a_timeline_that_never_said_it_adds_nothing() -> None:
    """안 적힌 것을 지어내지 않는다 -- 기본값은 계획을 만드는 자리가 정한다."""
    assert _timeline_output_settings({}) == {}


def test_the_rebuilt_timeline_actually_carries_it(tmp_path) -> None:
    """함수만 보는 시험은 배관만 본다 -- **실제로 저장된 타임라인**을 본다.

    오늘 세 번, 내가 쓴 시험이 검증 대상을 안 밟았다. 여기서는 API로 부분
    재생성을 돌리고 그 결과 타임라인에 화면 크기가 남았는지 본다.
    """
    from fastapi.testclient import TestClient

    from videobox_api.main import create_app

    from tests.test_api import _create_timeline_review_project  # type: ignore[attr-defined]

    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_timeline_review_project(client, tmp_path)
    session = client.post(
        f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job_id}
    ).json()

    started = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={
            "expected_revision": session["session_revision"],
            "segment_ids": ["seg_001"],
            "fields": ["broll"],
        },
    )

    assert started.status_code == 202, started.text
    # 목록 주소가 없으므로 저장된 파일을 직접 읽는다 -- 화면이 아니라 **저장된
    # 것**을 봐야 한다([[videobox-verify-saves-on-the-server-not-the-screen]]).
    written = sorted(tmp_path.glob(f"**/{project_id}/timelines/*.json")) or sorted(tmp_path.glob("**/timelines/*.json"))
    assert written, "타임라인이 하나도 안 저장됐다"
    rebuilt = json.loads(written[-1].read_text(encoding="utf-8"))
    assert rebuilt.get("output") or rebuilt.get("video_width"), (
        f"다시 만든 타임라인이 화면 크기를 잃었다: {sorted(rebuilt)}"
    )
