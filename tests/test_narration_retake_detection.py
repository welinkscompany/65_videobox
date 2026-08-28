from __future__ import annotations

from videobox_core_engine.narration_retake_detection import detect_retake_candidates


def test_flags_low_confidence_segments():
    segments = [
        {"start_sec": 0.0, "end_sec": 2.0, "text": "오늘은 라면을 끓여볼게요.", "confidence": 0.95},
        {"start_sec": 2.0, "end_sec": 4.0, "text": "먼저 므러 므럴 뜨거운 물을 준비해요.", "confidence": 0.42},
    ]

    candidates = detect_retake_candidates(segments)

    assert len(candidates) == 1
    assert candidates[0].segment_index == 1
    assert candidates[0].reason == "low_confidence"


def test_flags_retry_cue_and_the_segment_before_it():
    segments = [
        {"start_sec": 0.0, "end_sec": 2.0, "text": "오늘은 파스타를 만들 거예요.", "confidence": 0.9},
        {"start_sec": 2.0, "end_sec": 3.5, "text": "아, 잠깐, 다시 할게요.", "confidence": 0.9},
        {"start_sec": 3.5, "end_sec": 6.0, "text": "오늘은 라면을 끓여볼게요.", "confidence": 0.9},
    ]

    candidates = detect_retake_candidates(segments)

    assert [candidate.segment_index for candidate in candidates] == [0, 1]
    assert candidates[0].reason == "retry_cue_precursor"
    assert candidates[1].reason == "retry_cue"


def test_does_not_flag_the_word_in_the_middle_of_a_sentence():
    # "다시"가 문장 맨 앞이 아니면 재시도 표현이 아니다 -- 그냥 낱말이다.
    segments = [
        {"start_sec": 0.0, "end_sec": 2.0, "text": "이걸 다시 보면 재밌어요.", "confidence": 0.9},
    ]

    assert detect_retake_candidates(segments) == ()


def test_high_confidence_clean_speech_has_no_candidates():
    segments = [
        {"start_sec": 0.0, "end_sec": 2.0, "text": "안녕하세요.", "confidence": 0.99},
        {"start_sec": 2.0, "end_sec": 4.0, "text": "오늘 영상 시작할게요.", "confidence": 0.97},
    ]

    assert detect_retake_candidates(segments) == ()


def test_empty_and_whitespace_segments_are_skipped():
    segments = [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "   ", "confidence": 0.1},
        {"start_sec": 1.0, "end_sec": 2.0, "text": "", "confidence": 0.1},
    ]

    assert detect_retake_candidates(segments) == ()


def test_candidates_stay_in_chronological_order():
    segments = [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "므러 므럴", "confidence": 0.3},
        {"start_sec": 1.0, "end_sec": 2.0, "text": "괜찮은 문장이에요.", "confidence": 0.9},
        {"start_sec": 2.0, "end_sec": 3.0, "text": "다시 말할게요.", "confidence": 0.9},
    ]

    candidates = detect_retake_candidates(segments)

    assert [candidate.segment_index for candidate in candidates] == [0, 1, 2]


def test_a_custom_confidence_threshold_is_honored():
    segments = [{"start_sec": 0.0, "end_sec": 1.0, "text": "괜찮아요.", "confidence": 0.7}]

    assert detect_retake_candidates(segments, confidence_threshold=0.9)[0].reason == "low_confidence"
    assert detect_retake_candidates(segments, confidence_threshold=0.5) == ()
