"""본인 유튜브 영상 하나로 목소리 샘플과 편집 스타일 리포트를 함께 뽑는 길.

owner 요청(2026-08-29): "내 유튜브 영상 있는걸로 학습은 안돼?" 실제 네트워크로
유튜브에 안 닿는다 -- `yt_dlp.YoutubeDL`만 가짜로 바꾸고, 그 뒤(오디오 추출·
목소리 샘플 등록·컷 빠르기·색감 분석)는 전부 진짜 ffmpeg로 돈다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _build_reference_video(path: Path) -> None:
    # 색이 다른 두 장면 + 소리가 있는 영상 -- 목소리 샘플·컷 감지·색감 분석이
    # 전부 뭔가를 잴 수 있게.
    _generate([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=64x64:d=2:r=15",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-shortest", "-pix_fmt", "yuv420p", str(path),
    ])


class _FakeYoutubeDL:
    def __init__(self, options: dict) -> None:
        self.options = options

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> dict:
        destination = Path(self.options["outtmpl"].replace("%(id)s", "fake123").replace("%(ext)s", "mp4"))
        _build_reference_video(destination)
        return {"id": "fake123", "ext": "mp4"}

    def prepare_filename(self, info: dict) -> str:
        return self.options["outtmpl"].replace("%(id)s", info["id"]).replace("%(ext)s", info["ext"])


@pytest.fixture
def stub_youtube_download(monkeypatch: pytest.MonkeyPatch) -> None:
    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _FakeYoutubeDL)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_imports_a_voice_sample_and_a_style_report_from_one_video(
    tmp_path: Path, stub_youtube_download: None
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Reference Import"}).json()["project_id"]

    started = client.post(
        f"/api/projects/{project_id}/reference-style/from-youtube",
        json={"url": "https://youtu.be/dQw4w9WgXcQ"},
    )

    # 비동기로 바뀌었다(owner 결정 2026-08-29, 2회차) -- 요청 자체는 바로
    # 202로 돌아오고, 실제 결과는 job_id로 상태를 확인해서 받는다.
    # `TestClient`는 백그라운드 작업을 응답 준비 과정에서 같이 끝내므로
    # 바로 이어서 확인해도 이미 끝나 있다.
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    assert started.json()["status"] == "processing"

    response = client.get(f"/api/projects/{project_id}/reference-style/from-youtube/{job_id}")
    assert response.status_code == 200, response.text
    status_body = response.json()
    assert status_body["status"] == "succeeded", status_body
    body = status_body["result"]
    assert body["voice_sample_asset_id"]
    assert body["pacing"]["clip_count"] >= 1
    assert body["pacing"]["average_clip_duration_sec"] > 0
    assert body["color"]["sample_count"] >= 1
    # 순수 빨강 화면이라 따뜻한 쪽으로 나와야 한다.
    assert body["color"]["warm_cool_bias"] > 0

    stored = LocalProjectStore(tmp_path).get_asset(project_id=project_id, asset_id=body["voice_sample_asset_id"])
    assert stored["asset_type"] == AssetType.VOICE_SAMPLE_AUDIO.value

    voices = client.get(f"/api/projects/{project_id}/assets/voice-sample").json()["assets"]
    assert body["voice_sample_asset_id"] in [item["asset_id"] for item in voices]


def test_rejects_a_url_that_is_not_youtube_before_touching_anything(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Reference Import Reject"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/reference-style/from-youtube",
        json={"url": "https://vimeo.com/12345"},
    )

    # 잘못된 링크는 서버 고장(500)이 아니라 owner가 고칠 수 있는 입력(422)이다
    # (2026-08-29 QA에서 YoutubeImportError가 500으로 새던 것을 잡음).
    assert response.status_code == 422, response.text
    assert LocalProjectStore(tmp_path).list_assets(project_id=project_id) == []


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_does_not_leave_the_downloaded_video_behind(tmp_path: Path, stub_youtube_download: None) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "Cleanup Check"}).json()["project_id"]

    client.post(
        f"/api/projects/{project_id}/reference-style/from-youtube",
        json={"url": "https://youtu.be/dQw4w9WgXcQ"},
    )

    staging_dir = tmp_path / "projects" / project_id / "staging"
    leftovers = list(staging_dir.glob("youtube-import-*")) if staging_dir.is_dir() else []
    assert leftovers == []
