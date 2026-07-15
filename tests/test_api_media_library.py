from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_capcut_export.adapter import CapCutExportAdapter
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_freshness
from videobox_core_engine.media_pack_service import MediaPackService, compute_pack_integrity
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore
from videobox_domain_models.assets import AssetType
import videobox_core_engine.project_asset_materializer as materializer_module


def _indexed_library(tmp_path: Path) -> MediaLibraryStore:
    asset_path = tmp_path / "installed-pack" / "assets" / "music-001.mp3"
    sfx_path = tmp_path / "installed-pack" / "assets" / "sfx-001.wav"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"synthetic music")
    sfx_path.write_bytes(b"synthetic sfx")
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    sfx_digest = hashlib.sha256(sfx_path.read_bytes()).hexdigest()
    library = MediaLibraryStore(tmp_path / "library")
    library.index_verified_pack(
        pack_id="starter-001",
        version="1.0.0",
        install_path=asset_path.parents[1],
        assets=[
            {
                "library_asset_id": "pack:starter-001:music-001",
                "asset_id": "music-001",
                "media_type": "music",
                "duration_seconds": 12.5,
                "tags": ["calm", "business"],
                "sha256": digest,
                "path": asset_path,
                "source": "Synthetic source",
                "creator": "Synthetic creator",
                "license": {
                    "official_url": "https://example.test/license",
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "a" * 64,
                    "attribution_required": True,
                    "attribution_text": "Music by Synthetic creator",
                },
            }
            ,
            {
                "library_asset_id": "pack:starter-001:sfx-001",
                "asset_id": "sfx-001",
                "media_type": "sfx",
                "duration_seconds": 1.0,
                "tags": ["impact"],
                "sha256": sfx_digest,
                "path": sfx_path,
                "source": "Synthetic source",
                "creator": "Synthetic creator",
                "license": {
                    "official_url": "https://example.test/license",
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "a" * 64,
                    "attribution_required": False,
                    "attribution_text": "",
                },
            },
        ],
    )
    return library


