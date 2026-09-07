"""더빙이 실제 규모에서 타임라인을 다시 만들 수 있는지.

더빙은 끝날 때마다 부분 재생성을 지난다 -- 그게 있어야 내레이션이 실제로
갈아 끼워진다. 창작자의 실제 대본은 **243문단**이라(2026-09-03 실측, 8분 15초
영상) 재생성도 그 규모를 견뎌야 한다.

**목소리는 만들지 않는다.** 243번 합성하면 52분이 걸리는데, 알고 싶은 것은
"구조가 243장면을 견디는가"이지 "합성이 되는가"가 아니다. 소리 파일 하나를
243장면이 같이 쓰면 같은 위험을 3초에 잰다.
"""
import time
from pathlib import Path

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def test_partial_regeneration_holds_at_real_script_scale(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="scale")
    pipeline = LocalPipelineRunner(store)

    # 진짜 소리 파일 하나만 만들어 243장면이 같이 쓴다. 합성은 관심사가 아니다.
    import subprocess
    wav = tmp_path / "take.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=5", str(wav)], check=True, timeout=120)
    asset = store.register_asset(project_id=project.project_id,
                                 asset_type=AssetType.GENERATED_TTS_AUDIO, source_path=wav)

    segments = [
        {"segment_id": f"s{i:03d}", "caption_text": f"{i}번째 문장입니다",
         "start_sec": (i - 1) * 5.0, "end_sec": i * 5.0, "cut_action": "keep",
         "review_required": False, "broll_override": None, "visual_overlays": [],
         "music_override": None, "sfx_override": None,
         "tts_replacement": {"recommendation_id": f"tts_candidate_{i:03d}", "asset_id": asset.asset_id}}
        for i in range(1, 244)
    ]
    timeline = store.save_timeline_run(project_id=project.project_id, output_mode="review",
        timeline_payload={"timeline_id": "timeline_001", "project_id": project.project_id,
                          "version": "draft-v1", "tracks": [], "output": {"width": 1920, "height": 1080}})
    session = store.save_editing_session(project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"project_id": project.project_id,
                         "timeline_id": timeline["timeline_id"], "segments": segments,
                         "session_revision": 1, "history": [], "undo_stack": [], "redo_stack": []})

    start = time.time()
    pipeline.start_editing_session_partial_regeneration(
        project_id=project.project_id, session_id=session["session_id"],
        segment_ids=[s["segment_id"] for s in segments],
        fields=["tts_replacement"],
        expected_revision=int(session["session_revision"]),
    )
    elapsed = time.time() - start

    # 실측 2.4초. 넉넉히 잡아도 이 안이어야 한다 -- 여기서 몇 분이 걸리면
    # 더빙이 끝난 뒤 화면이 한참 멈춘다.
    assert elapsed < 60, f"243장면 재생성이 {elapsed:.0f}초 걸렸다"
    refreshed = store.get_editing_session(
        project_id=project.project_id, session_id=session["session_id"])
    assert len(refreshed["segments"]) == 243
