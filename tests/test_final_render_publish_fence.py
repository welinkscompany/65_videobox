from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.exact_preview import ExactPreviewRequest
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


@pytest.mark.parametrize(
    ("input_kind", "asset_type"),
    (
        ("broll", AssetType.BROLL_VIDEO),
        ("bgm", AssetType.BGM),
        ("sfx", AssetType.SFX),
        ("export_overlay", AssetType.IMAGE),
    ),
)
def test_final_render_snapshots_every_unstamped_composition_input_before_render(
    tmp_path: Path, input_kind: str, asset_type: AssetType,
) -> None:
    """A legacy base input changing during render must not gain an export pointer."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name=f"final {input_kind} pre-render fence")
    source = tmp_path / f"{input_kind}.bin"
    source.write_bytes(f"{input_kind}-before-render".encode())
    asset = store.register_asset(project_id=project.project_id, asset_type=asset_type, source_path=source)
    clip = {
        "clip_id": input_kind,
        "asset_id": asset.asset_id,
        "asset_uri": asset.storage_uri,
        "start_sec": 0,
        "end_sec": 1,
    }
    timeline_payload: dict[str, Any] = {
        "review_flags": [],
        "pending_recommendations": [],
        "tracks": [] if input_kind == "export_overlay" else [{"track_type": input_kind, "clips": [clip]}],
        "export_overlays": [clip] if input_kind == "export_overlay" else [],
    }
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload=timeline_payload,
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_revision=session["session_revision"],
    )
    timeline_job = store.create_job(project_id=project.project_id, job_type=JobType.TIMELINE_BUILD, status=JobStatus.RUNNING)
    store.update_job(project_id=project.project_id, job_id=timeline_job["job_id"], status=JobStatus.SUCCEEDED, output_ref=timeline["timeline_id"])
    job = store.create_job(project_id=project.project_id, job_type=JobType.FINAL_RENDER, input_ref=timeline_job["job_id"], status=JobStatus.RUNNING)
    renderer = _MutatingRenderer(mutate_path=store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri))

    LocalPipelineRunner(store, final_renderer=renderer).run_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
        job=job,
    )

    failed = store.get_job(project_id=project.project_id, job_id=job["job_id"])
    assert failed["status"] == JobStatus.FAILED.value
    assert "stale_output_asset: content SHA-256 changed" in str(failed["error_message"])
    assert not list((store.project_root(project.project_id) / "exports" / "final_render").glob("*/output.mp4"))


def test_final_render_snapshots_segment_narration_source_before_render(tmp_path: Path) -> None:
    """Virtual narration segments must fence the source file they actually render."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="final segment narration pre-render fence")
    source = tmp_path / "narration.wav"
    source.write_bytes(b"narration-before-render")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "review_flags": [],
            "pending_recommendations": [],
            "narration_source_uri": asset.storage_uri,
            "tracks": [{"track_type": "narration", "clips": [{
                "clip_id": "segment-1",
                "asset_uri": f"local://projects/{project.project_id}/segments/segment-1",
                "start_sec": 0,
                "end_sec": 1,
            }]}],
        },
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_revision=session["session_revision"],
    )
    timeline_job = store.create_job(project_id=project.project_id, job_type=JobType.TIMELINE_BUILD, status=JobStatus.RUNNING)
    store.update_job(project_id=project.project_id, job_id=timeline_job["job_id"], status=JobStatus.SUCCEEDED, output_ref=timeline["timeline_id"])
    job = store.create_job(project_id=project.project_id, job_type=JobType.FINAL_RENDER, input_ref=timeline_job["job_id"], status=JobStatus.RUNNING)
    renderer = _MutatingRenderer(mutate_path=store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri))

    LocalPipelineRunner(store, final_renderer=renderer).run_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job["job_id"],
        job=job,
    )

    failed = store.get_job(project_id=project.project_id, job_id=job["job_id"])
    assert failed["status"] == JobStatus.FAILED.value
    assert "stale_output_asset: content SHA-256 changed" in str(failed["error_message"])
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


