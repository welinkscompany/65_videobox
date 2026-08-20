"""아이콘 글꼴 아이콘이 **완성본 픽셀에** 실제로 찍히는지 잰다.

이 저장소는 필터 문자열만 보고 여러 번 속았다. 문자열에 `drawtext=`가 있어도
글꼴에 그 글자가 없으면 ffmpeg는 조용히 빈 상자(두부)를 그리고 성공으로 끝난다.
그래서 여기서는 **실제로 렌더한 프레임의 색 픽셀을 센다.**

렌더 경로가 둘이라는 것도 이 파일이 지킨다. `build_plan_filter_graph`(완성본이
나오는 그래프)와 `_apply_export_overlays`(legacy 경로)를 나란히 두고 같은
아이콘으로 잰다 -- 한쪽만 고쳐 놓고 닫은 적이 실제로 있었다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer, FinalRenderError
from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_ICON_FONT_SHAPES,
    bundled_icon_font_file,
)
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or bundled_icon_font_file() is None,
    reason="ffmpeg and the bundled icon font are both required to measure pixels",
)

WIDTH, HEIGHT = 320, 240
# 도형·아이콘 강조색은 0xFFD400(노랑)이다. 검은 화면 위에서 이것만 세면 된다.
_MIN_ACCENT_PIXELS = 120


def _frame_size(path: Path) -> tuple[int, int]:
    """완성본 경로와 미리보기 경로는 해상도가 다르다(미리보기는 긴 변 720).
    픽셀 수를 그대로 견주면 그 차이에 속으므로 크기를 먼저 잰다."""
    reported = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    width, height = (int(value) for value in reported.split(",")[:2])
    return width, height


def _accent_mask(path: Path, *, at_sec: float) -> tuple[bytes, int, int]:
    """강조색이 칠해진 자리를 1로 둔 지도. 픽셀 수가 아니라 **모양**을 견주려면
    이게 필요하다 -- 두부는 전부 같은 상자라 모양으로 봐야 확실히 갈린다."""
    width, height = _frame_size(path)
    frame = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        check=True, capture_output=True, timeout=60,
    ).stdout
    assert len(frame) == width * height * 3
    mask = bytes(
        1 if frame[index] > 180 and frame[index + 1] > 140 and frame[index + 2] < 100 else 0
        for index in range(0, len(frame), 3)
    )
    return mask, width, height


def _accent_pixels(path: Path, *, at_sec: float) -> int:
    mask, _width, _height = _accent_mask(path, at_sec=at_sec)
    return sum(mask)


def _accent_box(path: Path, *, at_sec: float) -> tuple[float, float, float, float]:
    """칠해진 자리의 테두리를, 화면 크기에 대한 비율로. 해상도가 달라도 견줄 수
    있어야 '같은 자리에 같은 비율로 그렸는가'를 물을 수 있다."""
    mask, width, height = _accent_mask(path, at_sec=at_sec)
    lit = [index for index, value in enumerate(mask) if value]
    assert lit, "nothing was painted"
    columns = [index % width for index in lit]
    rows = [index // width for index in lit]
    return (
        min(columns) / width, min(rows) / height,
        (max(columns) + 1) / width, (max(rows) + 1) / height,
    )


def _black_clip(path: Path, *, seconds: int = 3) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"color=c=black:s={WIDTH}x{HEIGHT}:d={seconds}", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )
    return path


def _icon_overlay(shape: str) -> dict[str, object]:
    return {
        "overlay_type": "shape_overlay",
        "shape": shape,
        "vertical": "middle",
        "horizontal": "center",
        "size": "large",
        "start_sec": 1.0,
        "end_sec": 2.0,
    }


# ---------------------------------------------------------------------------
# 경로 1: composition plan 그래프. 완성본 MP4가 나오는 경로다.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["icon_lightbulb", "icon_search", "icon_question", "icon_exclamation"])
def test_plan_path_actually_paints_the_icon_font_icon(tmp_path: Path, shape: str) -> None:
    """전구·돋보기·물음표·느낌표 -- 예전에 두부로 나와서 목록에서 뺐던 넷이다.

    같은 필터 문자열이 나와도 글꼴에 글자가 없으면 색 픽셀은 나오지 않는다.
    그러니 여기서 세는 것은 문자열이 아니라 실제로 칠해진 픽셀이다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"plan icon {shape}")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=_black_clip(tmp_path / f"{shape}-source.mp4"),
    )
    timeline = {
        "output": {"width": WIDTH, "height": HEIGHT},
        "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b", "asset_id": asset.asset_id,
            "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}",
            "start_sec": 0, "end_sec": 3,
        }]}],
        "export_overlays": [_icon_overlay(shape)],
    }
    output = tmp_path / f"{shape}-plan.mp4"

    FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT).render_exact_preview_to_mp4(
        project_id=project.project_id,
        composition_plan=CompositionPlan.from_timeline(timeline=timeline),
        timeline_context=timeline,
        output_path=output,
        subtitle_ass_path=None,
    )

    assert _accent_pixels(output, at_sec=1.5) >= _MIN_ACCENT_PIXELS
    # 시간 창 밖에서는 아무것도 그리지 않는다.
    assert _accent_pixels(output, at_sec=0.4) == 0


