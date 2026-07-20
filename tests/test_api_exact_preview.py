from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.exact_preview import ExactPreviewRequest
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _session(client: TestClient, tmp_path) -> tuple[str, str]:
    project_id = client.post("/api/projects", json={"name": "Exact preview API"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "output": {"width": 1280, "height": 720, "duration_sec": 2.0},
            "tracks": [],
        },
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": [{"segment_id": "s1", "caption_text": "caption", "start_sec": 0, "end_sec": 2}]},
    )
    return project_id, session["session_id"]


def test_exact_preview_api_exposes_fenced_status_and_no_legacy_final_url(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, session_id = _session(client, tmp_path)

    started = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/exact-preview",
        json={"expected_revision": 1, "start_sec": 0, "end_sec": 2},
    )

    assert started.status_code == 202
    body = started.json()
    assert body["status"] in {"pending", "running", "failed"}
    assert body["timeline_start_sec"] == 0.0
    assert body["timeline_end_sec"] == 2.0
    assert body["artifact_revision"] == 1
    assert body["generation_id"].startswith("exact_preview_")
    assert "artifact_uri" not in body and "url" not in body


def test_exact_preview_content_revalidates_session_and_refuses_range_after_stale_transition(tmp_path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, session_id = _session(client, tmp_path)
    store = LocalProjectStore(tmp_path)
    pipeline = LocalPipelineRunner(store)
    session, _timeline, plan, fingerprint = pipeline._exact_preview_inputs(project_id=project_id, session_id=session_id)
    record = store.begin_exact_preview(
        project_id=project_id,
        request=ExactPreviewRequest(session_id=session_id, expected_revision=1, start_sec=0, end_sec=2),
        fingerprint=fingerprint,
        duration_sec=plan.duration_sec,
    )
    source = tmp_path / "proxy.mp4"
    source.write_bytes(b"0123456789")
    assert store.claim_exact_preview(project_id=project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.finish_exact_preview(project_id=project_id, generation_id=record["generation_id"], fingerprint=fingerprint, artifact_path=source, owner_token="worker")
    content = f"/api/projects/{project_id}/exact-previews/{record['generation_id']}/content"
    ranged = client.get(content, headers={"Range": "bytes=2-5"})
    assert ranged.status_code == 206 and ranged.headers["accept-ranges"] == "bytes" and ranged.content == b"2345"
    assert client.get(content, headers={"Range": "bytes=999-1000"}).status_code == 416

    store.update_editing_session(project_id=project_id, session_id=session_id, session_payload=session, expected_revision=1)
    status = client.get(f"/api/projects/{project_id}/exact-previews/{record['generation_id']}")
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "stale" and status.json()["content_url"] is None
    assert client.get(content, headers={"Range": "bytes=2-5"}).status_code == 404


def test_exact_preview_status_revalidates_tracked_asset_fingerprint_before_exposing_url(tmp_path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "tracked source"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    source = tmp_path / "tracked.mp4"; source.write_bytes(b"original-source")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 2.0}, "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b1", "asset_id": asset.asset_id, "asset_uri": f"local://projects/{project_id}/assets/{asset.asset_id}", "start_sec": 0, "end_sec": 2,
        }]}]},
    )
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    pipeline = LocalPipelineRunner(store)
    _session_row, _timeline, plan, fingerprint = pipeline._exact_preview_inputs(project_id=project_id, session_id=session["session_id"])
    record = store.begin_exact_preview(project_id=project_id, request=ExactPreviewRequest(session_id=session["session_id"], expected_revision=1), fingerprint=fingerprint, duration_sec=plan.duration_sec)
    output = tmp_path / "proxy.mp4"; output.write_bytes(b"0123456789")
    assert store.claim_exact_preview(project_id=project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.finish_exact_preview(project_id=project_id, generation_id=record["generation_id"], fingerprint=fingerprint, artifact_path=output, owner_token="worker")
    stored_source = store.resolve_storage_uri(project_id=project_id, storage_uri=store.get_asset(project_id=project_id, asset_id=asset.asset_id)["storage_uri"])
    stored_source.write_bytes(b"changed-source")

    status = client.get(f"/api/projects/{project_id}/exact-previews/{record['generation_id']}")
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "stale" and status.json()["content_url"] is None


def test_exact_preview_revalidates_narration_source_uri_without_asset_id(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "narration uri source"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    raw = tmp_path / "narration.wav"; raw.write_bytes(b"narration-original")
    narration = store.register_asset(project_id=project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=raw)
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"narration_source_uri": narration.storage_uri, "output": {"duration_sec": 2}, "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "n1", "asset_uri": f"local://projects/{project_id}/segments/seg-1", "start_sec": 0, "end_sec": 2}]},
        ]},
    )
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    pipeline = LocalPipelineRunner(store)
    _row, _timeline, plan, fingerprint = pipeline._exact_preview_inputs(project_id=project_id, session_id=session["session_id"])
    record = store.begin_exact_preview(project_id=project_id, request=ExactPreviewRequest(session_id=session["session_id"], expected_revision=1), fingerprint=fingerprint, duration_sec=plan.duration_sec)
    output = tmp_path / "proxy.mp4"; output.write_bytes(b"0123456789")
    assert store.claim_exact_preview(project_id=project_id, generation_id=record["generation_id"], owner_token="worker")
    assert store.finish_exact_preview(project_id=project_id, generation_id=record["generation_id"], fingerprint=fingerprint, artifact_path=output, owner_token="worker")
    store.resolve_storage_uri(project_id=project_id, storage_uri=narration.storage_uri).write_bytes(b"narration-mutated")

    status = client.get(f"/api/projects/{project_id}/exact-previews/{record['generation_id']}")
    assert status.status_code == 200 and status.json()["status"] == "stale" and status.json()["content_url"] is None
