from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3
import subprocess
from threading import Barrier
from typing import Any

import pytest

from videobox_core_engine.ass_subtitles import render_editing_session_ass
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_variants import MaterializedVariant, build_variant_timeline_payload
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class _FakeFinalRenderer:
    def __init__(self) -> None:
        self.received_calls: list[dict[str, Any]] = []
        self.video_width = 1280
        self.video_height = 720

    def render_timeline_to_mp4(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None = None,
        subtitle_ass_path: Path | None = None,
        composition_plan: Any = None,
        on_progress: Any = None,
    ) -> Path:
        self.received_calls.append(
            {
                "project_id": project_id,
                "timeline": timeline,
                "output_path": output_path,
                "subtitle_file_path": subtitle_file_path,
                "subtitle_ass_path": subtitle_ass_path,
                "subtitle_ass_text": subtitle_ass_path.read_text(encoding="utf-8") if subtitle_ass_path else None,
                "composition_plan": composition_plan,
            }
        )
        if on_progress is not None:
            on_progress(100)
        output_path.write_bytes(b"fake rendered mp4 bytes")
        return output_path


def _build_approved_timeline_job(
    store: LocalProjectStore,
    runner: LocalPipelineRunner,
    project_id: str,
    narration_asset: dict[str, Any],
) -> dict[str, Any]:
    # Build a clean (no review blockers) timeline directly, bypassing
    # segment-analysis review flagging: these tests only exercise the
    # final-render wiring, not the upstream review workflow.
    timeline = runner.timeline_builder.build(
        project_id=project_id,
        segments=[
            {
                "segment_id": "seg_001",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "text": "Hello there.",
                "review_required": False,
            }
        ],
        recommendations=[],
        narration_source_uri=str(narration_asset["storage_uri"]),
    )
    timeline_payload = {
        "project_id": timeline.project_id,
        "narration_source_uri": timeline.narration_source_uri,
        "tracks": [
            {
                "track_id": track.track_id,
                "track_type": track.track_type,
                "clips": [
                    {
                        "clip_id": clip.clip_id,
                        "segment_id": clip.segment_id,
                        "asset_uri": clip.asset_uri,
                        "start_sec": clip.start_sec,
                        "end_sec": clip.end_sec,
                        "clip_type": clip.clip_type,
                        "recommendation_id": clip.recommendation_id,
                    }
                    for clip in track.clips
                ],
            }
            for track in timeline.tracks
        ],
        "review_flags": [],
        "applied_recommendations": timeline.applied_recommendations,
        "pending_recommendations": timeline.pending_recommendations,
        "recommendation_decisions": timeline.recommendation_decisions,
        "export_overlays": timeline.export_overlays,
    }
    persisted_timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode=timeline.output_mode,
        timeline_payload=timeline_payload,
    )
    timeline_job = store.create_job(
        project_id=project_id,
        job_type=JobType.TIMELINE_BUILD,
        status=JobStatus.RUNNING,
    )
    store.update_job(
        project_id=project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=persisted_timeline["timeline_id"],
    )
    runner.approve_timeline_review(project_id=project_id, timeline_job_id=timeline_job["job_id"])
    return {"job_id": timeline_job["job_id"], "timeline_id": persisted_timeline["timeline_id"]}


def test_start_final_render_persists_export_and_updates_job(tmp_path: Path) -> None:
    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final Render Pipeline Project")
    fake_renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=fake_renderer)

    narration_asset = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration_asset)

    result = runner.start_final_render(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
    )

    assert result["status"] == "succeeded"
    assert len(fake_renderer.received_calls) == 1
    assert fake_renderer.received_calls[0]["project_id"] == project.project_id
    assert fake_renderer.received_calls[0]["subtitle_file_path"] is None
    assert fake_renderer.received_calls[0]["composition_plan"] is not None

    fetched = runner.get_final_render_result(project_id=project.project_id, job_id=result["job_id"])
    assert fetched["status"] == "succeeded"
    assert fetched["render"]["export_type"] == "final_render"
    assert fetched["render"]["file_uri"].startswith(f"local://projects/{project.project_id}/exports/final_render/")


