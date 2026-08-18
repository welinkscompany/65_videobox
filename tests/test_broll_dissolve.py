"""장면이 바뀔 때 부드럽게 넘어가기 -- 디졸브.

**처음에 이 저장소의 렌더러를 concat 모델로 잘못 읽었다.** 그래서 "전환을 넣으면
전체 길이가 줄고 그 뒤 모든 시각이 밀린다"고 판단했다. 실제로는 `색 캔버스 위에
각 클립을 자기 타임라인 위치에 올리는` 오버레이 모델이고, 겹침은 이미 지원한다
(`test_plan_renderer_explicitly_preserves_gaps_and_later_broll_wins_overlap`).

그래서 디졸브는 길이를 건드리지 않는다. 겹치는 구간에서 **위에 오는 클립의 투명도만**
0에서 1로 올리면 아래 클립이 비쳐 보인다. 자막·소리·재생 위치는 그대로다.
"""

from __future__ import annotations

from pathlib import Path

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_storage.local_project_store import LocalProjectStore


def _graph(tmp_path: Path, *, controls: dict) -> str:
    plan = CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720},
        "tracks": [{"track_type": "broll", "clips": [
            {"clip_id": "under", "asset_uri": "local://under", "start_sec": 0, "end_sec": 4},
            {"clip_id": "over", "asset_uri": "local://over", "start_sec": 3, "end_sec": 7, "media_controls": controls},
        ]}],
    })
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    return renderer.build_plan_filter_graph(composition_plan=plan, source_indices={"under": 1, "over": 2})


def test_a_clip_can_fade_in_over_the_one_before_it(tmp_path: Path) -> None:
    graph = _graph(tmp_path, controls={"fade_in_sec": 1.0})

    # 알파를 태워야 아래 클립이 비친다. 알파 없이 fade를 걸면 검은색으로 가라앉는다.
    assert "fade=t=in:st=0:d=1.0:alpha=1" in graph
    assert "format=yuva420p" in graph, "알파 채널이 없으면 fade의 alpha=1이 아무 일도 하지 않는다"


def test_a_clip_can_fade_out_at_its_own_end(tmp_path: Path) -> None:
    graph = _graph(tmp_path, controls={"fade_out_sec": 0.5})

    # 4초짜리 클립의 끝 0.5초에서 시작한다.
    assert "fade=t=out:st=3.5:d=0.5:alpha=1" in graph


def test_no_fade_means_no_filter_at_all(tmp_path: Path) -> None:
    """안 쓰는 사람에게 필터를 더하지 않는다. 렌더가 느려질 이유가 없다."""
    graph = _graph(tmp_path, controls={})

    assert "fade=" not in graph
    assert "yuva420p" not in graph


def test_the_total_length_does_not_move(tmp_path: Path) -> None:
    """디졸브의 요점이다 -- 길이가 바뀌면 자막도 소리도 전부 밀린다."""
    plain = _graph(tmp_path, controls={})
    dissolved = _graph(tmp_path, controls={"fade_in_sec": 1.0, "fade_out_sec": 0.5})

    assert ":d=7.0" in plain and ":d=7.0" in dissolved


# ---------------------------------------------------------------------------
# 여기부터는 **실제로 mp4를 만들어** 확인한다.
#
# 이 저장소가 가장 비싸게 배운 것이 "화면엔 있는데 완성본엔 안 나온다"이다.
# 필터 문자열만 보는 위 테스트들은 그걸 못 잡는다 -- ffmpeg가 그 필터를 거부해도
# 문자열은 멀쩡하기 때문이다.
# ---------------------------------------------------------------------------

import shutil
import subprocess

import pytest

from videobox_domain_models.assets import AssetType

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _generate(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=120)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_a_dissolve_actually_survives_into_the_rendered_mp4(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="디졸브")

    narration = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(narration)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration)

    broll = tmp_path / "broll.mp4"
    _generate(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=15", str(broll)])
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll)

    uri = f"local://projects/{project.project_id}/assets/{asset.asset_id}"
    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [
                {"asset_uri": f"local://projects/{project.project_id}/segments/seg_001", "start_sec": 0.0, "end_sec": 6.0},
            ]},
            # 두 클립을 **겹쳐** 놓고, 위 클립을 서서히 나타나게 한다. 캡컷의 디졸브다.
            {"track_type": "broll", "clips": [
                {"asset_uri": uri, "start_sec": 0.0, "end_sec": 4.0},
                {"asset_uri": uri, "start_sec": 3.0, "end_sec": 6.0, "media_controls": {"fade_in_sec": 1.0}},
            ]},
        ],
    }

    output = tmp_path / "dissolved.mp4"
    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
        project_id=project.project_id, timeline=timeline, output_path=output,
    )

    assert output.exists() and output.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(output)],
        capture_output=True, text=True, timeout=60,
    )
    # **길이가 안 움직인다.** 디졸브의 요점이고, 움직이면 자막·소리가 전부 밀린다.
    assert float(probe.stdout.strip()) == pytest.approx(6.0, abs=1.0)
