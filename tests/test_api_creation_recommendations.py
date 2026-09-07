"""주제 하나로 BGM·이미지 스타일·목소리 세트를 미리 보는 길.

owner 요청(2026-08-28, 필수 지정): "주제 하나로 BGM+이미지스타일+AI보이스까지
세트로 자동 추천." 세 추천 모두 이미 있는 재료 위에서 고르는 것이다 -- BGM은
의미 기반 색인, 스타일은 낱말 매칭, 목소리는 이미 등록된 샘플이다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.media_library_store import MediaLibraryStore


class _Embeddings:
    """차분한 낱말이 있으면 그쪽 축, 없으면 반대 축을 켠다 -- 실제 모델 대역."""

    def embed(self, request):
        vectors = []
        for text in request.inputs:
            calm = 1.0 if ("차분" in text or "느림" in text or "잔잔" in text) else 0.0
            busy = 1.0 if ("신나" in text or "빠름" in text) else 0.0
            vectors.append([calm, busy])

        class _Response:
            pass

        response = _Response()
        response.vectors = tuple(vectors)
        return response


def _library_with_bgm(tmp_path: Path) -> MediaLibraryStore:
    store = MediaLibraryStore(tmp_path / "library")
    install_path = tmp_path / "pack"
    (install_path / "assets").mkdir(parents=True, exist_ok=True)
    payload = b"calm music bytes"
    path = install_path / "assets" / "calm-piano.wav"
    path.write_bytes(payload)
    store.index_verified_pack(
        pack_id="p", version="1.0.0", install_path=install_path,
        assets=[{
            "library_asset_id": "pack:p:calm-piano", "asset_id": "calm-piano",
            "media_type": "music", "duration_seconds": 90.0,
            "sha256": hashlib.sha256(payload).hexdigest(), "path": str(path),
            "source": "https://example.test", "creator": "tester", "tags": ["music"],
            "license": {
                "official_url": "https://example.test/l",
                "evidence_timestamp": "2026-01-01T00:00:00+00:00",
                "evidence_sha256": "0" * 64,
            },
        }],
    )
    store.activate_pack(pack_id="p", version="1.0.0", install_path=install_path)
    store.save_audio_descriptor(
        library_asset_id="pack:p:calm-piano",
        sha256=hashlib.sha256(b"calm-piano").hexdigest(),
        measurements={"duration_seconds": 90.0, "loudness_rms": 0.1, "brightness_hz": 800.0, "onset_rate_per_second": 0.5},
        words={"세기": "약함", "밝기": "낮음", "빠르기": "느림"},
        description="잔잔한 피아노 배경음악",
        embedding=[1.0, 0.0],
    )
    return store


def _client(tmp_path: Path, *, with_embeddings: bool = True) -> TestClient:
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=_library_with_bgm(tmp_path),
        media_analysis_poll_interval_seconds=3600,
    )
    if with_embeddings:
        app.state.media_analysis_embedding_provider = _Embeddings()
        app.state.media_analysis_profile = {"embedding_model_name": "test-embed"}
    else:
        app.state.media_analysis_embedding_provider = None
    return TestClient(app)


def test_recommends_bgm_style_and_says_no_voice_registered_yet(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "Recommendation Draft"}).json()["project_id"]
        response = client.post(
            f"/api/projects/{project_id}/creation-recommendations",
            json={"topic": "집에서 즐기는 차분한 브이로그", "script_text": "오늘은 차분하게 하루를 보내는 브이로그예요."},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["bgm_semantic"] is True
    assert [item["library_asset_id"] for item in body["bgm"]] == ["pack:p:calm-piano"]
    # "브이로그" 낱말이 있으니 실사 시네마틱 스타일을 골라야 한다.
    assert body["image_style"]["style_id"] == "cinematic_realistic"
    assert body["voice"]["asset_id"] is None
    assert "등록된 목소리가 아직 없어요" in body["voice"]["note"]


def test_style_still_matches_the_topic_word_when_the_written_script_never_repeats_it(tmp_path: Path) -> None:
    # 실제로 컨테이너에서 겪은 것(2026-08-28): 주제엔 "브이로그"가 있었는데
    # 유진이 쓴 대본 문장에는 그 낱말이 한 번도 안 나와 기본 스타일로 떨어졌다.
    # 스타일은 주제와 대본을 같이 봐야 한다.
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "Topic Word Draft"}).json()["project_id"]
        response = client.post(
            f"/api/projects/{project_id}/creation-recommendations",
            json={
                "topic": "집에서 즐기는 차분한 브이로그",
                "script_text": "아침 햇살이 창문 틈으로 슬쩍 들어옵니다. 오늘 하루는 조용히 시작해 볼게요.",
            },
        )

    assert response.status_code == 200
    assert response.json()["image_style"]["style_id"] == "cinematic_realistic"


def test_recommends_the_most_recently_registered_voice_sample(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id = client.post("/api/projects", json={"name": "Voice Draft"}).json()["project_id"]
        first_sample = tmp_path / "voice-a.wav"
        first_sample.write_bytes(b"voice a")
        second_sample = tmp_path / "voice-b.wav"
        second_sample.write_bytes(b"voice b")
        client.post(
            f"/api/projects/{project_id}/assets/voice-sample",
            json={"source_path": str(first_sample)},
        )
        second = client.post(
            f"/api/projects/{project_id}/assets/voice-sample",
            json={"source_path": str(second_sample)},
        ).json()

        response = client.post(
            f"/api/projects/{project_id}/creation-recommendations",
            json={"topic": "동화 같은 어린이 이야기"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["voice"]["asset_id"] == second["asset_id"]
    # "동화" 낱말이 있으니 동화 수채화풍을 골라야 한다.
    assert body["image_style"]["style_id"] == "fairytale_watercolor"


def test_says_so_plainly_when_the_local_embedding_model_is_away(tmp_path: Path) -> None:
    with _client(tmp_path, with_embeddings=False) as client:
        project_id = client.post("/api/projects", json={"name": "No Model Draft"}).json()["project_id"]
        response = client.post(
            f"/api/projects/{project_id}/creation-recommendations",
            json={"topic": "아무 주제"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["bgm"] == []
    assert body["bgm_semantic"] is False


def test_unknown_project_is_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/projects/does-not-exist/creation-recommendations",
            json={"topic": "아무 주제"},
        )

    assert response.status_code == 404
