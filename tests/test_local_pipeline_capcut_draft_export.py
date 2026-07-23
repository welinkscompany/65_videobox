from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import wave

import pytest

from videobox_capcut_export.pycapcut_adapter import CapCutDraftExportResult, PyCapCutRealExportAdapter
from videobox_core_engine.capcut_handoff import CapCutHandoffService
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_source_verifier import OutputSourceStaleError
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_storage.local_project_store import LocalProjectStore


class _FakePyCapCutExporter:
    def __init__(self) -> None:
        self.received_calls: list[dict[str, Any]] = []

    def export_timeline(
        self,
        *,
        project_id: str,
        timeline: dict[str, Any],
        drafts_root: Path,
        draft_name: str,
        subtitle_file_path: Path | None = None,
        editing_session: dict[str, Any] | None = None,
    ) -> Path:
        self.received_calls.append({"project_id": project_id, "draft_name": draft_name, "editing_session": editing_session})
        draft_path = drafts_root / draft_name
        draft_path.mkdir(parents=True, exist_ok=True)
        (draft_path / "draft_content.json").write_text("{}", encoding="utf-8")
        return draft_path


def _build_approved_timeline_job(store: LocalProjectStore, runner: LocalPipelineRunner, project_id: str) -> str:
    raw_audio_asset_dir = store.project_root(project_id)
    raw_audio_path = raw_audio_asset_dir / "narration_source.wav"
    raw_audio_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(raw_audio_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 8_000)
    narration_asset = runner.register_narration_asset(project_id=project_id, source_path=raw_audio_path)

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
    timeline_job = store.create_job(project_id=project_id, job_type=JobType.TIMELINE_BUILD, status=JobStatus.RUNNING)
    store.update_job(
        project_id=project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=persisted_timeline["timeline_id"],
    )
    runner.approve_timeline_review(project_id=project_id, timeline_job_id=timeline_job["job_id"])
    return timeline_job["job_id"]


def test_start_capcut_draft_export_persists_export_and_updates_job(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Draft Export Pipeline Project")
    fake_exporter = _FakePyCapCutExporter()
    runner = LocalPipelineRunner(store, pycapcut_exporter=fake_exporter)

    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)

    result = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    assert result["status"] == "succeeded"
    assert len(fake_exporter.received_calls) == 1

    fetched = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=result["job_id"])
    assert fetched["status"] == "succeeded"
    assert fetched["export"]["export_type"] == "capcut_draft_export"
    assert fetched["export"]["file_uri"].startswith(
        f"local://projects/{project.project_id}/exports/capcut_draft/"
    )


