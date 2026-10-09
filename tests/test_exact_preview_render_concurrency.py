"""미리보기 렌더는 동시에 하나만 돈다 -- 편집을 몰아치면 렌더가 겹겹이 쌓여 서버 CPU·메모리를 먹었다.

실제 ffmpeg 없이 렌더러 대역으로, 서로 다른 두 프로젝트의 미리보기를 동시에 시켜 본다.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _record(store: LocalProjectStore, runner: LocalPipelineRunner, tmp_path: Path, name: str) -> tuple[str, str]:
    project = store.bootstrap_project(name=name)
    source = tmp_path / f"{name}.mp4"
    source.write_bytes(b"source")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project.project_id, output_mode="review", source_session_revision=1,
        timeline_payload={
            "output": {"duration_sec": 1},
            "tracks": [{"track_type": "broll", "clips": [{
                "clip_id": "b", "asset_id": asset.asset_id,
                "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}",
                "start_sec": 0, "end_sec": 1,
            }]}],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []},
    )
    record = runner.start_exact_preview(
        project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"],
    )
    return project.project_id, record["generation_id"]


def test_only_one_exact_preview_renders_at_a_time(tmp_path: Path) -> None:
    state = {"now": 0, "peak": 0}
    lock = threading.Lock()
    first_inside = threading.Event()
    release = threading.Event()

    class _Slow(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            first_inside.set()
            release.wait(timeout=5)
            with lock:
                state["now"] -= 1
            output_path.write_bytes(b"ok")
            return output_path

    store = LocalProjectStore(tmp_path)
    runner = LocalPipelineRunner(store, final_renderer=_Slow(store=store))
    jobs = [_record(store, runner, tmp_path, name) for name in ("a", "b", "c")]
    threads = [threading.Thread(target=runner.run_exact_preview, kwargs={"project_id": p, "generation_id": g}) for p, g in jobs]
    for thread in threads:
        thread.start()
    assert first_inside.wait(timeout=5)
    threading.Event().wait(0.5)  # 나머지가 들어올 틈을 준다
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert state["peak"] == 1, state
    assert all(store.get_exact_preview(project_id=p, generation_id=g)["state"] == "succeeded" for p, g in jobs)
