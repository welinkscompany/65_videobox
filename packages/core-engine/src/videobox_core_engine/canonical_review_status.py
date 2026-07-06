from __future__ import annotations


def canonical_review_status(value: object, *, default: str) -> str:
    return str(value or default).strip().lower() or default
