"""팩을 갱신할 방법이 제품에 없었다 — owner 지시로 새 곡을 넣다가 드러났다.

2026-09-05, owner: "브이로그용 30곡 찾아서 넣어줘. 게임음악은 다 삭제해."

곡을 갈아 끼운 팩(`starter-v1@1.1.0`)을 만들어 검증까지 마쳤는데 **설치할 길이
없었다.** 설치기(`MediaPackService.install`)는 있지만 부르는 자리가 어디에도
없다 -- 화면에도, API에도, 스크립트에도. 최초 설치는 사람이 손으로 한 것이다.

손으로 넣으려 했더니 **SQLite가 readonly**로 막았다. API 서버가 그 파일을
열고 있기 때문이고, 9p 마운트에서는 더 잘 난다. **DB를 가진 프로세스가
설치해야 한다** -- 그래서 API에 그 자리를 만든다.

**임의 경로를 받지 않는다.** 팩 디렉터리는 데이터 폴더 안에서만 고른다.
경로를 그대로 받으면 컨테이너 어디든 읽어 들일 수 있는 문이 된다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _pack(root: Path, *, version: str = "9.9.9") -> Path:
    """작은 팩 하나. 실제 오디오가 필요하므로 기존 팩에서 한 자산만 빌려 온다."""
    source = Path("dist/starter-media-pack")
    if not (source / "manifest.json").exists():
        return Path()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    directory = root / "small-pack"
    (directory / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / asset["path"], directory / asset["path"])
    manifest["assets"] = [asset]
    manifest["version"] = version
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return directory


def test_install_refuses_a_directory_outside_the_data_folder(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))

    response = client.post("/api/media-library/install", json={"directory_name": "../../etc"})

    assert response.status_code == 422
    assert response.json()["detail"] == "pack_directory_invalid"


def test_install_says_so_when_the_named_pack_is_not_there(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))

    response = client.post("/api/media-library/install", json={"directory_name": "no-such-pack"})

    assert response.status_code == 404
    assert response.json()["detail"] == "pack_not_found"