def test_capcut_entrypoint_blocks_stale_review_and_subtitle_until_regenerated(tmp_path: Path) -> None:
    """Task 12 E2E: stale dependency never reaches the CapCut adapter."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut stale output gate")
    fake_exporter = _FakePyCapCutExporter()
    runner = LocalPipelineRunner(store, pycapcut_exporter=fake_exporter)
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)
    timeline_id = runner.get_timeline_result(project_id=project.project_id, job_id=timeline_job_id)["timeline"]["timeline_id"]
    session = store.save_editing_session(project_id=project.project_id, timeline_id=timeline_id, session_payload={"segments": [], "history": []})
    assert store.get_timeline_run(project_id=project.project_id, timeline_id=timeline_id)["source_session_revision"] == session["session_revision"]
    store.save_subtitle_run(project_id=project.project_id, timeline_id=timeline_id, subtitle_payload={"entries": []})
    store.update_editing_session(project_id=project.project_id, session_id=session["session_id"], session_payload={"segments": [], "history": []}, expected_revision=session["session_revision"])
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)
    with pytest.raises(RuntimeError, match="stale_output_asset"):
        runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)
    assert fake_exporter.received_calls == []
    runner.start_subtitle_render(project_id=project.project_id, timeline_job_id=timeline_job_id)
    recovered = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)
    assert recovered["status"] == "succeeded"
    assert len(fake_exporter.received_calls) == 1


def test_start_capcut_draft_export_raises_clear_error_when_not_configured(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Draft Export Unconfigured Project")
    runner = LocalPipelineRunner(store)

    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)

    with pytest.raises(RuntimeError, match="not configured"):
        runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)


def test_start_capcut_draft_export_passes_matching_editing_session_to_adapter(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Styled Session")
    fake_exporter = _FakePyCapCutExporter()
    runner = LocalPipelineRunner(store, pycapcut_exporter=fake_exporter)
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)
    timeline_id = runner.get_timeline_result(project_id=project.project_id, job_id=timeline_job_id)["timeline"]["timeline_id"]
    store.save_editing_session(project_id=project.project_id, timeline_id=timeline_id, session_payload={"project_id": project.project_id, "timeline_id": timeline_id, "caption_style": {"text_color": "#00FF00FF"}, "segments": [{"segment_id": "seg_001", "caption_text": "CapCut style", "start_sec": 0.0, "end_sec": 2.0}], "history": []})
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)

    runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    assert fake_exporter.received_calls[0]["editing_session"]["caption_style"]["text_color"] == "#00FF00FF"


def test_capcut_draft_export_persists_adapter_compatibility_warnings(tmp_path: Path) -> None:
    class WarningExporter(_FakePyCapCutExporter):
        def export_timeline(self, **kwargs: Any) -> CapCutDraftExportResult:
            draft_path = super().export_timeline(**kwargs)
            return CapCutDraftExportResult(draft_path=draft_path, capcut_compatibility_warnings=["ducking warning"])

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut warning persistence")
    runner = LocalPipelineRunner(store, pycapcut_exporter=WarningExporter())
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)

    result = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    persisted = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=result["job_id"])
    assert persisted["export"]["notes"] == ["ducking warning"]


def test_register_capcut_draft_handoff_persists_source_and_registered_project_paths(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut handoff persistence")
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"capcut")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)
    runner = LocalPipelineRunner(
        store,
        pycapcut_exporter=_FakePyCapCutExporter(),
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)
    export_job = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    handoff = runner.register_capcut_draft_handoff(project_id=project.project_id, job_id=export_job["job_id"])
    persisted = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=export_job["job_id"])

    assert handoff["status"] == "ready"
    assert handoff["source_file_uri"] == persisted["export"]["file_uri"]
    assert handoff["registered_project_path"].endswith(f"videobox-{persisted['export']['export_id']}")
    assert persisted["export"]["handoff"] == handoff
    assert Path(handoff["registered_project_path"]).joinpath("draft_content.json").is_file()


def test_register_capcut_draft_handoff_rejects_a_stale_export_before_registering(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut stale handoff")
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"capcut")
    (local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft").mkdir(parents=True)
    runner = LocalPipelineRunner(
        store,
        pycapcut_exporter=_FakePyCapCutExporter(),
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)
    timeline_id = runner.get_timeline_result(project_id=project.project_id, job_id=timeline_job_id)["timeline"]["timeline_id"]
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_id,
        session_payload={"segments": [], "history": []},
    )
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)
    export_job = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)
    store.update_editing_session(
        project_id=project.project_id,
        session_id=session["session_id"],
        session_payload={"segments": [], "history": []},
        expected_revision=session["session_revision"],
    )

    with pytest.raises(OutputSourceStaleError, match="CapCut draft export freshness changed"):
        runner.register_capcut_draft_handoff(project_id=project.project_id, job_id=export_job["job_id"])

    persisted = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=export_job["job_id"])
    assert persisted["export"]["handoff"] is None


def test_register_capcut_draft_handoff_discards_a_registration_when_its_session_becomes_stale_after_copy(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut handoff post-copy stale fence")
    local_app_data = tmp_path / "LocalAppData"
    executable = local_app_data / "CapCut" / "Apps" / "8.7.0" / "CapCut.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"capcut")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    timeline_job_id = _build_approved_timeline_job(
        store,
        LocalPipelineRunner(store, pycapcut_exporter=_FakePyCapCutExporter()),
        project.project_id,
    )
    timeline_id = store.get_job(project_id=project.project_id, job_id=timeline_job_id)["output_ref"]
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_id,
        session_payload={"segments": [], "history": []},
    )
    runner_without_handoff = LocalPipelineRunner(store, pycapcut_exporter=_FakePyCapCutExporter())
    runner_without_handoff.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)
    export_job = runner_without_handoff.start_capcut_draft_export(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    class _SessionMutatingHandoffService(CapCutHandoffService):
        def register(self, **kwargs: Any):  # type: ignore[no-untyped-def]
            record = super().register(**kwargs)
            current = store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])
            store.update_editing_session(
                project_id=project.project_id,
                session_id=current["session_id"],
                session_payload={"segments": [], "history": []},
                expected_revision=current["session_revision"],
            )
            return record

    runner = LocalPipelineRunner(
        store,
        pycapcut_exporter=_FakePyCapCutExporter(),
        capcut_handoff_service=_SessionMutatingHandoffService(local_app_data=local_app_data),
    )

    with pytest.raises(OutputSourceStaleError, match="CapCut draft export freshness changed"):
        runner.register_capcut_draft_handoff(project_id=project.project_id, job_id=export_job["job_id"])

    export = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=export_job["job_id"])["export"]
    assert export["handoff"] is None
    assert not (project_root / f"videobox-{export['export_id']}").exists()
    assert not (local_app_data / "VideoBox" / "capcut-handoffs" / f"{export['export_id']}.json").exists()


def test_capcut_draft_export_result_preserves_failed_job_reason_with_null_artifact(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut failure recovery")
    runner = LocalPipelineRunner(store)
    job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.CAPCUT_DRAFT_EXPORT,
        input_ref="timeline_build_job_001",
    )
    store.update_job(
        project_id=project.project_id,
        job_id=job["job_id"],
        status=JobStatus.FAILED,
        error_message="CapCut draft package could not be written.",
    )

    result = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=job["job_id"])

    assert result == {
        "job_id": job["job_id"],
        "status": "failed",
        "export": None,
        "error_message": "CapCut draft package could not be written.",
    }


def test_real_capcut_draft_keeps_short_tts_silence_material_after_temp_export_is_removed(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Persisted CapCut Silence Material Project")
    runner = LocalPipelineRunner(store, pycapcut_exporter=PyCapCutRealExportAdapter(store=store))
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)

    result = runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)
    persisted = runner.get_capcut_draft_export_result(project_id=project.project_id, job_id=result["job_id"])
    draft_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=persisted["export"]["file_uri"])
    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))

    audio_paths = [Path(material["path"]) for material in content["materials"]["audios"]]
    assert any(path.name.startswith("videobox_silence_") for path in audio_paths)
    assert all(path.is_file() for path in audio_paths)
