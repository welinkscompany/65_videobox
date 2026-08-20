"""장면에 얹은 표시가 등장·퇴장·이동하는가.

**필터 문자열이 아니라 픽셀로 잰다.** 이 저장소는 "필터가 붙어 있으니 되겠지"에
여러 번 속았다 -- 문자열은 멀쩡한데 화면은 그대로였다. 그래서 서로 다른 시각의
프레임을 실제로 뽑아 진하기와 자리를 비교한다.

**두 렌더 경로를 모두 본다.** 그래프 경로(`build_plan_filter_graph`)와 legacy
경로(`_apply_export_overlays`)가 따로 있고, 한쪽만 고쳐서 미리보기와 완성본이
어긋난 적이 있다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import (
    FfmpegFinalRenderer,
    export_overlay_shape_filters,
)
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

_ICON_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\seguisym.ttf",
)
ICON_FONT = next((path for path in _ICON_FONT_CANDIDATES if Path(path).is_file()), None)

PROBE_WIDTH, PROBE_HEIGHT = 320, 180


def _shape_overlay(**overrides: object) -> dict[str, object]:
    overlay: dict[str, object] = {
        "overlay_type": "shape_overlay",
        "shape": "highlight_box",
        "vertical": "middle",
        "horizontal": "center",
        "size": "large",
        "start_sec": 0.5,
        "end_sec": 3.0,
    }
    overlay.update(overrides)
    return overlay


def _filters(overlay: dict[str, object], *, width: int = 1280, height: int = 720,
             font_file: str | None = None) -> list[str]:
    return export_overlay_shape_filters(
        overlay,
        width=width,
        height=height,
        start_sec=float(overlay["start_sec"]),  # type: ignore[arg-type]
        end_sec=float(overlay["end_sec"]),  # type: ignore[arg-type]
        font_file=font_file,
    )


# --- 픽셀로 재는 도구 -------------------------------------------------------
#
# 바탕은 파랑(0,0,255), 표시는 노랑(255,212,0)이다. 겹치는 만큼 **빨강 채널**이
# 올라가므로 빨강 하나만 보면 진하기와 자리를 둘 다 알 수 있다.


def _render_probe(filters: list[str], output: Path, *, duration: float = 4.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", f"color=c=blue:s={PROBE_WIDTH}x{PROBE_HEIGHT}:r=25:d={duration}",
            "-vf", ",".join(filters),
            # 무손실로 굽는다. 손실 코덱은 알파 차이를 뭉개서 "안 변했다"는 거짓
            # 통과를 만든다.
            "-c:v", "ffv1", "-pix_fmt", "bgr0", str(output),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def _red_channel(video: Path, at_sec: float) -> list[int]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(at_sec), "-i", str(video), "-frames:v", "1",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return list(result.stdout[0::3])


def _strength(video: Path, at_sec: float) -> float:
    """표시가 얼마나 진하게 얹혔는가. 전부 사라지면 0이다."""
    red = _red_channel(video, at_sec)
    return sum(red) / len(red)


def _centroid_x(video: Path, at_sec: float) -> float | None:
    """표시가 화면 가로 어디에 있는가. 없으면 None."""
    red = _red_channel(video, at_sec)
    hits = [index % PROBE_WIDTH for index, value in enumerate(red) if value > 100]
    return sum(hits) / len(hits) if hits else None


def _probe(tmp_path: Path, name: str, overlay: dict[str, object],
           *, font_file: str | None = None) -> Path:
    output = tmp_path / f"{name}.mkv"
    _render_probe(
        _filters(overlay, width=PROBE_WIDTH, height=PROBE_HEIGHT, font_file=font_file),
        output,
    )
    return output


# --- 경계: 지금까지 만든 것이 그대로여야 한다 -------------------------------


def test_overlays_that_never_asked_for_motion_render_exactly_as_before() -> None:
    """승인 기록 5항의 경계: 기존 오버레이의 결과가 바뀌면 안 된다.

    `움직임`을 저장한 적 없는 옛 오버레이에는 `motion` 열쇠가 아예 없다. 그것도,
    `그대로`를 고른 것도, 예전과 **한 글자도 다르지 않은** 필터를 내야 한다.
    """
    before = "drawbox=x=665:y=266:w=538:h=187:color=0xFFD400@0.9:t=8:enable='between(t,0.0,1.5)'"
    overlay = _shape_overlay(horizontal="right", size="medium", start_sec=0.0, end_sec=1.5)

    assert _filters(overlay) == [before]
    assert _filters({**overlay, "motion": "none"}) == [before]
    # 저장된 값이 목록 밖이면 조용히 `그대로`로 좁힌다 -- 알 수 없는 이름 때문에
    # 표시가 통째로 사라지면 owner는 이유를 알 수 없다.
    assert _filters({**overlay, "motion": "wobble"}) == [before]


def test_underline_without_motion_renders_exactly_as_before() -> None:
    before = "drawbox=x=665:y=442:w=538:h=11:color=0xFFD400@0.9:t=fill:enable='between(t,0.0,1.5)'"
    overlay = _shape_overlay(
        shape="underline", horizontal="right", size="medium", start_sec=0.0, end_sec=1.5
    )

    assert _filters(overlay) == [before]
    assert _filters({**overlay, "motion": "none"}) == [before]


@pytest.mark.skipif(ICON_FONT is None, reason="no font carrying the icon glyphs is available")
def test_icon_without_motion_renders_exactly_as_before() -> None:
    overlay = _shape_overlay(
        shape="icon_arrow_right", horizontal="right", size="medium", start_sec=0.0, end_sec=1.5
    )

    unchanged = _filters(overlay, font_file=ICON_FONT)

    assert len(unchanged) == 1
    assert unchanged[0].endswith("fontcolor=0xFFD400@0.9:borderw=11:bordercolor=black@0.7:"
                                "enable='between(t,0.0,1.5)'")
    assert "alpha=" not in unchanged[0]
    assert _filters({**overlay, "motion": "none"}, font_file=ICON_FONT) == unchanged


# --- 두 렌더 경로 -----------------------------------------------------------


def test_both_render_paths_carry_the_same_motion_for_a_drawn_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """렌더 경로가 둘이다. 한쪽만 움직이면 미리보기와 완성본이 어긋난다."""
    overlay = _shape_overlay(motion="fade_in", start_sec=0.5, end_sec=3.0)
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path),
        overlay_font_file=str(tmp_path / "no-font-anywhere.ttf"),
        video_width=1280,
        video_height=720,
    )

    plan_graph = renderer.build_plan_filter_graph(
        composition_plan=CompositionPlan.from_timeline(timeline={
            "output": {"width": 1280, "height": 720},
            "tracks": [],
            "export_overlays": [dict(overlay)],
        }),
        source_indices={},
    )
    legacy_graph = _legacy_filter_graph(renderer, [dict(overlay)], tmp_path, monkeypatch)

    for graph in (plan_graph, legacy_graph):
        # 움직임은 여러 조각으로 나뉜다: 한 조각짜리면 아무것도 움직이지 않는다.
        assert graph.count("drawbox=") > 1
        # 조각마다 진하기가 달라야 한다 -- 같은 색이 반복되면 그냥 깜빡임이다.
        assert graph.count("0xFFD400@0.9") < graph.count("drawbox=")

    plan_boxes = sorted(part for part in plan_graph.split(";") if "drawbox=" in part)
    legacy_boxes = sorted(part for part in legacy_graph.split(";") if "drawbox=" in part)
    assert len(plan_boxes) == len(legacy_boxes)


@pytest.mark.skipif(ICON_FONT is None, reason="no font carrying the icon glyphs is available")
def test_both_render_paths_carry_the_same_motion_for_an_icon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overlay = _shape_overlay(shape="icon_star", motion="fade_in_out", start_sec=0.5, end_sec=3.0)
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path),
        overlay_font_file=ICON_FONT,
        video_width=1280,
        video_height=720,
    )

    plan_graph = renderer.build_plan_filter_graph(
        composition_plan=CompositionPlan.from_timeline(timeline={
            "output": {"width": 1280, "height": 720},
            "tracks": [],
            "export_overlays": [dict(overlay)],
        }),
        source_indices={},
    )
    legacy_graph = _legacy_filter_graph(renderer, [dict(overlay)], tmp_path, monkeypatch)

    for graph in (plan_graph, legacy_graph):
        assert "alpha=" in graph


def test_a_motion_chosen_on_screen_survives_all_the_way_to_the_filter_graph(
    tmp_path: Path,
) -> None:
    """편집 세션에 저장한 움직임이 렌더까지 닿는가.

    이 저장소가 반복해서 걸린 함정이 이것이다 -- 부품(저장·렌더)은 각각 되는데
    사이를 잇는 자리가 없어 화면에서 고른 것이 완성본에 닿지 않는다. 그래서
    세션 저장부터 필터 그래프까지 한 번에 통과시켜 본다.
    """
    from videobox_core_engine.composition_plan import materialize_editing_session_timeline
    from videobox_core_engine.editing_session import (
        build_editing_session,
        update_segment_shape_overlay,
    )

    session = update_segment_shape_overlay(
        session=build_editing_session(
            project_id="project_001",
            timeline={"timeline_id": "timeline_001"},
            segments=[{
                "segment_id": "seg_001",
                "text": "여기를 보세요",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "review_required": False,
                "cleanup_decision": "keep",
            }],
        ),
        segment_id="seg_001",
        shape="highlight_box",
        vertical="middle",
        horizontal="center",
        size="medium",
        motion="fade_in",
    )
    materialized = materialize_editing_session_timeline(
        timeline={"tracks": [], "output": {"width": 1280, "height": 720}},
        editing_session=session,
    )

    assert materialized["export_overlays"][0]["motion"] == "fade_in"

    graph = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path),
        overlay_font_file=str(tmp_path / "no-font-anywhere.ttf"),
        video_width=1280,
        video_height=720,
    ).build_plan_filter_graph(
        composition_plan=CompositionPlan.from_timeline(timeline=materialized),
        source_indices={},
    )

    assert graph.count("drawbox=") > 1, "고른 움직임이 렌더까지 닿지 않았다"


def _legacy_filter_graph(
    renderer: FfmpegFinalRenderer,
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


# --- 픽셀로 재기: 도형(drawbox) --------------------------------------------


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_a_shape_set_to_appear_slowly_really_gets_stronger(tmp_path: Path) -> None:
    """`천천히 나타나기`. 서로 다른 시각의 프레임에서 진하기가 실제로 달라야 한다."""
    video = _probe(tmp_path, "appear", _shape_overlay(motion="fade_in"))

    just_started = _strength(video, 0.55)
    halfway = _strength(video, 0.70)
    settled = _strength(video, 2.00)

    assert just_started < halfway < settled
    # 다 나타난 뒤에는 `그대로`와 같은 진하기여야 한다.
    steady = _probe(tmp_path, "appear_steady", _shape_overlay())
    assert abs(settled - _strength(steady, 2.00)) < 0.5


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_a_shape_set_to_disappear_slowly_really_gets_weaker(tmp_path: Path) -> None:
    video = _probe(tmp_path, "vanish", _shape_overlay(motion="fade_out"))

    steady = _strength(video, 1.00)
    fading = _strength(video, 2.80)
    gone = _strength(video, 3.20)

    assert gone < fading < steady
    assert gone == pytest.approx(_strength(video, 0.20), abs=0.01), "장면 밖에도 표시가 남았다"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_a_shape_set_to_appear_and_disappear_does_both(tmp_path: Path) -> None:
    video = _probe(tmp_path, "both", _shape_overlay(motion="fade_in_out"))

    entering = _strength(video, 0.58)
    middle = _strength(video, 1.70)
    leaving = _strength(video, 2.90)

    assert entering < middle
    assert leaving < middle


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_a_shape_set_to_slide_in_really_moves(tmp_path: Path) -> None:
    """`왼쪽에서 밀려 들어오기`. 자리가 실제로 옮겨져야 한다."""
    video = _probe(tmp_path, "slide", _shape_overlay(motion="slide_in_left"))

    early = _centroid_x(video, 0.58)
    later = _centroid_x(video, 0.75)
    resting = _centroid_x(video, 2.00)

    assert early is not None and later is not None and resting is not None
    assert early < later < resting
    # 도착한 자리는 움직이지 않는 같은 표시와 같아야 한다.
    steady = _probe(tmp_path, "slide_steady", _shape_overlay())
    assert resting == pytest.approx(_centroid_x(steady, 2.00), abs=1.0)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_motion_never_shows_the_shape_outside_its_own_scene(tmp_path: Path) -> None:
    """움직임을 얹었다고 장면 밖으로 새어 나오면 안 된다."""
    for motion in ("fade_in", "fade_out", "fade_in_out", "slide_in_left", "slide_in_right"):
        video = _probe(tmp_path, f"window_{motion}", _shape_overlay(motion=motion))
        blank = _strength(video, 0.20)
        assert _strength(video, 3.40) == pytest.approx(blank, abs=0.01), motion
        assert _strength(video, 1.70) > blank + 1.0, motion


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
def test_motion_fits_inside_a_very_short_scene(tmp_path: Path) -> None:
    """짧은 장면에서 움직임이 끝나기 전에 장면이 끝나면 표시가 영영 흐리다."""
    short = _shape_overlay(motion="fade_in", start_sec=0.5, end_sec=0.8)
    video = _probe(tmp_path, "short", short)

    assert _strength(video, 0.55) < _strength(video, 0.75)


@pytest.mark.skipif(
    not FFMPEG_AVAILABLE or ICON_FONT is None, reason="ffmpeg or an icon font is unavailable"
)
def test_the_plan_graph_itself_survives_ffmpeg_and_moves_the_pixels(tmp_path: Path) -> None:
    """완성본이 나오는 그래프를 **통짜로** ffmpeg에 넘겨 본다.

    `-vf`로 필터 하나만 재면 반쪽이다. 그래프 경로는 여러 필터를 `;`로 이어
    `-filter_complex`에 넘기고, 밀려 들어오기의 자리 식에는 따옴표와 쉼표가 들어
    있다. 그 파서를 통과하는지, 그리고 실제로 움직이는지 여기서 확인한다.
    """
    renderer = FfmpegFinalRenderer(
        store=LocalProjectStore(tmp_path / "store"),
        overlay_font_file=ICON_FONT,
        video_width=PROBE_WIDTH,
        video_height=PROBE_HEIGHT,
        video_fps=25,
    )

    for name, shape, motion in (
        ("graph_box", "highlight_box", "slide_in_left"),
        ("graph_icon", "icon_star", "slide_in_left"),
    ):
        graph = renderer.build_plan_filter_graph(
            composition_plan=CompositionPlan.from_timeline(timeline={
                "output": {"width": PROBE_WIDTH, "height": PROBE_HEIGHT},
                "tracks": [],
                "export_overlays": [_shape_overlay(shape=shape, motion=motion)],
            }),
            source_indices={},
        )
        output = tmp_path / f"{name}.mkv"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-filter_complex", graph, "-map", "[vout]",
             "-c:v", "ffv1", "-pix_fmt", "bgr0", str(output)],
            check=True, capture_output=True, timeout=120,
        )

        early, later, resting = (_centroid_x(output, at) for at in (0.58, 0.75, 2.00))
        assert early is not None and later is not None and resting is not None, name
        assert early < later < resting, name


# --- 픽셀로 재기: 아이콘(drawtext) ------------------------------------------


@pytest.mark.skipif(
    not FFMPEG_AVAILABLE or ICON_FONT is None, reason="ffmpeg or an icon font is unavailable"
)
def test_an_icon_set_to_appear_slowly_really_gets_stronger(tmp_path: Path) -> None:
    overlay = _shape_overlay(shape="icon_star", motion="fade_in")
    video = _probe(tmp_path, "icon_appear", overlay, font_file=ICON_FONT)

    just_started = _strength(video, 0.55)
    halfway = _strength(video, 0.70)
    settled = _strength(video, 2.00)

    assert just_started < halfway < settled
    steady = _probe(tmp_path, "icon_steady", _shape_overlay(shape="icon_star"), font_file=ICON_FONT)
    assert abs(settled - _strength(steady, 2.00)) < 0.5


@pytest.mark.skipif(
    not FFMPEG_AVAILABLE or ICON_FONT is None, reason="ffmpeg or an icon font is unavailable"
)
def test_an_icon_set_to_slide_in_really_moves(tmp_path: Path) -> None:
    overlay = _shape_overlay(shape="icon_star", motion="slide_in_right")
    video = _probe(tmp_path, "icon_slide", overlay, font_file=ICON_FONT)

    early = _centroid_x(video, 0.58)
    later = _centroid_x(video, 0.75)
    resting = _centroid_x(video, 2.00)

    assert early is not None and later is not None and resting is not None
    # 오른쪽에서 들어오므로 무게중심이 왼쪽으로 옮겨 온다.
    assert early > later > resting
    steady = _probe(tmp_path, "icon_slide_steady", _shape_overlay(shape="icon_star"),
                    font_file=ICON_FONT)
    assert resting == pytest.approx(_centroid_x(steady, 2.00), abs=1.0)
