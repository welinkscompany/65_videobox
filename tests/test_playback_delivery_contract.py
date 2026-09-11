import re
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


def _make_final_render_job(store: LocalProjectStore, *, project_id: str, tmp_path: Path):
    """완성본 job 하나를 실제 저장소 경로에 만든다 -- 여러 시험이 공유하는 셋업."""
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"0123456789")
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review",
        timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []},
    )
    export = store.save_final_render(project_id=project_id, timeline_id=timeline["timeline_id"], source_output_path=source)
    job = store.create_job(project_id=project_id, job_type=JobType.FINAL_RENDER, status=JobStatus.SUCCEEDED)
    store.update_job(project_id=project_id, job_id=job["job_id"], status=JobStatus.SUCCEEDED, output_ref=export["export_id"])
    return job


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


def test_final_render_content_has_a_download_filename_and_range_playback_still_works(tmp_path: Path) -> None:
    """완성본 내려받기 이름 문제(task-3, 2026-09-11): `video/mp4`는 인라인 취급이라
    `Content-Disposition`이 안 붙었고, 브라우저는 확장자 없는 `content`로 저장했다.

    같은 주소를 화면의 <video> 태그가 재생에도 쓴다(OutputsPage.tsx) -- 이름을
    붙이면서 Range 재생(206)이 그대로인지 한 시험에서 같이 지킨다.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    owner = client.post("/api/projects", json={"name": "가을 브이로그"}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    job = _make_final_render_job(store, project_id=owner, tmp_path=tmp_path)
    final_url = f"/api/projects/{owner}/final-renders/{job['job_id']}/content"

    playback = client.get(final_url, headers={"Range": "bytes=2-5"})
    assert playback.status_code == 206
    assert playback.headers["content-type"].startswith("video/mp4")
    assert playback.headers["content-range"] == "bytes 2-5/10"
    assert playback.content == b"2345"

    download = client.get(final_url)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("video/mp4")
    disposition = download.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    extended_name = unquote(disposition.split("filename*=UTF-8''", 1)[1])
    assert extended_name == "가을 브이로그.mp4"


def test_final_render_content_disposition_caps_an_unbounded_project_name(tmp_path: Path) -> None:
    """감사 실측(final-fix-report.md 발견 3): 300자 한글 이름은 2,753자 헤더를
    만들고, ~430자부터 nginx `proxy_buffer_size`(기본 4k)를 넘겨 재생·내려받기
    둘 다 502로 죽는다. `TestClient`는 실제 nginx를 지나지 않아(§10 메모) 502
    자체는 여기서 못 재현하지만, 헤더 길이가 안전 범위 안에 있는지와 퍼센트
    인코딩이 코드 포인트 중간에서 안 잘렸는지는 여기서 확인할 수 있다.

    `store.bootstrap_project`로 직접 만든다 -- Pydantic 검증(`CreateProjectRequest`)을
    거치지 않는 경로(이미 만들어진 프로젝트, 마이그레이션 등)로도 긴 이름이
    들어올 수 있어서, 다듬기 자체가 그 경로와 무관하게 안전해야 한다.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    store = LocalProjectStore(tmp_path)
    long_name = "가을" * 150  # 300자, 감사에서 쓴 것과 같은 길이
    project = store.bootstrap_project(long_name)
    job = _make_final_render_job(store, project_id=project.project_id, tmp_path=tmp_path)

    response = client.get(f"/api/projects/{project.project_id}/final-renders/{job['job_id']}/content")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]

    # nginx 기본 proxy_buffer_size(4096바이트)보다 훨씬 작게 -- 다른 응답
    # 헤더들과 합쳐도 여유가 크게 남는다.
    assert len(disposition) < 1200, disposition

    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    # 퍼센트 인코딩을 *자른 뒤* 만들었다면(바이트/문자 수로 자름) 한 글자를
    # 나타내는 %XX 조각 중간이 끊겨 `unquote`가 대체 문자를 넣거나 예외를
    # 낸다. `errors="strict"`로 그 자리를 잡는다 -- 코드 포인트 경계에서만
    # 잘랐다면(원문을 자른 뒤 인코딩) 항상 온전한 문자열로 디코딩된다.
    decoded = unquote(encoded, errors="strict")
    assert decoded
    assert "가을" in decoded
    assert len(decoded) < len(long_name) + len(".mp4")


def test_final_render_content_disposition_strips_unsafe_project_name_characters(tmp_path: Path) -> None:
    """프로젝트 이름에 경로 구분자·따옴표·줄바꿈이 섞여 있어도 안전해야 한다.

    줄바꿈을 그대로 헤더 값에 넣으면 `Content-Disposition` 뒤에 다른 응답 헤더를
    끼워 넣는 HTTP 응답 분할이 가능해진다 -- job_id가 아니라 사용자가 지은
    프로젝트 이름을 헤더에 실으므로 반드시 걸러야 한다.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    unsafe_name = 'evil"name\r\nX-Injected: 1\\../also/bad'
    owner = client.post("/api/projects", json={"name": unsafe_name}).json()["project_id"]
    store = LocalProjectStore(tmp_path)
    job = _make_final_render_job(store, project_id=owner, tmp_path=tmp_path)

    response = client.get(f"/api/projects/{owner}/final-renders/{job['job_id']}/content")
    assert response.status_code == 200
    assert "x-injected" not in {key.lower() for key in response.headers.keys()}

    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    ascii_filename = re.search(r'filename="([^"]*)"', disposition)
    assert ascii_filename is not None, disposition
    assert not any(char in ascii_filename.group(1) for char in ("/", "\\", "\r", "\n"))
