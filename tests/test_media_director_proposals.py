from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

from videobox_core_engine.director_proposals import create_proposal, create_and_save_proposal
from videobox_core_engine.media_ranking import rank_candidates
from videobox_storage.local_project_store import LocalProjectStore
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.script_draft_session import build_provisional_script_draft_session
from videobox_domain_models.assets import AssetType


PROJECT_ID = "project"


def candidate(asset_id: str = "asset-a"):
    return rank_candidates(
        {"segment_id": "script:s:001", "text": "여행", "duration_sec": 3},
        [{"asset_id": asset_id, "media_type": "broll", "tags": ["여행"], "availability": "available", "license": "valid", "review_status": "approved"}],
    )[0]


def test_proposal_is_frozen_and_codes_are_stable() -> None:
    proposal = create_proposal(base_session_revision=4, asset_index_revision=9, source_session_id="session-1", candidates=[candidate()], revision=1)
    assert proposal.candidates[0].visible_reference_code == "P01-B-01"
    with pytest.raises(FrozenInstanceError):
        proposal.status = "stale"  # type: ignore[misc]
    with pytest.raises((TypeError, AttributeError)):
        proposal.candidates[0].scores["favorite"] = 99  # type: ignore[index]


def test_proposal_deep_freezes_nested_diff_controls_and_metadata() -> None:
    ranked = __import__("videobox_core_engine.media_ranking", fromlist=["rank_candidates"]).rank_candidates(
        {"text": "여행", "duration_sec": 2},
        [{"asset_id": "a", "media_type": "bgm", "tags": ["여행"], "availability": "available", "license": "valid", "review_status": "approved", "controls": {"trim": {"enabled": True}}, "mood": {"name": "calm"}}],
    )
    proposal = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=ranked, revision=1, diff={"nested": {"items": ["x"]}})
    with pytest.raises((TypeError, AttributeError)):
        proposal.diff["nested"]["items"].append("mutate")  # type: ignore[index]
    with pytest.raises(TypeError):
        proposal.candidates[0].controls["trim"]["enabled"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        proposal.candidates[0].canonical_metadata["mood"]["name"] = "loud"  # type: ignore[index]


def test_deep_frozen_snapshot_persists_as_json(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    ranked = __import__("videobox_core_engine.media_ranking", fromlist=["rank_candidates"]).rank_candidates(
        {"text": "여행", "duration_sec": 2},
        [{"asset_id": "a", "media_type": "bgm", "tags": ["여행"], "availability": "available", "license": "valid", "review_status": "approved", "controls": {"trim": {"enabled": True}}}],
    )
    proposal = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=ranked, revision=1, diff={"nested": {"items": ["x"]}})
    store.save_director_proposal(project.project_id, proposal)
    assert store.get_director_proposal(project.project_id, proposal.proposal_id).diff["nested"]["items"] == ("x",)


def test_proposal_round_trips_source_and_target_identity_without_mutating_session(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    session = {"session_id": "session-1", "segments": [{"segment_id": "script:s:001"}]}
    before = repr(session)
    proposal = create_proposal(base_session_revision=2, asset_index_revision=3, source_session_id="session-1", source_script_segment_ids=["script:s:001"], target_segment_ids=["target-9"], candidates=[candidate()], revision=1)
    store.save_director_proposal(project.project_id, proposal)
    reloaded = LocalProjectStore(tmp_path).get_director_proposal(project.project_id, proposal.proposal_id)
    assert reloaded.source_script_segment_ids == ("script:s:001",)
    assert reloaded.target_segment_ids == ("target-9",)
    assert repr(session) == before


def test_proposal_persists_revision_preferences_expiry_and_selective_stale(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    proposal = create_proposal(base_session_revision=4, asset_index_revision=9, source_session_id="session-1", source_script_segment_ids=["script:s:001"], candidates=[candidate()], revision=1, expires_at="2030-01-01T00:00:00+00:00")
    store.save_director_proposal(project.project_id, proposal)
    store.save_director_preferences(project.project_id, {"exclude_tag": ["광고"], "pin_asset": ["asset-a"]})
    loaded = store.get_director_proposal(project.project_id, proposal.proposal_id)
    assert loaded.base_session_revision == 4
    assert loaded.asset_index_revision == 9
    assert store.get_director_preferences(project.project_id)["exclude_tag"] == ["광고"]
    assert store.mark_director_proposals_stale_for_script_alignment(project.project_id, "session-1", ["script:s:001"]) == 1
    assert store.get_director_proposal(project.project_id, proposal.proposal_id).status == "stale"
    assert store.mark_director_proposals_stale_for_script_alignment(project.project_id, "session-1", ["script:s:001"]) == 0


def test_preferences_are_project_scoped_and_media_codes_are_stable(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    first, second = store.bootstrap_project("first"), store.bootstrap_project("second")
    store.save_director_preferences(first.project_id, {"pin_asset": ["only-first"]})
    assert LocalProjectStore(tmp_path).get_director_preferences(second.project_id)["pin_asset"] == []
    candidates = [candidate("b"), candidate("m"), candidate("s")]
    # reference code media letter contract is supplied by the ranker for B/M/S.
    from videobox_core_engine.media_ranking import rank_candidates
    ranked = rank_candidates({"text": "x", "duration_sec": 1}, [
        {"asset_id": "b", "media_type": "broll", "availability": "available", "license": "valid", "review_status": "approved"},
        {"asset_id": "m", "media_type": "bgm", "availability": "available", "license": "valid", "review_status": "approved"},
        {"asset_id": "s", "media_type": "sfx", "availability": "available", "license": "valid", "review_status": "approved"},
    ])
    assert [item.visible_reference_code[4] for item in ranked] == ["B", "M", "S"]
    assert all(set(item.scores) >= {"semantic_similarity", "structured_tag_match", "duration_match", "availability_license"} and item.reason_chips for item in ranked)


def test_asset_index_revision_is_durable(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    assert store.bump_asset_index_revision(project.project_id) == 1
    assert LocalProjectStore(tmp_path).get_asset_index_revision(project.project_id) == 1


def test_asset_index_revision_is_unique_when_two_store_instances_interleave(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    with ThreadPoolExecutor(max_workers=2) as pool:
        revisions = list(pool.map(lambda _: LocalProjectStore(tmp_path).bump_asset_index_revision(project.project_id), range(2)))
    assert sorted(revisions) == [1, 2]


def test_register_and_metadata_index_mutations_bump_durable_asset_index_revision(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.bin"
    source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    assert store.get_asset_index_revision(project.project_id) == 1
    store.update_asset_metadata(project_id=project.project_id, asset_id=asset.asset_id, metadata_patch={"tags": ["여행"]})
    assert LocalProjectStore(tmp_path / "projects").get_asset_index_revision(project.project_id) == 2


def test_asset_mutations_rollback_when_index_increment_fails(tmp_path, monkeypatch) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.bin"
    source.write_bytes(b"clip")
    monkeypatch.setattr(store, "_increment_asset_index_revision_with_connection", lambda *_: (_ for _ in ()).throw(RuntimeError("index failure")))
    with pytest.raises(RuntimeError, match="index failure"):
        store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    assert store.list_assets(project_id=project.project_id) == []

    good = LocalProjectStore(tmp_path / "projects")
    asset = good.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    monkeypatch.setattr(good, "_increment_asset_index_revision_with_connection", lambda *_: (_ for _ in ()).throw(RuntimeError("index failure")))
    with pytest.raises(RuntimeError, match="index failure"):
        good.update_asset_metadata(project_id=project.project_id, asset_id=asset.asset_id, metadata_patch={"tags": ["changed"]})
    assert good.get_asset(project_id=project.project_id, asset_id=asset.asset_id)["metadata"] == {}


def test_delete_asset_bumps_revision_and_rolls_back_db_when_increment_fails(tmp_path, monkeypatch) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.bin"
    source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    store.record_media_analysis_cache(project_id=project.project_id, asset_id=asset.asset_id, source_sha256="sha", cache_key="key")
    monkeypatch.setattr(store, "_increment_asset_index_revision_with_connection", lambda *_: (_ for _ in ()).throw(RuntimeError("index failure")))
    with pytest.raises(RuntimeError, match="index failure"):
        store.delete_asset(project_id=project.project_id, asset_id=asset.asset_id)
    assert store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)["asset_id"] == asset.asset_id
    assert store.list_media_analysis_cache(project_id=project.project_id, asset_id=asset.asset_id)
    monkeypatch.undo()
    store.delete_asset(project_id=project.project_id, asset_id=asset.asset_id)
    assert LocalProjectStore(tmp_path / "projects").get_asset_index_revision(project.project_id) == 2
    with pytest.raises(KeyError):
        store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)


def test_proposal_revision_allocator_is_monotonic_after_reload(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    assert store.next_director_proposal_revision(project.project_id) == 1
    assert LocalProjectStore(tmp_path).next_director_proposal_revision(project.project_id) == 2


def test_proposal_revision_allocator_is_unique_when_two_store_instances_interleave(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    with ThreadPoolExecutor(max_workers=2) as pool:
        revisions = list(pool.map(lambda _: LocalProjectStore(tmp_path).next_director_proposal_revision(project.project_id), range(2)))
    assert sorted(revisions) == [1, 2]


def test_store_backed_proposal_creation_allocates_p01_then_p02_after_restart(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    first = create_and_save_proposal(store=store, project_id=project.project_id, base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate("one")])
    second = create_and_save_proposal(store=LocalProjectStore(tmp_path), project_id=project.project_id, base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate("two")])
    assert (first.revision_code, first.candidates[0].visible_reference_code) == ("P01", "P01-B-01")
    assert (second.revision_code, second.candidates[0].visible_reference_code) == ("P02", "P02-B-01")


def test_same_proposal_id_rejects_changed_immutable_snapshot(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    original = create_proposal(proposal_id="proposal:fixed", base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate("one")], revision=1)
    changed = create_proposal(proposal_id="proposal:fixed", base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate("two")], revision=1)
    store.save_director_proposal(project.project_id, original)
    with pytest.raises(ValueError, match="immutable"):
        store.save_director_proposal(project.project_id, changed)
    assert store.get_director_proposal(project.project_id, original.proposal_id).candidates[0].asset_id == "one"


def test_concurrent_same_proposal_id_accepts_only_one_immutable_snapshot(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    proposals = [
        create_proposal(proposal_id="proposal:race", base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate(asset_id)], revision=1)
        for asset_id in ("one", "two")
    ]
    def save(proposal):
        try:
            LocalProjectStore(tmp_path).save_director_proposal(project.project_id, proposal)
            return "saved"
        except ValueError:
            return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, proposals))
    assert sorted(outcomes) == ["rejected", "saved"]
    assert LocalProjectStore(tmp_path).get_director_proposal(project.project_id, "proposal:race").candidates[0].asset_id in {"one", "two"}


def test_expiry_is_evaluated_without_sleep(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    proposal = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id="s", candidates=[candidate()], revision=1, expires_at="2020-01-01T00:00:00+00:00")
    store.save_director_proposal(project.project_id, proposal)
    assert store.get_director_proposal(project.project_id, proposal.proposal_id, now=datetime(2021, 1, 1, tzinfo=UTC)).status == "expired"


def test_successful_alignment_selectively_stales_ready_proposals_after_restart(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="script-draft", session_payload=build_provisional_script_draft_session(project_id=project.project_id, script_asset_id="script", script_text="첫 문장입니다."))
    matching = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id=session["session_id"], source_script_segment_ids=["script:script:001"], candidates=[candidate("match")], revision=1)
    other = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id="other-session", source_script_segment_ids=["script:script:001"], candidates=[candidate("other")], revision=1)
    store.save_director_proposal(project.project_id, matching)
    store.save_director_proposal(project.project_id, other)
    aligned = LocalPipelineRunner(store).apply_script_draft_narration_alignment(project_id=project.project_id, session_id=session["session_id"], expected_revision=session["session_revision"], aligned_segments=[{"source_script_segment_id": "script:script:001", "start_sec": 0.0, "end_sec": 2.0}])
    assert aligned["timing_source"] == "narration_alignment"
    reloaded = LocalProjectStore(tmp_path)
    assert reloaded.get_director_proposal(project.project_id, matching.proposal_id).status == "stale"
    assert reloaded.get_director_proposal(project.project_id, other.proposal_id).status == "ready"


def test_alignment_and_stale_are_atomic_when_stale_write_fails(tmp_path, monkeypatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project("p")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="script-draft", session_payload=build_provisional_script_draft_session(project_id=project.project_id, script_asset_id="script", script_text="첫 문장입니다."))
    proposal = create_proposal(base_session_revision=1, asset_index_revision=1, source_session_id=session["session_id"], source_script_segment_ids=["script:script:001"], candidates=[candidate()], revision=1)
    store.save_director_proposal(project.project_id, proposal)
    monkeypatch.setattr(store, "_mark_director_proposals_stale_with_connection", lambda *_: (_ for _ in ()).throw(RuntimeError("stale failure")))
    with pytest.raises(RuntimeError, match="stale failure"):
        LocalPipelineRunner(store).apply_script_draft_narration_alignment(project_id=project.project_id, session_id=session["session_id"], expected_revision=1, aligned_segments=[{"source_script_segment_id": "script:script:001", "start_sec": 0.0, "end_sec": 2.0}])
    assert store.get_editing_session(project_id=project.project_id, session_id=session["session_id"])["timing_source"] == "provisional_script"
    assert store.get_director_proposal(project.project_id, proposal.proposal_id).status == "ready"
