from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from videobox_api.main import create_app
import videobox_api.main as api_main
from videobox_api.orchestration import LocalFirstRuntimeService
from videobox_domain_models.assets import AssetType


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
    assert store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={})
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
