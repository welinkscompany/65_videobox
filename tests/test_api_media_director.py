from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore
import videobox_api.main as api_main
from videobox_api.orchestration import LocalFirstRuntimeService
from videobox_domain_models.assets import AssetType
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
from videobox_provider_interfaces.llm import StructuredLLMResponse


def test_director_route_surface_has_no_gemini_or_legacy_localfirst_dependency() -> None:
    router_path = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "videobox_api" / "routers" / "director_proposals.py"
    source = router_path.read_text(encoding="utf-8")

    assert "gemini_keys" not in source
    assert "Gemini" not in source
    assert "LocalFirst" not in source


def test_director_reload_get_is_behavioral_read_only_and_never_calls_a_provider(tmp_path: Path) -> None:
    class ForbiddenRuntime:
        calls = 0
        def generate_structured(self, **kwargs):
            type(self).calls += 1
            raise AssertionError("reload must not call a provider")
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: ForbiddenRuntime())
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "reload"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    before = deepcopy(app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]))

    response = client.get(f"/api/projects/{project_id}/director/sessions/{session['session_id']}/reload")

    assert response.status_code == 200
    assert response.json()["conversation"] is None and response.json()["proposal"] is None
    assert app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert ForbiddenRuntime.calls == 0


def test_director_normal_message_uses_local_only_structured_runtime_contract(tmp_path: Path) -> None:
    class StrictLocalRuntime:
        external_calls = 0
        calls: list[dict] = []

        def generate_structured(self, *, project_id, task_type, prompt, response_schema, now=None):
            assert project_id == self.project_id
            assert task_type.value == "operator_copy"
            assert prompt == "로컬 응답을 생성해줘"
            assert response_schema == {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
            assert now is None
            type(self).calls.append({"project_id": project_id, "task_type": task_type, "prompt": prompt})
            return StructuredLLMResponse(provider_name="strict-local", model_name="fixture", output_data={"text": "로컬 응답입니다."}, raw_text='{"text":"로컬 응답입니다."}', metadata={"provider_trace": {"routing_mode": "local_only"}})

    runtime = StrictLocalRuntime()
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: runtime)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "strict runtime"}).json()["project_id"]
    runtime.project_id = project_id
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    conversation = client.post(f"/api/projects/{project_id}/director/conversations", json={"session_id": session["session_id"]}).json()

    response = client.post(f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages", json={"session_id": session["session_id"], "client_message_id": "message-1", "text": "로컬 응답을 생성해줘"})

    assert response.status_code == 200, response.text
    assert response.json()["assistant_message"]["text"] == "로컬 응답입니다."
    assert len(StrictLocalRuntime.calls) == 1
    assert StrictLocalRuntime.external_calls == 0


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
    applied = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply",
        json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]},
    )
    assert applied.status_code == 200, applied.text
    # Local output remains allowed for user-owned unknown rights, but the
    # output input must retain the operator-facing copyright warning.
    assert applied.json()["segments"][0]["broll_override"]["warning_provenance"] == ["copyright_confirmation_required"]


