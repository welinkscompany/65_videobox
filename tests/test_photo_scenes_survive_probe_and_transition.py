"""사진 장면을 막고 있던 두 자리 — 실측 2026-09-06.

owner가 사진 56장을 자료실에 넣었고 사진이 장면이 될 수 있게 됐다. 그 뒤
렌더러를 다시 읽어 보니 사진만 걸리는 자리가 둘 남아 있었다.

**1. png 장면은 렌더가 통째로 죽는다.** 길이를 재는 자리가 모든 장면에
`ffprobe`로 `format=duration`을 묻는데, png는 `N/A`를 준다(호스트 ffprobe
8.1.1, 컨테이너 7.1.5 둘 다 실측). 그러면 `float()`가 실패하고
`B-roll source has no readable duration`으로 멈춘다. jpg는 `0.040000`을 줘서
죽지는 않았다 -- **그래서 이 결함이 지금까지 안 보였다.**

사진에는 잴 길이가 없는 게 맞다. `-loop 1`이라 장면이 요구하는 만큼 늘어난다.

**2. 사진 장면에 전환을 걸면 그 전환 입력에 `-loop 1`이 안 붙는다.** 전환은
양쪽 원본을 입력으로 한 번 더 다는데, 그 두 줄이 이미지 여부를 `False`로
박아 두었다. 한 장짜리 스트림을 잘라 쓰게 되어 전환이 조용히 사라진다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe가 없으면 잴 수 없다")
def test_a_png_scene_does_not_kill_the_render(tmp_path: Path) -> None:
    photo = tmp_path / "scene.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
         "-frames:v", "1", str(photo)],
        check=True,
    )

    duration = FfmpegFinalRenderer(store=None)._probe_media_duration(photo)

    assert duration > 0, "png 사진에서 쓸 수 있는 길이가 안 나왔다"


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe가 없으면 잴 수 없다")
def test_a_photo_is_never_too_short_for_its_scene(tmp_path: Path) -> None:
    """사진은 장면이 아무리 길어도 모자라지 않는다 -- 늘리면 되기 때문이다.

    영상은 원본보다 긴 장면에 놓으면 `늘리기`나 `채우기`를 켜라고 막는다.
    사진에 그 막음이 걸리면 창작자가 못 넘어간다.
    """
    photo = tmp_path / "scene.jpg"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
         "-frames:v", "1", str(photo)],
        check=True,
    )

    duration = FfmpegFinalRenderer(store=None)._probe_media_duration(photo)

    assert duration >= 3600, f"사진 길이가 {duration}이라 긴 장면에서 막힌다"


def test_a_video_still_reports_its_real_length(tmp_path: Path) -> None:
    """사진을 고치면서 영상 길이 검사가 헐거워지면 안 된다."""
    video = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:duration=2:rate=10",
         str(video)],
        check=True,
    )

    duration = FfmpegFinalRenderer(store=None)._probe_media_duration(video)

    assert 1.5 < duration < 2.5, duration
