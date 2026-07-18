from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _approved(client: TestClient, project_id: str) -> dict:
    path = f"/api/projects/{project_id}/creation-briefs"
    brief = client.post(path, json={"script_filename": "a.txt", "script_text": "제품 소개", "idempotency_key": "brief", "capability_profile": {}}).json()
    brief = client.post(f"{path}/{brief['brief_id']}/bypass", json={"expected_revision": brief["revision"]}).json()
    brief = client.patch(f"{path}/{brief['brief_id']}", json={"summary": "소개", "expected_revision": brief["revision"]}).json()
    return client.post(f"{path}/{brief['brief_id']}/approve", json={"expected_revision": brief["revision"]}).json()


def test_draft_readiness_api_resumes_and_keeps_preview_out_of_editing_sessions(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path)); project_id = client.post("/api/projects", json={"name": "Draft"}).json()["project_id"]
    brief = _approved(client, project_id); path = f"/api/projects/{project_id}/draft-readiness"
    run = client.post(path, json={"brief_id": brief["brief_id"], "narration_choice": {"kind": "silent"}, "idempotency_key": "run", "expected_brief_revision": brief["revision"]})
    assert run.status_code == 201
    assert run.json()["status"] == "asset_check"
    planning = client.post(f"{path}/{run.json()['readiness_id']}/retry", json={"expected_revision": run.json()["revision"]})
    assert planning.json()["status"] == "planning"
    complete = client.post(f"{path}/{run.json()['readiness_id']}/complete", json={"expected_revision": planning.json()["revision"]})
    assert complete.status_code == 200
    assert complete.json()["status"] == "needs_assets"
    assert LocalProjectStore(tmp_path).list_editing_sessions(project_id=project_id) == []


def test_draft_readiness_audio_upload_is_narration_and_options_hide_voice_samples(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path)); project_id = client.post("/api/projects", json={"name": "Audio"}).json()["project_id"]
    uploaded = client.post(f"/api/projects/{project_id}/draft-readiness/narration/upload", files={"file": ("voice.wav", b"wav", "audio/wav")})
    assert uploaded.status_code == 201 and uploaded.json()["asset_type"] == "narration_audio"
    options = client.get(f"/api/projects/{project_id}/draft-readiness/narration-options")
    assert options.status_code == 200
    assert options.json()["assets"] == [{"asset_id": uploaded.json()["asset_id"], "asset_type": "narration_audio"}]


def test_draft_readiness_upload_rejects_unknown_project_before_creating_staging(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    response = client.post("/api/projects/../../escape/draft-readiness/narration/upload", files={"file": ("voice.wav", b"wav", "audio/wav")})
    assert response.status_code in {400, 404}
    assert not (tmp_path / "projects" / ".." / ".." / "escape" / "staging").exists()


def test_draft_readiness_broll_upload_is_project_owned_and_locally_ready(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path)); project_id = client.post("/api/projects", json={"name": "Broll"}).json()["project_id"]
    response = client.post(f"/api/projects/{project_id}/draft-readiness/broll/upload", files={"file": ("scene.mp4", b"video", "video/mp4")})
    assert response.status_code == 201
    assert response.json()["asset_type"] == "broll_video"
    assert response.json()["scan_status"] == "local_ready"


def test_draft_readiness_api_rejects_a_candidate_range_beyond_known_video_length(tmp_path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Bounded range")
    client = TestClient(create_app(projects_root=tmp_path)); project_id = project.project_id
    brief = _approved(client, project_id)
    source = tmp_path / "scene.mp4"; source.write_bytes(b"video")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    store._execute(project_id, "UPDATE assets SET duration_sec = ? WHERE asset_id = ?", (3.0, asset.asset_id))
    base = f"/api/projects/{project_id}/draft-readiness"
    started = client.post(base, json={"brief_id": brief["brief_id"], "narration_choice": {"kind": "silent"}, "idempotency_key": "bounded", "expected_brief_revision": brief["revision"]}).json()
    planning = client.post(f"{base}/{started['readiness_id']}/retry", json={"expected_revision": started["revision"]}).json()
    ready = client.post(f"{base}/{started['readiness_id']}/complete", json={"expected_revision": planning["revision"]}).json()

    response = client.patch(f"{base}/{started['readiness_id']}/candidates/range", json={"asset_id": asset.asset_id, "start_sec": 1, "end_sec": 3.5, "expected_revision": ready["revision"]})

    assert response.status_code == 400
    assert response.json()["detail"] == "draft_readiness_candidate_range_invalid"