def test_variant_final_render_publishes_without_treating_derived_timeline_as_master(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Variant final render project")
    source = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={"review_flags": [], "pending_recommendations": [], "tracks": [], "segments": []},
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="draft",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variants = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )
    renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    materialized = runner._materialize_variant_for_output(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_id=variants[0]["variant_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="approved",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    batch = runner.start_variant_renders(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_ids=[variants[0]["variant_id"]],
    )
    item = batch["items"][0]

    runner.run_final_render_job(
        project_id=project.project_id,
        timeline_job_id=item["timeline_job_id"],
        job={"job_id": item["job_id"]},
    )

    result = runner.get_final_render_result(project_id=project.project_id, job_id=item["job_id"])
    assert result["status"] == "succeeded"
    assert result["render"]["timeline_id"] == materialized["timeline_id"]


def test_materialized_variant_timeline_carries_its_own_orientation_output_size(tmp_path: Path) -> None:
    """세로 변형본이 마스터의 1920x1080을 그대로 물고 오면 안 된다.

    2026-09-11 실물 측정: `project-e6c75c36`의 완성본/가로/세로 변형본이
    셋 다 1920x1080, md5까지 같았다. 마스터 payload를 베낄 때 `output`이
    같이 딸려 온 것이 원인이다 -- `_materialize_variant_for_output`은
    `kind`로 크기를 다시 정해야 한다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Variant orientation output project")
    source = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "tracks": [],
            "segments": [],
            "output": {"width": 1920, "height": 1080},
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="draft",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variants = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )
    variants_by_kind = {variant["kind"]: variant for variant in variants}
    runner = LocalPipelineRunner(store, final_renderer=_FakeFinalRenderer())

    horizontal = runner._materialize_variant_for_output(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_id=variants_by_kind["horizontal"]["variant_id"],
    )
    vertical = runner._materialize_variant_for_output(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_id=variants_by_kind["vertical_full"]["variant_id"],
    )

    horizontal_timeline = store.get_timeline_run(
        project_id=project.project_id, timeline_id=horizontal["timeline_id"]
    )
    vertical_timeline = store.get_timeline_run(
        project_id=project.project_id, timeline_id=vertical["timeline_id"]
    )
    assert horizontal_timeline["output"] == {"width": 1920, "height": 1080}
    assert vertical_timeline["output"] == {"width": 1080, "height": 1920}


def test_materialize_rebuilds_a_cache_left_by_the_old_copy_logic(tmp_path: Path) -> None:
    """`get_variant_materialization`이 있으면 무조건 재사용하던 문제.

    2026-09-11 실물 측정(project-e6c75c36): Task 1·2가 컨테이너에 올라간 뒤에도
    `가로·세로 출력 만들기`로 나온 완성본·가로·세로가 셋 다 1920x1080에 md5까지
    같았다. 원인은 캔버스 크기 결함이 아니라 **캐시**다 -- 이 owner의 변형본은
    전부 옛(버그가 있던) 조립 로직이 만든 `variant_materializations` 행을 이미
    갖고 있었고, `_materialize_variant_for_output`은 `source_variant_revision`만
    맞으면 그 행의 `timeline_id`를 그대로 돌려줬다. 버튼을 다시 눌러도 같은 낡은
    타임라인만 계속 나왔다.

    이 시험은 그 상태를 그대로 재현한다: 옛 로직이 만들었을 법한(마스터와 같은
    가로 크기, 화면 채우기로 안 고친 트랙) 타임라인을 만들어 캐시 행에 직접
    꽂아 두고, 그 다음 materialize를 호출한다. `output`이 이미 맞다는 이유로
    통과하는 시험(Task 1의 시험)과 달리, **캐시가 있을 때** 다시 만드는지를
    잰다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Variant stale cache project")
    source = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "tracks": [],
            "segments": [],
            "output": {"width": 1920, "height": 1080},
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="draft",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variants = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )
    vertical = next(variant for variant in variants if variant["kind"] == "vertical_full")

    # 옛(버그가 있던) `_materialize_variant_for_output`이 만들었을 타임라인 --
    # 마스터를 그대로 베껴 캔버스가 1920x1080이다. 이걸 캐시 행에 직접 심어서
    # "이미 있는 낡은 materialization"을 재현한다.
    stale_timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "tracks": [],
            "segments": [],
            "output": {"width": 1920, "height": 1080},
        },
    )
    store.save_variant_materialization(
        project_id=project.project_id,
        variant_id=vertical["variant_id"],
        source_session_id=vertical["source_session_id"],
        source_session_revision=vertical["source_session_revision"],
        source_variant_revision=vertical["variant_revision"],
        timeline_id=stale_timeline["timeline_id"],
        segments=[],
    )

    runner = LocalPipelineRunner(store, final_renderer=_FakeFinalRenderer())
    materialized = runner._materialize_variant_for_output(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_id=vertical["variant_id"],
    )

    rebuilt_timeline = store.get_timeline_run(
        project_id=project.project_id, timeline_id=materialized["timeline_id"]
    )
    assert materialized["timeline_id"] != stale_timeline["timeline_id"]
    assert rebuilt_timeline["output"] == {"width": 1080, "height": 1920}


def _ffprobe_dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    width_str, height_str = result.stdout.strip().split(",")
    return int(width_str), int(height_str)


def _ffprobe_duration_sec(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return float(result.stdout.strip())


def _average_rgb_at(path: Path, *, at_sec: float) -> tuple[int, int, int]:
    """그 순간의 화면을 1픽셀로 줄여 평균 색을 잰다.

    장면마다 다른 색을 넣어 두면 **어느 장면이 실제로 그 자리에 있는지**를
    타임라인 숫자가 아니라 픽셀로 가를 수 있다.
    """
    frame = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path),
            "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "pipe:1",
        ],
        capture_output=True, timeout=30,
    )
    assert frame.returncode == 0, frame.stderr.decode("utf-8", errors="replace")
    assert len(frame.stdout) >= 3, f"{at_sec}초에서 프레임을 못 뽑았다"
    return frame.stdout[0], frame.stdout[1], frame.stdout[2]


def _black_pixel_fraction(path: Path, *, width: int, height: int, at_sec: float) -> float:
    """실제 프레임 하나를 통째로 읽어 거의 검은 픽셀의 비율을 잰다.

    타임라인 숫자나 필터 문자열을 읽는 것으로는 이 결함(위아래 검은 띠)을
    못 잡는다 -- 실제로 뽑은 그림이라야 잡힌다.
    """
    frame = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ],
        capture_output=True, timeout=30,
    )
    assert frame.returncode == 0, frame.stderr.decode("utf-8", errors="replace")
    pixels = frame.stdout
    assert len(pixels) == width * height * 3
    total = width * height
    black = sum(
        1
        for index in range(0, len(pixels), 3)
        if pixels[index] < 16 and pixels[index + 1] < 16 and pixels[index + 2] < 16
    )
    return black / total


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_vertical_variant_render_actually_comes_out_vertical_and_not_mostly_black_bars(
    tmp_path: Path,
) -> None:
    """Task 2 RED: 타임라인 `output`이 1080x1920으로 고쳐져도(Task 1), 클립의
    화면 맞춤(`fit`)이 마스터(가로 캔버스에서 고른 값, 기본은 `fit`=패딩)를
    그대로 물려받으면 실제 mp4는 가운데 얇은 띠만 그림이고 위아래가 거의 다
    검은 띠다. **타임라인 숫자가 아니라 실제로 렌더한 mp4를 ffprobe·픽셀로
    잰다.**

    가로 16:9(640x360) 원본을 1080x1920 세로 캔버스에 `pad`로 넣으면:
    scale=min(1080/640, 1920/360)=1.6875 → 그림 608px, 남는 1312px(전체의
    약 68%)이 위아래 검은 띠가 된다.
    """
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Vertical output pixels")
    source = tmp_path / "landscape.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=2", "-pix_fmt", "yuv420p", str(source)],
        check=True, capture_output=True,
    )
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    master_timeline: dict[str, Any] = {
        "output": {"width": 1920, "height": 1080},
        "tracks": [
            {
                "track_type": "broll",
                "clips": [
                    {
                        "clip_id": "c1",
                        "asset_id": asset.asset_id,
                        "asset_uri": asset.storage_uri,
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        # `fit`을 아예 안 적는다 -- 대표님 실제 편집본 대다수가
                        # 이 상태다(가로 캔버스에서는 기본값의 차이가 안
                        # 보이니 안 건드린다). "안 고름"이 이 결함의 실제
                        # 조건이다.
                        "media_controls": {},
                    }
                ],
            }
        ],
    }
    derived = MaterializedVariant(
        source_session_id="session-1",
        source_session_revision=1,
        source_variant_id="variant-1",
        source_variant_revision=1,
        segments=(),
    )
    variant_timeline = build_variant_timeline_payload(
        master_timeline=master_timeline, variant_kind="vertical_full", derived=derived,
    )
    assert variant_timeline["output"] == {"width": 1080, "height": 1920}

    renderer = FfmpegFinalRenderer(store=store)
    output = tmp_path / "vertical.mp4"
    plan = renderer.extract_composition_plan(timeline=variant_timeline)
    renderer.render_timeline_to_mp4(
        project_id=project.project_id,
        timeline=variant_timeline,
        output_path=output,
        composition_plan=plan,
    )

    width, height = _ffprobe_dimensions(output)
    assert (width, height) == (1080, 1920), f"완성본 실제 크기가 세로가 아니다: {width}x{height}"

    black_fraction = _black_pixel_fraction(output, width=width, height=height, at_sec=1.0)
    assert black_fraction < 0.2, (
        f"세로 완성본 화면의 {black_fraction:.0%}가 검은 띠다 -- 화면 채우기가 "
        "아니라 위아래 패딩으로 나온 것으로 보인다."
    )


