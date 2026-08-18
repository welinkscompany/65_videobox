"""화면에 있는 `재생 속도`·`소리 크기`가 실제 결과에 닿는지.

2026-08-18에 배선을 추적해 보니 두 입력이 **눌리는데 무시되고 있었다.**
inspector에 필드가 있고 저장도 성공하는데, `normalize_media_controls()`가
broll 경로에서 두 값을 조용히 버렸고 렌더러에도 해당 필터가 없었다.
API 응답 모델에는 필드가 있어서 더 헷갈렸다 -- 기능이 없는 것보다 나쁘다.

여기 있는 테스트는 세 층을 각각 잡는다: 정규화가 값을 지키는가,
합성 계획이 배속만큼 소스를 더 먹는가, 렌더러가 필터를 내는가.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_storage.local_project_store import LocalProjectStore


def _broll_timeline(controls: dict[str, object], *, end_sec: float = 4.0) -> dict[str, object]:
    return {
        "output": {"width": 320, "height": 240},
        "tracks": [
            {
                "track_type": "broll",
                "clips": [
                    {
                        "clip_id": "b1",
                        "asset_uri": "file:///broll.mp4",
                        "start_sec": 0.0,
                        "end_sec": end_sec,
                        "media_controls": controls,
                    }
                ],
            }
        ],
    }


def test_normalized_broll_controls_keep_the_speed_and_volume_the_creator_typed() -> None:
    controls = normalize_media_controls(
        {"speed": 2.0, "volume": 0.5},
        media_kind="broll",
        duration_sec=4.0,
    )

    assert controls["speed"] == 2.0
    assert controls["volume"] == 0.5


def test_untouched_broll_controls_default_to_normal_speed_and_loudness() -> None:
    controls = normalize_media_controls({}, media_kind="broll", duration_sec=4.0)

    assert controls["speed"] == 1.0
    assert controls["volume"] == 1.0


@pytest.mark.parametrize(
    ("controls", "message"),
    [
        ({"speed": 0.0}, "speed"),
        ({"speed": -1.0}, "speed"),
        ({"speed": 8.0}, "speed"),
        ({"volume": -0.5}, "volume"),
        ({"volume": 4.0}, "volume"),
    ],
)
def test_broll_speed_and_volume_outside_the_editable_range_are_refused(
    controls: dict[str, object], message: str
) -> None:
    # 화면 입력이 허용하는 범위(속도 0.25~4, 소리 0~2)와 같은 경계를 쓴다.
    # 넓게 받아 두면 화면에서 못 만드는 값이 저장돼 렌더러에서 터진다.
    with pytest.raises(ValueError, match=message):
        normalize_media_controls(controls, media_kind="broll", duration_sec=4.0)


def test_nonfinite_speed_and_volume_use_the_same_stable_error() -> None:
    for controls in ({"speed": float("nan")}, {"volume": float("inf")}):
        with pytest.raises(ValueError, match="media_controls_invalid_number"):
            normalize_media_controls(controls, media_kind="broll", duration_sec=4.0)


def test_double_speed_broll_reads_twice_as_much_source_for_the_same_timeline_window() -> None:
    # 2배속으로 4초를 채우려면 원본 8초가 필요하다. 예전처럼 4초만 읽으면
    # 절반만 빨리 지나가고 뒤 2초가 비었다.
    plan = CompositionPlan.from_timeline(timeline=_broll_timeline({"speed": 2.0}))

    item = next(item for item in plan.items if item.track_type == "broll")
    assert item.source_out_sec - item.source_in_sec == pytest.approx(8.0)


def test_half_speed_broll_reads_half_the_source_for_the_same_timeline_window() -> None:
    plan = CompositionPlan.from_timeline(timeline=_broll_timeline({"speed": 0.5}))

    item = next(item for item in plan.items if item.track_type == "broll")
    assert item.source_out_sec - item.source_in_sec == pytest.approx(2.0)


def test_a_source_window_that_only_fills_the_window_once_sped_up_is_not_called_short() -> None:
    # 원본 4초를 0.5배속으로 늘리면 타임라인 8초를 채운다. 배속을 무시하고
    # 재면 "원본이 모자라다"고 잘못 막는다.
    plan = CompositionPlan.from_timeline(
        timeline=_broll_timeline({"speed": 0.5, "loop": False, "in_sec": 0.0, "out_sec": 4.0}, end_sec=8.0)
    )

    item = next(item for item in plan.items if item.track_type == "broll")
    assert item.end_sec - item.start_sec == pytest.approx(8.0)


def test_the_video_graph_retimes_a_sped_up_broll(tmp_path: Path) -> None:
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=320, video_height=240)
    plan = CompositionPlan.from_timeline(timeline=_broll_timeline({"speed": 2.0}))

    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={"b1": 0})

    assert "setpts=(PTS-STARTPTS)/2.0" in graph


def test_the_video_graph_leaves_normal_speed_clips_untouched(tmp_path: Path) -> None:
    # 안 쓰는 기능에 필터를 더하지 않는다. 배속 1은 예전 그래프 그대로여야
    # 한다 -- 필터를 하나 더 태울 때마다 화질과 시간이 든다.
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=320, video_height=240)
    plan = CompositionPlan.from_timeline(timeline=_broll_timeline({}))

    graph = renderer.build_plan_filter_graph(composition_plan=plan, source_indices={"b1": 0})

    assert "/1.0" not in graph
    assert "setpts=PTS-STARTPTS" in graph


def test_the_audio_graph_retimes_and_levels_opted_in_broll_sound(tmp_path: Path) -> None:
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=320, video_height=240)
    plan = CompositionPlan.from_timeline(
        timeline=_broll_timeline({"speed": 2.0, "volume": 0.5, "preserve_source_audio": True})
    )

    graph = renderer.build_plan_audio_filter_graph(composition_plan=plan, source_indices={"b1": 0})

    assert "atempo=2.0" in graph
    assert "volume=0.5" in graph


def test_extreme_speeds_are_split_into_atempo_steps_ffmpeg_actually_accepts(tmp_path: Path) -> None:
    # atempo는 한 번에 0.5~2.0배만 받는다. 4배를 그대로 주면 ffmpeg가 거절해
    # 렌더가 통째로 실패한다 -- 나눠서 태워야 한다.
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=320, video_height=240)
    plan = CompositionPlan.from_timeline(
        timeline=_broll_timeline({"speed": 4.0, "preserve_source_audio": True, "loop": True})
    )

    graph = renderer.build_plan_audio_filter_graph(composition_plan=plan, source_indices={"b1": 0})

    assert "atempo=2.0,atempo=2.0" in graph
    assert "atempo=4.0" not in graph


@pytest.mark.skipif(
    not __import__("shutil").which("ffmpeg") or not __import__("shutil").which("ffprobe"),
    reason="ffmpeg/ffprobe not installed on this machine",
)
def test_a_sped_up_broll_actually_shows_a_later_moment_in_the_real_mp4(tmp_path: Path) -> None:
    """그래프가 아니라 **나온 파일**로 확인한다.

    이 저장소가 비싸게 배운 것: 필터 문자열이 맞아도 결과가 틀릴 수 있다.
    원본을 1초마다 색이 바뀌게(빨강·초록·파랑·빨강) 만들어 두고, 2배속으로
    절반 길이에 넣었을 때 **네 색이 전부 들어왔는지**를 본다.

    한 시각을 찍어 비교하지 않는다. `setpts` 뒤에 `-r`로 프레임을 다시 고르면
    경계가 한두 프레임 밀리는데, 그건 배속이 맞는지와 상관없는 흔들림이다.
    실제로 처음에 0.5초 한 점을 찍었다가 경계에 걸려 "배속이 안 걸렸다"고
    잘못 읽었다. 순서를 보면 그 흔들림에 흔들리지 않는다.
    """
    import subprocess

    from videobox_domain_models.assets import AssetType

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="B-roll speed end to end")
    narration_file = tmp_path / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:a", "pcm_s16le", str(narration_file)],
        check=True, capture_output=True, timeout=60,
    )
    # 0~1초 빨강, 1~2초 초록, 2~3초 파랑, 3~4초 빨강.
    broll_file = tmp_path / "colour-clock.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=15:d=1",
            "-f", "lavfi", "-i", "color=c=lime:s=320x240:r=15:d=1",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=15:d=1",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:r=15:d=1",
            "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(broll_file),
        ],
        check=True, capture_output=True, timeout=120,
    )
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    output = tmp_path / "sped-up.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
        project_id=project.project_id,
        output_path=output,
        timeline={
            "narration_source_uri": narration.storage_uri,
            "tracks": [
                {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
                {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"speed": 2.0, "loop": False}}]},
            ],
        },
    )

    def colour_bands(path: Path) -> list[str]:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            capture_output=True, timeout=120, check=True,
        ).stdout
        frame_size = 320 * 240 * 3
        middle = frame_size // 2 // 3 * 3
        bands: list[str] = []
        for index in range(len(raw) // frame_size):
            frame = raw[index * frame_size:(index + 1) * frame_size]
            red, green, blue = frame[middle], frame[middle + 1], frame[middle + 2]
            colour = "red" if red > max(green, blue) else "green" if green > blue else "blue"
            if not bands or bands[-1] != colour:
                bands.append(colour)
        return bands

    # 원본 4초가 통째로 타임라인 2초 안에 들어왔다는 뜻이다. 배속을 무시하면
    # 앞 2초만 재생돼 빨강·초록 둘로 끝난다.
    assert colour_bands(output) == ["red", "green", "blue", "red"]
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(output)],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout.strip()
    assert float(duration) == pytest.approx(2.0, abs=0.1)


@pytest.mark.skipif(
    not __import__("shutil").which("ffmpeg") or not __import__("shutil").which("ffprobe"),
    reason="ffmpeg/ffprobe not installed on this machine",
)
def test_broll_volume_actually_changes_how_loud_the_finished_file_is(tmp_path: Path) -> None:
    """`소리 크기`가 완성본의 실제 음량을 바꾸는지.

    2026-08-18에 배속을 렌더러까지 이어 놓고도 음량은 **여전히 결과에 닿지
    않았다.** 음량은 그 클립의 자체 소리를 살려 둘 때만 섞이는데, 그걸 켜는
    자리가 화면에 없었기 때문이다. 이제 켤 수 있으니, 켜고 줄이면 실제로
    조용해지는지를 파일에서 잰다.

    길이가 아니라 **음량으로** 잰다 -- 이 저장소가 소리 문제를 길이로 재다가
    무음 완성본을 내보낸 적이 있다.
    """
    import subprocess

    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs
    from videobox_domain_models.assets import AssetType

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="B-roll volume end to end")
    narration_file = tmp_path / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:a", "pcm_s16le", str(narration_file)],
        check=True, capture_output=True, timeout=60,
    )
    # 소리가 실린 B-roll. 내레이션은 무음이라 완성본의 소리는 전부 여기서 온다.
    broll_file = tmp_path / "loud-broll.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=teal:s=320x240:r=15:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(broll_file),
        ],
        check=True, capture_output=True, timeout=120,
    )
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)

    def render(volume: float, name: str) -> Path:
        output = tmp_path / name
        FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
            project_id=project.project_id,
            output_path=output,
            timeline={
                "narration_source_uri": narration.storage_uri,
                "tracks": [
                    {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
                    {"track_type": "broll", "clips": [{
                        "asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 2.0,
                        "media_controls": {"preserve_source_audio": True, "loop": False, "volume": volume},
                    }]},
                ],
            },
        )
        return output

    loud = probe_audio_peak_dbfs(render(1.0, "loud.mp4"))
    quiet = probe_audio_peak_dbfs(render(0.25, "quiet.mp4"))

    assert loud is not None and quiet is not None
    # 4분의 1로 줄이면 약 12dB 낮아진다. 측정 오차를 감안해 6dB만 요구한다.
    assert quiet < loud - 6
