from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.ffmpeg_final_renderer import (
    FfmpegFinalRenderer,
    FinalRenderError,
)
from videobox_core_engine.ass_subtitles import render_editing_session_ass
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.timeline_clip_source_resolution import ResolvedClipSource
from videobox_core_engine.output_source_verifier import OutputSourceStaleError

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

# A text overlay needs a real font file. This test used to lean on the
# renderer's old default -- a Windows path -- so it only ever proved anything
# on Windows and would have failed in the container it ships to. Name the
# font the test actually uses instead.
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
)
OVERLAY_FONT = next((path for path in _FONT_CANDIDATES if Path(path).is_file()), None)


def test_final_renderer_rejects_post_materialization_content_mutation_before_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 12 RED: no renderer may silently consume a swapped local asset."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="stale final source")
    source = tmp_path / "broll.mp4"
    source.write_bytes(b"original")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    stored = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri)
    expected_sha = __import__("hashlib").sha256(stored.read_bytes()).hexdigest()
    stored.write_bytes(b"mutated after materialization")
    renderer = FfmpegFinalRenderer(store=store)
    monkeypatch.setattr(FfmpegFinalRenderer, "_run", lambda _self, _command: pytest.fail("ffmpeg must not start"))
    timeline = {"tracks": [{"track_type": "broll", "clips": [{"asset_uri": asset.storage_uri, "asset_id": asset.asset_id, "start_sec": 0, "end_sec": 1, "expected_content_sha256": expected_sha}]}]}
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset"):
        renderer.render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=tmp_path / "out.mp4")


# 컨테이너는 메모리 2GiB인데 CPU는 호스트의 16개가 그대로 보인다. x264는 그 수만큼
# 스레드를 잡아 1080p에서 인코더를 아예 열지 못하고, ffmpeg는 "streams received no
# packets"로만 끝난다 -- owner에게는 "완성본을 만들지 못했어요"로 보인다.
# 컨테이너에서 실측: 스레드 1·4·8·12는 성공, 16(기본값)만 실패.
def test_the_encoder_thread_count_is_capped_so_a_small_container_can_open_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.os.cpu_count", lambda: 64)
    monkeypatch.setattr(FfmpegFinalRenderer, "_cgroup_cpu_quota", staticmethod(lambda: None))

    assert renderer.encoder_thread_limit() == 8

    monkeypatch.setattr(FfmpegFinalRenderer, "_cgroup_cpu_quota", staticmethod(lambda: None))
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.os.cpu_count", lambda: None)
    assert renderer.encoder_thread_limit() == 1

    # 컨테이너가 받은 몫이 `nproc`보다 작으면 그쪽을 따른다. `cpus: 2.0`으로 묶여
    # 있는데 16개를 띄우면 빨라지지도 않으면서 프로세스 상한만 먹는다.
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.os.cpu_count", lambda: 16)
    monkeypatch.setattr(FfmpegFinalRenderer, "_cgroup_cpu_quota", staticmethod(lambda: 2))
    assert renderer.encoder_thread_limit() == 2


# 인코더만 묶는 것으로는 부족했다 -- 실제로 막힌 것은 필터 쪽 스레드였다.
# 컨테이너에서 실측: 필터 스레드를 안 정하면 실패하고 2·4·8은 모두 성공한다.
def test_the_render_command_caps_filter_threads_not_just_the_encoder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Threads")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    renderer = FfmpegFinalRenderer(store=store)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 30.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_audio_stream_duration", lambda _self, _path: 999.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_visual_stream", lambda _self, _path: True)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.verify_output_sources", lambda **_kwargs: None)

    timeline = {
        "timeline_id": "timeline-threads", "project_id": project.project_id, "output": {"width": 1920, "height": 1080},
        "tracks": [{"track_id": "t", "track_type": "broll", "clips": [{
            "clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id,
            "asset_uri": asset.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0,
            "media_controls": {},
        }]}],
    }
    renderer._render_composition_plan_to_mp4(
        project_id=project.project_id,
        composition_plan=renderer.extract_composition_plan(timeline=timeline),
        timeline_context=timeline,
        output_path=tmp_path / "out.mp4",
        subtitle_file_path=None,
        subtitle_ass_path=None,
        proxy_profile=False,
    )

    command = commands[0]
    cap = renderer.encoder_thread_limit()
    assert command[command.index("-filter_complex_threads") + 1] == str(cap)
    assert command[command.index("-filter_threads") + 1] == str(cap)
    assert command[command.index("-threads") + 1] == str(cap)


