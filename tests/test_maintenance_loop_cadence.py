"""The idle stack was never idle.

With nobody using the app, the workspace container sat at ~33% CPU and
Postgres at ~41%, and the database committed ~180 transactions a second.
The cause was the maintenance loop's own cadence: it ran every 50 ms, and
each pass listed every project and then queried each of them -- three times
over, because recovery, dispatch polling and event pruning all shared the
one loop body.

Pruning is the clearest case. It deletes events older than 30 days; running
that DELETE twenty times a second cannot find anything the previous pass
missed.
"""

from __future__ import annotations

import inspect
import time

from conftest import wait_for

import pytest
from fastapi.testclient import TestClient

from videobox_api import main as api_main


def test_the_maintenance_loop_does_not_poll_twenty_times_a_second() -> None:
    default = inspect.signature(api_main.create_app).parameters["media_analysis_poll_interval_seconds"].default

    # Fast enough that analysis still starts while the owner is looking at the
    # screen, slow enough that an idle stack stays idle.
    assert default >= 1.0
    assert default <= 5.0


def test_pruning_thirty_day_old_events_runs_far_less_often_than_dispatch() -> None:
    # A 30-day retention window does not need a sub-second cadence. Tying it
    # to the dispatch interval is what made an idle stack run DELETEs
    # continuously.
    assert api_main.HERMES_EVENT_PRUNE_INTERVAL_SECONDS >= 300


def test_a_failing_prune_does_not_fall_back_to_running_every_second(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the hourly schedule is that an unhealthy database stops
    being hammered. If a raising prune left the next-run time unset, the loop
    would retry it on every pass -- reintroducing the load exactly when the
    database can least afford it."""
    calls = 0

    async def failing_prune(_app) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(api_main, "_prune_hermes_run_events", failing_prune)

    app = api_main.create_app(
        projects_root=tmp_path / "projects",
        media_analysis_poll_interval_seconds=0.01,
    )
    with TestClient(app):
        # 한 번은 돌아야 하고, 그 뒤로 여러 번 돌 수 있는 시간을 준다.
        # 여기서 지키는 것은 **실패한 정비가 다시 안 걸린다**이므로, 기다린 뒤에도
        # 1회여야 한다.
        wait_for(lambda: calls >= 1)
        time.sleep(0.3)

    assert calls == 1, f"a failing prune ran {calls} times instead of keeping its schedule"


def test_a_failing_maintenance_pass_says_why_and_keeps_running(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """뒤에서 도는 정비 한 바퀴가 통째로 `except Exception: pass`에 감싸여
    있었다. 분석 폴링, 라이브러리 색인, 기동 복구, 이벤트 정리가 전부 그
    안에 있으니 무엇이 계속 터져도 화면은 정상이고 로그는 비어 있었다.

    이유는 남기되 동작은 그대로다 -- 한 바퀴가 터져도 작업자는 계속 돌아야
    한다."""
    import logging

    calls = 0

    async def failing_poll(_app, *, recover_running: bool) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("데이터베이스에 닿지 못했습니다")

    monkeypatch.setattr(api_main, "_poll_media_analysis", failing_poll)

    with caplog.at_level(logging.WARNING, logger="videobox_api.main"):
        app = api_main.create_app(
            projects_root=tmp_path / "projects",
            media_analysis_poll_interval_seconds=0.01,
        )
        with TestClient(app):
            wait_for(lambda: calls > 1)

    assert calls > 1, f"작업자가 첫 실패에서 멈췄습니다 (calls={calls})"

    records = [record for record in caplog.records if record.name == "videobox_api.main"]
    assert any(
        "데이터베이스에 닿지 못했습니다" in (record.exc_text or "")
        or "데이터베이스에 닿지 못했습니다" in str(record.exc_info)
        for record in records
    ), [record.getMessage() for record in records]


def test_the_analysis_cache_is_actually_pruned(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`prune_stale_media_analysis_cache` had tests but no caller, so
    `media_analysis_cache` and `media_embeddings` grew forever. A retention
    policy nobody runs is not a retention policy."""
    pruned: list[str] = []

    def fake_prune(self, *, project_id: str, retention_days: int = 30) -> int:
        pruned.append(project_id)
        return 0

    monkeypatch.setattr(
        "videobox_storage.local_project_store.LocalProjectStore.prune_stale_media_analysis_cache",
        fake_prune,
    )
    monkeypatch.setattr(api_main, "HERMES_EVENT_PRUNE_INTERVAL_SECONDS", 0.05)

    app = api_main.create_app(
        projects_root=tmp_path / "projects",
        media_analysis_poll_interval_seconds=0.01,
    )
    app.state.store.bootstrap_project("보관 정리")
    with TestClient(app):
        wait_for(lambda: bool(pruned))

    assert pruned, "analysis cache retention never ran"
