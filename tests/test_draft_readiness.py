from __future__ import annotations

from pathlib import Path

import pytest

from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _approved_brief(store: LocalProjectStore, project_id: str) -> dict:
    brief = store.create_creation_brief(project_id=project_id, script_filename="script.txt", script_text="첫 장면에서 제품을 소개하고 마지막에 신청을 안내합니다.", idempotency_key="brief", capability_profile={})
    brief = store.bypass_creation_interview(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])
    brief = store.update_creation_brief_summary(project_id=project_id, brief_id=brief["brief_id"], summary="제품 소개", expected_revision=brief["revision"])
    return store.approve_creation_brief(project_id=project_id, brief_id=brief["brief_id"], expected_revision=brief["revision"])


def test_draft_readiness_persists_deterministic_preview_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("Ready")
    brief = _approved_brief(store, project.project_id)
    broll_file = tmp_path / "cut.mp4"; broll_file.write_bytes(b"video")
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
    broll_path = tmp_path / "broll.mp4"; broll_path.write_bytes(b"video")
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


def test_draft_readiness_persists_candidate_skip_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Choices"); brief = _approved_brief(store, project.project_id)
    path = tmp_path / "b.mp4"; path.write_bytes(b"video"); store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="choices", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    skipped = store.update_draft_readiness_candidate(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=ready["result"]["broll_candidates"][0]["asset_id"], skipped=True, expected_revision=ready["revision"])
    assert skipped["result"]["broll_candidates"][0]["skipped"] is True
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_draft_readiness_persists_candidate_range_and_rejects_invalid_values_without_editing_session(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Ranges"); brief = _approved_brief(store, project.project_id)
    path = tmp_path / "range.mp4"; path.write_bytes(b"video"); asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=path)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="ranges", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    ready = store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    updated = store.update_draft_readiness_candidate_range(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=asset.asset_id, start_sec=1.5, end_sec=4.0, expected_revision=ready["revision"])
    resumed = LocalProjectStore(tmp_path).get_draft_readiness(project_id=project.project_id, readiness_id=ready["readiness_id"])
    assert updated["result"]["broll_candidates"][0]["target_range"] == {"start_sec": 1.5, "end_sec": 4.0}
    assert resumed["result"]["broll_candidates"][0]["target_range"] == {"start_sec": 1.5, "end_sec": 4.0}
    with pytest.raises(ValueError, match="draft_readiness_candidate_range_invalid"):
        store.update_draft_readiness_candidate_range(project_id=project.project_id, readiness_id=ready["readiness_id"], asset_id=asset.asset_id, start_sec=4, end_sec=1.5, expected_revision=updated["revision"])
    assert store.list_editing_sessions(project_id=project.project_id) == []


def test_draft_readiness_planner_failure_is_durable_and_retryable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("Failure"); brief = _approved_brief(store, project.project_id)
    started = store.start_draft_readiness(project_id=project.project_id, brief_id=brief["brief_id"], narration_choice={"kind": "silent"}, idempotency_key="failure", expected_brief_revision=brief["revision"])
    planning = store.begin_draft_readiness_planning(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=started["revision"])
    monkeypatch.setattr(store, "_draft_readiness_plan", lambda **_: (_ for _ in ()).throw(RuntimeError("do not expose details")))
    with pytest.raises(RuntimeError): store.complete_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"], expected_revision=planning["revision"])
    failed = LocalProjectStore(tmp_path).get_draft_readiness(project_id=project.project_id, readiness_id=started["readiness_id"])
    assert failed["status"] == "failed" and failed["error_code"] == "draft_readiness_planning_failed"
