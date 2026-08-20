from __future__ import annotations

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore

BOUNDARY = "----videoboxKoreanName"


def _browser_style_upload(filename: str, payload: bytes, *, field: str = "file", mime: str = "video/mp4") -> bytes:
    """What a browser actually puts on the wire: the filename as raw UTF-8
    bytes inside `filename="..."`, and no `_charset_` field anywhere.
    """
    head = (
        f'--{BOUNDARY}\r\n'
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    return head + payload + f"\r\n--{BOUNDARY}--\r\n".encode("utf-8")


def test_a_korean_filename_survives_the_upload(tmp_path) -> None:
    """The stored name and the extension check read the same string, so they
    have to agree. A latin-1 mangle happens to leave `.wav` readable, which is
    what would make a regression here show up as a wrong name rather than a
    rejected upload -- quieter, and worse.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "한글 이름"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/draft-readiness/broll/upload",
        content=_browser_style_upload("새벽-바다.mp4", b"video"),
        headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert response.status_code == 201, response.text

    stored = [
        str((asset.get("metadata") or {}).get("title") or "")
        for asset in LocalProjectStore(tmp_path).list_assets(project_id=project_id)
    ]
    assert "새벽-바다" in stored, stored


def test_a_korean_narration_name_is_not_rejected_for_its_extension(tmp_path) -> None:
    """The suffix check reads the same mangled string. A latin-1 mangle keeps
    `.wav` readable so it survives today, but the check and the stored name
    must agree on one repaired filename rather than each mending it alone.
    """
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "한글 이름"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/draft-readiness/narration/upload",
        content=_browser_style_upload("내레이션-1화.wav", b"wav", mime="audio/wav"),
        headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert response.status_code == 201, response.text
