from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

import pytest

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.footage_organizer_store import FootageOrganizerStore
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_core_engine.library_footage_indexer import (
    FOOTAGE_DESCRIPTION_VERSION,
    index_pending_library_footage,
)


def _client(tmp_path: Path, renderer=None) -> tuple[TestClient, MediaLibraryStore, str]:
    library = MediaLibraryStore(tmp_path / "library")
    source = tmp_path / "take.mp4"
    source.write_bytes(b"synthetic source")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    library.register_user_asset(
        library_asset_id="asset-take",
        media_type="broll",
        origin="user",
        content_sha256=digest,
        managed_relative_path="take.mp4",
        byte_count=source.stat().st_size,
        mime_type="video/mp4",
        lifecycle="ready",
    )
    # The global library root is the parent of managed_relative_path.
    source.replace(tmp_path / "library" / "take.mp4")
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=library,
        footage_detector=lambda _asset: {"total_duration": 4.0},
        footage_derivative_renderer=renderer,
    )
    return TestClient(app), library, digest


def test_proposal_edit_preview_cancel_and_double_approval_are_safe(tmp_path: Path) -> None:
    client, library, digest = _client(tmp_path)
    created = client.post(
        "/api/footage/proposals",
        json={"library_asset_id": "asset-take", "idempotency_key": "proposal-1"},
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert proposal["status"] == "draft"
    assert proposal["source_sha256"] == digest
    proposal_id = proposal["proposal_id"]

    edited = client.patch(
        f"/api/footage/proposals/{proposal_id}",
        json={
            "operation": "exclude",
            "expected_revision": proposal["revision"],
            "segment_id": proposal["segments"][0]["segment_id"],
        },
    )
    assert edited.status_code == 200, edited.text
    before = FootageOrganizerStore(tmp_path / "library").get_proposal(proposal_id)
    preview = client.post(
        f"/api/footage/proposals/{proposal_id}/preview",
        json={"expected_revision": edited.json()["revision"]},
    )
    cancel = client.post(f"/api/footage/proposals/{proposal_id}/cancel")
    assert preview.status_code == 200, preview.text
    assert "ranges=" in preview.json()["preview_url"]
    assert preview.json()["preview_url"].endswith("ranges=")
    assert "source-segment" not in preview.json()["preview_url"]
    assert cancel.status_code == 200, cancel.text
    after = FootageOrganizerStore(tmp_path / "library").get_proposal(proposal_id)
    assert before == after
    assert library.user_asset_store.get_asset("asset-take").content_sha256 == digest

    approved = client.post(
        f"/api/footage/proposals/{proposal_id}/approve",
        json={"expected_revision": edited.json()["revision"], "idempotency_key": "approve-1"},
    )
    replay = client.post(
        f"/api/footage/proposals/{proposal_id}/approve",
        json={"expected_revision": edited.json()["revision"], "idempotency_key": "approve-1"},
    )
    assert approved.status_code == replay.status_code == 200
    assert approved.json() == replay.json()
    assert approved.json()["status"] == "approved"
    queue = FootageOrganizerStore(tmp_path / "library").list_segment_index_queue()
    assert {item["source_segment_id"] for item in queue} == {
        segment["source_segment_id"] for segment in edited.json()["segments"]
    }


def test_virtual_sequence_reorder_preview_cancel_and_approval(tmp_path: Path) -> None:
    client, _library, _digest = _client(tmp_path)
    proposed = client.post(
        "/api/footage/proposals",
        json={"library_asset_id": "asset-take", "idempotency_key": "proposal-seq"},
    ).json()
    segment_id = proposed["segments"][0]["source_segment_id"]
    sequence = client.post(
        "/api/footage/sequences",
        json={
            "source_id": proposed["source_id"],
            "name": "short take",
            "items": [{"source_segment_id": segment_id, "item_order": 1}],
        },
    )
    assert sequence.status_code == 201, sequence.text
    sequence_id = sequence.json()["sequence_id"]
    reorder = client.patch(
        f"/api/footage/sequences/{sequence_id}/reorder",
        json={"expected_revision": 1, "item_ids": [sequence.json()["items"][0]["item_id"]]},
    )
    assert reorder.status_code == 200, reorder.text
    assert client.post(f"/api/footage/sequences/{sequence_id}/preview").status_code == 200
    assert client.post(f"/api/footage/sequences/{sequence_id}/cancel").status_code == 200
    approved = client.post(f"/api/footage/sequences/{sequence_id}/approve", json={"idempotency_key": "seq-1"})
    replay = client.post(f"/api/footage/sequences/{sequence_id}/approve", json={"idempotency_key": "seq-1"})
    assert approved.status_code == replay.status_code == 200
    assert approved.json() == replay.json()


def test_explicit_derivative_render_is_independent_and_idempotent(tmp_path: Path) -> None:
    seen_ranges: list[tuple[float, float]] = []

    def renderer(source: Path, output: Path, ranges: list[tuple[float, float]]) -> None:
        seen_ranges.extend(ranges)
        output.write_bytes(source.read_bytes() + b"\nderived")

    client, library, digest = _client(tmp_path, renderer=renderer)
    proposed = client.post(
        "/api/footage/proposals",
        json={"library_asset_id": "asset-take", "idempotency_key": "proposal-render"},
    ).json()
    approved = client.post(
        f"/api/footage/proposals/{proposed['proposal_id']}/approve",
        json={"expected_revision": proposed["revision"], "idempotency_key": "approve-render"},
    )
    assert approved.status_code == 200, approved.text
    rendered = client.post(
        "/api/footage/derivatives/render",
        json={"source_kind": "proposal", "source_id": proposed["proposal_id"], "idempotency_key": "render-1"},
    )
    replay = client.post(
        "/api/footage/derivatives/render",
        json={"source_kind": "proposal", "source_id": proposed["proposal_id"], "idempotency_key": "render-1"},
    )
    assert rendered.status_code == replay.status_code == 202
    assert rendered.json() == replay.json()
    assert rendered.json()["status"] == "succeeded"
    derived_id = rendered.json()["derived_asset_id"]
    assert derived_id != "asset-take"
    source = library.user_asset_store.get_asset("asset-take")
    assert source is not None and source.content_sha256 == digest
    derived = library.user_asset_store.get_asset(derived_id)
    assert derived is not None and derived.machine_metadata["semantic_index_status"] == "queued"
    assert any(item["library_asset_id"] == derived_id for item in library.list_footage_needing_analysis(paths=[tmp_path / "library" / "derived" / "footage"], description_version=2))
    assert seen_ranges == [(0.0, 4.0)]


def test_derivative_renderer_receives_all_approved_ranges_in_order(tmp_path: Path) -> None:
    seen_ranges: list[tuple[float, float]] = []

    def renderer(source: Path, output: Path, ranges: list[tuple[float, float]]) -> None:
        seen_ranges.extend(ranges)
        output.write_bytes(source.read_bytes() + b"\nderived")

    client, _library, _digest = _client(tmp_path, renderer=renderer)
    proposed = client.post(
        "/api/footage/proposals",
        json={
            "library_asset_id": "asset-take",
            "idempotency_key": "proposal-multi-range",
            "analysis": {
                "total_duration": 100.0,
                "analysis_windows": [
                    {"start_sec": 0.0, "end_sec": 6.0},
                    {"start_sec": 6.0, "end_sec": 12.0},
                ],
            },
        },
    ).json()
    approved = client.post(
        f"/api/footage/proposals/{proposed['proposal_id']}/approve",
        json={"expected_revision": proposed["revision"], "idempotency_key": "approve-multi-range"},
    )
    assert approved.status_code == 200, approved.text
    rendered = client.post(
        "/api/footage/derivatives/render",
        json={"source_kind": "proposal", "source_id": proposed["proposal_id"], "idempotency_key": "render-multi-range"},
    )
    assert rendered.status_code == 202 and rendered.json()["status"] == "succeeded"
    assert seen_ranges == [(0.0, 6.0), (6.0, 12.0), (12.0, 100.0)]


def test_source_preview_reuses_range_delivery_without_mutating_library(tmp_path: Path) -> None:
    client, library, _digest = _client(tmp_path)
    proposal = client.post(
        "/api/footage/proposals",
        json={"library_asset_id": "asset-take", "idempotency_key": "proposal-range"},
    ).json()
    source_id = proposal["source_id"]
    before = library.user_asset_store.get_asset("asset-take")
    response = client.get(
        f"/api/footage/sources/{source_id}/preview", headers={"Range": "bytes=0-3"}
    )
    assert response.status_code == 206
    assert response.content == b"synt"
    assert response.headers["accept-ranges"] == "bytes"
    assert library.user_asset_store.get_asset("asset-take") == before

    ranged = client.get(f"/api/footage/sources/{source_id}/preview?ranges=0.000-1.250,2.000-3.500")
    assert ranged.status_code == 503
    assert client.get(f"/api/footage/sources/{source_id}/preview?ranges=bad").status_code == 422


def test_proposal_preview_materializes_only_current_ranges(tmp_path: Path) -> None:
    seen: list[tuple[float, float]] = []

    def renderer(source: Path, output: Path, ranges: list[tuple[float, float]]) -> None:
        seen.extend(ranges)
        output.write_bytes("|".join(f"{start:.1f}-{end:.1f}" for start, end in ranges).encode())

    client, _library, _digest = _client(tmp_path, renderer=renderer)
    proposed = client.post(
        "/api/footage/proposals",
        json={"library_asset_id": "asset-take", "idempotency_key": "proposal-preview-ranges", "analysis": {"total_duration": 10.0, "analysis_windows": [{"start_sec": 1.0, "end_sec": 3.0}, {"start_sec": 6.0, "end_sec": 8.0}]}},
    ).json()
    preview = client.post(f"/api/footage/proposals/{proposed['proposal_id']}/preview", json={"expected_revision": proposed["revision"]})
    assert preview.status_code == 200
    response = client.get(preview.json()["preview_url"])
    assert response.status_code == 200
    expected_ranges = [(item["start_sec"], item["end_sec"]) for item in proposed["segments"]]
    assert response.content == "|".join(f"{start:.1f}-{end:.1f}" for start, end in expected_ranges).encode()
    assert seen == expected_ranges


def test_proposal_preview_fails_closed_when_range_renderer_fails(tmp_path: Path) -> None:
    def renderer(_source: Path, _output: Path, _ranges: list[tuple[float, float]]) -> None:
        raise RuntimeError("renderer unavailable")

    client, _library, _digest = _client(tmp_path, renderer=renderer)
    proposed = client.post("/api/footage/proposals", json={"library_asset_id": "asset-take", "idempotency_key": "proposal-preview-fail"}).json()
    preview = client.post(f"/api/footage/proposals/{proposed['proposal_id']}/preview", json={"expected_revision": proposed["revision"]})
    response = client.get(preview.json()["preview_url"])
    assert response.status_code == 503
    assert response.json()["detail"] == "footage_preview_render_unavailable"


class _SearchEmbeddings:
    def embed(self, request):
        class _Response:
            vectors = tuple([1.0, 0.0] for _ in request.inputs)

        return _Response()


def test_approved_segments_are_registered_in_library_search_with_stable_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, library, digest = _client(tmp_path)
    app = client.app
    app.state.media_analysis_embedding_provider = _SearchEmbeddings()
    app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}

    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(
        source_id="source:asset-take", source_sha256=digest,
        library_asset_id="asset-take", filename="take.mp4",
    )
    first = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=1.25,
        segment_id="fseg-first", label="첫 장면",
    )
    second = store.create_source_segment(
        source_id=source.source_id, start_sec=2.0, end_sec=3.5,
        segment_id="fseg-second", label="둘째 장면",
    )
    proposal = store.create_proposal(
        source_id=source.source_id, source_sha256=digest,
        segments=[first, second], proposal_id="fprop-search",
    )
    library.save_footage_descriptor(
        content_sha256=digest, library_asset_id="asset-take", filename="take.mp4",
        duration_seconds=4.0, width=1920, height=1080,
        tags={"layers": {"place": ["실내"]}},
        description="가로 영상. 두 장면이 이어지는 촬영본.", embedding=[1.0, 0.0],
        description_version=FOOTAGE_DESCRIPTION_VERSION,
    )

    original_register = library.register_approved_footage_segments
    calls = 0

    def lose_response(*, segments):
        nonlocal calls
        if calls == 0:
            calls += 1
            raise RuntimeError("simulated response loss after approval commit")
        return original_register(segments=segments)

    monkeypatch.setattr(library, "register_approved_footage_segments", lose_response)
    lost = client.post(
        f"/api/footage/proposals/{proposal.proposal_id}/approve",
        json={"expected_revision": proposal.revision, "idempotency_key": "approve-search"},
    )
    assert lost.status_code == 500
    monkeypatch.setattr(library, "register_approved_footage_segments", original_register)

    approved = client.post(
        f"/api/footage/proposals/{proposal.proposal_id}/approve",
        json={"expected_revision": proposal.revision, "idempotency_key": "approve-search"},
    )
    assert approved.status_code == 200, approved.text

    # The inherited parent embedding is already current, so approval must
    # reconcile the durable segment queue instead of leaving stale pending
    # work that the pending query can no longer discover.
    assert FootageOrganizerStore(tmp_path / "library").list_segment_index_queue() == []

    matches = client.get(
        "/api/library/search",
        params={"q": "장면", "media_type": "broll", "limit": 10},
    ).json()["matches"]
    found = {item.get("source_segment_id") for item in matches}
    assert {"fseg-first", "fseg-second"} <= found
    segment_matches = [item for item in matches if item.get("source_segment_id")]
    assert all(item["library_asset_id"] == "asset-take" for item in segment_matches)
    assert all(item["preview_url"] == "/api/library/assets/asset-take/preview" for item in segment_matches)
    assert {(item["source_sha256"], item["start_sec"], item["end_sec"]) for item in segment_matches} >= {
        (digest, 0.0, 1.25), (digest, 2.0, 3.5),
    }
    assert len([item for item in matches if item.get("source_segment_id") == "fseg-first"]) == 1

    replay = client.post(
        f"/api/footage/proposals/{proposal.proposal_id}/approve",
        json={"expected_revision": proposal.revision, "idempotency_key": "approve-search"},
    )
    assert replay.status_code == 200
    connection = sqlite3.connect(library.database_path)
    try:
        indexed = connection.execute(
            "SELECT source_segment_id FROM footage_index WHERE source_segment_id IS NOT NULL ORDER BY source_segment_id"
        ).fetchall()
    finally:
        connection.close()
    assert [str(row[0]) for row in indexed] == ["fseg-first", "fseg-second"]


