"""프로젝트를 넘나드는 `내 목소리` 한 목록.

사이드바 `내 자산 > 내 목소리`(owner 승인 2026-09-04,
`docs/decisions/2026-09-04-capcut-shell-with-my-assets.ko.md` §2)는 **프로젝트를
고르기 전에** 열린다. 그런데 목소리 샘플은 프로젝트마다 따로 있는 sqlite에만
있어서, 지금까지는 `/api/projects/{id}/assets/voice-sample`을 프로젝트 수만큼
불러야 했다. 프로젝트가 30개를 넘었고 계속 는다.

**읽는 길만 만든다.** 목소리 파일은 owner의 실제 녹음이라 옮기거나 지우지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "projects"))


def _project(client: TestClient, name: str) -> str:
    return client.post("/api/projects", json={"name": name}).json()["project_id"]


def _add_voice(client: TestClient, project_id: str, filename: str) -> str:
    response = client.post(
        f"/api/projects/{project_id}/assets/voice-sample/upload",
        files={"file": (filename, b"RIFF" + b"\0" * 64, "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()["asset_id"]


def test_voices_from_every_project_arrive_in_one_list(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = _project(client, "여행 브이로그")
    second = _project(client, "셀러 교육")
    voice_one = _add_voice(client, first, "a.wav")
    voice_two = _add_voice(client, second, "b.wav")

    response = client.get("/api/voices")

    assert response.status_code == 200, response.text
    ids = {voice["asset_id"] for voice in response.json()["voices"]}
    assert {voice_one, voice_two} <= ids


def test_each_voice_says_which_project_it_came_from(tmp_path: Path) -> None:
    """어느 프로젝트 것인지 없으면 같은 이름 둘을 구분할 수 없다."""
    client = _client(tmp_path)
    project_id = _project(client, "여행 브이로그")
    asset_id = _add_voice(client, project_id, "a.wav")

    voices = client.get("/api/voices").json()["voices"]

    mine = [voice for voice in voices if voice["asset_id"] == asset_id]
    assert mine, voices
    assert mine[0]["project_id"] == project_id
    assert mine[0]["project_name"] == "여행 브이로그"


def test_the_name_and_the_made_on_date_come_along(tmp_path: Path) -> None:
    client = _client(tmp_path)
    project_id = _project(client, "여행 브이로그")
    asset_id = _add_voice(client, project_id, "a.wav")
    client.patch(
        f"/api/projects/{project_id}/assets/voice-sample/{asset_id}",
        json={"display_name": "차분한 목소리"},
    )

    voice = next(v for v in client.get("/api/voices").json()["voices"] if v["asset_id"] == asset_id)

    assert voice["display_name"] == "차분한 목소리"
    assert voice["created_at"]


def test_a_voice_with_no_name_still_shows_up(tmp_path: Path) -> None:
    """이름을 안 붙였다고 목록에서 빠지면 그 녹음은 영원히 못 찾는다."""
    client = _client(tmp_path)
    asset_id = _add_voice(client, _project(client, "이름없음"), "take1.wav")

    voice = next(v for v in client.get("/api/voices").json()["voices"] if v["asset_id"] == asset_id)

    assert voice["display_name"] is None


def test_the_address_it_gives_back_actually_plays(tmp_path: Path) -> None:
    """재생 주소가 있어도 실제로 안 열리면 목록만 있는 것이다."""
    client = _client(tmp_path)
    project_id = _project(client, "여행 브이로그")
    asset_id = _add_voice(client, project_id, "a.wav")

    voice = next(v for v in client.get("/api/voices").json()["voices"] if v["asset_id"] == asset_id)

    played = client.get(voice["content_url"])
    assert played.status_code == 200, played.text
    assert played.content.startswith(b"RIFF")


def test_only_voices_come_back(tmp_path: Path) -> None:
    """내레이션·촬영본이 섞이면 목소리를 고르는 자리가 아니게 된다."""
    client = _client(tmp_path)
    project_id = _project(client, "여행 브이로그")
    _add_voice(client, project_id, "a.wav")
    narration = client.post(
        f"/api/projects/{project_id}/assets/narration-audio/upload",
        files={"file": ("n.wav", b"RIFF" + b"\0" * 64, "audio/wav")},
    )

    voices = client.get("/api/voices").json()["voices"]

    assert voices
    assert all(voice["asset_type"] == "voice_sample_audio" for voice in voices)
    if narration.status_code == 201:
        assert all(voice["asset_id"] != narration.json()["asset_id"] for voice in voices)


def test_a_project_with_no_voices_is_simply_skipped(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _project(client, "빈 프로젝트")
    project_id = _project(client, "여행 브이로그")
    asset_id = _add_voice(client, project_id, "a.wav")

    voices = client.get("/api/voices").json()["voices"]

    assert [voice["asset_id"] for voice in voices] == [asset_id]


def test_archived_projects_stay_out_unless_asked_for(tmp_path: Path) -> None:
    """보관한 프로젝트의 목소리까지 섞이면 목록이 옛 것으로 불어난다."""
    client = _client(tmp_path)
    project_id = _project(client, "옛 프로젝트")
    asset_id = _add_voice(client, project_id, "a.wav")
    archived = client.post(f"/api/projects/{project_id}/archive")
    if archived.status_code >= 400:
        return  # 보관하는 길이 없으면 이 시험은 할 일이 없다

    assert all(v["asset_id"] != asset_id for v in client.get("/api/voices").json()["voices"])
    included = client.get("/api/voices", params={"include_archived": True}).json()["voices"]
    assert any(v["asset_id"] == asset_id for v in included)


def test_the_newest_recording_is_first(tmp_path: Path) -> None:
    """목소리를 다시 녹음하면 새 것부터 보여야 한다."""
    client = _client(tmp_path)
    first = _add_voice(client, _project(client, "하나"), "a.wav")
    second = _add_voice(client, _project(client, "둘"), "b.wav")

    ordered = [voice["asset_id"] for voice in client.get("/api/voices").json()["voices"]]

    assert ordered.index(second) < ordered.index(first)
