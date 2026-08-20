"""사진·일러스트를 여러 프로젝트가 나눠 쓰는 자리.

프로젝트 **안**의 이미지는 이미 됐다 -- `AssetType.IMAGE`가 있고 오버레이도
그려진다. 없던 것은 **라이브러리**(프로젝트 공유) 쪽이다. 이 파일은 그 층이
전부 이어졌는지 본다: 종류·저장소·들여오기·미리보기·검색·프로젝트 복사.

특히 두 가지를 못박는다.
- 그림에 **오디오 파형을 만들지 않는다.** 파형 경로를 이미지에 태우면 화면은
  파형 칸을 보여 주는데 실제로는 아무것도 못 그린다.
- 그림에는 **의미 색인이 없다.** 되는 척하면 안 되므로 검색 응답의
  `semantic`은 로컬 모델이 살아 있어도 항상 거짓이어야 한다.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_domain_models.library_assets import LibraryMediaType
from videobox_storage.library_user_asset_store import (
    LibraryUserAssetStore,
    ensure_library_user_asset_schema,
)
from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore


FFMPEG = shutil.which("ffmpeg")


def _png(path: Path, *, size: str = "320x240", color: str = "orange") -> bytes:
    """실제 PNG 바이트. 썸네일이 진짜로 만들어지는지 봐야 하므로 가짜는 못 쓴다."""
    assert FFMPEG is not None
    result = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}",
         "-frames:v", "1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return path.read_bytes()


def _app(tmp_path: Path):
    return create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    )


class _Embeddings:
    """로컬 모델이 살아 있는 상황을 만든다. 그림은 그래도 의미검색이 없다."""

    def embed(self, request):
        class _Response:
            vectors = tuple([1.0, 0.0] for _ in request.inputs)

        return _Response()


def test_image_is_a_library_media_type() -> None:
    assert LibraryMediaType("image") is LibraryMediaType.IMAGE


def test_the_store_accepts_and_filters_images(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path / "state")
    store.register_asset(
        library_asset_id="user_image_1",
        media_type=LibraryMediaType.IMAGE,
        origin="user",
        content_sha256="a" * 64,
        managed_relative_path="assets/image/aa/aaa.png",
        byte_count=10,
        mime_type="image/png",
    )
    store.register_asset(
        library_asset_id="user_music_1",
        media_type=LibraryMediaType.MUSIC,
        origin="user",
        content_sha256="b" * 64,
        managed_relative_path="assets/music/bb/bbb.mp3",
        byte_count=10,
        mime_type="audio/mpeg",
    )
    images = store.list_assets(media_type="image")
    assert [asset.library_asset_id for asset in images] == ["user_image_1"]


def test_a_library_made_before_images_still_opens(tmp_path: Path) -> None:
    """옛 저장소는 `CHECK (media_type IN ('broll','music','sfx'))`로 굳어 있다.

    SQLite는 CHECK만 따로 못 고친다. 옮겨 심지 않으면 owner의 기존 라이브러리는
    그림을 영원히 못 받는다 -- 화면에는 탭이 보이는데 넣으면 실패한다.
    """
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    database = root / "media_library.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE library_user_assets (
            library_asset_id TEXT PRIMARY KEY,
            media_type TEXT NOT NULL CHECK (media_type IN ('broll', 'music', 'sfx')),
            origin TEXT NOT NULL CHECK (origin IN ('builtin', 'user')),
            lifecycle TEXT NOT NULL CHECK (lifecycle IN ('processing', 'ready', 'needs_attention', 'trashed')),
            content_sha256 TEXT NOT NULL UNIQUE,
            managed_relative_path TEXT NOT NULL,
            byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
            mime_type TEXT NOT NULL,
            technical_json TEXT NOT NULL DEFAULT '{}',
            machine_json TEXT NOT NULL DEFAULT '{}',
            user_json TEXT NOT NULL DEFAULT '{}',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            trashed_at TEXT
        );
        INSERT INTO library_user_assets VALUES (
            'user_old_music', 'music', 'user', 'ready', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
            'assets/music/cc/ccc.mp3', 10, 'audio/mpeg', '{}', '{}', '{}', '{}',
            '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00', NULL
        );
        """
    )
    connection.commit()
    ensure_library_user_asset_schema(connection)
    connection.commit()
    connection.close()

    store = LibraryUserAssetStore(root)
    store.register_asset(
        library_asset_id="user_image_new",
        media_type=LibraryMediaType.IMAGE,
        origin="user",
        content_sha256="d" * 64,
        managed_relative_path="assets/image/dd/ddd.png",
        byte_count=10,
        mime_type="image/png",
    )
    kept = {asset.library_asset_id for asset in store.list_assets()}
    assert kept == {"user_old_music", "user_image_new"}


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is required to make a real png")
def test_an_image_gets_a_thumbnail_and_never_a_waveform(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    payload = _png(tmp_path / "photo.png")
    created = client.post(
        "/api/library/ingest",
        data={"media_type": "image", "idempotency_key": "image-1"},
        files=[("files", ("photo.png", payload, "image/png"))],
    )
    assert created.status_code == 201, created.text
    item = created.json()["items"][0]
    assert item["state"] == "ready"
    asset_id = item["library_asset_id"]

    listed = client.get("/api/library/assets?media_type=image").json()["assets"]
    entry = next(value for value in listed if value["library_asset_id"] == asset_id)
    assert entry["media_type"] == "image"
    # 파형 칸을 내려보내면 화면이 그걸 믿고 자리를 만든다. 그림에는 없다.
    assert entry.get("waveform_url") is None

    preview = client.get(f"/api/library/assets/{asset_id}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/")

    thumbnail = client.get(f"/api/library/assets/{asset_id}/thumbnail")
    assert thumbnail.status_code == 200
    # 해시 막대 SVG는 ffmpeg가 못 그렸을 때의 대체물이다. 그림은 진짜로 그려진다.
    assert thumbnail.headers["content-type"] == "image/png"

    assert client.get(f"/api/library/assets/{asset_id}/waveform").status_code == 404


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is required to make a real png")
def test_image_search_matches_words_and_never_claims_meaning(tmp_path: Path) -> None:
    app = _app(tmp_path)
    app.state.media_analysis_embedding_provider = _Embeddings()
    app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}
    client = TestClient(app)
    client.post(
        "/api/library/ingest",
        data={"media_type": "image", "idempotency_key": "image-search"},
        files=[("files", ("바다풍경.png", _png(tmp_path / "sea.png"), "image/png"))],
    )

    response = client.get("/api/library/search?q=바다&media_type=image")
    assert response.status_code == 200
    body = response.json()
    assert [match["media_type"] for match in body["matches"]] == ["image"]
    # 그림에는 색인이 없다. 로컬 모델이 살아 있어도 `뜻으로 찾음`이라 하면 거짓말이다.
    assert body["semantic"] is False


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is required to make a real png")
def test_a_library_image_becomes_a_project_image_asset(tmp_path: Path) -> None:
    client = TestClient(_app(tmp_path))
    created = client.post(
        "/api/library/ingest",
        data={"media_type": "image", "idempotency_key": "image-materialize"},
        files=[("files", ("logo.png", _png(tmp_path / "logo.png"), "image/png"))],
    ).json()["items"][0]
    project_id = client.post("/api/projects", json={"name": "P"}).json()["project_id"]

    materialized = client.post(
        f"/api/library/assets/{created['library_asset_id']}/materialize",
        json={"project_id": project_id},
    )
    assert materialized.status_code == 201, materialized.text
    # 오버레이 경로가 읽는 종류다. 여기서 어긋나면 얹기 단추가 조용히 실패한다.
    assert materialized.json()["asset"]["asset_type"] == "image"


