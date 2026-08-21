"""대본 한 줄을 그림 모델이 알아듣는 말로 바꾸는 자리.

**2026-08-21 실측이 이 파일의 근거다.** 같은 씨앗(606386459)·같은 설정으로 두 번 만들었다.

| 넣은 말 | 나온 것 |
|---|---|
| `자막은 따로, 음악도 따로 붙입니다` | 픽셀아트 당나귀 두 마리 |
| 같은 뜻의 영어 묘사 | 실제로 그 장면 |

증거: `artifacts/scene-image-check/korean.png`, `english.png`.

**그림 모델은 한국어를 거절하지 않는다.** 아무 그림이나 그럴듯하게 내놓는다 --
그래서 배관만 보면 다 되는 것처럼 보이고, owner만 24초 뒤에 당나귀를 본다.
"""
from __future__ import annotations

import pytest

from videobox_core_engine.scene_image_prompt import (
    SceneImagePromptUnavailable,
    SceneImagePromptWriter,
    needs_rewriting,
)


class _Runtime:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.prompts.append(prompt)

        class _Response:
            output_data = {"image_prompt": self.answer}

        return _Response()


def test_only_korean_gets_rewritten() -> None:
    assert needs_rewriting("자막은 따로 붙입니다") is True
    assert needs_rewriting("a quiet desk at dawn") is False
    # 섞여 있어도 한글이 한 글자라도 있으면 그림 모델에게는 못 알아들을 말이다.
    assert needs_rewriting("a desk, 새벽 빛") is True


def test_it_asks_for_a_visible_scene_not_a_translation() -> None:
    """대본은 말이고 그림은 장면이다. 문장을 그대로 옮기면 '설명하는 그림'이 나온다."""
    runtime = _Runtime("a desk with two screens, cinematic, 16:9")

    written = SceneImagePromptWriter(runtime_service=runtime).write(
        project_id="p", line="자막은 따로, 음악도 따로 붙입니다",
    )

    assert written == "a desk with two screens, cinematic, 16:9"
    asked = runtime.prompts[0]
    assert "Do not translate" in asked
    assert "English only" in asked
    # 글자를 그리지 말라고 못박는다 -- FLUX는 한국어 글자를 못 그리면서 자꾸 그리려 든다.
    assert "No text, letters, captions" in asked
    assert "자막은 따로, 음악도 따로 붙입니다" in asked


def test_a_vertical_project_asks_for_a_vertical_frame() -> None:
    runtime = _Runtime("a desk, cinematic, 9:16 vertical")

    SceneImagePromptWriter(runtime_service=runtime).write(project_id="p", line="첫 장면", vertical=True)

    assert "9:16 vertical" in runtime.prompts[0]


def test_an_answer_that_came_back_in_korean_is_not_accepted() -> None:
    """한국어로 답해 버리면 고친 것이 아니다. 조용히 넘기면 당나귀가 나온다."""
    runtime = _Runtime("책상 위에 화면 두 개가 있는 장면")

    with pytest.raises(SceneImagePromptUnavailable) as exc:
        SceneImagePromptWriter(runtime_service=runtime).write(project_id="p", line="첫 장면")

    assert str(exc.value) == "scene_image_prompt_still_korean"


def test_a_silent_model_is_reported_not_papered_over() -> None:
    class _Silent:
        def generate_structured(self, **_kwargs):
            raise RuntimeError("local runtime unavailable")

    with pytest.raises(SceneImagePromptUnavailable) as exc:
        SceneImagePromptWriter(runtime_service=_Silent()).write(project_id="p", line="첫 장면")

    assert str(exc.value) == "scene_image_prompt_writer_unavailable"