def test_partial_regenerated_director_broll_preserves_source_identity_and_blocks_stale_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Director B-roll override must remain fail-closed after partial regeneration."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "partial Director lineage"}).json()["project_id"]
    source = tmp_path / "broll.mp4"
    source.write_bytes(b"director broll bytes")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={
            "semantic_score": .9,
            "review_status": "approved",
            "license_policy": "unknown_user_owned",
            "warning_provenance": ["copyright_confirmation_required"],
            "controls": {"in_sec": .1, "out_sec": 1.5, "fit": "crop"},
        },
    )
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:partial", cache_key="partial")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"])
    assert claim is not None
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "director broll"}]})
    source_timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        timeline_payload={
            "tracks": [],
            "caption_segments": [{"segment_id": "seg_001", "text": "Director B-roll", "start_sec": 0, "end_sec": 2, "confidence": 1}],
            "applied_recommendations": [], "pending_recommendations": [], "review_flags": [],
        },
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=source_timeline["timeline_id"],
        session_payload={"segments": [{"segment_id": "seg_001", "caption_text": "Director B-roll", "start_sec": 0, "end_sec": 2}], "history": []},
    )
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    candidate = next(item for item in proposal["candidates"] if item["media_type"] == "broll")
    materialized = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/candidates/{candidate['candidate_id']}/materialize",
    )
    assert materialized.status_code == 201, materialized.text
    applied = client.post(
        f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/apply",
        json={"candidate_ids": [candidate["candidate_id"]], "expected_revision": session["session_revision"]},
    )
    assert applied.status_code == 200, applied.text
    partial = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/partial-regeneration",
        json={"segment_ids": ["seg_001"], "fields": ["broll"], "expected_revision": applied.json()["session_revision"]},
    )
    assert partial.status_code == 202, partial.text
    timeline = client.get(f"/api/projects/{project_id}/partial-regenerations/{partial.json()['job_id']}").json()["timeline"]
    broll_clip = next(track for track in timeline["tracks"] if track["track_type"] == "broll")["clips"][0]
    assert broll_clip["asset_uri"] == applied.json()["segments"][0]["broll_override"]["asset_uri"]
    assert broll_clip["expected_content_sha256"] == candidate["expected_content_sha256"]
    assert broll_clip["media_revision"]
    assert broll_clip["warning_provenance"] == ["copyright_confirmation_required"]
    stale_path = store.resolve_storage_uri(project_id=project_id, storage_uri=broll_clip["asset_uri"])
    stale_path.write_bytes(stale_path.read_bytes() + b" mutated")
    monkeypatch.setattr(FfmpegFinalRenderer, "_run", lambda _self, _command: pytest.fail("ffmpeg must not start"))
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset"):
        FfmpegFinalRenderer(store=store).render_timeline_to_mp4(project_id=project_id, timeline=timeline, output_path=tmp_path / "out.mp4")
    # The PyCapCut adapter calls this same shared guard before it creates a
    # draft folder; assert that its input contract is blocked as well without
    # making this API-lineage regression depend on the optional pycapcut wheel.
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset"):
        verify_output_sources(store=store, project_id=project_id, timeline=timeline)


def test_director_preference_put_merges_partial_updates_without_dropping_existing_fields(tmp_path: Path) -> None:
    """Task 16 RED: each project-scoped manual preference control is independently durable."""
    client = TestClient(create_app(projects_root=tmp_path / "projects"))
    project_id = client.post("/api/projects", json={"name": "preference merge"}).json()["project_id"]

    first = client.put(f"/api/projects/{project_id}/director/preferences", json={"pin_asset": ["asset-a"]})
    second = client.put(f"/api/projects/{project_id}/director/preferences", json={"exclude_asset": ["asset-b"]})

    assert first.status_code == second.status_code == 200
    assert second.json() == {
        "pin_asset": ["asset-a"], "exclude_asset": ["asset-b"], "exclude_creator": [], "exclude_tag": [],
    }
    assert client.get(f"/api/projects/{project_id}/director/preferences").json() == second.json()


