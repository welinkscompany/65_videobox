from __future__ import annotations


DEFAULT_OPERATOR_REVIEW_TEXT = "Operator review required before approval or output."


def canonical_operator_review_text(value: object) -> str:
    text = str(value or "").strip()
    return text or DEFAULT_OPERATOR_REVIEW_TEXT
