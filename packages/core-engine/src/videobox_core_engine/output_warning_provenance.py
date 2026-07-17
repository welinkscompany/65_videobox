"""Durable operator warnings carried by every locally produced artifact."""
from __future__ import annotations

from typing import Any


_UNKNOWN_RIGHTS = "copyright_confirmation_required"
_UNKNOWN_RIGHTS_NOTE = (
    "copyright_confirmation_required: user-owned media rights are unknown; "
    "local output is allowed, confirm copyright before publishing."
)


def collect_output_warning_provenance(timeline: dict[str, Any]) -> list[str]:
    """Return a stable de-duplicated provenance list from every output clip."""
    warnings: list[str] = []
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict):
            continue
        for clip in track.get("clips", []):
            if not isinstance(clip, dict):
                continue
            for warning in clip.get("warning_provenance", []):
                if isinstance(warning, str) and warning and warning not in warnings:
                    warnings.append(warning)
    return warnings


def output_warning_notes(timeline: dict[str, Any]) -> list[str]:
    provenance = collect_output_warning_provenance(timeline)
    notes = [_UNKNOWN_RIGHTS_NOTE] if _UNKNOWN_RIGHTS in provenance else []
    return notes


def output_metadata(timeline: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "warning_provenance": collect_output_warning_provenance(timeline),
        "warnings": output_warning_notes(timeline),
    }


__all__ = ["collect_output_warning_provenance", "output_metadata", "output_warning_notes"]
