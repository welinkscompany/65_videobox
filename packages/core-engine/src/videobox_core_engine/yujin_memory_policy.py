"""Pure, bounded policy for non-executing Yujin memory candidates."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence


SUPPORTED_CATEGORIES = frozenset(
    {"pacing", "caption", "audio", "tone", "workflow"}
)
MAX_PROPOSED_TEXT_CHARACTERS = 280
MAX_PROPOSED_TEXT_UTF8_BYTES = 1024

_RAW_TRANSCRIPT = re.compile(
    r"(?:^|\s)(?:user|assistant|system|사용자|어시스턴트)\s*:",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"\b(?:password|passwd|secret|auth|authorization|credential|bearer|jwt|"
    r"api[\s_-]*key|payment|account|card|"
    r"access[\s_-]*token|refresh[\s_-]*token|oauth|cookie)\b",
    re.IGNORECASE,
)
_KOREAN_SENSITIVE = re.compile(
    r"(?:"
    r"비밀번호|비밀\s*번호|암호|비밀|인증|토큰|"
    r"api\s*키|자격\s*증명|쿠키|결제|"
    r"계좌(?:\s*(?:번호|정보))?|"
    r"카드\s*(?:번호|정보|결제)|연락처"
    r")(?=$|[\s:=]|은|는|이|가|을|를|와|과|으로|로)",
    re.IGNORECASE,
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.")
_PROVIDER_TOKEN = re.compile(
    r"(?:\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bxox[a-z]-[A-Za-z0-9-]{16,}\b|"
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b|"
    r"\bAIza[A-Za-z0-9_-]{20,}\b|"
    r"\bya29\.[A-Za-z0-9_-]{16,}\b|"
    r"\bhf_[A-Za-z0-9]{16,}\b)"
)
_PRIVATE_KEY_PEM = re.compile(
    r"-----BEGIN (?:[A-Z0-9][A-Z0-9 -]* )?PRIVATE KEY-----",
    re.IGNORECASE,
)
_EMAIL = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])",
    re.UNICODE,
)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:0\d{1,2}[-.\s]?)"
    r"\d{3,4}[-.\s]?\d{4}(?!\d)"
)
_INTERNATIONAL_PHONE = re.compile(
    r"(?<![\w+])\+\d{1,3}(?:[ .()/-]*\d){7,14}(?!\d)"
)
_CONTACT_LABEL = re.compile(
    r"(?i)(?:phone|telephone|mobile|전화(?:번호)?|휴대폰)"
    r"\s*[:=]?\s*\d{2,4}(?:[-.\s]\d{2,4}){2,3}"
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PATH = re.compile(
    r"(?:\b(?:file|local)://|\\\\[^\s\\/]+[\\/]|"
    r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|"
    r"(?<![A-Za-z0-9])[A-Za-z]:(?![\\/])(?:[^:\s\\/]+[\\/])+[^\s\\/]+|"
    r"(?:^|\s)(?:~|\.\.?)[\\/][^\s]+|"
    r"(?:^|\s)/(?!/)[^\s/]+(?:/[^\s/]+)*)",
    re.IGNORECASE,
)
_REMOTE_URI = re.compile(
    r"\b(?:s3|gs|gcs|az|azure|ftp|sftp|ssh|data)://\S+",
    re.IGNORECASE,
)
_WEB_URL = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


def _canonical_text(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).split()
    ).casefold()


def _display_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"[^\S\r\n]+", " ", normalized).strip()


def validate_yujin_memory_candidate(
    *,
    category: str,
    proposed_text: str,
    source_texts: Sequence[str],
) -> str:
    if category not in SUPPORTED_CATEGORIES:
        raise ValueError("memory_candidate_category_unsupported")
    if not proposed_text.strip():
        raise ValueError("memory_candidate_text_empty")
    if len(proposed_text) > MAX_PROPOSED_TEXT_CHARACTERS:
        raise ValueError("memory_candidate_text_too_long")
    if len(proposed_text.encode("utf-8")) > MAX_PROPOSED_TEXT_UTF8_BYTES:
        raise ValueError("memory_candidate_text_too_many_bytes")
    if "\r" in proposed_text or "\n" in proposed_text:
        raise ValueError("memory_candidate_text_multiline")
    display_text = _display_text(proposed_text)
    if len(display_text) > MAX_PROPOSED_TEXT_CHARACTERS:
        raise ValueError("memory_candidate_text_too_long")
    if len(display_text.encode("utf-8")) > MAX_PROPOSED_TEXT_UTF8_BYTES:
        raise ValueError("memory_candidate_text_too_many_bytes")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in display_text
    ):
        raise ValueError("memory_candidate_control_character_forbidden")
    if _RAW_TRANSCRIPT.search(display_text):
        raise ValueError("memory_candidate_raw_transcript_forbidden")
    if any(
        pattern.search(display_text)
        for pattern in (
            _SECRET,
            _KOREAN_SENSITIVE,
            _JWT,
            _PROVIDER_TOKEN,
            _PRIVATE_KEY_PEM,
            _EMAIL,
            _PHONE,
            _INTERNATIONAL_PHONE,
            _CONTACT_LABEL,
            _CARD,
            _PATH,
            _REMOTE_URI,
            _WEB_URL,
        )
    ):
        raise ValueError("memory_candidate_sensitive_text_forbidden")

    candidate = _canonical_text(display_text)
    for source_text in source_texts:
        source = _canonical_text(source_text)
        if source and source in candidate:
            raise ValueError(
                "memory_candidate_full_source_message_forbidden"
            )
    return display_text


def is_yujin_memory_retrieval_query_safe(value: str) -> bool:
    """Scan the full user prompt before any bounded provider projection."""

    display_text = _display_text(value)
    if (
        not display_text
        or "\r" in value
        or "\n" in value
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs"}
            for character in display_text
        )
        or _RAW_TRANSCRIPT.search(display_text)
    ):
        return False
    return not any(
        pattern.search(display_text)
        for pattern in (
            _SECRET,
            _KOREAN_SENSITIVE,
            _JWT,
            _PROVIDER_TOKEN,
            _PRIVATE_KEY_PEM,
            _EMAIL,
            _PHONE,
            _INTERNATIONAL_PHONE,
            _CONTACT_LABEL,
            _CARD,
            _PATH,
            _REMOTE_URI,
            _WEB_URL,
        )
    )


__all__ = [
    "MAX_PROPOSED_TEXT_CHARACTERS",
    "MAX_PROPOSED_TEXT_UTF8_BYTES",
    "SUPPORTED_CATEGORIES",
    "is_yujin_memory_retrieval_query_safe",
    "validate_yujin_memory_candidate",
]
