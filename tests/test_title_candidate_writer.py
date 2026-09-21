"""확정된 대본에서 유튜브 제목 후보 여러 개를 뽑는다(제목 선택 게이트, W1015).

`script_draft_writer.py`와 같은 원칙을 따른다 -- 구조화 출력으로만 묻고,
못 하면 조용히 넘기지 않는다.
"""
from __future__ import annotations

import pytest

from videobox_core_engine.title_candidate_writer import (
    TitleCandidatesUnavailable,
    TitleCandidateWriter,
)


class _Runtime:
    def __init__(self, answer: dict[str, object]) -> None:
        self.answer = answer
        self.prompts: list[str] = []
        self.task_types: list[object] = []
        self.schemas: list[dict[str, object]] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.prompts.append(prompt)
        self.task_types.append(task_type)
        self.schemas.append(response_schema)
        answer = self.answer

        class _Response:
            output_data = answer

        return _Response()


def _titles(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "titles": ["라면 맛있게 끓이는 법 3가지", "이 라면 레시피 하나면 끝", "집라면 업그레이드하기"],
    }
    base.update(overrides)
    return base


def test_it_asks_for_titles_in_korean_using_the_confirmed_script() -> None:
    runtime = _Runtime(_titles())

    TitleCandidateWriter(runtime_service=runtime).write(
        project_id="p", script_text="오늘은 라면을 세 가지 방법으로 끓여 볼게요.",
    )

    asked = runtime.prompts[0]
    assert "오늘은 라면을 세 가지 방법으로 끓여 볼게요." in asked
    assert "한국어" in asked
    assert runtime.task_types[0].value == "title_candidates"


def test_it_uses_structured_output() -> None:
    runtime = _Runtime(_titles())

    TitleCandidateWriter(runtime_service=runtime).write(project_id="p", script_text="라면")

    schema = runtime.schemas[0]
    assert schema["type"] == "object"
    assert schema["required"] == ["titles"]
    assert schema["properties"]["titles"]["type"] == "array"


def test_it_returns_the_titles_in_order() -> None:
    runtime = _Runtime(_titles())

    written = TitleCandidateWriter(runtime_service=runtime).write(
        project_id="p", script_text="라면"
    )

    assert written == (
        "라면 맛있게 끓이는 법 3가지", "이 라면 레시피 하나면 끝", "집라면 업그레이드하기",
    )


def test_blank_and_duplicate_titles_are_dropped() -> None:
    runtime = _Runtime(_titles(titles=["같은 제목", "  ", "같은 제목", "다른 제목"]))

    written = TitleCandidateWriter(runtime_service=runtime).write(
        project_id="p", script_text="라면"
    )

    assert written == ("같은 제목", "다른 제목")


def test_an_empty_answer_is_refused() -> None:
    runtime = _Runtime(_titles(titles=[]))

    with pytest.raises(TitleCandidatesUnavailable) as exc:
        TitleCandidateWriter(runtime_service=runtime).write(project_id="p", script_text="라면")

    assert str(exc.value) == "title_candidates_empty"


def test_an_english_title_is_refused() -> None:
    runtime = _Runtime(_titles(titles=["Ramen Tips", "라면 끓이기"]))

    with pytest.raises(TitleCandidatesUnavailable) as exc:
        TitleCandidateWriter(runtime_service=runtime).write(project_id="p", script_text="라면")

    assert str(exc.value) == "title_candidates_not_korean"


def test_a_silent_model_is_reported_not_papered_over() -> None:
    class _Silent:
        def generate_structured(self, **_kwargs):
            raise RuntimeError("local runtime unavailable")

    with pytest.raises(TitleCandidatesUnavailable) as exc:
        TitleCandidateWriter(runtime_service=_Silent()).write(
            project_id="p", script_text="라면"
        )

    assert str(exc.value) == "title_candidate_writer_unavailable"


def test_an_empty_script_is_rejected_before_asking_the_model() -> None:
    runtime = _Runtime(_titles())

    with pytest.raises(TitleCandidatesUnavailable) as exc:
        TitleCandidateWriter(runtime_service=runtime).write(project_id="p", script_text="  ")

    assert str(exc.value) == "title_candidates_script_empty"
    assert runtime.prompts == []
