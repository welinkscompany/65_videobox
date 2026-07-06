from __future__ import annotations


VALID_CANONICAL_TRACK_TYPES = {"narration", "broll", "bgm"}


def canonical_track_type(value: object) -> str:
    return str(value or "").strip().lower()
