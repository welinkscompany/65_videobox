"""사진에서 그림을 한 장도 못 뽑았다 — 실측 2026-09-06.

owner 요청("사진 의미검색도 만들어줘")으로 사진을 촬영본 색인에 태웠는데, 그
색인은 `media_probe.probe()`가 준 프레임을 시각 모델에 보낸다. 실제 사진으로
재 보니 **프레임이 0개**였다(2048×1152 사진, 길이 0.04초).

원인: 프레임 뽑는 자리가 영상만 가정한다. 길이를 `MAX_FRAMES`로 나눠 그 시각마다
`-ss`로 찾아 들어가는데, 사진은 길이가 0.04초라 그 안을 찾다 빈손이 된다.

**사진은 그림이 한 장뿐이다.** 시각을 셀 것 없이 그대로 읽으면 된다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.media_probe import FFmpegMediaProbe


def _make_photo(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:duration=1",
         "-frames:v", "1", str(path)],
        check=True,
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg가 없으면 잴 수 없다")
def test_a_photo_yields_one_frame_for_the_vision_model(tmp_path: Path) -> None:
    photo = tmp_path / "still.jpg"
    _make_photo(photo)

    result = FFmpegMediaProbe().probe(photo)

    assert result.width == 640
    assert result.height == 360
    assert len(result.frames) >= 1, "사진에서 그림을 한 장도 못 뽑았다"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg가 없으면 잴 수 없다")
def test_a_video_still_gets_several_frames(tmp_path: Path) -> None:
    """사진을 고치면서 영상이 한 장으로 줄면 안 된다 -- 장면을 훑어야 한다."""
    video = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:duration=4:rate=15",
         str(video)],
        check=True,
    )

    result = FFmpegMediaProbe().probe(video)

    assert len(result.frames) >= 2, f"영상인데 {len(result.frames)}장뿐이다"