def test_plan_path_draws_a_different_shape_for_each_icon(tmp_path: Path) -> None:
    """두부는 전부 같은 상자다. 서로 다른 픽셀 수가 나오면 진짜 글자라는 뜻이다.

    이 검사가 없으면 '전부 그려졌다'와 '전부 같은 두부였다'를 구분하지 못한다 --
    2026-08-20에 이모지 넷이 정확히 그렇게 통과했다(같은 1930 픽셀).
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="plan icon spread")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=_black_clip(tmp_path / "spread-source.mp4"),
    )
    masks: dict[str, bytes] = {}
    for shape in sorted(SHAPE_OVERLAY_ICON_FONT_SHAPES):
        timeline = {
            "output": {"width": WIDTH, "height": HEIGHT},
            "tracks": [{"track_type": "broll", "clips": [{
                "clip_id": "b", "asset_id": asset.asset_id,
                "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}",
                "start_sec": 0, "end_sec": 3,
            }]}],
            "export_overlays": [_icon_overlay(shape)],
        }
        output = tmp_path / f"spread-{shape}.mp4"
        FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT).render_exact_preview_to_mp4(
            project_id=project.project_id,
            composition_plan=CompositionPlan.from_timeline(timeline=timeline),
            timeline_context=timeline,
            output_path=output,
            subtitle_ass_path=None,
        )
        masks[shape] = _accent_mask(output, at_sec=1.5)[0]

    empty = [shape for shape, mask in masks.items() if sum(mask) < _MIN_ACCENT_PIXELS]
    assert empty == [], f"drew nothing: {empty}"
    # 두부라면 어느 둘을 견줘도 지도가 똑같다. 잉크 양이 우연히 같을 수는 있어도
    # (오름세·내림세처럼 좌우 대칭인 한 쌍) 칠해진 자리까지 같지는 않다.
    identical = [
        (first, second)
        for index, first in enumerate(sorted(masks))
        for second in sorted(masks)[index + 1:]
        if sum(a ^ b for a, b in zip(masks[first], masks[second])) < _MIN_ACCENT_PIXELS
    ]
    assert identical == [], f"these drew the same picture: {identical}"


# ---------------------------------------------------------------------------
# 경로 2: legacy `_apply_export_overlays`. 같은 아이콘을 같은 자리에 그려야 한다.
# ---------------------------------------------------------------------------


def test_legacy_path_actually_paints_the_icon_font_icon(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT)

    overlaid = renderer._apply_export_overlays(
        project_id="project_001",
        video_path=_black_clip(tmp_path / "legacy-source.mp4"),
        overlays=[_icon_overlay("icon_lightbulb")],
        work_dir=tmp_path,
    )

    assert _accent_pixels(overlaid, at_sec=1.5) >= _MIN_ACCENT_PIXELS
    assert _accent_pixels(overlaid, at_sec=0.4) == 0


def test_both_paths_put_the_same_icon_in_the_same_place(tmp_path: Path) -> None:
    """경로마다 따로 계산하면 같은 표시가 다른 자리에 그려진다. 실제로 겪은 함정이다.

    두 경로는 해상도가 다르다 -- 미리보기는 긴 변을 720으로 맞춘다. 그래서
    픽셀 수가 아니라 **화면에 대한 비율**로 견준다. 크기 프리셋 자체가 화면
    크기에 대한 비율이므로, 그것이 지켜졌는지 묻는 것이 곧 맞는 질문이다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="both paths")
    source = _black_clip(tmp_path / "both-source.mp4")
    asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source
    )
    overlay = _icon_overlay("icon_search")
    timeline = {
        "output": {"width": WIDTH, "height": HEIGHT},
        "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b", "asset_id": asset.asset_id,
            "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}",
            "start_sec": 0, "end_sec": 3,
        }]}],
        "export_overlays": [overlay],
    }
    renderer = FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT)
    plan_output = tmp_path / "both-plan.mp4"
    renderer.render_exact_preview_to_mp4(
        project_id=project.project_id,
        composition_plan=CompositionPlan.from_timeline(timeline=timeline),
        timeline_context=timeline,
        output_path=plan_output,
        subtitle_ass_path=None,
    )
    legacy_output = renderer._apply_export_overlays(
        project_id=project.project_id, video_path=source, overlays=[overlay], work_dir=tmp_path
    )

    assert _accent_pixels(plan_output, at_sec=1.5) >= _MIN_ACCENT_PIXELS
    assert _accent_pixels(legacy_output, at_sec=1.5) >= _MIN_ACCENT_PIXELS
    plan_box = _accent_box(plan_output, at_sec=1.5)
    legacy_box = _accent_box(legacy_output, at_sec=1.5)

    assert all(abs(a - b) < 0.04 for a, b in zip(plan_box, legacy_box)), (plan_box, legacy_box)
    # 가운데에 그리라고 했으니 실제로 가운데여야 한다. 자리 계산이 한쪽에서만
    # 틀어지면 위 비교만으로는 둘 다 틀린 경우를 못 잡는다.
    for box in (plan_box, legacy_box):
        assert abs((box[0] + box[2]) / 2 - 0.5) < 0.04, box
        assert abs((box[1] + box[3]) / 2 - 0.5) < 0.04, box


def test_an_icon_font_icon_stops_the_render_when_the_font_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """글꼴이 없으면 빈 상자를 그리느니 멈춘다. 새 글꼴에도 같은 장치가 걸린다."""
    import videobox_core_engine.overlay_shapes as overlay_shapes

    monkeypatch.setattr(overlay_shapes, "ICON_FONT_FILES", (str(tmp_path / "absent.ttf"),))
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT)

    with pytest.raises(FinalRenderError, match="(?i)icon"):
        renderer._apply_export_overlays(
            project_id="project_001",
            video_path=_black_clip(tmp_path / "blocked.mp4"),
            overlays=[_icon_overlay("icon_lightbulb")],
            work_dir=tmp_path,
        )
