from __future__ import annotations

import re
import subprocess
import tempfile
import os
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from math import ceil
from pathlib import Path
from typing import Any, NamedTuple

from videobox_core_engine.ass_subtitles import caption_band_px
from videobox_core_engine.canonical_track import canonical_track_type
from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.filters import filter_chain
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
from videobox_core_engine.output_warning_provenance import output_warning_notes
from videobox_core_engine.overlay_shapes import (
    BUNDLED_ICON_FONT_DIRECTORY,
    CONTAINER_ICON_FONT_DIRECTORY,
    ICON_FONT_FILE_NAME,
    ICON_FONT_GLYPH_SET,
    SHAPE_OVERLAY_DRAWN_SHAPES,
    canonical_shape_overlay_motion,
    overlay_icon_glyph,
    resolve_icon_font,
)
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.timeline_clip_source_resolution import (
    ResolvedClipSource,
    TimelineClipSourceError,
    resolve_broll_clip_source,
    resolve_generic_asset_uri,
    resolve_narration_clip_source,
)


class FinalRenderError(RuntimeError):
    pass



"""이 아래로는 들리지 않는 것으로 본다. 완전 무음은 -91dB로 측정된다."""
AUDIBLE_PEAK_DBFS = -60.0


def probe_audio_peak_dbfs(path: Path, *, ffmpeg_binary: str = "ffmpeg") -> float | None:
    """만들어진 파일에서 실제로 들리는 가장 큰 음량(dBFS). 재지 못하면 None.

    오디오 스트림이 20초로 멀쩡히 있어도 내용이 무음일 수 있다. 길이만 봐서는
    구분되지 않아 완전 무음(-91dB) 완성본이 그대로 나간 적이 있다. 영상은 건너뛰고
    오디오만 디코딩하므로 긴 영상에서도 몇 초면 끝난다.
    """
    try:
        result = subprocess.run(
            [
                ffmpeg_binary,
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    found = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", result.stderr or "")
    if found is None:
        return None
    try:
        return float(found.group(1))
    except ValueError:
        return None


def _atempo_chain(speed: float) -> str:
    """배속을 ffmpeg가 실제로 받는 `atempo` 단계로 나눈다.

    `atempo`는 한 번에 0.5~2.0배만 받는다. 4배를 그대로 주면 ffmpeg가 필터를
    거절해 **렌더가 통째로 실패한다.** 허용 범위(0.25~4)의 양 끝이 정확히 두
    단계이므로, 한계에 닿을 때까지 곱을 쪼개고 나머지를 마지막에 태운다.
    """
    steps: list[float] = []
    remaining = speed
    while remaining > 2.0:
        steps.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        steps.append(0.5)
        remaining /= 0.5
    steps.append(remaining)
    return ",".join(f"atempo={step}" for step in steps)


def _audio_cleanup_chain(controls: dict[str, Any]) -> str:
    """켜 둔 소리 정리 필터를 `,`로 시작하는 조각으로 만든다. 없으면 빈 문자열.

    **순서가 뜻을 바꾼다.** 잡음을 먼저 걷어내고 음량을 맞춰야 한다 -- 반대로
    하면 `loudnorm`이 잡음까지 포함한 크기를 기준으로 맞춰서, 잡음을 지운 뒤
    결과가 목표보다 조용해진다.

    `loudnorm`은 EBU R128 기준값(I=-16 LUFS)으로 맞춘다. 유튜브·팟캐스트가
    쓰는 값이라 다른 데 올려도 다시 안 맞춰도 된다.
    """
    chain = ""
    if controls.get("denoise"):
        chain += ",afftdn"
    if controls.get("normalize_loudness"):
        chain += ",loudnorm=I=-16:TP=-1.5:LRA=11"
    return chain


def rendered_audio_has_sound(path: Path, *, ffmpeg_binary: str = "ffmpeg") -> bool | None:
    """들을 만한 소리가 담겼는가. 재지 못했으면 None — 모르는 것과 없는 것은 다르다.

    렌더러 객체가 아니라 만들어진 '파일'에 대한 질문이므로 함수로 둔다. 렌더러
    인터페이스에 얹으면 대역 렌더러를 쓰는 호출부가 전부 깨진다.
    """
    peak = probe_audio_peak_dbfs(path, ffmpeg_binary=ffmpeg_binary)
    if peak is None:
        return None
    return peak > AUDIBLE_PEAK_DBFS


def export_overlay_text_lines(overlay: dict[str, Any]) -> list[str]:
    """오버레이가 화면에 그려야 할 글줄. 두 렌더 경로가 이 하나를 쓴다.

    예전에는 두 경로 모두 `text or title or body` 한 줄만 그려서, owner가
    저장한 표의 열·행과 설명 카드의 제목·본문이 어디에도 나오지 않았다 --
    화면과 백엔드는 보내고 저장하는데 렌더만 안 읽는 필드였다. 이미 보이던
    문구(`text`)는 계속 보인다: 구조를 그리면서 문구를 조용히 빼지 않는다.
    """
    overlay_type = str(overlay.get("overlay_type") or "").strip().lower()
    if overlay_type == "shape_overlay":
        # 도형·아이콘은 글줄이 아니다. `export_overlay_shape_filters`가 도형은
        # drawbox로, 아이콘은 글자 하나를 drawtext로 따로 그린다 -- 여기서 글줄을
        # 돌려주면 아래에 쌓이는 자막 자리로 밀려나고 검은 상자까지 딸려온다.
        return []
    text = str(overlay.get("text") or "").strip()
    title = str(overlay.get("title") or "").strip()
    body = str(overlay.get("body") or "").strip()
    lines: list[str] = []
    if overlay_type in {"table_card", "table_overlay"}:
        raw_columns = overlay.get("columns")
        columns = [str(item).strip() for item in raw_columns] if isinstance(raw_columns, list) else []
        if any(columns):
            lines.append(" | ".join(columns))
        raw_rows = overlay.get("rows")
        for row in raw_rows if isinstance(raw_rows, list) else []:
            if not isinstance(row, list):
                continue
            cells = [str(cell).strip() for cell in row]
            if any(cells):
                lines.append(" | ".join(cells))
        if text:
            lines.append(text)
    elif overlay_type == "explanation_card":
        lines = [item for item in (title, body, text) if item]
    else:
        fallback = text or title or body
        lines = [fallback] if fallback else []
    deduplicated: list[str] = []
    for line in lines:
        if line not in deduplicated:
            deduplicated.append(line)
    return deduplicated


# 여러 줄을 쌓을 때 줄 사이 간격(px). drawtext는 자기 줄의 text_h만 알므로
# 줄 높이는 fontsize 36 기준 고정 간격으로 잡는다.
_OVERLAY_LINE_PITCH_PX = 54
_OVERLAY_FONT_SIZE_PX = 36
_OVERLAY_BOX_BORDER_PX = 12
# fontsize 36에서 drawtext가 실제로 잡은 `text_h`는 32~36px이었다(실측, 한글).
# 자리를 정할 때만 쓰는 어림값이라 넉넉한 쪽으로 잡는다 -- 실제 그릴 때는 어림이
# 아니라 drawtext가 아는 `text_h`를 그대로 쓴다.
_OVERLAY_TEXT_HEIGHT_ESTIMATE_PX = 40
# 화면 가장자리에서 띄우는 거리. 비율로 두어야 세로 영상에서도 같은 여백이 된다.
# 0.05는 1080에서 54px이고, 결함 이전 자리(`h-(text_h*3)`)와 거의 같은 높이다 --
# 자막이 없을 때는 지금까지 보던 자리가 그대로 유지된다.
_OVERLAY_SAFE_MARGIN_RATIO = 0.05
# 자막 띠와 카드 사이에 남길 틈. 글자 높이 어림에 ±4px 오차가 있으므로 그보다
# 좁은 틈은 틈이라고 부를 수 없다. 1080에서 22px.
_OVERLAY_CAPTION_GAP_RATIO = 0.02

# 정지 도형 프리셋: (가로 비율, 세로 비율). 자유 좌표는 범위 밖이므로 화면
# 크기에 대한 비율만 있다 -- 미리보기 프록시와 완성본이 해상도가 달라도 같은
# 자리에 같은 비율로 그려진다.
_SHAPE_OVERLAY_SIZE_FRACTIONS = {
    "small": (0.28, 0.18),
    "medium": (0.42, 0.26),
    "large": (0.60, 0.36),
}
# 강조용 노랑. drawbox는 `#` 표기도 받지만 필터 문자열 안에서는 0x 표기가 안전하다.
_SHAPE_OVERLAY_RGB = "0xFFD400"
_SHAPE_OVERLAY_BASE_ALPHA = 0.9
_SHAPE_OVERLAY_COLOR = f"{_SHAPE_OVERLAY_RGB}@{_SHAPE_OVERLAY_BASE_ALPHA}"

# 등장·퇴장·이동에 쓰는 시간(초). 화면에서 고르는 값이 아니다 -- 길이를 정하는
# 입력칸을 주면 그게 곧 키프레임 편집기의 첫 칸이 되고, 승인 범위 밖이다.
_SHAPE_OVERLAY_MOTION_SEC = 0.4

# 도형(drawbox)의 움직임을 몇 조각으로 쪼갤 것인가. **왜 쪼개는지가 중요하다:**
# 2026-08-20에 컨테이너의 ffmpeg 7.1.5로 직접 재 보니 `drawbox`에는 시간을 담은
# 변수가 아예 없다.
#  - `color=0xFFD400@min(1,t)` → "Invalid alpha value specifier"로 즉시 실패.
#  - 식 안의 `t`는 시간이 아니라 **두께**다(`x='10+80*t'`가 t=fill일 때 상자를
#    화면 밖으로 밀어냈고, t=1일 때 x=90에 고정됐다 -- 시간이 흘러도 그대로).
#  - 프레임 번호 `n`은 "Undefined constant"다.
# 그래서 시간을 다룰 수 있는 유일한 손잡이인 `enable`로 짧은 조각을 쌓는다.
# 조각마다 알파와 x가 다르면 그것이 곧 움직임이다.
#
# 24조각을 고른 근거도 실측이다: 1280x720·3초·30fps에서 한 조각 0.50초, 24조각
# 0.51초로 사실상 같았다(`enable`이 거짓인 프레임에서는 필터가 통째로 건너뛴다).
# 0.4초를 24로 나누면 조각당 약 17ms -- 30fps에서 프레임보다 짧으므로 계단이
# 보이지 않는다.
_SHAPE_OVERLAY_MOTION_STEPS = 24


def transition_boundaries(items: Iterable[Any]) -> list[tuple[Any, Any]]:
    """전환이 실제로 걸리는 `(앞 장면, 들어오는 장면)` 쌍을 순서대로.

    **두 곳이 반드시 같은 답을 내야 한다** -- 필터 그래프를 만드는 쪽과
    ffmpeg 입력을 다는 쪽이 서로 다르게 세면 필터가 엉뚱한 입력을 가리킨다.
    그래서 세는 규칙을 여기 한 벌만 둔다.

    전환이 걸려 있어도 **앞 장면이 딱 붙어 있지 않으면 쌍이 아니다.** 사이가
    비어 있으면 넘겨줄 그림이 없다 -- 지어내지 않고 그냥 빼는 쪽이 맞다.
    """
    ordered = sorted(
        (item for item in items if item.track_type == "broll"),
        key=lambda item: (item.start_sec, item.clip_id),
    )
    pairs: list[tuple[Any, Any]] = []
    for item in ordered:
        if not item.transition:
            continue
        previous = next(
            (
                candidate for candidate in ordered
                if candidate is not item and abs(candidate.end_sec - item.start_sec) <= 1e-6
            ),
            None,
        )
        if previous is not None:
            pairs.append((previous, item))
    return pairs


def _seconds(value: float) -> str:
    """필터 문자열에 넣을 초. 부동소수 찌꺼기(`4.500000000000001`)를 잘라 낸다."""
    return str(round(float(value), 6))


def _escaped_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _overlay_block_bottom_px(
    *, line_count: int, video_height: int, caption_band: tuple[int, int] | None
) -> int:
    """글줄 뭉치의 **아래 변**을 어디에 둘 것인가 (px, 화면 위에서 잰 값).

    2026-08-20 완성본에서 설명 카드의 제목과 표의 한 줄이 자막에 가렸다. 원인은
    글줄을 화면 맨 아래에 고정으로 쌓았기 때문이고, 자막 기본 자리가 바로 거기다.

    **아래를 무조건 비워 두는 식으로 고치지 않는다.** 자막은 위로 올릴 수 있고
    (`position_y_percent`), 그때는 아래가 넓은 자리다. 그래서 자막이 실제로 먹는
    띠를 받아서 그 띠를 피해 **넓은 쪽**에 놓는다.
    """
    margin = max(8, round(video_height * _OVERLAY_SAFE_MARGIN_RATIO))
    default_bottom = video_height - margin
    if caption_band is None:
        return default_bottom
    gap = max(6, round(video_height * _OVERLAY_CAPTION_GAP_RATIO))
    band_top, band_bottom = caption_band
    block_height = (
        max(0, line_count - 1) * _OVERLAY_LINE_PITCH_PX
        + _OVERLAY_TEXT_HEIGHT_ESTIMATE_PX
        + 2 * _OVERLAY_BOX_BORDER_PX
    )
    if default_bottom - block_height >= band_bottom + gap:
        # 자막이 위쪽에 있다 -- 원래 자리(아래)가 그대로 넓다.
        return default_bottom
    above_bottom = band_top - gap
    room_above, room_below = above_bottom - margin, default_bottom - (band_bottom + gap)
    if room_above >= block_height or room_above >= room_below:
        return above_bottom
    return default_bottom


def export_overlay_text_filters(
    lines: list[str],
    *,
    font_file: str,
    video_height: int,
    start_sec: float,
    end_sec: float,
    caption_band: tuple[int, int] | None,
) -> list[str]:
    """오버레이 글줄이 그릴 drawtext 필터. **두 렌더 경로가 이 하나를 쓴다.**

    경로마다 따로 쓰면 같은 카드가 미리보기와 완성본에서 다른 자리에 그려진다 --
    이 저장소는 그 함정에 이미 두 번 걸렸다.

    쌓는 순서는 그대로다: 마지막 줄이 뭉치의 아래 변에 오고 앞 줄일수록 위로
    올라간다. 읽는 순서는 위에서 아래다.
    """
    font = _escaped_filter_path(font_file)
    block_bottom = _overlay_block_bottom_px(
        line_count=len(lines), video_height=video_height, caption_band=caption_band
    )
    # drawtext의 `y`는 글자 **위**를 가리키고 상자는 거기서 `boxborderw`만큼 더
    # 번진다. 아래 변을 맞추려면 그 둘을 빼야 한다. `text_h`는 글꼴마다 다르므로
    # 어림하지 않고 drawtext가 아는 값을 그대로 식에 남긴다.
    bottom_offset = video_height - block_bottom + _OVERLAY_BOX_BORDER_PX
    filters: list[str] = []
    for line_index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        rise_px = (len(lines) - 1 - line_index) * _OVERLAY_LINE_PITCH_PX
        y_expression = f"h-{bottom_offset}-text_h" + (f"-{rise_px}" if rise_px else "")
        filters.append(
            f"drawtext=fontfile='{font}':text='{escaped}':x=(w-text_w)/2:y={y_expression}:"
            f"fontsize={_OVERLAY_FONT_SIZE_PX}:fontcolor=white:box=1:boxcolor=black@0.65:"
            f"boxborderw={_OVERLAY_BOX_BORDER_PX}:enable='between(t,{start_sec},{end_sec})'"
        )
    return filters


def caption_segments_from_timeline(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    """타임라인의 자막 클립을 `caption_band_px`가 읽는 모양으로 옮긴다.

    조각 이어붙이기 경로에는 canonical plan이 없어서 자막을 여기서 모은다.
    돌려주는 모양은 `render_editing_session_ass`가 받는 `segments`와 같다.
    """
    segments: list[dict[str, Any]] = []
    for track in timeline.get("tracks", []):
        if not isinstance(track, dict) or canonical_track_type(track.get("track_type")) != "caption":
            continue
        for clip in track.get("clips", []) if isinstance(track.get("clips"), list) else []:
            if not isinstance(clip, dict):
                continue
            segments.append({
                "caption_text": clip.get("caption_text"),
                "caption_style": clip.get("caption_style"),
                "start_sec": clip.get("start_sec"),
                "end_sec": clip.get("end_sec"),
            })
    return segments


def _motion_number(value: float) -> str:
    """필터 식에 넣을 숫자. 꼬리 0을 떼어 필터 문자열이 읽히게 둔다."""
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _shape_motion_sec(motion: str, *, start_sec: float, end_sec: float) -> float:
    """이 표시가 등장·퇴장에 쓸 수 있는 시간.

    장면보다 긴 움직임을 걸면 표시가 **끝까지 흐린 채로** 장면이 끝난다. 짧은
    장면에서는 장면 길이에 맞춰 줄인다 -- 나타났다 사라지는 것은 둘로 나눠 써야
    하므로 더 짧게 잡는다.
    """
    span = end_sec - start_sec
    if motion == "none" or span <= 0:
        return 0.0
    share = span / 3 if motion == "fade_in_out" else span / 2
    return min(_SHAPE_OVERLAY_MOTION_SEC, share)


def _shape_motion_slices(
    motion: str, *, start_sec: float, end_sec: float
) -> list[tuple[str, float, float]]:
    """`drawbox`로 움직임을 내기 위한 시간 조각들.

    돌려주는 것은 `(구간 조건식, 알파 배수, 가로 오프셋 비율)`이다. `그대로`면
    조각이 하나뿐이고, 그 하나는 이 기능이 생기기 전과 **한 글자도 같아야 한다** --
    승인 기록 5항이 "기존에 만들어 둔 오버레이의 결과가 바뀌면 안 된다"고 못박았다.
    """
    if motion == "none":
        return [(f"between(t,{start_sec},{end_sec})", 1.0, 0.0)]

    window = _shape_motion_sec(motion, start_sec=start_sec, end_sec=end_sec)
    steps = _SHAPE_OVERLAY_MOTION_STEPS
    spans: list[tuple[float, float, float, float]] = []

    entering = motion in {"fade_in", "fade_in_out", "slide_in_left", "slide_in_right"}
    if entering:
        direction = -1.0 if motion == "slide_in_left" else 1.0
        sliding = motion in {"slide_in_left", "slide_in_right"}
        for index in range(steps):
            progress = (index + 1) / steps
            spans.append((
                start_sec + window * index / steps,
                start_sec + window * (index + 1) / steps,
                1.0 if sliding else progress,
                direction * (1.0 - progress) if sliding else 0.0,
            ))
    body_start = start_sec + window if entering else start_sec
    body_end = end_sec - window if motion in {"fade_out", "fade_in_out"} else end_sec
    if body_end > body_start:
        spans.append((body_start, body_end, 1.0, 0.0))
    if motion in {"fade_out", "fade_in_out"}:
        for index in range(steps):
            # 마지막 조각의 알파가 0이 되면 아무것도 안 그리는 필터가 하나 남는다.
            # 1에서 시작해 한 칸씩 내려오면 끝은 1/steps -- 거기서 장면이 끝난다.
            spans.append((
                body_end + window * index / steps,
                body_end + window * (index + 1) / steps,
                1.0 - index / steps,
                0.0,
            ))

    slices: list[tuple[str, float, float]] = []
    for position, (slice_start, slice_end, alpha, offset) in enumerate(spans):
        # 조각 경계에서 `between`을 쓰면 두 조각이 **같은 프레임에 겹쳐** 그려져
        # 그 한 프레임만 진해진다(실측: 21.39 → 31.11 → 21.39). 반열림 구간이면
        # 값이 평평하다. 마지막 조각만 끝을 닫아 장면 끝까지 그린다.
        last = position == len(spans) - 1
        closing = "lte" if last else "lt"
        slices.append((
            f"gte(t,{_motion_number(slice_start)})*{closing}(t,{_motion_number(slice_end)})",
            alpha,
            offset,
        ))
    return slices


def _shape_overlay_color(alpha_scale: float) -> str:
    if alpha_scale >= 1.0:
        return _SHAPE_OVERLAY_COLOR
    return f"{_SHAPE_OVERLAY_RGB}@{round(_SHAPE_OVERLAY_BASE_ALPHA * alpha_scale, 3)}"


def _icon_motion_expressions(
    motion: str, *, start_sec: float, end_sec: float, base_x: str
) -> tuple[str | None, str]:
    """아이콘(`drawtext`)의 `(알파 식, 가로 자리 식)`.

    도형과 달리 `drawtext`는 `alpha`·`x`에 **진짜 시간 식**을 받는다(실측으로
    확인했다). 그래서 조각을 쌓지 않고 식 하나로 매끄럽게 간다 -- 필터도 하나다.
    두 방식이 다른 이유는 ffmpeg 쪽 사정이지 화면에서 고른 것의 차이가 아니다.

    밀려 들어오는 거리는 **화면 가장자리까지 딱 그만큼**이다. 화면 너비를 통째로
    쓰면 절반 넘게 화면 밖에 있다가 마지막에 휙 들어와서, 고른 사람이 기대한
    "밀려 들어오기"로 보이지 않는다. `text_w`는 그리기 직전에 ffmpeg가 아는
    값이라 여기서 픽셀로 고정할 수 없고, 식에 그대로 태운다.
    """
    if motion == "none":
        return None, base_x
    window = _shape_motion_sec(motion, start_sec=start_sec, end_sec=end_sec)
    if window <= 0:
        return None, base_x
    span = _motion_number(window)
    appearing = f"clip((t-{_motion_number(start_sec)})/{span},0,1)"
    leaving = f"clip(({_motion_number(end_sec)}-t)/{span},0,1)"
    if motion == "fade_in":
        return appearing, base_x
    if motion == "fade_out":
        return leaving, base_x
    if motion == "fade_in_out":
        return f"min({appearing},{leaving})", base_x
    # 쉼표가 든 식은 따옴표로 묶어야 ffmpeg가 옵션 구분자로 읽지 않는다. 자리 식
    # 안의 `({base_x})` 괄호도 필수다 -- `w-text_w-77` 같은 식을 괄호 없이 빼면
    # 부호가 뒤집힌다.
    if motion == "slide_in_left":
        return None, f"'({base_x})-(1-{appearing})*(({base_x})+text_w)'"
    return None, f"'({base_x})+(1-{appearing})*(w-({base_x}))'"


def _icon_overlay_filter(
    overlay: dict[str, Any],
    *,
    glyph: str,
    width: int,
    height: int,
    start_sec: float,
    end_sec: float,
    font_file: str | None,
) -> str:
    """아이콘 오버레이가 그릴 drawtext 필터.

    아이콘은 자산 파일이 아니라 **글꼴에 이미 있는 글자 하나**다. 그래서 새 필터
    체계를 만들지 않고 두 렌더 경로가 이미 쓰는 drawtext를 그대로 탄다 -- 크기
    3단은 fontsize로, 위치 9칸은 도형과 같은 여백 계산으로 간다.
    """
    resolved_font = resolve_icon_font(glyph, preferred=font_file)
    if resolved_font is None:
        # 없는 글자를 그리면 ffmpeg는 실패하지 않고 빈 상자를 그린다. 그 완성본은
        # 성공으로 끝나서 owner가 알아채지 못하므로 여기서 멈춘다.
        # 안내는 **실제로 듣는 조치**를 말해야 한다. 아이콘 글꼴 글자는 위 함수가
        # `preferred`를 일부러 무시하므로 `VIDEOBOX_OVERLAY_FONT`를 바꿔도 달라지지
        # 않는다 -- 그걸 시키면 owner가 안 되는 일을 반복하게 된다.
        if glyph in ICON_FONT_GLYPH_SET:
            raise FinalRenderError(
                "The bundled icon font is missing, so this mark would render as an empty box. "
                f"Restore '{ICON_FONT_FILE_NAME}' under '{BUNDLED_ICON_FONT_DIRECTORY}' "
                f"(or '{CONTAINER_ICON_FONT_DIRECTORY}') and retry."
            )
        raise FinalRenderError(
            "Overlay font cannot draw this icon; it would render as an empty box. "
            "Install a font that includes it or set VIDEOBOX_OVERLAY_FONT."
        )
    size = str(overlay.get("size") or "").strip().lower()
    _width_fraction, height_fraction = _SHAPE_OVERLAY_SIZE_FRACTIONS.get(
        size, _SHAPE_OVERLAY_SIZE_FRACTIONS["medium"]
    )
    font_size = max(8, round(height * height_fraction))
    margin_x, margin_y = round(width * 0.06), round(height * 0.08)
    horizontal = str(overlay.get("horizontal") or "").strip().lower()
    vertical = str(overlay.get("vertical") or "").strip().lower()
    # 글자 크기는 글꼴마다 달라 픽셀로 고정할 수 없다. drawtext가 아는 실제 글자
    # 상자(text_w/text_h)로 계산해야 9칸이 어느 글꼴에서나 같은 자리에 온다.
    x = (
        str(margin_x) if horizontal == "left"
        else f"w-text_w-{margin_x}" if horizontal == "right"
        else "(w-text_w)/2"
    )
    y = (
        str(margin_y) if vertical == "top"
        else f"h-text_h-{margin_y}" if vertical == "bottom"
        else "(h-text_h)/2"
    )
    # 등장·퇴장·이동.
    alpha_expression, x = _icon_motion_expressions(
        canonical_shape_overlay_motion(overlay.get("motion")),
        start_sec=start_sec,
        end_sec=end_sec,
        base_x=x,
    )
    # `alpha`는 fontcolor에 이미 붙은 0.9를 **덮어쓰지 않고 곱한다**(실측: 0.9와
    # alpha=0.5가 fontcolor 1.0과 alpha=0.45와 같은 픽셀을 냈다). 그래서 다
    # 나타났을 때의 진하기가 `그대로`와 같다.
    alpha = f"alpha='{alpha_expression}':" if alpha_expression else ""
    # 강조색만으로는 밝은 화면 위에서 사라진다. 같은 글자에 어두운 테두리를 둘러
    # 어느 장면에서도 보이게 한다. 테두리도 `alpha`를 따라 함께 흐려진다(실측).
    return (
        f"drawtext=fontfile='{_escaped_filter_path(resolved_font)}':text='{glyph}':x={x}:y={y}:"
        f"fontsize={font_size}:fontcolor={_SHAPE_OVERLAY_COLOR}:"
        f"borderw={max(2, round(font_size * 0.06))}:bordercolor=black@0.7:{alpha}"
        f"enable='between(t,{start_sec},{end_sec})'"
    )


def export_overlay_shape_filters(
    overlay: dict[str, Any],
    *,
    width: int,
    height: int,
    start_sec: float,
    end_sec: float,
    font_file: str | None = None,
) -> list[str]:
    """정지 도형·아이콘 오버레이가 그릴 필터. 두 렌더 경로가 이 하나를 쓴다 --
    경로마다 따로 계산하면 같은 표시가 다른 자리에 그려진다.

    강조 상자·밑줄은 drawbox로, 화살표 같은 아이콘은 drawtext로 그린다. drawbox가
    사각형만 그릴 수 있어서 화살표를 못 넣었던 자리를, 글꼴에 이미 있는 글자
    하나로 메운 것이다 -- 자산 파일도 굽는 단계도 없다.
    """
    if str(overlay.get("overlay_type") or "").strip().lower() != "shape_overlay":
        return []
    shape = str(overlay.get("shape") or "").strip().lower()
    glyph = overlay_icon_glyph(shape)
    if glyph is not None:
        return [_icon_overlay_filter(
            overlay, glyph=glyph, width=width, height=height,
            start_sec=start_sec, end_sec=end_sec, font_file=font_file,
        )]
    if shape not in SHAPE_OVERLAY_DRAWN_SHAPES:
        return []
    size = str(overlay.get("size") or "").strip().lower()
    width_fraction, height_fraction = _SHAPE_OVERLAY_SIZE_FRACTIONS.get(
        size, _SHAPE_OVERLAY_SIZE_FRACTIONS["medium"]
    )
    box_width = max(2, round(width * width_fraction))
    box_height = max(2, round(height * height_fraction))
    margin_x, margin_y = round(width * 0.06), round(height * 0.08)
    horizontal = str(overlay.get("horizontal") or "").strip().lower()
    vertical = str(overlay.get("vertical") or "").strip().lower()
    x = (
        margin_x if horizontal == "left"
        else width - box_width - margin_x if horizontal == "right"
        else (width - box_width) // 2
    )
    y = (
        margin_y if vertical == "top"
        else height - box_height - margin_y if vertical == "bottom"
        else (height - box_height) // 2
    )
    if shape == "underline":
        # 밑줄은 고른 칸의 아래 변에 놓인 채워진 띠다.
        bar_height = max(4, round(height * 0.015))
        draw_y, draw_height, thickness = y + box_height - bar_height, bar_height, "fill"
    else:
        draw_y, draw_height, thickness = y, box_height, str(max(3, round(height * 0.011)))
    # 등장·퇴장·이동. `그대로`면 조각이 하나뿐이라 예전 필터와 글자까지 같다.
    motion = canonical_shape_overlay_motion(overlay.get("motion"))
    # 밀려 들어오는 거리는 **가장자리까지 딱 그만큼**이다. 화면 너비를 통째로
    # 쓰면 대부분의 시간을 화면 밖에서 보내다가 마지막에 휙 들어온다.
    travel = x + box_width if motion == "slide_in_left" else max(0, width - x)
    return [
        f"drawbox=x={x + round(offset * travel)}:y={draw_y}:w={box_width}:h={draw_height}:"
        f"color={_shape_overlay_color(alpha)}:t={thickness}:enable='{enable}'"
        for enable, alpha, offset in _shape_motion_slices(
            motion, start_sec=start_sec, end_sec=end_sec
        )
    ]


def _default_overlay_font() -> str:
    r"""The name here must match the one the failure message tells the owner to
    set. It read `VIDEBOX_OVERLAY_FONT` -- an `O` short -- so following the
    instruction changed nothing. The default is a font that exists in the
    container and has Korean glyphs; the old `C:\Windows\Fonts` default
    could never resolve there."""
    return os.environ.get("VIDEOBOX_OVERLAY_FONT", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


class TransitionSources(NamedTuple):
    """전환 하나가 쓰는 두 입력, 그리고 앞 장면이 재료를 꺼낼 지점.

    `outgoing_start_sec`을 렌더러가 **실제로 재서** 넘긴다. 앞 장면이 원본을
    끝까지 다 쓴 경우 그 뒤에는 빌릴 프레임이 한 장도 없고, 그러면 `tpad`가
    붙들 프레임도 없어 **전환이 통째로 사라진다.** 그때 ffmpeg는 실패하지
    않는다 -- 성공(0)으로 끝나고 길이도 맞는데 화면만 딱 끊긴다. 실측으로
    확인했다. 이 저장소가 가장 싫어하는 종류의 실패라 그냥 두지 않는다.
    """

    outgoing_index: int
    incoming_index: int
    outgoing_start_sec: float


@dataclass(frozen=True, slots=True)
class CompositionRenderInputs:
    """The one immutable composition/caption input accepted by every renderer."""

    composition_plan: CompositionPlan
    captions: tuple[Any, ...]


@dataclass(slots=True)
class FfmpegFinalRenderer:
    store: LocalProjectStore
    ffmpeg_binary: str = "ffmpeg"
    render_timeout_seconds: int = 1800
    video_width: int = 1280
    video_height: int = 720
    video_fps: int | str = 30
    video_sar: str = "1:1"
    bgm_volume: float = 0.25
    # Read when a renderer is built, not when this module is imported --
    # otherwise setting the variable after import silently does nothing,
    # which is the same trap the misspelled name set.
    overlay_font_file: str = field(default_factory=_default_overlay_font)
    ffprobe_binary: str = "ffprobe"
    # (경로, selector, mtime) → 스트림 존재 여부. 렌더 하나가 같은 원본을
    # 클립 수만큼 다시 재지 않게 한다. `_replace_sharing_caches`를 거치지 않고
    # `dataclasses.replace()`를 직접 부르면 렌더마다 빈 채로 되돌아간다 --
    # `init=False` 필드는 `replace()`가 새로 만들 때 `default_factory`를
    # 다시 부르기 때문이다.
    _stream_probe_cache: dict[tuple[str, str, int], bool] = field(default_factory=dict, init=False, repr=False, compare=False)
    # (경로, mtime) → sha256. `verify_output_sources()`가 같은 소스를 다시 재는
    # 것을 막는다. 위와 같은 이유로 `_replace_sharing_caches`를 거쳐야 렌더를
    # 넘어 산다. 자세한 내용은
    # `output_source_verifier.capture_output_source_snapshots`의 docstring.
    _output_source_hash_cache: dict[tuple[Path, int], str] = field(default_factory=dict, init=False, repr=False, compare=False)

    def _replace_sharing_caches(self, **changes: Any) -> "FfmpegFinalRenderer":
        """`dataclasses.replace(self, **changes)`, but the new instance keeps
        this one's per-source caches instead of starting them empty.

        `replace()` doesn't pass `init=False` fields to the constructor, so
        each one's `default_factory` runs again on the copy -- a plain
        `replace(self, ...)` silently resets `_stream_probe_cache` and
        `_output_source_hash_cache` on every proxy/plan renderer built for a
        render (2026-08-28: found while measuring why per-render caching
        wasn't paying off across repeated exact-preview requests for the
        same project). Sharing the same dict objects instead means a hash or
        probe computed by one renderer copy is visible to the next.
        """
        new_renderer = replace(self, **changes)
        new_renderer._stream_probe_cache = self._stream_probe_cache
        new_renderer._output_source_hash_cache = self._output_source_hash_cache
        return new_renderer

    @staticmethod
    def _cgroup_cpu_quota() -> int | None:
        """컨테이너가 실제로 받은 CPU 몫. 한도가 없으면 None.

        `nproc`은 호스트의 CPU를 그대로 보여 준다 -- `cpus: 2.0`으로 묶어도 16이라고
        답한다. ffmpeg는 그 숫자를 믿고 스레드를 잡는다.
        """
        try:
            raw = Path("/sys/fs/cgroup/cpu.max").read_text(encoding="utf-8").split()
        except OSError:
            return None
        if len(raw) != 2 or raw[0] == "max":
            return None
        try:
            quota, period = int(raw[0]), int(raw[1])
        except ValueError:
            return None
        if quota <= 0 or period <= 0:
            return None
        return max(1, quota // period)

    def encoder_thread_limit(self) -> int:
        """ffmpeg가 잡을 스레드 수의 상한. 인코더와 필터 그래프 양쪽에 쓴다.

        **컨테이너의 프로세스 상한이 128인데 ffmpeg는 호스트 CPU 수(16)를 보고
        스레드를 잡는다.** 입력 5개짜리 필터 그래프에 x264와 aac까지 붙으면 그 상한을
        넘고, 스레드 생성이 EAGAIN으로 실패한다. ffmpeg는 그것을 `Error reinitializing
        filters!`와 `streams received no packets`로만 말하고, owner 화면에는
        "완성본을 만들지 못했어요"로만 보인다 -- 어디에도 이유가 없다.

        컨테이너에서 실측했다. 필터 스레드를 안 정하면(=기본 16) 실패하고, 2·4·8은
        모두 성공한다. 인코더만 묶는 것으로는 부족했다 -- **막힌 것은 인코더가 아니라
        필터 쪽 스레드였다.**

        그래서 `nproc`이 아니라 **컨테이너가 실제로 받은 CPU 몫**을 기준으로 삼는다.
        `compose.yaml`은 이 서비스를 `cpus: 2.0`으로 묶는데 `nproc`은 16이라고 답한다.
        받은 것이 2개뿐인데 8개를 띄우는 것은 빨라지지도 않으면서 상한만 먹는다.

        더 큰 해상도나 더 많은 입력에서는 이 상한으로도 모자랄 수 있다. 그때는 이
        숫자가 아니라 컨테이너의 `pids_limit`과 `cpus`를 봐야 한다.
        """
        budget = self._cgroup_cpu_quota() or os.cpu_count() or 1
        return max(1, min(budget, 8))

    def extract_composition_plan(
        self, *, timeline: dict[str, Any], captions: list[dict[str, Any]] | None = None
    ) -> CompositionPlan:
        """Return the pure composition authority shared with exact preview.

        Task 1 intentionally leaves the established ffmpeg command path
        untouched.  Task 2 will pass this exact object into both final/proxy
        command construction before claiming command-level parity.
        """
        return CompositionPlan.from_timeline(timeline=timeline, captions=captions or [])

    def build_final_render_inputs(self, *, composition_plan: CompositionPlan) -> CompositionRenderInputs:
        return CompositionRenderInputs(composition_plan=composition_plan, captions=composition_plan.captions)

    def build_exact_preview_inputs(self, *, composition_plan: CompositionPlan) -> CompositionRenderInputs:
        # This is intentionally the same value object as final output.  A
        # proxy is a different profile, never a different composition.
        return CompositionRenderInputs(composition_plan=composition_plan, captions=composition_plan.captions)

    def _frame_seconds(self) -> float:
        """프레임 한 장의 길이. `video_fps`는 `30`일 수도 `30000/1001`일 수도 있다."""
        numerator, separator, denominator = str(self.video_fps).partition("/")
        frames_per_second = float(numerator) / float(denominator) if separator else float(numerator)
        return 1.0 / frames_per_second if frames_per_second > 0 else 1.0 / 30.0

    def _broll_fit_transform(self, controls: dict[str, Any]) -> str:
        """화면 클립을 출력 크기에 맞추는 방법. 전환 양쪽도 **같은 것**을 써야 한다.

        여기가 어긋나면 전환 중에만 그림이 튄다 -- 잘린 화면과 여백 넣은 화면이
        1초 동안 서로 넘어가는 모양이 된다.
        """
        # 손떨림 보정은 **크기를 맞추기 전에** 건다. `deshake`는 흔들린 만큼
        # 화면을 밀어서 보정하므로 가장자리가 비는데, 원본 해상도에서 걸어야
        # 그 뒤의 `scale`·`crop`이 빈 자리를 함께 처리한다. 순서를 뒤집으면
        # 출력 크기에 맞춘 그림이 다시 밀리면서 검은 테두리가 남는다.
        stabilize = "deshake," if controls.get("stabilize") else ""
        if controls["fit"] == "crop":
            transform = (
                f"{stabilize}scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=increase,"
                f"crop={self.video_width}:{self.video_height}"
            )
        else:
            transform = (
                f"{stabilize}scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"pad={self.video_width}:{self.video_height}:(ow-iw)/2:(oh-ih)/2"
            )
        # 색감(`filters.py`)을 **여기서** 붙인다. 이 함수가 전환 양쪽에도 쓰이므로
        # (위 docstring 참고) 여기 붙이면 전환 중에도 같은 색이 유지된다.
        # 다른 데 붙였다가는 전환 1초 동안만 색이 튄다 -- `fit`이 어긋났을 때와
        # 똑같은 사고다.
        look = filter_chain(controls.get("filter"))
        return f"{transform},{look}" if look else transform

    def _transition_side_filter(
        self, *, source_index: int, source_start_sec: float, seconds: float,
        speed: float, transform: str, sar: str, label: str,
    ) -> str:
        """전환 한쪽의 재료를 정확히 ``seconds``초짜리 스트림으로 만든다.

        **`fps`가 맨 끝에 와야 한다.** `xfade`는 들어오는 스트림이 *고정
        프레임률*이라야 받아 주는데, `trim`·`setpts`를 거치면 그 정보가 사라진다.
        앞쪽에 두었다가 컨테이너에서 이렇게 거부당했다:

            The inputs needs to be a constant frame rate; current rate of 1/0 is invalid

        같은 이유로 **`settb`를 쓰지 않는다.** 시간기준을 다시 잡으면 프레임률이
        `1/0`(모름)이 되어 xfade가 거부한다. 처음에 `settb=AVTB`를 넣었다가
        이 사고를 냈다 -- 개발 기기의 ffmpeg 8.1은 통과시키고 컨테이너의 7.1은
        거부해서, **로컬 테스트는 전부 초록인데 실물만 터졌다.**

        `tpad=stop_mode=clone`은 원본이 모자랄 때의 대비다. 앞 장면의 남은
        원본이 전환 길이보다 짧으면 마지막 프레임을 붙들어 길이를 채운다.
        **길이를 못 채우면 xfade가 조용히 짧아져** 뒤가 어긋난다.
        """
        source_window = _seconds(source_start_sec + seconds * speed)
        retime = "setpts=PTS-STARTPTS" if speed == 1.0 else f"setpts=(PTS-STARTPTS)/{speed}"
        return (
            f"[{source_index}:v]trim=start={_seconds(source_start_sec)}:end={source_window},{retime},"
            f"{transform},setsar={sar},format=yuv420p,"
            f"tpad=stop_mode=clone:stop_duration={_seconds(seconds)},"
            f"trim=start=0:end={_seconds(seconds)},setpts=PTS-STARTPTS,fps={self.video_fps}[{label}]"
        )

    def build_plan_filter_graph(
        self, *, composition_plan: CompositionPlan, source_indices: dict[str, int],
        export_overlay_indices: dict[int, int] | None = None,
        track_overlay_indices: dict[str, int] | None = None,
        transition_source_indices: dict[str, TransitionSources] | None = None,
    ) -> str:
        """Build the shared timeline placement graph.

        Video policy is intentionally deterministic: an all-black canvas
        starts at PTS zero, each B-roll source is placed at its canonical
        timeline PTS, and later `(start_sec, clip_id)` overlays win where
        intervals overlap.  That preserves leading/internal gaps instead of
        concatenating unrelated source segments.

        **이 함수 하나가 완성본과 정확 미리보기 양쪽을 만든다.** 둘 다
        `_render_composition_plan_to_mp4`를 거치므로 여기만 고치면 두 곳이
        같이 바뀐다. `render_timeline_to_mp4`의 조각 추출+concat 경로는
        `composition_plan` 없이 부를 때만 쓰이며 지금 제품 경로에는 없다.
        """
        duration = max(composition_plan.duration_sec, 0.001)
        sar = composition_plan.sample_aspect_ratio.replace(":", "/")
        filters = [
            f"color=c=black:s={self.video_width}x{self.video_height}:r={self.video_fps}:d={duration}[canvas0]"
        ]
        canvas = "canvas0"
        broll = sorted(
            (item for item in composition_plan.items if item.track_type == "broll"),
            key=lambda item: (item.start_sec, item.clip_id),
        )
        for ordinal, item in enumerate(broll, start=1):
            index = source_indices[item.clip_id]
            label = f"v_{item.clip_id}"
            duration_sec = item.end_sec - item.start_sec
            controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(duration_sec, 0.001))
            transform = self._broll_fit_transform(controls)
            # 배속을 걸면 원본 창이 **화면에서 차지하는 시간**은 그만큼 줄거나
            # 는다. 아래 loop/pad 판단은 전부 화면 시간 기준이므로 여기서 한 번
            # 환산해 두고 그 값만 쓴다.
            speed = float(controls["speed"]) * item.playback_rate
            source_window_sec = (item.source_out_sec - item.source_in_sec) / speed
            if controls["pad"] and not controls["loop"]:
                transform += f",tpad=stop_mode=add:stop_duration={max(0.0, duration_sec - source_window_sec)}"
            # 배속 1에는 필터를 더하지 않는다 -- 안 쓰는 기능에 화질과 시간을
            # 들이지 않는다.
            retime = "setpts=PTS-STARTPTS" if speed == 1.0 else f"setpts=(PTS-STARTPTS)/{speed}"
            source_filter = (
                f"[{index}:v]trim=start={item.source_in_sec}:end={item.source_out_sec},{retime}"
            )
            if controls["loop"] and source_window_sec < duration_sec:
                numerator, separator, denominator = str(self.video_fps).partition("/")
                frames_per_second = float(numerator) / float(denominator) if separator else float(numerator)
                loop_frames = max(1, ceil(source_window_sec * frames_per_second))
                source_filter += (
                    f",fps={self.video_fps},loop=loop=-1:size={loop_frames}:start=0,"
                    f"trim=duration={duration_sec},setpts=PTS-STARTPTS"
                )
            # 디졸브. **알파를 태워야** 아래 클립이 비친다 -- `alpha=1` 없이 fade를
            # 걸면 검은색으로 가라앉는다. 안 쓰면 필터를 아예 더하지 않는다.
            dissolve = ""
            if controls["fade_in_sec"] or controls["fade_out_sec"]:
                dissolve = ",format=yuva420p"
                if controls["fade_in_sec"]:
                    dissolve += f",fade=t=in:st=0:d={controls['fade_in_sec']}:alpha=1"
                if controls["fade_out_sec"]:
                    dissolve += f",fade=t=out:st={max(0.0, duration_sec - controls['fade_out_sec'])}:d={controls['fade_out_sec']}:alpha=1"
            filters.append(
                f"{source_filter},{transform}{dissolve},setsar={sar},setpts=PTS+{item.start_sec}/TB[{label}]"
            )
            next_canvas = f"canvas{ordinal}"
            filters.append(f"[{canvas}][{label}]overlay=eof_action=pass:repeatlast=0[{next_canvas}]")
            canvas = next_canvas
        # ------------------------------------------------------------------
        # 장면 전환.
        #
        # **아무것도 옮기지 않는다.** 전환은 들어오는 클립 B의 첫 `d`초 구간
        # `[T, T+d]` 안에서만 일어나고, 그 구간에 `xfade(앞 장면의 남은 원본,
        # B의 앞부분)`을 얹는다. B는 자기 자리에 그대로 있고 A도 그대로다.
        # 그래서 **전체 길이·자막 위치가 하나도 안 움직인다.**
        #
        # A쪽 재료를 타임라인이 아니라 **원본 뒷부분**(`source_out_sec` 이후)에서
        # 빌리는 것이 핵심이다. 타임라인에서 빌리면 A의 마지막 구간이 두 번 보인다.
        #
        # 두 클립을 모두 **덮어써야** 하므로 위 배치 루프가 끝난 뒤에 그린다.
        for ordinal, (previous, item) in enumerate(transition_boundaries(composition_plan.items), start=1):
            if transition_source_indices is None:
                continue
            indices = transition_source_indices.get(item.clip_id)
            if indices is None:
                continue
            incoming_sec = item.end_sec - item.start_sec
            outgoing_sec = previous.end_sec - previous.start_sec
            # 전환이 옆 장면보다 길면 그 장면을 통째로 먹는다. 짧은 쪽에 맞춘다.
            seconds = min(float(item.transition["duration_sec"]), incoming_sec, outgoing_sec)
            if seconds <= 0:
                continue
            outgoing_index, incoming_index, outgoing_start_sec = indices
            outgoing_controls = normalize_media_controls(
                previous.media_controls, media_kind="broll", duration_sec=max(outgoing_sec, 0.001)
            )
            incoming_controls = normalize_media_controls(
                item.media_controls, media_kind="broll", duration_sec=max(incoming_sec, 0.001)
            )
            filters.append(self._transition_side_filter(
                source_index=outgoing_index,
                # 앞 장면이 **원래 안 쓰고 남긴** 원본이다. 남은 것이 없으면
                # 렌더러가 마지막 프레임 자리를 재서 넘겨 준다.
                source_start_sec=outgoing_start_sec,
                seconds=seconds, speed=float(outgoing_controls["speed"]),
                transform=self._broll_fit_transform(outgoing_controls), sar=sar,
                label=f"transition_out_{ordinal}",
            ))
            filters.append(self._transition_side_filter(
                source_index=incoming_index,
                # 들어오는 장면은 앞당기지 않는다. 자기 첫 프레임 그대로다.
                source_start_sec=item.source_in_sec,
                seconds=seconds, speed=float(incoming_controls["speed"]),
                transform=self._broll_fit_transform(incoming_controls), sar=sar,
                label=f"transition_in_{ordinal}",
            ))
            label = f"transition_{item.clip_id}"
            filters.append(
                f"[transition_out_{ordinal}][transition_in_{ordinal}]"
                f"xfade=transition={item.transition['type']}:duration={_seconds(seconds)}:offset=0,"
                # xfade는 안에서 yuv444p로 섞는다. 여기서 되돌려 놓지 않으면
                # 캔버스에 얹을 때 변환기가 끼어든다.
                f"format=yuv420p,setsar={sar},setpts=PTS+{item.start_sec}/TB[{label}]"
            )
            next_canvas = f"canvas_transition_{ordinal}"
            filters.append(f"[{canvas}][{label}]overlay=eof_action=pass:repeatlast=0[{next_canvas}]")
            canvas = next_canvas
        track_overlays = sorted(
            (item for item in composition_plan.items if item.track_type == "overlay"),
            key=lambda item: (item.start_sec, item.clip_id),
        )
        for ordinal, item in enumerate(track_overlays, start=1):
            if track_overlay_indices is None or item.clip_id not in track_overlay_indices:
                raise FinalRenderError(
                    "Exact preview overlay source is unavailable. Restore a local image or video source and retry."
                )
            index = track_overlay_indices[item.clip_id]
            label = f"track_overlay_{ordinal}"
            next_canvas = f"canvas_track_overlay_{ordinal}"
            filters.append(
                f"[{index}:v]trim=start={item.source_in_sec}:end={item.source_out_sec},setpts=PTS-STARTPTS,"
                f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"setsar={sar},setpts=PTS+{item.start_sec}/TB[{label}]"
            )
            filters.append(
                f"[{canvas}][{label}]overlay=(W-w)/2:(H-h)/2:eof_action=pass:repeatlast=0[{next_canvas}]"
            )
            canvas = next_canvas
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            if export_overlay_indices is None or overlay_index not in export_overlay_indices:
                continue
            start_sec, end_sec = float(overlay.get("start_sec") or 0.0), float(overlay.get("end_sec") or 0.0)
            if end_sec <= start_sec:
                continue
            source_index = export_overlay_indices[overlay_index]
            label = f"export_overlay_{overlay_index}"
            next_canvas = f"canvas_export_{overlay_index}"
            filters.append(
                f"[{source_index}:v]trim=duration={end_sec - start_sec},setpts=PTS-STARTPTS,"
                f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,"
                f"setpts=PTS+{start_sec}/TB[{label}]"
            )
            filters.append(f"[{canvas}][{label}]overlay=(W-w)/2:(H-h)/2:eof_action=pass:repeatlast=0[{next_canvas}]")
            canvas = next_canvas
        # 자막은 ASS로, 글줄 오버레이는 drawtext로 그려서 두 필터는 서로를 모른다.
        # 자막이 먹는 띠를 여기서 받아 카드가 그 위를 밟지 않게 한다.
        plan_caption_segments = [
            {"caption_text": cue.text, "caption_style": cue.style, "start_sec": cue.start_sec, "end_sec": cue.end_sec}
            for cue in composition_plan.captions
        ]
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            if overlay.get("asset_uri") or overlay.get("asset_id"):
                continue
            lines = export_overlay_text_lines(dict(overlay))
            if not lines:
                continue
            start_sec, end_sec = float(overlay.get("start_sec") or 0.0), float(overlay.get("end_sec") or 0.0)
            if end_sec <= start_sec:
                continue
            if not Path(self.overlay_font_file).is_file():
                raise FinalRenderError("Overlay font is missing; set VIDEOBOX_OVERLAY_FONT before rendering text overlays.")
            text_filters = export_overlay_text_filters(
                lines, font_file=self.overlay_font_file, video_height=self.video_height,
                start_sec=start_sec, end_sec=end_sec,
                caption_band=caption_band_px(
                    plan_caption_segments, video_width=self.video_width, video_height=self.video_height,
                    start_sec=start_sec, end_sec=end_sec,
                ),
            )
            for line_index, text_filter in enumerate(text_filters):
                next_canvas = f"canvas_text_{overlay_index}_{line_index}"
                filters.append(f"[{canvas}]{text_filter}[{next_canvas}]")
                canvas = next_canvas
        # 정지 도형(강조 상자·밑줄)과 아이콘(화살표 등). 글줄 경로와 분리한다 --
        # 도형은 글꼴이 필요 없고, 아이콘은 글자 하나라 줄 쌓기를 타지 않는다.
        # 두 렌더 경로가 export_overlay_shape_filters 하나를 같이 쓴다.
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            start_sec, end_sec = float(overlay.get("start_sec") or 0.0), float(overlay.get("end_sec") or 0.0)
            if end_sec <= start_sec:
                continue
            shape_filters = export_overlay_shape_filters(
                dict(overlay), width=self.video_width, height=self.video_height,
                start_sec=start_sec, end_sec=end_sec, font_file=self.overlay_font_file,
            )
            for shape_index, shape_filter in enumerate(shape_filters):
                next_canvas = f"canvas_shape_{overlay_index}_{shape_index}"
                filters.append(f"[{canvas}]{shape_filter}[{next_canvas}]")
                canvas = next_canvas
        filters.append(f"[{canvas}]null[vout]")
        return ";".join(filters)

    def build_plan_audio_filter_graph(
        self, *, composition_plan: CompositionPlan, source_indices: dict[str, int],
        soundless_source_clip_ids: set[str] | frozenset[str] = frozenset(),
    ) -> str:
        """Shared audio placement/control graph for final and proxy output."""
        duration = max(composition_plan.duration_sec, 0.001)
        # 음소거한 레인(`track_states.py`)은 **아예 안 섞는다.** 음량 값을
        # 덮어쓰는 방식은 트랙마다 제어가 달라서 통하지 않는다 -- 내레이션은
        # `media_controls`를 안 읽고, `bgm`·`sfx`는 `gain_db`를 쓴다.
        muted = composition_plan.muted_tracks
        narration = [
            item for item in composition_plan.items
            if item.track_type == "narration" and "narration" not in muted
        ]
        filters: list[str] = []
        narration_labels: list[str] = []
        for item in narration:
            label = f"a_{item.clip_id}"
            delay = max(0, round(item.start_sec * 1000))
            retime = "" if item.playback_rate == 1.0 else f",{_atempo_chain(item.playback_rate)}"
            filters.append(f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec}{retime},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
            narration_labels.append(f"[{label}]")
        if not narration_labels:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration}[narration_mix]")
        elif len(narration_labels) == 1:
            filters.append(f"{narration_labels[0]}anull[narration_mix]")
        else:
            # `normalize=0` -- 클립이 둘로 잘렸다고 목소리가 절반이 되면 안 된다.
            filters.append(f"{''.join(narration_labels)}amix=inputs={len(narration_labels)}:duration=longest:normalize=0[narration_mix]")

        has_ducked_bgm = any(
            item.track_type == "bgm"
            and "bgm" not in muted
            and normalize_media_controls(
                item.media_controls,
                media_kind="audio",
                duration_sec=max(item.end_sec - item.start_sec, 0.001),
            )["ducking"]
            for item in composition_plan.items
        )
        narration_sidechain = "[narration_mix]"
        labels = ["[narration_mix]"]
        if has_ducked_bgm:
            filters.append("[narration_mix]asplit=2[narration_final][narration_sidechain]")
            narration_sidechain = "[narration_sidechain]"
            labels = ["[narration_final]"]
        for item in composition_plan.items:
            if item.track_type in muted:
                continue
            if item.track_type == "broll":
                controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                if not controls["preserve_source_audio"]:
                    continue
                if item.clip_id in soundless_source_clip_ids:
                    # 원본에 오디오 스트림이 없다. 없는 `[N:a]`를 그래프에 넣으면
                    # ffmpeg가 통째로 실패한다 -- 실을 소리가 없으니 건너뛴다.
                    continue
                label = f"a_{item.clip_id}"
                delay = max(0, round(item.start_sec * 1000))
                speed = float(controls["speed"]) * item.playback_rate
                volume = float(controls["volume"])
                # 소리도 화면과 **같은 배속**으로 가야 입이 맞는다. 화면만
                # 빨라지면 말과 그림이 어긋난다.
                source_window_sec = (item.source_out_sec - item.source_in_sec) / speed
                timeline_duration_sec = item.end_sec - item.start_sec
                source_filter = f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec}"
                if speed != 1.0:
                    source_filter += f",{_atempo_chain(speed)}"
                if volume != 1.0:
                    source_filter += f",volume={volume}"
                if controls["loop"] and source_window_sec < timeline_duration_sec:
                    # Normalize before aloop so its sample count exactly spans
                    # the selected source window, not an input-dependent rate.
                    source_filter += (
                        f",aresample=48000,aloop=loop=-1:size={max(1, ceil(source_window_sec * 48000))}:start=0,"
                        f"atrim=duration={timeline_duration_sec}"
                    )
                filters.append(f"{source_filter},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
                labels.append(f"[{label}]")
            elif item.track_type in {"bgm", "sfx"}:
                controls = normalize_media_controls(item.media_controls, media_kind="audio", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                label = f"a_{item.clip_id}"
                delay = max(0, round(item.start_sec * 1000))
                effect = f"volume={controls['gain_db']}dB"
                effect += _audio_cleanup_chain(controls)
                if controls["fade_in_sec"]:
                    effect += f",afade=t=in:st=0:d={controls['fade_in_sec']}"
                if controls["fade_out_sec"]:
                    effect += f",afade=t=out:st={max(0.0, item.end_sec - item.start_sec - controls['fade_out_sec'])}:d={controls['fade_out_sec']}"
                retime = "" if item.playback_rate == 1.0 else f",{_atempo_chain(item.playback_rate)}"
                filters.append(f"[{source_indices[item.clip_id]}:a]atrim=start={item.source_in_sec}:end={item.source_out_sec}{retime},{effect},asetpts=PTS-STARTPTS,adelay={delay}|{delay}[{label}]")
                if item.track_type == "bgm" and controls["ducking"]:
                    ducked = f"duck_{item.clip_id}"
                    filters.append(f"[{label}]{narration_sidechain}sidechaincompress=threshold=0.05:ratio=8[{ducked}]")
                    labels.append(f"[{ducked}]")
                else:
                    labels.append(f"[{label}]")
        # `normalize=0`. 이게 없으면 `amix`가 입력 수만큼 나눠서, **소리를 하나
        # 더할 때마다 이미 있던 소리가 전부 작아진다** -- B-roll 소리를 켰더니
        # 그 장면과 상관없는 구간의 내레이션까지 조용해졌다(2026-08-19 완성본에서
        # 재서 찾았다). 켠 사람은 소리를 더한 것이지 나머지를 줄인 게 아니다.
        #
        # 합쳐서 너무 커지는 것은 클립별 `소리 크기`와 `gain_db`로 조절한다.
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
            f"apad=whole_dur={duration},atrim=duration={duration},asetpts=PTS-STARTPTS[aout]"
        )
        return ";".join(filters)

    @staticmethod
    def _timeline_from_plan(*, composition_plan: CompositionPlan, timeline_context: dict[str, Any]) -> dict[str, Any]:
        """Rehydrate only the source-resolution shape from the authoritative plan."""
        tracks: dict[str, list[dict[str, Any]]] = {}
        for item in composition_plan.items:
            controls = dict(item.media_controls)
            # Range normalization has already shifted source time exactly once.
            # Put that resolved source in on the source-reading contract; do
            # not consult the mutable timeline again for placement/trim.
            if item.track_type == "broll":
                controls["in_sec"] = item.source_in_sec
            tracks.setdefault(item.track_type, []).append({
                "clip_id": item.clip_id,
                "asset_id": item.asset_id,
                "asset_uri": item.asset_uri,
                "start_sec": item.start_sec,
                "end_sec": item.end_sec,
                "source_in_sec": item.source_in_sec,
                "source_out_sec": item.source_out_sec,
                "media_controls": controls,
                "expected_content_sha256": item.expected_content_sha256,
                "media_revision": item.media_revision,
                "overlay_type": item.overlay_type,
                "overlay_payload": dict(item.overlay_payload),
            })
        return {
            "output": {
                "width": composition_plan.width, "height": composition_plan.height,
                "fps_num": composition_plan.fps_num, "fps_den": composition_plan.fps_den,
                "sample_aspect_ratio": composition_plan.sample_aspect_ratio,
                "rotation": composition_plan.rotation,
            },
            "narration_source_uri": timeline_context.get("narration_source_uri"),
            "tracks": [{"track_type": kind, "clips": clips} for kind, clips in tracks.items()],
            "export_overlays": [dict(item) for item in composition_plan.export_overlays],
        }

    def render_exact_preview_to_mp4(
        self,
        *,
        project_id: str,
        composition_plan: CompositionPlan,
        timeline_context: dict[str, Any],
        output_path: Path,
        subtitle_ass_path: Path | None,
    ) -> Path:
        """Render a 720-long-edge, current-plan proxy with burned ASS captions."""
        inputs = self.build_exact_preview_inputs(composition_plan=composition_plan)
        if not inputs.composition_plan.items:
            raise FinalRenderError("Exact preview has no composable clips. Restore missing source media and retry.")
        if composition_plan.width >= composition_plan.height:
            width, height = 720, max(2, round((composition_plan.height * 720 / composition_plan.width) / 2) * 2)
        else:
            width, height = max(2, round((composition_plan.width * 720 / composition_plan.height) / 2) * 2), 720
        proxy_renderer = self._replace_sharing_caches(
            video_width=width, video_height=height,
            video_fps=f"{composition_plan.fps_num}/{composition_plan.fps_den}",
            video_sar=composition_plan.sample_aspect_ratio,
        )
        return proxy_renderer.render_timeline_to_mp4(
            project_id=project_id,
            timeline=proxy_renderer._timeline_from_plan(composition_plan=inputs.composition_plan, timeline_context=timeline_context),
            output_path=output_path,
            subtitle_ass_path=subtitle_ass_path,
            composition_plan=inputs.composition_plan,
            proxy_profile=True,
        )

    def _render_composition_plan_to_mp4(
        self,
        *,
        project_id: str,
        composition_plan: CompositionPlan,
        timeline_context: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None,
        subtitle_ass_path: Path | None,
        proxy_profile: bool,
    ) -> Path:
        """Render the canonical plan directly; never sequentially concatenate it."""
        if not composition_plan.items:
            raise FinalRenderError("Timeline has no composable clips to render.")
        generated_ass: Path | None = None
        verify_output_sources(
            store=self.store, project_id=project_id, timeline=timeline_context,
            hash_cache=self._output_source_hash_cache,
        )
        source_paths: list[tuple[Path, bool, bool]] = []
        # **2026-08-27: owner가 실제 프로젝트에서 컷 한 번에 21초가 걸린다고
        # 신고했다.** 서버 기록으로 실측했다(created_at→updated_at). 원인은
        # B-roll 입력에 `-ss`가 없어서였다 -- `trim=start=X` **필터**는 X초까지
        # 디코딩한 뒤 버린다. 494초짜리 원본에서 그 버리는 시간이 고스란히
        # 렌더 시간에 얹혔다.
        #
        # `-ss`를 `-i` **앞**에 두면(입력 탐색) 그 낭비가 사라진다. `-copyts`를
        # 같이 써서 **trim/atrim 필터는 한 글자도 안 바꾼다** -- 원래 타임스탬프가
        # 그대로 보존되므로 자르는 지점이 절대 시각 그대로다. 컨테이너의 실제
        # ffmpeg로 검증했다: 500초 원본에서 3초를 뽑는 데 1.56초 → 0.11초
        # (14배), 비디오 픽셀과 오디오 PCM이 old/new 사이에 바이트 단위로
        # 동일했다.
        fast_seek_offsets: dict[int, float] = {}
        # `source_indices`는 `clip_id`로 찾는다. 갓 나눈 조각(`split_segment`)은
        # 합쳐지기 전까지 **둘이 같은 clip_id를 그대로 쓴다** -- 재보고 알았다:
        # 이 경우 나중 항목이 앞 항목의 색인을 덮어써서 둘 다 같은 물리 입력을
        # 가리키게 된다. 예전엔 그 입력에 탐색이 없어서 우연히 안전했다(둘 다
        # 처음부터 다 읽힌 스트림에서 절대 시각으로 잘랐다). 여기서 탐색을 걸면
        # 겹친 clip_id 중 하나는 **존재하지 않는 시간대**를 찾게 된다 -- 실측
        # 회귀 시험(`test_split_merge_and_reorder_...`)이 잡아냈다. 그 겹침
        # 구조는 고치지 않고, 겹치는 clip_id에는 이 최적화를 안전하게 끈다.
        broll_clip_id_counts: dict[str, int] = {}
        for item in composition_plan.items:
            if item.track_type == "broll":
                broll_clip_id_counts[item.clip_id] = broll_clip_id_counts.get(item.clip_id, 0) + 1
        source_indices: dict[str, int] = {}
        track_overlay_indices: dict[str, int] = {}
        soundless_source_clip_ids: set[str] = set()
        broll_source_paths: dict[str, Path] = {}
        # 디코더 스레드를 1로 묶을 입력들. 지금은 전환 입력만 들어간다.
        #
        # 전환 하나가 입력을 **둘** 늘린다. 이 저장소는 입력이 늘어 컨테이너의
        # 프로세스 상한(128)에 걸린 사고를 이미 두 번 겪었고, 그때 ffmpeg는
        # 이유를 말해 주지 않았다(`encoder_thread_limit` 참고). 전환 입력은
        # 1초 남짓만 읽으므로 1스레드로 충분하다 -- 미리 줄여 둔다.
        #
        # **주의: 이것이 2026-08-22의 렌더 실패를 고친 것은 아니다.** 그건
        # `settb`가 프레임률을 지워 xfade가 거부한 것이었다
        # (`_transition_side_filter` 참고). 여기는 예방일 뿐이다.
        single_thread_source_indices: set[int] = set()
        for item in composition_plan.items:
            if item.track_type == "overlay":
                # Overlay items are represented in the canonical plan but need
                # a visual source.  Fail closed rather than silently omit one.
                if not item.asset_uri:
                    raise FinalRenderError("Exact preview overlay source is missing. Restore it and retry.")
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=item.asset_uri)
                if not source.is_file():
                    raise FinalRenderError(f"Exact preview source is missing: '{source}'. Restore or re-import it and retry.")
                is_image = source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
                if not is_image and not self._has_visual_stream(source):
                    raise FinalRenderError("Exact preview overlay source must be a local image or video. Restore it and retry.")
                track_overlay_indices[item.clip_id] = len(source_paths)
                source_indices[item.clip_id] = len(source_paths)
                source_paths.append((source, is_image, False))
                continue
            elif item.track_type == "narration":
                source = self._resolve_narration_clip_source(
                    project_id=project_id, timeline=timeline_context,
                    clip={"asset_uri": item.asset_uri, "start_sec": item.start_sec, "end_sec": item.end_sec},
                ).path
                should_loop = False
            elif item.track_type == "broll":
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=str(item.asset_uri or ""))
                controls = normalize_media_controls(item.media_controls, media_kind="broll", duration_sec=max(item.end_sec - item.start_sec, 0.001))
                available_source_window = min(self._probe_media_duration(source), item.source_out_sec) - item.source_in_sec
                if available_source_window <= 0:
                    raise FinalRenderError("B-roll source bounds are outside the available media. Adjust trim or source controls.")
                if available_source_window < item.end_sec - item.start_sec and not controls["loop"] and not controls["pad"]:
                    raise FinalRenderError("B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration.")
                if controls["preserve_source_audio"] and not self._has_audio_stream(source):
                    soundless_source_clip_ids.add(item.clip_id)
                should_loop = controls["loop"]
                broll_source_paths[item.clip_id] = source
            elif item.track_type in {"bgm", "sfx"}:
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=str(item.asset_uri or ""))
                should_loop = item.track_type == "bgm"
            else:
                continue
            if not source.is_file():
                raise FinalRenderError(f"Exact preview source is missing: '{source}'. Restore or re-import it and retry.")
            source_indices[item.clip_id] = len(source_paths)
            # B-roll만 대상이다 -- 내레이션·bgm·sfx는 소리뿐이라 이 낭비가 크지
            # 않고, 굳이 넓히지 않는다. 시작점이 0이면 얻을 것도 없다.
            # `clip_id`가 겹치면 안전하게 끈다 -- 위 `broll_clip_id_counts` 참고.
            if item.track_type == "broll" and item.source_in_sec > 0 and broll_clip_id_counts.get(item.clip_id, 0) == 1:
                fast_seek_offsets[len(source_paths)] = item.source_in_sec
            source_paths.append((source, False, should_loop))
        # 전환은 두 클립의 원본을 **한 번 더** 읽는다.
        #
        # 필터그래프에서 입력 하나는 한 번만 쓸 수 있다. 이미 배치에 쓴
        # `[N:v]`를 전환에서 또 쓰려면 `split`으로 갈라야 하는데, 그러면 전환을
        # 안 쓰는 클립의 사슬까지 전부 바꿔야 한다. 같은 파일을 입력으로 다시
        # 다는 편이 기존 사슬을 하나도 건드리지 않는다 -- 이 파일이 화면 오버레이에
        # 쓰는 것과 **같은 방식**이다. 값은 전환 하나당 디코더 두 개다.
        transition_source_indices: dict[str, TransitionSources] = {}
        for previous, item in transition_boundaries(composition_plan.items):
            outgoing = broll_source_paths.get(previous.clip_id)
            incoming = broll_source_paths.get(item.clip_id)
            if outgoing is None or incoming is None:
                continue
            # 앞 장면이 원본을 어디까지 썼는지 **재서** 정한다. 남은 뒷부분이
            # 있으면 거기서 빌리고, 끝까지 다 썼으면 마지막 프레임 자리에서
            # 시작해 `tpad`가 그 한 장을 붙들게 한다. 이 계산을 빼면 전환이
            # 조용히 사라진다(`TransitionSources` 참고).
            last_frame_start = max(0.0, self._probe_media_duration(outgoing) - self._frame_seconds())
            transition_source_indices[item.clip_id] = TransitionSources(
                outgoing_index=len(source_paths),
                incoming_index=len(source_paths) + 1,
                outgoing_start_sec=min(previous.source_out_sec, last_frame_start),
            )
            # 이 둘은 **1초 남짓만 읽는다.** 디코더 스레드를 넉넉히 줄 이유가 없고,
            # 주면 실제로 렌더가 통째로 죽는다 -- 컨테이너에서 실측했다.
            # 자세한 이유는 `single_thread_source_indices` 참고.
            single_thread_source_indices.add(len(source_paths))
            single_thread_source_indices.add(len(source_paths) + 1)
            source_paths.append((outgoing, False, False))
            source_paths.append((incoming, False, False))
        export_overlay_indices: dict[int, int] = {}
        for overlay_index, overlay in enumerate(composition_plan.export_overlays):
            asset_uri = str(overlay.get("asset_uri") or "")
            asset_id = str(overlay.get("asset_id") or "")
            if not asset_uri and asset_id:
                asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
            if not asset_uri:
                continue
            try:
                source = self._resolve_generic_asset_uri(project_id=project_id, asset_uri=asset_uri)
            except FinalRenderError:
                raise FinalRenderError("Exact preview export overlay source is unavailable. Restore it and retry.") from None
            if not source.is_file():
                raise FinalRenderError("Exact preview export overlay source is missing. Restore it and retry.")
            export_overlay_indices[overlay_index] = len(source_paths)
            source_paths.append((source, source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}, False))
        graph = self.build_plan_filter_graph(
            composition_plan=composition_plan, source_indices=source_indices,
            export_overlay_indices=export_overlay_indices,
            track_overlay_indices=track_overlay_indices,
            transition_source_indices=transition_source_indices,
        )
        duration = max(composition_plan.duration_sec, 0.001)
        graph += ";" + self.build_plan_audio_filter_graph(
            composition_plan=composition_plan, source_indices=source_indices,
            soundless_source_clip_ids=soundless_source_clip_ids,
        )
        video_label = "vout"
        if subtitle_file_path is not None and subtitle_ass_path is None:
            generated_ass = self.convert_legacy_subtitle_to_ass(
                subtitle_file_path=subtitle_file_path, output_dir=output_path.parent
            )
            subtitle_ass_path = generated_ass
        if subtitle_ass_path is not None:
            escaped = subtitle_ass_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
            graph += f";[vout]subtitles=filename='{escaped}'[vburned]"
            video_label = "vburned"
        sar = composition_plan.sample_aspect_ratio.replace(":", "/")
        graph += f";[{video_label}]setsar={sar},setpts=PTS-STARTPTS[vfinal]"
        video_label = "vfinal"
        threads = str(self.encoder_thread_limit())
        # 필터 스레드를 정하지 않으면 ffmpeg가 호스트 CPU 수만큼 잡고, 컨테이너의
        # 프로세스 상한(128)에 걸려 스레드 생성이 실패한다. 자세한 이유는
        # `encoder_thread_limit` 참고.
        command = [self.ffmpeg_binary, "-y", "-filter_complex_threads", threads, "-filter_threads", threads]
        for source_index, (path, is_image, should_loop) in enumerate(source_paths):
            # 디코더도 상한을 지켜야 한다. 인코더·필터만 묶으면 입력 하나마다
            # 디코더가 호스트 CPU 수(16)만큼 스레드를 잡아, 입력 6개짜리 렌더가
            # 컨테이너 프로세스 상한(128)을 넘본다. 그 압박에서 스레드 생성이
            # 조용히 실패하면 오디오 브랜치만 일찍 끝난 채 성공(0)으로 끝날 수
            # 있다 — 2026-08-16에 20초 영상에 5초 소리만 담긴 완성본이 그렇게
            # 나왔다.
            #
            # 전환 입력은 그보다 더 묶는다. 1초 남짓만 읽는 입력에 스레드를
            # 넉넉히 주면 상한을 넘겨 렌더가 통째로 죽는다.
            command += ["-threads", "1" if source_index in single_thread_source_indices else threads]
            if should_loop:
                command += ["-stream_loop", "-1"]
            if is_image:
                command += ["-loop", "1", "-framerate", str(self.video_fps)]
            seek_offset = fast_seek_offsets.get(source_index)
            if seek_offset is not None:
                command += ["-ss", str(seek_offset), "-copyts"]
            command += ["-i", str(path)]
        command += [
            "-filter_complex", graph, "-map", f"[{video_label}]", "-map", "[aout]",
            "-r", str(self.video_fps), "-c:v", "libx264", "-threads", str(self.encoder_thread_limit()),
            "-bf", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-t", str(duration),
            "-movflags", "+faststart" if proxy_profile else "+faststart",
            "-avoid_negative_ts", "disabled", "-muxpreload", "0", "-muxdelay", "0",
            "-metadata:s:v:0", f"rotate={composition_plan.rotation}",
            str(output_path),
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self._run(command)
        finally:
            if generated_ass is not None:
                generated_ass.unlink(missing_ok=True)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed rendering canonical composition: {result.stderr[-800:]}")
        # 오디오가 타임라인보다 짧게 나온 출력은 조용히 내보내지 않는다. 스레드
        # 압박에서 ffmpeg가 오디오 쪽만 일찍 끝내고도 0으로 종료한 실사례가
        # 있다(2026-08-16, 20초 영상에 5초 소리). 허용 오차는 AAC 프레임
        # 정렬을 감안한 값이다.
        audio_duration = self._probe_audio_stream_duration(output_path)
        if audio_duration is None or audio_duration + 0.75 < duration:
            measured = "missing" if audio_duration is None else f"{audio_duration:.2f}s"
            raise FinalRenderError(
                f"Rendered audio track is shorter than the timeline ({measured} < {duration:.2f}s). Retry the render."
            )
        return output_path

    def _run(self, command: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.render_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise FinalRenderError(f"'{self.ffmpeg_binary}' binary was not found. Install ffmpeg.") from exc
        except subprocess.TimeoutExpired as exc:
            raise FinalRenderError(f"ffmpeg timed out after {self.render_timeout_seconds}s.") from exc

    def convert_legacy_subtitle_to_ass(self, *, subtitle_file_path: Path, output_dir: Path) -> Path:
        """Convert session-less SRT/WebVTT-style input to the renderer's ASS input."""
        source = Path(subtitle_file_path)
        if not source.is_file():
            raise FinalRenderError("Legacy subtitle artifact is missing; regenerate subtitles before final render.")
        output_dir.mkdir(parents=True, exist_ok=True)
        ass_path = output_dir / f".legacy_subtitle_{uuid.uuid4().hex}.ass"
        result = self._run([self.ffmpeg_binary, "-y", "-i", str(source), "-f", "ass", str(ass_path)])
        if result.returncode != 0 or not ass_path.is_file():
            ass_path.unlink(missing_ok=True)
            raise FinalRenderError(f"Unable to convert legacy subtitle artifact to ASS: {result.stderr[-800:]}")
        return ass_path

    def _has_stream(self, path: Path, *, selector: str, codec_type: str, error_label: str) -> bool:
        """`selector`(`a:0`/`v:0`)의 스트림이 실제로 있는지 ffprobe에게 묻는다.

        같은 파일을 클립마다 다시 재지 않도록 경로+수정시각으로 캐시한다 --
        프로세스 하나가 수십 ms라, 클립 30개짜리 렌더가 시작도 전에 초 단위를
        먹는다.
        """
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = -1
        key = (str(path), selector, stamp)
        cached = self._stream_probe_cache.get(key)
        if cached is not None:
            return cached
        try:
            result = subprocess.run(
                [
                    self.ffprobe_binary,
                    "-v",
                    "error",
                    "-select_streams",
                    selector,
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise FinalRenderError(f"Unable to inspect {error_label}. Install/configure ffprobe.") from exc
        found = result.returncode == 0 and result.stdout.strip() == codec_type
        self._stream_probe_cache[key] = found
        return found

    def _has_audio_stream(self, path: Path) -> bool:
        """`원본 소리 살리기`가 켜진 원본에 실제로 오디오 스트림이 있는지 잰다.

        무음 B-roll(영상만 있는 원본)의 없는 스트림을 참조하면 렌더가 통째로
        막힌다. 짐작하지 말고 ffprobe에게 물어본다.
        """
        return self._has_stream(path, selector="a:0", codec_type="audio", error_label="source audio")

    def _has_visual_stream(self, path: Path) -> bool:
        """Accept non-image overlays only when ffprobe confirms a video stream."""
        return self._has_stream(path, selector="v:0", codec_type="video", error_label="overlay media")

    def rendered_audio_has_sound(self, path: Path) -> bool | None:
        """이 렌더러가 쓰는 ffmpeg로 재는 편의 메서드. 판단은 모듈 함수에 있다."""
        return rendered_audio_has_sound(path, ffmpeg_binary=self.ffmpeg_binary)

    def _probe_audio_stream_duration(self, path: Path) -> float | None:
        """출력물 '오디오 스트림'의 실제 길이.

        컨테이너(format) 길이는 영상이 길면 영상을 따라가므로, 오디오가 잘렸는지는
        스트림을 직접 봐야 한다. 실패하면 None -- 호출부가 fail-closed로 다룬다.
        """
        try:
            result = subprocess.run(
                [
                    self.ffprobe_binary,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        try:
            return float((result.stdout or "").strip())
        except ValueError:
            return None

    def _probe_media_duration(self, path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    self.ffprobe_binary,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=min(self.render_timeout_seconds, 60),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise FinalRenderError("Unable to inspect B-roll duration. Install/configure ffprobe.") from exc
        if result.returncode != 0:
            raise FinalRenderError(f"Unable to inspect B-roll duration for '{path}': {result.stderr[-800:]}")
        try:
            duration = float(result.stdout.strip())
        except ValueError as exc:
            raise FinalRenderError(f"B-roll source has no readable duration: '{path}'.") from exc
        if duration <= 0:
            raise FinalRenderError(f"B-roll source has no usable duration: '{path}'.")
        return duration

    def _resolve_narration_clip_source(
        self, *, project_id: str, timeline: dict[str, Any], clip: dict[str, Any]
    ) -> ResolvedClipSource:
        try:
            return resolve_narration_clip_source(store=self.store, project_id=project_id, timeline=timeline, clip=clip)
        except TimelineClipSourceError as exc:
            raise FinalRenderError(str(exc)) from exc

    def _resolve_broll_clip_source(self, *, project_id: str, clip: dict[str, Any]) -> ResolvedClipSource:
        try:
            return resolve_broll_clip_source(store=self.store, project_id=project_id, clip=clip)
        except (TimelineClipSourceError, KeyError, OSError, ValueError) as exc:
            raise FinalRenderError(
                f"Unable to resolve B-roll media for '{clip.get('asset_uri')}'. Re-select or re-import the asset."
            ) from exc

    def _resolve_generic_asset_uri(self, *, project_id: str, asset_uri: str) -> Path:
        try:
            return resolve_generic_asset_uri(store=self.store, project_id=project_id, asset_uri=asset_uri)
        except (TimelineClipSourceError, KeyError, OSError, ValueError) as exc:
            raise FinalRenderError(
                f"Unable to resolve media asset '{asset_uri}'. Re-select or re-import the asset."
            ) from exc

    def _extract_segment(self, *, source: ResolvedClipSource, output_path: Path, video: bool, media_controls: dict[str, Any] | None = None) -> None:
        command = [self.ffmpeg_binary, "-y"]
        if source.trim_start_sec:
            command += ["-ss", str(source.trim_start_sec)]
        if video and source.target_duration_sec is not None:
            command += ["-stream_loop", "-1"]
        command += ["-i", str(source.path)]
        output_duration_sec = source.target_duration_sec if source.target_duration_sec is not None else source.trim_duration_sec
        if output_duration_sec is not None:
            command += ["-t", str(output_duration_sec)]
        if video:
            controls = normalize_media_controls(media_controls, media_kind="broll", duration_sec=float(output_duration_sec or 0.001))
            source_start_sec = float(source.trim_start_sec or 0.0) + float(controls.get("in_sec", 0.0)) + controls["trim_start_sec"]
            if source_start_sec:
                command = [self.ffmpeg_binary, "-y", "-ss", str(source_start_sec)] + command[2:]
            if not controls["loop"]:
                command = [item for index, item in enumerate(command) if not (item == "-stream_loop" or (index and command[index - 1] == "-stream_loop"))]
            available_duration_sec = self._probe_media_duration(source.path) - source_start_sec
            if "out_sec" in controls:
                available_duration_sec = min(available_duration_sec, float(controls["out_sec"]) - source_start_sec)
            if available_duration_sec <= 0:
                raise FinalRenderError(f"B-roll trim starts after the source ends: '{source.path}'. Reduce trim_start_sec.")
            # **완성본 MP4는 이 경로로 나온다.** 그래프(`build_plan_filter_graph`)는
            # 미리보기 쪽이고, 여기를 빼먹으면 배속이 화면에만 있고 파일에는 없다 --
            # 2026-08-18에 실제 mp4의 색을 읽어 보고 알았다.
            speed = float(controls["speed"])
            # 아래 판단은 전부 **화면 시간** 기준이므로 원본 여유를 한 번 환산한다.
            available_duration_sec /= speed
            needs_padding = bool(
                output_duration_sec is not None
                and not controls["loop"]
                and float(output_duration_sec) > available_duration_sec
            )
            if needs_padding and not controls["pad"]:
                raise FinalRenderError(
                    "B-roll source is shorter than its timeline window. Enable loop or pad to preserve timeline duration."
                )
            if controls["fit"] == "crop":
                video_filter = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=increase,crop={self.video_width}:{self.video_height},setsar={self.video_sar.replace(':', '/')}"
            else:
                video_filter = f"scale={self.video_width}:{self.video_height}:force_original_aspect_ratio=decrease,pad={self.video_width}:{self.video_height}:(ow-iw)/2:(oh-ih)/2,setsar={self.video_sar.replace(':', '/')}"
            if needs_padding:
                video_filter += f",tpad=stop_mode=add:stop_duration={float(output_duration_sec) - available_duration_sec}"
            # 되감기(retime)는 **자르고 늘리기 전에** 온다. 배속 1이면 아무것도
            # 더하지 않는다 -- 안 쓰는 기능에 화질과 시간을 들이지 않는다.
            if speed != 1.0:
                video_filter = f"setpts=PTS/{speed}," + video_filter
            command += [
                "-vf",
                video_filter,
                "-r",
                str(self.video_fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
            ]
            if controls["preserve_source_audio"] and self._has_audio_stream(source.path):
                # 소리도 화면과 같은 배속이어야 입이 맞는다. 음량은 여기서만
                # 걸 수 있다 -- 이 조각이 그대로 이어붙기 때문이다.
                audio_effects = []
                if speed != 1.0:
                    audio_effects.append(_atempo_chain(speed))
                if float(controls["volume"]) != 1.0:
                    audio_effects.append(f"volume={float(controls['volume'])}")
                command += ["-map", "0:v:0", "-map", "0:a:0"]
                if audio_effects:
                    command += ["-af", ",".join(audio_effects)]
                command += ["-c:a", "aac", "-ar", "48000", "-ac", "2"]
            elif controls["preserve_source_audio"]:
                # 원본에 오디오 스트림이 아예 없다. 스트림 없는 조각을 만들면
                # concat이 **첫 조각**의 구성을 기준으로 삼아, 무음 조각이 앞에
                # 올 때 뒤 조각의 소리가 통째로 사라지거나 `[1:a]` 믹스가 막힌다.
                # 무음을 실어 조각들의 모양을 맞춘다.
                input_at = command.index(str(source.path)) + 1
                command[input_at:input_at] = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                command += ["-map", "0:v:0", "-map", "1:a", "-shortest"]
                command += ["-c:a", "aac", "-ar", "48000", "-ac", "2"]
            else:
                command += ["-an"]
        else:
            command += ["-vn"]
            if output_duration_sec is not None:
                command += ["-af", f"apad,atrim=duration={output_duration_sec}"]
            command += ["-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le"]
        command.append(str(output_path))
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed extracting segment from '{source.path}': {result.stderr[-800:]}")

    def _concat(self, *, segment_paths: list[Path], output_path: Path, work_dir: Path) -> None:
        list_path = work_dir / f"{output_path.stem}_concat_list.txt"
        list_path.write_text(
            "\n".join(f"file '{segment_path.as_posix()}'" for segment_path in segment_paths),
            encoding="utf-8",
        )
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed concatenating segments into '{output_path}': {result.stderr[-800:]}")

    def _apply_export_overlays(
        self,
        *,
        project_id: str,
        video_path: Path,
        overlays: list[dict[str, Any]],
        work_dir: Path,
        captions: list[dict[str, Any]] | None = None,
    ) -> Path:
        text_filters: list[str] = []
        image_overlays: list[tuple[Path, float, float]] = []
        for overlay in overlays:
            overlay_type = str(overlay.get("overlay_type") or "").strip().lower()
            start_sec = float(overlay.get("start_sec") or 0.0)
            end_sec = float(overlay.get("end_sec") or start_sec)
            if end_sec <= start_sec:
                continue
            if overlay_type in {"image", "image_card", "image_overlay", "visual_overlay", "hook_title"}:
                asset_uri = str(overlay.get("asset_uri") or "").strip()
                asset_id = str(overlay.get("asset_id") or "").strip()
                if not asset_uri and asset_id:
                    asset_uri = f"local://projects/{project_id}/assets/{asset_id}"
                if asset_uri:
                    image_overlays.append(
                        (self._resolve_generic_asset_uri(project_id=project_id, asset_uri=asset_uri), start_sec, end_sec)
                    )
            # 정지 도형과 아이콘. 둘 다 이어붙는 단일 필터이므로 같은 사슬에 싣는다.
            # 글줄 검사보다 앞에 있어야 한다 -- 글줄이 없는 도형 장면이 글꼴 없는
            # 환경에서 막히면 안 된다(아이콘은 자기 글꼴을 스스로 확인한다).
            text_filters.extend(
                export_overlay_shape_filters(
                    overlay, width=self.video_width, height=self.video_height,
                    start_sec=start_sec, end_sec=end_sec, font_file=self.overlay_font_file,
                )
            )
            lines = export_overlay_text_lines(overlay)
            if not lines:
                continue
            if not Path(self.overlay_font_file).is_file():
                raise FinalRenderError(
                    f"Overlay font is missing: '{self.overlay_font_file}'. Install the font or set VIDEOBOX_OVERLAY_FONT."
                )
            # 자리 잡기는 그래프 경로와 **같은 함수**를 쓴다. 여기서 따로 계산하면
            # 같은 카드가 미리보기와 완성본에서 다른 자리에 그려진다.
            text_filters.extend(
                export_overlay_text_filters(
                    lines, font_file=self.overlay_font_file, video_height=self.video_height,
                    start_sec=start_sec, end_sec=end_sec,
                    caption_band=caption_band_px(
                        captions or [], video_width=self.video_width, video_height=self.video_height,
                        start_sec=start_sec, end_sec=end_sec,
                    ),
                )
            )
        if not text_filters and not image_overlays:
            return video_path
        overlaid_path = work_dir / "broll_with_overlays.mp4"
        command = [self.ffmpeg_binary, "-y", "-i", str(video_path)]
        for image_path, _start_sec, _end_sec in image_overlays:
            command += ["-loop", "1", "-i", str(image_path)]
        current_label = "[0:v]"
        filter_parts: list[str] = []
        for index, (_image_path, start_sec, end_sec) in enumerate(image_overlays, start=1):
            next_label = f"[overlay_{index}]"
            filter_parts.append(
                f"{current_label}[{index}:v]overlay=x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2:"
                f"enable='between(t,{start_sec},{end_sec})':eof_action=repeat:shortest=1{next_label}"
            )
            current_label = next_label
        for index, text_filter in enumerate(text_filters, start=1):
            next_label = f"[text_{index}]"
            filter_parts.append(f"{current_label}{text_filter}{next_label}")
            current_label = next_label
        command += [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            current_label,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            str(overlaid_path),
        ]
        result = self._run(command)
        if result.returncode != 0:
            raise FinalRenderError(f"ffmpeg failed applying export overlays: {result.stderr[-800:]}")
        return overlaid_path

    @staticmethod
    def _legacy_overlay_inputs(timeline: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect legacy overlays and asset-backed materialized overlay clips."""
        overlays = [
            dict(item)
            for item in timeline.get("export_overlays", [])
            if isinstance(item, dict)
        ]
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict) or canonical_track_type(track.get("track_type")) != "overlay":
                continue
            for clip in track.get("clips", []):
                if not isinstance(clip, dict):
                    continue
                payload = dict(clip.get("overlay_payload") or {}) if isinstance(clip.get("overlay_payload"), dict) else {}
                for key in ("overlay_type", "asset_id", "asset_uri", "start_sec", "end_sec", "clip_id", "segment_id"):
                    if key not in payload and clip.get(key) is not None:
                        payload[key] = clip[key]
                overlays.append(payload)
        return overlays

    def render_timeline_to_mp4(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None = None,
        subtitle_ass_path: Path | None = None,
        on_progress: Callable[[int], None] | None = None,
        composition_plan: CompositionPlan | None = None,
        proxy_profile: bool = False,
    ) -> Path:
        if composition_plan is not None:
            plan_renderer = self if proxy_profile else self._replace_sharing_caches(
                video_width=composition_plan.width,
                video_height=composition_plan.height,
                video_fps=f"{composition_plan.fps_num}/{composition_plan.fps_den}",
                video_sar=composition_plan.sample_aspect_ratio,
            )
            return plan_renderer._render_composition_plan_to_mp4(
                project_id=project_id, composition_plan=composition_plan, timeline_context=timeline,
                output_path=output_path, subtitle_file_path=subtitle_file_path,
                subtitle_ass_path=subtitle_ass_path, proxy_profile=proxy_profile,
            )
        # 여기부터가 **조각 추출 + concat 경로**다. 완성본도 정확 미리보기도
        # 이쪽으로 나가지 않는다 -- 둘 다 위에서 `composition_plan`을 넘겨
        # `_render_composition_plan_to_mp4`로 간다. 장면 전환은 그 그래프에만
        # 구현돼 있다.
        #
        # **조용히 빼먹지 않는다.** 이 저장소가 가장 비싸게 배운 것이
        # "화면엔 있는데 완성본엔 없다"이고, 그 사고는 두 렌더 경로 중 한 곳만
        # 고쳐서 두 번 났다. 전환이 걸린 타임라인이 이 경로로 들어오면 여기서
        # 멈춘다 -- 전환 없는 mp4를 성공이라고 돌려주는 것보다 낫다.
        if any(
            isinstance(clip, dict) and clip.get("transition")
            for track in timeline.get("tracks", []) if isinstance(track, dict)
            and canonical_track_type(track.get("track_type")) == "broll"
            for clip in (track.get("clips") or [])
        ):
            raise FinalRenderError(
                "Scene transitions render only from the composition plan. "
                "Pass composition_plan to render this timeline."
            )
        # 색감·손떨림 보정과 눈·음소거도 **같은 이유로** 여기서 멈춘다. 이 경로의
        # `_extract_segment`는 자기 `scale/crop` 사슬을 따로 만들고 색감을 안
        # 붙이며, 트랙 상태도 안 읽는다. 전환만 막아 두고 이 둘을 열어 두면
        # 같은 사고를 셋째·넷째로 내는 것이다(2026-08-23 코드리뷰 지적).
        #
        # 손떨림 보정(2026-09-01)은 바로 그 다섯째가 될 뻔했다. `deshake`를
        # `_broll_fit_transform`에만 넣고 이 경로를 잊었는데, 그러면 화면에서
        # 켠 보정이 조용히 사라진 mp4가 나온다. **화면 사슬을 건드릴 때마다
        # 이 목록을 같이 늘려야 한다** -- 이 저장소가 이미 네 번 겪은 함정이다.
        if any(
            isinstance(clip, dict) and isinstance(clip.get("media_controls"), dict)
            and (clip["media_controls"].get("filter") or clip["media_controls"].get("stabilize"))
            for track in timeline.get("tracks", []) if isinstance(track, dict)
            for clip in (track.get("clips") or [])
        ):
            raise FinalRenderError(
                "Clip colour looks and stabilisation render only from the composition plan. "
                "Pass composition_plan to render this timeline."
            )
        if isinstance(timeline.get("track_states"), dict) and timeline["track_states"]:
            raise FinalRenderError(
                "Track hide/mute renders only from the composition plan. "
                "Pass composition_plan to render this timeline."
            )
        verify_output_sources(
            store=self.store, project_id=project_id, timeline=timeline,
            hash_cache=self._output_source_hash_cache,
        )
        # Keep extraction on the final-render path now so source/timeline
        # shapes are validated by its existing regression suite.  The proxy
        # renderer is deliberately not introduced in this task.
        inputs = self.build_final_render_inputs(
            composition_plan=composition_plan or self.extract_composition_plan(timeline=timeline)
        )
        def report_progress(percent: int) -> None:
            if on_progress is not None:
                on_progress(percent)
        narration_clips: list[dict[str, Any]] = []
        broll_clips: list[dict[str, Any]] = []
        bgm_clips: list[dict[str, Any]] = []
        sfx_clips: list[dict[str, Any]] = []
        for track in timeline.get("tracks", []):
            if not isinstance(track, dict):
                continue
            track_type = canonical_track_type(track.get("track_type"))
            clips = track.get("clips", [])
            if not isinstance(clips, list):
                continue
            valid_clips = sorted(
                (clip for clip in clips if isinstance(clip, dict)),
                key=lambda clip: float(clip.get("start_sec", 0.0)),
            )
            if track_type == "narration":
                narration_clips.extend(valid_clips)
            elif track_type == "broll":
                broll_clips.extend(valid_clips)
            elif track_type == "bgm":
                bgm_clips.extend(valid_clips)
            elif track_type == "sfx":
                sfx_clips.extend(valid_clips)

        if not narration_clips:
            raise FinalRenderError("Timeline has no narration clips to render.")
        if not broll_clips:
            raise FinalRenderError("Timeline has no broll clips to render.")

        with tempfile.TemporaryDirectory(prefix="videobox_render_") as raw_work_dir:
            work_dir = Path(raw_work_dir)

            narration_segment_paths = []
            for index, clip in enumerate(narration_clips, start=1):
                source = self._resolve_narration_clip_source(project_id=project_id, timeline=timeline, clip=clip)
                if composition_plan is not None and str(clip.get("asset_uri") or "").startswith("local://projects/"):
                    source = ResolvedClipSource(
                        path=source.path,
                        trim_start_sec=float(clip.get("source_in_sec") or 0.0),
                        trim_duration_sec=float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)),
                        target_duration_sec=float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)),
                    )
                segment_path = work_dir / f"narration_{index:03d}.wav"
                self._extract_segment(source=source, output_path=segment_path, video=False)
                narration_segment_paths.append(segment_path)
            narration_path = work_dir / "narration_full.wav"
            self._concat(segment_paths=narration_segment_paths, output_path=narration_path, work_dir=work_dir)
            report_progress(25)

            broll_segment_paths = []
            preserve_broll_source_audio = all(
                normalize_media_controls(
                    clip.get("media_controls"),
                    media_kind="broll",
                    duration_sec=max(float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0)), 0.001),
                )["preserve_source_audio"]
                for clip in broll_clips
            )
            for index, clip in enumerate(broll_clips, start=1):
                source = self._resolve_broll_clip_source(project_id=project_id, clip=clip)
                segment_path = work_dir / f"broll_{index:03d}.mp4"
                self._extract_segment(source=source, output_path=segment_path, video=True, media_controls=clip.get("media_controls") if isinstance(clip.get("media_controls"), dict) else None)
                broll_segment_paths.append(segment_path)
            video_path = work_dir / "broll_full.mp4"
            self._concat(segment_paths=broll_segment_paths, output_path=video_path, work_dir=work_dir)
            # 오버레이 재인코딩은 `-an`으로 돈다. 살려 둔 B-roll 소리는 오버레이를
            # 얹기 **전** 파일에서 가져와야 한다 -- 얹은 파일에서 `[1:a]`를 찾으면
            # 오버레이가 하나라도 있는 순간 렌더가 통째로 막힌다.
            broll_audio_source_path = video_path
            video_path = self._apply_export_overlays(
                project_id=project_id,
                video_path=video_path,
                overlays=self._legacy_overlay_inputs(timeline),
                work_dir=work_dir,
                # 자막을 실제로 **구울 때만** 그 자리를 비켜 준다. 소프트 자막
                # (`-c:s mov_text`)은 화면에 얹히지 않으므로 피할 것도 없다.
                captions=caption_segments_from_timeline(timeline) if subtitle_ass_path is not None else [],
            )
            report_progress(60)

            audio_path = narration_path
            if preserve_broll_source_audio:
                mixed_path = work_dir / "audio_with_broll_source.wav"
                command = [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(narration_path),
                    "-i",
                    str(broll_audio_source_path),
                    "-filter_complex",
                    # `normalize=0`이 **꼭 있어야 한다.** `amix`는 기본으로 입력
                    # 수만큼 나누므로, B-roll 소리를 켜면 그 장면과 아무 상관
                    # 없는 구간의 내레이션까지 6dB 내려간다 -- 완성본을 재서
                    # 찾았다(2026-08-19). 켠 사람은 소리를 **더한** 것이지
                    # 나머지를 줄인 게 아니다.
                    #
                    # 합쳐서 커지는 것은 클립별 `소리 크기`로 조절한다.
                    "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[aout]",
                    "-map",
                    "[aout]",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_s16le",
                    str(mixed_path),
                ]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing B-roll source audio: {result.stderr[-800:]}")
                audio_path = mixed_path
            if bgm_clips:
                bgm_source = self._resolve_generic_asset_uri(
                    project_id=project_id, asset_uri=str(bgm_clips[0].get("asset_uri") or "")
                )
                mixed_path = work_dir / "audio_with_bgm.wav"
                bgm_clip = bgm_clips[0]
                bgm_duration = float(bgm_clip.get("end_sec", 0.0)) - float(bgm_clip.get("start_sec", 0.0))
                bgm_controls = normalize_media_controls(bgm_clip.get("media_controls"), media_kind="audio", duration_sec=max(bgm_duration, 0.001))
                bgm_filter = f"volume={bgm_controls['gain_db']}dB"
                bgm_filter += _audio_cleanup_chain(bgm_controls)
                if bgm_controls["fade_in_sec"]:
                    bgm_filter += f",afade=t=in:st=0:d={bgm_controls['fade_in_sec']}"
                if bgm_controls["fade_out_sec"]:
                    bgm_filter += f",afade=t=out:st={max(0.0, bgm_duration - bgm_controls['fade_out_sec'])}:d={bgm_controls['fade_out_sec']}"
                # `normalize=0` -- 음악을 깔았다고 내레이션이 6dB 내려가면 안 된다.
                # 같은 함정(amix 기본 normalize=1)에 이미 두 번 걸렸다.
                mix_filter = f"[1:a]{bgm_filter}[bgm];[0:a][bgm]amix=inputs=2:duration=first:normalize=0[aout]"
                if bgm_controls["ducking"]:
                    mix_filter = f"[1:a]{bgm_filter}[bgm];[bgm][0:a]sidechaincompress=threshold=0.05:ratio=8[ducked];[0:a][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
                command = [
                    self.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(narration_path),
                    "-stream_loop",
                    "-1",
                    "-i",
                    str(bgm_source),
                    "-filter_complex",
                    mix_filter,
                    "-map",
                    "[aout]",
                    str(mixed_path),
                ]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing bgm: {result.stderr[-800:]}")
                audio_path = mixed_path
            if sfx_clips:
                mixed_path = work_dir / "audio_with_sfx.wav"
                command = [self.ffmpeg_binary, "-y", "-i", str(audio_path)]
                filter_parts = ["[0:a]anull[base]"]
                mix_inputs = "[base]"
                for index, clip in enumerate(sfx_clips, start=1):
                    source = self._resolve_generic_asset_uri(
                        project_id=project_id, asset_uri=str(clip.get("asset_uri") or "")
                    )
                    command += ["-i", str(source)]
                    start_ms = int(float(clip.get("start_sec", 0.0)) * 1000)
                    duration_sec = float(clip.get("end_sec", 0.0)) - float(clip.get("start_sec", 0.0))
                    controls = normalize_media_controls(clip.get("media_controls"), media_kind="audio", duration_sec=max(duration_sec, 0.001))
                    sfx_filter = f"[{index}:a]volume={controls['gain_db']}dB{_audio_cleanup_chain(controls)},atrim=duration={duration_sec}"
                    if controls["fade_in_sec"]:
                        sfx_filter += f",afade=t=in:st=0:d={controls['fade_in_sec']}"
                    if controls["fade_out_sec"]:
                        sfx_filter += f",afade=t=out:st={max(0.0, duration_sec - controls['fade_out_sec'])}:d={controls['fade_out_sec']}"
                    filter_parts.append(f"{sfx_filter},adelay={start_ms}|{start_ms}[sfx{index}]")
                    mix_inputs += f"[sfx{index}]"
                # `normalize=0` -- 효과음은 더한 것이지 나머지를 줄인 게 아니다.
                filter_parts.append(f"{mix_inputs}amix=inputs={len(sfx_clips) + 1}:duration=first:normalize=0[aout]")
                command += ["-filter_complex", ";".join(filter_parts), "-map", "[aout]", str(mixed_path)]
                result = self._run(command)
                if result.returncode != 0:
                    raise FinalRenderError(f"ffmpeg failed mixing sfx: {result.stderr[-800:]}")
                audio_path = mixed_path
            report_progress(80)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                self.ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
            ]
            if subtitle_file_path is not None and subtitle_ass_path is None:
                command += ["-i", str(subtitle_file_path), "-c:s", "mov_text", "-map", "2:s"]
            if subtitle_ass_path is not None:
                escaped_ass_path = subtitle_ass_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
                command += ["-vf", f"subtitles=filename='{escaped_ass_path}'"]
            command += [
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v", "libx264" if (subtitle_ass_path is not None or proxy_profile) else "copy",
                "-c:a",
                "aac",
            ]
            if proxy_profile:
                command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-metadata:s:v:0", f"rotate={inputs.composition_plan.rotation}"]
            for note in output_warning_notes(timeline):
                command += ["-metadata", f"comment={note}"]
            command += [
                "-shortest",
                str(output_path),
            ]
            result = self._run(command)
            if result.returncode != 0:
                raise FinalRenderError(f"ffmpeg failed muxing final output: {result.stderr[-800:]}")
            report_progress(100)

        return output_path


__all__ = ["FfmpegFinalRenderer", "FinalRenderError"]
