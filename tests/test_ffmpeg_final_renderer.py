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
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.editing_session import build_editing_session, update_segment_image_overlay
from videobox_core_engine.overlay_shapes import SHAPE_OVERLAY_ICON_GLYPHS, font_supports_glyph
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

# 아이콘 오버레이는 글자 하나를 그린다. 그 글자를 전부 가진 글꼴이라야 검사가
# 의미 있다 -- 나눔고딕에는 없는 기호가 있어 후보를 따로 고른다.
_ICON_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    r"C:\Windows\Fonts\seguisym.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
)
ICON_FONT = next(
    (
        path
        for path in _ICON_FONT_CANDIDATES
        if Path(path).is_file()
        and all(font_supports_glyph(path, glyph) for glyph in SHAPE_OVERLAY_ICON_GLYPHS.values())
    ),
    None,
)


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


@pytest.mark.skipif(OVERLAY_FONT is None, reason="no font available to draw a text overlay")
def test_apply_export_overlays_draws_table_structure_in_the_legacy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """렌더 경로가 둘이다: composition plan 그래프뿐 아니라 이 legacy 경로도
    표의 열·행을 실제로 그려야 한다. 예전에는 `text`만 그렸다."""
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, overlay_font_file=OVERLAY_FONT)
    captured: list[list[str]] = []

    def fake_run(self: FfmpegFinalRenderer, command: list[str]) -> subprocess.CompletedProcess:
        captured.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(FfmpegFinalRenderer, "_run", fake_run)

    result = renderer._apply_export_overlays(
        project_id="project_001",
        video_path=tmp_path / "video.mp4",
        overlays=[{
            "overlay_type": "table_overlay",
            "columns": ["항목", "값"],
            "rows": [["길이", "10초"]],
            "text": "요약표",
            "start_sec": 0.0,
            "end_sec": 1.0,
        }],
        work_dir=tmp_path,
    )

    assert result != tmp_path / "video.mp4"
    assert captured, "the overlay render command never ran"
    filter_graph = captured[0][captured[0].index("-filter_complex") + 1]
    assert "항목 | 값" in filter_graph
    assert "길이 | 10초" in filter_graph
    assert "요약표" in filter_graph
    assert filter_graph.index("항목 | 값") < filter_graph.index("길이 | 10초")


def test_apply_export_overlays_draws_static_shapes_in_the_legacy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """렌더 경로가 둘이다: 그래프 경로뿐 아니라 이 legacy 경로도 정지 도형을
    drawbox로 그려야 한다. 도형은 글줄이 아니므로 글꼴 없이도 그려진다."""
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(
        store=store, overlay_font_file=str(tmp_path / "no-font-anywhere.ttf")
    )
    captured: list[list[str]] = []

    def fake_run(self: FfmpegFinalRenderer, command: list[str]) -> subprocess.CompletedProcess:
        captured.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(FfmpegFinalRenderer, "_run", fake_run)

    result = renderer._apply_export_overlays(
        project_id="project_001",
        video_path=tmp_path / "video.mp4",
        overlays=[
            {
                "overlay_type": "shape_overlay",
                "shape": "highlight_box",
                "vertical": "middle",
                "horizontal": "right",
                "size": "medium",
                "start_sec": 0.0,
                "end_sec": 1.5,
            },
            {
                "overlay_type": "shape_overlay",
                "shape": "underline",
                "vertical": "bottom",
                "horizontal": "center",
                "size": "small",
                "start_sec": 2.0,
                "end_sec": 3.0,
            },
        ],
        work_dir=tmp_path,
    )

    assert result != tmp_path / "video.mp4"
    assert captured, "the overlay render command never ran"
    filter_graph = captured[0][captured[0].index("-filter_complex") + 1]
    assert filter_graph.count("drawbox=") == 2
    assert "between(t,0.0,1.5)" in filter_graph
    assert "between(t,2.0,3.0)" in filter_graph
    assert "t=fill" in filter_graph
    assert "drawtext" not in filter_graph


