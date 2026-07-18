from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def test_storage_uri_resolution_rejects_path_escape(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Safe paths")

    with pytest.raises(ValueError, match="storage_uri_path_escape"):
        store.resolve_storage_uri(
            project_id=project.project_id,
            storage_uri=f"local://projects/{project.project_id}/../other-project/secret.mp4",
        )


def test_asset_and_final_content_are_project_scoped_and_support_byte_ranges(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    owner = client.post("/api/projects", json={"name": "Owner"}).json()["project_id"]
    outsider = client.post("/api/projects", json={"name": "Outsider"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"0123456789")
    asset = store.register_asset(project_id=owner, asset_type=AssetType.RAW_VIDEO, source_path=source, mime_type="video/mp4")
    timeline = store.save_timeline_run(project_id=owner, output_mode="review", timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []})
    export = store.save_final_render(project_id=owner, timeline_id=timeline["timeline_id"], source_output_path=source)
    job = store.create_job(project_id=owner, job_type=JobType.FINAL_RENDER, status=JobStatus.SUCCEEDED)
    store.update_job(project_id=owner, job_id=job["job_id"], status=JobStatus.SUCCEEDED, output_ref=export["export_id"])

    asset_url = f"/api/projects/{owner}/assets/{asset.asset_id}/content"
    final_url = f"/api/projects/{owner}/final-renders/{job['job_id']}/content"
    for url in (asset_url, final_url):
        response = client.get(url, headers={"Range": "bytes=2-5"})
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 2-5/10"
        assert response.content == b"2345"
        assert response.headers["content-type"].startswith("video/mp4")
        assert client.get(url, headers={"Range": "bytes=99-100"}).status_code == 416

    assert client.get(f"/api/projects/{outsider}/assets/{asset.asset_id}/content").status_code == 404
    assert client.get(f"/api/projects/{outsider}/final-renders/{job['job_id']}/content").status_code == 404


def test_unsafe_asset_content_is_download_only_and_all_successes_disable_mime_sniffing(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Safe browser"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    html = tmp_path / "not-a-video.html"
    html.write_text("<script>window.pwned=true</script>", encoding="utf-8")
    unsafe = store.register_asset(project_id=project, asset_type=AssetType.RAW_VIDEO, source_path=html, mime_type="text/html")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    safe = store.register_asset(project_id=project, asset_type=AssetType.RAW_VIDEO, source_path=video, mime_type="video/mp4")

    unsafe_response = client.get(f"/api/projects/{project}/assets/{unsafe.asset_id}/content")
    assert unsafe_response.status_code == 200
    assert unsafe_response.headers["content-type"].startswith("application/octet-stream")
    assert unsafe_response.headers["content-disposition"].startswith("attachment;")
    assert unsafe_response.headers["x-content-type-options"] == "nosniff"

    safe_response = client.get(f"/api/projects/{project}/assets/{safe.asset_id}/content", headers={"Range": "bytes=0-1"})
    assert safe_response.status_code == 206
    assert safe_response.headers["content-type"].startswith("video/mp4")
    assert safe_response.headers["x-content-type-options"] == "nosniff"


def test_flac_filename_mime_alias_is_normalized_to_playable_audio(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project = client.post("/api/projects", json={"name": "FLAC audition"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    flac = tmp_path / "audition.flac"
    flac.write_bytes(b"fLaC012345")
    asset = store.register_asset(project_id=project, asset_type=AssetType.NARRATION_AUDIO, source_path=flac)

    response = client.get(f"/api/projects/{project}/assets/{asset.asset_id}/content", headers={"Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.headers["content-type"].startswith("audio/flac")
    assert response.headers["content-range"] == "bytes 0-3/10"
    assert response.headers["x-content-type-options"] == "nosniff"
