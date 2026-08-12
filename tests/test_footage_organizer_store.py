from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
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


def _source(tmp_path: Path, *, source_id: str, digest: str):
    MediaLibraryStore(tmp_path / "library").register_user_asset(
        library_asset_id=f"asset-{source_id}",
        media_type="broll",
        origin="user",
        content_sha256=digest,
        managed_relative_path=f"{source_id}.mp4",
        byte_count=1,
        mime_type="video/mp4",
    )
    return FootageOrganizerStore(tmp_path / "library").register_source(
        source_id=source_id,
        source_sha256=digest,
        library_asset_id=f"asset-{source_id}",
    )


def test_source_segments_are_immutable_and_proposals_keep_boundaries(
    tmp_path: Path,
) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = _source(tmp_path, source_id="source-1", digest="a" * 64)
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


def test_source_requires_canonical_library_asset_and_finite_boundaries(
    tmp_path: Path,
) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    with pytest.raises(ValueError, match="library_asset_id"):
        store.register_source(
            source_id="orphan", source_sha256="e" * 64, library_asset_id=""
        )
    source = _source(tmp_path, source_id="source-finite", digest="f" * 64)
    with pytest.raises(ValueError, match="boundaries"):
        store.create_source_segment(
            source_id=source.source_id, start_sec=float("nan"), end_sec=1.0
        )
    with pytest.raises(ValueError, match="boundaries"):
        store.create_source_segment(
            source_id=source.source_id, start_sec=0.0, end_sec=float("inf")
        )


def test_canonical_library_asset_cannot_be_deleted_while_source_is_derived(
    tmp_path: Path,
) -> None:
    media_store = MediaLibraryStore(tmp_path / "library")
    media_store.register_user_asset(
        library_asset_id="asset-delete-guard",
        media_type="broll",
        origin="user",
        content_sha256="1" * 64,
        managed_relative_path="guard.mp4",
        byte_count=1,
        mime_type="video/mp4",
    )
    organizer = FootageOrganizerStore(tmp_path / "library")
    organizer.register_source(
        source_id="source-delete-guard",
        source_sha256="1" * 64,
        library_asset_id="asset-delete-guard",
    )
    with pytest.raises(sqlite3.IntegrityError):
        media_store.user_asset_store.permanently_delete_asset("asset-delete-guard")


