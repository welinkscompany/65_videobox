"""이미 가져온 자료도 카드에 이름이 보인다 (2026-10-09).

가져올 때 이름을 싣기 전에 들어온 자료는 `metadata.title`이 없어 `자료 N`으로 보였다.
목록 응답에만 자료실 파일 이름(확장자 뗀 앞 60자)을 실어 준다 -- 저장 데이터는 안 건드린다.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from videobox_api.routers.assets import build_assets_router


class _FakeOrchestrator:
    def __init__(self, assets: list[dict]) -> None:
        self._assets = assets

    def list_broll_assets(self, project_id: str) -> list[dict]:
        return self._assets


def _asset(metadata: dict) -> dict:
    return {
        "asset_id": "a1",
        "project_id": "p1",
        "asset_type": "broll_video",
        "storage_uri": "x",
        "metadata": metadata,
        "created_at": "2026-10-09T00:00:00Z",
    }


def _client(assets: list[dict], lookup=None) -> TestClient:
    app = FastAPI()
    app.include_router(build_assets_router(_FakeOrchestrator(assets), None, library_filename_lookup=lookup))  # type: ignore[arg-type]
    return TestClient(app)


def _lookup(library_asset_id: str) -> str | None:
    return "월 수익 비교.png" if library_asset_id == "lib-1" else None


def test_old_imported_card_gets_the_library_file_name_in_the_response_only() -> None:
    assets = [_asset({"source_library_asset_id": "lib-1"})]
    body = _client(assets, _lookup).get("/api/projects/p1/assets/broll-video").json()
    assert body["assets"][0]["metadata"]["title"] == "월 수익 비교"
    assert "title" not in assets[0]["metadata"]


def test_an_existing_title_is_kept() -> None:
    body = _client([_asset({"source_library_asset_id": "lib-1", "title": "내 제목"})], _lookup).get(
        "/api/projects/p1/assets/broll-video"
    ).json()
    assert body["assets"][0]["metadata"]["title"] == "내 제목"


def test_unknown_library_asset_or_no_lookup_leaves_the_card_alone() -> None:
    meta = {"source_library_asset_id": "lib-x"}
    assert "title" not in _client([_asset(meta)], _lookup).get("/api/projects/p1/assets/broll-video").json()["assets"][0]["metadata"]
    meta2 = {"source_library_asset_id": "lib-1"}
    assert "title" not in _client([_asset(meta2)]).get("/api/projects/p1/assets/broll-video").json()["assets"][0]["metadata"]


def test_long_names_are_cut_to_sixty_characters() -> None:
    body = _client([_asset({"source_library_asset_id": "lib-1"})], lambda _i: ("가" * 80) + ".mp4").get(
        "/api/projects/p1/assets/broll-video"
    ).json()
    assert body["assets"][0]["metadata"]["title"] == "가" * 60


def test_main_lookup_reads_the_real_library_filename(tmp_path) -> None:
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        import pytest

        pytest.skip("ffmpeg is required to make a real png")
    from videobox_api.main import _library_filename_lookup, create_app
    from videobox_storage.media_library_store import MediaLibraryStore

    png = tmp_path / "x.png"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=64x64", "-frames:v", "1", str(png)], check=True, timeout=30)
    store = MediaLibraryStore(tmp_path / "library")
    client = TestClient(create_app(projects_root=tmp_path / "projects", media_library_store=store, media_analysis_poll_interval_seconds=3600))
    created = client.post(
        "/api/library/ingest",
        data={"media_type": "image", "idempotency_key": "lookup"},
        files=[("files", ("월 수익 비교.png", png.read_bytes(), "image/png"))],
    ).json()["items"][0]
    lookup = _library_filename_lookup(store)
    assert lookup(created["library_asset_id"]) == "월 수익 비교.png"
    assert lookup("nope") is None