#: 마지막 장면 앞에 **일부러 둔 빈 구간**. 세션은 장면 사이에 틈을 허용한다
#: (`_validate_segment_bounds`는 겹침만 막는다) -- 장면 길이를 줄이면 실제로
#: 생긴다. 이 틈이 있어야 "숏폼은 당겨 붙인다 / 전체본은 그대로 둔다"가 서로
#: 다른 주장이 된다. 틈이 없으면 전체본을 당겨도 결과가 같아서 시험이 못 잡는다.
_SCENE_GAP_SEC = 1.0


def _three_scene_bounds() -> tuple[tuple[str, str, float, float], ...]:
    return (
        ("seg_001", "red", 0.0, 5.0),
        ("seg_002", "green", 5.0, 10.0),
        ("seg_003", "blue", 10.0 + _SCENE_GAP_SEC, 15.0 + _SCENE_GAP_SEC),
    )


def _three_scene_short_form_project(store: LocalProjectStore, tmp_path: Path) -> dict[str, Any]:
    """장면 셋(각 5초, 색이 다름)에 자막이 붙은 판 하나를 세운다."""
    project = store.bootstrap_project(name="Short form scene pick render")
    colors = tuple((segment_id, color) for segment_id, color, _start, _end in _three_scene_bounds())
    bounds = {segment_id: (start, end) for segment_id, _color, start, end in _three_scene_bounds()}
    assets: dict[str, Any] = {}
    for segment_id, color in colors:
        source = tmp_path / f"{segment_id}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=640x360:d=5",
                "-pix_fmt", "yuv420p", str(source),
            ],
            check=True, capture_output=True,
        )
        assets[segment_id] = store.register_asset(
            project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source
        )
    master = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "output": {"width": 1920, "height": 1080},
            "segments": [
                {"segment_id": segment_id, "start_sec": bounds[segment_id][0], "end_sec": bounds[segment_id][1]}
                for segment_id, _color in colors
            ],
            "tracks": [
                {
                    "track_id": "track_broll",
                    "track_type": "broll",
                    "clips": [
                        {
                            "clip_id": f"clip_{segment_id}",
                            "segment_id": segment_id,
                            "asset_id": assets[segment_id].asset_id,
                            "asset_uri": assets[segment_id].storage_uri,
                            "start_sec": bounds[segment_id][0],
                            "end_sec": bounds[segment_id][1],
                            "media_controls": {},
                        }
                        for segment_id, _color in colors
                    ],
                }
            ],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=master["timeline_id"],
        session_payload={
            "project_id": project.project_id,
            "timeline_id": master["timeline_id"],
            # `build_editing_session`이 실제로 쓰는 모양 그대로다 --
            # `source_offset_sec`/`source_slices`/`content_windows`가 있어야
            # 원본 좌표가 장면 자리와 독립이다(장면을 옮겨도 같은 그림).
            "segments": [
                {
                    "segment_id": segment_id,
                    "caption_text": f"장면{index + 1}",
                    "start_sec": bounds[segment_id][0],
                    "end_sec": bounds[segment_id][1],
                    "source_offset_sec": 0.0,
                    "source_slices": [
                        {"segment_id": segment_id, "source_offset_sec": 0.0, "duration_sec": 5.0}
                    ],
                    "cut_action": "keep",
                    "review_required": False,
                    "broll_override": None,
                    "visual_overlays": [],
                    "music_override": None,
                    "sfx_override": None,
                    "tts_replacement": None,
                    "content_windows": [
                        {
                            "caption_id": f"caption-{segment_id}",
                            "start_offset_sec": 0.0,
                            "duration_sec": 5.0,
                            "source_segment_id": segment_id,
                            "caption_text": f"장면{index + 1}",
                            "review_required": False,
                            "visual_overlays": [],
                        }
                    ],
                }
                for index, (segment_id, _color) in enumerate(colors)
            ],
            "history": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=master["timeline_id"],
        status="draft",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    store.ensure_output_variants(project_id=project.project_id, session_id=session["session_id"])
    return {"project_id": project.project_id, "session": session, "master": master}


def _render_variant_the_way_the_final_job_does(
    *, store: LocalProjectStore, project_id: str, session_id: str, variant_id: str, output_path: Path
) -> dict[str, Any]:
    """`run_final_render_job`이 렌더 직전에 밟는 순서를 그대로 밟는다.

    세션 조회 -> 세션 반영 -> 합성 계획 -> ffmpeg. 승인·게이트 배관은 다른
    시험들이 이미 지키므로 여기서는 **실제로 나온 파일**만 본다.
    """
    renderer = FfmpegFinalRenderer(store=store)
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    materialized = runner._materialize_variant_for_output(
        project_id=project_id, session_id=session_id, variant_id=variant_id
    )
    variant_timeline = store.get_timeline_run(
        project_id=project_id, timeline_id=materialized["timeline_id"]
    )
    editing_session = runner._editing_session_for_output_timeline(
        project_id=project_id, timeline=variant_timeline
    )
    materialized_timeline = materialize_editing_session_timeline(
        timeline=variant_timeline, editing_session=editing_session, project_id=project_id
    )
    plan = runner.build_composition_plan(
        timeline=variant_timeline, editing_session=editing_session, project_id=project_id
    )
    ass_text = render_editing_session_ass(
        {
            "caption_style": (editing_session or {}).get("caption_style") or {},
            "segments": [
                {
                    "caption_text": cue.text,
                    "caption_style": cue.style,
                    "start_sec": cue.start_sec,
                    "end_sec": cue.end_sec,
                }
                for cue in plan.captions
            ],
        },
        video_width=plan.width,
        video_height=plan.height,
    )
    renderer.render_timeline_to_mp4(
        project_id=project_id,
        timeline=materialized_timeline,
        output_path=output_path,
        composition_plan=plan,
    )
    return {"timeline": variant_timeline, "plan": plan, "ass_text": ass_text}


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_short_form_render_is_actually_shorter_and_moves_its_captions_with_it(
    tmp_path: Path,
) -> None:
    """Task 5 RED: 3장면 중 2장면만 고른 숏폼이 **실제로 짧아야** 한다.

    2026-09-11 실물 측정(project-e6c75c36): 유진이 3장면 중 2개를 골랐는데
    나온 파일은 **15.000초 -- 완성본과 똑같았다.** 지금까지의 시험은 전부
    `selected_segment_ids`(장면 목록)만 단언했고, **나온 파일의 길이는 아무도
    안 쟀다.** 값을 적는 것과 결과가 그렇게 되는 것은 다른 주장이다.

    그래서 이 시험은 세 가지를 **만들어진 mp4**에 대고 잰다:
    1. 길이가 10초(2장면 x 5초)다 -- 15초가 아니다.
    2. 0초에 고른 첫 장면(초록)이 있다 -- 버린 장면(빨강)이 아니다.
    3. 자막이 함께 앞으로 온다 -- 5초 늦은 자막은 숏폼이 아니다.
    """
    store = LocalProjectStore(tmp_path)
    scenario = _three_scene_short_form_project(store, tmp_path)
    short = store.create_output_variant(
        project_id=scenario["project_id"],
        source_session_id=scenario["session"]["session_id"],
        kind="vertical_highlight",
        selected_segment_ids=["seg_002", "seg_003"],
    )
    assert short["selected_segment_ids"] == ["seg_002", "seg_003"]

    output = tmp_path / "short.mp4"
    rendered = _render_variant_the_way_the_final_job_does(
        store=store,
        project_id=scenario["project_id"],
        session_id=scenario["session"]["session_id"],
        variant_id=short["variant_id"],
        output_path=output,
    )

    duration = _ffprobe_duration_sec(output)
    assert duration == pytest.approx(10.0, abs=0.25), (
        f"숏폼이 안 짧아졌다: {duration:.3f}초 (2장면 x 5초 = 10초여야 한다)"
    )
    assert _ffprobe_dimensions(output) == (1080, 1920)

    # 버린 장면(빨강)이 앞에 남아 있지 않은가 -- 픽셀로 가른다.
    red, green, blue = _average_rgb_at(output, at_sec=1.0)
    assert green > 100 and red < 80, (
        f"숏폼 1초 지점이 고른 첫 장면(초록)이 아니다: rgb=({red},{green},{blue}) -- "
        "버린 도입부가 그대로 앞에 남은 것으로 보인다."
    )
    red, green, blue = _average_rgb_at(output, at_sec=6.0)
    assert blue > 100 and red < 80, (
        f"숏폼 6초 지점이 고른 둘째 장면(파랑)이 아니다: rgb=({red},{green},{blue})"
    )

    # 자막도 같이 앞으로 와야 한다. 5초 늦은 자막이면 숏폼이 아니다.
    cues = [(round(cue.start_sec, 3), round(cue.end_sec, 3), cue.text) for cue in rendered["plan"].captions]
    assert cues == [(0.0, 5.0, "장면2"), (5.0, 10.0, "장면3")], f"자막 자리가 안 옮겨졌다: {cues}"
    assert "Dialogue: 0,0:00:00.00,0:00:05.00" in rendered["ass_text"]
    assert "장면1" not in rendered["ass_text"]


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_vertical_full_render_is_never_retimed_by_the_short_form_fix(tmp_path: Path) -> None:
    """세로 **전체본**은 당겨 붙이지 않는다 -- 같은 이야기, 다른 화면비다.

    전체본은 마스터와 장면 구성·순서가 완전히 같아야 하고, 다르면
    `materialize_variant`가 `vertical_full_segment_order_or_membership_changed`로
    거부한다. 숏폼을 짧게 만드는 고침이 전체본에도 새면 그 뜻이 깨지므로,
    **나온 파일 길이와 장면 순서를 실제로 잰다.**
    """
    store = LocalProjectStore(tmp_path)
    scenario = _three_scene_short_form_project(store, tmp_path)
    variants = store.list_output_variants(
        project_id=scenario["project_id"], session_id=scenario["session"]["session_id"]
    )
    vertical_full = next(variant for variant in variants if variant["kind"] == "vertical_full")

    output = tmp_path / "vertical_full.mp4"
    rendered = _render_variant_the_way_the_final_job_does(
        store=store,
        project_id=scenario["project_id"],
        session_id=scenario["session"]["session_id"],
        variant_id=vertical_full["variant_id"],
        output_path=output,
    )

    duration = _ffprobe_duration_sec(output)
    expected = 15.0 + _SCENE_GAP_SEC
    assert duration == pytest.approx(expected, abs=0.25), (
        f"세로 전체본 길이가 마스터와 달라졌다: {duration:.3f}초 ({expected}초여야 한다)"
    )
    assert [segment["segment_id"] for segment in rendered["timeline"]["segments"]] == [
        "seg_001", "seg_002", "seg_003",
    ]
    # **빈 구간까지 그대로다.** 마지막 장면은 11초에서 시작한다 -- 당겨 붙이면
    # 10초로 오고 그러면 마스터와 다른 이야기가 된다.
    assert [(segment["start_sec"], segment["end_sec"]) for segment in rendered["timeline"]["segments"]] == [
        (0.0, 5.0), (5.0, 10.0), (10.0 + _SCENE_GAP_SEC, 15.0 + _SCENE_GAP_SEC),
    ]
    # 세 장면이 각자 자기 자리에 그대로 있다 -- 색으로 가른다.
    assert _average_rgb_at(output, at_sec=1.0)[0] > 100  # 빨강
    assert _average_rgb_at(output, at_sec=6.0)[1] > 100  # 초록
    assert _average_rgb_at(output, at_sec=12.0)[2] > 100  # 파랑
    cues = [(round(cue.start_sec, 3), round(cue.end_sec, 3), cue.text) for cue in rendered["plan"].captions]
    assert cues == [
        (0.0, 5.0, "장면1"),
        (5.0, 10.0, "장면2"),
        (10.0 + _SCENE_GAP_SEC, 15.0 + _SCENE_GAP_SEC, "장면3"),
    ]


def test_final_render_does_not_publish_when_session_changes_after_last_pipeline_check(tmp_path: Path) -> None:
    """The storage publish fence, not a timing assumption, owns the final CAS."""
    class _SessionMutatingPublishStore(LocalProjectStore):
        def save_final_render(self, **kwargs: Any) -> dict[str, Any]:
            session_id = str(kwargs["source_session_id"])
            expected_revision = int(kwargs["source_session_revision"])
            session = self.get_editing_session(project_id=str(kwargs["project_id"]), session_id=session_id)
            self.update_editing_session(
                project_id=str(kwargs["project_id"]),
                session_id=session_id,
                session_payload=session,
                expected_revision=expected_revision,
            )
            return super().save_final_render(**kwargs)

    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")
    store = _SessionMutatingPublishStore(tmp_path)
    project = store.bootstrap_project(name="Final render publish session fence")
    renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration)
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_job["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    with pytest.raises(RuntimeError, match="final_render_session_revision_changed"):
        runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    assert len(renderer.received_calls) == 1
    assert list((store.project_root(project.project_id) / "exports" / "final_render").glob("export_*")) == []
    assert store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])["session_revision"] == 2