def test_legacy_orphan_source_is_quarantined_from_reads(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    database = root / "media_library.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE library_footage_sources (source_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL, library_asset_id TEXT)"
        )
        connection.execute(
            "INSERT INTO library_footage_sources VALUES ('legacy-orphan', ?, 'old.mp4', '2026-01-01T00:00:00+00:00', NULL)",
            ("2" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    store = FootageOrganizerStore(root)
    assert store.get_source("legacy-orphan") is None
    assert store.list_sources() == []
    assert store.list_quarantined_sources() == ["legacy-orphan"]


def test_direct_sql_cannot_mutate_source_identity_or_segment_integrity(
    tmp_path: Path,
) -> None:
    _source(tmp_path, source_id="source-sql", digest="3" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    segment = store.create_source_segment(
        source_id="source-sql", start_sec=0.0, end_sec=1.0
    )
    connection = sqlite3.connect(store.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE library_footage_sources SET source_sha256 = ? WHERE source_id = ?",
                ("4" * 64, "source-sql"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE library_source_segments SET start_sec = ?, end_sec = ? WHERE segment_id = ?",
                (float("inf"), 2.0, segment.segment_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE library_source_segments SET start_sec = ? WHERE segment_id = ?",
                (0.25, segment.segment_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO library_source_segments (segment_id, source_id, source_sha256, start_sec, end_sec, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-segment", "source-sql", "9" * 64, 0.0, 1.0, "2026-01-01T00:00:00+00:00"),
            )
    finally:
        connection.rollback()
        connection.close()


def test_direct_sql_rejects_invalid_proposal_and_virtual_sequence_rows(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, source_id="source-sql-derived", digest="5" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    segment = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=1.0
    )
    proposal = store.create_proposal(
        source_id=source.source_id, source_sha256=source.source_sha256, segments=[segment]
    )
    sequence = store.create_virtual_sequence(
        source_id=source.source_id,
        items=[VirtualSequenceItem.create(source_segment_id=segment.segment_id, item_order=1)],
    )
    connection = sqlite3.connect(store.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE footage_proposals SET source_sha256 = ? WHERE proposal_id = ?",
                ("6" * 64, proposal.proposal_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE footage_proposal_segments SET start_sec = ? WHERE proposal_id = ?",
                (float("inf"), proposal.proposal_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE library_virtual_sequences SET source_sha256 = ? WHERE sequence_id = ?",
                ("6" * 64, sequence.sequence_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO library_virtual_sequence_items (item_id, sequence_id, item_order, source_segment_id, start_sec, end_sec) VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-item", sequence.sequence_id, 2, segment.segment_id, 0.0, float("inf")),
            )
    finally:
        connection.rollback()
        connection.close()


def test_virtual_sequence_item_cannot_reference_segment_from_another_source(
    tmp_path: Path,
) -> None:
    first = _source(tmp_path, source_id="source-seq-a", digest="8" * 64)
    second = _source(tmp_path, source_id="source-seq-b", digest="9" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    first_segment = store.create_source_segment(source_id=first.source_id, start_sec=0, end_sec=1)
    second_segment = store.create_source_segment(source_id=second.source_id, start_sec=0, end_sec=1)
    sequence = store.create_virtual_sequence(
        source_id=first.source_id,
        items=[VirtualSequenceItem.create(source_segment_id=first_segment.segment_id, item_order=1)],
    )
    connection = sqlite3.connect(store.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO library_virtual_sequence_items (item_id, sequence_id, item_order, source_segment_id) VALUES (?, ?, ?, ?)",
                ("cross-source-item", sequence.sequence_id, 2, second_segment.segment_id),
            )
    finally:
        connection.rollback()
        connection.close()


def test_proposal_and_sequence_parent_triggers_require_canonical_asset_hash(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, source_id="source-parent-canonical", digest="a" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    connection = sqlite3.connect(store.database_path)
    try:
        # Simulate a legacy/noncanonical parent: the source row still points at
        # an asset ID, but that asset's content hash no longer matches.
        connection.execute(
            "UPDATE library_user_assets SET content_sha256 = ? WHERE library_asset_id = ?",
            ("b" * 64, source.library_asset_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO footage_proposals (proposal_id, source_id, source_sha256, status, revision, confirmed_json, machine_json, created_at, updated_at) VALUES (?, ?, ?, 'draft', 1, '{}', '{}', ?, ?)",
                ("noncanonical-proposal", source.source_id, source.source_sha256, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO library_virtual_sequences (sequence_id, source_id, source_sha256, name, revision, created_at) VALUES (?, ?, ?, '', 1, ?)",
                ("noncanonical-sequence", source.source_id, source.source_sha256, "2026-01-01T00:00:00+00:00"),
            )
    finally:
        connection.rollback()
        connection.close()


def test_whitespace_legacy_source_is_quarantined_and_derived_reads_are_blocked(
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    root.mkdir()
    connection = sqlite3.connect(root / "media_library.sqlite")
    try:
        connection.execute(
            "CREATE TABLE library_footage_sources (source_id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL, library_asset_id TEXT)"
        )
        connection.execute(
            "CREATE TABLE footage_proposals (proposal_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_sha256 TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, confirmed_json TEXT NOT NULL, machine_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO library_footage_sources VALUES ('source-whitespace', ?, 'old.mp4', '2026-01-01T00:00:00+00:00', '   ')",
            ("7" * 64,),
        )
        connection.execute(
            "INSERT INTO footage_proposals VALUES ('legacy-proposal', 'source-whitespace', ?, 'draft', 1, '{}', '{}', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
            ("7" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    store = FootageOrganizerStore(root)
    source_id = "source-whitespace"
    assert store.get_source(source_id) is None
    assert store.list_sources() == []
    assert source_id in store.list_quarantined_sources()
    assert store.get_proposal("legacy-proposal") is None


def test_proposal_revision_is_optimistic_and_status_is_bounded(tmp_path: Path) -> None:
    store = FootageOrganizerStore(tmp_path / "library")
    source = _source(tmp_path, source_id="source-1", digest="b" * 64)
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
    source = _source(tmp_path, source_id="source-1", digest="c" * 64)
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
    source = _source(tmp_path, source_id="source-1", digest="d" * 64)
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


def test_virtual_sequence_keeps_each_item_source_identity(tmp_path: Path) -> None:
    first = _source(tmp_path, source_id="source-first", digest="1" * 64)
    second = _source(tmp_path, source_id="source-second", digest="2" * 64)
    store = FootageOrganizerStore(tmp_path / "library")
    first_segment = store.create_source_segment(source_id=first.source_id, start_sec=0.0, end_sec=1.0)
    second_segment = store.create_source_segment(source_id=second.source_id, start_sec=2.0, end_sec=3.0)

    sequence = store.create_virtual_sequence(
        source_id=first.source_id,
        items=[
            VirtualSequenceItem.create(
                source_id=second.source_id,
                source_segment_id=second_segment.segment_id,
                item_order=1,
                start_sec=2.0,
                end_sec=3.0,
            ),
            VirtualSequenceItem.create(
                source_id=first.source_id,
                source_segment_id=first_segment.segment_id,
                item_order=2,
                start_sec=0.0,
                end_sec=1.0,
            ),
        ],
    )

    loaded = store.get_virtual_sequence(sequence.sequence_id)
    assert loaded is not None
    assert [item.source_id for item in loaded.items] == [second.source_id, first.source_id]
    assert [source.source_id for source in loaded.sources] == [first.source_id, second.source_id]


def test_concurrent_library_connections_do_not_rebuild_schema_each_time(tmp_path: Path) -> None:
    root = tmp_path / "library"

    def open_and_list(_: int) -> list[object]:
        return FootageOrganizerStore(root).list_sources()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(open_and_list, range(8)))

    assert results == [[] for _ in range(8)]
