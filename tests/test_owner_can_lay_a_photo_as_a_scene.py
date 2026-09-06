"""owner가 손으로 사진을 장면 화면으로 깔지 못했다 — 전수 조사 2026-09-06.

> owner: "내가 혹시 영상말고 사진을 넣는것도 우리 자산으로 만들어서 영상으로
> 천천히 슬로우 모션같은 효과로 만들어도 되는거지?"

렌더러는 사진 장면을 이미 그린다(`-loop 1` + zoompan), 움직임도 고를 수 있고
(`photo_motion`), 유진에게 말하면 깔린다(`test_yujin_can_place_a_photo.py`).
**손으로 거는 길만 막혀 있었다** -- 손으로 화면을 거는 유일한 백엔드 경로가
`asset_type != broll_video`면 `asset_missing`으로 되돌린다.

사진도 장면이다. 유진이 쓰는 것과 **같은 `broll_override`**에 실리고, 렌더러가
확장자를 보고 사진으로 읽는다. 그래서 새 칸을 만들지 않고 이 문지기가 사진을
같이 받게 한다 -- 다만 **느슨하게 풀지는 않는다**: 음악·효과음은 그대로 막힌다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _create_timeline_session(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    narration = tmp_path / "narration.wav"
    script = tmp_path / "script.txt"
    narration.write_bytes(b"narration")
    script.write_text("One sentence.", encoding="utf-8")
    project_id = client.post("/api/projects", json={"name": "사진 장면"}).json()["project_id"]
    narration_asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio", json={"source_path": str(narration)},
    ).json()["asset_id"]
    script_asset_id = client.post(
        f"/api/projects/{project_id}/assets/script-document", json={"source_path": str(script)},
    ).json()["asset_id"]
    transcription_job_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription", json={"narration_asset_id": narration_asset_id},
    ).json()["job_id"]
    segment_job_id = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_job_id, "script_asset_id": script_asset_id},
    ).json()["job_id"]
    timeline_job_id = client.post(
        f"/api/projects/{project_id}/jobs/build-timeline",
        json={"segment_analysis_job_id": segment_job_id, "recommendation_job_ids": []},
    ).json()["job_id"]
    session_id = client.post(
        f"/api/projects/{project_id}/editing-sessions", json={"timeline_job_id": timeline_job_id},
    ).json()["session_id"]
    return project_id, session_id


def _register(store: LocalProjectStore, *, project_id: str, asset_type: AssetType, path: Path) -> str:
    return store.register_asset(
        project_id=project_id, asset_type=asset_type, source_path=path,
    ).asset_id


def test_a_project_photo_can_be_laid_as_the_scene(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    photo = tmp_path / "바다.jpg"
    photo.write_bytes(b"jpeg bytes")
    store = LocalProjectStore(tmp_path / "projects")
    asset_id = _register(store, project_id=project_id, asset_type=AssetType.IMAGE, path=photo)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": asset_id, "expected_revision": before["session_revision"]},
    )

    assert response.status_code == 200, response.text
    override = response.json()["segments"][0]["broll_override"]
    assert override["asset_id"] == asset_id
    # 신원(해시·판)은 영상과 똑같이 실려야 한다. 안 실리면 출력 검증이 그 장면을
    # "바뀐 원본"으로 읽는다.
    assert override["expected_content_sha256"]
    assert override["media_revision"]


def test_the_photo_scene_can_choose_its_movement(tmp_path: Path) -> None:
    """깐 다음에 움직임을 고를 수 있어야 owner 요청("천천히 슬로우 모션")이 닫힌다."""
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    photo = tmp_path / "노을.png"
    photo.write_bytes(b"png bytes")
    store = LocalProjectStore(tmp_path / "projects")
    asset_id = _register(store, project_id=project_id, asset_type=AssetType.IMAGE, path=photo)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={
            "asset_id": asset_id,
            "expected_revision": before["session_revision"],
            "media_controls": {"photo_motion": "zoom_in"},
        },
    )

    assert response.status_code == 200, response.text
    override = response.json()["segments"][0]["broll_override"]
    assert override["media_controls"]["photo_motion"] == "zoom_in"


def test_the_editor_sees_the_photo_as_that_scene_screen(tmp_path: Path) -> None:
    """화면이 읽는 곳까지 닿아야 완료다.

    편집기의 사진 움직임 칸은 **클립 원본의 확장자**로 붙는다
    (`inspectorRegistry.ts`의 `looksLikePhoto`). 깐 사진이 그 장면의 화면
    클립으로 안 나오면, 저장은 됐는데 움직임을 고를 자리가 없다.
    """
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    photo = tmp_path / "골목.jpg"
    photo.write_bytes(b"jpeg bytes")
    store = LocalProjectStore(tmp_path / "projects")
    asset_id = _register(store, project_id=project_id, asset_type=AssetType.IMAGE, path=photo)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": asset_id, "expected_revision": before["session_revision"]},
    )
    manifest = client.get(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/playback-manifest",
    ).json()

    broll_clips = [
        clip
        for track in manifest["tracks"] if track["track_type"] == "broll"
        for clip in track["clips"]
    ]
    assert any(str(clip.get("asset_uri") or "").lower().endswith(".jpg") for clip in broll_clips), broll_clips


def test_music_in_the_scene_slot_is_still_refused(tmp_path: Path) -> None:
    """느슨하게 풀지 않는다 -- 소리를 화면 자리에 걸면 여전히 막힌다."""
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id, session_id = _create_timeline_session(client, tmp_path)
    music = tmp_path / "노래.mp3"
    music.write_bytes(b"mp3 bytes")
    store = LocalProjectStore(tmp_path / "projects")
    asset_id = _register(store, project_id=project_id, asset_type=AssetType.BGM, path=music)
    before = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json()

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/seg_001/broll",
        json={"asset_id": asset_id, "expected_revision": before["session_revision"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "asset_missing"
    assert client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}").json() == before
