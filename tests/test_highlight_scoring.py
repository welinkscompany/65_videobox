from __future__ import annotations

from videobox_core_engine.highlight_scoring import select_highlight_segment_ids


def test_picks_dense_caption_segments_over_silent_ones() -> None:
    segments = [
        {"segment_id": "seg-dense", "caption_text": "정말 중요한 대사가 여기 가득 담겨 있어요", "start_sec": 0.0, "end_sec": 2.0},
        {"segment_id": "seg-silent", "caption_text": "", "start_sec": 2.0, "end_sec": 30.0},
    ]

    assert select_highlight_segment_ids(segments) == ("seg-dense",)


def test_preserves_chronological_order_of_picked_segments() -> None:
    segments = [
        {"segment_id": "seg-1", "caption_text": "짧은 말", "start_sec": 0.0, "end_sec": 1.0},
        {"segment_id": "seg-2", "caption_text": "훨씬 더 길고 밀도 높은 대사가 여기 있습니다 계속됩니다", "start_sec": 1.0, "end_sec": 2.0},
    ]

    # seg-2가 점수는 더 높지만(밀도), 원래 순서(seg-1 -> seg-2)를 유지해야 한다.
    assert select_highlight_segment_ids(segments) == ("seg-1", "seg-2")


def test_falls_back_to_full_list_when_nothing_scores() -> None:
    segments = [
        {"segment_id": "seg-a", "caption_text": "", "start_sec": 0.0, "end_sec": 5.0},
        {"segment_id": "seg-b", "caption_text": "", "start_sec": 5.0, "end_sec": 10.0},
    ]

    assert select_highlight_segment_ids(segments) == ("seg-a", "seg-b")


def test_empty_input_returns_empty_tuple() -> None:
    assert select_highlight_segment_ids([]) == ()
