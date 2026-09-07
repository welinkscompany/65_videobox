"""프로젝트 자산 등록 문이 아무 호스트 경로나 읽어 주던 결함 (코드리뷰 2026-09-07).

`POST /api/projects/{id}/assets/{...}`가 `source_path`로 받은 절대 경로를
봉쇄 검사 없이 프로젝트로 복사하고 `/content`로 도로 내려줬다. 다른 프로젝트
DB, 자료실 `media_library.sqlite`, 마운트된 설정을 전부 꺼낼 수 있었다 --
`docs/handoffs/2026-09-07-full-audit-docs-tests-boundaries.ko.md` §1-1.

여기서 재는 문 일곱: narration-audio, script-document, broll-video,
broll-video/batch, raw-video, sfx, voice-sample. 프로젝트 자신의 폴더는
계속 허용된다(업로드 문이 그 안에 잠깐 파일을 두고 이 경로를 그대로 탄다).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # 드롭 폴더도 시험이 쥔 자리로 옮긴다 -- 실제 컴퓨터의 드롭 폴더가
    # 허용 폴더가 되면 이 시험이 그 폴더 상태에 따라 흔들린다.
    monkeypatch.setenv("VIDEOBOX_MEDIA_INBOX_WATCH_PATH", str(tmp_path / "drop"))
    (tmp_path / "drop").mkdir(parents=True, exist_ok=True)
    return TestClient(create_app(projects_root=tmp_path / "projects"))


@pytest.fixture()
def project_id(client: TestClient) -> str:
    return client.post("/api/projects", json={"name": "봉쇄 시험"}).json()["project_id"]


@pytest.fixture()
def secret_file(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    secret = outside / "secret.txt"
    secret.write_text("TOP SECRET HOST FILE", encoding="utf-8")
    return secret


_SINGLE_PATH_DOORS = [
    "narration-audio",
    "script-document",
    "broll-video",
    "raw-video",
    "sfx",
    "voice-sample",
]


@pytest.mark.parametrize("door", _SINGLE_PATH_DOORS)
def test_register_asset_by_path_outside_allowed_roots_is_refused(
    client: TestClient, project_id: str, secret_file: Path, door: str
) -> None:
    response = client.post(
        f"/api/projects/{project_id}/assets/{door}",
        json={"source_path": str(secret_file)},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["reason"] == "source_path_not_visible"
    # 등록도 안 됐어야 한다 -- 어느 목록에도 그 파일이 나타나지 않는다.
    assert not list((client.app.state.store.project_root(project_id)).rglob("secret.txt"))


def test_register_broll_batch_by_path_outside_allowed_roots_is_refused(
    client: TestClient, project_id: str, secret_file: Path
) -> None:
    response = client.post(
        f"/api/projects/{project_id}/assets/broll-video/batch",
        json={"source_paths": [str(secret_file)]},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["reason"] == "source_path_not_visible"
    assert not list((client.app.state.store.project_root(project_id)).rglob("secret.txt"))


def test_register_broll_batch_by_directory_outside_allowed_roots_is_refused(
    client: TestClient, project_id: str, secret_file: Path
) -> None:
    response = client.post(
        f"/api/projects/{project_id}/assets/broll-video/batch",
        json={"source_directory": str(secret_file.parent)},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["reason"] == "source_path_not_visible"


def test_register_narration_audio_by_path_inside_project_root_still_works(
    client: TestClient, project_id: str
) -> None:
    """프로젝트 자신의 폴더는 계속 허용된다 -- 업로드 문이 그 안에 잠깐
    파일을 두고 같은 등록 경로를 탄다."""
    project_root = client.app.state.store.project_root(project_id)
    inside = project_root / "tmp" / "already-here.wav"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(b"RIFF....WAVEfmt ")
    response = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(inside)},
    )
    assert response.status_code == 201, response.text