def test_final_render_does_not_publish_when_review_reopens_after_last_pipeline_check(
    tmp_path: Path,
) -> None:
    """The publish transaction must reject a post-render review reopen."""

    class _ReviewReopeningPublishStore(LocalProjectStore):
        def save_final_render(self, **kwargs: Any) -> dict[str, Any]:
            self.save_review_state(
                project_id=str(kwargs["project_id"]),
                timeline_id=str(kwargs["timeline_id"]),
                status="draft",
            )
            return super().save_final_render(**kwargs)

    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")
    store = _ReviewReopeningPublishStore(tmp_path)
    project = store.bootstrap_project(name="Final render publish review fence")
    renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    narration = runner.register_narration_asset(
        project_id=project.project_id,
        source_path=raw_audio,
    )
    timeline_job = _build_approved_timeline_job(
        store,
        runner,
        project.project_id,
        narration,
    )

    with pytest.raises(RuntimeError, match="final_render_source_fence_failed"):
        runner.start_final_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job["job_id"],
        )

    assert len(renderer.received_calls) == 1
    assert (
        list(
            (store.project_root(project.project_id) / "exports" / "final_render").glob(
                "export_*"
            )
        )
        == []
    )
    assert store.get_review_state(
        project_id=project.project_id,
        timeline_id=timeline_job["timeline_id"],
    )["status"] == "draft"