def test_director_preference_partial_mutations_do_not_lose_concurrent_updates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Task 16 RED: partial preference fields must merge inside one SQLite write transaction."""
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project(name="atomic director preferences")
    original = store.get_director_preferences
    barrier = __import__("threading").Barrier(2)

    def synchronized_read(project_id: str) -> dict[str, list[str]]:
        if __import__("threading").current_thread().name.startswith("ThreadPoolExecutor"):
            snapshot = original(project_id)
            barrier.wait(timeout=2)
            return snapshot
        return original(project_id)

    monkeypatch.setattr(store, "get_director_preferences", synchronized_read)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(
            lambda preference: store.save_director_preferences(project.project_id, preference),
            [{"pin_asset": ["asset-a"]}, {"exclude_asset": ["asset-b"]}],
        ))

    assert store.get_director_preferences(project.project_id) == {
        "pin_asset": ["asset-a"], "exclude_asset": ["asset-b"], "exclude_creator": [], "exclude_tag": [],
    }


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


def test_recovery_apply_selects_current_materialization_for_reused_candidate_id(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "recover candidate"}).json()["project_id"]
    source = tmp_path / "bed.mp3"; source.write_bytes(b"bed")
    store.register_asset(project_id=project_id, asset_type=AssetType.BGM, source_path=source, metadata={
        "canonical_metadata_indexed": True, "mood": "calm", "energy": "low", "genre": "ambient",
        "recommended_use": "bed", "license": "valid", "review_status": "approved",
    })
    timeline_id = store.save_timeline_run(project_id=project_id, output_mode="preview", timeline_payload={"tracks": []})["timeline_id"]
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline_id, session_payload={
        "segments": [{"segment_id": "seg", "caption_text": "voice", "start_sec": 0, "end_sec": 2}], "history": [],
    })
    first_proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    first_candidate = first_proposal["candidates"][0]
    first_materialized = client.post(
        f"/api/projects/{project_id}/director/proposals/{first_proposal['proposal_id']}/candidates/{first_candidate['candidate_id']}/materialize"
    ).json()
    store.resolve_storage_uri(project_id=project_id, storage_uri=first_materialized["storage_uri"]).write_bytes(b"corrupted")

    recovery_proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    recovery_candidate = recovery_proposal["candidates"][0]
    recovery_materialized = client.post(
        f"/api/projects/{project_id}/director/proposals/{recovery_proposal['proposal_id']}/candidates/{recovery_candidate['candidate_id']}/materialize"
    ).json()
    response = client.post(
        f"/api/projects/{project_id}/director/proposals/{recovery_proposal['proposal_id']}/apply",
        json={"candidate_ids": [recovery_candidate["candidate_id"]], "expected_revision": recovery_proposal["base_session_revision"]},
    )

    assert response.status_code == 200
    assert response.json()["segments"][0]["music_override"]["asset_id"] == recovery_materialized["asset_id"]


def test_batch_apply_materializes_two_candidates_and_consumes_one_proposal_in_one_session_revision(tmp_path: Path) -> None:
    """Task 15 RED: multi-candidate Director apply is one backend transaction, never a client loop."""
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "batch director"}).json()["project_id"]
    source = tmp_path / "batch.mp4"; source.write_bytes(b"batch-local-broll")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="batch")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "batch"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [
        {"segment_id": "seg-1", "caption_text": "first"}, {"segment_id": "seg-2", "caption_text": "second"},
    ], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    selected = [item["candidate_id"] for item in proposal["candidates"] if item["candidate_id"].split(":")[1] in {"seg-1", "seg-2"}]

    response = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={
        "candidate_ids": selected, "expected_revision": session["session_revision"],
    })

    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied["session_revision"] == session["session_revision"] + 1
    assert {segment["segment_id"] for segment in applied["segments"] if segment.get("broll_override")} == {"seg-1", "seg-2"}
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "applied"
    assert len(store.list_assets(project_id=project_id)) == 2


def test_batch_apply_source_failure_leaves_session_proposal_and_assets_clean(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects"); client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "batch rollback"}).json()["project_id"]
    source = tmp_path / "rollback.mp4"; source.write_bytes(b"before")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="rollback")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "before"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "before"}], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    source_in_project = store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri)
    source_in_project.write_bytes(b"mutated-after-proposal")

    response = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={"candidate_ids": [proposal["candidates"][0]["candidate_id"]], "expected_revision": session["session_revision"]})

    assert response.status_code == 409
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"])["session_revision"] == session["session_revision"]
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "ready"
    assert [item["asset_id"] for item in store.list_assets(project_id=project_id)] == [asset.asset_id]
    assert not (store.project_root(project_id) / ".materializing").exists()


def test_batch_apply_transaction_failure_compensates_copied_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(projects_root=tmp_path / "projects"); client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "batch transaction rollback"}).json()["project_id"]
    source = tmp_path / "transaction.mp4"; source.write_bytes(b"transaction")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(source.read_bytes()).hexdigest(); analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="transaction")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "transaction"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "transaction"}], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    monkeypatch.setattr(store, "_invalidate_output_freshness_with_connection", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("rollback")))

    with pytest.raises(RuntimeError, match="rollback"):
        client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={"candidate_ids": [proposal["candidates"][0]["candidate_id"]], "expected_revision": session["session_revision"]})

    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"])["session_revision"] == session["session_revision"]
    assert store.get_director_proposal(project_id, proposal["proposal_id"]).status == "ready"
    assert [item["asset_id"] for item in store.list_assets(project_id=project_id)] == [asset.asset_id]
    assert not (store.project_root(project_id) / ".materializing").exists()


def test_batch_apply_post_commit_session_mirror_failure_preserves_db_owned_asset_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The JSON mirror is recoverable; a committed batch must not be compensated."""
    app = create_app(projects_root=tmp_path / "projects"); client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "post commit mirror"}).json()["project_id"]
    source = tmp_path / "post-commit.mp4"; source.write_bytes(b"post-commit")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(source.read_bytes()).hexdigest(); analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="post-commit")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "post-commit"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "post-commit"}], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    original_replace = Path.replace
    def fail_session_mirror(source_path: Path, target_path: Path) -> Path:
        if target_path.parent.name == "editing_sessions":
            raise OSError("injected mirror publish failure")
        return original_replace(source_path, target_path)
    monkeypatch.setattr(Path, "replace", fail_session_mirror)

    with pytest.raises(OSError, match="SQLite commit succeeded"):
        client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={"candidate_ids": [proposal["candidates"][0]["candidate_id"]], "expected_revision": session["session_revision"]})

    # Do not read the session while the injected mirror fault remains active:
    # reads deliberately repair the mirror from the committed SQLite value.
    materialized = [item for item in store.list_assets(project_id=project_id) if item["asset_id"] != asset.asset_id]
    assert len(materialized) == 1
    materialized_path = store.resolve_storage_uri(project_id=project_id, storage_uri=materialized[0]["storage_uri"])
    assert materialized_path.is_file() and materialized_path.read_bytes() == b"post-commit"
    monkeypatch.undo()
    recovered = store.get_editing_session(project_id=project_id, session_id=session["session_id"])
    assert recovered["session_revision"] == session["session_revision"] + 1


