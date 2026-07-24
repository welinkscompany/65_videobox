from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.jobs import JobStatus, JobType


def test_approval_endpoint_creates_one_real_session_only_after_explicit_post(tmp_path):
    client = TestClient(create_app(projects_root=tmp_path)); project = client.post("/api/projects", json={"name": "Draft"}).json()["project_id"]
    base = f"/api/projects/{project}"; brief = client.post(f"{base}/creation-briefs", json={"script_filename":"a.txt", "script_text":"소개", "idempotency_key":"brief", "capability_profile":{}}).json()
    brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/bypass", json={"expected_revision":brief["revision"]}).json(); brief = client.patch(f"{base}/creation-briefs/{brief['brief_id']}", json={"summary":"소개", "expected_revision":brief["revision"]}).json(); brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/approve", json={"expected_revision":brief["revision"]}).json()
    upload = client.post(f"{base}/draft-readiness/broll/upload", files={"file": ("scene.mp4", b"local-scene", "video/mp4")})
    assert upload.status_code == 201
    run = client.post(f"{base}/draft-readiness", json={"brief_id":brief["brief_id"],"narration_choice":{"kind":"silent"},"idempotency_key":"ready","expected_brief_revision":brief["revision"],}).json()
    planning = client.post(f"{base}/draft-readiness/{run['readiness_id']}/retry", json={"expected_revision":run["revision"]}).json()
    run = client.post(f"{base}/draft-readiness/{run['readiness_id']}/complete", json={"expected_revision":planning["revision"]}).json()
    assert LocalProjectStore(tmp_path).list_editing_sessions(project_id=project) == []
    body = {"brief_id":brief["brief_id"],"readiness_id":run["readiness_id"],"expected_brief_revision":brief["revision"],"expected_readiness_revision":run["revision"],"idempotency_key":"once","allow_placeholder":True}
    made = client.post(f"{base}/draft-bundles", json=body)
    assert made.status_code == 201 and made.json()["session_id"] and made.json()["clip_ids"]
    assert client.post(f"{base}/draft-bundles", json=body).json()["session_id"] == made.json()["session_id"]
    manifest = client.get(f"{base}/editing-sessions/{made.json()['session_id']}/playback-manifest")
    assert manifest.status_code == 200
    assert manifest.json()["source_status"] == {"status": "current", "source_session_id": made.json()["session_id"], "source_session_revision": 1}
    assert manifest.json()["captions"]
    assert {track["track_type"] for track in manifest.json()["tracks"]} == {"narration", "broll"}
    assert manifest.json()["tracks"][0]["clips"][0]["clip_type"] == "narration"
    assert manifest.json()["tracks"][0]["clips"][0]["asset_id"]


def test_gap_bundle_is_hard_blocked_before_final_or_capcut_job_is_queued(tmp_path):
    client = TestClient(create_app(projects_root=tmp_path)); project = client.post("/api/projects", json={"name": "Gap"}).json()["project_id"]; base = f"/api/projects/{project}"
    brief = client.post(f"{base}/creation-briefs", json={"script_filename":"a.txt", "script_text":"소개", "idempotency_key":"brief", "capability_profile":{}}).json(); brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/bypass", json={"expected_revision":brief["revision"]}).json(); brief = client.patch(f"{base}/creation-briefs/{brief['brief_id']}", json={"summary":"소개", "expected_revision":brief["revision"]}).json(); brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/approve", json={"expected_revision":brief["revision"]}).json()
    run = client.post(f"{base}/draft-readiness", json={"brief_id":brief["brief_id"],"narration_choice":{"kind":"silent"},"idempotency_key":"ready","expected_brief_revision":brief["revision"]}).json(); planning = client.post(f"{base}/draft-readiness/{run['readiness_id']}/retry", json={"expected_revision":run["revision"]}).json(); run = client.post(f"{base}/draft-readiness/{run['readiness_id']}/complete", json={"expected_revision":planning["revision"]}).json()
    bundle = client.post(f"{base}/draft-bundles", json={"brief_id":brief["brief_id"],"readiness_id":run["readiness_id"],"expected_brief_revision":brief["revision"],"expected_readiness_revision":run["revision"],"idempotency_key":"once","allow_placeholder":True}).json()
    manifest = client.get(f"{base}/editing-sessions/{bundle['session_id']}/playback-manifest")
    assert manifest.status_code == 200
    assert manifest.json()["gap_slots"] == [{"gap_id": "gap-broll-1", "segment_id": bundle["segment_ids"][0], "start_sec": 0.0, "end_sec": 5.0, "reason": "장면을 보여 줄 영상이 없어요."}]
    placeholder = next(clip for track in manifest.json()["tracks"] if track["track_type"] == "broll" for clip in track["clips"] if clip["asset_id"].startswith("asset_gap_placeholder_"))
    matching_gap = next(gap for gap in manifest.json()["gap_slots"] if gap["gap_id"] == "gap-broll-1")
    assert placeholder["clip_type"] == "broll" and placeholder["segment_id"] == matching_gap["segment_id"]
    assert len(placeholder["expected_content_sha256"]) == 64 and placeholder["media_revision"]
    assert client.post(f"{base}/jobs/final-render", json={"timeline_job_id":bundle["timeline_job_id"]}).status_code == 400
    assert client.post(f"{base}/jobs/capcut-draft-export", json={"timeline_job_id":bundle["timeline_job_id"]}).status_code == 400


def test_final_render_content_is_project_scoped_playable_mp4(tmp_path):
    client = TestClient(create_app(projects_root=tmp_path)); project = client.post("/api/projects", json={"name": "Playback"}).json()["project_id"]
    store = LocalProjectStore(tmp_path); source = tmp_path / "actual.mp4"; source.write_bytes(b"fake-mp4")
    # The content endpoint uses the persisted export ownership, not a browser-supplied path.
    timeline = store.save_timeline_run(project_id=project, output_mode="review", timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []})
    exported = store.save_final_render(project_id=project, timeline_id=timeline["timeline_id"], source_output_path=source)
    job = store.create_job(project_id=project, job_type=JobType.FINAL_RENDER, status=JobStatus.SUCCEEDED); store.update_job(project_id=project, job_id=job["job_id"], status=JobStatus.SUCCEEDED, output_ref=exported["export_id"])
    response = client.get(f"/api/projects/{project}/final-renders/{job['job_id']}/content")
    assert response.status_code == 200 and response.headers["content-type"].startswith("video/mp4") and response.content == b"fake-mp4"