def test_approved_segments_without_parent_embedding_are_indexer_pending_and_searchable(
    tmp_path: Path,
) -> None:
    client, library, digest = _client(tmp_path)
    app = client.app
    app.state.media_analysis_embedding_provider = _SearchEmbeddings()
    app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}

    store = FootageOrganizerStore(tmp_path / "library")
    source = store.register_source(
        source_id="source:asset-take", source_sha256=digest,
        library_asset_id="asset-take", filename="take.mp4",
    )
    first = store.create_source_segment(
        source_id=source.source_id, start_sec=0.0, end_sec=1.25,
        segment_id="fseg-first", label="첫 장면",
    )
    second = store.create_source_segment(
        source_id=source.source_id, start_sec=2.0, end_sec=3.5,
        segment_id="fseg-second", label="둘째 장면",
    )
    proposal = store.create_proposal(
        source_id=source.source_id, source_sha256=digest,
        segments=[first, second], proposal_id="fprop-pending-search",
    )

    approved = client.post(
        f"/api/footage/proposals/{proposal.proposal_id}/approve",
        json={"expected_revision": proposal.revision, "idempotency_key": "approve-pending-search"},
    )
    assert approved.status_code == 200, approved.text

    queue = store.list_segment_index_queue()
    assert {item["source_segment_id"] for item in queue if item["state"] == "pending"} == {
        "fseg-first", "fseg-second",
    }
    pending = library.list_footage_needing_analysis(
        paths=[tmp_path / "library" / "take.mp4"],
        description_version=FOOTAGE_DESCRIPTION_VERSION,
    )
    assert {item["source_segment_id"] for item in pending if item.get("is_segment")} == {
        "fseg-first", "fseg-second",
    }
    assert all(item["source_id"] == source.source_id for item in pending if item.get("is_segment"))
    assert all(item["library_asset_id"] == "asset-take" for item in pending if item.get("is_segment"))

    report = index_pending_library_footage(
        store=library,
        paths=[tmp_path / "library" / "take.mp4"],
        media_probe=None,
        vision_provider=None,
        vision_model_name=None,
        embedding_provider=_SearchEmbeddings(),
        embedding_model_name="test-embed",
        max_clips=2,
    )
    assert len(report.analyzed) == 2
    assert store.list_segment_index_queue() == []

    matches = client.get(
        "/api/library/search",
        params={"q": "장면", "media_type": "broll", "limit": 10},
    ).json()["matches"]
    segments = {item["source_segment_id"]: item for item in matches if item.get("source_segment_id")}
    assert {"fseg-first", "fseg-second"} <= set(segments)
    assert all(item["source_id"] == source.source_id for item in segments.values())
    assert all(item["library_asset_id"] == "asset-take" for item in segments.values())
    assert {(item["start_sec"], item["end_sec"]) for item in segments.values()} >= {
        (0.0, 1.25), (2.0, 3.5),
    }
