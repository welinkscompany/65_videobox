from __future__ import annotations

from videobox_core_engine.script_scene_planner import HeuristicSegmentAnalyzer


def _segment(text: str, start_sec: float, end_sec: float, confidence: float = 0.99) -> dict[str, object]:
    return {"text": text, "start_sec": start_sec, "end_sec": end_sec, "confidence": confidence}


def test_analyze_flags_a_long_gap_between_segments_as_silence() -> None:
    analyzer = HeuristicSegmentAnalyzer()

    segments = analyzer.analyze(
        project_id="proj_1",
        transcript_segments=[
            _segment("Welcome to the office tour.", 0.0, 2.0),
            _segment("Let's look at the kitchen.", 5.5, 7.5),
        ],
        script_text=None,
    )

    assert segments[0]["review_required"] is False
    assert segments[0]["review_reasons"] == []
    assert segments[1]["review_required"] is True
    assert "narration_silence_gap" in segments[1]["review_reasons"]


def test_analyze_flags_near_duplicate_consecutive_text_as_a_retake() -> None:
    analyzer = HeuristicSegmentAnalyzer()

    segments = analyzer.analyze(
        project_id="proj_1",
        transcript_segments=[
            _segment("This is our main conference room.", 0.0, 2.0),
            _segment("This is our main conference room area.", 2.1, 4.1),
        ],
        script_text=None,
    )

    assert segments[1]["review_required"] is True
    assert "narration_retake_duplicate" in segments[1]["review_reasons"]


def test_analyze_does_not_flag_short_pauses_or_distinct_sentences() -> None:
    analyzer = HeuristicSegmentAnalyzer()

    segments = analyzer.analyze(
        project_id="proj_1",
        transcript_segments=[
            _segment("Welcome to the office tour.", 0.0, 2.0),
            _segment("Let's start with the lobby.", 2.5, 4.5),
        ],
        script_text=None,
    )

    assert segments[0]["review_required"] is False
    assert segments[1]["review_required"] is False
    assert segments[1]["review_reasons"] == []


def test_analyze_still_reports_existing_heuristics_alongside_new_reasons() -> None:
    analyzer = HeuristicSegmentAnalyzer()

    segments = analyzer.analyze(
        project_id="proj_1",
        transcript_segments=[_segment("Let's restart this section.", 0.0, 2.0, confidence=0.99)],
        script_text=None,
    )

    assert segments[0]["review_required"] is True
    assert "restart_keyword" in segments[0]["review_reasons"]
