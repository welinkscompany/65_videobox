"""주제 한 줄에서 **대본 초안**을 받아 온다.

대본도 찍어 둔 영상도 없는 사람에게는 지금까지 첫 걸음이 없었다. 첫 화면의 세 길
(이어서 하기·대본이 있어요·찍어 둔 영상이 있어요)은 전부 **이미 가진 것**을 전제한다.

**반드시 구조화 출력으로 묻는다.** 2026-08-21 실측으로 같은 모델에 같은 것을 물었을 때
갈렸다.

| 어떻게 물었나 | 결과 |
|---|---|
| 구조화 출력(JSON 스키마) | **2.3초**, 한국어 다섯 줄 |
| 자유형 대화 | 26초, 생각 과정이 영어로 새어 나옴 |

자유형 쪽이 나쁜 이유는 느려서가 아니다. **배관만 보면 답이 온 것처럼 보인다** --
`output_text`에 글자가 들어 있으니 성공으로 읽히고, owner만 영어 독백을 받는다.

**닿지 않으면 그냥 넘기지 않는다.** 빈 초안·영어 초안을 그대로 돌려주는 것은 조용히
틀린 것을 주는 일이고, 실패하는 것보다 나쁘다(`scene_image_prompt.py`에서 같은 것을
배웠다 -- 그림 모델은 한국어를 거절하지 않고 당나귀를 그렸다).

**초안은 제안이지 확정이 아니다.** 여기서는 아무것도 저장하지 않는다. owner가 화면에서
고치고 확인해야 기획(`createCreationBrief`)으로 넘어간다 --
`decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`가 남기라고 못박은
사람 게이트 셋 중 `대본 확정`이 이 자리다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from videobox_provider_interfaces.llm import LLMTaskType


_HANGUL = re.compile(r"[가-힣]")

#: 화면이 값을 안 실어 보내도 말이 되는 초안이 나와야 한다. 60초·5장면은 숏폼
#: 한 편의 흔한 모양이고, 화면의 기본값과 같은 값을 여기에도 둔다.
DEFAULT_DURATION_SEC = 60
DEFAULT_SCENE_COUNT = 5

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["title", "scenes"],
    "properties": {
        "title": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["narration"],
                "properties": {
                    "narration": {"type": "string"},
                    "visual": {"type": "string"},
                },
            },
        },
    },
}

#: 한국어로 답하라고 **명시한다.** 안 적으면 영어로 나온다 -- 자산 색인에서 이미
#: 같은 것을 겪었고, 언어가 어긋나면 검색 점수까지 떨어졌다(§10.15 4항).
_INSTRUCTION = """당신은 한국어 영상 대본을 쓰는 작가입니다.

주제를 읽고, 그 주제로 만들 영상의 대본 초안을 씁니다.

지켜야 할 것:
- 반드시 한국어로만 답합니다. 영어 문장을 섞지 않습니다.
- 전체 길이는 약 {duration_sec}초 분량으로 씁니다.
- 장면은 정확히 {scene_count}개로 나눕니다. 한 장면은 약 {per_scene_sec}초 분량입니다.
- `narration`에는 그 장면에서 **말할 내용**만 적습니다. 지시문이나 설명을 적지 않습니다.
- `visual`에는 그 장면에서 **보여 줄 그림**을 짧게 적습니다.
- 생각 과정을 적지 않습니다. 결과만 적습니다.

주제:
{topic}
"""


@dataclass(slots=True, frozen=True)
class ScriptDraftUnavailable(Exception):
    """유진이 쓸 수 있는 대본을 돌려주지 못했다. **조용히 넘기지 않는다.**"""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True, frozen=True)
class ScriptDraftScene:
    scene_number: int
    narration: str
    #: 그 장면에서 보여 줄 그림. 없을 수 있다 -- 있으면 좋은 것이지 없다고
    #: 쓸 수 있는 대본을 버릴 이유가 아니다.
    visual: str = ""


@dataclass(slots=True, frozen=True)
class ScriptDraft:
    title: str
    #: 고칠 수 있는 글 한 덩이. 장면 줄을 그대로 이어 붙인 것이라 둘이 어긋나지 않는다.
    script_text: str
    scenes: tuple[ScriptDraftScene, ...]


@dataclass(slots=True)
class ScriptDraftWriter:
    runtime_service: Any

    def write(
        self,
        *,
        project_id: str,
        topic: str,
        duration_sec: int = DEFAULT_DURATION_SEC,
        scene_count: int = DEFAULT_SCENE_COUNT,
    ) -> ScriptDraft:
        subject = (topic or "").strip()
        if not subject:
            raise ScriptDraftUnavailable("script_draft_topic_empty")
        scenes_asked = max(1, int(scene_count))
        seconds_asked = max(1, int(duration_sec))
        try:
            response = self.runtime_service.generate_structured(
                project_id=project_id,
                task_type=LLMTaskType.SCRIPT_DRAFT,
                prompt=_INSTRUCTION.format(
                    topic=subject,
                    duration_sec=seconds_asked,
                    scene_count=scenes_asked,
                    per_scene_sec=max(1, round(seconds_asked / scenes_asked)),
                ),
                response_schema=_RESPONSE_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 - 로컬 런타임 경계
            # **제 시간에 못 끝낸 것과 닿지 못한 것을 나눈다.** 둘 다 "잠시 뒤 다시"로
            # 뭉치면 owner는 같은 길이로 몇 번이고 다시 누른다 -- 찍어 둔 영상
            # 받아쓰기에서 이미 겪은 함정이다(`SourceVideoStart.tsx`).
            #
            # 2026-08-21 실측: 60초·5장면은 8.0초, **5분·12장면은 28.7초**로
            # 로컬 런타임 기본 상한 30초에 여유가 거의 없다. 길게 부탁하면
            # 실제로 넘어간다.
            if str(getattr(exc, "error_code", "") or "").upper() == "LOCAL_TIMEOUT":
                raise ScriptDraftUnavailable("script_draft_took_too_long") from exc
            raise ScriptDraftUnavailable("script_draft_writer_unavailable") from exc

        output = getattr(response, "output_data", None) or {}
        scenes = _read_scenes(output.get("scenes"))
        if not scenes:
            # 모양이 어긋난 답과 빈 답을 같은 말로 묶는다. owner가 할 다음 행동이
            # 같기 때문이다 -- 다시 눌러 보거나, 주제를 바꿔 적는다.
            raise ScriptDraftUnavailable("script_draft_empty")
        if any(not _HANGUL.search(scene.narration) for scene in scenes):
            # 한 줄이라도 한국어가 아니면 그 줄은 owner가 읽을 대본이 아니다.
            # 구조화 출력을 써도 생각 과정이 영어로 새는 일이 있었다.
            raise ScriptDraftUnavailable("script_draft_not_korean")

        return ScriptDraft(
            title=str(output.get("title") or "").strip() or subject,
            script_text="\n".join(scene.narration for scene in scenes),
            scenes=scenes,
        )


def _read_scenes(raw: Any) -> tuple[ScriptDraftScene, ...]:
    if not isinstance(raw, list):
        return ()
    scenes: list[ScriptDraftScene] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or "").strip()
        if not narration:
            continue
        scenes.append(
            ScriptDraftScene(
                scene_number=len(scenes) + 1,
                narration=narration,
                visual=str(item.get("visual") or "").strip(),
            )
        )
    return tuple(scenes)


__all__ = [
    "DEFAULT_DURATION_SEC",
    "DEFAULT_SCENE_COUNT",
    "ScriptDraft",
    "ScriptDraftScene",
    "ScriptDraftUnavailable",
    "ScriptDraftWriter",
]