def _installable_sparse_pack(root: Path) -> Path:
    asset = root / "assets" / "music-001.mp3"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"synthetic music")
    evidence = root / "evidence" / "music-001.txt"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("Synthetic official license evidence", encoding="utf-8")
    padding = root / "padding.bin"
    with padding.open("wb") as handle:
        handle.truncate(300 * 1024**2 - asset.stat().st_size)
    declared_bytes, pack_sha256 = compute_pack_integrity(root)
    manifest = {
        "pack_id": "starter-001", "version": "1.0.0", "declared_bytes": declared_bytes,
        "sha256": pack_sha256,
        "assets": [{"asset_id": "music-001", "pack_path": "assets/music-001.mp3", "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "media_type": "music", "duration_seconds": 12.5, "source": "Synthetic", "creator": "Synthetic", "license": {"official_url": "https://example.test/license", "commercial_use": True, "redistribution": True, "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_materialize_verified_library_music_registers_a_project_local_bgm_with_license_snapshot(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id = client.post("/api/projects", json={"name": "Library materialization"}).json()["project_id"]

    response = client.post(
        "/api/media-library/assets/pack:starter-001:music-001/materialize",
        json={"project_id": project_id},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["asset_type"] == "bgm"
    assert payload["storage_uri"].startswith(f"local://projects/{project_id}/assets/")
    assert hashlib.sha256(
        LocalProjectStore(tmp_path / "projects").resolve_storage_uri(project_id=project_id, storage_uri=payload["storage_uri"]).read_bytes()
    ).hexdigest() == hashlib.sha256((tmp_path / "installed-pack" / "assets" / "music-001.mp3").read_bytes()).hexdigest()
    assert payload["metadata"] == {
        "source_library_asset_id": "pack:starter-001:music-001",
        "source_pack_id": "starter-001",
        "source_pack_version": "1.0.0",
        "license_snapshot": {
            "official_url": "https://example.test/license",
            "evidence_timestamp": "2026-07-12T10:00:00Z",
            "evidence_sha256": "a" * 64,
            "source": "Synthetic source",
            "creator": "Synthetic creator",
            "attribution_required": True,
            "attribution_text": "Music by Synthetic creator",
        },
    }
    assert library.list_recent_usage() == ["pack:starter-001:music-001"]


def test_materialize_missing_library_asset_returns_422_without_creating_project_asset_or_recent_usage(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id = client.post("/api/projects", json={"name": "Missing library asset"}).json()["project_id"]

    response = client.post(
        "/api/media-library/assets/pack:starter-001:missing/materialize",
        json={"project_id": project_id},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"
    assert library.list_recent_usage() == []


def test_library_materialize_does_not_reuse_same_sha_user_uploaded_audio(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    app = create_app(projects_root=tmp_path / "projects", media_library_store=library)
    client = TestClient(app); project_id = client.post("/api/projects", json={"name": "provenance"}).json()["project_id"]
    same_bytes = tmp_path / "user.mp3"; same_bytes.write_bytes(b"synthetic music")
    user_asset = app.state.store.register_asset(project_id=project_id, asset_type=AssetType.BGM, source_path=same_bytes, source_kind="user_uploaded")
    materialized = client.post("/api/media-library/assets/pack:starter-001:music-001/materialize", json={"project_id": project_id})
    assert materialized.status_code == 201
    assert materialized.json()["asset_id"] != user_asset.asset_id
    assert materialized.json()["metadata"]["source_library_asset_id"] == "pack:starter-001:music-001"
    assert materialized.json()["metadata"]["license_snapshot"]["official_url"] == "https://example.test/license"


def test_library_materialize_same_sha_is_concurrent_idempotent_and_failure_cleans_registered_copy(tmp_path: Path, monkeypatch) -> None:
    library = _indexed_library(tmp_path)
    app = create_app(projects_root=tmp_path / "projects", media_library_store=library)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "same sha"}).json()["project_id"]
    path = "/api/media-library/assets/pack:starter-001:music-001/materialize"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: TestClient(app).post(path, json={"project_id": project_id}), range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["asset_id"] == responses[1].json()["asset_id"]
    assert len(LocalProjectStore(tmp_path / "projects").list_assets(project_id=project_id)) == 1

    project_store = app.state.store
    original_sha = materializer_module.sha256_file
    def mismatch_only_after_copy(path: Path) -> str:
        if path.suffix == ".wav" and "projects" in str(path):
            return "0" * 64
        return original_sha(path)
    monkeypatch.setattr(materializer_module, "sha256_file", mismatch_only_after_copy)
    second = client.post("/api/media-library/assets/pack:starter-001:sfx-001/materialize", json={"project_id": project_id})
    assert second.status_code == 422
    assert len(project_store.list_assets(project_id=project_id)) == 1


def test_media_library_list_and_favorite_api_expose_verified_assets_and_persist_global_favorites(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))

    listed = client.get("/api/media-library/assets")

    assert listed.status_code == 200
    assert listed.json()["assets"] == [
        {
            "library_asset_id": "pack:starter-001:music-001",
            "asset_id": "music-001",
            "media_type": "music",
            "duration_seconds": 12.5,
            "version": "1.0.0",
            "verified": True,
            "available": True,
            "source": "Synthetic source",
            "creator": "Synthetic creator",
            "official_license_url": "https://example.test/license",
            "evidence_timestamp": "2026-07-12T10:00:00Z",
            "tags": ["calm", "business"],
            "attribution_required": True,
            "attribution_text": "Music by Synthetic creator",
        },
        {
            "library_asset_id": "pack:starter-001:sfx-001",
            "asset_id": "sfx-001",
            "media_type": "sfx",
            "duration_seconds": 1.0,
            "version": "1.0.0",
            "verified": True,
            "available": True,
            "source": "Synthetic source",
            "creator": "Synthetic creator",
            "official_license_url": "https://example.test/license",
            "evidence_timestamp": "2026-07-12T10:00:00Z",
            "tags": ["impact"],
            "attribution_required": False,
            "attribution_text": "",
        },
    ]
    favorite = client.put("/api/media-library/assets/pack:starter-001:music-001/favorite", json={"enabled": True})
    assert favorite.status_code == 200
    assert favorite.json() == {"asset_ids": ["pack:starter-001:music-001"]}
    assert client.get("/api/media-library/favorites").json() == {"asset_ids": ["pack:starter-001:music-001"]}


def test_verified_library_asset_preview_streams_without_creating_project_state(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))

    preview = client.get("/api/media-library/assets/pack:starter-001:music-001/preview")

    assert preview.status_code == 200
    assert preview.content == b"synthetic music"
    assert preview.headers["content-type"] == "audio/mpeg"


def test_media_library_api_exposes_install_state_and_metadata_for_tag_duration_attribution_search(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))

    state = client.get("/api/media-library/install-state")
    listed = client.get("/api/media-library/assets")

    assert state.json() == {"status": "installed", "installed_asset_count": 2}
    music = listed.json()["assets"][0]
    assert music["tags"] == ["calm", "business"]
    assert music["duration_seconds"] == 12.5
    assert music["attribution_required"] is True
    assert music["attribution_text"] == "Music by Synthetic creator"


def test_media_library_api_reports_not_installed_without_blocking_project_api(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path / "projects"))

    assert client.get("/api/media-library/install-state").json() == {"status": "not_installed", "installed_asset_count": 0}
    assert client.post("/api/projects", json={"name": "Still editable"}).status_code == 201


def test_tampered_library_asset_stays_visible_as_disabled_and_cannot_preview_or_materialize(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    (tmp_path / "installed-pack" / "assets" / "music-001.mp3").write_bytes(b"tampered")

    assets = client.get("/api/media-library/assets").json()["assets"]

    tampered = next(asset for asset in assets if asset["asset_id"] == "music-001")
    assert tampered["available"] is False
    assert tampered["verified"] is False
    assert client.get("/api/media-library/assets/pack:starter-001:music-001/preview").status_code == 422
    project_id = client.post("/api/projects", json={"name": "Tampered media"}).json()["project_id"]
    assert client.post("/api/media-library/assets/pack:starter-001:music-001/materialize", json={"project_id": project_id}).status_code == 422


def test_media_library_favorite_rejects_unknown_or_unavailable_asset_ids(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))

    response = client.put("/api/media-library/assets/pack:starter-001:missing/favorite", json={"enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"
    assert library.list_favorites() == []


def test_materialize_rejects_source_swapped_after_lookup_before_project_registration(tmp_path: Path, monkeypatch) -> None:
    library = _indexed_library(tmp_path)
    original_get = library.get_verified_asset
    source = tmp_path / "installed-pack" / "assets" / "music-001.mp3"

    def swap_after_lookup(*, library_asset_id: str):
        asset = original_get(library_asset_id=library_asset_id)
        source.write_bytes(b"swapped after verification")
        return asset

    monkeypatch.setattr(library, "get_verified_asset", swap_after_lookup)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id = client.post("/api/projects", json={"name": "Swap guard"}).json()["project_id"]

    response = client.post("/api/media-library/assets/pack:starter-001:music-001/materialize", json={"project_id": project_id})

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"
    assert LocalProjectStore(tmp_path / "projects").list_assets(project_id=project_id) == []


def test_preview_rejects_source_swapped_after_lookup_before_response(tmp_path: Path, monkeypatch) -> None:
    library = _indexed_library(tmp_path)
    original_get = library.get_verified_asset
    source = tmp_path / "installed-pack" / "assets" / "music-001.mp3"

    def swap_after_lookup(*, library_asset_id: str):
        asset = original_get(library_asset_id=library_asset_id)
        source.write_bytes(b"swapped after verification")
        return asset

    monkeypatch.setattr(library, "get_verified_asset", swap_after_lookup)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))

    response = client.get("/api/media-library/assets/pack:starter-001:music-001/preview")

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"


def test_installed_sparse_pack_materializes_into_a_project_local_asset(tmp_path: Path) -> None:
    library = MediaLibraryStore(tmp_path / "library")
    service = MediaPackService(
        user_library_root=tmp_path / "user-library",
        library_store=library,
        duration_probe=lambda _path: 12.5,
        media_probe=lambda _path: {"codec_name": "mp3", "bit_rate": "320000", "is_cbr": True},
    )
    assert service.install(_installable_sparse_pack(tmp_path / "source-pack")).status == "installed"
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id = client.post("/api/projects", json={"name": "Installed pack materialization"}).json()["project_id"]

    response = client.post("/api/media-library/assets/pack:starter-001:music-001/materialize", json={"project_id": project_id})

    assert response.status_code == 201
    asset = response.json()
    assert asset["storage_uri"].startswith(f"local://projects/{project_id}/assets/imported/")
    assert FfmpegFinalRenderer(store=LocalProjectStore(tmp_path / "projects"))._resolve_generic_asset_uri(project_id=project_id, asset_uri=asset["storage_uri"]).is_file()


def test_materialize_rejects_an_existing_library_asset_after_checksum_verification_is_lost(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    project_store = LocalProjectStore(tmp_path / "projects")
    session_before = project_store.get_editing_session(project_id=project_id, session_id=session_id)
    timeline_before = project_store.get_timeline_run(project_id=project_id, timeline_id=session_before["timeline_id"])
    assets_before = project_store.list_assets(project_id=project_id)
    recent_before = library.list_recent_usage()
    (tmp_path / "installed-pack" / "assets" / "music-001.mp3").write_bytes(b"tampered")

    response = client.post(
        "/api/media-library/assets/pack:starter-001:music-001/materialize",
        json={"project_id": project_id},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"
    assert project_store.list_assets(project_id=project_id) == assets_before
    assert project_store.get_editing_session(project_id=project_id, session_id=session_id) == session_before
    assert project_store.get_timeline_run(project_id=project_id, timeline_id=session_before["timeline_id"]) == timeline_before
    assert library.list_recent_usage() == recent_before


def _create_timeline_session(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    narration = tmp_path / "narration.wav"
    script = tmp_path / "script.txt"
    narration.write_bytes(b"narration")
    script.write_text("One sentence.", encoding="utf-8")
    project_id = client.post("/api/projects", json={"name": "Materialized timeline"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_job_id, "script_asset_id": script_asset_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={"segment_analysis_job_id": segment_job_id, "recommendation_job_ids": []},
    ).json()["job_id"]
    session_id = client.post(
        f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job_id},
    ).json()["session_id"]
    return project_id, session_id


def test_partial_regeneration_stamps_output_provenance_with_final_session_revision_and_later_edit_is_stale(
    tmp_path: Path,
) -> None:
    """Partial regeneration must not make its newly-created timeline stale at birth."""
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    partial = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={"segment_ids": ["seg_001"], "fields": ["caption"], "expected_revision": before["session_revision"]},
    )
    assert partial.status_code == 202, partial.text
    partial_job_id = partial.json()["job_id"]
    timeline = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial_job_id}").json()["timeline"]
    refreshed = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()
    assert timeline["source_session_revision"] == refreshed["session_revision"]

    store = LocalProjectStore(tmp_path / "projects")
    review = store.get_review_state(project_id=project_id, timeline_id=timeline["timeline_id"])
    assert review["source_session_revision"] == refreshed["session_revision"]
    assert review["is_current"] is True
    verify_output_freshness(editing_session=refreshed, timeline=timeline, review=review)

    changed = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/caption",
        json={"caption_text": "A genuine later edit.", "expected_revision": refreshed["session_revision"]},
    )
    assert changed.status_code == 200, changed.text
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset: editing session revision changed"):
        verify_output_freshness(editing_session=changed.json(), timeline=timeline, review=review)


def test_only_materialized_matching_project_audio_assets_can_override_and_build_timeline(tmp_path: Path) -> None:
    library = _indexed_library(tmp_path)
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=library))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    raw_id_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": "music-001", "expected_revision": before["session_revision"]},
    )

    assert raw_id_response.status_code == 422
    assert raw_id_response.json()["detail"] == "asset_missing"
    assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json() == before

    bgm = client.post(
        "/api/media-library/assets/pack:starter-001:music-001/materialize", json={"project_id": project_id},
    ).json()
    wrong_type_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/sfx",
        json={"asset_id": bgm["asset_id"], "expected_revision": before["session_revision"]},
    )
    assert wrong_type_response.status_code == 422
    assert wrong_type_response.json()["detail"] == "asset_missing"
    assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json() == before
    sfx = client.post(
        "/api/media-library/assets/pack:starter-001:sfx-001/materialize", json={"project_id": project_id},
    ).json()
    music_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/music",
        json={"asset_id": bgm["asset_id"], "expected_revision": before["session_revision"]},
    )
    sfx_response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/sfx",
        json={"asset_id": sfx["asset_id"], "expected_revision": before["session_revision"] + 1},
    )

    assert music_response.status_code == 200
    assert sfx_response.status_code == 200
    assert music_response.json()["segments"][0]["music_override"]["asset_uri"] == bgm["storage_uri"]
    assert sfx_response.json()["segments"][0]["sfx_override"]["asset_uri"] == sfx["storage_uri"]

    partial = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/partial-regeneration",
        json={"segment_ids": ["seg_001"], "fields": ["music", "sfx"], "expected_revision": before["session_revision"] + 2},
    )
    assert partial.status_code == 202
    timeline = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{partial.json()['job_id']}",
    ).json()["timeline"]
    bgm_track = next(track for track in timeline["tracks"] if track["track_type"] == "bgm")
    assert [clip["asset_uri"] for clip in bgm_track["clips"]] == [bgm["storage_uri"]]
    assert bgm["storage_uri"].endswith("/assets/imported/music-001.mp3")

    approval = client.post(
        f"/api/projects/{project_id}/review-snapshots/{partial.json()['job_id']}/recommendations/manual_sfx_seg_001/approve",
    )
    assert approval.status_code == 200
    approved_timeline = client.get(
        f"/api/projects/{project_id}/partial-regenerations/{partial.json()['job_id']}",
    ).json()["timeline"]
    sfx_track = next(track for track in approved_timeline["tracks"] if track["track_type"] == "sfx")
    assert [clip["asset_uri"] for clip in sfx_track["clips"]] == [sfx["storage_uri"]]
    project_store = LocalProjectStore(tmp_path / "projects")
    renderer = FfmpegFinalRenderer(store=project_store)
    assert renderer._resolve_generic_asset_uri(project_id=project_id, asset_uri=bgm["storage_uri"]).is_file()
    assert renderer._resolve_generic_asset_uri(project_id=project_id, asset_uri=sfx["storage_uri"]).is_file()
    capcut_payload = CapCutExportAdapter().build_payload(project_id=project_id, timeline=approved_timeline)
    bgm_payload = next(track for track in capcut_payload["capcut_tracks"] if track["track_name"] == "bgm")
    assert bgm_payload["segments"][0]["source_uri"] == bgm["storage_uri"]
    sfx_payload = next(track for track in capcut_payload["capcut_tracks"] if track["track_name"] == "sfx")
    assert sfx_payload["segments"][0]["source_uri"] == sfx["storage_uri"]
