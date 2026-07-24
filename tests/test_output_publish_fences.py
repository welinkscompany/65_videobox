from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from videobox_api.models import (
    CapCutDraftExportArtifactResponse,
    SubtitleArtifactResponse,
)
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_source_verifier import (
    OutputSourceStaleError,
    verify_output_freshness,
)
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


class _DraftExporter:
    def __init__(self, *, mutate_path: Path | None = None) -> None:
        self.mutate_path = mutate_path

    def export_timeline(
        self,
        *,
        drafts_root: Path,
        draft_name: str,
        **_kwargs: Any,
    ) -> Path:
        draft_path = drafts_root / draft_name
        draft_path.mkdir(parents=True)
        (draft_path / "draft_content.json").write_text("{}", encoding="utf-8")
        if self.mutate_path is not None:
            self.mutate_path.write_bytes(b"changed-during-capcut-export")
        return draft_path


class _FinalRenderer:
    video_width = 1280
    video_height = 720

    def render_timeline_to_mp4(
        self,
        *,
        output_path: Path,
        on_progress: Any = None,
        **_kwargs: Any,
    ) -> Path:
        output_path.write_bytes(b"rendered-before-session-creation")
        if on_progress is not None:
            on_progress(100)
        return output_path


class _PublishMutatingStore(LocalProjectStore):
    session_id: str
    mutate_before: str
    mutated: bool

    def _create_session_once(self, project_id: str, timeline_id: str) -> None:
        if self.mutated:
            return
        self.mutated = True
        self.save_editing_session(
            project_id=project_id,
            timeline_id=timeline_id,
            session_payload={
                "segments": [
                    {
                        "segment_id": "segment-1",
                        "start_sec": 2,
                        "end_sec": 4,
                        "caption_text": "session created during output",
                        "cut_action": "keep",
                    }
                ],
                "history": [],
            },
        )

    def _mutate_session_once(self, project_id: str) -> None:
        if self.mutated:
            return
        self.mutated = True
        current = self.get_editing_session(project_id=project_id, session_id=self.session_id)
        self.update_editing_session(
            project_id=project_id,
            session_id=self.session_id,
            expected_revision=current["session_revision"],
            session_payload={
                **current,
                "segments": [
                    {
                        "segment_id": "segment-1",
                        "start_sec": 0,
                        "end_sec": 1,
                        "caption_text": "changed before publish",
                        "cut_action": "keep",
                    }
                ],
            },
        )

    def save_subtitle_run(self, **kwargs: Any) -> dict[str, Any]:
        if self.mutate_before == "subtitle-session-created":
            self._create_session_once(
                str(kwargs["project_id"]),
                str(kwargs["timeline_id"]),
            )
        if self.mutate_before == "subtitle-review":
            self.save_review_state(
                project_id=str(kwargs["project_id"]),
                timeline_id=str(kwargs["timeline_id"]),
                status="draft",
            )
        if self.mutate_before == "subtitle":
            self._mutate_session_once(str(kwargs["project_id"]))
        return super().save_subtitle_run(**kwargs)

    def save_capcut_draft_export(self, **kwargs: Any) -> dict[str, Any]:
        if self.mutate_before == "capcut-session-created":
            self._create_session_once(
                str(kwargs["project_id"]),
                str(kwargs["timeline_id"]),
            )
        if self.mutate_before == "capcut":
            self._mutate_session_once(str(kwargs["project_id"]))
        return super().save_capcut_draft_export(**kwargs)

    def save_final_render(self, **kwargs: Any) -> dict[str, Any]:
        if self.mutate_before == "final-session-created":
            self._create_session_once(
                str(kwargs["project_id"]),
                str(kwargs["timeline_id"]),
            )
        return super().save_final_render(**kwargs)


