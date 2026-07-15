from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from videobox_api.main import create_app
import videobox_api.main as api_main
from videobox_api.orchestration import LocalFirstRuntimeService
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType


def test_create_app_rejects_fallback_capable_runtime_from_local_only_factory(tmp_path: Path) -> None:
    """The local-only DI seam cannot be used to smuggle a Gemini fallback graph."""
    def fallback_factory(store):
        return LocalFirstRuntimeService(
            store=store,
            local_provider=object(),
            gemini_provider=object(),
            local_config=object(),
            gemini_config=object(),
        )

    with pytest.raises(ValueError, match="fallback-capable"):
        create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=fallback_factory)


def test_director_route_never_invokes_local_failure_or_external_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Director composition is local-store only; it cannot reach a fallback provider graph."""
    class LocalFailureRuntime:
        routing_mode = "local_only"

        def __init__(self) -> None:
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            raise AssertionError("Director proposal must not request runtime generation")

    runtime = LocalFailureRuntime()
    external_calls = {"gemini": 0, "http": 0}

    def forbidden_gemini(*args, **kwargs):
        external_calls["gemini"] += 1
        raise AssertionError("Gemini construction is forbidden for Director")

    def forbidden_http(*args, **kwargs):
        external_calls["http"] += 1
        raise AssertionError("External HTTP is forbidden for Director")

    monkeypatch.setattr(api_main, "GeminiRESTStructuredProvider", forbidden_gemini, raising=False)
    monkeypatch.setattr(api_main, "urlopen", forbidden_http)
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: runtime)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "no-runtime"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "local"}], "history": []})

    response = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]})

    assert response.status_code == 409
    assert response.json()["code"] == "director_analysis_blocked"
    assert runtime.calls == 0
    assert external_calls == {"gemini": 0, "http": 0}


def test_director_reports_recovery_lifecycle_when_analysis_is_not_applicable(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "blocked"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "blocked"}], "history": []})
    response = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]})
    assert response.status_code == 409
    assert response.json()["code"] == "director_analysis_blocked"
    assert response.json()["lifecycle"]["status"] == "blocked"
    assert response.json()["lifecycle"]["recovery_action"] == "analyse_or_retry_assets"


def test_editing_session_get_preserves_history_action_metadata(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "history metadata"}).json()["project_id"]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": [{
            "mutation_type": "caption_update", "segment_id": "seg-1", "action_id": "action-1",
            "label": "자막 변경", "created_at": "2026-07-16T00:00:00Z", "reversible": True, "blocked_reason": None,
        }]},
    )
    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session['session_id']}")
    assert response.status_code == 200
    assert response.json()["history"] == [{
        "mutation_type": "caption_update", "segment_id": "seg-1", "caption_text": None, "cut_action": None,
        "asset_id": None, "overlay_type": None, "recommendation_id": None, "inverse_payload": None,
        "forward_payload": None, "action_id": "action-1", "label": "자막 변경", "created_at": "2026-07-16T00:00:00Z",
        "reversible": True, "blocked_reason": None,
    }]


def test_director_proposal_api_e2e_is_snapshot_only_and_returns_actionable_stale_preflight(tmp_path: Path) -> None:
    """Task 9 contract: proposal reads real local state but never edits the session."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "director"}).json()["project_id"]
    store = app.state.store
    source = tmp_path / "office.mp4"
    source.write_bytes(b"current-local-broll")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={
            "semantic_score": 0.9,
            "license_policy": "unknown_user_owned",
            "warning_provenance": ["copyright_confirmation_required"],
            "review_status": "approved",
        },
    )
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="local")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
    assert claim is not None
    assert store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "office"}]})
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline_001",
        session_payload={"segments": [{"segment_id": "seg_001", "source_script_segment_id": "script_001", "caption_text": "office work", "start_sec": 0, "end_sec": 3}], "history": []},
    )
    session_before = deepcopy(store.get_editing_session(project_id=project_id, session_id=session["session_id"]))

    created = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]})
    assert created.status_code == 201
    proposal = created.json()
    assert proposal["candidates"][0]["visible_reference_code"] == "P01-B-01"
    assert proposal["candidates"][0]["license_policy"] == "unknown_user_owned"
    assert "copyright_confirmation_required" in proposal["candidates"][0]["warning_provenance"]
    assert proposal["diff"]["placements"]["add"]
    assert proposal["diff"]["placements"]["replace"]
    assert proposal["diff"]["placements"]["remove"]
    assert proposal["diff"]["selection_scope"] == ["seg_001"]
    assert proposal["diff"]["scene_controls"]
    assert proposal["diff"]["gain_ducking"]
    assert proposal["diff"]["caption_impact"]
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == session_before

    assert client.get(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}").json()["proposal_id"] == proposal["proposal_id"]
    preflight = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["diff"] == proposal["diff"]
    store.update_asset_metadata(project_id=project_id, asset_id=asset.asset_id, metadata_patch={"tags": ["changed"]})
    stale = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/preflight")
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_proposal"
    assert "asset_index_revision" in stale.json()["stale_reasons"]
    assert stale.json()["action"] == "refresh"
    assert stale.json()["diff"] == proposal["diff"]
    refreshed = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/refresh")
    assert refreshed.status_code == 201
    preferences = client.put(f"/api/projects/{project_id}/director/preferences", json={"pin_asset": [asset.asset_id]}).json()
    assert preferences["pin_asset"] == [asset.asset_id]
    assert client.get(f"/api/projects/{project_id}/director/preferences").json()["pin_asset"] == [asset.asset_id]


