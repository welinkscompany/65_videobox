"""선택 장면 리플 배속의 공통 출력 계약.

손으로 완성 track을 붙이지 않는다. 제품이 만드는 editing session을 먼저 만든 뒤
그 세션을 materialize해서 preview·render·export가 함께 읽을 시간축을 확인한다.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from videobox_domain_models.assets import AssetType
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.composition_plan import materialize_editing_session_timeline
from videobox_core_engine.editing_session import apply_yujin_editing_proposal, build_editing_session, set_segment_ripple_playback_rate
from videobox_domain_models.yujin_editing_proposals import YujinEditingProposal
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_storage.local_project_store import LocalProjectStore


def _source_timeline() -> dict:
    clips = lambda prefix: [
        {"clip_id": f"{prefix}-1", "segment_id": "scene-1", "asset_uri": f"local://{prefix}-1", "start_sec": 0.0, "end_sec": 4.0},
        {"clip_id": f"{prefix}-2", "segment_id": "scene-2", "asset_uri": f"local://{prefix}-2", "start_sec": 4.0, "end_sec": 8.0},
        {"clip_id": f"{prefix}-3", "segment_id": "scene-3", "asset_uri": f"local://{prefix}-3", "start_sec": 8.0, "end_sec": 12.0},
    ]
    broll = clips("broll")
    broll[1]["media_controls"] = {"speed": 1.5}
    return {
        "project_id": "project-ripple",
        "timeline_id": "timeline-ripple",
        "output": {"width": 1080, "height": 1920, "duration_sec": 12.0},
        "tracks": [
            {"track_type": "narration", "clips": clips("narration")},
            {"track_type": "broll", "clips": broll},
            {"track_type": "sfx", "clips": clips("sfx")},
            {"track_type": "bgm", "clips": [
                {"clip_id": "bgm-global", "asset_uri": "local://bgm", "start_sec": 0.0, "end_sec": 12.0},
            ]},
        ],
    }


def _session(timeline: dict) -> dict:
    return build_editing_session(
        project_id="project-ripple",
        timeline=timeline,
        segments=[
            {"segment_id": "scene-1", "text": "첫 장면", "start_sec": 0.0, "end_sec": 4.0},
            {"segment_id": "scene-2", "text": "둘째 장면", "start_sec": 4.0, "end_sec": 8.0},
            {"segment_id": "scene-3", "text": "셋째 장면", "start_sec": 8.0, "end_sec": 12.0},
        ],
    )


def _clip(materialized: dict, track_type: str, clip_id: str) -> dict:
    return next(
        clip
        for track in materialized["tracks"]
        if track["track_type"] == track_type
        for clip in track["clips"]
        if clip["clip_id"] == clip_id
    )


def test_ripple_speed_materializes_one_shared_video_voice_caption_and_audio_timeline() -> None:
    timeline = _source_timeline()
    session = set_segment_ripple_playback_rate(
        session=_session(timeline), segment_id="scene-2", rate=2.0,
    )

    materialized = materialize_editing_session_timeline(
        timeline=timeline,
        editing_session=session,
        project_id="project-ripple",
    )

    for track_type in ("narration", "broll", "sfx"):
        middle = _clip(materialized, track_type, f"{track_type}-2")
        later = _clip(materialized, track_type, f"{track_type}-3")
        assert (middle["start_sec"], middle["end_sec"]) == (4.0, 6.0)
        assert (later["start_sec"], later["end_sec"]) == (6.0, 10.0)
        assert middle["playback_rate"] == 2.0

    # 장면 배속과 B-roll 자체 속도는 서로 다른 편집이다. 실제 출력 비율은 곱한다.
    assert _clip(materialized, "broll", "broll-2")["effective_playback_rate"] == 3.0
    # session에서 만든 caption window도 정확히 같은 축으로 줄어야 한다.
    middle_caption = next(cue for cue in materialized["session_captions"] if cue["segment_id"] == "scene-2")
    assert (middle_caption["start_sec"], middle_caption["end_sec"]) == (4.0, 6.0)
    # 전역 배경 음악은 빨라지지 않지만, 짧아진 완성본 끝(10초)에서 멈춘다.
    bgm = _clip(materialized, "bgm", "bgm-global")
    assert (bgm["start_sec"], bgm["end_sec"]) == (0.0, 10.0)
    assert bgm.get("playback_rate", 1.0) == 1.0


def test_ai_applied_speed_proposal_materializes_the_shared_output_timeline() -> None:
    timeline = _source_timeline()
    session = apply_yujin_editing_proposal(
        session=_session(timeline),
        proposal=YujinEditingProposal.model_validate({
            "proposal_id": "ai-speed", "base_session_revision": 1,
            "operations": [{"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}],
        }),
    )

    materialized = materialize_editing_session_timeline(
        timeline=timeline, editing_session=session, project_id="project-ripple",
    )

    for track_type in ("narration", "broll", "sfx"):
        clip = _clip(materialized, track_type, f"{track_type}-2")
        assert (clip["start_sec"], clip["end_sec"], clip["playback_rate"]) == (4.0, 6.0, 2.0)
    caption = next(cue for cue in materialized["session_captions"] if cue["segment_id"] == "scene-2")
    assert (caption["start_sec"], caption["end_sec"]) == (4.0, 6.0)


def test_ripple_speed_reaches_composition_and_the_actual_video_and_audio_filters(tmp_path) -> None:
    from videobox_core_engine.composition_plan import CompositionPlan

    timeline = _source_timeline()
    session = set_segment_ripple_playback_rate(
        session=_session(timeline), segment_id="scene-2", rate=2.0,
    )
    materialized = materialize_editing_session_timeline(
        timeline=timeline,
        editing_session=session,
        project_id="project-ripple",
    )
    plan = CompositionPlan.from_timeline(
        timeline=materialized,
        captions=materialized["session_captions"],
    )
    narration = next(item for item in plan.items if item.clip_id == "narration-2")
    broll = next(item for item in plan.items if item.clip_id == "broll-2")
    sfx = next(item for item in plan.items if item.clip_id == "sfx-2")
    assert narration.playback_rate == 2.0
    assert broll.playback_rate == 2.0
    assert sfx.playback_rate == 2.0

    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path), video_width=320, video_height=240)
    sources = {item.clip_id: index for index, item in enumerate(plan.items)}
    video = renderer.build_plan_filter_graph(composition_plan=plan, source_indices=sources)
    audio = renderer.build_plan_audio_filter_graph(composition_plan=plan, source_indices=sources)
    # B-roll 자체 1.5배와 장면 2배가 실제 영상 필터에서 3배가 된다.
    assert "setpts=(PTS-STARTPTS)/3.0" in video
    # 내레이션과 효과음도 같은 장면 비율로 빨라진다. BGM은 normal pitch다.
    assert audio.count("atempo=2.0") >= 2


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required to make local export sources")
def test_capcut_export_uses_the_same_materialized_scene_speed_for_voice_and_video(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="Ripple speed CapCut")
    narration_path = tmp_path / "narration.wav"
    broll_path = tmp_path / "broll.mp4"
    for command in (
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_path)],
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=240x320:rate=15", str(broll_path)],
    ):
        subprocess.run(command, check=True, capture_output=True, text=True)
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_path)
    source = {
        "project_id": project.project_id,
        "timeline_id": "timeline-ripple-capcut",
        "narration_source_uri": narration.storage_uri,
        "tracks": [
            {"track_type": "narration", "clips": [{"clip_id": "voice", "segment_id": "scene", "asset_uri": f"local://projects/{project.project_id}/segments/scene", "start_sec": 0.0, "end_sec": 4.0}]},
            {"track_type": "broll", "clips": [{"clip_id": "video", "segment_id": "scene", "asset_uri": broll.storage_uri, "start_sec": 0.0, "end_sec": 4.0}]},
        ],
    }
    session = set_segment_ripple_playback_rate(
        session=build_editing_session(
            project_id=project.project_id,
            timeline=source,
            segments=[{"segment_id": "scene", "text": "빠른 장면", "start_sec": 0.0, "end_sec": 4.0}],
        ),
        segment_id="scene",
        rate=2.0,
    )
    materialized = materialize_editing_session_timeline(
        timeline=source,
        editing_session=session,
        project_id=project.project_id,
    )

    result = PyCapCutRealExportAdapter(store=store, video_width=320, video_height=240).export_timeline(
        project_id=project.project_id,
        timeline=materialized,
        drafts_root=tmp_path / "drafts",
        draft_name="ripple-speed-contract",
        editing_session=session,
    )

    import json
    content = json.loads((result.draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}
    for track_name in ("voiceover", "broll"):
        segment = tracks[track_name][0]
        assert segment["target_timerange"]["duration"] == 2_000_000
        assert segment["source_timerange"]["duration"] == 4_000_000
        assert segment["speed"] == pytest.approx(2.0)
