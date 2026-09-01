"""깨진 한글 이름 되살리기 -- **되살릴 수 있을 때만** 손대는지 잰다.

멀쩡한 이름을 망가뜨리는 것이 깨진 이름을 그냥 두는 것보다 나쁘다. 그래서
안 바꿔야 하는 경우를 바꾸는 경우보다 더 많이 적어 둔다.
"""

from __future__ import annotations

from videobox_core_engine.mojibake import repair_mojibake_metadata, repair_mojibake_text


def test_restores_the_names_that_were_actually_broken_in_the_owner_project() -> None:
    """2026-09-01에 실제로 깨져 있던 다섯 개. 실물이 회귀 시험이다."""
    assert repair_mojibake_text("01-»õº®-¹Ù´Ù") == "01-새벽-바다"
    assert repair_mojibake_text("02-µµ½Ã-Àú³á") == "02-도시-저녁"
    assert repair_mojibake_text("03-Ã¥»ó-ÀÛ¾÷") == "03-책상-작업"
    assert repair_mojibake_text("04-ÃÊ·Ï-¿©¹é") == "04-초록-여백"
    assert repair_mojibake_text("05-¸¶¹«¸®") == "05-마무리"


def test_leaves_alone_everything_that_is_not_broken_korean() -> None:
    """**여기가 이 함수의 핵심이다.** 하나라도 잘못 바꾸면 이름이 사라진다."""
    for untouched in (
        "천장-확인",           # 이미 멀쩡한 한글
        "1번째 장면 그림",      # 한글 + 숫자
        "big20",              # 순수 ASCII
        "",                   # 빈 값
        "Cafe Jazz",          # 서양 글자
        "Résumé",             # latin-1로 되돌아가지만 결과에 한글이 없다
        "café ☕",            # latin-1로 인코딩 자체가 안 된다
        "01-새벽-바다",         # 이미 고쳐진 것을 또 건드리지 않는다
    ):
        assert repair_mojibake_text(untouched) == untouched, untouched


def test_repairing_twice_changes_nothing_more() -> None:
    """읽을 때마다 도는 함수다. 두 번 돈다고 더 바뀌면 안 된다."""
    once = repair_mojibake_text("02-µµ½Ã-Àú³á")
    assert repair_mojibake_text(once) == once


def test_metadata_repair_touches_only_what_a_person_reads() -> None:
    """저장 경로와 해시는 사람이 읽는 값이 아니다 -- 건드리면 파일을 못 찾는다."""
    repaired = repair_mojibake_metadata({
        "title": "02-µµ½Ã-Àú³á",
        "tags": ["¹Ù´Ù", "calm"],
        "storage_uri": "local://projects/p/assets/imported/broll-abc.mp4",
        "duration_sec": 6.0,
    })

    assert repaired["title"] == "02-도시-저녁"
    assert repaired["tags"] == ["바다", "calm"]
    # 손대면 안 되는 것은 글자 하나 안 바뀐다.
    assert repaired["storage_uri"] == "local://projects/p/assets/imported/broll-abc.mp4"
    assert repaired["duration_sec"] == 6.0


def test_metadata_repair_returns_the_same_object_when_nothing_was_broken() -> None:
    """멀쩡한 자산에 새 사전을 만들지 않는다 -- 읽는 자리마다 도는 함수다."""
    metadata = {"title": "천장-확인", "tags": ["실내"]}

    assert repair_mojibake_metadata(metadata) is metadata
    assert repair_mojibake_metadata(None) is None