def test_final_render_rechecks_materialized_source_inside_publish_fence(tmp_path: Path) -> None:
    """A byte replacement after pipeline validation cannot gain an export pointer."""
    class _SourceMutatingPublishStore(LocalProjectStore):
        source_path: Path

        def save_final_render(self, **kwargs: Any) -> dict[str, Any]:
            self.source_path.write_bytes(b"replaced after final pipeline validation")
            return super().save_final_render(**kwargs)

    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"original narration bytes")
    store = _SourceMutatingPublishStore(tmp_path)
    project = store.bootstrap_project(name="Final render publish source fence")
    runner = LocalPipelineRunner(store, final_renderer=_FakeFinalRenderer())
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration)
    timeline = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_job["timeline_id"])
    narration_clip = next(
        clip
        for track in timeline["tracks"]
        if track["track_type"] == "narration"
        for clip in track["clips"]
    )
    narration_clip["asset_id"] = narration["asset_id"]
    narration_clip["asset_uri"] = narration["storage_uri"]
    store.source_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=narration_clip["asset_uri"])
    narration_clip["expected_content_sha256"] = sha256(store.source_path.read_bytes()).hexdigest()
    store.update_timeline_run(
        project_id=project.project_id,
        timeline_id=timeline_job["timeline_id"],
        timeline_payload=timeline,
    )

    with pytest.raises(RuntimeError, match="stale_output_asset: content SHA-256 changed"):
        runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    assert list((store.project_root(project.project_id) / "exports" / "final_render").glob("export_*")) == []


def test_final_render_rechecks_revision_only_source_inside_publish_fence(tmp_path: Path) -> None:
    """Revision-only legacy materializations need the same final publish fence."""
    class _RevisionMutatingPublishStore(LocalProjectStore):
        asset_id: str

        def save_final_render(self, **kwargs: Any) -> dict[str, Any]:
            connection = sqlite3.connect(self.database_path(str(kwargs["project_id"])))
            try:
                connection.execute(
                    "UPDATE assets SET created_at = ? WHERE project_id = ? AND asset_id = ?",
                    ("2099-01-01T00:00:00+00:00", str(kwargs["project_id"]), self.asset_id),
                )
                connection.commit()
            finally:
                connection.close()
            return super().save_final_render(**kwargs)

    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"revision-only narration bytes")
    store = _RevisionMutatingPublishStore(tmp_path)
    project = store.bootstrap_project(name="Final render revision-only publish fence")
    runner = LocalPipelineRunner(store, final_renderer=_FakeFinalRenderer())
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration)
    timeline = store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_job["timeline_id"])
    narration_clip = next(
        clip
        for track in timeline["tracks"]
        if track["track_type"] == "narration"
        for clip in track["clips"]
    )
    narration_clip["asset_id"] = narration["asset_id"]
    narration_clip["asset_uri"] = narration["storage_uri"]
    narration_clip["media_revision"] = store.get_asset(
        project_id=project.project_id, asset_id=narration["asset_id"]
    )["created_at"]
    store.asset_id = narration["asset_id"]
    store.update_timeline_run(
        project_id=project.project_id,
        timeline_id=timeline_job["timeline_id"],
        timeline_payload=timeline,
    )

    with pytest.raises(RuntimeError, match="stale_output_asset: media revision changed"):
        runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    assert list((store.project_root(project.project_id) / "exports" / "final_render").glob("export_*")) == []


