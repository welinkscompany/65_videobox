from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore

FFMPEG = shutil.which("ffmpeg")


def _client(tmp_path: Path) -> TestClient:
    return create_app(projects_root=tmp_path / "projects", media_library_store=MediaLibraryStore(tmp_path / "library"))


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is needed to make a real clip")
def test_a_library_clip_is_analysed_once_it_joins_a_project(tmp_path: Path) -> None:
    """촬영본을 `재료 → 라이브러리`에서 프로젝트에 넣으면 유진의 추천이 영원히
    막혔다. 추천은 409 `director_analysis_blocked`을 돌려주고, 화면은 "자산
    화면에서 확인한 뒤 다시 눌러 주세요"라고 하는데 **그 화면에는 확인을 시작할
    단추가 없다.** 분석을 거는 `POST /api/projects/{id}/media-analysis`는 있지만
    부르는 화면이 하나도 없고, 뒤에서 도는 재분석 작업자는 한 번도 분석하지 않은
    자산을 일부러 건너뛴다. 막다른 길이었다.

    올려서 넣는 길(`assets.py`)과 수신함(`media_inbox.py`)은 넣는 순간 분석을
    건다. 라이브러리에서 넣는 길 둘만 안 걸었다 -- 같은 자리에 같은 자산이
    들어가는데 한쪽만 태그가 붙는다.
    """
    clip = tmp_path / "scene.mp4"
    assert FFMPEG is not None
    result = subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "color=c=teal:s=320x180:d=1", "-r", "10", str(clip)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    client = TestClient(_client(tmp_path))
    ingested = client.post(
        "/api/library/ingest",
        data={"media_type": "broll", "idempotency_key": "clip-1"},
        files=[("files", ("scene.mp4", clip.read_bytes(), "video/mp4"))],
    )
    assert ingested.status_code == 201, ingested.text
    library_asset_id = ingested.json()["items"][0]["library_asset_id"]

    project_id = client.post("/api/projects", json={"name": "추천 받아 보기"}).json()["project_id"]
    materialized = client.post(f"/api/library/assets/{library_asset_id}/materialize", json={"project_id": project_id})
    assert materialized.status_code == 201, materialized.text
    asset_id = materialized.json()["asset"]["asset_id"]

    queued = client.get(f"/api/projects/{project_id}/media-analysis").json()["items"]
    assert [item for item in queued if item["asset_id"] == asset_id], queued


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is needed to make a real clip")
def test_music_joining_a_project_is_not_sent_for_scene_analysis(tmp_path: Path) -> None:
    """장면 분석은 촬영본을 보는 일이다. 배경 음악 서른 개를 프로젝트에 넣었다고
    로컬 모델을 서른 번 돌리면, 고쳐 놓고 더 나쁜 것을 만든 셈이 된다.
    """
    client = TestClient(_client(tmp_path))
    ingested = client.post(
        "/api/library/ingest",
        data={"media_type": "music", "idempotency_key": "song-1"},
        files=[("files", ("song.mp3", b"fake audio bytes", "audio/mpeg"))],
    )
    assert ingested.status_code == 201, ingested.text
    library_asset_id = ingested.json()["items"][0]["library_asset_id"]

    project_id = client.post("/api/projects", json={"name": "음악만"}).json()["project_id"]
    materialized = client.post(f"/api/library/assets/{library_asset_id}/materialize", json={"project_id": project_id})
    assert materialized.status_code == 201, materialized.text

    assert client.get(f"/api/projects/{project_id}/media-analysis").json()["items"] == []
