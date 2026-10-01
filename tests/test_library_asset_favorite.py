"""자료실 즐겨찾기 (2026-10-01 점검).

자료실 왼쪽 `즐겨찾기` 분류는 `user_metadata.favorite`를 읽는데, 그 값을 쓰는 길이
없었다. 음악·효과음 줄의 ☆ 단추는 눌러도 아무 일도 하지 않았다(클릭 전파만 막음).
기존 `/api/media-library/.../favorite`는 기본 소재팩 저장소를 보므로 대표님 자산
(`user_...`)에는 `asset_missing`을 낸다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.library_assets import LibraryMediaType
from videobox_storage.media_library_store import MediaLibraryStore


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_library_store.user_asset_store.register_asset(
        library_asset_id="user_song_1",
        media_type=LibraryMediaType.MUSIC,
        origin="user",
        content_sha256="d" * 64,
        managed_relative_path="assets/music/dd/song.mp3",
        byte_count=10,
        mime_type="audio/mpeg",
        user_metadata={"filename": "bgm.mp3"},
    )
    return TestClient(app)


def test_the_owner_can_star_and_unstar_an_own_asset(tmp_path: Path) -> None:
    client = _client(tmp_path)

    starred = client.patch("/api/library/assets/user_song_1/favorite", json={"favorite": True})
    assert starred.status_code == 200, starred.text
    assert starred.json()["asset"]["user_metadata"]["favorite"] is True
    assert starred.json()["asset"]["user_metadata"]["filename"] == "bgm.mp3"

    listed = client.get("/api/library/assets/user_song_1").json()["asset"]
    assert listed["user_metadata"]["favorite"] is True

    unstarred = client.patch("/api/library/assets/user_song_1/favorite", json={"favorite": False})
    assert "favorite" not in unstarred.json()["asset"]["user_metadata"]


def test_an_unknown_asset_is_404(tmp_path: Path) -> None:
    response = _client(tmp_path).patch("/api/library/assets/user_nope/favorite", json={"favorite": True})
    assert response.status_code == 404
