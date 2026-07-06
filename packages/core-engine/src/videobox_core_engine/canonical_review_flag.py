from __future__ import annotations


VALID_CANONICAL_REVIEW_FLAG_CODES = {
    "segment_review_required",
    "broll_review_required",
    "tts_replacement_review_required",
}


def canonical_review_flag_code(value: object) -> str:
    return str(value or "").strip().lower()
