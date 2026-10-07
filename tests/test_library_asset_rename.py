"""자료실 이름 바꾸기 (2026-10-02, 점검 후속 A4).

2026-10-01 점검에서 자료실 이름 24개가 `³ìÀ½ 2026-...` 꼴로 깨져 있었다(cp949 바이트를
라틴1로 읽은 것). 고칠 길이 없었다. 이름은 `user_metadata.filename`에 있다.
파일과 관리 경로는 해시로 찾으므로 이름을 바꿔도 손대지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.library_assets import LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.media_library_store import MediaLibraryStore

BROKEN = "\xb3\xec\xc0\xbd 2026-02-07 163617.mp4"
FIXED = "녹음 2026-02-07 163617.mp4"


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_library_store.user_asset_store.register_asset(
        library_asset_id="user_clip_1",
        media_type=LibraryMediaType.BROLL,
        origin="user",
        content_sha256="c" * 64,
        managed_relative_path="assets/broll/cc/clip.mp4",
        byte_count=10,
        mime_type="video/mp4",
        user_metadata={"filename": BROKEN, "favorite": True, "tags": ["도시"]},
    )
    return TestClient(app)


def test_the_owner_can_rename_an_own_asset_and_the_other_notes_stay(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.patch("/api/library/assets/user_clip_1/filename", json={"filename": f"  {FIXED} "})

    assert response.status_code == 200, response.text
    metadata = response.json()["asset"]["user_metadata"]
    assert metadata == {"filename": FIXED, "favorite": True, "tags": ["도시"]}
    again = client.get("/api/library/assets/user_clip_1").json()["asset"]
    assert again["user_metadata"]["filename"] == FIXED
    assert again["managed_relative_path"] == "assets/broll/cc/clip.mp4"


def test_the_renamed_asset_is_found_by_its_new_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.patch("/api/library/assets/user_clip_1/filename", json={"filename": FIXED})

    found = client.get("/api/library/assets", params={"q": "녹음"}).json()["assets"]

    assert [asset["library_asset_id"] for asset in found if asset["origin"] == "user"] == ["user_clip_1"]


@pytest.mark.parametrize("bad", ["", "   ", "a/b.mp4", "a\\b.mp4", "줄\n바꿈.mp4", "탭\t.mp4", ".", "..", "x" * 256])
def test_a_name_that_is_not_a_plain_file_name_is_refused(tmp_path: Path, bad: str) -> None:
    client = _client(tmp_path)

    response = client.patch("/api/library/assets/user_clip_1/filename", json={"filename": bad})

    assert response.status_code == 422, response.text
    assert client.get("/api/library/assets/user_clip_1").json()["asset"]["user_metadata"]["filename"] == BROKEN


def test_unknown_fields_are_refused(tmp_path: Path) -> None:
    response = _client(tmp_path).patch(
        "/api/library/assets/user_clip_1/filename", json={"filename": FIXED, "managed_relative_path": "x"}
    )
    assert response.status_code == 422


def test_an_unknown_asset_is_404(tmp_path: Path) -> None:
    response = _client(tmp_path).patch("/api/library/assets/user_nope/filename", json={"filename": FIXED})
    assert response.status_code == 404


def test_a_builtin_row_is_never_renamed_in_the_store(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path)
    store.register_asset(
        library_asset_id="builtin_1",
        media_type=LibraryMediaType.MUSIC,
        origin="builtin",
        content_sha256="e" * 64,
        managed_relative_path="assets/music/ee/x.mp3",
        byte_count=1,
        mime_type="audio/mpeg",
        user_metadata={"filename": "x.mp3"},
    )
    with pytest.raises(ValueError, match="builtin_asset_immutable"):
        store.rename_asset("builtin_1", filename="y.mp3")
    assert store.get_asset("builtin_1").user_metadata["filename"] == "x.mp3"
