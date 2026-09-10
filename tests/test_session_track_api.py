"""자유 멀티트랙 Phase 5 -- 트랙 추가·삭제·순서를 화면이 부를 수 있는 문.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 5.

엔진 쪽(`session_tracks.py`)은 앞 조각에서 됐고, 여기는 그것을 **화면이 실제로
부를 수 있게** 잇는다. 이 저장소가 반복해 온 실패가 "부품은 있는데 부르는
자리가 없다"이므로, 엔진만 만들고 멈추지 않는다.

**아직 편집기 화면은 안 고친다.** 지금 타임라인은 트랙 줄이 다섯 개로 박혀
있어서 같은 종류 트랙 둘은 한 줄에 겹쳐 그려진다(사라지진 않는다). 화면은
Phase 7 몫이고, 그때까지 이 문은 API로만 열려 있다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore

from tests.test_editor_view_model_api import _manifest_fixture


def _tracks(store: LocalProjectStore, project_id: str, session_id: str) -> list[dict]:
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    return session.get("tracks") or []


def test_adding_a_broll_track_shows_up_in_the_session(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    added = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "broll", "label": "브롤 2"},
    )

    assert added.status_code == 200, added.text
    assert added.json()["session_revision"] == 2
    stored = _tracks(LocalProjectStore(tmp_path), project_id, session_id)
    broll = [track for track in stored if track["kind"] == "broll"]
    assert [track["label"] for track in broll] == ["broll", "브롤 2"]


def test_the_screen_can_read_the_track_list_back(tmp_path) -> None:
    """추가만 되고 읽을 길이 없으면 화면이 목록을 그릴 수 없다."""
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    listed = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks")

    assert listed.status_code == 200, listed.text
    # 트랙을 저장한 적 없는 세션도 옛 고정 다섯 역할로 답해야 한다.
    assert [track["kind"] for track in listed.json()["tracks"]] == [
        "narration", "broll", "bgm", "sfx", "overlay",
    ]


def test_narration_stays_shut_through_the_door_too(tmp_path) -> None:
    """엔진이 막아도 문이 열려 있으면 뜻이 없다 -- 여기서도 거절해야 한다."""
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)

    refused = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "narration", "label": "내레이션 2"},
    )

    assert refused.status_code == 422, refused.text


def test_removing_a_track_goes_through_and_the_last_one_is_refused(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "broll", "label": "브롤 2"},
    )

    removed = client.request(
        "DELETE",
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks/track-broll-2",
        json={"expected_revision": 2},
    )
    assert removed.status_code == 200, removed.text

    # 마지막 브롤 줄까지 지우면 놓을 자리가 사라진다 -- 문에서도 막는다.
    refused = client.request(
        "DELETE",
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks/track-broll",
        json={"expected_revision": 3},
    )
    assert refused.status_code == 422, refused.text


def test_reordering_through_the_door_changes_which_track_is_on_top(tmp_path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "broll", "label": "브롤 2"},
    )

    reordered = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks/order",
        json={"expected_revision": 2, "kind": "broll", "track_ids": ["track-broll-2", "track-broll"]},
    )

    assert reordered.status_code == 200, reordered.text
    listed = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks").json()
    broll = [track["track_id"] for track in listed["tracks"] if track["kind"] == "broll"]
    # 목록은 아래→위 순서다. 뒤집었으니 원래 아래였던 것이 위로 간다.
    assert broll == ["track-broll-2", "track-broll"]


def test_a_stale_revision_is_refused_so_two_screens_cannot_clobber_each_other(tmp_path) -> None:
    """같은 편집본을 두 창에서 열어 두면 한쪽이 다른 쪽 트랙을 조용히
    덮어쓸 수 있다 -- 다른 편집 문들과 같은 방식으로 막는다."""
    client = TestClient(create_app(projects_root=tmp_path))
    project_id, _, session_id = _manifest_fixture(client, tmp_path)
    client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "broll", "label": "브롤 2"},
    )

    stale = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/tracks",
        json={"expected_revision": 1, "kind": "broll", "label": "브롤 3"},
    )

    assert stale.status_code == 409, stale.text
