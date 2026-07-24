from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
import wave

import pytest

from videobox_capcut_export.pycapcut_adapter import CapCutDraftExportResult, PyCapCutRealExportAdapter
from videobox_core_engine.capcut_handoff import CapCutHandoffService
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_source_verifier import OutputSourceStaleError
from videobox_domain_models.assets import AssetType
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
        self.received_calls.append({"project_id": project_id, "draft_name": draft_name, "editing_session": editing_session, "timeline": timeline})
        draft_path = drafts_root / draft_name
        draft_path.mkdir(parents=True, exist_ok=True)
        (draft_path / "draft_content.json").write_text("{}", encoding="utf-8")
        return draft_path


def _build_approved_timeline_job(
    store: LocalProjectStore,
    runner: LocalPipelineRunner,
    project_id: str,
    *,
    extra_tracks: list[dict[str, Any]] | None = None,
) -> str:
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
        ] + list(extra_tracks or []),
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
    store.save_editing_session(project_id=project.project_id, timeline_id=timeline_id, session_payload={"project_id": project.project_id, "timeline_id": timeline_id, "caption_style": {"text_color": "#00FF00FF"}, "segments": [{"segment_id": "seg_001", "caption_text": "CapCut style", "start_sec": 4.0, "end_sec": 6.0}], "history": []})
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)

    runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    assert fake_exporter.received_calls[0]["editing_session"]["caption_style"]["text_color"] == "#00FF00FF"
    narration = next(
        track
        for track in fake_exporter.received_calls[0]["timeline"]["tracks"]
        if track["track_type"] == "narration"
    )
    assert (narration["clips"][0]["start_sec"], narration["clips"][0]["end_sec"]) == (4.0, 6.0)


def test_capcut_draft_export_passes_only_materialized_session_captions_to_adapter(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut materialized captions")
    fake_exporter = _FakePyCapCutExporter()
    runner = LocalPipelineRunner(store, pycapcut_exporter=fake_exporter)
    timeline_job_id = _build_approved_timeline_job(store, runner, project.project_id)
    timeline_id = runner.get_timeline_result(
        project_id=project.project_id,
        job_id=timeline_job_id,
    )["timeline"]["timeline_id"]
    store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_id,
        session_payload={
            "project_id": project.project_id,
            "timeline_id": timeline_id,
            "caption_style": {"text_color": "#00FF00FF"},
            "segments": [
                {
                    "segment_id": "seg_removed",
                    "caption_text": "삭제된 자막",
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "cut_action": "remove",
                },
                {
                    "segment_id": "seg_merged",
                    "caption_text": "병합 전 자막",
                    "start_sec": 1.0,
                    "end_sec": 3.0,
                    "content_windows": [
                        {
                            "source_segment_id": "seg_kept",
                            "caption_text": "병합 후 남은 자막",
                            "start_offset_sec": 0.0,
                            "duration_sec": 2.0,
                        }
                    ],
                },
            ],
            "history": [],
        },
    )
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)

    runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    received = fake_exporter.received_calls[0]
    assert received["editing_session"]["segments"] == received["timeline"]["session_captions"]
    assert [
        (caption["segment_id"], caption["caption_text"], caption["start_sec"], caption["end_sec"])
        for caption in received["editing_session"]["segments"]
    ] == [("seg_kept", "병합 후 남은 자막", 1.0, 3.0)]


