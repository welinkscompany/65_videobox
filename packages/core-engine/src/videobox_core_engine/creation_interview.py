"""Provider-neutral, deterministic creation-interview planning.

Task 7 deliberately keeps this local: a managed driver may implement the same
protocol later, but creation briefs must never need a network provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


MAX_CREATION_INTERVIEW_QUESTIONS = 5


@dataclass(frozen=True, slots=True)
class CreationInterviewQuestion:
    field: str
    prompt: str
    question_id: str | None = None


class CreationInterviewRuntime(Protocol):
    """Plans follow-ups from retained script text without coupling to a vendor."""

    def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]: ...


class DeterministicCreationInterviewRuntime:
    """A transparent local driver used by normal and test execution.

    It only asks for fields not already unambiguously present in the script.
    The heuristics are intentionally conservative; no remote model is called.
    """

    _CANDIDATES = (
        CreationInterviewQuestion("audience", "이 영상은 누구에게 보여줄까요?"),
        CreationInterviewQuestion("tone", "어떤 분위기로 만들까요?"),
        CreationInterviewQuestion("format", "어디에 올릴 영상인가요?"),
        CreationInterviewQuestion("call_to_action", "시청자가 다음에 무엇을 하면 좋을까요?"),
        CreationInterviewQuestion("duration", "원하는 영상 길이가 있나요?"),
    )

    def plan_questions(self, *, script_text: str) -> list[CreationInterviewQuestion]:
        normalized = script_text.casefold()
        known_fields = {
            "audience": ("고객", "시청자", "초보", "직원", "학생", "어린이"),
            "tone": ("친근", "차분", "재미", "전문", "감성", "밝은"),
            "format": ("유튜브", "릴스", "쇼츠", "인스타", "광고"),
            "call_to_action": ("신청", "구매", "방문", "구독", "클릭", "문의"),
            "duration": ("초", "분", "minute", "second"),
        }
        format_destinations = (
            ("유튜브", "youtube", "쇼츠", "shorts"),
            ("인스타", "instagram", "릴스", "reels"),
        )
        contradictory_format = sum(any(term in normalized for term in destination) for destination in format_destinations) > 1
        return [
            question
            for question in self._CANDIDATES
            if question.field == "format" and contradictory_format
            or not any(term in normalized for term in known_fields[question.field])
        ][:MAX_CREATION_INTERVIEW_QUESTIONS]
