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

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


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
    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(project_id=project.project_id, timeline=timeline, output_path=output_path)
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
