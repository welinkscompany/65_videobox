"""업로드 천장을 owner가 실제로 쓰는 경로로 잰다.

**없는 경로에 큰 몸통을 보내 재지 않는다.** 그렇게 재면 앱이 본문을 읽지 않고 바로
닫는 바람에 nginx가 502를 내고, 프록시는 멀쩡한데 실패로 보인다 — 2026-08-20에
실제로 그 헛경보가 났다. 같은 순간 진짜 업로드 경로로는 47MB가 3.6초에 201이었다.

틀린 경보를 내는 검증기는 아무도 안 돌리게 된다. 그래서 진짜 영상으로, 진짜
업로드 문에 대고 잰다.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BOUNDARY_PREFIX = "----videobox"


def make_clip(target: Path, *, seconds: int = 6) -> int:
    """1MB를 확실히 넘는 진짜 mp4. noise가 압축을 무겁게 만든다."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", f"gradients=s=1920x1080:c0=#0B3D5C:c1=#6FB3D2:speed=0.05:d={seconds},noise=alls=8:allf=t",
            "-t", str(seconds), "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "veryfast", "-crf", "36", "-an", str(target),
        ],
        check=True, capture_output=True, timeout=600,
    )
    return target.stat().st_size


def upload(url: str, clip: Path) -> int | str:
    """브라우저가 보내는 그대로 — 파일명은 원시 UTF-8 바이트."""
    boundary = BOUNDARY_PREFIX + uuid.uuid4().hex
    head = (
        "--" + boundary + "\r\n"
        'Content-Disposition: form-data; name="file"; filename="' + clip.name + '"\r\n'
        "Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8")
    tail = ("\r\n--" + boundary + "--\r\n").encode("utf-8")
    request = urllib.request.Request(url, data=head + clip.read_bytes() + tail, method="POST")
    request.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception as error:  # noqa: BLE001 - 무엇이 막았는지 그대로 남긴다
        return repr(error)


def measure(base: str, project_id: str) -> tuple[bool, str]:
    if shutil.which("ffmpeg") is None:
        return False, "ffmpeg가 없어 못 쟀다"
    work = Path(tempfile.mkdtemp())
    try:
        clip = work / "천장-확인.mp4"
        size = make_clip(clip)
        status = upload(f"{base}/api/projects/{project_id}/draft-readiness/broll/upload", clip)
        megabytes = size // (1024 * 1024)
        return status == 201, f"{megabytes}MB → {status}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
