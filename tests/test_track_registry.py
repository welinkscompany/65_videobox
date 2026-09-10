"""자유 멀티트랙 Phase 1 -- 트랙 레지스트리 모델·마이그레이션·검증.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 1.
아직 아무도 이 모델을 실제 렌더·세션에서 안 읽는다 -- 모델 자체의 앞뒤가
맞는지만 여기서 확인한다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.track_registry import (
    Track,
    TrackRegistryError,
    migrate_legacy_tracks_to_registry,
    validate_tracks,
)

_LEGACY_ROLES = ("narration", "broll", "bgm", "sfx", "overlay")


def test_migration_preserves_order_and_marks_narration_as_the_anchor() -> None:
    tracks = migrate_legacy_tracks_to_registry(_LEGACY_ROLES)

    assert [t.kind for t in tracks] == list(_LEGACY_ROLES)
    assert [t.order for t in tracks] == [0, 1, 2, 3, 4]
    anchors = [t for t in tracks if t.is_timing_anchor]
    assert len(anchors) == 1
    assert anchors[0].kind == "narration"


def test_a_track_with_an_unsupported_kind_is_rejected() -> None:
    with pytest.raises(TrackRegistryError):
        Track(track_id="t1", label="x", kind="not_a_real_kind", order=0)


def test_only_a_narration_track_may_be_the_timing_anchor() -> None:
    with pytest.raises(TrackRegistryError):
        Track(track_id="t1", label="x", kind="broll", order=0, is_timing_anchor=True)


def test_only_a_caption_track_may_carry_a_source_track_id() -> None:
    with pytest.raises(TrackRegistryError):
        Track(track_id="t1", label="x", kind="broll", order=0, source_track_id="track-narration")


def test_two_narration_anchors_is_rejected() -> None:
    tracks = [
        Track(track_id="n1", label="a", kind="narration", order=0, is_timing_anchor=True),
        Track(track_id="n2", label="b", kind="narration", order=1, is_timing_anchor=True),
    ]
    with pytest.raises(TrackRegistryError):
        validate_tracks(tracks)


def test_narration_tracks_present_but_no_anchor_is_rejected() -> None:
    """내레이션 트랙이 있는데 기준이 하나도 없으면 앞뒤가 안 맞는다."""
    tracks = [
        Track(track_id="n1", label="a", kind="narration", order=0, is_timing_anchor=False),
        Track(track_id="b1", label="b", kind="broll", order=1),
    ]
    with pytest.raises(TrackRegistryError):
        validate_tracks(tracks)


def test_no_narration_tracks_at_all_does_not_require_an_anchor() -> None:
    """대본만 있고 아직 내레이션이 없는 세션 -- 기준을 못 정하는 게 정상이다."""
    tracks = [Track(track_id="b1", label="b", kind="broll", order=0)]

    validate_tracks(tracks)  # 예외 없이 통과해야 한다


def test_a_second_non_anchor_narration_track_is_allowed() -> None:
    """내레이션이 여러 개라도 기준이 정확히 하나면 유효하다."""
    tracks = [
        Track(track_id="n1", label="a", kind="narration", order=0, is_timing_anchor=True),
        Track(track_id="n2", label="더빙", kind="narration", order=1, is_timing_anchor=False),
    ]

    validate_tracks(tracks)


def test_a_caption_track_pointing_at_a_real_narration_track_is_valid() -> None:
    tracks = [
        Track(track_id="n1", label="a", kind="narration", order=0, is_timing_anchor=True),
        Track(track_id="c1", label="자막", kind="caption", order=1, source_track_id="n1"),
    ]

    validate_tracks(tracks)


def test_a_caption_track_pointing_at_a_missing_narration_track_is_rejected() -> None:
    tracks = [
        Track(track_id="n1", label="a", kind="narration", order=0, is_timing_anchor=True),
        Track(track_id="c1", label="자막", kind="caption", order=1, source_track_id="does-not-exist"),
    ]
    with pytest.raises(TrackRegistryError):
        validate_tracks(tracks)


def test_duplicate_track_ids_are_rejected() -> None:
    tracks = [
        Track(track_id="dup", label="a", kind="broll", order=0),
        Track(track_id="dup", label="b", kind="bgm", order=1),
    ]
    with pytest.raises(TrackRegistryError):
        validate_tracks(tracks)


def test_duplicate_order_values_are_rejected() -> None:
    tracks = [
        Track(track_id="t1", label="a", kind="broll", order=0),
        Track(track_id="t2", label="b", kind="bgm", order=0),
    ]
    with pytest.raises(TrackRegistryError):
        validate_tracks(tracks)
