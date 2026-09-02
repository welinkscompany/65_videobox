"""번역 서비스 -- 지어낸 장면은 버리고, 한 묶음이 실패해도 나머지는 살린다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from videobox_core_engine.caption_translation_service import CaptionTranslationService


@dataclass
class _Response:
    output_data: Any


class _Runtime:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.prompts: list[str] = []

    def generate_structured(self, *, project_id: str, task_type: Any, prompt: str, response_schema: Any) -> _Response:
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Response(reply)


def _reply(pairs: list[tuple[int, str]]) -> dict[str, Any]:
    return {
        "schema_version": "videobox.caption-translation.v1",
        "translations": [{"scene": number, "text": text} for number, text in pairs],
    }


def test_translations_come_back_keyed_by_scene() -> None:
    runtime = _Runtime([_reply([(1, "Hello")])])
    service = CaptionTranslationService(runtime=runtime)
    assert service.translate(
        project_id="project_001", language="en", captions=[("segment_001", "안녕하세요")]
    ) == {"segment_001": "Hello"}


def test_a_made_up_scene_is_dropped() -> None:
    """모델이 없는 번호를 지어내면 그 줄만 버린다 -- 조용히 통과시키지 않는다."""
    runtime = _Runtime([_reply([(1, "Hello"), (99, "Ghost")])])
    service = CaptionTranslationService(runtime=runtime)
    assert service.translate(
        project_id="project_001", language="en", captions=[("segment_001", "안녕하세요")]
    ) == {"segment_001": "Hello"}


def test_blank_captions_are_never_sent() -> None:
    runtime = _Runtime([_reply([(1, "Hi")])])
    service = CaptionTranslationService(runtime=runtime)
    result = service.translate(
        project_id="project_001",
        language="en",
        captions=[("segment_001", "   "), ("segment_002", "안녕")],
    )
    assert result == {"segment_002": "Hi"}
    # 빈 자막은 번호도 못 받는다 -- 보낸 줄은 하나뿐이다.
    assert runtime.prompts[0].rstrip().endswith("1. 안녕")


def test_a_failed_batch_does_not_lose_the_others() -> None:
    """열세 장면이면 두 묶음이다. 앞이 죽어도 뒤의 번역은 남는다."""
    captions = [(f"segment_{index:03d}", f"자막{index}") for index in range(1, 14)]
    runtime = _Runtime([RuntimeError("local model is busy"), _reply([(1, "Line 13")])])
    service = CaptionTranslationService(runtime=runtime)
    assert service.translate(project_id="project_001", language="en", captions=captions) == {
        "segment_013": "Line 13"
    }


def test_long_projects_are_split_into_batches() -> None:
    captions = [(f"segment_{index:03d}", f"자막{index}") for index in range(1, 14)]
    runtime = _Runtime([_reply([]), _reply([])])
    CaptionTranslationService(runtime=runtime).translate(
        project_id="project_001", language="en", captions=captions
    )
    assert len(runtime.prompts) == 2


def test_unknown_language_is_refused_before_calling_the_model() -> None:
    runtime = _Runtime([])
    with pytest.raises(ValueError):
        CaptionTranslationService(runtime=runtime).translate(
            project_id="project_001", language="klingon", captions=[("segment_001", "안녕")]
        )
    assert runtime.prompts == []


def test_scene_ids_with_colons_survive_the_round_trip() -> None:
    """이 저장소의 장면 식별자에는 콜론이 들어 있다(`timeline_001:001`).

    식별자를 그대로 프롬프트에 적어 보내던 처음 판은 `번호: 자막`을 콜론으로
    가르다가 `timeline_001`에서 잘렸다 -- 번역이 통째로 버려졌다. 모델에게는
    번호만 보내고, 되돌리는 일은 이쪽에서 한다.
    """
    runtime = _Runtime([_reply([(1, "Hello"), (2, "Nice to meet you")])])
    result = CaptionTranslationService(runtime=runtime).translate(
        project_id="project_001",
        language="en",
        captions=[("timeline_001:001", "안녕하세요"), ("timeline_001:002", "반갑습니다")],
    )
    assert result == {"timeline_001:001": "Hello", "timeline_001:002": "Nice to meet you"}
    # 식별자는 모델에게 나가지 않는다.
    assert "timeline_001" not in runtime.prompts[0]
