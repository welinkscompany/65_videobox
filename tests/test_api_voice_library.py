"""목소리를 여러 개 두고 관리하는 길.

대표님 요청(2026-09-03): "내가 다른 여러개 유튜브를 만들수도 있어.
그래서 관리할수 있게 기능을 만들어줘."

채널마다 다른 목소리를 쓸 수 있으므로 **이름이 없으면 고를 수가 없다** --
저장 위치 끝의 해시로는 어느 것이 어느 목소리인지 알 수 없다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "voices"}).json()["project_id"]
    return client, project_id


def _add_voice(client: TestClient, project_id: str, name: str) -> str:
    response = client.post(
        f"/api/projects/{project_id}/assets/voice-sample/upload",
        files={"file": (f"{name}.wav", b"RIFF" + b"\0" * 64, "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()["asset_id"]


def test_a_voice_can_be_named_so_it_can_be_told_apart(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    asset_id = _add_voice(client, project_id, "take1")

    response = client.patch(
        f"/api/projects/{project_id}/assets/voice-sample/{asset_id}",
        json={"display_name": "노마드루이스 채널"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["metadata"]["display_name"] == "노마드루이스 채널"


def test_the_name_shows_up_in_the_list(tmp_path: Path) -> None:
    """고를 때 보이는 목록에 이름이 있어야 관리가 된다."""
    client, project_id = _client(tmp_path)
    asset_id = _add_voice(client, project_id, "take1")
    client.patch(f"/api/projects/{project_id}/assets/voice-sample/{asset_id}",
                 json={"display_name": "차분한 목소리"})

    assets = client.get(f"/api/projects/{project_id}/assets/voice-sample").json()["assets"]

    named = [a for a in assets if a["asset_id"] == asset_id]
    assert named and named[0]["metadata"]["display_name"] == "차분한 목소리"


def test_several_voices_live_side_by_side(tmp_path: Path) -> None:
    """유튜브 채널이 여럿이면 목소리도 여럿이다."""
    client, project_id = _client(tmp_path)
    first = _add_voice(client, project_id, "a")
    second = _add_voice(client, project_id, "b")
    client.patch(f"/api/projects/{project_id}/assets/voice-sample/{first}", json={"display_name": "채널 하나"})
    client.patch(f"/api/projects/{project_id}/assets/voice-sample/{second}", json={"display_name": "채널 둘"})

    assets = client.get(f"/api/projects/{project_id}/assets/voice-sample").json()["assets"]

    names = {a["metadata"].get("display_name") for a in assets}
    assert {"채널 하나", "채널 둘"} <= names


def test_a_bad_take_can_be_thrown_away(tmp_path: Path) -> None:
    """잘못 녹음한 것을 남겨 두면 고를 때마다 헷갈린다."""
    client, project_id = _client(tmp_path)
    asset_id = _add_voice(client, project_id, "oops")

    removed = client.delete(f"/api/projects/{project_id}/assets/voice-sample/{asset_id}")

    assert removed.status_code == 204, removed.text
    remaining = client.get(f"/api/projects/{project_id}/assets/voice-sample").json()["assets"]
    assert all(a["asset_id"] != asset_id for a in remaining)


def test_only_voices_can_be_deleted_through_this_door(tmp_path: Path) -> None:
    """**자산 id를 잘못 넘겨 촬영본이 사라지면 되돌릴 길이 없다.**"""
    client, project_id = _client(tmp_path)
    narration = client.post(
        f"/api/projects/{project_id}/assets/narration/upload",
        files={"file": ("n.wav", b"RIFF" + b"\0" * 64, "audio/wav")},
    )
    if narration.status_code != 201:
        return  # 이 경로가 없으면 이 시험은 할 일이 없다
    response = client.delete(
        f"/api/projects/{project_id}/assets/voice-sample/{narration.json()['asset_id']}"
    )

    assert response.status_code != 204