def test_exact_preview_rehashes_large_input_once_before_short_writer_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The writer publish boundary must not repeat a large full-file hash."""

    class _OutputOnlyRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            output_path.write_bytes(b"rendered")
            self.rendered.set()
            return output_path

    class _PublishBarrierStore(LocalProjectStore):
        entered_publish: Event
        continue_publish: Event

        def finish_exact_preview(self, **kwargs: Any) -> bool:  # type: ignore[no-untyped-def]
            self.entered_publish.set()
            assert self.continue_publish.wait(timeout=2)
            return super().finish_exact_preview(**kwargs)

    store = _PublishBarrierStore(tmp_path)
    store.entered_publish, store.continue_publish = Event(), Event()
    project = store.bootstrap_project(name="bounded exact-preview publish")
    source = tmp_path / "large-source.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 1}, "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b", "asset_id": asset.asset_id,
            "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}", "start_sec": 0, "end_sec": 1,
        }]}]},
    )
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    renderer = _OutputOnlyRenderer(store=store)
    renderer.rendered = Event()
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    stored_source = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).resolve()
    from videobox_core_engine import local_pipeline

    original_hash = local_pipeline.sha256_file
    post_render_hashes = {"count": 0}
    counter_lock = Lock()

    def count_post_render_hash(path: Path) -> str:
        value = original_hash(path)
        if renderer.rendered.is_set() and Path(path).resolve() == stored_source:
            with counter_lock:
                post_render_hashes["count"] += 1
        return value

    monkeypatch.setattr(local_pipeline, "sha256_file", count_post_render_hash)
    record = runner.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"])
    worker = Thread(target=runner.run_exact_preview, kwargs={"project_id": project.project_id, "generation_id": record["generation_id"]})
    worker.start()
    assert store.entered_publish.wait(timeout=2)

    store.continue_publish.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert post_render_hashes["count"] == 1
    assert store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])["state"] == "succeeded"


def test_exact_preview_slow_rehash_does_not_starve_concurrent_session_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The expensive post-render hash runs before, rather than inside, SQLite publication."""

    class _OutputOnlyRenderer(FfmpegFinalRenderer):
        def render_exact_preview_to_mp4(self, *, output_path: Path, **_kwargs: Any) -> Path:
            output_path.write_bytes(b"rendered")
            self.rendered.set()
            return output_path

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="non-starving exact-preview rehash")
    source = tmp_path / "slow-large-source.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={"output": {"duration_sec": 1}, "tracks": [{"track_type": "broll", "clips": [{
            "clip_id": "b", "asset_id": asset.asset_id,
            "asset_uri": f"local://projects/{project.project_id}/assets/{asset.asset_id}", "start_sec": 0, "end_sec": 1,
        }]}]},
    )
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": []})
    renderer = _OutputOnlyRenderer(store=store)
    renderer.rendered = Event()
    runner = LocalPipelineRunner(store, final_renderer=renderer)
    stored_source = store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri).resolve()
    from videobox_core_engine import local_pipeline

    original_hash = local_pipeline.sha256_file
    hash_started, allow_hash, session_mutated = Event(), Event(), Event()

    def pause_post_render_hash(path: Path) -> str:
        if renderer.rendered.is_set() and Path(path).resolve() == stored_source:
            hash_started.set()
            assert allow_hash.wait(timeout=2)
        return original_hash(path)

    monkeypatch.setattr(local_pipeline, "sha256_file", pause_post_render_hash)
    record = runner.start_exact_preview(project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"])
    worker = Thread(target=runner.run_exact_preview, kwargs={"project_id": project.project_id, "generation_id": record["generation_id"]})
    worker.start()
    assert hash_started.wait(timeout=2)

    def mutate_session() -> None:
        current = store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])
        store.update_editing_session(
            project_id=project.project_id,
            session_id=session["session_id"],
            session_payload=current,
            expected_revision=current["session_revision"],
        )
        session_mutated.set()

    mutation_worker = Thread(target=mutate_session)
    mutation_worker.start()
    assert session_mutated.wait(timeout=1), "slow source hashing must not hold the SQLite writer lock"
    allow_hash.set()
    worker.join(timeout=2)
    mutation_worker.join(timeout=2)

    assert not worker.is_alive() and not mutation_worker.is_alive()
    published = store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert published["state"] == "obsolete"


def test_exact_preview_stages_large_artifact_before_writer_lock_does_not_starve_session_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow worker-output copy must complete before SQLite publication begins."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="bounded exact-preview artifact staging")
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id="timeline_001",
        session_payload={"segments": [], "history": []},
    )
    record = store.begin_exact_preview(
        project_id=project.project_id,
        request=ExactPreviewRequest(session_id=session["session_id"], expected_revision=session["session_revision"]),
        fingerprint="sha256:bounded-artifact-copy",
    )
    assert store.claim_exact_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token="worker")
    worker_output = tmp_path / "large-worker-output.mp4"
    worker_output.write_bytes(b"x" * (2 * 1024 * 1024))
    from videobox_storage import local_project_store

    original_copyfile = local_project_store.shutil.copyfile
    copy_started, allow_copy, session_mutated = Event(), Event(), Event()

    def pause_copyfile(source: Path, destination: Path, *args: Any, **kwargs: Any) -> str:
        copy_started.set()
        assert allow_copy.wait(timeout=2)
        return original_copyfile(source, destination, *args, **kwargs)

    monkeypatch.setattr(local_project_store.shutil, "copyfile", pause_copyfile)
    worker = Thread(
        target=store.finish_exact_preview,
        kwargs={
            "project_id": project.project_id,
            "generation_id": record["generation_id"],
            "fingerprint": record["fingerprint"],
            "artifact_path": worker_output,
            "owner_token": "worker",
        },
    )
    worker.start()
    assert copy_started.wait(timeout=2)

    def mutate_session() -> None:
        current = store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])
        store.update_editing_session(
            project_id=project.project_id,
            session_id=session["session_id"],
            session_payload=current,
            expected_revision=current["session_revision"],
        )
        session_mutated.set()

    mutation_worker = Thread(target=mutate_session)
    mutation_worker.start()
    assert session_mutated.wait(timeout=1), "artifact copy must not hold the SQLite writer lock"
    allow_copy.set()
    worker.join(timeout=2)
    mutation_worker.join(timeout=2)

    assert not worker.is_alive() and not mutation_worker.is_alive()
    assert store.get_exact_preview(project_id=project.project_id, generation_id=record["generation_id"])["state"] == "obsolete"
