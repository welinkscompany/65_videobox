from __future__ import annotations

from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.capcut_handoff import CapCutHandoffService
from videobox_core_engine.editor_playback_manifest import build_editor_playback_manifest
import subprocess
import json
import pytest
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _ready(
    store: LocalProjectStore,
    project_id: str,
    script_text: str = "제품을 소개합니다.",
) -> tuple[dict, dict]:
    brief = store.create_creation_brief(project_id=project_id, script_filename="script.txt", script_text=script_text, idempotency_key="brief", capability_profile={}, runtime=type("R", (), {"plan_questions": lambda *_args, **_kwargs: []})())
    brief = store.bypass_creation_interview(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project_id, brief_id=brief["brief_id"], summary="제품 소개", expected_revision=brief["revision"])
    brief = store.approve_creation_brief(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    run = store.start_draft_readiness(project_id=project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="ready", expected_brief_revision=brief["revision"], defer=False)
    return brief, run


def test_materializes_one_real_draft_bundle_and_reuses_same_idempotency_result(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Atomic")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="approve-once", allow_placeholder=True)
    first = store.materialize_atomic_draft_bundle(**payload)
    second = store.materialize_atomic_draft_bundle(**payload)
    assert first["session_id"] == second["session_id"]
    assert first["timeline_id"] == second["timeline_id"]
    assert first["segment_ids"] and first["asset_ids"] and first["clip_ids"]
    session = store.get_editing_session(project_id=project.project_id, session_id=first["session_id"])
    assert session["timeline_id"] == first["timeline_id"]
    assert any(track["track_type"] == "narration" for track in session["tracks"])
    visible_segment_id = session["segments"][0]["segment_id"]
    placeholder = next(
        clip
        for track in session["tracks"]
        for clip in track["clips"]
        if clip.get("gap_slot_id")
    )
    assert placeholder["segment_id"] == visible_segment_id
    assert placeholder["source_segment_id"] == "script-1"
    assert session["gap_slots"][0]["segment_id"] == visible_segment_id
    assert session["gap_slots"][0]["source_segment_id"] == "script-1"


def test_real_asset_bundle_keeps_unique_tracks_and_places_each_source_on_its_visible_segment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("Aligned real assets")
    for index in range(4):
        source = tmp_path / f"scene-{index}.mp4"
        source.write_bytes(f"scene-{index}".encode())
        store.register_asset(
            project_id=project.project_id,
            asset_type=AssetType.BROLL_VIDEO,
            source_path=source,
        )
    monkeypatch.setattr(
        store,
        "_probe_playable_broll_duration",
        lambda **_kwargs: 6.0,
    )
    brief, readiness = _ready(
        store,
        project.project_id,
        "첫 장면입니다. 둘째 장면입니다. 셋째 장면입니다. 마지막 장면입니다.",
    )

    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id,
        brief_id=brief["brief_id"],
        expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"],
        expected_readiness_revision=readiness["revision"],
        idempotency_key="aligned-assets",
    )
    session = store.get_editing_session(
        project_id=project.project_id,
        session_id=bundle["session_id"],
    )
    timeline = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=bundle["timeline_id"],
    )
    manifest = build_editor_playback_manifest(
        project_id=project.project_id,
        session=session,
        timeline=timeline,
        asset_content_url_prefix=f"/api/projects/{project.project_id}/assets",
    )
    visible = [
        (segment["segment_id"], segment["start_sec"], segment["end_sec"])
        for segment in session["segments"]
    ]
    broll = next(track for track in manifest["tracks"] if track["track_type"] == "broll")

    assert len({track["track_id"] for track in manifest["tracks"]}) == len(manifest["tracks"])
    assert [
        (clip["segment_id"], clip["start_sec"], clip["end_sec"])
        for clip in broll["clips"]
    ] == visible
    raw_broll = next(track for track in timeline["tracks"] if track["track_type"] == "broll")
    assert [clip["source_segment_id"] for clip in raw_broll["clips"]] == [
        "script-1",
        "script-2",
        "script-3",
        "script-4",
    ]
    assert [
        (clip["media_controls"]["in_sec"], clip["media_controls"]["out_sec"])
        for clip in raw_broll["clips"]
    ] == [(0, 5.0)] * 4
    assert bundle["segment_ids"] == [segment_id for segment_id, _, _ in visible]


