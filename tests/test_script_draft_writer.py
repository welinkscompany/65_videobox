"""대본도 영상도 없는 사람이 첫 걸음을 뗄 수 있게, 유진이 대본 초안을 쓴다.

**여기서 지키는 것은 셋이다.**

1. **구조화 출력으로만 묻는다.** 자유형 대화로 같은 것을 물으면 생각 과정이
   영어로 새어 나온다. 배관만 보면 답이 온 것처럼 보이지만, owner가 받는 것은
   한국어 대본이 아니다.
2. **못 하면 거절한다.** 빈 초안이나 영어 초안을 그대로 넘기면 owner는 그것을
   고쳐 쓸 수 있는 글로 알고 기획까지 들고 간다.
3. **길이와 장면 수를 요청에 싣는다.** 60초 다섯 장면과 3분 열 장면은 전혀
   다른 글이다. 물어보지 않으면 모델이 매번 다른 길이를 돌려준다.
"""
from __future__ import annotations

import pytest

from videobox_core_engine.script_draft_writer import (
    ScriptDraftUnavailable,
    ScriptDraftWriter,
)


class _Runtime:
    """물어본 말과 돌려준 답만 붙잡는다. 여기서 재는 것은 글 품질이 아니라
    **무엇을 물었고 무엇을 받아들이는가**이다."""

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


def _draft(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "집에서 만드는 라면 세 가지",
        "scenes": [
            {"narration": "오늘은 라면을 세 가지 방법으로 끓여 볼게요.", "visual": "끓는 냄비 가까이"},
            {"narration": "첫 번째는 계란을 마지막에 넣는 방법입니다.", "visual": "계란을 넣는 손"},
        ],
    }
    base.update(overrides)
    return base


def test_it_asks_in_korean_and_says_how_long_and_how_many_scenes() -> None:
    runtime = _Runtime(_draft())

    ScriptDraftWriter(runtime_service=runtime).write(
        project_id="p", topic="집에서 라면 맛있게 끓이는 법", duration_sec=60, scene_count=5,
    )

    asked = runtime.prompts[0]
    assert "집에서 라면 맛있게 끓이는 법" in asked
    # 한국어로 답하라고 적지 않으면 영어로 나온다(§10.15 4항에서 같은 것을 배웠다).
    assert "한국어" in asked
    assert "60" in asked and "5" in asked


def test_it_uses_structured_output_not_free_conversation() -> None:
    """자유형으로 물으면 생각 과정이 영어로 새어 나온다. 스키마가 그 문을 닫는다."""
    runtime = _Runtime(_draft())

    ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    schema = runtime.schemas[0]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"title", "scenes"}
    assert schema["properties"]["scenes"]["type"] == "array"
    assert runtime.task_types[0].value == "script_draft"


def test_it_returns_both_one_script_and_the_scene_lines() -> None:
    """화면은 둘 다 필요하다 -- owner는 글을 고치고, 기획은 장면을 읽는다."""
    runtime = _Runtime(_draft())

    written = ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert written.title == "집에서 만드는 라면 세 가지"
    assert [scene.scene_number for scene in written.scenes] == [1, 2]
    assert written.scenes[0].narration == "오늘은 라면을 세 가지 방법으로 끓여 볼게요."
    assert written.scenes[0].visual == "끓는 냄비 가까이"
    # 고칠 수 있는 글 한 덩이. 장면 줄을 그대로 이어 붙인 것이라 둘이 어긋나지 않는다.
    assert written.script_text == (
        "오늘은 라면을 세 가지 방법으로 끓여 볼게요.\n첫 번째는 계란을 마지막에 넣는 방법입니다."
    )


def test_a_scene_without_a_picture_note_is_still_a_scene() -> None:
    """`visual`은 있으면 좋은 것이지 없으면 초안을 버릴 이유가 아니다."""
    runtime = _Runtime(_draft(scenes=[{"narration": "라면을 끓입니다."}]))

    written = ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert written.scenes[0].visual == ""


def test_an_empty_draft_is_refused_not_handed_over() -> None:
    """빈 초안을 넘기면 owner는 빈 칸을 보고 자기가 잘못 눌렀다고 생각한다."""
    runtime = _Runtime(_draft(scenes=[]))

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert str(exc.value) == "script_draft_empty"


def test_blank_narration_lines_do_not_count_as_a_draft() -> None:
    runtime = _Runtime(_draft(scenes=[{"narration": "   "}, {"narration": ""}]))

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert str(exc.value) == "script_draft_empty"


def test_an_english_answer_is_refused_because_the_owner_asked_in_korean() -> None:
    """구조화 출력을 써도 생각 과정이 영어로 새는 일이 있었다. 그대로 넘기면
    owner는 고칠 수 없는 글을 받는다."""
    runtime = _Runtime(_draft(scenes=[
        {"narration": "오늘은 라면을 끓여 볼게요."},
        {"narration": "Let me think about the second scene here."},
    ]))

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert str(exc.value) == "script_draft_not_korean"


def test_a_silent_model_is_reported_not_papered_over() -> None:
    class _Silent:
        def generate_structured(self, **_kwargs):
            raise RuntimeError("local runtime unavailable")

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=_Silent()).write(project_id="p", topic="라면")

    assert str(exc.value) == "script_draft_writer_unavailable"


def test_running_out_of_time_is_not_the_same_as_not_answering() -> None:
    """**2026-08-21 실측이 이 갈래의 근거다.** 60초·5장면은 8.0초에 왔고
    5분·12장면은 28.7초까지 갔다 -- 로컬 런타임 기본 상한이 30초다.

    둘을 "잠시 뒤 다시"로 뭉치면 owner는 같은 길이로 몇 번이고 다시 누른다.
    받아쓰기에서 이미 같은 함정을 밟았다."""

    class _SlowRuntime:
        def generate_structured(self, **_kwargs):
            error = RuntimeError("timed out")
            error.error_code = "LOCAL_TIMEOUT"
            raise error

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=_SlowRuntime()).write(
            project_id="p", topic="라면", duration_sec=300, scene_count=12,
        )

    assert str(exc.value) == "script_draft_took_too_long"


def test_a_shapeless_answer_is_refused() -> None:
    """스키마를 줘도 모델이 다른 모양을 돌려줄 수 있다. 그때 터지는 대신 거절한다."""
    runtime = _Runtime({"title": "제목", "scenes": ["줄 하나"]})

    with pytest.raises(ScriptDraftUnavailable) as exc:
        ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면")

    assert str(exc.value) == "script_draft_empty"


def test_a_missing_title_falls_back_to_the_topic_instead_of_failing() -> None:
    """제목은 대본이 아니다. 제목이 없다고 쓸 수 있는 대본을 버리지 않는다."""
    runtime = _Runtime(_draft(title="  "))

    written = ScriptDraftWriter(runtime_service=runtime).write(project_id="p", topic="라면 끓이기")

    assert written.title == "라면 끓이기"
