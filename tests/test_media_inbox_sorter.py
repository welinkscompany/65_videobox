"""한 폴더에 넣으면 내용을 보고 가른다 (owner 승인 2026-09-07).

`docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`가 계약이다.

**여기서 만드는 파일은 전부 ffmpeg가 만든 진짜 미디어다.** 합성 바이트로 시험을
쓰면 ffprobe에 닿지 않아 이 종류의 결함을 하나도 못 잡는다 -- 이 저장소는 png와
jpg의 차이만으로 결함 넷을 겪었다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.media_inbox_sorter import (
    SFX_MAX_SECONDS,
    SortedDrop,
    classify_drop,
)


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe가 없으면 실물로 잴 수 없다",
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=120)


@pytest.fixture(scope="module")
def real_media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("real-media")
    made: dict[str, Path] = {}

    made["video"] = root / "야외촬영.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-pix_fmt", "yuv420p", "-shortest", str(made["video"]))

    made["silent_video"] = root / "무음촬영.mov"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
            "-pix_fmt", "yuv420p", str(made["silent_video"]))

    made["png"] = root / "썸네일.png"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=640x360:rate=1:duration=1",
            "-frames:v", "1", str(made["png"]))

    made["jpg"] = root / "사진.jpg"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=640x360:rate=1:duration=1",
            "-frames:v", "1", str(made["jpg"]))

    # 효과음: 한 번 나고 끝나는 짧은 소리.
    made["sfx"] = root / "딸깍.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=1.2", str(made["sfx"]))

    # 음악: 배경으로 깔리는 긴 트랙.
    made["music"] = root / "브금.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=45", str(made["music"]))

    # 앨범 아트가 박힌 음악. ffprobe에 **video 스트림이 하나 보인다** --
    # 이걸 영상으로 읽으면 음악이 통째로 촬영본 라이브러리로 들어간다.
    made["music_with_cover"] = root / "표지있는브금.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=40",
            "-i", str(made["png"]), "-map", "0:a", "-map", "1:v",
            "-c:v", "mjpeg", "-disposition:v:0", "attached_pic",
            str(made["music_with_cover"]))

    # 확장자가 거짓말하는 파일. 내용은 진짜 영상인데 이름은 .mp3다.
    made["video_named_mp3"] = root / "이름만음악.mp3"
    shutil.copy2(made["video"], made["video_named_mp3"])

    made["document"] = root / "메모.txt"
    made["document"].write_text("자산이 아니다", encoding="utf-8")

    made["broken"] = root / "깨진영상.mp4"
    made["broken"].write_bytes(b"\x00\x01\x02" * 4096)

    return made


def test_real_video_is_broll(real_media: dict[str, Path]) -> None:
    assert classify_drop(real_media["video"]) == SortedDrop("broll", "video_stream")
    assert classify_drop(real_media["silent_video"]) == SortedDrop("broll", "video_stream")


def test_real_pictures_are_images(real_media: dict[str, Path]) -> None:
    # png는 ffprobe가 길이를 안 준다(`N/A`), jpg는 0.04초를 준다. 둘 다 그림이다.
    assert classify_drop(real_media["png"]).media_type == "image"
    assert classify_drop(real_media["jpg"]).media_type == "image"


def test_short_audio_is_sfx_and_long_audio_is_music(real_media: dict[str, Path]) -> None:
    assert classify_drop(real_media["sfx"]) == SortedDrop("sfx", "audio_short")
    assert classify_drop(real_media["music"]) == SortedDrop("music", "audio_long")


def test_album_art_does_not_turn_music_into_footage(real_media: dict[str, Path]) -> None:
    assert classify_drop(real_media["music_with_cover"]).media_type == "music"


def test_the_extension_is_not_trusted(real_media: dict[str, Path]) -> None:
    assert classify_drop(real_media["video_named_mp3"]).media_type == "broll"


def test_documents_and_broken_files_have_no_asset_value(real_media: dict[str, Path]) -> None:
    assert classify_drop(real_media["document"]).media_type is None
    assert classify_drop(real_media["broken"]).media_type is None


def test_the_sfx_boundary_leans_towards_music() -> None:
    # 결정 문서: "확신이 없으면 음악으로 둔다." 경계에 정확히 걸린 길이는
    # 효과음이고, 그보다 길면 전부 음악이다.
    assert SFX_MAX_SECONDS <= 5.0
