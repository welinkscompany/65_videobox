"""깨진 한글 이름을 읽는 자리에서 되살린다.

2026-09-01에 실측으로 찾았다. `기능 섞어 쓰기 시험` 프로젝트의 촬영본 다섯 개가
`02-µµ½Ã-Àú³á`처럼 저장돼 있었다 -- 화면에서도 그대로 깨져 보이므로 표시가 아니라
**데이터**다. 2026-08-20 08:01 한 묶음으로 들어온 것이고, 그날 08:05 이후로 들어온
것은 전부 멀쩡하다. 지금 넣는 길이 깨뜨리는 게 아니라 그때 쓰던 도구가 깨뜨렸다
(같은 종류의 사고가 기록으로 남아 있다: Windows curl이 한글 파일명을 뭉갠 건).

**고치는 자리를 저장이 아니라 읽기로 잡은 이유.**

- 자산 이름을 바꾸는 길이 제품에 없다(API도 화면도). 그래서 데이터 이관은 손으로
  DB를 만지는 일이 되는데, 그건 다음에 같은 데이터가 또 나와도 아무도 못 고친다.
- 읽는 자리에서 고치면 **화면과 유진이 같이** 낫는다. 유진은 창작자가 붙인 이름을
  보고 소재를 고르므로(2026-09-01에 그 연결을 만들었다), 깨진 이름은 곧 "고를 수
  없는 소재"다 -- 실제로 `도시 저녁으로 바꿔 줘`에 편집안을 못 만들었다.

**되살릴 수 있을 때만 손댄다.** 아래 세 가지가 다 맞아야 바꾼다. 하나라도 어긋나면
원래 글자를 그대로 돌려준다 -- 멀쩡한 이름을 망가뜨리는 것이 깨진 이름을 그냥
두는 것보다 나쁘다.
"""

from __future__ import annotations

_HANGUL_RANGES = ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F))


def _has_hangul(value: str) -> bool:
    return any(any(start <= ord(ch) <= end for start, end in _HANGUL_RANGES) for ch in value)


def repair_mojibake_text(value: str) -> str:
    """CP949 한글이 latin-1로 잘못 읽힌 글자를 되돌린다. 아니면 그대로.

    조건 셋:

    1. 지금 글자에 한글이 **없다** -- 이미 멀쩡한 이름은 건드릴 이유가 없다.
    2. `latin-1`으로 되돌려 `cp949`로 읽는 것이 **깨지지 않고 된다**.
    3. 그 결과에 한글이 **있다** -- 이게 가장 중요하다. `Cafe`나 `Résumé` 같은
       멀쩡한 서양 글자는 2번을 우연히 통과할 수 있지만 3번에서 걸린다.
    """
    if not value or _has_hangul(value):
        return value
    try:
        repaired = value.encode("latin-1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if _has_hangul(repaired) else value


def repair_mojibake_metadata(metadata: object) -> object:
    """자산 metadata 안의 사람이 읽는 값만 되살린다.

    `title`과 `tags`만 본다 -- 저장 경로(`storage_uri`)나 해시는 사람이 읽는 값이
    아니고, 거기를 건드리면 파일을 못 찾는다.
    """
    if not isinstance(metadata, dict):
        return metadata
    title = metadata.get("title")
    tags = metadata.get("tags")
    repaired_title = repair_mojibake_text(title) if isinstance(title, str) else title
    repaired_tags = (
        [repair_mojibake_text(tag) if isinstance(tag, str) else tag for tag in tags]
        if isinstance(tags, list)
        else tags
    )
    if repaired_title == title and repaired_tags == tags:
        return metadata
    return {**metadata, "title": repaired_title, "tags": repaired_tags}


__all__ = ["repair_mojibake_metadata", "repair_mojibake_text"]
