"""캡컷 대조로 들어온 조정 항목이 **완성본 파일에 실제로 닿는지** 잰다.

화면에 스위치가 있고 저장이 되는 것과, 그것이 나온 mp4를 바꾸는 것은 다르다.
이 저장소는 배속을 렌더러까지 이어 놓고도 결과가 그대로였던 적이 있고
(2026-08-18), 손떨림 보정을 렌더 경로 **둘 중 하나에만** 붙여 둔 적도 있다
(2026-09-01). 둘 다 그래프 문자열만 봤으면 통과했을 결함이다.

그래서 여기서는 필터 이름이 아니라 **나온 파일의 픽셀과 소리**를 잰다.

느리다(ffmpeg를 여러 번 돌린다). 그래도 이 여섯은 렌더에 닿는 기능이라
실물로 재는 것 말고는 "된다"고 말할 근거가 없다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")

WIDTH, HEIGHT, FPS = 320, 240, 15


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True, timeout=180)


def _silence(path: Path, seconds: float = 2.0) -> Path:
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds), "-c:a", "pcm_s16le", str(path))
    return path


def _split_picture(path: Path) -> Path:
    """왼쪽 절반 빨강, 오른쪽 절반 파랑. 화면이 어디로 갔는지 한 점만 봐도 안다."""
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=red:s={WIDTH // 2}x{HEIGHT}:r={FPS}:d=2",
        "-f", "lavfi", "-i", f"color=c=blue:s={WIDTH // 2}x{HEIGHT}:r={FPS}:d=2",
        "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    )
    return path


def _noisy_picture(path: Path) -> Path:
    """알갱이가 잔뜩인 화면. 노이즈 제거가 실제로 무언가 할 대상이 있어야 한다."""
    _ffmpeg(
        "-f", "lavfi", "-i", f"nullsrc=s={WIDTH}x{HEIGHT}:r={FPS}:d=2",
        "-vf", "geq=random(1)*255:128:128",
        "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", str(path),
    )
    return path


def _quiet_tone(path: Path) -> Path:
    """작게 녹음된 소리. 음량 맞추기가 실제로 올릴 여지가 있어야 한다."""
    _ffmpeg(
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
        "-af", "volume=0.05", "-c:a", "pcm_s16le", str(path),
    )
    return path


def _first_frame_pixels(path: Path) -> bytes:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, timeout=180, check=True,
    ).stdout
    return raw[: WIDTH * HEIGHT * 3]


def _colour_at(frame: bytes, x: int, y: int) -> str:
    offset = (y * WIDTH + x) * 3
    red, green, blue = frame[offset], frame[offset + 1], frame[offset + 2]
    if max(red, green, blue) < 60:
        return "black"
    if red > blue + 40:
        return "red"
    if blue > red + 40:
        return "blue"
    return "other"


def _audio_bytes(path: Path) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-ac", "2", "-ar", "48000", "pipe:1"],
        capture_output=True, timeout=180, check=True,
    ).stdout


def _render(
    *, store: LocalProjectStore, project_id: str, narration_uri: str, tracks: list[dict], output: Path,
) -> Path:
    timeline = {
        "project_id": project_id,
        "narration_source_uri": narration_uri,
        "output": {"width": WIDTH, "height": HEIGHT},
        "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "narration", "asset_uri": narration_uri, "start_sec": 0.0, "end_sec": 2.0}]},
            *tracks,
        ],
    }
    # **composition plan 경로로 낸다.** legacy 경로는 이 기능들을 일부러 거절하고
    # (`_extract_segment`가 자기 사슬을 따로 만들기 때문) 완성본도 이 경로로 나온다.
    FfmpegFinalRenderer(store=store, video_width=WIDTH, video_height=HEIGHT, video_fps=FPS).render_timeline_to_mp4(
        project_id=project_id,
        timeline=timeline,
        output_path=output,
        composition_plan=CompositionPlan.from_timeline(timeline=timeline),
    )
    assert output.exists() and output.stat().st_size > 0, "완성본이 아예 안 나왔다"
    return output


def _broll_track(asset_uri: str, controls: dict) -> dict:
    return {"track_type": "broll", "clips": [{
        "clip_id": "broll", "asset_uri": asset_uri, "start_sec": 0.0, "end_sec": 2.0,
        "media_controls": {"loop": False, **controls},
    }]}


@pytest.fixture()
def picture_project(tmp_path: Path):
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="capcut controls reach the file")
    narration = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=_silence(tmp_path / "silence.wav")
    )
    broll = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=_split_picture(tmp_path / "split.mp4")
    )
    return store, project.project_id, narration.storage_uri, broll.storage_uri


def test_transform_actually_moves_the_picture_in_the_finished_file(picture_project, tmp_path: Path) -> None:
    """확대·위치·회전이 나온 파일의 픽셀을 바꾸는지.

    왼쪽 빨강 / 오른쪽 파랑을 넣고 **두 점만 본다.** 그림이 어디로 갔는지는
    그 두 점으로 충분하고, 사람이 읽어도 틀렸는지 바로 안다.
    """
    store, project_id, narration_uri, broll_uri = picture_project
    left, right = (WIDTH // 4, HEIGHT // 2), (WIDTH * 3 // 4, HEIGHT // 2)

    def colours(controls: dict, name: str) -> tuple[str, str]:
        frame = _first_frame_pixels(_render(
            store=store, project_id=project_id, narration_uri=narration_uri,
            tracks=[_broll_track(broll_uri, controls)], output=tmp_path / name,
        ))
        return _colour_at(frame, *left), _colour_at(frame, *right)

    assert colours({}, "plain.mp4") == ("red", "blue"), "손대지 않은 화면부터 기대와 다르다"
    # 반 바퀴 돌리면 좌우가 그대로 뒤집힌다. 경계에서 재지 않으므로 애매하지 않다.
    assert colours({"rotation_deg": 180.0}, "rotated.mp4") == ("blue", "red")
    # 반 화면만큼 오른쪽으로 밀면 왼쪽에 빈자리가 생긴다. **이걸 못 잡으면
    # `crop` 위치가 화면 안으로 당겨진 것이다** -- 값은 저장되는데 그림은
    # 그대로인 상태이고, 2026-09-01에 실제로 한 번 그랬다.
    assert colours({"position_x_percent": 50.0}, "panned.mp4")[0] == "black"
    # 줄이면 그림이 가운데로 모이고 가장자리가 빈다. **가장자리를 재는 점은
    # 따로 잡는다** -- 위의 `left`(화면 1/4 지점, x=80)는 절반으로 줄인 그림의
    # 왼쪽 끝과 정확히 겹쳐서, 제품이 맞게 동작해도 빨강이 잡힌다. 경계에서
    # 재면 무엇을 재는지 모르는 시험이 된다.
    shrunk = _first_frame_pixels(_render(
        store=store, project_id=project_id, narration_uri=narration_uri,
        tracks=[_broll_track(broll_uri, {"zoom": 0.5})], output=tmp_path / "shrunk.mp4",
    ))
    assert _colour_at(shrunk, WIDTH // 16, HEIGHT // 2) == "black"
    # 가운데는 그대로 그림이다 -- 줄인 것이지 지운 것이 아니다.
    assert _colour_at(shrunk, WIDTH // 2 - 20, HEIGHT // 2) == "red"


def test_picture_noise_reduction_and_stabilisation_change_a_grainy_finished_file(tmp_path: Path) -> None:
    """`hqdn3d`·`deshake`가 완성본까지 오는지.

    평평한 색 화면에는 둘 다 할 일이 없어 결과가 같다 -- 그래서 **알갱이가 있는
    원본**으로 잰다. 이 시험이 잡으려는 것은 필터 이름이 아니라 "렌더 경로 둘 중
    하나에만 붙어 있는" 상태다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="grainy source")
    narration = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=_silence(tmp_path / "silence.wav")
    )
    broll = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=_noisy_picture(tmp_path / "noise.mp4")
    )

    def frame(controls: dict, name: str) -> bytes:
        return _first_frame_pixels(_render(
            store=store, project_id=project.project_id, narration_uri=narration.storage_uri,
            tracks=[_broll_track(broll.storage_uri, controls)], output=tmp_path / name,
        ))

    plain = frame({}, "grain-plain.mp4")
    assert frame({"reduce_noise": True}, "grain-denoised.mp4") != plain, "노이즈 제거가 완성본에 안 닿았다"
    assert frame({"stabilize": True}, "grain-stabilised.mp4") != plain, "손떨림 보정이 완성본에 안 닿았다"


