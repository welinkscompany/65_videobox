from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_capcut_export.adapter import CapCutExportAdapter
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_pack_service import MediaPackService, compute_pack_integrity
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.media_library_store import MediaLibraryStore


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
                "sha256": digest,
                "path": asset_path,
                "source": "Synthetic source",
                "creator": "Synthetic creator",
                "license": {
                    "official_url": "https://example.test/license",
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "a" * 64,
                },
            }
            ,
            {
                "library_asset_id": "pack:starter-001:sfx-001",
                "asset_id": "sfx-001",
                "media_type": "sfx",
                "duration_seconds": 1.0,
                "sha256": sfx_digest,
                "path": sfx_path,
                "source": "Synthetic source",
                "creator": "Synthetic creator",
                "license": {
                    "official_url": "https://example.test/license",
                    "evidence_timestamp": "2026-07-12T10:00:00Z",
                    "evidence_sha256": "a" * 64,
                },
            },
        ],
    )
    return library


def _installable_sparse_pack(root: Path) -> Path:
    asset = root / "assets" / "music-001.mp3"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"synthetic music")
    padding = root / "padding.bin"
    with padding.open("wb") as handle:
        handle.truncate(300 * 1024**2 - asset.stat().st_size)
    declared_bytes, pack_sha256 = compute_pack_integrity(root)
    manifest = {
        "pack_id": "starter-001", "version": "1.0.0", "declared_bytes": declared_bytes,
        "sha256": pack_sha256,
        "assets": [{"asset_id": "music-001", "pack_path": "assets/music-001.mp3", "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "media_type": "music", "duration_seconds": 12.5, "source": "Synthetic", "creator": "Synthetic", "license": {"official_url": "https://example.test/license", "commercial_use": True, "redistribution": True, "evidence_timestamp": "2026-07-12T10:00:00Z", "evidence_sha256": "a" * 64}}],
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


def test_installed_sparse_pack_materializes_into_a_project_local_asset(tmp_path: Path) -> None:
    library = MediaLibraryStore(tmp_path / "library")
    service = MediaPackService(user_library_root=tmp_path / "user-library", library_store=library, duration_probe=lambda _path: 12.5)
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
