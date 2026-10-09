"""미리보기 한 번이 ffmpeg 오디오 조기 종료로 실패해도 같은 입력으로 한 번 더 시도한다.

실제 ffmpeg 없이 렌더러 대역으로 확인한다. 재시도는 **오디오가 타임라인보다 짧은 오류 하나**에만 건다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_core_engine.ffmpeg_final_renderer import (
    FfmpegFinalRenderer,
    FinalRenderAudioShortError,
    FinalRenderError,
)
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

_AUDIO_SHORT = "Rendered audio track is shorter than the timeline (5.00s < 20.00s). Retry the render."


def _runner_and_record(tmp_path: Path, renderer_cls: type) -> tuple[LocalProjectStore, LocalPipelineRunner, str, str]:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="audio short retry")
    source = tmp_path / "src.mp4"
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
    runner = LocalPipelineRunner(store, final_renderer=renderer_cls(store=store))
    record = runner.start_exact_preview(
        project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"],
    )
    return store, runner, project.project_id, record["generation_id"]


def test_audio_short_once_is_retried_and_preview_succeeds(tmp_path: Path) -> None:
    class _Flaky(FfmpegFinalRenderer):
        calls = 0

        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            type(self).calls += 1
            if type(self).calls == 1:
                raise FinalRenderAudioShortError(_AUDIO_SHORT)
            output_path.write_bytes(b"ok")
            return output_path

    store, runner, project_id, generation_id = _runner_and_record(tmp_path, _Flaky)
    runner.run_exact_preview(project_id=project_id, generation_id=generation_id)

    record = store.get_exact_preview(project_id=project_id, generation_id=generation_id)
    assert record["state"] == "succeeded", record
    assert _Flaky.calls == 2
    assert runner.last_exact_preview_attempts[generation_id] == 2


def test_audio_short_twice_fails_with_clear_reason_after_two_attempts(tmp_path: Path) -> None:
    class _Broken(FfmpegFinalRenderer):
        calls = 0

        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            type(self).calls += 1
            raise FinalRenderAudioShortError(_AUDIO_SHORT)

    store, runner, project_id, generation_id = _runner_and_record(tmp_path, _Broken)
    runner.run_exact_preview(project_id=project_id, generation_id=generation_id)

    record = store.get_exact_preview(project_id=project_id, generation_id=generation_id)
    assert record["state"] == "failed"
    assert _Broken.calls == 2
    assert "audio track is shorter" in str(record["error_message"])
    assert "attempts=2" in str(record["error_message"])


def test_other_render_failures_are_not_retried(tmp_path: Path) -> None:
    class _Other(FfmpegFinalRenderer):
        calls = 0

        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            type(self).calls += 1
            raise FinalRenderError("ffmpeg failed rendering canonical composition: boom")

    store, runner, project_id, generation_id = _runner_and_record(tmp_path, _Other)
    runner.run_exact_preview(project_id=project_id, generation_id=generation_id)

    record = store.get_exact_preview(project_id=project_id, generation_id=generation_id)
    assert record["state"] == "failed"
    assert _Other.calls == 1
    assert "attempts=" not in str(record["error_message"])
