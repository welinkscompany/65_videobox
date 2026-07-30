from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest
from pydantic import ValidationError


def _policy():
    return import_module("videobox_core_engine.yujin_memory_policy")


def _domain():
    return import_module("videobox_domain_models.yujin_memory")


@pytest.mark.parametrize("category", ["pacing", "caption", "audio", "tone", "workflow"])
def test_policy_accepts_only_short_supported_preferences(category: str) -> None:
    result = _policy().validate_yujin_memory_candidate(
        category=category,
        proposed_text="빠른 컷과 짧은 호흡을 선호합니다.",
        source_texts=("영상 템포를 조금 빠르게 해줘.",),
    )

    assert result == "빠른 컷과 짧은 호흡을 선호합니다."


@pytest.mark.parametrize(
    ("category", "text", "code"),
    [
        ("unknown", "짧은 선호", "memory_candidate_category_unsupported"),
        ("tone", "   ", "memory_candidate_text_empty"),
        ("tone", "a" * 281, "memory_candidate_text_too_long"),
        ("tone", "😀" * 260, "memory_candidate_text_too_many_bytes"),
        ("tone", "첫 줄\n둘째 줄", "memory_candidate_text_multiline"),
        (
            "tone",
            "USER: 빠르게 편집해줘 ASSISTANT: 네, 알겠습니다",
            "memory_candidate_raw_transcript_forbidden",
        ),
    ],
)
def test_policy_rejects_unbounded_or_raw_transcript_text(
    category: str,
    text: str,
    code: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{code}$"):
        _policy().validate_yujin_memory_candidate(
            category=category,
            proposed_text=text,
            source_texts=("source",),
        )


@pytest.mark.parametrize(
    "text",
    [
        "password=correct horse battery staple",
        "auth credential is private-value",
        "Authorization: Bearer abc.def.ghi",
        "API_KEY=sk-live-secret",
        "JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY----- ABCDEF",
        "비밀번호는 hunter2 입니다",
        "암호는 외부에 공개하지 않습니다",
        "비밀 토큰은 private-value 입니다",
        "인증 토큰은 abcdefgh 입니다",
        "API 키는 sk-private 입니다",
        "자격증명은 private-value 입니다",
        "쿠키는 session-private 입니다",
        "결제 계좌 번호는 123-45-67890 입니다",
        "카드 번호는 4111 1111 1111 1111 입니다",
        "연락처는 editor@example.com 입니다",
        "전화번호 010-1234-5678",
        "연락처는 +44 20 7946 0958 입니다",
        "Call +44 20 7946 0958",
        "phone 212-555-1212",
        "전화 212-555-1212",
        "카드 4111 1111 1111 1111",
        "payment account 123-456-7890",
        r"소스는 C:\Users\owner\video.mp4",
        r"소스는 \\server\share\video.mp4",
        "소스는 file:///tmp/video.mp4",
        "소스는 local://projects/private/video.mp4",
        "소스는 /Users/owner/video.mp4",
        "소스는 /workspace/private/video.mp4",
        "소스는 /clip.mp4",
        "소스는 ~/clip.mp4",
        "소스는 ./clip.mp4",
        "소스는 ../private/video.mp4",
        r"소스는 C:relative\file.txt",
        "소스는 s3://bucket/private.mp4",
        "미디어는 https://example.invalid/private/video.mp4",
        "https://media.example/video.mp4?X-Amz-Signature=deadbeef",
    ],
)
def test_policy_rejects_secrets_identifiers_and_local_paths(text: str) -> None:
    with pytest.raises(ValueError, match="^memory_candidate_sensitive_text_forbidden$"):
        _policy().validate_yujin_memory_candidate(
            category="workflow",
            proposed_text=text,
            source_texts=("source",),
        )


def test_policy_rejects_text_that_reproduces_a_full_source_message() -> None:
    with pytest.raises(
        ValueError,
        match="^memory_candidate_full_source_message_forbidden$",
    ):
        _policy().validate_yujin_memory_candidate(
            category="pacing",
            proposed_text="선호: 영상 템포를 빠르게 하고 컷을 짧게 해줘",
            source_texts=("영상 템포를 빠르게 하고 컷을 짧게 해줘",),
        )


def test_policy_returns_nfkc_trimmed_single_space_display_text() -> None:
    result = _policy().validate_yujin_memory_candidate(
        category="caption",
        proposed_text="  Ａ형\t자막을  선호합니다.  ",
        source_texts=("자막은 읽기 쉽게 해줘.",),
    )

    assert result == "A형 자막을 선호합니다."


def test_policy_rechecks_bounds_after_nfkc_expansion() -> None:
    with pytest.raises(
        ValueError,
        match="^memory_candidate_text_too_long$",
    ):
        _policy().validate_yujin_memory_candidate(
            category="tone",
            proposed_text="\ufdfa" * 280,
            source_texts=("source",),
        )


@pytest.mark.parametrize("text", ["safe\u0000text", "safe\u200btext"])
def test_policy_rejects_hidden_control_characters(text: str) -> None:
    with pytest.raises(
        ValueError,
        match="^memory_candidate_control_character_forbidden$",
    ):
        _policy().validate_yujin_memory_candidate(
            category="workflow",
            proposed_text=text,
            source_texts=("source",),
        )


def test_domain_candidate_is_frozen_typed_and_pending_only_at_creation() -> None:
    domain = _domain()
    assert {status.value for status in domain.MemoryCandidateStatus} == {
        "pending",
        "approved",
        "rejected",
        "stored",
        "failed",
        "deleted",
    }
    candidate = domain.YujinMemoryCandidate(
        candidate_id="memory-candidate-1",
        project_id="project-1",
        conversation_id="conversation-1",
        client_request_id="request-1",
        source_message_ids=("message-1",),
        memory_scope="creator",
        category="pacing",
        proposed_text="빠른 컷을 선호합니다.",
        status=domain.MemoryCandidateStatus.PENDING,
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        updated_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert candidate.status is domain.MemoryCandidateStatus.PENDING
    with pytest.raises(ValidationError):
        candidate.status = domain.MemoryCandidateStatus.APPROVED
    with pytest.raises(ValidationError):
        domain.YujinMemoryCandidate(
            **candidate.model_dump(),
            provider_body={"secret": "forbidden"},
        )
