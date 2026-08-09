"""Searching the music and effects library by what a scene needs.

Yujin and the screen both need one way to ask "what suits this?" and get
actual assets back, not a mood phrase. The ranking lives in the library
store; this is the route that reaches it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore


class _Embeddings:
    """Stands in for the local model: two axes, so a query can be aimed."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed(self, request):
        self.queries.extend(request.inputs)
        vectors = []
        for text in request.inputs:
            calm = 1.0 if ("차분" in text or "느림" in text) else 0.0
            busy = 1.0 if ("신나" in text or "빠름" in text) else 0.0
            vectors.append([calm, busy])

        class _Response:
            pass

        response = _Response()
        response.vectors = tuple(vectors)
        return response


def _library_with_two_tracks(tmp_path: Path) -> MediaLibraryStore:
    store = MediaLibraryStore(tmp_path / "library")
    install_path = tmp_path / "pack"
    (install_path / "assets").mkdir(parents=True, exist_ok=True)
    assets = []
    for asset_id, media_type, payload in (
        ("music-calm", "music", b"calm"),
        ("music-busy", "music", b"busy"),
        ("sfx-pop", "sfx", b"pop"),
    ):
        path = install_path / "assets" / f"{asset_id}.wav"
        path.write_bytes(payload)
        assets.append({
            "library_asset_id": f"pack:p:{asset_id}", "asset_id": asset_id,
            "media_type": media_type, "duration_seconds": 10.0,
            "sha256": hashlib.sha256(payload).hexdigest(), "path": str(path),
            "source": "https://example.test", "creator": "tester", "tags": [media_type],
            "license": {
                "official_url": "https://example.test/l",
                "evidence_timestamp": "2026-01-01T00:00:00+00:00",
                "evidence_sha256": "0" * 64,
            },
        })
    store.index_verified_pack(pack_id="p", version="1.0.0", install_path=install_path, assets=assets)
    store.activate_pack(pack_id="p", version="1.0.0", install_path=install_path)

    for asset_id, vector, pace in (
        ("music-calm", [1.0, 0.0], "느림"),
        ("music-busy", [0.0, 1.0], "빠름"),
        ("sfx-pop", [0.0, 1.0], "빠름"),
    ):
        store.save_audio_descriptor(
            library_asset_id=f"pack:p:{asset_id}",
            sha256=hashlib.sha256(asset_id.split("-")[1].encode()).hexdigest(),
            measurements={"duration_seconds": 10.0, "loudness_rms": 0.1, "brightness_hz": 1000.0, "onset_rate_per_second": 1.0},
            words={"세기": "보통", "밝기": "중간", "빠르기": pace},
            description=f"설명 {pace}",
            embedding=vector,
        )
    return store


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=_library_with_two_tracks(tmp_path),
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_analysis_embedding_provider = _Embeddings()
    app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}
    return TestClient(app)


def test_a_calm_request_ranks_the_calm_track_first(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/media-library/search", json={"query": "차분한 배경 음악", "media_type": "music"}
        )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert [match["asset_id"] for match in matches] == ["music-calm", "music-busy"]
    assert matches[0]["score"] > matches[1]["score"]
    # The owner sees what it is, not a slug and not a number they cannot read.
    assert matches[0]["words"]["빠르기"] == "느림"


def test_asking_for_effects_never_returns_music(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/media-library/search", json={"query": "신나는 소리", "media_type": "sfx"}
        )

    assert [match["asset_id"] for match in response.json()["matches"]] == ["sfx-pop"]


def test_search_says_so_plainly_when_the_local_model_is_away(tmp_path: Path) -> None:
    # No model means no query vector. Answering with an arbitrary list would
    # be worse than saying it cannot search right now.
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=_library_with_two_tracks(tmp_path),
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_analysis_embedding_provider = None

    with TestClient(app) as client:
        response = client.post(
            "/api/media-library/search", json={"query": "차분한 배경 음악", "media_type": "music"}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "library_search_unavailable"


def test_an_empty_query_is_rejected_rather_than_ranked(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/media-library/search", json={"query": "   ", "media_type": "music"}
        )

    assert response.status_code == 422


def _with_footage(tmp_path: Path):
    store = _library_with_two_tracks(tmp_path)
    store.save_footage_descriptor(
        content_sha256="a" * 64, filename="수영장.mp4", duration_seconds=29.0,
        width=1920, height=1080,
        tags={"layers": {"place": ["실내 수영장"]}},
        description="가로 영상. 아이가 물놀이하는 차분한 장면.",
        embedding=[1.0, 0.0],
    )
    store.save_footage_descriptor(
        content_sha256="b" * 64, filename="달리기.mp4", duration_seconds=12.0,
        width=1080, height=1920,
        tags={"layers": {"action": ["달리기"]}},
        description="세로 영상. 신나게 달리는 장면.",
        embedding=[0.0, 1.0],
    )
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=store,
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_analysis_embedding_provider = _Embeddings()
    app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}
    return TestClient(app)


def test_footage_can_be_found_before_it_is_ever_imported(tmp_path: Path) -> None:
    # 지금까지는 프로젝트로 가져와야만 분석돼서, 드롭 폴더에 있는 영상은
    # 유진에게 보이지 않았다.
    with _with_footage(tmp_path) as client:
        response = client.post(
            "/api/media-library/search", json={"query": "차분한 장면", "media_type": "broll"}
        )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert matches[0]["filename"] == "수영장.mp4"
    assert matches[0]["orientation"] == "가로"


def test_a_short_form_search_can_ask_for_vertical_only(tmp_path: Path) -> None:
    with _with_footage(tmp_path) as client:
        response = client.post(
            "/api/media-library/search",
            json={"query": "신나는 장면", "media_type": "broll", "orientation": "세로"},
        )

    assert [match["filename"] for match in response.json()["matches"]] == ["달리기.mp4"]


def test_orientation_is_only_meaningful_for_footage(tmp_path: Path) -> None:
    # 음악에 방향을 물어보는 것은 뜻이 없다. 조용히 무시하면 owner가 걸러진
    # 줄 알게 되므로 거절한다.
    with _with_footage(tmp_path) as client:
        response = client.post(
            "/api/media-library/search",
            json={"query": "차분한 음악", "media_type": "music", "orientation": "세로"},
        )

    assert response.status_code == 422