def test_loudness_and_denoise_reach_the_background_music_in_the_finished_file(tmp_path: Path) -> None:
    """`loudnorm`·`afftdn`이 완성본의 소리를 바꾸는지.

    **길이가 아니라 소리로 잰다** -- 이 저장소는 소리 문제를 길이로 재다가
    무음 완성본을 내보낸 적이 있다. 작게 녹음된 소리를 넣고, 음량 맞추기를 켜면
    실제로 커지는지 본다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="quiet music")
    narration = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=_silence(tmp_path / "silence.wav")
    )
    music = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BGM, source_path=_quiet_tone(tmp_path / "quiet.wav")
    )

    def render(controls: dict, name: str) -> Path:
        return _render(
            store=store, project_id=project.project_id, narration_uri=narration.storage_uri,
            tracks=[{"track_type": "bgm", "clips": [{
                "clip_id": "bgm", "asset_uri": music.storage_uri, "start_sec": 0.0, "end_sec": 2.0,
                "media_controls": controls,
            }]}],
            output=tmp_path / name,
        )

    plain = render({}, "quiet-plain.mp4")
    normalized = render({"normalize_loudness": True}, "quiet-normalized.mp4")

    quiet_peak = probe_audio_peak_dbfs(plain)
    loud_peak = probe_audio_peak_dbfs(normalized)
    assert quiet_peak is not None and loud_peak is not None, "완성본에서 음량을 못 읽었다"
    # -16 LUFS를 겨냥하므로 작게 녹음된 소리는 확실히 올라온다. 여유를 크게 둔
    # 이유는 정확한 값이 아니라 **닿았는가**를 재기 때문이다.
    assert loud_peak > quiet_peak + 6, f"음량 맞추기가 완성본에 안 닿았다 ({quiet_peak} → {loud_peak})"

    denoised = render({"denoise": True}, "quiet-denoised.mp4")
    assert _audio_bytes(denoised) != _audio_bytes(plain), "잡음 줄이기가 완성본에 안 닿았다"


def test_pitch_preservation_changes_the_sound_without_changing_the_length(picture_project, tmp_path: Path) -> None:
    """`음조 유지`를 끄면 소리가 달라지되 길이는 그대로여야 한다.

    길이가 같은 것이 중요하다 -- 길이가 바뀌면 자막도 다른 트랙도 전부 밀린다.
    바뀌는 것은 소리의 높낮이뿐이다.
    """
    store, project_id, narration_uri, _ = picture_project
    tone = store.register_asset(
        project_id=project_id, asset_type=AssetType.BROLL_VIDEO,
        source_path=_tone_video(tmp_path / "tone.mp4"),
    )

    def render(preserve: bool, name: str) -> Path:
        return _render(
            store=store, project_id=project_id, narration_uri=narration_uri,
            tracks=[_broll_track(tone.storage_uri, {
                "speed": 2.0, "preserve_source_audio": True, "preserve_pitch": preserve,
            })],
            output=tmp_path / name,
        )

    kept = render(True, "pitch-kept.mp4")
    lifted = render(False, "pitch-lifted.mp4")

    assert _audio_bytes(kept) != _audio_bytes(lifted), "음조 유지 스위치가 완성본에 안 닿았다"
    assert _duration(kept) == pytest.approx(_duration(lifted), abs=0.1), "높낮이만 바뀌어야 하는데 길이가 달라졌다"


def _tone_video(path: Path) -> Path:
    """소리가 실린 화면. 배속의 소리 쪽을 재려면 클립 자체에 소리가 있어야 한다."""
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=teal:s={WIDTH}x{HEIGHT}:r={FPS}:d=4",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    )
    return path


def _duration(path: Path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout.strip())
