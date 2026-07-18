from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _write_playable_video(path: Path, *, duration_sec: float = 6.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=white:s=320x180:d={duration_sec}", "-an", "-c:v", "libx264", str(path)],
        check=True,
        capture_output=True,
    )


def _approved_brief(store: LocalProjectStore, project_id: str, script_text: str = "첫 장면에서 제품을 소개하고 마지막에 신청을 안내합니다.") -> dict:
    brief = store.create_creation_brief(project_id=project_id, script_filename="script.txt", script_text=script_text, idempotency_key="brief", capability_profile={})
    brief = store.bypass_creation_interview(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project_id, brief_id=brief["brief_id"], summary="제품 소개", expected_revision=brief["revision"])
    return store.approve_creation_brief(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])


def test_draft_readiness_persists_deterministic_preview_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Ready")
    brief = _approved_brief(store, project.project_id)
    broll_file = tmp_path / "cut.mp4"; _write_playable_video(broll_file)
    broll = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_file)
    ready = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="ready-1", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=ready["readiness_id"], expected_revision=ready["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"], expected_revision=planning["revision"])
    resumed = LocalProjectStore(tmp_path).get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])
    assert ready["status"] == "ready"
    assert resumed["result"]["script_segments"]
    assert resumed["result"]["caption_texts"]
    assert resumed["result"]["broll_candidates"][0]["asset_id"] == broll.asset_id
    assert resumed["result"]["bgm"] == {"selection": None, "reason": "프로젝트에 사용할 배경음이 없어요."}
    assert resumed["result"]["sfx"] == {"selection": None, "reason": "프로젝트에 사용할 효과음이 없어요."}
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_draft_readiness_rejects_unapproved_cross_project_and_voice_sample_narration(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    first = store.bootstrap_project("First"); second = store.bootstrap_project("Second")
    brief = _approved_brief(store, first.project_id)
    voice_path = tmp_path / "voice.wav"; voice_path.write_bytes(b"wav")
    voice = store.register_asset(project_id=first.project_id, asset_type=AssetType.VOICE_SAMPLE_AUDIO, source_path=voice_path)
    with pytest.raises(ValueError, match="draft_readiness_narration_voice_sample_invalid"):
        store.start_draft_readiness(project_id=first.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "existing", "asset_id": voice.asset_id}, idempotency_key="voice", expected_brief_revision=brief["revision"])
    with pytest.raises(KeyError):
        store.start_draft_readiness(project_id=second.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="cross", expected_brief_revision=brief["revision"])


def test_draft_readiness_cancel_fences_late_result_and_idempotency_is_durable(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Fence"); brief = _approved_brief(store, project.project_id)
    created = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="same", expected_brief_revision=brief["revision"], defer=True)
    duplicate = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="same", expected_brief_revision=brief["revision"], defer=True)
    cancelled = store.cancel_draft_readiness(project_id=project.project_id, readiness_id=created["readiness_id"], expected_revision=created["revision"])
    assert duplicate["readiness_id"] == created["readiness_id"]
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ValueError, match="draft_readiness_cancelled"):
        store.complete_draft_readiness(project_id=project.project_id, readiness_id=created["readiness_id"], expected_revision=created["revision"])


def test_draft_readiness_starts_in_progress_then_completes_with_segment_candidates(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Lifecycle"); brief = _approved_brief(store, project.project_id)
    broll_path = tmp_path / "broll.mp4"; _write_playable_video(broll_path)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=broll_path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="life", expected_brief_revision=brief["revision"])
    assert started["status"] == "asset_check"
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    assert planning["status"] == "planning"
    completed = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    assert completed["status"] == "ready"
    candidate = completed["result"]["broll_candidates"][0]
    assert candidate["segment_id"] == "script-1"
    assert candidate["target_range"] == {"start_sec": 0, "end_sec": 5}


def test_draft_readiness_selects_one_usable_broll_candidate_per_script_segment(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("One candidate per scene"); brief = _approved_brief(store, project.project_id, "첫 장면입니다. 다음 장면입니다.")
    assets = []
    for index in range(8):
        path = tmp_path / f"scene-{index}.mp4"
        if index < 2:
            _write_playable_video(path, duration_sec=4.0)
        else:
            path.write_bytes(b"not a video")
        assets.append(store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=path))
    for asset in assets[:2]:
        store._execute(project.project_id, "UPDATE assets SET duration_sec = ? WHERE asset_id = ?", (4.0, asset.asset_id))

    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="bounded", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    completed = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])

    candidates = completed["result"]["broll_candidates"]
    assert [(item["asset_id"], item["segment_id"], item["target_range"]) for item in candidates] == [
        (assets[0].asset_id, "script-1", {"start_sec": 0, "end_sec": 4.0}),
        (assets[1].asset_id, "script-2", {"start_sec": 0, "end_sec": 4.0}),
    ]
    assert all(0 <= item["target_range"]["start_sec"] < item["target_range"]["end_sec"] <= 4.0 for item in candidates)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")
