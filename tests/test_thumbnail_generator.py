from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videobox_core_engine import thumbnail_generator


def test_thumbnail_ffmpeg_text_output_decodes_utf8_with_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = tmp_path / "한글-원본.mp4"
    output = tmp_path / "한글-썸네일.jpg"
    video.write_bytes(b"video")
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append(kwargs)
        output.write_bytes(b"thumbnail")
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr="잘못된 바이트 �"
        )

    monkeypatch.setattr(thumbnail_generator.subprocess, "run", fake_run)

    thumbnail_generator.generate_video_thumbnail(video, output)

    assert calls == [
        {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 30,
        }
    ]
