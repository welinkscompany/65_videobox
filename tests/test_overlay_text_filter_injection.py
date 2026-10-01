"""설명 카드·오버레이 글줄이 ffmpeg 필터를 끼워 넣지 못한다 (2026-10-01 보안 점검 M2).

글줄은 유진이 채팅에서 바로 적용한다. 예전 이스케이프는 작은따옴표 안에서
`\'`를 썼는데, ffmpeg 그래프 파서는 거기서 따옴표가 닫힌 것으로 본다. 그 뒤의
`,`가 필터 구분자가 되어 `drawtext=...:textfile=<아무 파일>`을 끼워 넣을 수 있었고,
실측으로 임의 파일 내용이 영상에 그려졌다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.ffmpeg_final_renderer import export_overlay_text_filters

FONT = Path("assets/fonts/korean/DoHyeon-Regular.ttf").resolve()
PAYLOAD = "a',drawtext=fontfile=f.ttf:textfile=does-not-exist.txt:x="


def _filters(line: str) -> str:
    return ",".join(
        export_overlay_text_filters(
            [line],
            font_file=str(FONT),
            video_height=360,
            start_sec=0.0,
            end_sec=1.0,
            caption_band=None,
        )
    )


def test_one_line_is_exactly_one_drawtext_filter() -> None:
    graph = _filters(PAYLOAD)
    # 끼워 넣은 drawtext는 글자 그대로 남아야 한다 -- 이스케이프되지 않은 `,drawtext=`가
    # 그래프에 보이면 두 번째 필터가 생긴 것이다.
    assert ",drawtext=" not in graph.replace("\,drawtext=", "")
    assert "expansion=none" in graph


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 없음")
@pytest.mark.parametrize(
    "line",
    [
        PAYLOAD,
        "가격: 9,900원; [특가] 오늘만 '반값'",
        "백슬래시 \ 와 퍼센트 %{pts} 그대로",
    ],
)
def test_ffmpeg_accepts_the_line_as_plain_text(line: str, tmp_path: Path) -> None:
    graph = _filters(line)
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=1",
            "-vf", graph, "-frames:v", "1", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