def test_draft_readiness_excludes_fake_video_files_and_repairs_legacy_candidates_on_read(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Playable candidates"); brief = _approved_brief(store, project.project_id, "첫 장면입니다. 다음 장면입니다.")
    for index in range(2):
        fake = tmp_path / f"fake-{index}.mp4"; fake.write_bytes(b"not a video")
        store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=fake)
    playable_path = tmp_path / "playable.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:d=2", "-an", "-c:v", "libx264", str(playable_path)], check=True, capture_output=True)
    playable = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=playable_path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="playable", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    assert [(item["asset_id"], item["target_range"]) for item in ready["result"]["broll_candidates"]] == [(playable.asset_id, {"start_sec": 0, "end_sec": 2.0})]
    assert ready["status"] == "needs_assets"
    assert ready["result"]["gap_slots"] == [{"gap_slot_id": "gap-broll-2", "segment_id": "script-2", "reason": "장면을 보여 줄 영상이 없어요.", "target_range": {"start_sec": 5, "end_sec": 10}, "media_type": "broll_video"}]
    with pytest.raises(ValueError, match="atomic_draft_bundle_gaps_require_placeholder_approval"):
        store.materialize_atomic_draft_bundle(project_id=project.project_id, brief_id=brief["brief_id"], expected_brief_revision=brief["revision"], readiness_id=ready["readiness_id"], expected_readiness_revision=ready["revision"], idempotency_key="must-not-skip-gap")

    stale = dict(ready["result"])
    stale["broll_candidates"] = [{"asset_id": playable.asset_id, "label": "재생할 장면", "segment_id": "script-1", "target_range": {"start_sec": 35, "end_sec": 10}, "skipped": False}]
    stale["gap_slots"] = []
    store._execute(project.project_id, "UPDATE draft_readiness SET result_json = ? WHERE readiness_id = ?", (json.dumps(stale, ensure_ascii=False), ready["readiness_id"]))

    listed = store.list_draft_readiness(project_id=project.project_id)
    assert [(item["asset_id"], item["target_range"]) for item in listed[0]["result"]["broll_candidates"]] == [(playable.asset_id, {"start_sec": 0, "end_sec": 2.0})]
    assert listed[0]["result"]["gap_slots"] == [{"gap_slot_id": "gap-broll-2", "segment_id": "script-2", "reason": "장면을 보여 줄 영상이 없어요.", "target_range": {"start_sec": 5, "end_sec": 10}, "media_type": "broll_video"}]
    repaired = store.get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])
    assert [(item["asset_id"], item["target_range"]) for item in repaired["result"]["broll_candidates"]] == [(playable.asset_id, {"start_sec": 0, "end_sec": 2.0})]

    partial = dict(repaired["result"])
    partial["gap_slots"] = []
    store._execute(project.project_id, "UPDATE draft_readiness SET result_json = ?, status = 'ready' WHERE readiness_id = ?", (json.dumps(partial, ensure_ascii=False), ready["readiness_id"]))
    completed_gaps = store.get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])
    assert completed_gaps["status"] == "needs_assets"
    assert completed_gaps["result"]["gap_slots"] == [{"gap_slot_id": "gap-broll-2", "segment_id": "script-2", "reason": "장면을 보여 줄 영상이 없어요.", "target_range": {"start_sec": 5, "end_sec": 10}, "media_type": "broll_video"}]
    store._execute(project.project_id, "UPDATE draft_readiness SET status = 'ready' WHERE readiness_id = ?", (ready["readiness_id"],))
    assert store.get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])["status"] == "needs_assets"


def test_draft_readiness_persists_candidate_skip_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Choices"); brief = _approved_brief(store, project.project_id)
    path = tmp_path / "b.mp4"; _write_playable_video(path); store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="choices", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    skipped = store.update_draft_readiness_candidate(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=ready["result"]["broll_candidates"][0]["asset_id"], skipped=True, expected_revision=ready["revision"])
    assert skipped["result"]["broll_candidates"][0]["skipped"] is True
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_draft_readiness_persists_candidate_range_and_rejects_invalid_values_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Ranges"); brief = _approved_brief(store, project.project_id)
    path = tmp_path / "range.mp4"; _write_playable_video(path); asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="ranges", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    updated = store.update_draft_readiness_candidate_range(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=asset.asset_id, start_sec=1.5, end_sec=4.0, expected_revision=ready["revision"])
    resumed = LocalProjectStore(tmp_path).get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])
    assert updated["result"]["broll_candidates"][0]["target_range"] == {"start_sec": 1.5, "end_sec": 4.0}
    assert resumed["result"]["broll_candidates"][0]["target_range"] == {"start_sec": 1.5, "end_sec": 4.0}
    with pytest.raises(ValueError, match="draft_readiness_candidate_range_invalid"):
        store.update_draft_readiness_candidate_range(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=asset.asset_id, start_sec=4, end_sec=1.5, expected_revision=updated["revision"])
    store._execute(project.project_id, "UPDATE assets SET duration_sec = ? WHERE asset_id = ?", (3.0, asset.asset_id))
    with pytest.raises(ValueError, match="draft_readiness_candidate_range_invalid"):
        store.update_draft_readiness_candidate_range(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=asset.asset_id, start_sec=1.5, end_sec=3.5, expected_revision=updated["revision"])
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_draft_readiness_planner_failure_is_durable_and_retryable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Failure"); brief = _approved_brief(store, project.project_id)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="failure", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    monkeypatch.setattr(store, "_draft_readiness_plan", lambda **_: (_ for _ in ()).throw(RuntimeError("do not expose details")))
    with pytest.raises(RuntimeError): store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    failed = LocalProjectStore(tmp_path).get_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"])
    assert failed["status"] == "failed" and failed["error_code"] == "draft_readiness_planning_failed"