def test_broll_extract_maps_trim_crop_loop_and_pad_into_one_ffmpeg_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 1.3)

    renderer._extract_segment(
        source=ResolvedClipSource(path=tmp_path / "short.mp4", trim_start_sec=0.1, trim_duration_sec=1.0, target_duration_sec=4.0),
        output_path=tmp_path / "segment.mp4",
        video=True,
        media_controls={"fit": "crop", "loop": False, "pad": True, "trim_start_sec": 0.2},
    )

    command = commands[0]
    assert command[2:4] == ["-ss", "0.30000000000000004"]
    assert "-stream_loop" not in command
    filter_value = command[command.index("-vf") + 1]
    assert "force_original_aspect_ratio=increase" in filter_value
    assert "tpad=stop_mode=add:stop_duration=3.0" in filter_value


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_final_render_preserves_opted_in_broll_source_audio(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="B-roll source audio")
    narration_file = tmp_path / "silence.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1", "-c:a", "pcm_s16le", str(narration_file)])
    broll_file = tmp_path / "child-source.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=15:d=1", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    output = tmp_path / "with-source-audio.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
        project_id=project.project_id,
        output_path=output,
        timeline={"narration_source_uri": narration.storage_uri, "tracks": [
            {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 1.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 1.0, "media_controls": {"preserve_source_audio": True}}]},
        ]},
    )

    audio = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-map", "0:a:0", "-t", "1", "-f", "s16le", "pipe:1"], capture_output=True, timeout=30)
    assert audio.returncode == 0
    assert any(sample != 0 for sample in audio.stdout)


def test_export_overlay_blocks_a_missing_font_before_starting_ffmpeg(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, overlay_font_file=str(tmp_path / "missing-font.ttf"))

    with pytest.raises(FinalRenderError, match="Overlay font is missing"):
        renderer._apply_export_overlays(
            project_id="project_001",
            video_path=tmp_path / "video.mp4",
            overlays=[{"text": "Visible message", "start_sec": 0.0, "end_sec": 1.0}],
            work_dir=tmp_path,
        )


