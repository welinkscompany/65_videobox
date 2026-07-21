from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


class _MutatingRenderer:
    """A renderer boundary that changes the selected override after output exists."""

    video_width = 1280
    video_height = 720

    def __init__(self, *, mutate_path: Path) -> None:
        self.mutate_path = mutate_path
        self.received_timeline: dict[str, Any] | None = None

    def render_timeline_to_mp4(
        self,
        *,
        timeline: dict[str, Any],
        output_path: Path,
        on_progress: Any = None,
        **_kwargs: Any,
    ) -> Path:
        self.received_timeline = timeline
        output_path.write_bytes(b"rendered-before-source-mutation")
        self.mutate_path.write_bytes(b"mutated-after-render")
        if on_progress is not None:
            on_progress(100)
        return output_path


def test_final_render_revalidates_materialized_session_override_before_publish(tmp_path: Path) -> None:
    """A replacement asset may not change after render and still become final output."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="final render publish source fence")
    source = tmp_path / "replacement.mp4"
    source.write_bytes(b"selected-before-render")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    stored_asset = store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)
    expected_sha = sha256(b"selected-before-render").hexdigest()
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "tracks": [
                {
                    "track_type": "broll",
                    "clips": [
                        {
                            "clip_id": "base",
                            "segment_id": "s1",
                            "asset_uri": "local://not-used-by-session-override",
                            "start_sec": 0,
                            "end_sec": 1,
                        }
                    ],
                }
            ],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={
            "segments": [
                {
                    "segment_id": "s1",
                    "start_sec": 0,
                    "end_sec": 1,
                    "cut_action": "keep",
                    "broll_override": {
                        "asset_id": asset.asset_id,
                        "expected_content_sha256": expected_sha,
                        "media_revision": stored_asset["created_at"],
                    },
                }
            ],
            "history": [],
        },
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_revision=session["session_revision"],
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        status=JobStatus.RUNNING,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.FINAL_RENDER,
        input_ref=timeline_job["job_id"],
        status=JobStatus.RUNNING,
    )
    renderer = _MutatingRenderer(
        mutate_path=store.resolve_storage_uri(
            project_id=project.project_id,
            storage_uri=asset.storage_uri,
        )
    )
    runner = LocalPipelineRunner(store, final_renderer=renderer)

    runner.run_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
        job=job,
    )

    failed = store.get_job(project_id=project.project_id, job_id=job["job_id"])
    assert failed["status"] == JobStatus.FAILED.value
    assert "stale_output_asset" in str(failed["error_message"])
    assert renderer.received_timeline is not None
    override = renderer.received_timeline["tracks"][0]["clips"][0]
    assert override["asset_id"] == asset.asset_id
    assert override["expected_content_sha256"] == expected_sha
    assert not list((store.project_root(project.project_id) / "exports" / "final_render").glob("*/output.mp4"))


def test_exact_preview_publish_rechecks_sources_inside_durable_publish_fence(tmp_path: Path) -> None:
    """The last source check belongs inside the claimed-record publication fence."""

    class _PublishMutatingStore(LocalProjectStore):
        mutate_path: Path

        def finish_exact_preview(self, **kwargs: Any) -> bool:  # type: ignore[no-untyped-def]
            self.mutate_path.write_bytes(b"changed-after-pipeline-revalidation")
            return super().finish_exact_preview(**kwargs)

    class _OutputOnlyRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            output_path.write_bytes(b"rendered-before-publish")
            return output_path

    store = _PublishMutatingStore(tmp_path)
    project = store.bootstrap_project(name="exact preview durable source fence")
    source = tmp_path / "preview-source.mp4"
    source.write_bytes(b"before-publish")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    store.mutate_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
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
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": []},
    )
    runner = LocalPipelineRunner(store, final_renderer=_OutputOnlyRenderer(store=store))
    record = runner.start_exact_preview(
        project_id=project.project_id,
        session_id=session["session_id"],
        expected_revision=session["session_revision"],
    )

    runner.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])

    published = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert published["state"] == "obsolete"
    assert published["invalidated_reason"] == "publish_source_fence_failed"
    assert published["artifact_uri"] is None


def test_exact_preview_baseline_source_completes_inside_durable_publish_fence(tmp_path: Path) -> None:
    """The durable source fence must not self-invalidate an unchanged preview."""

    class _OutputOnlyRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            output_path.write_bytes(b"unchanged-source-preview")
            return output_path

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="exact preview baseline source fence")
    source = tmp_path / "preview-source.mp4"
    source.write_bytes(b"unchanged-source")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
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
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": []},
    )
    runner = LocalPipelineRunner(store, final_renderer=_OutputOnlyRenderer(store=store))
    record = runner.start_exact_preview(
        project_id=project.project_id,
        session_id=session["session_id"],
        expected_revision=session["session_revision"],
    )

    runner.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])

    published = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert published["state"] == "succeeded"
    assert published["artifact_uri"] is not None


def test_exact_preview_timeline_mutation_after_render_is_never_published(tmp_path: Path) -> None:
    """A lock-safe fence still rejects a changed source timeline."""

    class _TimelineMutatingRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            output_path.write_bytes(b"rendered-before-timeline-mutation")
            latest = self.store.get_timeline_run(project_id=self.project_id, timeline_id=self.timeline_id)
            latest["output"]["marker"] = "changed-after-render"
            self.store.update_timeline_run(
                project_id=self.project_id, timeline_id=self.timeline_id, timeline_payload=latest,
            )
            return output_path

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="exact preview timeline source fence")
    source = tmp_path / "preview-source.mp4"
    source.write_bytes(b"timeline-source")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "output": {"duration_sec": 1},
            "tracks": [{"track_type": "broll", "clips": [{
                "clip_id": "b", "asset_id": asset.asset_id,
                "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}",
                "start_sec": 0, "end_sec": 1,
            }]}],
        },
    )
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    renderer = _TimelineMutatingRenderer(store=store)
    renderer.project_id, renderer.timeline_id = project.project_id, timeline["timeline_id"]
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    record = runner.start_exact_preview(
        project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"],
    )

    runner.run_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])

    published = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert published["state"] == "obsolete"
    assert published["invalidated_reason"] == "publish_revalidation_failed"
    assert published["artifact_uri"] is None
