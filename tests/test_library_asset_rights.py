"""대표님 자산의 권리 칸 (AK W1215-4, 2026-09-28).

자료실의 대표님 자산(`library_user_assets`)에는 "누가 만들었고 써도 되는가"를
적을 칸이 없었다. `provenance_json`은 131개 중 몇 개만, 그것도 "어느 폴더에서
왔나" 정도만 담았다. 여러 수익 채널에 같은 B롤을 돌려 쓰려면 먼저 이 칸이 있어야
한다.

- 칸: `rights_source` = `unknown`(기본) / `own_footage`(직접 촬영) /
  `ai_generated`(AI 생성) / `third_party_licensed`(남의 것, 사용 허락 있음 -- 허락
  내용을 적어야 한다).
- **기본은 `unknown`이고, 모르는 채로는 수익용으로 내보내지 않는다.** 업로드 승인
  요청이 그 문이다(업로드할 채널이 곧 수익 채널이다).
- 있던 기록은 값을 지어내지 않고 전부 `unknown`으로 옮긴다.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.library_assets import (
    LibraryAssetRights,
    LibraryMediaType,
    LibraryUserAsset,
)
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.media_library_store import MediaLibraryStore


def _register(store: LibraryUserAssetStore, asset_id: str = "user_clip_1", sha: str = "c") -> LibraryUserAsset:
    return store.register_asset(
        library_asset_id=asset_id,
        media_type=LibraryMediaType.BROLL,
        origin="user",
        content_sha256=sha * 64,
        managed_relative_path=f"assets/broll/{sha * 2}/{sha * 3}.mp4",
        byte_count=10,
        mime_type="video/mp4",
    )


def test_a_new_owner_asset_starts_unknown_and_is_not_cleared_for_monetized_use(tmp_path: Path) -> None:
    asset = _register(LibraryUserAssetStore(tmp_path / "library"))

    assert asset.rights_source is LibraryAssetRights.UNKNOWN
    assert asset.cleared_for_monetized_use is False
    assert asset.to_dict()["rights_source"] == "unknown"


@pytest.mark.parametrize("source", ["own_footage", "ai_generated"])
def test_setting_a_known_source_clears_the_asset(tmp_path: Path, source: str) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    _register(store)

    updated = store.update_rights("user_clip_1", rights_source=source)

    assert updated.rights_source.value == source
    assert updated.cleared_for_monetized_use is True
    assert store.get_asset("user_clip_1").rights_source.value == source


def test_third_party_material_needs_the_licence_written_down(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    _register(store)

    with pytest.raises(ValueError, match="rights_license_note_required"):
        store.update_rights("user_clip_1", rights_source="third_party_licensed")
    updated = store.update_rights(
        "user_clip_1", rights_source="third_party_licensed", license_note="Pexels 라이선스, 2026-09-28 확인"
    )

    assert updated.cleared_for_monetized_use is True
    assert updated.rights_license_note == "Pexels 라이선스, 2026-09-28 확인"


def test_an_unknown_rights_value_is_refused(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "library")
    _register(store)

    with pytest.raises(ValueError, match="rights_source_invalid"):
        store.update_rights("user_clip_1", rights_source="probably_fine")


def _pre_rights_schema() -> str:
    from videobox_storage.library_user_asset_store import LIBRARY_USER_ASSET_SCHEMA

    old = re.sub(r",\s*rights_source TEXT[^\n]*\n\s*rights_license_note TEXT", "", LIBRARY_USER_ASSET_SCHEMA)
    assert "rights_" not in old
    return old


@pytest.mark.parametrize("also_pre_image", [False, True])
def test_an_existing_owner_library_migrates_to_unknown_without_inventing_values(
    tmp_path: Path, also_pre_image: bool
) -> None:
    """제품 모양 DB(촬영본 트리거가 함께 있는 파일)에서 잰다 -- §10.17.

    `also_pre_image`는 그림 칸이 생기기 전 라이브러리다. 그 경우 표를 통째로 다시
    만드는 이관이 먼저 돌므로, 새 칸이 그 다시 만들기에서도 살아남는지 본다.
    """
    root = tmp_path / "library"
    MediaLibraryStore(root).inspect_active_assets()
    database = root / "media_library.sqlite"
    old_schema = _pre_rights_schema()
    if also_pre_image:
        old_schema = old_schema.replace("'broll', 'music', 'sfx', 'image'", "'broll', 'music', 'sfx'")
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE library_user_assets")
        connection.executescript(old_schema.split("CREATE TABLE IF NOT EXISTS library_ingest_batches", 1)[0])
        connection.execute(
            "INSERT INTO library_user_assets (library_asset_id, media_type, origin, lifecycle, content_sha256,"
            " managed_relative_path, byte_count, mime_type, provenance_json, created_at, updated_at)"
            " VALUES ('user_old', 'broll', 'user', 'ready', ?, 'assets/broll/dd/ddd.mp4', 5, 'video/mp4',"
            " '{\"generated_by\": \"comfyui\"}', '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')",
            ("d" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    store = MediaLibraryStore(root).user_asset_store
    migrated = store.get_asset("user_old")

    assert migrated is not None
    assert migrated.rights_source is LibraryAssetRights.UNKNOWN, "a value was invented during migration"
    assert migrated.provenance == {"generated_by": "comfyui"}
    connection = sqlite3.connect(database)
    try:
        triggers = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' AND sql LIKE '%library_user_assets%'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert triggers > 0, "the migration took the footage triggers with it"
    # 옮긴 뒤에도 칸을 쓸 수 있어야 한다.
    assert store.update_rights("user_old", rights_source="own_footage").cleared_for_monetized_use is True


def _app(tmp_path: Path):
    return create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    )


def test_the_api_shows_the_rights_and_lets_the_owner_set_them(tmp_path: Path) -> None:
    app = _app(tmp_path)
    _register(app.state.media_library_store.user_asset_store)
    client = TestClient(app)

    shown = client.get("/api/library/assets/user_clip_1").json()["asset"]
    assert shown["rights_source"] == "unknown"
    assert shown["cleared_for_monetized_use"] is False

    refused = client.patch("/api/library/assets/user_clip_1/rights", json={"rights_source": "third_party_licensed"})
    assert refused.status_code == 422
    assert "rights_license_note_required" in refused.text

    updated = client.patch("/api/library/assets/user_clip_1/rights", json={"rights_source": "own_footage"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["asset"]["rights_source"] == "own_footage"
    assert updated.json()["asset"]["cleared_for_monetized_use"] is True
