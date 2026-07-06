from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_path in (
    REPO_ROOT / "services" / "api" / "src",
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "provider-interfaces" / "src",
    REPO_ROOT / "packages" / "timeline-schema" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
    REPO_ROOT / "packages" / "capcut-export" / "src",
):
    sys.path.insert(0, str(src_path))

import uvicorn

from videobox_api.main import create_app
from videobox_core_engine.settings import WhisperSTTConfig


def main() -> None:
    app = create_app(whisper_stt_config=WhisperSTTConfig(enabled=True))
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
