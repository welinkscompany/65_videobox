"""e2e를 **진짜 백엔드**에 붙여 돌린다.

## 왜 이게 따로 있나

평소 e2e 48개는 손으로 쓴 `apps/web/e2e/support/fake-api-server.mjs`를 상대한다.
빠르고 결정적이라 그 자체로 좋지만, **진짜 FastAPI는 한 번도 불리지 않는다.**
2026-08-19에 그 사실이 기록됐고 "실제로 그렇게 돌려 보지는 않았다"고 남아 있었다.
2026-08-20에 처음으로 돌렸다.

## owner 컨테이너에 붙이지 않는 이유

e2e는 프로젝트를 만들고 고친다. 5173에 붙이면 owner의 실제 자료를 밟는다.
진짜 백엔드를 밟는 것이 목적이지 owner 자료를 밟는 것이 아니므로, 같은 코드의
API를 **빈 임시 폴더**로 따로 띄워 붙인다.

## 2026-08-20 첫 실행 결과 — 29 통과 / 19 실패

**실패를 곧바로 결함으로 세지 마라.** 대부분은 가짜 서버가 심어 두던 자료가
없어서다. 다만 그중 하나는 진짜였다:

빈 설치에서 `/projects`가 제품 화면이 아니라 `ProjectOnboarding`을 그린다
(`AppRouter.tsx`의 `if (projects.length === 0)`). 그 화면은 제품 껍데기 밖이고,
스타일이 없고, **창작자에게 파일 경로를 손으로 적으라고 한다.** product-shell
실패 10건이 전부 이 하나에서 나온다. 새 기계에서 VideoBox를 처음 켠 사람이
보는 첫 화면이 그것이다.

## 쓰는 법

```bash
.venv/Scripts/python.exe scripts/owner-path/run_e2e_against_real_backend.py
```
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_PORT = int(os.environ.get("VIDEOBOX_REAL_E2E_API_PORT", "8127"))


def _api_command(projects_root: Path) -> list[str]:
    source_roots = [
        REPO_ROOT / "services" / "api" / "src",
        REPO_ROOT / "packages" / "domain-models" / "src",
        REPO_ROOT / "packages" / "storage-abstractions" / "src",
        REPO_ROOT / "packages" / "provider-interfaces" / "src",
        REPO_ROOT / "packages" / "timeline-schema" / "src",
        REPO_ROOT / "packages" / "core-engine" / "src",
        REPO_ROOT / "packages" / "capcut-export" / "src",
    ]
    inline = (
        "import sys; sys.path[:0] = "
        + repr([str(path) for path in source_roots])
        + "; import uvicorn; from videobox_api.main import create_app; "
        + f"uvicorn.run(create_app(projects_root={str(projects_root / 'projects')!r}), "
        + f"host='127.0.0.1', port={API_PORT}, log_level='warning')"
    )
    return [sys.executable, "-c", inline]


def _wait_for_health(seconds: float = 60.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def main() -> int:
    projects_root = Path(tempfile.mkdtemp(prefix="videobox-e2e-real-"))
    print(f"빈 임시 데이터 폴더: {projects_root}", flush=True)
    api = subprocess.Popen(_api_command(projects_root))
    try:
        if not _wait_for_health():
            print("!! 진짜 API가 뜨지 않았습니다.")
            return 1
        print(f"진짜 API 준비됨 (127.0.0.1:{API_PORT}). e2e를 붙입니다.", flush=True)
        environment = {
            **os.environ,
            "PLAYWRIGHT_SKIP_FAKE_API": "1",
            "PLAYWRIGHT_FAKE_API_PORT": str(API_PORT),
        }
        return subprocess.call(
            ["npx", "playwright", "test", *sys.argv[1:]],
            cwd=REPO_ROOT / "apps" / "web",
            env=environment,
            shell=os.name == "nt",
        )
    finally:
        api.terminate()
        try:
            api.wait(timeout=15)
        except subprocess.TimeoutExpired:
            api.kill()


if __name__ == "__main__":
    raise SystemExit(main())