def test_director_candidate_preview_and_materialize_preserve_identity_controls_and_session(tmp_path: Path) -> None:
    """Task 10 RED: proposal candidates need a safe read-only preview/materialization boundary."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "candidate preview"}).json()["project_id"]
    source = tmp_path / "broll.mp4"
    source.write_bytes(b"candidate bytes")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"semantic_score": .9, "review_status": "approved", "license_policy": "unknown_user_owned", "warning_provenance": ["copyright_confirmation_required"], "controls": {"in_sec": 0.25, "out_sec": 1.75}})
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="candidate")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
    assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "broll"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "candidate", "start_sec": 1, "end_sec": 3}], "history": []})
    before = deepcopy(store.get_editing_session(project_id=project_id, session_id=session["session_id"]))
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    candidate = proposal["candidates"][0]

    preview = client.get(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/preview")
    assert preview.status_code == 200
    assert preview.content == b"candidate bytes"
    assert json.loads(preview.headers["x-videobox-proposal-controls"]) == candidate["controls"]
    assert preview.headers["x-videobox-autoplay"] == "false"
    assert preview.headers["x-videobox-in-sec"] == "0.25"
    assert preview.headers["x-videobox-out-sec"] == "1.75"
    assert not (store.project_root(project_id) / ".preview-snapshots").exists()
    stored_source = store.resolve_storage_uri(project_id=project_id, storage_uri=store.get_asset(project_id=project_id, asset_id=asset.asset_id)["storage_uri"])
    stored_source.unlink()
    failed = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize")
    assert failed.status_code == 409
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert [item["asset_id"] for item in store.list_assets(project_id=project_id)] == [asset.asset_id]
    assert not (store.project_root(project_id) / ".materializing").exists()
    stored_source.write_bytes(b"candidate bytes")
    materialized = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize")
    assert materialized.status_code == 201
    assert materialized.json()["content_sha256"] == candidate["expected_content_sha256"]
    assert materialized.json()["media_revision"] == candidate["media_revision"]
    assert materialized.json()["warning_provenance"] == ["copyright_confirmation_required"]
    assert materialized.json()["asset_id"] != asset.asset_id
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before


def test_indexed_bgm_preflight_needs_no_visual_analysis_and_bad_expiry_is_422(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "indexed"}).json()["project_id"]
    source = tmp_path / "music.mp3"; source.write_bytes(b"music")
    store.register_asset(project_id=project_id, asset_type=AssetType.BGM, source_path=source, metadata={"canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient", "recommended_use": "bed", "license": "valid", "review_status": "approved"})
    sfx = tmp_path / "impact.wav"; sfx.write_bytes(b"impact")
    store.register_asset(project_id=project_id, asset_type=AssetType.SFX, source_path=sfx, metadata={"canonical_metadata_indexed": True, "action_event": "impact", "intensity": "high", "recommended_use": "accent", "license": "valid", "review_status": "approved"})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "music"}], "history": []})
    assert client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"], "expires_at": "not-a-date"}).status_code == 422
    assert client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"], "expires_at": "2030-01-01T00:00:00"}).status_code == 422
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]})
    assert proposal.status_code == 201
    candidate = proposal.json()["candidates"][0]
    assert candidate["media_revision"]
    assert {item["media_type"] for item in proposal.json()["candidates"]} == {"bgm", "sfx"}
    assert client.post(f"/api/projects/{project_id}/director/proposals/{proposal.json()['proposal_id']}/preflight").status_code == 200


def test_materialized_candidate_apply_is_one_named_atomic_session_action(tmp_path: Path) -> None:
    """Task 11 RED: applying a proposal consumes materialized identity in one CAS edit."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "atomic director"}).json()["project_id"]
    source = tmp_path / "bed.mp3"; source.write_bytes(b"bed")
    store.register_asset(project_id=project_id, asset_type=AssetType.BGM, source_path=source, metadata={
        "canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient",
        "recommended_use": "bed", "license": "valid", "review_status": "approved",
    })
    timeline_id = store.save_timeline_run(project_id=project_id, output_mode="preview", timeline_payload={"tracks": []})["timeline_id"]
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline_id, session_payload={
        "segments": [{"segment_id": "seg", "caption_text": "voice", "start_sec": 0, "end_sec": 2, "cut_action": "keep", "review_required": False}], "history": [],
    })
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    candidate = proposal["candidates"][0]
    materialized = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize"
    )
    assert materialized.status_code == 201
    store.save_review_state(project_id=project_id, timeline_id=timeline_id, status="approved")
    subtitle = store.save_subtitle_run(project_id=project_id, timeline_id=timeline_id, subtitle_payload={"entries": []})
    preview = store.save_preview_run(
        project_id=project_id,
        timeline_id=timeline_id,
        preview_payload={"artifact_kind": "preview_manifest", "clips": [], "player_html": ""},
    )
    final_source = tmp_path / "final.mp4"; final_source.write_bytes(b"final")
    final = store.save_final_render(project_id=project_id, timeline_id=timeline_id, source_output_path=final_source)
    capcut = store.save_capcut_export(project_id=project_id, timeline_id=timeline_id, export_payload={"tracks": []})
    capcut_draft_source = tmp_path / "capcut-draft-source"
    capcut_draft_source.mkdir()
    (capcut_draft_source / "draft_content.json").write_text("{}", encoding="utf-8")
    capcut_draft = store.save_capcut_draft_export(
        project_id=project_id,
        timeline_id=timeline_id,
        source_draft_path=capcut_draft_source,
    )

    # These are the same durable job/result contracts used by the output GET
    # endpoints.  The output bodies are seeded deterministically here because
    # the media-director regression is about freshness after an edit, rather
    # than renderer/encoder correctness.
    def completed_output_job(job_type: JobType, output_ref: str) -> str:
        job = store.create_job(project_id=project_id, job_type=job_type, status=JobStatus.SUCCEEDED)
        store.update_job(
            project_id=project_id,
            job_id=job["job_id"],
            status=JobStatus.SUCCEEDED,
            output_ref=output_ref,
        )
        return str(job["job_id"])

    subtitle_job_id = completed_output_job(JobType.SUBTITLE_RENDER, subtitle["subtitle_id"])
    preview_job_id = completed_output_job(JobType.PREVIEW_RENDER, preview["preview_id"])
    capcut_job_id = completed_output_job(JobType.CAPCUT_EXPORT, capcut["export_id"])
    final_job_id = completed_output_job(JobType.FINAL_RENDER, final["export_id"])
    capcut_draft_job_id = completed_output_job(JobType.CAPCUT_DRAFT_EXPORT, capcut_draft["export_id"])
    response = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply", json={
        "candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"],
    })
    assert response.status_code == 200
    applied = response.json()
    assert applied["session_revision"] == session["session_revision"] + 1
    assert applied["undo_count"] == 1
    assert applied["history"][-1]["label"] == "디렉터 제안 적용"
    assert applied["segments"][0]["music_override"]["asset_id"] == materialized.json()["asset_id"]
    assert {key: value["is_current"] for key, value in applied["output_freshness"].items()} == {
        "review": False, "subtitle": False, "preview": False, "final": False, "capcut": False,
    }
    assert store.get_review_state(project_id=project_id, timeline_id=timeline_id)["is_current"] is False
    review_http = client.get(f"/api/projects/{project_id}/review-approvals/timelines/{timeline_id}")
    assert review_http.status_code == 200
    assert review_http.json()["is_current"] is False
    assert review_http.json()["source_session_revision"] == session["session_revision"]
    assert review_http.json()["invalidated_at"]
    assert review_http.json()["invalidated_reason"]
    assert store.get_subtitle_run(project_id=project_id, subtitle_id=subtitle["subtitle_id"])["is_current"] is False
    assert store.get_preview_run(project_id=project_id, preview_id=preview["preview_id"])["is_current"] is False
    assert store.get_final_render_export(project_id=project_id, export_id=final["export_id"])["is_current"] is False
    assert store.get_export_run(project_id=project_id, export_id=capcut["export_id"])["is_current"] is False
    assert store.get_capcut_draft_export(project_id=project_id, export_id=capcut_draft["export_id"])["is_current"] is False

    # API readers must return the durable stale marker, not a cached/job-start
    # snapshot, including the canonical review-approval reader.
    output_reads = {
        "subtitle": (f"/api/projects/{project_id}/subtitles/{subtitle_job_id}", "subtitle"),
        "preview": (f"/api/projects/{project_id}/previews/{preview_job_id}", "preview"),
        "capcut": (f"/api/projects/{project_id}/exports/{capcut_job_id}", "export"),
        "final": (f"/api/projects/{project_id}/final-renders/{final_job_id}", "render"),
        "capcut_draft": (f"/api/projects/{project_id}/capcut-draft-exports/{capcut_draft_job_id}", "export"),
    }
    for endpoint, artifact_key in output_reads.values():
        body = client.get(endpoint).json()
        assert body["status"] == "succeeded"
        artifact = body[artifact_key]
        assert artifact["source_session_revision"] == session["session_revision"]
        assert artifact["is_current"] is False
        assert artifact["invalidated_at"]
        assert artifact["invalidated_reason"] == "editing_session_mutation"
    undo = client.post(f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/undo", json={"expected_revision": applied["session_revision"]})
    assert undo.status_code == 200
    redo = client.post(f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/redo", json={"expected_revision": undo.json()["session_revision"]})
    assert redo.status_code == 200
    assert store.get_review_state(project_id=project_id, timeline_id=timeline_id)["is_current"] is False
    assert store.get_subtitle_run(project_id=project_id, subtitle_id=subtitle["subtitle_id"])["is_current"] is False
    assert store.get_preview_run(project_id=project_id, preview_id=preview["preview_id"])["is_current"] is False
    assert store.get_final_render_export(project_id=project_id, export_id=final["export_id"])["is_current"] is False
    assert store.get_export_run(project_id=project_id, export_id=capcut["export_id"])["is_current"] is False


def test_failed_apply_preserves_independent_materialized_asset_and_rolls_back_session_and_proposal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 11 RED: Task 10 project-local assets are reusable, never apply-owned or orphaned."""
    app = create_app(projects_root=tmp_path / "projects"); client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "apply rollback"}).json()["project_id"]
    source = tmp_path / "bed.mp3"; source.write_bytes(b"bed")
    store.register_asset(project_id=project_id, asset_type=AssetType.BGM, source_path=source, metadata={"canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient", "recommended_use": "bed", "license": "valid", "review_status": "approved"})
    timeline_id = store.save_timeline_run(project_id=project_id, output_mode="preview", timeline_payload={"tracks": []})["timeline_id"]
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline_id, session_payload={"segments": [{"segment_id": "seg", "caption_text": "voice", "start_sec": 0, "end_sec": 2, "cut_action": "keep", "review_required": False}], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json(); candidate = proposal["candidates"][0]
    materialized = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize").json()
    before = deepcopy(store.get_editing_session(project_id=project_id, session_id=session["session_id"]))
    asset_path = store.resolve_storage_uri(project_id=project_id, storage_uri=materialized["storage_uri"])
    monkeypatch.setattr(store, "_invalidate_output_freshness_with_connection", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected transaction failure")))
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply", json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]})
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "ready"
    assert asset_path.is_file() and sha256(asset_path.read_bytes()).hexdigest() == candidate["expected_content_sha256"]
    # Mutate only after the router's preflight has read the project-local file.
    # The store transaction must rehash and reject without consuming the proposal.
    monkeypatch.undo()
    original_apply = store.apply_director_proposal_transaction
    original_bytes = asset_path.read_bytes()
    def race_materialized_sha(**kwargs):
        asset_path.write_bytes(b"post-preflight mutation")
        return original_apply(**kwargs)
    monkeypatch.setattr(store, "apply_director_proposal_transaction", race_materialized_sha)
    sha_race = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply", json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]})
    assert sha_race.status_code == 409
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "ready"
    assert asset_path.is_file() and asset_path.read_bytes() == b"post-preflight mutation"
    assert not (store.project_root(project_id) / ".materializing").exists()
    asset_path.write_bytes(original_bytes)
    # Let route-level preflight pass, then mutate the durable asset-index just
    # before the store opens BEGIN IMMEDIATE.  The in-transaction SQL check,
    # not the earlier Python check, must reject this race.
    monkeypatch.undo()
    monkeypatch.undo()
    original_apply = store.apply_director_proposal_transaction
    def race_asset_index(**kwargs):
        store.bump_asset_index_revision(project_id)
        return original_apply(**kwargs)
    monkeypatch.setattr(store, "apply_director_proposal_transaction", race_asset_index)
    race = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply", json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]})
    assert race.status_code == 409
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "ready"
    assert asset_path.is_file() and sha256(asset_path.read_bytes()).hexdigest() == candidate["expected_content_sha256"]