def test_final_renderer_explains_missing_broll_media_before_rendering(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Missing B-roll")
    renderer = FfmpegFinalRenderer(store=store)

    with pytest.raises(FinalRenderError, match="Unable to resolve B-roll media"):
        renderer._resolve_broll_clip_source(
            project_id=project.project_id,
            clip={"asset_uri": f"local://projects/{project.project_id}/assets/asset_missing", "start_sec": 0.0, "end_sec": 1.0},
        )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_final_render_keeps_unknown_user_owned_rights_warning_in_mp4_metadata(tmp_path: Path) -> None:
    """Unknown user-owned B-roll remains locally renderable, but never silently loses its rights warning."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Unknown rights final metadata")
    narration_file = tmp_path / "narration.wav"
    broll_file = tmp_path / "broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(narration_file)])
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=1", str(broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    output = tmp_path / "unknown-rights.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
        project_id=project.project_id,
        output_path=output,
        timeline={"narration_source_uri": narration.storage_uri, "tracks": [
            {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 1.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 1.0, "warning_provenance": ["copyright_confirmation_required"]}]},
        ]},
    )

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "default=noprint_wrappers=1", str(output)], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stderr
    assert "copyright_confirmation_required" in probe.stdout


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_render_timeline_burns_editing_session_ass_without_subtitle_stream(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Styled Caption Render")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration_file)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll_file = tmp_path / "broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=2", str(broll_file)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    session = {"caption_style": {"font_family": "Arial", "font_size_px": 64, "text_color": "#FF0000FF"}, "segments": [{"caption_text": "STYLE", "start_sec": 0.2, "end_sec": 1.8}]}
    ass_path = tmp_path / "captions.ass"
    ass_path.write_text(render_editing_session_ass(session, video_width=320, video_height=240), encoding="utf-8")
    output_path = tmp_path / "styled.mp4"
    timeline = {"narration_source_uri": narration_asset.storage_uri, "tracks": [{"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/segments/seg_001", "start_sec": 0.0, "end_sec": 2.0}]}, {"track_type": "broll", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 2.0}]}]}

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=output_path, subtitle_ass_path=ass_path)

    frame = _frame_rgb(output_path, at_sec=1.0, width=320, height=240)
    assert max(frame[0::3]) > 180
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries", "stream=index", "-of", "csv=p=0", str(output_path)], capture_output=True, text=True, timeout=30)
    assert probe.stdout.strip() == ""


def test_resolve_narration_clip_source_uses_narration_source_uri_for_segment_style_asset_uri(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Resolver Project")
    narration_file = tmp_path / "narration.wav"
    narration_file.write_bytes(b"fake narration bytes")
    narration_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=narration_file,
    )
    renderer = FfmpegFinalRenderer(store=store)
    timeline = {"narration_source_uri": narration_asset.storage_uri}
    clip = {
        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
        "start_sec": 2.0,
        "end_sec": 5.0,
    }

    resolved = renderer._resolve_narration_clip_source(project_id=project.project_id, timeline=timeline, clip=clip)

    assert resolved.path == store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=narration_asset.storage_uri
    )
    assert resolved.trim_start_sec == 2.0
    assert resolved.trim_duration_sec == 3.0


def test_resolve_narration_clip_source_raises_without_narration_source_uri(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Resolver Missing Source Project")
    renderer = FfmpegFinalRenderer(store=store)
    clip = {
        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
        "start_sec": 0.0,
        "end_sec": 1.0,
    }

    with pytest.raises(FinalRenderError, match="narration_source_uri"):
        renderer._resolve_narration_clip_source(project_id=project.project_id, timeline={}, clip=clip)


def test_resolve_broll_clip_source_resolves_asset_style_uri_via_store(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Resolver Broll Project")
    broll_file = tmp_path / "broll.mp4"
    broll_file.write_bytes(b"fake broll bytes")
    broll_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=broll_file,
    )
    renderer = FfmpegFinalRenderer(store=store)
    clip = {
        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
        "start_sec": 0.0,
        "end_sec": 4.0,
    }

    resolved = renderer._resolve_broll_clip_source(project_id=project.project_id, clip=clip)

    assert resolved.path == store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=broll_asset.storage_uri
    )
    assert resolved.trim_start_sec == 0.0
    assert resolved.trim_duration_sec == 4.0
    assert resolved.target_duration_sec == 4.0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
@pytest.mark.skipif(OVERLAY_FONT is None, reason="no font available to draw a text overlay")
def test_render_timeline_loops_short_broll_and_pads_short_tts_to_the_timeline_window(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Short Source Duration Project")
    narration_file = tmp_path / "short_tts.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(narration_file)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll_file = tmp_path / "short_broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=15", str(broll_file)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "export_overlays": [{"text": "Overlay proof", "start_sec": 0.5, "end_sec": 3.5}],
        "tracks": [
            {"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0}]},
        ],
    }
    output_path = tmp_path / "duration_safe.mp4"
    FfmpegFinalRenderer(store=store, overlay_font_file=OVERLAY_FONT).render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=output_path)
    probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)], capture_output=True, text=True, timeout=30)
    assert float(probe.stdout.strip()) == pytest.approx(4.0, abs=0.6)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_render_timeline_materializes_image_overlay_during_its_window(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Image Overlay Project")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_file)])
    narration_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll_file = tmp_path / "black_broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=4", str(broll_file)])
    broll_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    image_file = tmp_path / "yellow_overlay.png"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=yellow:s=80x60", "-frames:v", "1", str(image_file)])
    image_asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=image_file)
    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "export_overlays": [{
            "overlay_type": "visual_overlay",
            "asset_id": image_asset.asset_id,
            "start_sec": 1.0,
            "end_sec": 3.0,
        }],
        "tracks": [
            {"track_type": "narration", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 4.0}]},
        ],
    }
    output_path = tmp_path / "image_overlay.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
        project_id=project.project_id,
        timeline=timeline,
        output_path=output_path,
    )

    before = _frame_rgb(output_path, at_sec=0.5, width=320, height=240)
    during = _frame_rgb(output_path, at_sec=2.0, width=320, height=240)

    assert max(before) < 8
    assert max(during) > 200


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_render_timeline_to_mp4_produces_a_real_playable_video(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render End To End Project")

    narration_file = tmp_path / "narration_source.wav"
    _generate(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            str(narration_file),
        ]
    )
    narration_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=narration_file,
    )

    broll_file = tmp_path / "broll_source.mp4"
    _generate(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=320x240:rate=15",
            str(broll_file),
        ]
    )
    broll_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=broll_file,
    )

    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                    },
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_002",
                        "start_sec": 3.0,
                        "end_sec": 6.0,
                    },
                ],
            },
            {
                "track_type": "broll",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 3.0,
                    },
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 3.0,
                        "end_sec": 6.0,
                    },
                ],
            },
        ],
    }

    renderer = FfmpegFinalRenderer(store=store)
    output_path = tmp_path / "final_output.mp4"

    result_path = renderer.render_timeline_to_mp4(
        project_id=project.project_id,
        timeline=timeline,
        output_path=output_path,
    )

    assert result_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert float(probe.stdout.strip()) == pytest.approx(6.0, abs=1.0)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_render_timeline_to_mp4_reports_progress_milestones(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Render Progress Project")

    narration_file = tmp_path / "narration_source.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(narration_file)])
    narration_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=narration_file,
    )

    broll_file = tmp_path / "broll_source.mp4"
    _generate(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15", str(broll_file)]
    )
    broll_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=broll_file,
    )

    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {
                "track_type": "narration",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                    }
                ],
            },
            {
                "track_type": "broll",
                "clips": [
                    {
                        "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}",
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                    }
                ],
            },
        ],
    }

    renderer = FfmpegFinalRenderer(store=store)
    output_path = tmp_path / "final_output.mp4"
    reported: list[int] = []

    renderer.render_timeline_to_mp4(
        project_id=project.project_id,
        timeline=timeline,
        output_path=output_path,
        on_progress=reported.append,
    )

    assert reported == sorted(reported)
    assert reported[-1] == 100


def _generate(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _frame_rgb(video_path: Path, *, at_sec: float, width: int, height: int) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(at_sec),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert len(result.stdout) == width * height * 3
    return result.stdout


# ---------------------------------------------------------------------------
# 2026-08-16: 완성본 오디오가 음악 구간 길이(5초)로 잘린 채 20초 영상이 성공(0)
# 처리된 실사례. 컨테이너 프로세스 상한(128) 근처에서 ffmpeg 스레드 생성이
# 조용히 실패하면 브랜치 하나만 일찍 끝난 채 출력이 나올 수 있다. 대책 둘 --
# 디코더까지 스레드 상한을 지키게 하고, 오디오가 짧게 나온 출력은 내보내기
# 전에 실패로 돌린다.
# ---------------------------------------------------------------------------


def _tiny_plan_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, renderer: FfmpegFinalRenderer, store: LocalProjectStore, project_id: str, commands: list[list[str]]) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 30.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_audio_stream_duration", lambda _self, _path: 5.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_visual_stream", lambda _self, _path: True)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.verify_output_sources", lambda **_kwargs: None)
    timeline = {
        "timeline_id": "timeline-decoder-threads", "project_id": project_id, "output": {"width": 1920, "height": 1080},
        "tracks": [{"track_id": "t", "track_type": "broll", "clips": [{
            "clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id,
            "asset_uri": asset.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 5.0,
            "media_controls": {},
        }]}],
    }
    renderer._render_composition_plan_to_mp4(
        project_id=project_id,
        composition_plan=renderer.extract_composition_plan(timeline=timeline),
        timeline_context=timeline,
        output_path=tmp_path / "out.mp4",
        subtitle_file_path=None,
        subtitle_ass_path=None,
        proxy_profile=False,
    )


def test_every_input_is_decoder_thread_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """인코더·필터만 묶으면 입력 6개짜리 렌더에서 디코더들이 호스트 CPU 수만큼
    스레드를 잡는다. 모든 `-i` 앞에 상한이 붙어야 한다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("DecoderThreads")
    renderer = FfmpegFinalRenderer(store=store)
    commands: list[list[str]] = []
    _tiny_plan_render(tmp_path, monkeypatch, renderer, store, project.project_id, commands)

    command = commands[0]
    cap = str(renderer.encoder_thread_limit())
    for index, token in enumerate(command):
        if token != "-i":
            continue
        window = command[max(0, index - 6):index]
        assert "-threads" in window and window[window.index("-threads") + 1] == cap, (
            f"input at position {index} has no decoder thread cap: {window}"
        )


def test_a_render_whose_audio_comes_out_short_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """오디오가 타임라인보다 짧게 나온 출력은 성공으로 내보내지 않는다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("ShortAudio")
    renderer = FfmpegFinalRenderer(store=store)
    commands: list[list[str]] = []
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 30.0)
    # 20초 계획인데 오디오 스트림이 5초로 끝난 상황.
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_audio_stream_duration", lambda _self, _path: 5.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_visual_stream", lambda _self, _path: True)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.verify_output_sources", lambda **_kwargs: None)
    timeline = {
        "timeline_id": "timeline-short-audio", "project_id": project.project_id, "output": {"width": 1920, "height": 1080},
        "tracks": [{"track_id": "t", "track_type": "broll", "clips": [{
            "clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id,
            "asset_uri": asset.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 20.0,
            "media_controls": {"loop": True},
        }]}],
    }
    with pytest.raises(FinalRenderError, match="audio"):
        renderer._render_composition_plan_to_mp4(
            project_id=project.project_id,
            composition_plan=renderer.extract_composition_plan(timeline=timeline),
            timeline_context=timeline,
            output_path=tmp_path / "out.mp4",
            subtitle_file_path=None,
            subtitle_ass_path=None,
            proxy_profile=False,
        )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is required")
def test_final_render_audio_spans_the_timeline_when_music_covers_one_segment(tmp_path: Path) -> None:
    """음악이 첫 구간에만 있어도 완성본 오디오는 타임라인 전체를 덮어야 한다.
    2026-08-16 실사례에서는 20초 영상에 5초 소리만 담긴 채 성공 처리됐다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("PartialMusic")
    video = tmp_path / "src.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
    ], check=True, capture_output=True)
    music = tmp_path / "bgm.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-ac", "2", "-ar", "48000", str(music),
    ], check=True, capture_output=True)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    bgm = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=music)
    timeline = {
        "timeline_id": "timeline-partial-music", "project_id": project.project_id,
        "output": {"width": 320, "height": 240},
        "tracks": [
            {"track_id": "v", "track_type": "broll", "clips": [{
                "clip_id": "b1", "clip_type": "broll", "asset_id": broll.asset_id,
                "asset_uri": broll.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 4.0,
                "media_controls": {},
            }]},
            {"track_id": "m", "track_type": "bgm", "clips": [{
                "clip_id": "m1", "clip_type": "bgm", "asset_id": bgm.asset_id,
                "asset_uri": bgm.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 1.0,
                "media_controls": {},
            }]},
        ],
    }
    output_path = tmp_path / "out.mp4"
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15)
    # 실제 파이프라인과 같은 경로(계획 기반)로 태운다.
    renderer.render_timeline_to_mp4(
        project_id=project.project_id, timeline=timeline, output_path=output_path,
        composition_plan=renderer.extract_composition_plan(timeline=timeline),
    )
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(output_path),
    ], capture_output=True, text=True, check=True)
    assert float(probe.stdout.strip()) == pytest.approx(4.0, abs=0.5)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_rendered_audio_has_sound_separates_a_silent_track_from_an_audible_one(tmp_path: Path) -> None:
    # 오디오 스트림이 20초로 멀쩡히 있어도 내용이 무음일 수 있다. 길이만 보던
    # 검사로는 구분되지 않아 완전 무음 완성본이 그대로 나갔다.
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store)
    silent = tmp_path / "silent.mp4"
    audible = tmp_path / "audible.mp4"
    for path, source in ((silent, "anullsrc=r=48000:cl=stereo"), (audible, "sine=frequency=440:r=48000")):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", source, "-t", "1", "-c:a", "aac", str(path)],
            capture_output=True, text=True, check=True,
        )

    assert renderer.rendered_audio_has_sound(silent) is False
    assert renderer.rendered_audio_has_sound(audible) is True


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_a_render_that_cannot_be_measured_claims_nothing_about_its_sound(tmp_path: Path) -> None:
    # 재지 못한 것과 소리가 없는 것은 다르다. 섞으면 멀쩡한 완성본에 경고가 붙는다.
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store)
    not_media = tmp_path / "not-media.mp4"
    not_media.write_bytes(b"this is not a video")

    assert renderer.rendered_audio_has_sound(not_media) is None


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
@pytest.mark.parametrize("soundless_first", [False, True])
def test_segment_render_survives_a_soundless_broll_between_sound_kept_brolls(tmp_path: Path, soundless_first: bool) -> None:
    """`원본 소리 살리기`를 켰는데 원본에 오디오 스트림이 아예 없어도 렌더가 막히면 안 된다.

    무음 원본이 섞이면 조각마다 스트림 구성이 달라진다. concat은 **첫 조각**의
    스트림 구성을 기준으로 삼으므로, 무음 조각이 앞에 오면 뒤 조각의 소리가
    통째로 사라지거나 `[1:a]` 믹스가 잡을 스트림이 없어 막힌다. 켠 사람은
    잘못한 게 없다 -- 무음 원본은 무음을 실어 주면 된다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="soundless broll must not block")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2", "-c:a", "pcm_s16le", str(narration_file)])
    sound_broll_file = tmp_path / "sound-broll.mp4"
    _generate([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=15:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(sound_broll_file),
    ])
    soundless_broll_file = tmp_path / "soundless-broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:r=15:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(soundless_broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    sound_broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=sound_broll_file)
    soundless_broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=soundless_broll_file)
    output = tmp_path / "soundless-mixed.mp4"

    FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
        project_id=project.project_id,
        output_path=output,
        timeline={"narration_source_uri": narration.storage_uri, "tracks": [
            {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
            {"track_type": "broll", "clips": (
                [
                    {"asset_uri": soundless_broll.storage_uri, "start_sec": 0.0, "end_sec": 1.0, "media_controls": {"preserve_source_audio": True, "loop": False}},
                    {"asset_uri": sound_broll.storage_uri, "start_sec": 1.0, "end_sec": 2.0, "media_controls": {"preserve_source_audio": True, "loop": False}},
                ]
                if soundless_first
                else [
                    {"asset_uri": sound_broll.storage_uri, "start_sec": 0.0, "end_sec": 1.0, "media_controls": {"preserve_source_audio": True, "loop": False}},
                    {"asset_uri": soundless_broll.storage_uri, "start_sec": 1.0, "end_sec": 2.0, "media_controls": {"preserve_source_audio": True, "loop": False}},
                ]
            )},
        ]},
    )

    peak = probe_audio_peak_dbfs(output)
    assert peak is not None and peak > -30.0, "내레이션 소리가 완성본에 남아 있어야 한다"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_plan_render_survives_a_soundless_broll_with_source_audio_kept(tmp_path: Path) -> None:
    """계획 기반 경로도 같은 함정을 밟는다 -- 렌더 경로가 둘이라는 걸 잊지 마라.

    그래프가 무음 원본의 `[N:a]`를 참조하면 ffmpeg가 통째로 실패한다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="plan path soundless broll")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2", "-c:a", "pcm_s16le", str(narration_file)])
    soundless_broll_file = tmp_path / "soundless-broll.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=320x240:r=15:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(soundless_broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=soundless_broll_file)
    output = tmp_path / "plan-soundless.mp4"
    timeline = {
        "timeline_id": "timeline-plan-soundless", "project_id": project.project_id,
        "narration_source_uri": narration.storage_uri,
        "output": {"width": 320, "height": 240},
        "tracks": [
            {"track_id": "n", "track_type": "narration", "clips": [{
                "clip_id": "n1", "clip_type": "narration", "asset_id": narration.asset_id,
                "asset_uri": narration.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 2.0,
            }]},
            {"track_id": "b", "track_type": "broll", "clips": [{
                "clip_id": "b1", "clip_type": "broll", "asset_id": broll.asset_id,
                "asset_uri": broll.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 2.0,
                "media_controls": {"preserve_source_audio": True, "loop": False},
            }]},
        ],
    }
    renderer = FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15)

    renderer.render_timeline_to_mp4(
        project_id=project.project_id, timeline=timeline, output_path=output,
        composition_plan=renderer.extract_composition_plan(timeline=timeline),
    )

    peak = probe_audio_peak_dbfs(output)
    assert peak is not None and peak > -30.0, "내레이션 소리가 완성본에 남아 있어야 한다"