def test_final_render_publish_cleans_private_stage_when_copy_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final render stage cleanup")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []},
    )
    source = tmp_path / "output.mp4"
    source.write_bytes(b"rendered output")

    def fail_copy(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("injected final render stage copy failure")

    monkeypatch.setattr("videobox_storage.local_project_store.shutil.copy2", fail_copy)

    with pytest.raises(OSError, match="injected final render stage copy failure"):
        store.save_final_render(
            project_id=project.project_id,
            timeline_id=timeline["timeline_id"],
            source_output_path=source,
        )

    final_root = store.project_root(project.project_id) / "exports" / "final_render"
    assert list(final_root.glob(".*.staging")) == []


def test_concurrent_final_publishes_allocate_distinct_transactional_export_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Concurrent final render IDs")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={"tracks": [], "review_flags": [], "pending_recommendations": []},
    )
    first, second = tmp_path / "first.mp4", tmp_path / "second.mp4"
    first.write_bytes(b"first final")
    second.write_bytes(b"second final")
    barrier = Barrier(2)
    from videobox_storage import local_project_store

    original_copy2 = local_project_store.shutil.copy2

    def synchronize_stage_copy(*args: Any, **kwargs: Any) -> Any:
        barrier.wait(timeout=5)
        return original_copy2(*args, **kwargs)

    monkeypatch.setattr(local_project_store.shutil, "copy2", synchronize_stage_copy)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda source: store.save_final_render(
                project_id=project.project_id, timeline_id=timeline["timeline_id"], source_output_path=source,
            ),
            (first, second),
        ))

    assert {result["export_id"] for result in results} == {"export_001", "export_002"}
    assert all(store.resolve_storage_uri(project_id=project.project_id, storage_uri=result["file_uri"]).is_file() for result in results)


def test_final_entrypoint_blocks_stale_review_and_subtitle_until_regenerated(tmp_path: Path) -> None:
    """Task 12 E2E: stale durable dependencies stop before the renderer call."""
    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final stale output gate")
    fake_renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=fake_renderer)
    narration = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration)
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline_job["timeline_id"], session_payload={"segments": [], "history": []})
    store.save_subtitle_run(project_id=project.project_id, timeline_id=timeline_job["timeline_id"], subtitle_payload={"entries": []})
    store.update_editing_session(project_id=project.project_id, session_id=session["session_id"], session_payload={"segments": [], "history": []}, expected_revision=session["session_revision"])
    # Reapproval clears the review gate; stale subtitle remains and must be
    # rejected by the output freshness verifier itself.
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])
    with pytest.raises(RuntimeError, match="stale_output_asset"):
        runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])
    assert fake_renderer.received_calls == []
    runner.start_subtitle_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])
    recovered = runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])
    assert recovered["status"] == "succeeded"
    assert len(fake_renderer.received_calls) == 1


def test_start_final_render_passes_latest_subtitle_file_path_to_renderer(tmp_path: Path) -> None:
    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final Render Subtitle Wiring Project")
    fake_renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=fake_renderer)

    narration_asset = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration_asset)

    persisted_subtitle = store.save_subtitle_run(
        project_id=project.project_id,
        timeline_id=timeline_job["timeline_id"],
        subtitle_payload={
            "format": "srt",
            "entries": [{"index": 1, "start_sec": 0.0, "end_sec": 2.0, "text": "Hello there."}],
        },
    )

    result = runner.start_final_render(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
    )

    assert result["status"] == "succeeded"
    received_subtitle_path = fake_renderer.received_calls[0]["subtitle_file_path"]
    assert received_subtitle_path is not None
    assert received_subtitle_path == store.resolve_storage_uri(
        project_id=project.project_id, storage_uri=persisted_subtitle["file_uri"]
    )
    assert received_subtitle_path.exists()


def test_start_final_render_derives_ass_from_matching_editing_session(tmp_path: Path) -> None:
    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final Render Styled Session")
    fake_renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=fake_renderer)
    narration_asset = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration_asset)
    store.save_editing_session(project_id=project.project_id, timeline_id=timeline_job["timeline_id"], session_payload={"project_id": project.project_id, "timeline_id": timeline_job["timeline_id"], "caption_style": {"text_color": "#FF0000FF"}, "segments": [{"segment_id": "seg_001", "caption_text": "Styled output", "start_sec": 0.0, "end_sec": 2.0}], "history": []})
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    ass_path = fake_renderer.received_calls[0]["subtitle_ass_path"]
    assert ass_path is not None
    assert "Styled output" in fake_renderer.received_calls[0]["subtitle_ass_text"]


def test_final_render_keeps_windowed_right_caption_style_after_merge(tmp_path: Path) -> None:
    from videobox_core_engine.editing_session import merge_adjacent_segments

    raw_audio = tmp_path / "narration.wav"
    raw_audio.write_bytes(b"fake wav data")
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final Render Windowed Caption Style")
    fake_renderer = _FakeFinalRenderer()
    runner = LocalPipelineRunner(store, final_renderer=fake_renderer)
    narration_asset = runner.register_narration_asset(project_id=project.project_id, source_path=raw_audio)
    timeline_job = _build_approved_timeline_job(store, runner, project.project_id, narration_asset)
    merged = merge_adjacent_segments(session={
        "segments": [
            {"segment_id": "left", "caption_text": "left", "caption_style": {"text_color": "#FFFFFFFF"}, "start_sec": 0.0, "end_sec": 1.0, "cut_action": "keep", "visual_overlays": []},
            {"segment_id": "right", "caption_text": "right", "caption_style": {"text_color": "#FF0000FF"}, "start_sec": 1.0, "end_sec": 2.0, "cut_action": "keep", "visual_overlays": []},
        ],
        "history": [], "undo_stack": [], "redo_stack": [], "session_revision": 1,
    }, left_segment_id="left", right_segment_id="right")
    store.save_editing_session(
        project_id=project.project_id, timeline_id=timeline_job["timeline_id"],
        session_payload={"project_id": project.project_id, "timeline_id": timeline_job["timeline_id"], **merged},
    )
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    runner.start_final_render(project_id=project.project_id, timeline_job_id=timeline_job["job_id"])

    ass = str(fake_renderer.received_calls[0]["subtitle_ass_text"])
    # The default 54 px logical style scales to 96 px at the 1920 px ASS
    # play resolution; keep the right caption's red color after the merge.
    assert "Style: Segment1,Pretendard,96,&H000000FF" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.00,Segment1,,0,0,0,,right" in ass