def _capture_export_overlay_filter_graph(
    renderer: FfmpegFinalRenderer,
    *,
    overlays: list[dict[str, object]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    captured: list[list[str]] = []

    def fake_run(self: FfmpegFinalRenderer, command: list[str]) -> subprocess.CompletedProcess:
        captured.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(FfmpegFinalRenderer, "_run", fake_run)
    renderer._apply_export_overlays(
        project_id="project_001",
        video_path=tmp_path / "video.mp4",
        overlays=overlays,
        work_dir=tmp_path,
    )
    assert captured, "the overlay render command never ran"
    return captured[0][captured[0].index("-filter_complex") + 1]


@pytest.mark.skipif(ICON_FONT is None, reason="no font carrying the icon glyphs is available")
def test_apply_export_overlays_draws_icon_overlays_in_the_legacy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """화살표 같은 아이콘은 drawbox로 못 그린다(사각형만 그린다).

    새 필터 체계를 만들지 않고 이미 있는 drawtext 경로를 그대로 쓴다 -- 크기는
    3단이 fontsize로, 위치는 9칸이 기존 x/y 식으로 간다.
    """
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path),
        overlay_font_file=ICON_FONT,
        video_width=1280,
        video_height=720,
    )

    filter_graph = _capture_export_overlay_filter_graph(
        renderer,
        overlays=[{
            "overlay_type": "shape_overlay",
            "shape": "icon_arrow_right",
            "vertical": "middle",
            "horizontal": "right",
            "size": "medium",
            "start_sec": 1.0,
            "end_sec": 2.0,
        }],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert "drawtext=" in filter_graph
    assert "text='→'" in filter_graph
    assert "fontsize=187" in filter_graph
    assert "x=w-text_w-77:y=(h-text_h)/2" in filter_graph
    assert "between(t,1.0,2.0)" in filter_graph
    # 아이콘은 도형이 아니다: drawbox로 사각형을 덧그리면 안 된다.
    assert "drawbox=" not in filter_graph
    # 글줄 오버레이의 검은 상자·아래 정렬은 아이콘에 딸려오지 않는다.
    assert "box=1" not in filter_graph


@pytest.mark.skipif(ICON_FONT is None, reason="no font carrying the icon glyphs is available")
def test_both_render_paths_place_the_same_icon_at_the_same_spot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이 저장소가 같은 함정에 여러 번 걸렸다: 렌더 경로가 둘이다.

    두 경로가 같은 아이콘을 같은 자리·같은 크기로 그리지 않으면, 미리보기에서
    맞춰 놓은 위치가 완성본에서 어긋난다.
    """
    from videobox_core_engine.composition_plan import CompositionPlan

    overlay = {
        "overlay_type": "shape_overlay",
        "shape": "icon_arrow_down_left",
        "vertical": "top",
        "horizontal": "left",
        "size": "large",
        "start_sec": 0.5,
        "end_sec": 3.25,
    }
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path),
        overlay_font_file=ICON_FONT,
        video_width=1080,
        video_height=1920,
    )

    legacy_graph = _capture_export_overlay_filter_graph(
        renderer, overlays=[dict(overlay)], tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    plan_graph = renderer.build_plan_filter_graph(
        composition_plan=CompositionPlan.from_timeline(timeline={
            "output": {"width": 1080, "height": 1920},
            "tracks": [],
            "export_overlays": [dict(overlay)],
        }),
        source_indices={},
    )

    placement = "text='↙':x=65:y=154:fontsize=691"
    assert placement in legacy_graph
    assert placement in plan_graph
    assert "enable='between(t,0.5,3.25)'" in legacy_graph
    assert "enable='between(t,0.5,3.25)'" in plan_graph


def test_icon_overlay_fails_closed_when_the_font_cannot_draw_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """글꼴이 없으면 조용히 두부(빈 상자)를 그리지 않고 멈춘다.

    빈 상자가 그려진 완성본은 성공으로 끝나기 때문에 owner가 알아채지 못한다.
    """
    import videobox_core_engine.overlay_shapes as overlay_shapes

    monkeypatch.setattr(overlay_shapes, "ICON_FONT_FALLBACKS", ())
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path), overlay_font_file=str(tmp_path / "no-font-anywhere.ttf")
    )
    overlays = [{
        "overlay_type": "shape_overlay",
        "shape": "icon_arrow_right",
        "vertical": "middle",
        "horizontal": "center",
        "size": "medium",
        "start_sec": 0.0,
        "end_sec": 1.0,
    }]

    with pytest.raises(FinalRenderError, match="Overlay font"):
        renderer._apply_export_overlays(
            project_id="project_001",
            video_path=tmp_path / "video.mp4",
            overlays=overlays,
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
    source_timeline = {
        "project_id": project.project_id,
        "timeline_id": "timeline_image_overlay",
        "narration_source_uri": narration_asset.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [
                {"segment_id": "scene-before", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 0.0, "end_sec": 1.0},
                {"segment_id": "scene-overlay", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 1.0, "end_sec": 3.0},
                {"segment_id": "scene-after", "asset_uri": f"local://projects/{project.project_id}/assets/{narration_asset.asset_id}", "start_sec": 3.0, "end_sec": 4.0},
            ]},
            {"track_type": "broll", "clips": [
                {"segment_id": "scene-before", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 0.0, "end_sec": 1.0},
                {"segment_id": "scene-overlay", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 1.0, "end_sec": 3.0},
                {"segment_id": "scene-after", "asset_uri": f"local://projects/{project.project_id}/assets/{broll_asset.asset_id}", "start_sec": 3.0, "end_sec": 4.0},
            ]},
        ],
    }
    editing_session = build_editing_session(
        project_id=project.project_id,
        timeline=source_timeline,
        segments=[
            {"segment_id": "scene-before", "text": "앞", "start_sec": 0.0, "end_sec": 1.0},
            {"segment_id": "scene-overlay", "text": "오버레이", "start_sec": 1.0, "end_sec": 3.0},
            {"segment_id": "scene-after", "text": "뒤", "start_sec": 3.0, "end_sec": 4.0},
        ],
    )
    editing_session = update_segment_image_overlay(
        session=editing_session,
        segment_id="scene-overlay",
        asset_id=image_asset.asset_id,
        text="Overlay proof",
    )
    timeline = materialize_editing_session_timeline(
        timeline=source_timeline,
        editing_session=editing_session,
        project_id=project.project_id,
    )
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


# ---------------------------------------------------------------------------
# 2026-08-27: owner가 실제 프로젝트에서 컷 하나 바꾸는 데 21초가 걸린다고
# 신고했다. 서버 기록으로 실측했고(created_at→updated_at), B-roll 원본이
# 494초짜리였다. `build_plan_filter_graph`는 `trim=start=X:end=Y` **필터**로
# 자르는데, 필터 트림은 입력을 처음부터 디코딩한 뒤 버린다 -- X초까지 읽고
# 버리는 시간이 고스란히 렌더 시간에 얹힌다. `-ss`를 `-i` **앞에** 두면
# (입력 탐색) 그 낭비가 사라진다. 반복 재생(loop) 클립은 건드리지 않는다 --
# 그 경우는 이미 있던 검증된 경로이고, `-ss`와 `-stream_loop`를 함께 쓰는
# 조합은 새로 검증이 필요해 이번 범위 밖이다.
# ---------------------------------------------------------------------------


def test_broll_source_uses_fast_seek_before_decoding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """자르는 시작점까지 디코딩해서 버리지 않는다 -- `-ss`를 `-i` 앞에 둔다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("FastSeek")
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
    # 원본이 494초짜리라는 실제 신고 사례를 그대로 쓴다.
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 494.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_audio_stream_duration", lambda _self, _path: 494.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_visual_stream", lambda _self, _path: True)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_audio_stream", lambda _self, _path: True)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.verify_output_sources", lambda **_kwargs: None)
    timeline = {
        "timeline_id": "timeline-fast-seek", "project_id": project.project_id, "output": {"width": 1920, "height": 1080},
        "tracks": [{"track_id": "t", "track_type": "broll", "clips": [{
            "clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id,
            "asset_uri": asset.storage_uri, "segment_id": "s1", "start_sec": 0.0, "end_sec": 1.5,
            "source_in_sec": 7.5, "source_out_sec": 9.0,
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
    i_index = command.index("-i")
    window = command[max(0, i_index - 6):i_index]
    # 컨테이너의 실제 ffmpeg로 실측·검증한 조합이다(픽셀·오디오 PCM까지 동일,
    # 500초 원본에서 3초를 뽑는 데 1.56초 → 0.11초로 14배 빨라졌다).
    # `-copyts`가 원래 타임스탬프를 보존하므로 **trim 필터는 한 글자도 안
    # 바꾼다** -- 잘라내는 지점이 절대 시각 그대로라 어긋날 여지가 없다.
    assert "-ss" in window, f"-ss가 -i 앞에 없다: {window}"
    assert float(window[window.index("-ss") + 1]) == pytest.approx(7.5)
    assert "-copyts" in window, f"-copyts가 -i 앞에 없다: {window}"
    filter_index = command.index("-filter_complex")
    graph = command[filter_index + 1]
    assert "trim=start=7.5:end=9.0" in graph, graph


def test_fast_seek_is_disabled_when_two_broll_items_share_a_clip_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`split_segment` 직후 두 조각이 합쳐지기 전까지 **같은 clip_id**를 그대로
    쓴다. `source_indices`는 clip_id로 찾으므로 나중 항목이 앞 항목의 색인을
    덮어쓴다 -- 실측으로 걸린 회귀다(`test_split_merge_and_reorder_...`가 픽셀로
    잡았다). 겹치면 빠른 탐색을 끈다: 두 clip_id 모두 `-ss`가 없어야 한다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("FastSeekCollision")
    renderer = FfmpegFinalRenderer(store=store)
    commands: list[list[str]] = []
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    monkeypatch.setattr(
        FfmpegFinalRenderer, "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 494.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_audio_stream_duration", lambda _self, _path: 494.0)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_visual_stream", lambda _self, _path: True)
    monkeypatch.setattr(FfmpegFinalRenderer, "_has_audio_stream", lambda _self, _path: True)
    monkeypatch.setattr("videobox_core_engine.ffmpeg_final_renderer.verify_output_sources", lambda **_kwargs: None)
    # 같은 clip_id("c1")를 쓰는 두 조각. source_in_sec가 서로 다르다 -- 실제
    # split 직후 모양 그대로다.
    timeline = {
        "timeline_id": "timeline-fast-seek-collision", "project_id": project.project_id, "output": {"width": 1920, "height": 1080},
        "tracks": [{"track_id": "t", "track_type": "broll", "clips": [
            {"clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id, "asset_uri": asset.storage_uri,
             "segment_id": "s1", "start_sec": 0.0, "end_sec": 2.0, "source_in_sec": 0.0, "source_out_sec": 2.0, "media_controls": {}},
            {"clip_id": "c1", "clip_type": "broll", "asset_id": asset.asset_id, "asset_uri": asset.storage_uri,
             "segment_id": "s2", "start_sec": 2.0, "end_sec": 4.0, "source_in_sec": 7.5, "source_out_sec": 9.5, "media_controls": {}},
        ]}],
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
    assert "-ss" not in command, f"clip_id가 겹치는데 -ss가 붙었다: {command}"
    assert "-copyts" not in command


def test_audio_cleanup_chain_stays_empty_until_the_owner_turns_a_filter_on() -> None:
    """캡컷 오디오 탭 대조로 들어온 둘(owner 승인 2026-09-01).

    기본값에서 필터가 하나라도 붙으면 **아무것도 안 고른 편집본이 바뀐다.**
    이 저장소가 이미 한 번 겪은 함정이라(색감 `filter` 칸) 여기서 못박는다.
    """
    from videobox_core_engine.ffmpeg_final_renderer import _audio_cleanup_chain

    assert _audio_cleanup_chain({"normalize_loudness": False, "denoise": False}) == ""
    assert _audio_cleanup_chain({}) == ""
    # 잡음을 먼저 걷고 음량을 맞춘다. 반대로 하면 loudnorm이 잡음까지 포함한
    # 크기로 맞춰서, 잡음을 지운 결과가 목표보다 조용해진다.
    assert _audio_cleanup_chain({"denoise": True, "normalize_loudness": True}) == ",afftdn,loudnorm=I=-16:TP=-1.5:LRA=11"
    assert _audio_cleanup_chain({"denoise": True}) == ",afftdn"
    assert _audio_cleanup_chain({"normalize_loudness": True}) == ",loudnorm=I=-16:TP=-1.5:LRA=11"


def test_broll_transform_puts_stabilisation_before_the_size_fit(tmp_path: Path) -> None:
    """`deshake`는 흔들린 만큼 화면을 밀어 가장자리를 비운다.

    원본 해상도에서 먼저 걸어야 뒤의 `scale`·`crop`이 그 빈 자리를 함께
    처리한다 -- 순서를 뒤집으면 출력 크기에 맞춘 그림이 다시 밀리면서 검은
    테두리가 남는다.
    """
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=1920, video_height=1080)

    plain = renderer._broll_fit_transform({"fit": "fit"})
    assert "deshake" not in plain

    for fit_mode in ("fit", "crop"):
        stabilised = renderer._broll_fit_transform({"fit": fit_mode, "stabilize": True})
        assert stabilised.startswith("deshake,"), stabilised
        assert stabilised.index("deshake") < stabilised.index("scale=")


def test_legacy_path_refuses_a_stabilised_clip_instead_of_dropping_it(tmp_path: Path) -> None:
    """렌더 경로가 둘인데 `deshake`는 그래프 쪽에만 붙는다.

    legacy 경로의 `_extract_segment`는 자기 `scale/crop` 사슬을 따로 만들어서,
    켜 둔 보정이 **조용히 사라진 mp4**가 나온다. 색감(`filter`)이 이미 같은
    이유로 여기서 멈추고 있었다 -- 손떨림 보정도 같은 자리에서 멈춰야 한다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="stabilise-guard")
    timeline = {
        "tracks": [
            {"track_type": "broll", "clips": [{
                "asset_uri": "asset://missing", "start_sec": 0.0, "end_sec": 1.0,
                "media_controls": {"stabilize": True},
            }]},
        ],
    }

    with pytest.raises(FinalRenderError, match="composition_plan"):
        FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
            project_id=project.project_id, timeline=timeline, output_path=tmp_path / "out.mp4"
        )
