"""장면 전환 -- 클립과 클립 사이를 넘기는 방법.

## 길이를 어떻게 맞췄는가 (이 파일에서 가장 중요한 것)

`xfade`는 보통 두 클립을 **겹쳐서** 이어 붙이므로 전체 길이가 전환 길이만큼
줄어든다. concat 모델 편집기에서는 그래서 자막이 밀린다.

**이 저장소는 concat 모델이 아니다.** `build_plan_filter_graph`는 검은 캔버스를
깔고 클립을 **각자의 타임라인 시각(PTS)에 얹는다**. 겹침은 이미 지원한다
(`test_broll_dissolve.py`가 같은 사실 위에 서 있다).

그래서 전환을 이렇게 넣었다 -- **아무것도 옮기지 않는다.**

- 전환은 들어오는 클립 B의 **첫 `d`초 안에서만** 일어난다. 구간은 `[T, T+d]`이고
  `T`는 B의 원래 시작 시각이다.
- 그 구간에 얹을 그림은 `xfade(A의 남은 원본, B의 앞부분)`이다. A는 자기 구간
  `[.., T]`을 그대로 쓰고, B도 자기 구간 `[T, ..]`을 그대로 쓴다.
- A쪽 재료는 **A가 원래 안 쓰고 남긴 원본 뒷부분**(`source_out_sec` 이후)이다.
  타임라인에서 빌려 오는 게 아니라 **원본에서** 빌려 온다.

따라서 **전체 길이·클립 시작 시각·자막 위치가 하나도 움직이지 않는다.**
치르는 값은 하나다 -- 원본이 모자라면 A의 마지막 프레임이 `d`초 동안 멎는다.
그건 `tpad=stop_mode=clone`이 맡는다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.composition_plan import CompositionPlan
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer, TransitionSources
from videobox_core_engine.transitions import (
    TRANSITION_CATALOG,
    normalize_transition,
)
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# ---------------------------------------------------------------------------
# 값 정규화
# ---------------------------------------------------------------------------


def test_the_catalog_is_small_on_purpose() -> None:
    """1,137개를 만들지 않는다. 서로 생김새가 겹치지 않는 여섯 갈래다."""
    assert len(TRANSITION_CATALOG) == 6
    assert set(TRANSITION_CATALOG) == {
        "fade", "fadeblack", "dissolve", "wipeleft", "slideup", "circleopen",
    }


def test_a_transition_records_who_chose_it() -> None:
    """유진이 골라 주는 것이 이 제품의 값어치다. 그때 자리가 있어야 한다."""
    assert normalize_transition({"type": "fade", "chosen_by": "yujin"})["chosen_by"] == "yujin"
    # 안 적으면 owner가 고른 것으로 본다. 지금 고를 수 있는 것은 owner뿐이다.
    assert normalize_transition({"type": "fade"})["chosen_by"] == "owner"


def test_no_transition_and_none_mean_the_same_thing() -> None:
    """화면에서 골랐다가 다시 끌 수 있어야 한다."""
    assert normalize_transition(None) is None
    assert normalize_transition({"type": "none"}) is None
    assert normalize_transition({"type": ""}) is None


def test_an_unknown_name_never_reaches_ffmpeg() -> None:
    """이 값은 필터 문자열로 들어간다. 모르는 값이 그대로 흘러가면 안 된다."""
    with pytest.raises(ValueError):
        normalize_transition({"type": "hologram_swirl"})
    with pytest.raises(ValueError):
        normalize_transition({"type": "fade", "duration_sec": 30.0})
    with pytest.raises(ValueError):
        normalize_transition({"type": "fade", "chosen_by": "somebody_else"})


def test_the_default_length_is_half_a_second() -> None:
    assert normalize_transition({"type": "fade"})["duration_sec"] == 0.5


# ---------------------------------------------------------------------------
# 필터 그래프
# ---------------------------------------------------------------------------


def _plan(*, transition: dict | None, gap: bool = False, second_clip_len: float = 4.0) -> CompositionPlan:
    second_start = 4.5 if gap else 4.0
    clip_b: dict = {
        "clip_id": "b", "asset_uri": "local://b",
        "start_sec": second_start, "end_sec": second_start + second_clip_len,
    }
    if transition is not None:
        clip_b["transition"] = transition
    return CompositionPlan.from_timeline(timeline={
        "output": {"width": 1280, "height": 720},
        "tracks": [{"track_type": "broll", "clips": [
            {"clip_id": "a", "asset_uri": "local://a", "start_sec": 0.0, "end_sec": 4.0},
            clip_b,
        ]}],
    })


def _graph(tmp_path: Path, plan: CompositionPlan, *, transition_indices=None) -> str:
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    # 앞 장면(a)은 원본 [0,4]를 쓰고 그 뒤가 남아 있다고 본다 -- 렌더러가
    # 실제로는 원본 길이를 재서 이 값을 정한다.
    default = {"b": TransitionSources(outgoing_index=3, incoming_index=4, outgoing_start_sec=4.0)}
    return renderer.build_plan_filter_graph(
        composition_plan=plan,
        source_indices={"a": 1, "b": 2},
        transition_source_indices=transition_indices if transition_indices is not None else default,
    )


def test_a_transition_puts_xfade_into_the_graph(tmp_path: Path) -> None:
    graph = _graph(tmp_path, _plan(transition={"type": "wipeleft", "duration_sec": 0.75}))

    assert "xfade=transition=wipeleft:duration=0.75:offset=0" in graph


def test_without_a_transition_no_xfade_is_added_at_all(tmp_path: Path) -> None:
    """안 쓰는 사람에게 필터를 더하지 않는다 -- 입력 두 개가 더 붙는 일이다."""
    graph = _graph(tmp_path, _plan(transition=None), transition_indices={})

    assert "xfade" not in graph


def test_the_total_length_does_not_move(tmp_path: Path) -> None:
    """전환을 넣어도 캔버스 길이가 그대로다. 움직이면 자막이 전부 밀린다."""
    plain = _graph(tmp_path, _plan(transition=None), transition_indices={})
    with_transition = _graph(tmp_path, _plan(transition={"type": "fade"}))

    assert ":d=8.0" in plain
    assert ":d=8.0" in with_transition


def test_neither_clip_is_moved_by_the_transition(tmp_path: Path) -> None:
    """A는 자기 자리, B도 자기 자리. 전환은 B의 첫 구간 **위에** 얹힐 뿐이다."""
    graph = _graph(tmp_path, _plan(transition={"type": "fade", "duration_sec": 0.5}))

    assert "setpts=PTS+0.0/TB[v_a]" in graph
    assert "setpts=PTS+4.0/TB[v_b]" in graph
    # 전환 자체는 B가 시작하는 바로 그 시각에 얹힌다.
    assert "setpts=PTS+4.0/TB[transition_b]" in graph


def test_the_outgoing_side_borrows_source_past_its_own_out_point(tmp_path: Path) -> None:
    """A의 재료는 **A가 원래 안 쓰고 남긴 원본 뒷부분**이다.

    타임라인에서 빌리면 A의 마지막 구간이 두 번 보인다. 원본에서 빌리면 아무
    시각도 어긋나지 않는다.
    """
    graph = _graph(tmp_path, _plan(transition={"type": "fade", "duration_sec": 0.5}))

    # A는 [0,4]에 원본 [0,4]를 쓴다. 전환은 그 다음인 원본 [4, 4.5]를 가져온다.
    assert "[3:v]trim=start=4.0:end=4.5" in graph
    # 원본이 모자랄 수 있다. 그때는 마지막 프레임을 멈춰 세워 길이를 채운다.
    assert "tpad=stop_mode=clone:stop_duration=0.5" in graph


def test_each_transition_side_ends_with_a_constant_frame_rate(tmp_path: Path) -> None:
    """`xfade`는 **고정 프레임률**이 아니면 거부한다.

    `trim`·`setpts`를 거치면 프레임률 정보가 사라지므로 `fps`가 사슬의 **맨 끝**에
    와야 한다. 그리고 `settb`를 쓰면 안 된다 -- 시간기준을 다시 잡으면 프레임률이
    `1/0`이 되어 같은 이유로 거부된다.

    이걸 어겼을 때 **개발 기기(ffmpeg 8.1)는 통과시키고 컨테이너(7.1)만 거부했다.**
    단위 테스트가 전부 초록인 채로 실물 렌더만 터졌다. 그래서 문자열로 못박는다.
    """
    graph = _graph(tmp_path, _plan(transition={"type": "fade", "duration_sec": 0.5}))

    assert "settb" not in graph, "settb는 프레임률을 지운다 -- xfade가 거부한다"
    for label in ("transition_out_1", "transition_in_1"):
        branch = next(part for part in graph.split(";") if part.endswith(f"[{label}]"))
        assert branch.endswith(f"fps=30[{label}]"), branch


def test_the_incoming_side_uses_its_own_first_frames(tmp_path: Path) -> None:
    """B는 앞당겨지지 않는다. 전환 중에 보이는 B는 B의 진짜 첫 프레임들이다."""
    graph = _graph(tmp_path, _plan(transition={"type": "fade", "duration_sec": 0.5}))

    assert "[4:v]trim=start=0.0:end=0.5" in graph


def test_a_gap_before_the_clip_means_no_transition(tmp_path: Path) -> None:
    """앞 장면이 붙어 있지 않으면 넘길 대상이 없다. 지어내지 않는다."""
    graph = _graph(tmp_path, _plan(transition={"type": "fade"}, gap=True))

    assert "xfade" not in graph


def test_a_transition_never_grows_past_the_clips_it_joins(tmp_path: Path) -> None:
    """짧은 장면에 긴 전환을 걸면 옆 장면을 먹는다. 짧은 쪽에 맞춘다."""
    plan = _plan(transition={"type": "fade", "duration_sec": 2.0}, second_clip_len=1.0)
    graph = _graph(tmp_path, plan)

    assert "duration=1.0:offset=0" in graph


def test_the_transition_is_drawn_after_both_clips(tmp_path: Path) -> None:
    """뒤에 그려야 이긴다. 앞에 그리면 B가 덮어 버려 전환이 안 보인다."""
    graph = _graph(tmp_path, _plan(transition={"type": "fade"}))

    assert graph.index("[v_b]overlay") < graph.index("[transition_b]overlay")


# ---------------------------------------------------------------------------
# 여기부터는 **실제로 mp4를 만들어** 픽셀을 잰다.
#
# 필터 문자열만 보는 위 테스트들은 "ffmpeg가 그 필터를 거부하는 경우"를 못 잡는다.
# 이 저장소가 가장 비싸게 배운 것이 "화면엔 있는데 완성본엔 안 나온다"이다.
# ---------------------------------------------------------------------------


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=180)


def _rgb_at(path: Path, *, at_sec: float, crop: str) -> tuple[int, int, int]:
    """한 시점, 한 구역의 평균 색."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path), "-frames:v", "1",
         "-vf", f"crop={crop},scale=1:1,format=rgb24", "-f", "rawvideo", "-"],
        check=True, capture_output=True, timeout=60,
    ).stdout
    return raw[0], raw[1], raw[2]


