"""프로젝트 b-roll 분석도 우리말로 답해야 한다.

라이브러리 색인은 우리말로 바꿨지만 프로젝트 쪽 분석은 그대로였다. 같은 영상을
편집기에서 열면 태그와 요약이 영어로 보이고, 대본 문장과 맞추는 의미검색도
언어가 어긋난 채로 돈다.
"""

from __future__ import annotations

from videobox_core_engine.media_analysis import VISION_ANALYSIS_PROMPT


def test_the_shared_prompt_asks_for_korean() -> None:
    assert "한국어" in VISION_ANALYSIS_PROMPT


def test_the_library_indexer_and_the_project_analysis_ask_the_same_thing() -> None:
    # 두 경로가 다른 말로 물으면 같은 영상이 서로 다른 언어로 설명된다.
    from videobox_core_engine.library_footage_indexer import _VISION_PROMPT

    assert _VISION_PROMPT == VISION_ANALYSIS_PROMPT
