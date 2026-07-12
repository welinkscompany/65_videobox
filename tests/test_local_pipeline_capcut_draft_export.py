from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import wave

import pytest

from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.local_pipeline import LocalPipelineRunner
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

    runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    assert fake_exporter.received_calls[0]["editing_session"]["caption_style"]["text_color"] == "#00FF00FF"


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
