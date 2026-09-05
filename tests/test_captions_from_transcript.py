"""받아쓰기를 캡션으로 옮긴다 — 캡컷 `자동 캡션` 자리 (계획 §4).

owner 지시(2026-09-05): 캡컷 캡션 패널의 카드 3장을 우리도 갖추라는 것.
세어 보니 `수동 캡션`은 이미 있고, `자동 캡션`은 **부품이 다 있는데 잇는
자리가 없었다**:

- 받아쓰기 작업(`POST /api/projects/{id}/jobs/transcription`)은 faster-whisper로
  **시간 구간별 텍스트**(`start_sec`·`end_sec`·`text`)를 돌려준다.
- 편집 세션의 장면도 시간 구간을 갖는다.
- 그런데 **그 둘을 잇는 코드가 없었다** -- 받아쓰기 결과는 제작 파이프라인의
  다음 단계(장면 분석)로만 흘렀다.

여기서 잇는다. 규칙은 하나: **말이 걸쳐 있는 장면에 그 말을 준다.**

`videobox-parts-exist-but-nothing-calls-them` 기억의 그 패턴이라, 새 기능을
만들기 전에 백엔드부터 뒤졌다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.editing_session import build_editing_session, captions_from_transcript


def _session() -> dict:
    return build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[
            {"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": ""},
            {"segment_id": "seg-2", "start_sec": 5.0, "end_sec": 10.0, "text": ""},
        ],
    )


def test_each_spoken_line_lands_on_the_scene_it_overlaps() -> None:
    applied = captions_from_transcript(
        session=_session(),
        transcript_segments=[
            {"start_sec": 0.5, "end_sec": 2.0, "text": "안녕하세요"},
            {"start_sec": 6.0, "end_sec": 8.0, "text": "오늘은 셀러 이야기예요"},
        ],
    )

    by_id = {segment["segment_id"]: segment for segment in applied["segments"]}
    assert by_id["seg-1"]["caption_text"] == "안녕하세요"
    assert by_id["seg-2"]["caption_text"] == "오늘은 셀러 이야기예요"


def test_two_lines_in_one_scene_are_joined_in_the_order_they_were_said() -> None:
    applied = captions_from_transcript(
        session=_session(),
        transcript_segments=[
            {"start_sec": 3.0, "end_sec": 3.5, "text": "둘째"},
            {"start_sec": 1.0, "end_sec": 1.5, "text": "첫째"},
        ],
    )

    assert applied["segments"][0]["caption_text"] == "첫째 둘째"


def test_a_line_that_straddles_a_cut_goes_to_the_scene_it_overlaps_most() -> None:
    """걸친 말을 양쪽에 다 넣으면 같은 문장이 두 번 보인다."""
    applied = captions_from_transcript(
        session=_session(),
        transcript_segments=[{"start_sec": 4.0, "end_sec": 9.0, "text": "걸친 말"}],
    )

    by_id = {segment["segment_id"]: segment for segment in applied["segments"]}
    assert by_id["seg-1"]["caption_text"] == ""
    assert by_id["seg-2"]["caption_text"] == "걸친 말"


def test_scenes_with_nothing_said_keep_what_they_had() -> None:
    """말이 없는 장면의 캡션을 지우지 않는다 -- 창작자가 쓴 것일 수 있다."""
    session = _session()
    session["segments"][1]["caption_text"] = "손으로 쓴 말"

    applied = captions_from_transcript(
        session=session,
        transcript_segments=[{"start_sec": 1.0, "end_sec": 2.0, "text": "받아쓴 말"}],
    )

    by_id = {segment["segment_id"]: segment for segment in applied["segments"]}
    assert by_id["seg-1"]["caption_text"] == "받아쓴 말"
    assert by_id["seg-2"]["caption_text"] == "손으로 쓴 말"


def test_it_refuses_an_empty_transcript_instead_of_wiping_the_captions() -> None:
    with pytest.raises(ValueError, match="transcript_has_no_speech"):
        captions_from_transcript(session=_session(), transcript_segments=[])


def test_the_change_can_be_undone_like_any_other_edit() -> None:
    applied = captions_from_transcript(
        session=_session(),
        transcript_segments=[{"start_sec": 1.0, "end_sec": 2.0, "text": "안녕"}],
    )

    assert applied["history"][-1]["mutation_type"] == "captions_from_transcript"