# ---------------------------------------------------------------------------
# 2026-09-12 대표님 실제 영상(494.837초, 1920x1080) 실측에서 잡힌 결함 셋.
#
# 자료실 영상 하나를 빈 편집판 장면에 깔고(`broll_override`) 장면을 94개로
# 쪼갠 뒤 숏폼을 만들었더니:
#   1. 그림이 고른 장면이 아니라 **원본 맨 앞 8초의 반복**이었다.
#   2. 화면의 **68.3%가 검은 띠**였다.
#   3. `mean_volume -91.0 dB`, 완전한 **무음**이었다.
#
# 셋 다 **나온 mp4를 재야** 보인다 -- 세션에 저장된 값은 셋 다 "정상"이었다.
# 그래서 여기 시험은 실제로 렌더하고 ffprobe·픽셀·dB로 잰다.
#
# 원본은 **시각을 색으로 심어** 만든다: T초 화면이 (R,G,B)=(2T, 255-2T, 120).
# 숏폼 어느 시각의 픽셀을 읽으면 원본 어느 초인지 역산할 수 있다 -- 대표님
# 영상에 구워진 자막으로 순간을 특정한 것과 같은 방법이다.
# ---------------------------------------------------------------------------

_REAL_FLOW_SOURCE_SEC = 30.0
_REAL_FLOW_SCENE_SEC = 10.0


def _timecoded_source(path: Path, *, seconds: float = _REAL_FLOW_SOURCE_SEC) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=black:s=32x18:r=30:d={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
            "-vf", "geq=r=2*T:g=255-2*T:b=120,scale=1920:1080:flags=neighbor",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True, capture_output=True,
    )