def test_an_owner_library_with_footage_triggers_can_still_widen_to_images(tmp_path: Path) -> None:
    """이관은 **실제 owner 라이브러리에서** 돌아야 한다.

    2026-08-20에 이관을 넣고 배포했더니 컨테이너에서 라이브러리에 **아무것도**
    추가할 수 없었다(그림뿐 아니라 영상·음악까지 500). 이관이 매번 실패하고
    롤백해서, 연결을 여는 모든 호출이 함께 죽었기 때문이다.

    원인은 한 파일을 두 저장소가 나눠 쓴다는 것이다. `media_library_store`가
    만든 촬영본 트리거 10개가 `library_user_assets`를 참조하는데, 이관이 그 표를
    `DROP` 한 뒤 새 표를 `RENAME` 하면 SQLite가 스키마를 다시 파싱하다가 참조가
    끊긴 트리거에서 멈춘다:

        error in trigger footage_sources_require_canonical_asset_insert:
        no such table: main.library_user_assets

    새로 만든 시험용 DB에는 그 트리거가 없어서 초록이었다. **제품에서는 두
    저장소가 같은 파일을 쓴다** -- 그 조건에서 재야 한다.
    """
    from videobox_storage.library_user_asset_store import LIBRARY_USER_ASSET_SCHEMA
    from videobox_storage.media_library_store import MediaLibraryStore

    root = tmp_path / "library"
    # 촬영본 트리거까지 만들어지는 진짜 라이브러리를 먼저 세운다. 읽기를 한 번
    # 시켜야 실제로 파일과 스키마가 생긴다.
    MediaLibraryStore(root).inspect_active_assets()
    database = root / "media_library.sqlite"
    old_schema = LIBRARY_USER_ASSET_SCHEMA.replace(
        "'broll', 'music', 'sfx', 'image'", "'broll', 'music', 'sfx'"
    )
    assert "'image'" not in old_schema.split("CREATE TABLE IF NOT EXISTS library_user_assets", 1)[1].split(")", 1)[0]
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE library_user_assets")
        connection.executescript(
            old_schema.split("CREATE TABLE IF NOT EXISTS library_ingest_batches", 1)[0]
        )
        connection.commit()
    finally:
        connection.close()

    # 그림을 받아들이게 넓히는 것이 이 호출의 일이다. 실패하면 라이브러리 전체가 멈춘다.
    store = MediaLibraryStore(root).user_asset_store
    store.create_ingest_batch(idempotency_key="after-migration")

    connection = sqlite3.connect(database)
    try:
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'library_user_assets'"
        ).fetchone()[0]
        triggers = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'"
            " AND sql LIKE '%library_user_assets%'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert "'image'" in definition, "그림을 받아들이도록 넓혀지지 않았다"
    # 트리거를 잃어버리는 것도 실패다. 촬영본이 정본 자산을 가리키게 지키는 장치다.
    assert triggers > 0, "이관이 촬영본 트리거를 데려갔다"