def test_store_startup_reconciles_crashed_batch_manifest_without_deleting_registered_asset(tmp_path: Path) -> None:
    """A restart compensates uncommitted batch bytes but keeps SQLite-owned bytes."""
    app = create_app(projects_root=tmp_path / "projects"); client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "batch recovery"}).json()["project_id"]
    source = tmp_path / "registered.mp4"; source.write_bytes(b"registered")
    registered = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    registered_path = store.resolve_storage_uri(project_id=project_id, storage_uri=registered.storage_uri)
    operations = store.project_root(project_id) / ".batch-director-operations"; stage = operations / "batch-crashed"; stage.mkdir(parents=True)
    staged_path = stage / "staged.mp4"; staged_path.write_bytes(b"staged")
    orphan_path = store.project_root(project_id) / "media" / "broll" / "orphan.mp4"; orphan_path.parent.mkdir(parents=True); orphan_path.write_bytes(b"orphan")
    manifest = operations / "batch-crashed.json"
    manifest.write_text(json.dumps({"operation_id": "batch-crashed", "status": "staging", "entries": [
        {"staged_path": str(staged_path), "destination_path": str(registered_path), "sha256": sha256(registered_path.read_bytes()).hexdigest()},
        {"staged_path": str(staged_path), "destination_path": str(orphan_path), "sha256": sha256(orphan_path.read_bytes()).hexdigest()},
    ]}), encoding="utf-8")

    type(store)(store.projects_root)

    assert registered_path.is_file()
    assert not orphan_path.exists()
    assert not staged_path.exists()
    assert not manifest.exists()


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
