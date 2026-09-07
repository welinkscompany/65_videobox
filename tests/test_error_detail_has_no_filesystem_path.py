"""`_http_error`가 컨테이너 절대 경로·ffmpeg stderr를 응답에 그대로 실어 나가던 것.

`_http_error`는 모든 분기에서 `detail=str(exc)`였다. `FileNotFoundError`면
404 본문에 `/videobox-data/...`가 그대로 나갔다 -- 라우터 18개 약 130곳이
이 함수를 탄다. `docs/handoffs/2026-09-07-full-audit-docs-tests-boundaries.ko.md`
§1-3.

재현: 자산을 등록하고 밑 파일을 지운 뒤 `/content`를 부르면, 응답 `detail`에
지워진 파일의 절대 경로가 그대로 실렸다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.errors import _http_error
from videobox_api.main import create_app


def test_http_error_never_puts_a_filesystem_path_in_the_response() -> None:
    """`_http_error`를 직접 재는 단위 시험 -- 두 분기 다 고정 코드만 낸다."""

    missing = _http_error(FileNotFoundError("/videobox-data/projects/p1/assets/imported/secret.mp4"))
    assert missing.status_code == 404
    assert missing.detail == {"reason": "asset_file_missing", "error_code": "FileNotFoundError"}

    unclassified = _http_error(RuntimeError("ffmpeg failed: -i '/videobox-data/projects/p1/x.mp4': No such file"))
    assert unclassified.status_code == 500
    assert unclassified.detail == {"reason": "internal_error", "error_code": "RuntimeError"}


def test_a_deleted_asset_file_leaks_no_path_when_content_is_requested(tmp_path: Path) -> None:
    """실제 재현: 자산을 올리고 밑 파일을 지운 뒤 `/content`를 부른다."""

    projects_root = tmp_path / "projects"
    client = TestClient(create_app(projects_root=projects_root))
    project_id = client.post("/api/projects", json={"name": "경로 유출 재현"}).json()["project_id"]
    uploaded = client.post(
        f"/api/projects/{project_id}/assets/narration-audio/upload",
        files={"file": ("narration.wav", b"RIFF" + b"\0" * 64, "audio/wav")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["asset_id"]

    store = client.app.state.store
    asset = store.get_asset(project_id=project_id, asset_id=asset_id)
    resolved_path = store.resolve_storage_uri(project_id=project_id, storage_uri=asset["storage_uri"])
    resolved_path.unlink()

    response = client.get(f"/api/projects/{project_id}/assets/{asset_id}/content")

    assert response.status_code == 404
    detail = response.json()["detail"]
    rendered = str(detail)
    assert "/" not in rendered and "\\" not in rendered, rendered
    assert detail == {"reason": "asset_file_missing", "error_code": "FileNotFoundError"}
