"""자막을 로컬 모델로 번역한다. 나가는 것은 없다.

## 한 번에 다 부르지 않는다

장면이 마흔 개인 프로젝트의 자막을 한 요청에 넣으면 로컬 모델이 뒤쪽을 흘린다
(같은 이유로 유진의 자산 목록에도 상한을 뒀다). 그래서 `_BATCH_SIZE`씩 끊어
부르고, 끊긴 묶음 하나가 실패해도 **나머지 번역은 살린다** -- 마흔 장면 중
하나 때문에 처음부터 다시 하게 만들지 않는다.

## 장면 식별자를 모델에게 보내지 않는다

이 저장소의 `segment_id`는 `timeline_001:001`처럼 **콜론이 들어 있다.**
`식별자: 자막` 꼴로 적어 보내면 어디까지가 식별자인지 모델도 알 수 없고, 되받은
줄을 다시 가르는 쪽도 틀린다(2026-09-02에 실제로 이렇게 어긋났다).

그래서 묶음 안에서만 쓰는 **번호**(1, 2, 3...)를 붙여 보내고 받은 번호를 다시
식별자로 옮긴다. 유진의 장면 번호에서 세운 것과 같은 규칙이다 -- 모델에게
자리를 세게 하지 않고, 표를 준다.

## 모르는 번호는 버린다

범위 밖의 번호가 오면 그 줄만 버린다. 편집 제안 쪽과 같은 태도다: 확실한 것만
통과시키고, 애매한 것은 조용히 통과시키지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Sequence

from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES
from videobox_provider_interfaces.llm import LLMProviderError, LLMTaskType


#: 한 번에 보내는 장면 수. 로컬 모델이 흘리지 않는 선에서 고른 값이다.
_BATCH_SIZE = 12


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"const": "videobox.caption-translation.v1"},
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"scene": {"type": "integer"}, "text": {"type": "string"}},
                    "required": ["scene", "text"],
                },
            },
        },
        "required": ["schema_version", "translations"],
    }


def _prompt(*, language: str, texts: Sequence[str]) -> str:
    language_name = SUPPORTED_CAPTION_LANGUAGES[language]
    example = {
        "schema_version": "videobox.caption-translation.v1",
        "translations": [{"scene": 1, "text": "..."}],
    }
    numbered = "\n".join(f"{number}. {text}" for number, text in enumerate(texts, start=1))
    return (
        f"너는 영상 자막을 {language_name}로 옮기는 번역가다. "
        # 자막은 화면에 잠깐 스치는 글이다. 문장이 길어지면 두 줄로 감기고
        # 장면이 끝나기 전에 다 못 읽는다 -- 뜻보다 길이가 먼저 깨진다.
        "자막은 화면에 잠깐 나왔다 사라지므로 **짧고 읽기 쉽게** 옮긴다. "
        "설명을 덧붙이지 말고, 원문에 없는 말을 지어내지 마라. "
        "말투와 존댓말 정도는 원문을 따른다. "
        f"각 줄은 `번호. 자막`이다. 받은 번호를 **그대로** 돌려주고(1부터 {len(texts)}까지), "
        "없는 번호를 만들지 마라. 빠뜨리지 말고 받은 줄 수만큼 돌려준다. "
        f"출력 예시: {json.dumps(example, ensure_ascii=False)}\n\n"
        f"옮길 자막:\n{numbered}"
    )


@dataclass(slots=True)
class CaptionTranslationService:
    runtime: object
    #: 모델이 못 한 묶음의 사유. 화면에 "몇 장면은 못 옮겼다"를 말해 줄 근거다.
    failures: list[str] = field(default_factory=list)

    def translate(
        self,
        *,
        project_id: str,
        language: str,
        captions: Sequence[tuple[str, str]],
    ) -> dict[str, str]:
        """`(장면번호, 자막)` 목록을 받아 `{장면번호: 번역}`을 돌려준다.

        빈 자막은 애초에 보내지 않는다. 실패한 묶음은 건너뛰고 나머지를 돌려준다.
        """
        if language not in SUPPORTED_CAPTION_LANGUAGES:
            raise ValueError(f"Unsupported caption language: {language}")
        pending = [(segment_id, text.strip()) for segment_id, text in captions if text and text.strip()]
        translated: dict[str, str] = {}
        for index in range(0, len(pending), _BATCH_SIZE):
            batch = pending[index : index + _BATCH_SIZE]
            # 프롬프트는 **try 밖에서** 만든다. 안에서 만들면 여기서 난 실수가
            # "모델이 바쁘다"로 둔갑해 번역이 조용히 비어 버린다(2026-09-02 실측).
            prompt = _prompt(language=language, texts=[text for _, text in batch])
            try:
                response = self.runtime.generate_structured(  # type: ignore[attr-defined]
                    project_id=project_id,
                    task_type=LLMTaskType.CAPTION_TRANSLATION,
                    prompt=prompt,
                    response_schema=_response_schema(),
                )
            except LLMProviderError as exc:
                # 한 묶음이 실패해도 앞뒤 묶음의 번역은 남긴다. 부분 번역은
                # 완성본에서 원문으로 자연히 메워진다(`caption_text_for_language`).
                #
                # **모델이 못 한 것만 삼킨다.** 처음에는 `except Exception`이었는데,
                # 그 안에서 난 우리 실수(NameError)까지 "모델이 바빴다"로 둔갑해
                # 번역이 통째로 비어 나갔다 -- 그런데도 응답은 200이었다.
                self.failures.append(str(exc))
                continue
            translated.update(_accepted(response.output_data, [segment_id for segment_id, _ in batch]))
        return translated


def _accepted(output_data: Any, segment_ids: Sequence[str]) -> dict[str, str]:
    """받은 번호를 다시 장면 식별자로 옮긴다. 범위 밖 번호는 버린다."""
    if not isinstance(output_data, Mapping):
        return {}
    rows = output_data.get("translations")
    if not isinstance(rows, list):
        return {}
    accepted: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            number = int(row.get("scene"))
        except (TypeError, ValueError):
            continue
        text = str(row.get("text") or "").strip()
        if 1 <= number <= len(segment_ids) and text:
            accepted[segment_ids[number - 1]] = text
    return accepted
