from __future__ import annotations


def canonical_source_uri(value: object) -> str:
    return str(value or "").strip()