def _approved_timeline(
    store: LocalProjectStore,
    *,
    project_id: str,
    tracks: list[dict[str, Any]] | None = None,
    with_session: bool = True,
    session_segments: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={
            "caption_segments": [
                {
                    "segment_id": "segment-1",
                    "text": "approved caption",
                    "start_sec": 0,
                    "end_sec": 1,
                }
            ],
            "tracks": tracks or [],
            "review_flags": [],
            "pending_recommendations": [],
        },
    )
    session = None
    if with_session:
        session = store.save_editing_session(
            project_id=project_id,
            timeline_id=timeline["timeline_id"],
            session_payload={
                "segments": session_segments or [
                    {
                        "segment_id": "segment-1",
                        "start_sec": 0,
                        "end_sec": 1,
                        "caption_text": "approved caption",
                        "cut_action": "keep",
                    }
                ],
                "history": [],
            },
        )
    store.save_review_state(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_id=session["session_id"] if session else None,
        source_session_revision=session["session_revision"] if session else None,
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
        output_ref=timeline["timeline_id"],
    )
    return timeline_job["job_id"], session


def test_subtitle_publish_rejects_a_session_revision_changed_after_rendering(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "subtitle"
    store.mutated = False
    project = store.bootstrap_project(name="subtitle durable revision fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
    )
    assert session is not None
    store.session_id = str(session["session_id"])
    runner = LocalPipelineRunner(store)

    with pytest.raises(RuntimeError, match="subtitle_render_session_revision_changed"):
        runner.start_subtitle_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    subtitle_jobs = [
        job for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.SUBTITLE_RENDER.value
    ]
    assert subtitle_jobs[-1]["status"] == JobStatus.FAILED.value
    assert not list((store.project_root(project.project_id) / "subtitles").glob("subtitle_*.srt"))


def test_subtitle_publish_rejects_review_reopened_at_the_publish_boundary(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "subtitle-review"
    store.mutated = False
    project = store.bootstrap_project(name="subtitle durable review fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
    )
    assert session is not None
    store.session_id = str(session["session_id"])
    runner = LocalPipelineRunner(store)

    with pytest.raises(RuntimeError, match="subtitle_render_source_fence_failed"):
        runner.start_subtitle_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    subtitle_jobs = [
        job for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.SUBTITLE_RENDER.value
    ]
    assert subtitle_jobs[-1]["status"] == JobStatus.FAILED.value
    assert not list((store.project_root(project.project_id) / "subtitles").glob("subtitle_*.srt"))


def test_subtitle_publish_rejects_a_session_created_after_absence_was_captured(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "subtitle-session-created"
    store.mutated = False
    project = store.bootstrap_project(name="subtitle durable absence fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    assert session is None
    runner = LocalPipelineRunner(store)

    with pytest.raises(RuntimeError, match="subtitle_render_session_presence_changed"):
        runner.start_subtitle_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    assert not list((store.project_root(project.project_id) / "subtitles").glob("subtitle_*.srt"))


def test_capcut_publish_rejects_a_session_revision_changed_after_postwork_check(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "capcut"
    store.mutated = False
    project = store.bootstrap_project(name="capcut durable revision fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
    )
    assert session is not None
    store.session_id = str(session["session_id"])
    runner = LocalPipelineRunner(store, pycapcut_exporter=_DraftExporter())

    with pytest.raises(RuntimeError, match="capcut_draft_export_session_revision_changed"):
        runner.start_capcut_draft_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    capcut_jobs = [
        job for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.CAPCUT_DRAFT_EXPORT.value
    ]
    assert capcut_jobs[-1]["status"] == JobStatus.FAILED.value
    assert not list((store.project_root(project.project_id) / "exports" / "capcut_draft").glob("export_*"))


def test_capcut_publish_rejects_a_materialized_source_changed_during_export(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="capcut durable source fence")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-before-capcut-export")
    asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
    )
    stored_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=asset.storage_uri,
    )
    timeline_job_id, _ = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
        tracks=[
            {
                "track_type": "broll",
                "clips": [
                    {
                        "clip_id": "broll-1",
                        "segment_id": "segment-1",
                        "asset_id": asset.asset_id,
                        "asset_uri": asset.storage_uri,
                        "start_sec": 0,
                        "end_sec": 1,
                    }
                ],
            }
        ],
    )
    runner = LocalPipelineRunner(
        store,
        pycapcut_exporter=_DraftExporter(mutate_path=stored_path),
    )

    with pytest.raises(RuntimeError, match="stale_output_asset: content SHA-256 changed"):
        runner.start_capcut_draft_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    capcut_jobs = [
        job for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.CAPCUT_DRAFT_EXPORT.value
    ]
    assert capcut_jobs[-1]["status"] == JobStatus.FAILED.value
    assert not list((store.project_root(project.project_id) / "exports" / "capcut_draft").glob("export_*"))


def test_capcut_publish_rejects_a_session_created_after_absence_was_captured(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "capcut-session-created"
    store.mutated = False
    project = store.bootstrap_project(name="capcut durable absence fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    assert session is None
    runner = LocalPipelineRunner(store, pycapcut_exporter=_DraftExporter())

    with pytest.raises(RuntimeError, match="capcut_draft_export_session_presence_changed"):
        runner.start_capcut_draft_export(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    assert not list(
        (store.project_root(project.project_id) / "exports" / "capcut_draft").glob("export_*")
    )


def test_final_publish_rejects_a_session_created_after_absence_was_captured(
    tmp_path: Path,
) -> None:
    store = _PublishMutatingStore(tmp_path)
    store.mutate_before = "final-session-created"
    store.mutated = False
    project = store.bootstrap_project(name="final durable absence fence")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    assert session is None
    runner = LocalPipelineRunner(store, final_renderer=_FinalRenderer())

    with pytest.raises(RuntimeError, match="final_render_session_presence_changed"):
        runner.start_final_render(
            project_id=project.project_id,
            timeline_job_id=timeline_job_id,
        )

    assert not list(
        (store.project_root(project.project_id) / "exports" / "final_render").glob("export_*")
    )


def test_subtitle_staging_is_removed_when_the_initial_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="subtitle staging cleanup")
    timeline_job_id, _ = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    timeline_id = store.get_job(
        project_id=project.project_id,
        job_id=timeline_job_id,
    )["output_ref"]
    original_write_text = Path.write_text

    def fail_staging_write(path: Path, data: str, **kwargs: Any) -> int:
        if path.name.endswith(".staging.srt"):
            path.write_bytes(b"partial subtitle")
            raise OSError("forced subtitle staging failure")
        return original_write_text(path, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_staging_write)

    with pytest.raises(OSError, match="forced subtitle staging failure"):
        store.save_subtitle_run(
            project_id=project.project_id,
            timeline_id=str(timeline_id),
            subtitle_payload={"format": "srt", "entries": []},
        )

    assert not list(
        (store.project_root(project.project_id) / "subtitles").glob("*.staging.srt")
    )


def test_capcut_staging_is_removed_when_the_initial_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="capcut staging cleanup")
    timeline_job_id, _ = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    timeline_id = store.get_job(
        project_id=project.project_id,
        job_id=timeline_job_id,
    )["output_ref"]
    source_draft = tmp_path / "source-draft"
    source_draft.mkdir()
    (source_draft / "draft_content.json").write_text("{}", encoding="utf-8")

    def fail_copytree(_source: Path, destination: Path) -> None:
        assert len(destination.parent.name) == 10
        destination.mkdir(parents=True)
        (destination / "partial.json").write_text("partial", encoding="utf-8")
        raise OSError("forced CapCut staging failure")

    monkeypatch.setattr("videobox_storage.local_project_store.shutil.copytree", fail_copytree)

    with pytest.raises(OSError, match="forced CapCut staging failure"):
        store.save_capcut_draft_export(
            project_id=project.project_id,
            timeline_id=str(timeline_id),
            source_draft_path=source_draft,
        )

    assert not [
        path
        for path in (
            store.project_root(project.project_id) / "exports" / "capcut_draft"
        ).iterdir()
        if path.name.startswith(".s")
    ]


def test_final_render_staging_is_removed_when_the_initial_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="final render staging cleanup")
    timeline_job_id, _ = _approved_timeline(
        store,
        project_id=project.project_id,
        with_session=False,
    )
    timeline_id = store.get_job(
        project_id=project.project_id,
        job_id=timeline_job_id,
    )["output_ref"]
    source_output = tmp_path / "source-output.mp4"
    source_output.write_bytes(b"source")
    observed_staging: Path | None = None

    def fail_copy2(_source: Path, destination: Path) -> None:
        nonlocal observed_staging
        observed_staging = destination.parent
        assert len(destination.parent.name) == 10
        destination.write_bytes(b"partial final render")
        raise OSError("forced final render staging failure")

    monkeypatch.setattr("videobox_storage.local_project_store.shutil.copy2", fail_copy2)

    with pytest.raises(OSError, match="forced final render staging failure"):
        store.save_final_render(
            project_id=project.project_id,
            timeline_id=str(timeline_id),
            source_output_path=source_output,
        )

    assert observed_staging is not None
    assert not observed_staging.exists()


def test_subtitle_payload_and_srt_use_the_latest_editing_session_caption_and_timing(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="subtitle editing session payload")
    timeline_job_id, session = _approved_timeline(
        store,
        project_id=project.project_id,
        session_segments=[
            {
                "segment_id": "segment-1",
                "start_sec": 1.25,
                "end_sec": 3.5,
                "caption_text": "latest editing-session caption",
                "cut_action": "keep",
            }
        ],
    )
    assert session is not None
    runner = LocalPipelineRunner(store)

    result = runner.start_subtitle_render(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )
    subtitle = runner.get_subtitle_result(
        project_id=project.project_id,
        job_id=result["job_id"],
    )["subtitle"]
    subtitle_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=subtitle["file_uri"],
    )

    assert subtitle_path.read_text(encoding="utf-8") == (
        "1\n"
        "00:00:01,250 --> 00:00:03,500\n"
        "latest editing-session caption\n"
    )
    assert subtitle["summary"]["entry_count"] == 1
    assert subtitle["source_session_id"] == session["session_id"]


def test_output_read_surfaces_preserve_session_id_and_reject_same_revision_other_session(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="output session identity")
    timeline_job_id, first_session = _approved_timeline(
        store,
        project_id=project.project_id,
    )
    assert first_session is not None
    timeline_id = str(
        store.get_job(project_id=project.project_id, job_id=timeline_job_id)["output_ref"]
    )
    subtitle = store.save_subtitle_run(
        project_id=project.project_id,
        timeline_id=timeline_id,
        subtitle_payload={"format": "srt", "entries": []},
        source_session_id=first_session["session_id"],
        source_session_revision=first_session["session_revision"],
    )
    source_draft = tmp_path / "identity-draft"
    source_draft.mkdir()
    (source_draft / "draft_content.json").write_text("{}", encoding="utf-8")
    capcut = store.save_capcut_draft_export(
        project_id=project.project_id,
        timeline_id=timeline_id,
        source_draft_path=source_draft,
        source_session_id=first_session["session_id"],
        source_session_revision=first_session["session_revision"],
    )
    second_session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_id,
        session_payload={
            "segments": [
                {
                    "segment_id": "segment-1",
                    "start_sec": 0,
                    "end_sec": 1,
                    "caption_text": "different session, same revision",
                    "cut_action": "keep",
                }
            ],
            "history": [],
        },
    )
    subtitle_row = store.get_subtitle_run(
        project_id=project.project_id,
        subtitle_id=subtitle["subtitle_id"],
    )
    capcut_row = store.get_capcut_draft_export(
        project_id=project.project_id,
        export_id=capcut["export_id"],
    )

    assert subtitle_row["source_session_id"] == first_session["session_id"]
    assert capcut_row["source_session_id"] == first_session["session_id"]
    assert SubtitleArtifactResponse(**subtitle_row).source_session_id == first_session["session_id"]
    assert (
        CapCutDraftExportArtifactResponse(**capcut_row).source_session_id
        == first_session["session_id"]
    )
    with pytest.raises(OutputSourceStaleError, match="subtitle session changed"):
        verify_output_freshness(
            editing_session=second_session,
            timeline=store.get_timeline_run(
                project_id=project.project_id,
                timeline_id=timeline_id,
            ),
            subtitle=subtitle_row,
        )
