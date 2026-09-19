"""`run_memory_librarian.py`가 컨테이너에서 실제로 owner가 손으로 돌리는 진입점이다.

`_default_runtime()`이 `VIDEOBOX_LOCAL_RUNTIME_BASE_URL` 환경변수를 무시하고
dataclass 리터럴 기본값(`http://127.0.0.1:1234/v1`)을 그대로 쓰면, 컨테이너
안에서는 127.0.0.1이 컨테이너 자신이라 LM Studio(호스트)에 닿지 않는다 --
실측(2026-09-19)으로 `ConnectionRefusedError`가 났다. 다른 시험들은 전부
`runtime_factory`를 주입해 이 기본 경로를 건너뛰므로 지금까지 못 잡았다.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = str(REPOSITORY_ROOT / "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)

import run_memory_librarian as librarian_script  # noqa: E402


def test_default_runtime_base_url_follows_the_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_LOCAL_RUNTIME_BASE_URL", "http://host.docker.internal:1234/v1")
    runtime = librarian_script._default_runtime()
    assert runtime.local_runtime_config.base_url == "http://host.docker.internal:1234/v1"


def test_default_runtime_keeps_its_own_longer_timeout(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS", raising=False)
    runtime = librarian_script._default_runtime()
    # 밤사이 여러 대화 증류는 1턴 대화보다 오래 걸린다(스크립트 자체 docstring).
    # 환경변수 기본(60초)보다 더 긴 상한을 계속 들고 가야 한다.
    assert runtime.local_runtime_config.timeout_seconds >= 120
