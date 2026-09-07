"""대본 한 줄을 **그림 만드는 프로그램이 알아듣는 말**로 바꾼다.

**2026-08-21 실측 -- 짐작이 아니다.** 같은 씨앗(606386459)·같은 설정으로 두 번 만들었다.

| 넣은 말 | 나온 것 |
|---|---|
| `자막은 따로, 음악도 따로 붙입니다` | **픽셀아트 당나귀 두 마리** |
| `a video editing desk with two separate screens, one showing subtitle text and one showing a music waveform, warm studio light, cinematic, 16:9` | 실제로 그 장면 |

증거는 `artifacts/scene-image-check/korean.png`와 `english.png`다.

FLUX의 글자 이해기(T5 + CLIP-L)는 영어로 배웠다. 한국어를 넣으면 거절하는 게 아니라
**아무 그림이나 그럴듯하게 내놓는다** -- 그래서 배관만 보면 다 되는 것처럼 보인다.
owner는 버튼을 누르고 24초를 기다린 뒤 당나귀를 받게 된다.

그래서 유진이 그 줄을 읽고 영어 묘사를 쓴다. 인계 문서의 "장면별 프롬프트(유진이 쓴다)"가
이 자리다.

**닿지 않으면 그냥 넣지 않는다.** 한국어를 그대로 흘려보내는 것은 조용히 틀린 그림을
만드는 것이고, 실패하는 것보다 나쁘다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from videobox_provider_interfaces.llm import LLMTaskType


_HANGUL = re.compile(r"[가-힣]")

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["image_prompt"],
    "properties": {
        "image_prompt": {"type": "string"},
    },
}

#: 창작자가 쓴 한 줄에서 **보이는 것**만 뽑아낸다. 대본은 말이고 그림은 장면이라,
#: 그대로 옮기면 "설명하는 그림"이 나온다. 글자를 그리지 말라고 못박는 이유는
#: FLUX가 한국어 글자를 못 그리면서도 자꾸 그리려 들기 때문이다.
_INSTRUCTION = """You write image prompts for a text-to-image model.

Read one line of a Korean video script and describe, in English, a single
photographic scene that could illustrate it.

Rules:
- Answer in English only. The image model does not understand Korean.
- Describe what is visible: subject, setting, lighting, camera framing.
- Do not translate the sentence. Describe a scene that shows what it means.
- No text, letters, captions, logos or watermarks in the image.
- One sentence, under 60 words.
- End with the words: cinematic, {orientation}

Korean script line:
{line}
"""


@dataclass(slots=True, frozen=True)
class SceneImagePromptUnavailable(Exception):
    """유진이 지금 답하지 못한다. **한국어를 그대로 흘려보내지 않는다.**"""

    message: str

    def __str__(self) -> str:
        return self.message


def needs_rewriting(prompt: str) -> bool:
    """한글이 한 글자라도 있으면 그림 모델에게는 못 알아들을 말이다.

    영어로 직접 적은 owner의 프롬프트는 건드리지 않는다 -- 사람이 쓴 것이
    모델이 다시 쓴 것보다 낫고, 무엇보다 그대로 만들어 줄 것을 기대한다.
    """
    return bool(_HANGUL.search(prompt or ""))


@dataclass(slots=True)
class SceneImagePromptWriter:
    runtime_service: Any

    def write(self, *, project_id: str, line: str, vertical: bool = False) -> str:
        orientation = "9:16 vertical" if vertical else "16:9"
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.SCENE_IMAGE_PROMPT,
                prompt=_INSTRUCTION.format(line=line.strip(), orientation=orientation),
                response_schema=_RESPONSE_SCHEMA,
            )
        except Exception as exc:
            raise SceneImagePromptUnavailable("scene_image_prompt_writer_unavailable") from exc
        written = str((response.output_data or {}).get("image_prompt") or "").strip()
        if not written:
            raise SceneImagePromptUnavailable("scene_image_prompt_writer_unavailable")
        if needs_rewriting(written):
            # 한국어로 답해 버리면 고친 것이 아니다. 조용히 넘기면 당나귀가 나온다.
            raise SceneImagePromptUnavailable("scene_image_prompt_still_korean")
        return written


__all__ = [
    "SceneImagePromptUnavailable",
    "SceneImagePromptWriter",
    "needs_rewriting",
]