def test_capcut_draft_export_maps_materialized_broll_source_window_to_adapter_controls(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut materialized B-roll source window")
    fake_exporter = _FakePyCapCutExporter()
    runner = LocalPipelineRunner(store, pycapcut_exporter=fake_exporter)
    broll_source = tmp_path / "materialized-broll.mp4"
    broll_source.write_bytes(b"materialized broll source")
    broll_asset = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=broll_source,
    )
    timeline_job_id = _build_approved_timeline_job(
        store,
        runner,
        project.project_id,
        extra_tracks=[
            {
                "track_id": "broll_overlay",
                "track_type": "broll",
                "clips": [
                    {
                        "clip_id": "clip_broll_001",
                        "segment_id": "seg_001",
                        "asset_id": broll_asset.asset_id,
                        "asset_uri": broll_asset.storage_uri,
                        "start_sec": 0.0,
                        "end_sec": 2.0,
                        "media_controls": {
                            "fit": "fit",
                            "loop": False,
                            "pad": True,
                            "trim_start_sec": 0.0,
                            "in_sec": 1.0,
                            "out_sec": 3.0,
                        },
                    }
                ],
            }
        ],
    )
    timeline_id = runner.get_timeline_result(
        project_id=project.project_id,
        job_id=timeline_job_id,
    )["timeline"]["timeline_id"]
    store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline_id,
        session_payload={
            "project_id": project.project_id,
            "timeline_id": timeline_id,
            "segments": [
                {
                    "segment_id": "seg_001",
                    "caption_text": "",
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "cut_action": "keep",
                }
            ],
            "history": [],
        },
    )
    runner.approve_timeline_review(project_id=project.project_id, timeline_job_id=timeline_job_id)

    runner.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=timeline_job_id)

    received_timeline = fake_exporter.received_calls[0]["timeline"]
    broll = next(track for track in received_timeline["tracks"] if track["track_type"] == "broll")
    clip = broll["clips"][0]
    assert (clip["source_in_sec"], clip["source_out_sec"]) == (1.0, 3.0)
    assert (clip["media_controls"]["in_sec"], clip["media_controls"]["out_sec"]) == (1.0, 3.0)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_atomic_reverse_reorder_capcut_draft_uses_materialized_narration_source_windows(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="CapCut reversed atomic narration")
    narration_path = tmp_path / "narration-20s.wav"
    with wave.open(str(narration_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00" * 20 * 8_000)
    narration = store.register_asset(
        project_id=project.project_id,
        asset_type=AssetType.NARRATION_AUDIO,
        source_path=narration_path,
    )
    broll_path = tmp_path / "broll-5s.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=15:d=5",
            "-an",
            "-c:v",
            "libx264",
            str(broll_path),
        ],
        check=True,
        capture_output=True,
    )
    for _ in range(4):
        store.register_asset(
            project_id=project.project_id,
            asset_type=AssetType.BROLL_VIDEO,
            source_path=broll_path,
        )
    brief = store.create_creation_brief(
        project_id=project.project_id,
        script_filename="script.txt",
        script_text="첫 장면입니다. 둘째 장면입니다. 셋째 장면입니다. 마지막 장면입니다.",
        idempotency_key="reverse-capcut-brief",
        capability_profile={},
        runtime=type(
            "NoQuestions",
            (),
            {"plan_questions": lambda *_args, **_kwargs: []},
        )(),
    )
    brief = store.bypass_creation_interview(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_revision=brief["revision"],
    )
    brief = store.update_creation_brief_summary(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        summary="네 장면 역순 편집",
        expected_revision=brief["revision"],
    )
    brief = store.approve_creation_brief(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_revision=brief["revision"],
    )
    readiness = store.start_draft_readiness(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        narration_choice={"kind": "existing", "asset_id": narration.asset_id},
        idempotency_key="reverse-capcut-ready",
        expected_brief_revision=brief["revision"],
        defer=False,
    )
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"],
        expected_readiness_revision=readiness["revision"],
        idempotency_key="reverse-capcut-bundle",
    )
    pipeline = LocalPipelineRunner(
        store,
        pycapcut_exporter=PyCapCutRealExportAdapter(
            store=store,
            video_width=160,
            video_height=90,
            video_fps=15,
        ),
    )
    session = store.get_editing_session(
        project_id=project.project_id,
        session_id=bundle["session_id"],
    )
    original_ids = [str(segment["segment_id"]) for segment in session["segments"]]
    assert len(original_ids) == 4
    reversed_ids = list(reversed(original_ids))
    bounds_by_id = {
        segment_id: {"start_sec": index * 5.0, "end_sec": (index + 1) * 5.0}
        for index, segment_id in enumerate(reversed_ids)
    }
    reordered = pipeline.reorder_editing_session_segments(
        project_id=project.project_id,
        session_id=session["session_id"],
        segment_ids=reversed_ids,
        bounds_by_id=bounds_by_id,
        expected_revision=session["session_revision"],
    )
    assert [str(segment["segment_id"]) for segment in reordered["segments"]] == reversed_ids
    pipeline.approve_timeline_review(
        project_id=project.project_id,
        timeline_job_id=bundle["timeline_job_id"],
    )

    result = pipeline.start_capcut_draft_export(
        project_id=project.project_id,
        timeline_job_id=bundle["timeline_job_id"],
    )

    export = pipeline.get_capcut_draft_export_result(
        project_id=project.project_id,
        job_id=result["job_id"],
    )["export"]
    draft_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=export["file_uri"],
    )
    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    voiceover = next(track["segments"] for track in content["tracks"] if track["name"] == "voiceover")
    assert [
        (segment["source_timerange"]["start"], segment["source_timerange"]["duration"])
        for segment in voiceover
    ] == [
        (15_000_000, 5_000_000),
        (10_000_000, 5_000_000),
        (5_000_000, 5_000_000),
        (0, 5_000_000),
    ]


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
