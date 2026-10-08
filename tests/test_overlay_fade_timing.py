"""얹은 그림·투명 영상의 나타나기/사라지기가 장면이 0초가 아닌 곳에서도 제때 걸리는가 -- 2026-10-08.

예전에는 `fade`가 0초에서 시작하는 얹은 그림 줄기 위에서 **타임라인 시각**(`st=12`)으로 돌았다.
장면이 12초에 시작하면 그림 안의 12초를 찾아 영영 안 나타났다. 실제 ffmpeg로 화소를 잰다.
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

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg가 있어야 잰다")
SCENE = 3.0  # 얹은 장면 길이. 나타나기/사라지기 창은 0.4초(길이의 3분의 1 이하).


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def _render_preview(tmp_path: Path, *, kind: str, start: float) -> Path:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="overlay fade timing")
    total = start + SCENE + 1.0
    narration = tmp_path / "n.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={total}", str(narration)])
    n_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration)
    broll = tmp_path / "b.mp4"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s=320x240:r=15:d={total}", str(broll)])
    b_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll)
    if kind == "webm":
        card = tmp_path / "card.webm"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=red@1.0:s=320x240:r=15:d={SCENE},format=yuva420p",
              "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(card)])
        o_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=card)
    else:
        card = tmp_path / "card.png"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240", "-frames:v", "1", str(card)])
        o_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=card)
    uri = lambda a: f"local://projects/{project.project_id}/assets/{a.asset_id}"  # noqa: E731
    bounds = [("scene-before", 0.0, start), ("scene-overlay", start, start + SCENE), ("scene-after", start + SCENE, total)]
    bounds = [b for b in bounds if b[2] > b[1]]
    source = {
        "project_id": project.project_id, "timeline_id": "timeline_fade", "narration_source_uri": n_asset.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [{"segment_id": s, "asset_uri": uri(n_asset), "start_sec": a, "end_sec": b} for s, a, b in bounds]},
            {"track_type": "broll", "clips": [{"segment_id": s, "asset_uri": uri(b_asset), "start_sec": a, "end_sec": b} for s, a, b in bounds]},
        ],
    }
    session = build_editing_session(project_id=project.project_id, timeline=source,
                                    segments=[{"segment_id": s, "text": s, "start_sec": a, "end_sec": b} for s, a, b in bounds])
    session = update_segment_image_overlay(session=session, segment_id="scene-overlay", asset_id=o_asset.asset_id, text="", motion="fade_in_out")
    timeline = materialize_editing_session_timeline(timeline=source, editing_session=session, project_id=project.project_id)
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15)
    plan = renderer.extract_composition_plan(timeline=timeline)
    out = tmp_path / "out.mp4"
    renderer.render_exact_preview_to_mp4(project_id=project.project_id, composition_plan=plan, timeline_context=timeline,
                                         output_path=out, subtitle_ass_path=None)
    return out


def _red_at(video: Path, t: float, tmp_path: Path) -> int:
    from PIL import Image

    frame = tmp_path / f"f_{t:.2f}.png"
    _run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(frame)])
    image = Image.open(frame).convert("RGB")
    return image.getpixel((image.size[0] // 2, image.size[1] // 2))[0]


@pytest.mark.parametrize("kind", ["webm", "image"])
@pytest.mark.parametrize("start", [1.0, 12.0])
def test_fade_in_and_out_follow_the_scene_not_the_clock(tmp_path: Path, kind: str, start: float) -> None:
    video = _render_preview(tmp_path, kind=kind, start=start)
    end = start + SCENE
    assert _red_at(video, start - 0.3, tmp_path) < 20, "장면 전에는 바탕만 보여야 한다"
    early = _red_at(video, start + 0.1, tmp_path)
    assert 10 < early < 170, f"나타나는 중이어야 한다(반쯤 투명): {early}"
    assert _red_at(video, start + 1.5, tmp_path) > 220, "가운데는 또렷해야 한다"
    late = _red_at(video, end - 0.1, tmp_path)
    assert 10 < late < 170, f"사라지는 중이어야 한다(반쯤 투명): {late}"