def _duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return float(probe.stdout.strip())


def _project_with_two_scenes(tmp_path: Path, *, source_sec: float = 6.0) -> tuple[LocalProjectStore, str, dict]:
    """빨강 장면 하나, 파랑 장면 하나. 색이 다르면 전환이 눈이 아니라 숫자로 보인다.

    ``source_sec``가 4.0이면 앞 장면이 원본을 **끝까지 다 쓴다** -- 전환이
    빌려 쓸 뒷부분이 한 프레임도 없는 경우다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="전환")

    narration = tmp_path / "narration.wav"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "sine=frequency=440:duration=8", str(narration)])
    narration_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration,
    )

    red = tmp_path / "red.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", f"color=c=red:s=320x240:r=15:d={source_sec}", "-pix_fmt", "yuv420p", str(red)])
    blue = tmp_path / "blue.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
          "-i", "color=c=blue:s=320x240:r=15:d=6", "-pix_fmt", "yuv420p", str(blue)])

    red_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=red)
    blue_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=blue)

    def uri(asset_id: str) -> str:
        return f"local://projects/{project.project_id}/assets/{asset_id}"

    timeline = {
        "narration_source_uri": narration_asset.storage_uri,
        "output": {"width": 320, "height": 240, "fps_num": 15, "fps_den": 1},
        "tracks": [
            {"track_type": "narration", "clips": [
                {"asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                 "start_sec": 0.0, "end_sec": 8.0},
            ]},
            {"track_type": "broll", "clips": [
                {"clip_id": "scene-a", "asset_uri": uri(red_asset.asset_id),
                 "start_sec": 0.0, "end_sec": 4.0},
                {"clip_id": "scene-b", "asset_uri": uri(blue_asset.asset_id),
                 "start_sec": 4.0, "end_sec": 8.0,
                 "transition": {"type": "wipeleft", "duration_sec": 1.0, "chosen_by": "owner"}},
            ]},
        ],
    }
    return store, project.project_id, timeline


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_a_transition_is_actually_visible_in_the_rendered_mp4(tmp_path: Path) -> None:
    """완성본을 만들어 **픽셀을 잰다.**

    빨강 장면이 [0,4], 파랑 장면이 [4,8], 경계에 1초짜리 `wipeleft`.
    전환 중(4.0~5.0)에는 화면 왼쪽이 아직 빨강이고 오른쪽이 이미 파랑이어야 한다.
    """
    store, project_id, timeline = _project_with_two_scenes(tmp_path)
    plan = CompositionPlan.from_timeline(timeline=timeline)
    output = tmp_path / "final.mp4"

    # **완성본이 나가는 바로 그 경로다** -- composition_plan을 넘기면
    # `_render_composition_plan_to_mp4`로 간다. 정확 미리보기도 같은 함수를 쓴다.
    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
        project_id=project_id, timeline=timeline, output_path=output, composition_plan=plan,
    )

    assert output.exists() and output.stat().st_size > 0

    left, right = "60:240:0:0", "60:240:260:0"
    # 전환 전 -- 온통 빨강.
    assert _rgb_at(output, at_sec=3.5, crop=left)[0] > 200
    assert _rgb_at(output, at_sec=3.5, crop=right)[0] > 200
    # 전환 중 -- 왼쪽은 아직 빨강, 오른쪽은 이미 파랑. **이게 전환이다.**
    mid_left = _rgb_at(output, at_sec=4.4, crop=left)
    mid_right = _rgb_at(output, at_sec=4.4, crop=right)
    assert mid_left[0] > 150 and mid_left[2] < 100, f"전환 중 왼쪽이 빨강이어야 한다: {mid_left}"
    assert mid_right[2] > 150 and mid_right[0] < 100, f"전환 중 오른쪽이 파랑이어야 한다: {mid_right}"
    # 전환 후 -- 온통 파랑.
    assert _rgb_at(output, at_sec=6.0, crop=left)[2] > 200
    assert _rgb_at(output, at_sec=6.0, crop=right)[2] > 200


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_a_transition_still_shows_when_the_earlier_scene_used_up_its_whole_source(tmp_path: Path) -> None:
    """앞 장면이 원본을 **끝까지 다 쓴** 경우.

    빌릴 뒷부분이 한 프레임도 없다. 이때 ffmpeg는 **실패하지 않는다** --
    성공(0)으로 끝나고 길이도 맞는데 전환만 조용히 사라진다. 실측으로 확인했고
    (`tpad`가 붙들 프레임이 없어서다) 그래서 렌더러가 마지막 프레임 자리를
    재서 넘긴다. 이 저장소가 가장 싫어하는 종류의 실패라 여기서 못박는다.
    """
    store, project_id, timeline = _project_with_two_scenes(tmp_path, source_sec=4.0)
    output = tmp_path / "exhausted.mp4"

    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
        project_id=project_id, timeline=timeline, output_path=output,
        composition_plan=CompositionPlan.from_timeline(timeline=timeline),
    )

    # 전환 중이면 왼쪽이 아직 빨강이어야 한다. 전환이 사라졌다면 이미 파랑이다.
    mid_left = _rgb_at(output, at_sec=4.4, crop="60:240:0:0")
    assert mid_left[0] > 150 and mid_left[2] < 100, f"전환이 사라졌다: {mid_left}"


def test_the_other_render_path_refuses_rather_than_dropping_the_transition(tmp_path: Path) -> None:
    """렌더 경로가 둘이다. 전환은 합성 계획 그래프에만 있다.

    조각 추출 + concat 경로(`composition_plan` 없이 부르는 쪽)는 전환을 못
    그린다. **조용히 빼고 성공하면 안 된다** -- 이 저장소는 두 경로 중 하나만
    고쳐서 같은 사고를 두 번 냈다.
    """
    store, project_id, timeline = _project_with_two_scenes(tmp_path)

    with pytest.raises(Exception, match="composition plan|composition_plan"):
        FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
            project_id=project_id, timeline=timeline, output_path=tmp_path / "concat.mp4",
        )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_the_rendered_length_is_the_same_with_and_without_a_transition(tmp_path: Path) -> None:
    """**전환을 넣어도 완성본 길이가 그대로다.**

    concat 모델이었다면 1초 짧아졌을 것이다. 그러면 자막이 전부 1초 밀린다.
    """
    store, project_id, timeline = _project_with_two_scenes(tmp_path)

    with_transition = tmp_path / "with.mp4"
    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
        project_id=project_id, timeline=timeline, output_path=with_transition,
        composition_plan=CompositionPlan.from_timeline(timeline=timeline),
    )

    plain_timeline = {
        **timeline,
        "tracks": [
            track if track["track_type"] != "broll" else {
                **track,
                "clips": [{k: v for k, v in clip.items() if k != "transition"} for clip in track["clips"]],
            }
            for track in timeline["tracks"]
        ],
    }
    without = tmp_path / "without.mp4"
    FfmpegFinalRenderer(store=store).render_timeline_to_mp4(
        project_id=project_id, timeline=plain_timeline, output_path=without,
        composition_plan=CompositionPlan.from_timeline(timeline=plain_timeline),
    )

    assert _duration(with_transition) == pytest.approx(_duration(without), abs=0.1)
    assert _duration(with_transition) == pytest.approx(8.0, abs=0.3)
