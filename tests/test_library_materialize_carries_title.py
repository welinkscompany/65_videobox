"""자료실 자산을 프로젝트로 가져오면 이름이 따라온다 (2026-10-08).

가져온 카드가 `자료 1`로만 보여서, 방금 만든 모션을 목록에서 못 찾았다. 프로젝트 카드는
`metadata.title`을 읽는다(`editorAssetProjection.projectBroll`). 자료실이 가진 파일 이름의
확장자 뗀 부분을 거기 실어 보낸다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore

FFMPEG = shutil.which("ffmpeg")


def _png(path: Path) -> bytes:
    assert FFMPEG is not None
    result = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=320x240", "-frames:v", "1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return path.read_bytes()


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is required to make a real png")
def test_a_materialized_library_asset_keeps_its_name_as_the_card_title(tmp_path: Path) -> None:
    client = TestClient(create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    ))
    created = client.post(
        "/api/library/ingest",
        data={"media_type": "image", "idempotency_key": "title-carry"},
        files=[("files", ("월 수익 비교.png", _png(tmp_path / "x.png"), "image/png"))],
    ).json()["items"][0]
    project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]
    materialized = client.post(f"/api/library/assets/{created['library_asset_id']}/materialize", json={"project_id": project_id})
    assert materialized.status_code == 201, materialized.text
    assert materialized.json()["asset"]["metadata"]["title"] == "월 수익 비교"
