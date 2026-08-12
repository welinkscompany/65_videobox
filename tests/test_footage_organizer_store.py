from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from videobox_domain_models.footage_organizer import (
    FootageProposalStatus,
    FootageSourceSegment,
    VirtualSequenceItem,
)
from videobox_storage.footage_organizer_store import (
    FootageOrganizerStore,
    OptimisticRevisionConflict,
)
from videobox_storage.media_library_store import MediaLibraryStore


def test_source_segments_are_immutable_and_proposals_keep_boundaries(
    tmp_path: Path,
) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(
        source_id="source-1", source_sha256="a" * 64, filename="camera.mp4"
    )
    segment = store.create_source_segment(
        source_id=source.source_id, start_sec=1.5, end_sec=4.0, label="opening"
    )
    proposal = store.create_proposal(
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        segments=[segment],
    )

    with pytest.raises(ValueError, match="immutable"):
        store.update_source_segment(
            segment_id=segment.segment_id, start_sec=2.0, end_sec=4.0
        )

    loaded = store.get_proposal(proposal.proposal_id)
    assert loaded is not None
    assert loaded.segments[0].start_sec == 1.5
    assert loaded.segments[0].end_sec == 4.0
    assert loaded.source_sha256 == "a" * 64


def test_proposal_revision_is_optimistic_and_status_is_bounded(tmp_path: Path) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(source_id="source-1", source_sha256="b" * 64)
    segment = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=2.0
    )
    proposal = store.create_proposal(
        source_id=source.source_id, source_sha256="b" * 64, segments=[segment]
    )

    approved = store.set_proposal_status(
        proposal_id=proposal.proposal_id,
        status=FootageProposalStatus.APPROVED,
        expected_revision=proposal.revision,
    )
    assert approved.status is FootageProposalStatus.APPROVED
    assert approved.revision == proposal.revision + 1

    with pytest.raises(OptimisticRevisionConflict):
        store.set_proposal_status(
            proposal_id=proposal.proposal_id,
            status="rejected",
            expected_revision=proposal.revision,
        )
    with pytest.raises(ValueError, match="status"):
        store.set_proposal_status(
            proposal_id=proposal.proposal_id,
            status="published",
            expected_revision=approved.revision,
        )


def test_user_confirmed_fields_survive_reanalysis(tmp_path: Path) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(source_id="source-1", source_sha256="c" * 64)
    first = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=2.0
    )
    proposal = store.create_proposal(
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        segments=[first],
    )
    confirmed = store.confirm_proposal_fields(
        proposal_id=proposal.proposal_id,
        expected_revision=proposal.revision,
        fields={"title": "Hero take", "keep": True},
    )
    reanalyzed_segment = store.create_source_segment(
        source_id=source.source_id, start_sec=0.25, end_sec=1.75
    )
    updated = store.reanalyze_proposal(
        proposal_id=proposal.proposal_id,
        expected_revision=confirmed.revision,
        segments=[reanalyzed_segment],
        machine_fields={"score": 0.91},
    )

    assert updated.revision == confirmed.revision + 1
    assert updated.confirmed_fields == {"title": "Hero take", "keep": True}
    assert updated.segments[0].start_sec == 0.25
    assert updated.machine_fields == {"score": 0.91}


def test_virtual_sequence_preserves_explicit_item_order_and_restricts_source_delete(
    tmp_path: Path,
) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(source_id="source-1", source_sha256="d" * 64)
    first = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=1.0
    )
    second = store.create_source_segment(
        source_id=source.source_id, start_sec=3.0, end_sec=5.0
    )
    sequence = store.create_virtual_sequence(
        source_id=source.source_id,
        items=[
            VirtualSequenceItem.create(source_segment_id=second.segment_id, item_order=2),
            VirtualSequenceItem.create(source_segment_id=first.segment_id, item_order=1),
        ],
    )

    assert [item.source_segment_id for item in sequence.items] == [
        first.segment_id,
        second.segment_id,
    ]
    with pytest.raises(sqlite3.IntegrityError):
        store.delete_source(source.source_id)

    # Existing MediaLibraryStore connections see the same additive schema.
    media_store = MediaLibraryStore(tmp_path / "library")
    connection = sqlite3.connect(media_store.database_path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert {
        "footage_proposals",
        "footage_proposal_segments",
        "library_source_segments",
        "library_virtual_sequences",
        "library_virtual_sequence_items",
    } <= tables