def test_every_amix_line_in_the_renderer_keeps_normalize_off() -> None:
    """`amix`는 기본으로 입력 수만큼 나눈다(normalize=1). 같은 함정에 이미
    세 번 걸렸다 -- 새 믹스 자리가 또 잊지 못하게 소스에서 직접 잰다.
    ffmpeg 없는 기계에서도 도는 가드다."""
    import inspect

    from videobox_core_engine import ffmpeg_final_renderer as module

    offenders = [
        line.strip()
        for line in inspect.getsource(module).splitlines()
        if "amix=inputs" in line and "normalize=0" not in line
    ]

    assert offenders == []


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
@pytest.mark.skipif(OVERLAY_FONT is None, reason="no usable overlay font on this machine")
def test_export_overlays_do_not_break_the_kept_broll_source_audio(tmp_path: Path) -> None:
    """자막 카드(오버레이)를 얹는 재인코딩이 `-an`으로 돌아서, 오버레이가 하나라도
    있으면 `원본 소리 살리기` 믹스가 잡을 `[1:a]`가 사라져 렌더가 통째로 막혔다.
    소리는 오버레이를 얹기 **전** 이어붙인 파일에서 가져와야 한다."""
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="overlay must not eat broll audio")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:a", "pcm_s16le", str(narration_file)])
    sound_broll_file = tmp_path / "sound-broll.mp4"
    _generate([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=15:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(sound_broll_file),
    ])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=sound_broll_file)
    output = tmp_path / "overlay-and-source-audio.mp4"

    FfmpegFinalRenderer(
        store=store, video_width=320, video_height=240, video_fps=15, overlay_font_file=OVERLAY_FONT,
    ).render_timeline_to_mp4(
        project_id=project.project_id,
        output_path=output,
        timeline={
            "narration_source_uri": narration.storage_uri,
            "export_overlays": [{"overlay_type": "explanation_card", "text": "설명 카드", "start_sec": 0.2, "end_sec": 1.2}],
            "tracks": [
                {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
                {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"preserve_source_audio": True, "loop": False}}]},
            ],
        },
    )

    peak = probe_audio_peak_dbfs(output)
    assert peak is not None and peak > -30.0, "살려 둔 B-roll 소리가 완성본에 남아 있어야 한다"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
