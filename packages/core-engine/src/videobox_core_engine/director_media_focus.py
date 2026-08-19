"""창작자가 말로 청한 **미디어 종류**를 고른다.

2026-08-19 owner 지적: "음악 추천해 줘"라고 했는데 후보에는 영상만 왔다.
말과 후보가 따로 놀면 대화로 편집한다는 말이 성립하지 않는다.

**모델에게 맡기지 않는다.** 같은 말에 다른 결과가 나오면 왜 그렇게 골랐는지
설명할 수 없고, 후보를 거르는 일은 조용히 틀리면 "있는데 안 나오는" 것으로
보인다. 규칙은 결정적이고 읽을 수 있어야 한다.
"""

from __future__ import annotations

# 종류마다 창작자가 실제로 쓰는 말. 영어·한글을 함께 둔다 -- owner는 `BGM`도
# `배경 음악`도 쓴다. 표기 흔들림(`b roll`, `브이로그` 아님)은 소문자로 맞춘 뒤 본다.
_MEDIA_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bgm", ("배경 음악", "배경음악", "브금", "bgm", "음악", "music")),
    ("sfx", ("효과음", "사운드 이펙트", "sfx", "sound effect")),
    ("broll", ("b-roll", "b roll", "broll", "브롤", "footage")),
)
# `영상`·`클립`은 한국어에서 **너무 넓다.** "영상 전체에 깔릴 배경 음악"은 음악
# 요청인데 `영상`만 보고 화면 후보까지 끼워 넣으면 청하지 않은 것이 섞인다.
# 그래서 이 말들은 **소리 쪽을 아무것도 청하지 않았을 때만** 화면으로 읽는다.
# `장면`은 더 넓다 -- "이 장면 분위기 어떻게 잡을까?"는 무엇을 청한 것이 아니다.
# 종류를 말하지 않은 물음은 좁히지 않는 것이 맞다.
_BROAD_VISUAL_WORDS = ("영상", "클립")
# 결과 순서를 고정한다. 집합으로 두면 같은 요청이 실행마다 다른 순서를 준다.
_MEDIA_ORDER = ("broll", "bgm", "sfx")


def media_focus_for_request(request_text: str | None) -> tuple[str, ...] | None:
    """청한 종류들. **아무 종류도 말하지 않았으면 `None`** -- 좁히지 않는다.

    넘겨짚어 거르면 있는 후보가 사라지고, 창작자는 라이브러리가 빈 줄 안다.
    """
    text = (request_text or "").strip().lower()
    if not text:
        return None
    found = {media_type for media_type, words in _MEDIA_WORDS if any(word in text for word in words)}
    if not found & {"bgm", "sfx"} and any(word in text for word in _BROAD_VISUAL_WORDS):
        found.add("broll")
    if not found:
        return None
    return tuple(media_type for media_type in _MEDIA_ORDER if media_type in found)
