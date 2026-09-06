"""프로젝트를 지워도 자료실 참조가 남는다 — 실측 2026-09-06.

프로젝트를 영구 삭제하면 폴더는 통째로 사라지는데, 자료실의 **참조 등록부**는
그대로다(그 등록부는 프로젝트 폴더가 아니라 자료실 DB에 있다).

그러면 **없는 프로젝트가 자산 정리를 영원히 막는다.** 실제로 그랬다: 시험용
껍데기 자산을 치우려는데 방금 지운 프로젝트 넷이 아직 그 자산을 쓴다고 나왔다.

지우는 것이 되돌릴 수 없으므로 삭제를 막는 쪽이 옳고(그 판단은 그대로 둔다),
**막는 근거가 유령이면 안 된다.**
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _library_asset(client: TestClient, tmp_path: Path, *, mark: int) -> str:
    """**시험마다 다른 바이트를 준다.** 자료실은 내용 해시로 같은 파일을 하나로
    묶으므로, 같은 바이트를 올리면 두 시험이 자산 하나를 나눠 쓰게 되고 앞
    시험이 지운 것을 뒤 시험이 다시 만난다(전에 같은 자리에서 겪었다).
    """
    photo = tmp_path / f"ingest-{mark}.jpg"
    photo.write_bytes(bytes([255, 216, 255]) + bytes([mark]) + bytes(64))
    with photo.open("rb") as handle:
        response = client.post(
            "/api/library/ingest",
            files={"files": ("ingest.jpg", handle, "image/jpeg")},
            data={"media_type": "image"},
        )
    assert response.status_code == 201, response.text
    items = response.json()["items"]
    assert items, response.text
    return str(items[0]["library_asset_id"])


def test_a_deleted_project_stops_blocking_its_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    asset_id = _library_asset(client, tmp_path, mark=1)
    project_id = client.post("/api/projects", json={"name": "지울 프로젝트"}).json()["project_id"]
    materialized = client.post(
        f"/api/library/assets/{asset_id}/materialize", json={"project_id": project_id}
    )
    assert materialized.status_code == 201, materialized.text

    blocked = client.post(f"/api/library/assets/{asset_id}/trash")
    assert blocked.status_code == 409, "쓰고 있는데 지워졌다"

    client.delete(f"/api/projects/{project_id}?confirm=true")

    freed = client.post(f"/api/library/assets/{asset_id}/trash")
    assert freed.status_code == 200, f"없는 프로젝트가 아직 막는다: {freed.text}"


def test_a_living_project_still_blocks(tmp_path: Path) -> None:
    """유령만 걷어낸다 -- 살아 있는 프로젝트가 쓰는 자산은 그대로 막힌다."""
    client = TestClient(create_app(projects_root=tmp_path))
    asset_id = _library_asset(client, tmp_path, mark=2)
    project_id = client.post("/api/projects", json={"name": "남을 프로젝트"}).json()["project_id"]
    client.post(f"/api/library/assets/{asset_id}/materialize", json={"project_id": project_id})

    assert client.post(f"/api/library/assets/{asset_id}/trash").status_code == 409
