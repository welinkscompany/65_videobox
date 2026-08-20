from __future__ import annotations

from videobox_core_engine.transcript_alignment import HeuristicTranscriptAligner, split_script_units


def test_transcript_aligner_merges_split_transcript_segments_to_match_script_sentences() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 0.8, "text": "Office over", "confidence": 0.98},
            {"start_sec": 0.8, "end_sec": 1.6, "text": "view intro", "confidence": 0.97},
            {"start_sec": 1.6, "end_sec": 3.0, "text": "Team update starts.", "confidence": 0.96},
        ],
        script_text="Office overview intro.\n\nTeam update starts.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.6,
            "text": "Office overview intro.",
            "confidence": 0.97,
        },
        {
            "start_sec": 1.6,
            "end_sec": 3.0,
            "text": "Team update starts.",
            "confidence": 0.96,
        },
    ]


def test_transcript_aligner_falls_back_to_original_segments_when_script_is_missing() -> None:
    aligner = HeuristicTranscriptAligner()
    transcript_segments = [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "Office overview.", "confidence": 0.99},
        {"start_sec": 1.0, "end_sec": 2.0, "text": "Team update starts.", "confidence": 0.98},
    ]

    assert aligner.align(transcript_segments=transcript_segments, script_text=None) == transcript_segments


def test_transcript_aligner_uses_partial_script_when_available_and_keeps_remaining_transcript() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 0.8, "text": "Office over", "confidence": 0.98},
            {"start_sec": 0.8, "end_sec": 1.6, "text": "view intro", "confidence": 0.97},
            {"start_sec": 1.6, "end_sec": 3.0, "text": "Team update starts.", "confidence": 0.96},
        ],
        script_text="Office overview intro.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.6,
            "text": "Office overview intro.",
            "confidence": 0.97,
        },
        {
            "start_sec": 1.6,
            "end_sec": 3.0,
            "text": "Team update starts.",
            "confidence": 0.96,
        },
    ]


def test_transcript_aligner_preserves_timestamps_when_rewriting_text() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 4.2, "end_sec": 5.1, "text": "Pro", "confidence": 0.95},
            {"start_sec": 5.1, "end_sec": 6.7, "text": "ject update", "confidence": 0.94},
        ],
        script_text="Project update.",
    )

    assert aligned[0]["start_sec"] == 4.2
    assert aligned[0]["end_sec"] == 6.7
    assert aligned[0]["text"] == "Project update."


def test_transcript_aligner_does_not_drop_spoken_words_when_script_is_only_partial_match() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 0.8, "text": "Office over", "confidence": 0.98},
            {"start_sec": 0.8, "end_sec": 1.6, "text": "view intro", "confidence": 0.97},
        ],
        script_text="Office overview.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.6,
            "text": "Office over view intro",
            "confidence": 0.97,
        }
    ]


def test_transcript_aligner_keeps_spoken_transcript_when_script_meaning_differs() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 1.0, "text": "Turn left now.", "confidence": 0.99},
        ],
        script_text="Turn right now.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "Turn left now.",
            "confidence": 0.99,
        }
    ]


def test_transcript_aligner_keeps_spoken_transcript_for_high_similarity_word_substitution() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 1.0, "text": "Send the file today.", "confidence": 0.99},
        ],
        script_text="Send the final today.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "Send the file today.",
            "confidence": 0.99,
        }
    ]


def test_transcript_aligner_splits_script_paragraph_into_sentence_units() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {"start_sec": 0.0, "end_sec": 0.8, "text": "Office over", "confidence": 0.98},
            {"start_sec": 0.8, "end_sec": 1.6, "text": "view intro", "confidence": 0.97},
            {"start_sec": 1.6, "end_sec": 3.0, "text": "Team update starts.", "confidence": 0.96},
        ],
        script_text="Office overview intro. Team update starts.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 1.6,
            "text": "Office overview intro.",
            "confidence": 0.97,
        },
        {
            "start_sec": 1.6,
            "end_sec": 3.0,
            "text": "Team update starts.",
            "confidence": 0.96,
        },
    ]