def test_concurrent_duplicate_approval_returns_one_atomic_bundle(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Concurrent approval")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="one-click", allow_placeholder=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: store.materialize_atomic_draft_bundle(**payload), range(2)))
    assert {result["bundle_id"] for result in results}.__len__() == 1
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1


def test_failed_materialization_can_retry_same_idempotency_key_without_orphan(tmp_path):
    root = tmp_path / "projects"; failed_once = False

    def fail_once(event: str) -> None:
        nonlocal failed_once
        if event == "after_copy:1" and not failed_once:
            failed_once = True
            raise OSError("one injected failure")

    store = LocalProjectStore(root, atomic_bundle_fault_hook=fail_once); project = store.bootstrap_project("Retry approval")
    brief, readiness = _ready(store, project.project_id)
    payload = dict(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="retry-once", allow_placeholder=True)
    with pytest.raises(OSError, match="one injected failure"):
        store.materialize_atomic_draft_bundle(**payload)
    result = store.materialize_atomic_draft_bundle(**payload)
    assert result["session_id"]
    assert len(store.list_editing_sessions(project_id=project.project_id)) == 1
    assert not list(store.project_root(project.project_id).glob("staging/draft-bundle-*"))


def test_rejects_stale_readiness_and_does_not_leave_partial_session(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Atomic")
    brief, readiness = _ready(store, project.project_id)
    try:
        store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"] + 1, idempotency_key="stale")
    except ValueError as exc:
        assert "revision_conflict" in str(exc)
    else: raise AssertionError("expected stale revision rejection")
    assert store.list_editing_sessions(project_id=project.project_id) == []


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_rejects_source_bytes_changed_after_readiness_without_partial_bundle(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Snapshot")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=2", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=broll.storage_uri); path.write_bytes(b"after")
    try:
        store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="changed")
    except ValueError as exc: assert "source_sha_conflict" in str(exc)
    else: raise AssertionError("changed source must be rejected")
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_gap_bundle_is_blocked_by_shared_pipeline_before_final_and_capcut(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Gap")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="gap", allow_placeholder=True)
    placeholder = next(asset_id for asset_id in bundle["asset_ids"] if asset_id.startswith("asset_gap_placeholder_"))
    assert store.get_asset(project_id=project.project_id, asset_id=placeholder)["metadata"]["in_app_only"] is True
    pipeline = LocalPipelineRunner(store)
    for action in (pipeline.start_final_render, pipeline.start_capcut_draft_export):
        try: action(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
        except ValueError as exc: assert "gap_blocks" in str(exc)
        else: raise AssertionError("gap draft output must be blocked")
    with pytest.raises(ValueError, match="gap_blocks"):
        pipeline.start_final_render_job(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    direct_job = store.create_job(project_id=project.project_id, job_type=JobType.FINAL_RENDER, input_ref=bundle["timeline_job_id"], status=JobStatus.RUNNING)
    pipeline.run_final_render_job(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"], job=direct_job)
    assert store.get_job(project_id=project.project_id, job_id=direct_job["job_id"])["status"] == JobStatus.FAILED.value


def test_each_gap_slot_gets_its_own_labeled_placeholder_clip_at_its_target_range(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Multiple gaps")
    brief, readiness = _ready(store, project.project_id)
    first_gap = {"gap_slot_id": "gap-opening", "reason": "첫 장면이 없어요.", "target_range": {"start_sec": 0, "end_sec": 2}}
    second_gap = {"gap_slot_id": "gap-closing", "reason": "마지막 장면이 없어요.", "target_range": {"start_sec": 7, "end_sec": 10}}
    updated_result = {**readiness["result"], "gap_slots": [first_gap, second_gap]}
    store._execute(project.project_id, "UPDATE draft_readiness SET result_json = ? WHERE readiness_id = ?", (json.dumps(updated_result, ensure_ascii=False), readiness["readiness_id"]))
    bundle = store.materialize_atomic_draft_bundle(
        project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"],
        readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"],
        idempotency_key="two-gaps", allow_placeholder=True,
    )
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    placeholder_clips = [clip for track in session["tracks"] for clip in track["clips"] if clip.get("gap_slot_id")]
    assert bundle["gap_slots"] == [first_gap, second_gap]
    assert len(placeholder_clips) == 2
    assert {(clip["gap_slot_id"], clip["start_sec"], clip["end_sec"], clip["label"]) for clip in placeholder_clips} == {
        ("gap-opening", 0, 2, "자산이 필요한 임시 장면"),
        ("gap-closing", 7, 10, "자산이 필요한 임시 장면"),
    }
    placeholder_assets = [asset_id for asset_id in bundle["asset_ids"] if asset_id.startswith("asset_gap_placeholder_")]
    assert len(placeholder_assets) == 2
    assert all(store.get_asset(project_id=project.project_id, asset_id=asset_id)["metadata"]["in_app_only"] for asset_id in placeholder_assets)


def test_atomic_bundle_session_is_immediately_editable_by_the_legacy_editor_contract(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Editor contract")
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="editor-contract", allow_placeholder=True)
    session = store.get_editing_session(project_id=project.project_id, session_id=bundle["session_id"])
    assert session["history"] == [] and session["undo_count"] == 0 and session["redo_count"] == 0
    assert session["segments"]
    assert {"segment_id", "caption_text", "start_sec", "end_sec", "cut_action", "review_required", "broll_override", "visual_overlays", "music_override", "sfx_override", "tts_replacement"} <= set(session["segments"][0])


def test_restart_removes_uncommitted_draft_bundle_operation_stage(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Recovery")
    orphan = store.project_root(project.project_id) / "staging" / "draft-bundle-orphan"; orphan.mkdir(parents=True)
    (orphan / "operation.json").write_text('{"kind":"atomic_draft_bundle","status":"staging"}', encoding="utf-8")
    LocalProjectStore(tmp_path / "projects")
    assert not orphan.exists()


@pytest.mark.parametrize("failure_event", ["after_copy:1", "after_copy:2", "before_db_commit"])
def test_atomic_bundle_copy_and_database_failure_leave_no_partial_bundle_or_mirror(tmp_path, failure_event):
    seen_manifests: list[dict] = []
    root = tmp_path / "projects"

    def fail(event: str) -> None:
        if event == failure_event:
            stages = list(root.glob("projects/*/staging/draft-bundle-*"))
            assert len(stages) == 1
            seen_manifests.append(json.loads((stages[0] / "operation.json").read_text(encoding="utf-8")))
            raise OSError(f"injected {event}")

    store = LocalProjectStore(root, atomic_bundle_fault_hook=fail)
    project = store.bootstrap_project("Injected failure")
    brief, readiness = _ready(store, project.project_id)
    with pytest.raises(OSError, match="injected"):
        store.materialize_atomic_draft_bundle(
            project_id=project.project_id, brief_id=brief["brief_id"],
            expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"],
            expected_readiness_revision=readiness["revision"], idempotency_key=failure_event,
            allow_placeholder=True,
        )
    assert seen_manifests and seen_manifests[0]["artifacts"]
    for artifact in seen_manifests[0]["artifacts"]:
        assert len(artifact["sha256"]) == 64
    assert store.list_editing_sessions(project_id=project.project_id) == []
    assert not list(store.project_root(project.project_id).glob("staging/draft-bundle-*"))
    assert not list((store.project_root(project.project_id) / "timelines").glob("timeline_draft_*.json"))
    assert not list((store.project_root(project.project_id) / "editing_sessions").glob("editing_session_draft_*.json"))
    assert not list((store.project_root(project.project_id) / "assets" / "narration_audio").glob("asset_silence_*.wav"))


def test_ready_asset_bundle_reaches_real_ffmpeg_final_render_after_explicit_review(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Render")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    assert readiness["status"] == "ready"
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="render")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store)
    result = pipeline.start_final_render(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    assert result["status"] == "succeeded"
    render = pipeline.get_final_render_result(project_id=project.project_id, job_id=result["job_id"])["render"]
    assert render and render["source_session_revision"] == 1 and render["is_current"] is True
    assert store.resolve_storage_uri(project_id=project.project_id, storage_uri=render["file_uri"]).read_bytes()[:4]


def test_ready_asset_bundle_reaches_real_capcut_draft_export_after_explicit_review(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("CapCut")
    video = tmp_path / "scene.mp4"; subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id); bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="capcut")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15))
    result = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    export = pipeline.get_capcut_draft_export_result(project_id=project.project_id, job_id=result["job_id"])["export"]
    assert result["status"] == "succeeded" and export and store.resolve_storage_uri(project_id=project.project_id, storage_uri=export["file_uri"]).is_dir()


def _ffprobe_streams(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
@pytest.mark.parametrize("narration_kind", ["source_video", "existing", "recorded", "silent"])
def test_each_approved_narration_path_reaches_ffmpeg_and_pycapcut_with_playable_bundle_output(tmp_path, narration_kind):
    """Task 9 matrix: all user-visible narration choices share both real output paths."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(f"Narration {narration_kind}")
    broll = tmp_path / "broll.mp4"
    source_video = tmp_path / "source.mp4"
    audio = tmp_path / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=15:d=1", "-an", "-c:v", "libx264", str(broll)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=s=320x180:r=15:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source_video)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(audio)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll)
    raw = store.register_asset(project_id=project.project_id, asset_type=AssetType.RAW_VIDEO, source_path=source_video)
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=audio, source_kind="browser_recording_normalized" if narration_kind == "recorded" else "local_file")
    brief = store.create_creation_brief(project_id=project.project_id, script_filename="script.txt", script_text="한 문장 소개", idempotency_key="brief", capability_profile={}, runtime=type("R", (), {"plan_questions": lambda *_args, **_kwargs: []})())
    brief = store.bypass_creation_interview(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project.project_id, brief_id=brief["brief_id"], summary="소개", expected_revision=brief["revision"])
    brief = store.approve_creation_brief(project_id=project.project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    choice = {"kind": narration_kind if narration_kind != "recorded" else "existing"}
    if narration_kind == "source_video": choice["asset_id"] = raw.asset_id
    elif narration_kind in {"existing", "recorded"}: choice["asset_id"] = narration.asset_id
    readiness = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice=choice, idempotency_key="ready", expected_brief_revision=brief["revision"], defer=False)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="bundle")
    timeline = store.get_timeline_run(project_id=project.project_id, timeline_id=bundle["timeline_id"])
    narration_clip = next(clip for track in timeline["tracks"] if track["track_type"] == "narration" for clip in track["clips"])
    assert len(narration_clip["expected_content_sha256"]) == 64
    assert narration_clip["media_revision"]
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15))
    render_job = pipeline.start_final_render(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    render = pipeline.get_final_render_result(project_id=project.project_id, job_id=render_job["job_id"])["render"]
    assert render is not None
    streams = _ffprobe_streams(store.resolve_storage_uri(project_id=project.project_id, storage_uri=render["file_uri"]))
    assert float(streams["format"]["duration"]) > 0
    assert {stream["codec_type"] for stream in streams["streams"]} >= {"video", "audio"}
    capcut_job = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    exported = pipeline.get_capcut_draft_export_result(project_id=project.project_id, job_id=capcut_job["job_id"])["export"]
    assert exported is not None and store.resolve_storage_uri(project_id=project.project_id, storage_uri=exported["file_uri"]).is_dir()


def test_voice_sample_is_rejected_before_atomic_bundle_can_be_built(tmp_path):
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("Voice sample boundary")
    voice = tmp_path / "voice.wav"; voice.write_bytes(b"not output narration")
    sample = store.register_asset(project_id=project.project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO, source_path=voice)
    brief, _ = _ready(store, project.project_id)
    with pytest.raises(ValueError, match="voice_sample_invalid"):
        store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "existing", "asset_id": sample.asset_id}, idempotency_key="sample", expected_brief_revision=brief["revision"], defer=False)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_bundle_derived_pycapcut_draft_registers_in_writable_local_capcut_smoke_environment(tmp_path):
    """This is a local fake installation smoke only; Desktop CapCut launch remains owner-gated."""
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("CapCut handoff smoke")
    video = tmp_path / "scene.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=15:d=1", "-an", "-c:v", "libx264", str(video)], check=True, capture_output=True)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    brief, readiness = _ready(store, project.project_id)
    bundle = store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=readiness["readiness_id"], expected_readiness_revision=readiness["revision"], idempotency_key="handoff")
    store.save_review_state(project_id=project.project_id, timeline_id=bundle["timeline_id"], status="approved", source_session_revision=1)
    local_app_data = tmp_path / "fake-local-app-data"
    executable = local_app_data / "CapCut" / "Apps" / "8.9.1" / "CapCut.exe"
    executable.parent.mkdir(parents=True); executable.write_bytes(b"fake executable")
    project_root = local_app_data / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    project_root.mkdir(parents=True)
    pipeline = LocalPipelineRunner(
        store,
        pycapcut_exporter=PyCapCutRealExportAdapter(store=store, video_width=320, video_height=180, video_fps=15),
        capcut_handoff_service=CapCutHandoffService(local_app_data=local_app_data),
    )
    export_job = pipeline.start_capcut_draft_export(project_id=project.project_id, timeline_job_id=bundle["timeline_job_id"])
    handoff = pipeline.register_capcut_draft_handoff(project_id=project.project_id, job_id=export_job["job_id"])
    registered = Path(handoff["registered_project_path"])
    assert handoff["status"] == "ready" and registered.parent == project_root
    assert (registered / "draft_content.json").is_file()
