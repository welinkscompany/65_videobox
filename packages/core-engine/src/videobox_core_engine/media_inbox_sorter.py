"""한 폴더에 들어온 파일이 무엇인지 **내용을 보고** 정한다.

owner 결정 2026-09-07 (`docs/decisions/2026-09-07-one-drop-folder-sorted-for-me.ko.md`):
owner는 영상·그림·음악·효과음을 폴더 하나에만 넣는다. 종류를 가르는 일은
VideoBox 몫이고, 틀리면 owner가 자료실에서 고친다.

이 모듈은 2026-08-10 결정("종류는 폴더로 나눈다")을 대체한다. 그 결정의 근거는
"내용을 보고 판단하면 틀릴 수 있다"였고 그건 지금도 맞다 -- 그래서 고치는 길
(`PATCH /api/library/assets/{id}/media-type`)이 이 기능의 조건이다.

**확장자를 믿지 않는다.** 휴대폰과 다운로드 폴더를 거친 파일은 이름이 내용과
자주 어긋난다. 이 저장소는 png/jpg 차이 하나로 결함 넷을 겪었다.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


_LOGGER = logging.getLogger(__name__)

FFPROBE_TIMEOUT_SECONDS = 60

#: 그림 파일에 붙는 코덱 이름. mp3의 앨범 아트도 이 중 하나(보통 `mjpeg`/`png`)로
#: video 스트림에 실려 오기 때문에, 이 이름들만 보고 "영상이다"라고 정하면 안 된다.
IMAGE_CODEC_NAMES = frozenset(
    {"png", "mjpeg", "bmp", "gif", "webp", "tiff", "targa", "ppm", "jpeg2000", "avif", "heif"}
)

#: 이보다 짧으면 효과음, 길면 음악. **경계에 걸린 값은 효과음이다.**
#:
#: 왜 5초인가:
#: - 효과음은 한 번 나고 끝나는 소리다 -- 딸깍·전환음·알림음. 실제로 재보면
#:   대부분 2초 안쪽이고, 긴 것도 몇 초를 넘지 않는다.
#: - 배경음악은 트랙이나 루프라 짧아도 30초 위다(스톡 음원의 최소 길이가 대개
#:   그쯤이다).
#: - 그래서 5~30초 구간은 실제로 거의 비어 있다. 경계를 그 빈 구간의 **아래쪽
#:   끝**에 둔다.
#:
#: 왜 빈 구간의 가운데가 아니라 아래쪽 끝인가: 결정 문서가 "확신이 없으면
#: 음악으로 둔다"고 못박았다. 경계를 낮게 잡을수록 애매한 길이(5~30초 -- 긴
#: 앰비언스, 짧은 루프)가 음악으로 간다. 효과음 목록이 더 좁게 쓰이므로 잘못
#: 섞였을 때 음악 쪽이 눈에 덜 거슬린다.
SFX_MAX_SECONDS = 5.0

#: 이보다 짧은 "영상"은 사진 한 장이다. `media_probe._STILL_MAX_SECONDS`와 같은
#: 값이고 같은 이유다 -- ffprobe는 사진에 길이 0이 아니라 한 프레임 길이(jpg는
#: 0.04초)를 준다. png는 아예 안 준다.
STILL_MAX_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class SortedDrop:
    """무엇으로 받을지와, 왜 그렇게 정했는지.

    `media_type`이 `None`이면 자산 가치가 없다고 본 것이다 -- **지우지 않고**
    `불필요` 폴더로 옮긴다(owner가 직접 보고 지운다).
    """

    media_type: str | None
    reason: str


def probe_streams(path: Path, *, ffprobe_binary: str = "ffprobe") -> dict[str, Any] | None:
    """ffprobe에게 이 파일 안에 무엇이 있는지 묻는다. 못 읽으면 `None`."""
    try:
        completed = subprocess.run(
            [
                ffprobe_binary, "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,codec_name,disposition",
                "-of", "json", str(path),
            ],
            # **인코딩을 못박는다.** 윈도우에서 `text=True`만 쓰면 cp949로
            # 읽는데, ffprobe는 한글 파일 이름이 들어간 오류 문구를 UTF-8로
            # 낸다 -- 읽기 스레드가 UnicodeDecodeError로 죽었다(실측).
            # owner 파일 이름은 대부분 한글이라 이건 예외가 아니라 기본이다.
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=FFPROBE_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "")
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _duration(payload: dict[str, Any]) -> float | None:
    raw = (payload.get("format") or {}).get("duration")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def classify_drop(
    path: Path,
    *,
    probe: Callable[[Path], dict[str, Any] | None] = probe_streams,
) -> SortedDrop:
    """이 파일을 무엇으로 받을지 정한다.

    갈래 순서에 이유가 있다:

    1. **진짜 video 스트림이 있으면 영상이다.** 그림 코덱이 아닌 video 스트림은
       움직이는 그림뿐이다.
    2. **audio 스트림이 있으면 소리다.** 앨범 아트가 박힌 mp3가 여기서 걸린다 --
       video 스트림이 하나 보이지만 그건 그림 코덱이라 1번을 통과하지 못한다.
       (1번보다 뒤에 두는 이유: 소리 있는 촬영본은 1번에서 이미 끝났다.)
    3. **그림 코덱만 남으면 사진이다.**
    4. 아무것도 못 읽으면 자산 가치가 없다고 본다.

    아는 한계: mjpeg로만 인코딩된 소리 없는 **영상**은 3번에서 사진이 된다.
    요즘 카메라·휴대폰은 이런 파일을 만들지 않고, 틀려도 owner가 자료실에서
    영상으로 고칠 수 있다.
    """
    payload = probe(path)
    if payload is None:
        return SortedDrop(None, "unreadable")
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        return SortedDrop(None, "no_streams")

    video_codecs: list[str] = []
    image_codecs: list[str] = []
    has_audio = False
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        codec_type = str(stream.get("codec_type") or "")
        codec_name = str(stream.get("codec_name") or "").lower()
        if codec_type == "audio":
            has_audio = True
        elif codec_type == "video":
            attached = bool((stream.get("disposition") or {}).get("attached_pic"))
            if attached or codec_name in IMAGE_CODEC_NAMES:
                image_codecs.append(codec_name)
            else:
                video_codecs.append(codec_name)

    duration = _duration(payload)

    if video_codecs:
        return SortedDrop("broll", "video_stream")
    if has_audio:
        if duration is None:
            # 길이를 못 읽었다. 결정 문서: 확신이 없으면 음악.
            return SortedDrop("music", "audio_unknown_length")
        if duration <= SFX_MAX_SECONDS:
            return SortedDrop("sfx", "audio_short")
        return SortedDrop("music", "audio_long")
    if image_codecs:
        if duration is None or duration <= STILL_MAX_SECONDS:
            return SortedDrop("image", "still_image")
        # 그림 코덱인데 길다 -- 움직이는 gif 같은 것. 소리는 없다.
        return SortedDrop("broll", "animated_image")
    return SortedDrop(None, "no_media_streams")


__all__ = [
    "IMAGE_CODEC_NAMES",
    "SFX_MAX_SECONDS",
    "STILL_MAX_SECONDS",
    "SortedDrop",
    "classify_drop",
    "probe_streams",
]