def test_transcript_aligner_splits_coarse_transcript_segment_to_match_multiple_script_sentences() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {
                "start_sec": 0.0,
                "end_sec": 3.0,
                "text": "Office overview intro. Team update starts.",
                "confidence": 0.98,
            }
        ],
        script_text="Office overview intro. Team update starts.",
    )

    assert [segment["text"] for segment in aligned] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert aligned[0]["start_sec"] == 0.0
    assert aligned[-1]["end_sec"] == 3.0
    assert aligned[0]["end_sec"] < aligned[1]["end_sec"]


def test_transcript_aligner_splits_coarse_transcript_segment_even_when_script_is_partial() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {
                "start_sec": 0.0,
                "end_sec": 3.0,
                "text": "Office overview intro. Team update starts.",
                "confidence": 0.98,
            }
        ],
        script_text="Office overview intro.",
    )

    assert [segment["text"] for segment in aligned] == [
        "Office overview intro.",
        "Team update starts.",
    ]
    assert aligned[0]["start_sec"] == 0.0
    assert aligned[-1]["end_sec"] == 3.0


def test_transcript_aligner_does_not_split_common_abbreviations_as_sentence_boundaries() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {
                "start_sec": 0.0,
                "end_sec": 2.0,
                "text": "U.S. team update starts.",
                "confidence": 0.98,
            }
        ],
        script_text="U.S. team update starts.",
    )

    assert aligned == [
        {
            "start_sec": 0.0,
            "end_sec": 2.0,
            "text": "U.S. team update starts.",
            "confidence": 0.98,
        }
    ]


def test_split_script_units_keeps_common_inline_abbreviations_inside_sentence() -> None:
    assert split_script_units("Compare A vs. B before launch.") == [
        "Compare A vs. B before launch."
    ]
    assert split_script_units("Bring snacks, etc. before noon.") == [
        "Bring snacks, etc. before noon."
    ]
    assert split_script_units("Meet Capt. Rogers tomorrow.") == [
        "Meet Capt. Rogers tomorrow."
    ]


def test_split_script_units_still_splits_after_sentence_final_abbreviations() -> None:
    assert split_script_units("Bring snacks, etc. We start at noon.") == [
        "Bring snacks, etc.",
        "We start at noon.",
    ]
    assert split_script_units("Meet on Main St. We start now.") == [
        "Meet on Main St.",
        "We start now.",
    ]


def test_transcript_aligner_keeps_positive_durations_when_splitting_short_coarse_segment() -> None:
    aligner = HeuristicTranscriptAligner()

    aligned = aligner.align(
        transcript_segments=[
            {
                "start_sec": 0.0,
                "end_sec": 0.01,
                "text": "Alpha. Beta.",
                "confidence": 0.98,
            }
        ],
        script_text="Alpha. Beta.",
    )

    assert len(aligned) == 2
    assert aligned[0]["start_sec"] < aligned[0]["end_sec"]
    assert aligned[1]["start_sec"] < aligned[1]["end_sec"]
    assert aligned[0]["end_sec"] <= aligned[1]["start_sec"]


def test_split_script_units_keeps_a_list_number_with_the_sentence_it_labels() -> None:
    """번호 매긴 대본이 번호만 있는 장면을 만들었다(2026-08-20 실측).

    유진에게 대본을 써 달라고 하면 `1. ...` `2. ...` 꼴로 준다. 그대로 대본으로
    쓰면 `1.`이 문장 하나로 잘려 **자막이 "1"인 장면**이 생겼다. 다섯 문장짜리
    대본이 열세 장면이 됐고, 그중 다섯은 숫자만 보였다.
    """
    assert split_script_units("1. 붉게 물든 단풍. 2. 낙엽이 흩날린다.") == [
        "1. 붉게 물든 단풍.",
        "2. 낙엽이 흩날린다.",
    ]
    assert split_script_units("1) 첫 문장이다. 2) 둘째 문장이다.") == [
        "1) 첫 문장이다.",
        "2) 둘째 문장이다.",
    ]
    # 줄로 나뉜 번호 목록도 마찬가지다.
    assert split_script_units("1. 첫 장면\n2. 둘째 장면") == [
        "1. 첫 장면",
        "2. 둘째 장면",
    ]
    # 문장 끝에 온 숫자는 여전히 문장의 끝이다.
    assert split_script_units("총 3. 그리고 다음 문장.") == [
        "총 3.",
        "그리고 다음 문장.",
    ]