def _source_second_shown_at(path: Path, *, at_sec: float, width: int, height: int) -> float:
    """숏폼 `at_sec`의 가운데 픽셀이 가리키는 **원본 초**."""
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        capture_output=True, timeout=60,
    )
    assert frame.returncode == 0, frame.stderr.decode("utf-8", errors="replace")
    pixels = frame.stdout
    assert len(pixels) == width * height * 3
    index = ((height // 2) * width + width // 2) * 3
    red, green = pixels[index], pixels[index + 1]
    return (red + (255 - green)) / 4.0


def _band_brightness(path: Path, *, at_sec: float, width: int, height: int) -> tuple[float, float, float]:
    """위/가운데/아래 가로 띠의 평균 밝기(0~255). 검은 띠는 여기서 0 근처로 나온다."""
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(at_sec), "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
        capture_output=True, timeout=60,
    )
    assert frame.returncode == 0, frame.stderr.decode("utf-8", errors="replace")
    pixels = frame.stdout
    assert len(pixels) == width * height
    band = height // 4

    def average(top: int, bottom: int) -> float:
        chunk = pixels[top * width:bottom * width]
        return sum(chunk) / len(chunk)

    return (
        average(0, band),
        average(height // 2 - band // 2, height // 2 + band // 2),
        average(height - band, height),
    )


def _mean_volume_db(path: Path) -> float:
    """**소리는 길이가 아니라 음량으로 잰다.** 스트림이 있어도 무음일 수 있다."""
    result = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    raise AssertionError(f"volumedetect가 mean_volume을 안 냈다: {result.stderr[-500:]}")


def _render_short_form_from_one_long_video(tmp_path: Path) -> dict[str, Any]:
    """대표님이 실제로 밟은 길을 그대로 밟고 숏폼 mp4를 돌려준다.

    빈 편집판 -> 자료실 영상을 장면에 깔기 -> 장면 길이를 영상 길이로 ->
    쪼개기 -> 숏폼 변형본 -> 렌더. 전부 제품 자신의 함수를 쓴다.
    """
    from videobox_core_engine import editing_session as session_ops
    from videobox_core_engine.blank_editing_session import (
        build_blank_editing_session,
        build_blank_timeline_payload,
    )
    from videobox_core_engine.output_variants import materialize_variant, variant_render_session
    from videobox_domain_models.output_variants import OutputVariant

    store = LocalProjectStore(tmp_path / "store")
    project = store.bootstrap_project(name="Real flow short form")
    source = tmp_path / "long.mp4"
    _timecoded_source(source)
    asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source
    )

    session = build_blank_editing_session(project_id=project.project_id, timeline_id="timeline_001")
    scene_id = session["segments"][0]["segment_id"]
    session = session_ops.update_segment_broll_override(
        session=session, segment_id=scene_id, asset_id=asset.asset_id, media_controls={}
    )
    session = session_ops.set_segment_bounds(
        session=session, segment_id=scene_id, start_sec=0.0, end_sec=_REAL_FLOW_SOURCE_SEC
    )
    for cut in (_REAL_FLOW_SCENE_SEC, _REAL_FLOW_SCENE_SEC * 2):
        target = next(
            item["segment_id"] for item in session["segments"]
            if item["start_sec"] < cut < item["end_sec"]
        )
        session = session_ops.split_segment(session=session, segment_id=target, split_sec=cut)
    for segment in session["segments"]:
        segment["review_required"] = False

    timeline = build_blank_timeline_payload()
    timeline["timeline_id"] = "timeline_001"
    timeline["project_id"] = project.project_id

    picked = (session["segments"][0]["segment_id"], session["segments"][2]["segment_id"])
    variant = OutputVariant(
        variant_id="variant-1", kind="vertical_highlight", variant_revision=1,
        source_session_id="editing_session_001",
        source_session_revision=int(session["session_revision"]),
        selected_segment_ids=picked,
    )
    derived = materialize_variant(variant, session["segments"])
    variant_timeline = build_variant_timeline_payload(
        master_timeline=timeline, variant_kind="vertical_highlight", derived=derived,
    )
    variant_timeline["timeline_id"] = "timeline_002"
    variant_timeline["project_id"] = project.project_id
    render_session = variant_render_session(master_session=session, variant_timeline=variant_timeline)

    renderer = FfmpegFinalRenderer(store=store)
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    materialized = materialize_editing_session_timeline(
        timeline=variant_timeline, editing_session=render_session, project_id=project.project_id,
    )
    plan = runner.build_composition_plan(
        timeline=variant_timeline, editing_session=render_session, project_id=project.project_id,
    )
    output = tmp_path / "short.mp4"
    renderer.render_timeline_to_mp4(
        project_id=project.project_id, timeline=materialized,
        output_path=output, composition_plan=plan,
    )
    width, height = _ffprobe_dimensions(output)
    return {"output": output, "width": width, "height": height}


@pytest.fixture(scope="module")
def real_flow_short_form(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    if not FFMPEG_AVAILABLE:
        pytest.skip("ffmpeg/ffprobe not installed on this machine")
    return _render_short_form_from_one_long_video(tmp_path_factory.mktemp("real_flow"))


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_short_form_shows_each_picked_moment_not_the_start_of_the_source(
    real_flow_short_form: dict[str, Any],
) -> None:
    """**그림이 고른 장면이어야 한다.**

    쪼갠 장면이 `broll_override.media_controls.trim_start_sec`을 안 옮겨서, 고른
    장면 열 개가 전부 원본 0초부터 다시 시작했다. `loop: true`가 기본이라 길이만
    맞고 그림은 계속 맨 앞이었다 -- "61초짜리 숏폼"이 사실은 앞 8초의 반복.
    """
    output = real_flow_short_form["output"]
    width, height = real_flow_short_form["width"], real_flow_short_form["height"]
    # 1번째 장면(원본 0~10초)의 1초 지점 -> 원본 1초.
    first = _source_second_shown_at(output, at_sec=1.0, width=width, height=height)
    assert abs(first - 1.0) < 2.0, f"숏폼 1초가 원본 {first:.2f}초를 보여 준다(1초여야 함)"
    # 3번째 장면(원본 20~30초)의 1초 지점 -> 원본 21초. **여기가 무너졌던 자리다.**
    second = _source_second_shown_at(
        output, at_sec=_REAL_FLOW_SCENE_SEC + 1.0, width=width, height=height
    )
    assert abs(second - 21.0) < 2.0, (
        f"숏폼 11초가 원본 {second:.2f}초를 보여 준다(21초여야 함) -- "
        "쪼갠 장면이 b-roll의 맨 앞을 다시 보여 주고 있다."
    )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_short_form_broll_laid_on_a_scene_fills_the_vertical_frame(
    real_flow_short_form: dict[str, Any],
) -> None:
    """**검은 띠가 없어야 한다.**

    `build_variant_timeline_payload`의 화면 채우기는 **마스터 타임라인의 트랙
    클립**만 고친다. 자료실 영상을 장면에 까는 화면 경로(`broll_override`)로
    들어온 클립은 렌더 때 세션에서 새로 만들어지므로 그 길을 안 지난다 --
    대표님 편집본은 트랙이 비어 있어 화면 전체가 이 경로였고, 실측 68.3%가
    검은 띠였다.
    """
    output = real_flow_short_form["output"]
    width, height = real_flow_short_form["width"], real_flow_short_form["height"]
    assert (width, height) == (1080, 1920)
    for at_sec in (1.0, _REAL_FLOW_SCENE_SEC + 1.0):
        top, middle, bottom = _band_brightness(output, at_sec=at_sec, width=width, height=height)
        assert top > 16.0 and bottom > 16.0, (
            f"{at_sec}초에서 위={top:.1f} 가운데={middle:.1f} 아래={bottom:.1f} -- "
            "위아래가 검은 띠다."
        )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_short_form_from_a_talking_video_is_not_silent(
    real_flow_short_form: dict[str, Any],
) -> None:
    """**소리가 들려야 한다.** 스트림이 아니라 음량으로 잰다.

    빈 편집판에는 내레이션 트랙이 없다. 그 판에 깐 영상의 소리가 곧 말소리인데
    `preserve_source_audio` 기본값이 꺼짐이라 통째로 버려졌다 -- 실측 -91.0 dB.
    """
    measured = _mean_volume_db(real_flow_short_form["output"])
    assert measured > -60.0, f"숏폼이 사실상 무음이다: mean_volume {measured:.1f} dB"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on this machine")
def test_a_looping_broll_shorter_than_its_scene_still_renders_after_a_split(tmp_path: Path) -> None:
    """쪼갠 장면의 b-roll 시작점이 원본 끝을 넘어도 렌더는 살아 있어야 한다.

    장식용 짧은 b-roll은 `loop`로 장면을 채운다. 장면을 쪼개면 시작점이 앞으로
    가는데, 3초짜리 원본을 5초 지점부터 쓰라고 하면 예전 검사가 렌더를 통째로
    죽였다(`B-roll source bounds are outside the available media`). 되풀이 중에
    "원본 끝을 지났다"는 곧 "처음으로 돌아왔다"는 뜻이다.
    """
    from videobox_core_engine import editing_session as session_ops
    from videobox_core_engine.blank_editing_session import (
        build_blank_editing_session,
        build_blank_timeline_payload,
    )

    store = LocalProjectStore(tmp_path / "store")
    project = store.bootstrap_project(name="Short looping broll")
    source = tmp_path / "decor.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3",
         "-pix_fmt", "yuv420p", str(source)],
        check=True, capture_output=True,
    )
    asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source
    )
    session = build_blank_editing_session(project_id=project.project_id, timeline_id="timeline_001")
    scene_id = session["segments"][0]["segment_id"]
    session = session_ops.update_segment_broll_override(
        session=session, segment_id=scene_id, asset_id=asset.asset_id, media_controls={}
    )
    session = session_ops.set_segment_bounds(
        session=session, segment_id=scene_id, start_sec=0.0, end_sec=10.0
    )
    session = session_ops.split_segment(session=session, segment_id=scene_id, split_sec=5.0)
    for segment in session["segments"]:
        segment["review_required"] = False
    assert [
        segment["broll_override"]["media_controls"]["trim_start_sec"]
        for segment in session["segments"]
    ] == [0.0, 5.0]

    timeline = build_blank_timeline_payload()
    timeline["timeline_id"] = "timeline_001"
    timeline["project_id"] = project.project_id
    renderer = FfmpegFinalRenderer(store=store)
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=session, project_id=project.project_id,
    )
    plan = runner.build_composition_plan(
        timeline=timeline, editing_session=session, project_id=project.project_id,
    )
    output = tmp_path / "out.mp4"
    renderer.render_timeline_to_mp4(
        project_id=project.project_id, timeline=materialized,
        output_path=output, composition_plan=plan,
    )
    assert output.stat().st_size > 0
