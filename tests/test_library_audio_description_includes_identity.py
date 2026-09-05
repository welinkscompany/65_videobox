"""효과음 설명이 **소리의 정체를 안 담았다** — 실측 2026-09-05.

owner: "유진이 명령해서 의미에 맞는 영상추천, 음악추천, 효과음 추천 이런게
나올수 있도록".

유진에게 "팝 하고 터지는 짧은 소리 넣어줘"라고 했더니 `sfx-rpg-explosion1`
(RPG 폭발음)을 골랐다. 유진 탓이 아니었다 -- 자료실 검색을 그대로 재 보니
상위 넷의 점수가 **0.646086 / 0.646015 / 0.646015 / 0.646015**로 사실상
같았다. 색인 설명이 서로 구별되지 않는다는 뜻이다.

왜 그런지는 설명을 보면 바로 나온다:

| 자산 | 색인 설명 |
|---|---|
| `sfx-rpg-explosion1` | 아주 짧게 한 번 스치는 효과음. 잔잔하게 깔리는 작은 소리, 낮고 묵직한 음색, 빠르게 몰아치고... |
| `sfx-n4-button` | 아주 짧게 한 번 스치는 효과음. 잔잔하게 깔리는 작은 소리, 부드럽고 무난한 음색, 빠르게 몰아치고... |

**폭발음과 버튼음이 거의 같은 문장이다.** 설명은 소리를 재서(세기·밝기·
빠르기·길이) 쓰는데, 효과음은 그 셋의 27가지 칸에 100개가 들어가니 겹칠
수밖에 없다. 그리고 창작자가 찾을 때 쓰는 말은 음향 특성이 아니라 **정체**다
-- "휙", "딸깍", "팝".

정체는 이미 이름에 있다(`sfx-various-click`). 설명에 넣지 않았을 뿐이다.
임베딩 모델은 다국어라(영어 질의가 한국어 설명에 걸리는 것을 실측했다)
영어 이름도 도움이 되지만, 흔한 낱말은 한국어 뜻을 같이 적어 준다.
"""

from __future__ import annotations

from videobox_core_engine.library_audio_indexer import build_asset_description

WORDS = {"세기": "조용함", "밝기": "중간", "빠르기": "빠름"}


def test_the_sentence_says_what_the_sound_actually_is() -> None:
    """폭발음과 버튼음이 다른 문장을 갖는다."""
    explosion = build_asset_description(
        media_type="sfx", words=WORDS, duration_seconds=1.6, asset_name="sfx-rpg-explosion1",
    )
    button = build_asset_description(
        media_type="sfx", words=WORDS, duration_seconds=1.6, asset_name="sfx-n4-button",
    )

    assert explosion != button
    assert "explosion" in explosion
    assert "button" in button


def test_common_words_carry_their_korean_meaning() -> None:
    """창작자는 "딸깍"이라고 찾지 `click`이라고 찾지 않는다."""
    described = build_asset_description(
        media_type="sfx", words=WORDS, duration_seconds=0.4, asset_name="sfx-various-click",
    )

    assert "딸깍" in described


def test_a_meaningless_name_adds_nothing() -> None:
    """사용자가 올린 자산의 이름은 내용 해시라 뜻이 없다. 넣으면 방해만 된다."""
    described = build_asset_description(
        media_type="sfx", words=WORDS, duration_seconds=0.4,
        asset_name="user_8b8e39e429054a53adb3b502ef93578f",
    )
    plain = build_asset_description(media_type="sfx", words=WORDS, duration_seconds=0.4)

    assert described == plain


def test_the_name_is_optional() -> None:
    """이름 없이 부르던 자리를 깨뜨리지 않는다."""
    assert build_asset_description(media_type="music", words=WORDS, duration_seconds=90.0)
