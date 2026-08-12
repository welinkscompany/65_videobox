from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.footage_organizer_store import FootageOrganizerStore
from videobox_storage.media_library_store import MediaLibraryStore


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
