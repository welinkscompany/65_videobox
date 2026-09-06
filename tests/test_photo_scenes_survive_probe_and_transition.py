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


def test_every_input_decides_photo_ness_the_same_way() -> None:
    """입력을 다는 자리마다 **같은 함수로** 사진인지 판단하는가.

    전환 입력 두 줄만 `False`로 박혀 있어서 사진 장면의 전환이 조용히 사라졌다.
    그 두 줄이 다시 굳어도 아무 시험이 안 깨졌다 -- 실제 전환 렌더를 세우려면
    ffmpeg를 태운 계획 하나를 통째로 만들어야 해서 아무도 안 세웠기 때문이다.

    **이 시험이 지키는 것은 결과가 아니라 모양이다.** 필터가 옳게 그려지는지는
    못 본다. 다만 "한 자리만 다르게 판단한다"는 이 저장소의 되풀이되는 실패
    하나는 확실히 잡는다.
    """
    import re

    from videobox_core_engine import ffmpeg_final_renderer

    source = Path(ffmpeg_final_renderer.__file__).read_text(encoding="utf-8")
    appends = re.findall(r"source_paths\.append\(\((.+?)\)\)", source)

    assert len(appends) >= 4, f"입력을 다는 자리를 못 찾았다: {appends}"
    for arguments in appends:
        flag = arguments.split(",")[1].strip()
        assert flag == "is_image" or flag.startswith("_looks_like_image("), (
            f"사진 여부를 다르게 판단하는 자리가 있다: {arguments}"
        )


def test_the_old_path_refuses_a_photo_scene_instead_of_hanging(tmp_path: Path) -> None:
    """옛 concat 경로는 사진을 **정지 그림으로** 낸다 -- 그마저도 jpg면 안 끝난다.

    실측 2026-09-06: `-stream_loop -1`만 걸고 `-loop 1`을 안 붙이면 jpg 입력이
    30초가 지나도 안 끝나고 48바이트짜리 깨진 파일이 남는다(png는 정상).

    이 경로는 전환·색감·손떨림·트랙 상태에 대해 **일부러 멈춘다** -- 그쪽 기능이
    조용히 사라진 mp4를 내는 것보다 낫기 때문이다. 그 목록에 사진만 빠져 있었다.
    지금은 제품에서 이 경로에 닿지 않지만, 이 목록은 "닿을 때를 대비한 것"이다.
    """
    import pytest as _pytest

    from videobox_core_engine.ffmpeg_final_renderer import FinalRenderError

    photo = tmp_path / "scene.jpg"
    photo.write_bytes(bytes([255, 216, 255]) + bytes(64))
    timeline = {
        "tracks": [
            {
                "track_type": "broll",
                "clips": [{"clip_id": "c1", "asset_uri": f"file://{photo.as_posix()}", "start_sec": 0.0, "end_sec": 3.0}],
            }
        ]
    }

    with _pytest.raises(FinalRenderError) as caught:
        FfmpegFinalRenderer(store=None).render_timeline_to_mp4(
            project_id="p1", timeline=timeline, output_path=tmp_path / "out.mp4"
        )

    assert "composition plan" in str(caught.value).lower(), caught.value
