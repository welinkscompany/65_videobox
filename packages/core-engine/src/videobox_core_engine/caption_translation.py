"""자막 번역을 원본 옆에 두고, 출력할 때 어느 쪽을 실을지 고른다.

## 왜 덮어쓰지 않는가

번역은 **되돌릴 수 있어야 한다.** 원본 자막을 번역으로 갈아치우면 한국어로
돌아갈 방법이 없고, 다시 번역해도 이미 영어가 된 자막을 영어로 번역하는 꼴이
된다. 그래서 원본 `caption_text`는 그대로 두고 `caption_translations`에
언어별로 나란히 쌓는다.

## 왜 세션에 언어를 적는가 (렌더러 인자가 아니라)

이 저장소에는 렌더 경로가 둘이고, 한쪽만 고쳐서 같은 함정에 두 번 빠진 기록이
있다(`docs/development-fast-path.ko.md`). 그래서 "어느 언어로 낼지"를 렌더
함수 인자로 흘려보내지 않는다 -- `editing_session["caption_language"]`에 적어
두면 자막을 모으는 **한 자리**(`materialize_editing_session_timeline`)에서만
읽으면 되고, 그 아래로는 모든 출력 경로가 저절로 같은 자막을 본다.

덤으로 선택이 프로젝트에 저장돼서, 다시 내보낼 때 다시 고르지 않아도 된다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


#: 고를 수 있는 자막 언어. 값은 화면에 그대로 쓰는 이름이다(창작자 언어 규정).
#:
#: 한국어는 여기 없다 -- **원본이 곧 한국어**라서 고를 것이 아니라 "번역 안 함"이
#: 기본값이다. 목록에 넣으면 "한국어로 번역"이라는 뜻 없는 선택지가 생긴다.
SUPPORTED_CAPTION_LANGUAGES: dict[str, str] = {
    "en": "영어",
    "ja": "일본어",
    "zh": "중국어",
}


def caption_text_for_language(source: Mapping[str, Any], language: str | None) -> str:
    """이 자막을 `language`로 낼 때 실제로 화면에 나갈 글자.

    번역이 없거나 비어 있으면 **원본을 돌려준다.** 반쯤 번역된 상태에서
    내보내도 자막이 통째로 빠지는 장면이 생기지 않게 하려는 것이다 -- 빈 번역은
    "자막 없음"이 아니라 "아직 번역이 없음"이다.
    """
    original = str(source.get("caption_text") or "")
    if not language:
        return original
    translations = source.get("caption_translations")
    if not isinstance(translations, Mapping):
        return original
    translated = str(translations.get(language) or "").strip()
    return translated or original


def apply_caption_translations(
    *,
    session: dict[str, Any],
    language: str,
    texts_by_segment: Mapping[str, str],
) -> dict[str, Any]:
    """장면별 번역을 세션에 적는다. 원본과 다른 언어 번역은 건드리지 않는다.

    쓰는 자리는 `update_segment_caption`과 **똑같다**: 장면에 쓰고, 그 장면을
    가리키는 content window에도 같이 쓴다. 자막을 나눠 놓은 프로젝트에서 한쪽만
    갱신되면 완성본에 옛 자막이 섞여 나온다.
    """
    if language not in SUPPORTED_CAPTION_LANGUAGES:
        raise ValueError(f"Unsupported caption language: {language}")
    updated = deepcopy(session)
    for segment in updated.get("segments", []):
        if not isinstance(segment, dict):
            continue
        containing_segment_id = str(segment.get("segment_id") or "")
        text = texts_by_segment.get(containing_segment_id)
        if text is not None and str(text).strip():
            _store(segment, language, str(text).strip())
        content_windows = segment.get("content_windows")
        if not isinstance(content_windows, list):
            continue
        for window in content_windows:
            if not isinstance(window, dict):
                continue
            source_segment_id = str(window.get("source_segment_id") or containing_segment_id)
            window_text = texts_by_segment.get(source_segment_id)
            if window_text is not None and str(window_text).strip():
                _store(window, language, str(window_text).strip())
    return updated


def _store(target: dict[str, Any], language: str, text: str) -> None:
    translations = target.get("caption_translations")
    target["caption_translations"] = {
        **(translations if isinstance(translations, Mapping) else {}),
        language: text,
    }
