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
