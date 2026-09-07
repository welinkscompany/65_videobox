"""틀리게 갈린 것을 owner가 자료실에서 고친다 (owner 승인 2026-09-07).

`docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`가 이걸 **조건**으로
달았다: "틀리면 owner가 자료실에서 고칠 수 있어야 한다. 그 길이 없으면 이 결정을
실행할 수 없다."

고칠 수 있는 범위는 **같은 갈래 안**이다 -- 음악↔효과음, 영상↔그림.
소리를 그림이라고 부르는 것은 고치기가 아니라 고장이다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore


def _client(tmp_path):
    return TestClient(
        create_app(
            projects_root=tmp_path / "projects",
            media_library_store=MediaLibraryStore(tmp_path / "library"),
        )
    )


def _ingest(client: TestClient, *, media_type: str, filename: str, body: bytes) -> str:
    response = client.post(
        "/api/library/ingest",
        data={"media_type": media_type, "idempotency_key": f"key-{filename}"},
        files=[("files", (filename, body, "application/octet-stream"))],
    )
    assert response.status_code == 201, response.text
    return response.json()["items"][0]["library_asset_id"]


def test_owner_can_move_a_track_from_music_to_sfx_and_back(tmp_path) -> None:
    client = _client(tmp_path)
    asset_id = _ingest(client, media_type="music", filename="딸깍.wav", body="짧은 소리".encode("utf-8"))

    corrected = client.patch(
        f"/api/library/assets/{asset_id}/media-type", json={"media_type": "sfx"}
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["asset"]["media_type"] == "sfx"

    # 자료실 목록에서도 옮겨 가 있어야 한다. DB만 바뀌고 목록이 그대로면
    # owner에게는 고쳐지지 않은 것이다.
    sfx = client.get("/api/library/assets", params={"media_type": "sfx"}).json()["assets"]
    music = client.get("/api/library/assets", params={"media_type": "music"}).json()["assets"]
    assert [item["library_asset_id"] for item in sfx] == [asset_id]
    assert asset_id not in [item["library_asset_id"] for item in music]

    # 되돌릴 수도 있어야 한다.
    back = client.patch(
        f"/api/library/assets/{asset_id}/media-type", json={"media_type": "music"}
    )
    assert back.status_code == 200
    assert back.json()["asset"]["media_type"] == "music"


def test_the_bytes_are_still_readable_after_the_correction(tmp_path) -> None:
    client = _client(tmp_path)
    asset_id = _ingest(client, media_type="sfx", filename="브금.wav", body="긴 소리".encode("utf-8"))

    client.patch(f"/api/library/assets/{asset_id}/media-type", json={"media_type": "music"})

    # 바이트가 사는 자리는 종류 이름을 담고 있다(`assets/<종류>/...`). 고치면서
    # 그 자리를 잃으면 미리 듣기가 조용히 404가 된다.
    assert client.get(f"/api/library/assets/{asset_id}/preview").status_code == 200


def test_owner_can_move_a_still_between_footage_and_pictures(tmp_path) -> None:
    client = _client(tmp_path)
    asset_id = _ingest(client, media_type="broll", filename="사진.png", body="그림 바이트".encode("utf-8"))

    corrected = client.patch(
        f"/api/library/assets/{asset_id}/media-type", json={"media_type": "image"}
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["asset"]["media_type"] == "image"


def test_sound_cannot_be_relabelled_as_a_picture(tmp_path) -> None:
    client = _client(tmp_path)
    asset_id = _ingest(client, media_type="music", filename="브금2.wav", body="소리 바이트".encode("utf-8"))

    refused = client.patch(
        f"/api/library/assets/{asset_id}/media-type", json={"media_type": "image"}
    )
    assert refused.status_code == 422
    assert refused.json()["detail"] == "media_type_group_mismatch"


def test_an_unknown_kind_is_refused(tmp_path) -> None:
    client = _client(tmp_path)
    asset_id = _ingest(client, media_type="music", filename="브금3.wav", body="소리".encode("utf-8"))

    refused = client.patch(
        f"/api/library/assets/{asset_id}/media-type", json={"media_type": "노래"}
    )
    assert refused.status_code == 422


def test_a_missing_asset_is_a_404(tmp_path) -> None:
    client = _client(tmp_path)
    assert (
        client.patch("/api/library/assets/user_nope/media-type", json={"media_type": "sfx"}).status_code
        == 404
    )
