"""Choose which part of a B-roll clip to use for a segment (Task 23).

Media analysis already detects scene boundaries and stores them as
``media_scene_windows``.  Until now nothing read them back, so every candidate
range was the first ``needed_sec`` of the file.  For the owner's footage --
ten-minute handheld takes -- that head is typically the camera being set up,
which is the least usable part of the clip.

This module is deliberately pure: it takes the numbers and returns a range, so
the choice can be tested without ffprobe or a real file.  Scene boundaries mark
where the *picture changes*, not where the footage is good, so treat this as a
better-than-the-head heuristic rather than highlight detection.
"""

from __future__ import annotations

from typing import Any, Iterable

__all__ = ["choose_broll_source_window"]


def choose_broll_source_window(
    *,
    duration_sec: float,
    needed_sec: float,
    scene_windows: Iterable[dict[str, Any]],
) -> dict[str, float]:
    """Return ``{"start_sec", "end_sec"}`` covering ``needed_sec`` of footage.

    Falls back to the head of the clip whenever the windows cannot supply a
    long enough stretch, so unanalyzed footage behaves exactly as it did
    before this function existed.
    """
    if not needed_sec > 0:
        raise ValueError("broll_source_window_needed_sec_invalid")

    head = {"start_sec": 0.0, "end_sec": float(min(needed_sec, duration_sec))}
    qualifying = _qualifying_windows(
        scene_windows, needed_sec=needed_sec, duration_sec=duration_sec
    )
    if not qualifying:
        return head

    # The opening window is where the operator is still settling the shot, so
    # it only wins when nothing else can hold the segment.
    preferred = [window for window in qualifying if window[2] > 0] or qualifying
    # Longest first: a longer scene is more likely to be a steady take. Ties go
    # to the earlier window so the choice stays deterministic.
    start_sec = min(preferred, key=lambda window: (-(window[1] - window[0]), window[0]))[0]
    return {"start_sec": float(start_sec), "end_sec": float(start_sec + needed_sec)}


def _qualifying_windows(
    scene_windows: Iterable[dict[str, Any]],
    *,
    needed_sec: float,
    duration_sec: float,
) -> list[tuple[float, float, int]]:
    """Windows long enough to hold the segment without running past the clip."""
    qualifying: list[tuple[float, float, int]] = []
    for index, window in enumerate(scene_windows):
        try:
            start_sec = float(window["start_sec"])
            end_sec = float(window["end_sec"])
        except (KeyError, TypeError, ValueError):
            continue
        # A stored window can outrun the real duration if the file was replaced
        # after analysis; clamp rather than emit a range the renderer cannot read.
        end_sec = min(end_sec, duration_sec)
        if start_sec < 0 or end_sec - start_sec < needed_sec:
            continue
        qualifying.append((start_sec, end_sec, index))
    return qualifying
