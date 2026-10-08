"""투명 모션 오버레이(VP9 알파 webm)가 완성본·미리보기에서 투명한 채로 남는가 -- Task 9, 2026-10-08.

ffmpeg는 webm을 기본 디코더로 열면 알파를 버린다(저장된 색만 남는다).
`libvpx-vp9` 디코더를 지정해야 알파가 산다. 그래서 미리보기(브라우저)는 투명한데
완성본에는 바탕이 칠해진 상자가 나오는 어긋남이 생긴다. 실제 ffmpeg로 화소를 잰다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.editing_session import build_editing_session, update_segment_image_overlay
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg가 있어야 잰다")


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr


def _alpha_webm(path: Path) -> None:
    """가운데만 불투명 빨강, 나머지는 완전 투명(저장된 색은 흰색). 알파를 버리면 모서리가 하얗게 나온다."""
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white@0.0:s=320x240:r=15:d=4,format=yuva420p",
        "-vf", "drawbox=x=110:y=80:w=100:h=80:color=red@1.0:t=fill:replace=1",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(path),
    ])


def _render(tmp_path: Path, *, preview: bool = False) -> Path:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="transparent overlay must stay transparent")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_file)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll_file = tmp_path / "black_broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=4", str(broll_file)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    webm_file = tmp_path / "card.webm"
    _alpha_webm(webm_file)
    webm_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=webm_file)
    uri = lambda a: f"local://projects/{project.project_id}/assets/{a.asset_id}"  # noqa: E731
    bounds = [("scene-before", 0.0, 1.0), ("scene-overlay", 1.0, 3.0), ("scene-after", 3.0, 4.0)]
    source_timeline = {
        "project_id": project.project_id,
        "timeline_id": "timeline_alpha_overlay",
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [{"segment_id": s, "asset_uri": uri(narration_asset), "start_sec": a, "end_sec": b} for s, a, b in bounds]},
            {"track_type": "broll", "clips": [{"segment_id": s, "asset_uri": uri(broll_asset), "start_sec": a, "end_sec": b} for s, a, b in bounds]},
        ],
    }
    session = build_editing_session(
        project_id=project.project_id,
        timeline=source_timeline,
        segments=[{"segment_id": s, "text": s, "start_sec": a, "end_sec": b} for s, a, b in bounds],
    )
    session = update_segment_image_overlay(session=session, segment_id="scene-overlay", asset_id=webm_asset.asset_id, text="")
    timeline = materialize_editing_session_timeline(timeline=source_timeline, editing_session=session, project_id=project.project_id)
    output_path = tmp_path / "out.mp4"
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15)
    plan = renderer.extract_composition_plan(timeline=timeline)
    if preview:
        renderer.render_exact_preview_to_mp4(
            project_id=project.project_id, composition_plan=plan, timeline_context=timeline,
            output_path=output_path, subtitle_ass_path=None,
        )
    else:
        renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=output_path, composition_plan=plan)
    return output_path


def _pixels(output_path: Path, tmp_path: Path) -> tuple[tuple[int, ...], tuple[int, ...]]:
    from PIL import Image

    frame = tmp_path / "frame.png"
    _generate(["ffmpeg", "-y", "-ss", "1.5", "-i", str(output_path), "-frames:v", "1", str(frame)])
    image = Image.open(frame).convert("RGB")
    w, h = image.size
    # 출력은 계획의 크기(세로 1080x1920)이고 320x240 카드는 폭에 맞춰 가운데에 놓인다.
    # 그래서 '투명 자리'는 화면 모서리(바깥 여백, 어차피 검정)가 아니라 카드 안쪽 왼쪽 가운데에서 잰다.
    return image.getpixel((w // 10, h // 2)), image.getpixel((w // 2, h // 2))


def test_a_transparent_motion_overlay_keeps_its_transparency_in_the_final_render(tmp_path: Path) -> None:
    corner, center = _pixels(_render(tmp_path), tmp_path)
    assert max(corner) < 40, f"투명 자리에 바탕이 칠해졌다: {corner}"
    assert center[0] > 150 and center[1] < 90, f"불투명한 가운데가 사라졌다: {center}"


def test_a_transparent_motion_overlay_keeps_its_transparency_in_the_exact_preview(tmp_path: Path) -> None:
    corner, center = _pixels(_render(tmp_path, preview=True), tmp_path)
    assert max(corner) < 40, f"미리보기에서 투명 자리에 바탕이 칠해졌다: {corner}"
    assert center[0] > 150 and center[1] < 90, f"미리보기에서 불투명한 가운데가 사라졌다: {center}"


def test_an_opaque_video_overlay_is_opened_the_old_way(tmp_path: Path) -> None:
    """mp4(알파 없음)에는 디코더를 강제하지 않는다 -- VP8·H.264에 libvpx-vp9를 걸면 렌더가 죽는다."""
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    clip = tmp_path / "plain.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=15:d=1", str(clip)])
    alpha = tmp_path / "alpha.webm"
    _alpha_webm(alpha)
    assert renderer._is_vp9_with_alpha(clip) is False
    assert renderer._is_vp9_with_alpha(alpha) is True