@pytest.mark.parametrize("ducking", [False, True])
def test_adding_bgm_does_not_quiet_the_narration_in_the_segment_path(tmp_path: Path, ducking: bool) -> None:
    """음악을 깔았다고 **내레이션이 작아지면 안 된다.**

    `amix`는 기본으로 입력 수만큼 나눈다(normalize=1). 조각 이어붙이기 경로의
    음악 믹스에는 `normalize=0`이 없어서, 무음 음악을 깔아도 말소리가 6dB
    내려갔다. 같은 함정에 이미 두 번 걸렸다 -- 이번이 세 번째 자리다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"bgm must not duck narration ducking={ducking}")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2", "-c:a", "pcm_s16le", str(narration_file)])
    # 음악은 **무음**으로 둔다. 그래야 완성본 음량 변화가 오직 섞는 방식 때문임을 안다.
    bgm_file = tmp_path / "silent-bgm.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:a", "pcm_s16le", str(bgm_file)])
    broll_file = tmp_path / "backdrop.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=15:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    bgm = store.register_asset(project_id=project.project_id, asset_type=AssetType.BGM, source_path=bgm_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)

    def render(with_bgm: bool, name: str) -> Path:
        output = tmp_path / name
        tracks: list[dict] = [
            {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"loop": False}}]},
        ]
        if with_bgm:
            tracks.append({"track_type": "bgm", "clips": [{
                "asset_uri": bgm.storage_uri, "start_sec": 0.0, "end_sec": 2.0,
                "media_controls": {"ducking": ducking},
            }]})
        FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
            project_id=project.project_id, output_path=output,
            timeline={"narration_source_uri": narration.storage_uri, "tracks": tracks},
        )
        return output

    without = probe_audio_peak_dbfs(render(False, "no-bgm.mp4"))
    with_bgm = probe_audio_peak_dbfs(render(True, "with-bgm.mp4"))

    assert without is not None and with_bgm is not None
    # 소리를 더했으니 조용해질 리가 없다. 측정 오차만 감안한다.
    assert with_bgm >= without - 1.0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_adding_sfx_does_not_quiet_the_narration_in_the_segment_path(tmp_path: Path) -> None:
    """효과음도 같다 -- 더한 것이지 나머지를 줄인 게 아니다."""
    from videobox_core_engine.ffmpeg_final_renderer import probe_audio_peak_dbfs

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="sfx must not duck narration")
    narration_file = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2", "-c:a", "pcm_s16le", str(narration_file)])
    sfx_file = tmp_path / "silent-sfx.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1", "-c:a", "pcm_s16le", str(sfx_file)])
    broll_file = tmp_path / "backdrop.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=15:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(broll_file)])
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_file)
    sfx = store.register_asset(project_id=project.project_id, asset_type=AssetType.SFX, source_path=sfx_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)

    def render(with_sfx: bool, name: str) -> Path:
        output = tmp_path / name
        tracks: list[dict] = [
            {"track_type": "narration", "clips": [{"asset_uri": narration.storage_uri, "start_sec": 0.0, "end_sec": 2.0}]},
            {"track_type": "broll", "clips": [{"asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 2.0, "media_controls": {"loop": False}}]},
        ]
        if with_sfx:
            tracks.append({"track_type": "sfx", "clips": [{
                "asset_uri": sfx.storage_uri, "start_sec": 0.5, "end_sec": 1.5, "media_controls": {},
            }]})
        FfmpegFinalRenderer(store=store, video_width=320, video_height=240, video_fps=15).render_timeline_to_mp4(
            project_id=project.project_id, output_path=output,
            timeline={"narration_source_uri": narration.storage_uri, "tracks": tracks},
        )
        return output

    without = probe_audio_peak_dbfs(render(False, "no-sfx.mp4"))
    with_sfx = probe_audio_peak_dbfs(render(True, "with-sfx.mp4"))

    assert without is not None and with_sfx is not None
    assert with_sfx >= without - 1.0
