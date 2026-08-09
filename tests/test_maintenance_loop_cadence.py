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
        # Long enough for many passes at a 10 ms cadence.
        time.sleep(0.6)

    assert calls == 1, f"a failing prune ran {calls} times instead of keeping its schedule"


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
        time.sleep(0.4)

    assert pruned, "analysis cache retention never ran"
