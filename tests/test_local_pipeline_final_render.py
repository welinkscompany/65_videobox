from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import sqlite3
from threading import Barrier
from typing import Any

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


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
    assert "Style: Segment1,Arial,36,&H000000FF" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:02.00,Segment1,,0,0,0,,right" in ass
