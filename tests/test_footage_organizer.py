from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.footage_organizer import FootageOrganizerService
from videobox_core_engine.auto_cut import AutoCutPlanner
from videobox_core_engine.settings import AutoCutConfig
from videobox_domain_models.footage_organizer import FootageProposalSegment
from videobox_storage.footage_organizer_store import FootageOrganizerStore, OptimisticRevisionConflict
from videobox_storage.media_library_store import MediaLibraryStore


def _source(tmp_path: Path, *, asset_id: str = "asset-1", digest: str = "a" * 64):
    MediaLibraryStore(tmp_path / "library").register_user_asset(
        library_asset_id=asset_id,
        media_type="broll",
        origin="user",
        content_sha256=digest,
        managed_relative_path="take.mp4",
        byte_count=1,
        mime_type="video/mp4",
    )
    return FootageOrganizerStore(tmp_path / "library").register_source(
        source_id=f"source:{asset_id}",
        source_sha256=digest,
        library_asset_id=asset_id,
        filename="take.mp4",
    )


def _detector(_asset):
    return {
        "total_duration": 20.0,
        "scene_timestamps": [5.0, 15.0],
        "black_regions": [{"start": 9.0, "end": 10.0}],
        "static_windows": [{"start_sec": 15.0, "end_sec": 20.0}],
        "audio_windows": [{"start_sec": 0.5, "end_sec": 4.5}],
        "analysis_windows": [{"start_sec": 5.0, "end_sec": 9.0}],
    }


def test_propose_segments_combines_windows_with_explainable_reasons_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    store = FootageOrganizerStore(tmp_path / "library")
    service = FootageOrganizerService(
        store=store, detector=_detector, planner=AutoCutPlanner(config=AutoCutConfig(auto_cut_threshold=10.0))
    )

    proposal = service.propose_segments(source.library_asset_id, "request-1")

    assert proposal.status.value == "draft"
    assert [(s.start_sec, s.end_sec) for s in proposal.segments] == [
        (0.0, 0.5),
        (0.5, 4.5),
        (4.5, 5.0),
        (5.0, 9.0),
        (9.0, 10.0),
        (10.0, 15.0),
        (15.0, 20.0),
    ]
    assert "scene_change" in proposal.segments[3].machine_fields["reason_codes"]
    assert "black_screen" in proposal.segments[4].machine_fields["reason_codes"]
    assert proposal.segments[6].machine_fields["reason_labels"]
    assert store.get_source(source.source_id).source_sha256 == source.source_sha256
    assert store.get_source(source.source_id).filename == "take.mp4"


def test_short_input_returns_one_useful_segment_and_idempotent_retry_replays_same_proposal(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, asset_id="asset-short", digest="b" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    service = FootageOrganizerService(
        store=store,
        detector=lambda _asset: {"total_duration": 4.0, "scene_timestamps": [1.0]},
    )

    first = service.propose_segments("asset-short", "retry-key")
    second = service.propose_segments("asset-short", "retry-key")

    assert first.proposal_id == second.proposal_id
    assert first.revision == second.revision == 1
    assert [(s.start_sec, s.end_sec) for s in first.segments] == [(0.0, 4.0)]


def test_draft_operations_require_expected_revision_and_are_non_session_mutations(tmp_path: Path) -> None:
    source = _source(tmp_path, asset_id="asset-edit", digest="c" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    service = FootageOrganizerService(
        store=store,
        detector=lambda _asset: {
            "total_duration": 12.0,
            "analysis_windows": [{"start_sec": 0.0, "end_sec": 6.0}, {"start_sec": 6.0, "end_sec": 12.0}],
        },
        planner=AutoCutPlanner(config=AutoCutConfig(auto_cut_threshold=10.0)),
    )
    proposal = service.propose_segments("asset-edit", "edit-key")
    first = service.move_boundary(
        proposal_id=proposal.proposal_id,
        segment_id=proposal.segments[0].segment_id,
        boundary_sec=5.0,
        expected_revision=proposal.revision,
    )
    assert first.revision == 2
    split = service.split_draft(
        proposal_id=first.proposal_id,
        segment_id=first.segments[0].segment_id,
        split_sec=2.5,
        expected_revision=first.revision,
    )
    assert split.revision == 3
    excluded = service.exclude_draft(
        proposal_id=split.proposal_id,
        segment_id=split.segments[0].segment_id,
        expected_revision=split.revision,
    )
    assert excluded.revision == 4
    with pytest.raises(OptimisticRevisionConflict):
        service.exclude_draft(
            proposal_id=excluded.proposal_id,
            segment_id=excluded.segments[0].segment_id,
            expected_revision=split.revision,
        )


def test_approved_proposal_cannot_be_mutated_or_reanalyzed(tmp_path: Path) -> None:
    source = _source(tmp_path, asset_id="asset-approved", digest="d" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    service = FootageOrganizerService(
        store=store,
        detector=lambda _asset: {"total_duration": 4.0},
    )
    proposal = service.propose_segments("asset-approved", "approved-key")
    approved = store.set_proposal_status(
        proposal_id=proposal.proposal_id,
        status="approved",
        expected_revision=proposal.revision,
    )

    with pytest.raises(ValueError, match="draft"):
        service.exclude_draft(
            proposal_id=approved.proposal_id,
            segment_id=approved.segments[0].segment_id,
            expected_revision=approved.revision,
        )
    with pytest.raises(ValueError, match="draft"):
        store.reanalyze_proposal(
            proposal_id=approved.proposal_id,
            expected_revision=approved.revision,
            segments=[],
        )
    current = store.get_proposal(approved.proposal_id)
    assert current is not None
    assert current.status.value == "approved"
    assert current.revision == approved.revision
