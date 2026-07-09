from __future__ import annotations

from pathlib import Path
from typing import Any

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


class _FakeFinalRenderer:
    def __init__(self) -> None:
        self.received_calls: list[dict[str, Any]] = []

    def render_timeline_to_mp4(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        output_path: Path,
        subtitle_file_path: Path | None = None,
        on_progress: Any = None,
    ) -> Path:
        self.received_calls.append(
            {
                "project_id": project_id,
                "timeline": timeline,
                "output_path": output_path,
                "subtitle_file_path": subtitle_file_path,
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

    fetched = runner.get_final_render_result(project_id=project.project_id, job_id=result["job_id"])
    assert fetched["status"] == "succeeded"
    assert fetched["render"]["export_type"] == "final_render"
    assert fetched["render"]["file_uri"].startswith(f"local://projects/{project.project_id}/exports/final_render/")


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
