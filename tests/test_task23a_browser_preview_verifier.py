from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_task23a_verifier_transcodes_hevc_and_preserves_source() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "verify_task23a_browser_preview.py"), "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["source_unchanged"] is True
    assert payload["input_video_codec"] in {"hevc", "h265"}
    assert payload["output_video_codec"] == "h264"
    assert payload["output_pixel_format"] == "yuv420p"
    assert payload["range_status"] == 206
    assert payload["external_provider_calls"] == 0
