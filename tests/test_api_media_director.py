from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from videobox_api.main import create_app
from videobox_storage.local_project_store import LocalProjectStore
from videobox_domain_models.assets import AssetType
from videobox_domain_models.director_proposals import DirectorCandidate, DirectorProposal
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_domain_models.yujin_creator_context import UserApprovedPreference
from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_core_engine.output_source_verifier import OutputSourceStaleError, verify_output_sources
from videobox_provider_interfaces.llm import StructuredLLMResponse


def test_director_route_surface_has_no_external_provider_dependency() -> None:
    router_path = Path(__file__).resolve().parents[1] / "services" / "api" / "src" / "videobox_api" / "routers" / "director_proposals.py"
    source = router_path.read_text(encoding="utf-8")

    retired_provider = "g" + "emini"
    assert retired_provider not in source.lower()


def test_yujin_editing_proposal_is_read_only_until_apply(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture",
                output_data={"schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.", "proposal": {"proposal_id": "fixture", "base_session_revision": 1, "operations": [{"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}]}},
                raw_text="{}", metadata={},
            )
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "editing candidate"}).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [
                {"segment_id": "scene-1", "start_sec": 0, "end_sec": 4},
                {"segment_id": "scene-2", "start_sec": 4, "end_sec": 12},
            ],
            "history": [],
        },
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/yujin-editing-proposals",
        json={"instruction": "두 번째 장면을 두 배로 빠르게 하고 자막도 맞춰줘"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ready"
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"])["session_revision"] == session["session_revision"]
    proposal_id = response.json()["proposal_id"]
    store.update_editing_session(project_id=project_id, session_id=session["session_id"], session_payload=session)

    stale = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/yujin-editing-proposals/{proposal_id}/preflight"
    )

    assert stale.status_code == 409
    assert stale.json()["action"] == "새 편집안을 받아 보세요."


def test_yujin_editing_proposal_preview_creates_a_durable_preview_without_mutating_the_session(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture", raw_text="{}", metadata={},
                output_data={"schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.", "proposal": {
                    "proposal_id": "preview", "base_session_revision": 1,
                    "operations": [{"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}],
                }},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "editing proposal preview"}).json()["project_id"]
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"output": {"width": 1280, "height": 720, "duration_sec": 12}, "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project_id, timeline_id=timeline["timeline_id"],
        session_payload={"segments": [
            {"segment_id": "scene-1", "start_sec": 0, "end_sec": 4},
            {"segment_id": "scene-2", "start_sec": 4, "end_sec": 12},
        ], "history": []},
    )
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "둘째 장면을 빠르게"}).json()
    before = store.get_editing_session(project_id=project_id, session_id=session["session_id"])

    response = client.post(f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/preview")

    assert response.status_code == 202, response.text
    assert response.json()["generation_id"].startswith("proposal_preview_")
    assert response.json()["status"] in {"pending", "running", "failed"}
    assert store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before


def test_yujin_editing_proposal_preview_recovers_a_running_claim_from_a_previous_process(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("proposal preview restart recovery")
    session = store.save_editing_session(
        project_id=project.project_id, timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    record = store.begin_proposal_preview(
        project_id=project.project_id, session_id=session["session_id"], proposal_id="proposal",
        expected_revision=session["session_revision"], fingerprint="f" * 64,
    )
    assert store.claim_proposal_preview(
        project_id=project.project_id, generation_id=record["generation_id"],
        owner_token="proposal-preview-worker:previous-process:worker",
    )

    recovered = LocalProjectStore(tmp_path / "projects")
    assert recovered.recover_inherited_proposal_preview_claims(
        project_id=project.project_id,
        process_epoch="new-process",
    ) == 1

    failed = recovered.get_proposal_preview(project_id=project.project_id, generation_id=record["generation_id"])
    assert failed["state"] == "failed"
    assert failed["error_message"] == "process_restarted"
    retried = recovered.begin_proposal_preview(
        project_id=project.project_id, session_id=session["session_id"], proposal_id="proposal",
        expected_revision=session["session_revision"], fingerprint="f" * 64,
    )
    assert retried["generation_id"] != record["generation_id"]
    assert retried["state"] == "pending"


def _proposal_preview_scene_speed_runtime() -> object:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture", raw_text="{}", metadata={},
                output_data={"schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.", "proposal": {
                    "proposal_id": "preview", "base_session_revision": 1,
                    "operations": [{"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2}],
                }},
            )
    return EditingRuntime()


def _start_a_real_proposal_preview(client: TestClient, store: LocalProjectStore, project_id: str) -> tuple[str, str]:
    timeline = store.save_timeline_run(
        project_id=project_id, output_mode="review", source_session_revision=1,
        timeline_payload={"output": {"width": 1280, "height": 720, "duration_sec": 12}, "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project_id, timeline_id=timeline["timeline_id"],
        session_payload={"segments": [
            {"segment_id": "scene-1", "start_sec": 0, "end_sec": 4},
            {"segment_id": "scene-2", "start_sec": 4, "end_sec": 12},
        ], "history": []},
    )
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "둘째 장면을 빠르게"}).json()
    started = client.post(f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/preview")
    assert started.status_code == 202, started.text
    return session["session_id"], started.json()["generation_id"]


def test_yujin_editing_proposal_preview_status_polling_alone_recovers_a_running_claim_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker can die mid-render *after* the API process that started it has
    already restarted (new store, new process epoch). The only thing the
    creator does afterwards is poll the status GET -- never POST again. If
    the GET route never re-runs the restart fence, this ``running`` row
    (owned by a process that no longer exists) is stuck forever."""
    monkeypatch.setattr(LocalPipelineRunner, "run_proposal_preview", lambda self, **kwargs: None)
    projects_root = tmp_path / "projects"
    app = create_app(projects_root=projects_root, local_only_runtime_service_factory=lambda _: _proposal_preview_scene_speed_runtime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "proposal preview poll-only running recovery"}).json()["project_id"]
    _session_id, generation_id = _start_a_real_proposal_preview(client, store, project_id)
    assert store.get_proposal_preview(project_id=project_id, generation_id=generation_id)["state"] == "pending"
    assert store.claim_proposal_preview(
        project_id=project_id, generation_id=generation_id,
        owner_token="proposal-preview-worker:dead-process:worker",
    )

    # A brand-new API process attaches to the same project directory. It
    # never calls the preview POST route again -- only GET polling follows.
    restarted_app = create_app(projects_root=projects_root, local_only_runtime_service_factory=lambda _: _proposal_preview_scene_speed_runtime())
    restarted_client = TestClient(restarted_app)

    response = restarted_client.get(f"/api/projects/{project_id}/proposal-previews/{generation_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] not in {"pending", "running"}


def test_yujin_editing_proposal_preview_status_polling_alone_recovers_an_aged_orphan_pending_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the process dies after the ``pending`` DB row is created but before
    any worker thread claims it, the row never reaches ``running`` and the
    restart-epoch fence never sees it. GET polling alone must still retire
    it once it is old enough to be unambiguously orphaned."""
    monkeypatch.setattr(LocalPipelineRunner, "run_proposal_preview", lambda self, **kwargs: None)
    projects_root = tmp_path / "projects"
    app = create_app(projects_root=projects_root, local_only_runtime_service_factory=lambda _: _proposal_preview_scene_speed_runtime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "proposal preview poll-only pending recovery"}).json()["project_id"]
    _session_id, generation_id = _start_a_real_proposal_preview(client, store, project_id)
    assert store.get_proposal_preview(project_id=project_id, generation_id=generation_id)["state"] == "pending"
    store._execute(
        project_id,
        "UPDATE proposal_preview_renders SET created_at = ? WHERE generation_id = ?",
        ("2020-01-01T00:00:00+00:00", generation_id),
    )

    restarted_app = create_app(projects_root=projects_root, local_only_runtime_service_factory=lambda _: _proposal_preview_scene_speed_runtime())
    restarted_client = TestClient(restarted_app)

    response = restarted_client.get(f"/api/projects/{project_id}/proposal-previews/{generation_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] not in {"pending", "running"}


def test_yujin_editing_proposal_preview_reports_a_concurrent_session_conflict_as_creator_safe_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(provider_name="local", model_name="fixture", raw_text="{}", metadata={}, output_data={
                "schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.",
                "proposal": {"proposal_id": "race", "base_session_revision": 1, "operations": [{"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 2}]},
            })

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app, raise_server_exceptions=False)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "proposal preview revision race"}).json()["project_id"]
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []})
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "미리보기"}).json()

    original = LocalPipelineRunner.start_proposal_preview
    def race_revision(runner, **kwargs):
        store.update_editing_session(project_id=project_id, session_id=session["session_id"], session_payload=session, expected_revision=1)
        return original(runner, **kwargs)
    monkeypatch.setattr(LocalPipelineRunner, "start_proposal_preview", race_revision)

    response = client.post(f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/preview")

    assert response.status_code == 409
    assert response.json() == {"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."}


def test_proposal_preview_cleanup_keeps_only_its_retained_terminal_records_and_never_touches_exact_or_source_files(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("proposal preview cleanup")
    session = store.save_editing_session(project_id=project.project_id, timeline_id="timeline", session_payload={"segments": [], "history": []})
    source = store.project_root(project.project_id) / "inputs" / "raw_video" / "source.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"source")
    exact = store.project_root(project.project_id) / "derived" / "exact_previews" / "exact_preview_keep.mp4"
    exact.parent.mkdir(parents=True, exist_ok=True)
    exact.write_bytes(b"exact")
    records = []
    for proposal_id in ("old", "middle", "new"):
        record = store.begin_proposal_preview(project_id=project.project_id, session_id=session["session_id"], proposal_id=proposal_id, expected_revision=1, fingerprint=(proposal_id[0] * 64))
        assert store.claim_proposal_preview(project_id=project.project_id, generation_id=record["generation_id"], owner_token=f"owner-{proposal_id}")
        rendered = tmp_path / f"{proposal_id}.mp4"
        rendered.write_bytes(proposal_id.encode())
        assert store.finish_proposal_preview(project_id=project.project_id, generation_id=record["generation_id"], fingerprint=record["fingerprint"], artifact_path=rendered, owner_token=f"owner-{proposal_id}")
        assert store.mark_proposal_preview_stale(project_id=project.project_id, generation_id=record["generation_id"], reason="test")
        records.append(record)
    store._execute(project.project_id, "UPDATE proposal_preview_renders SET updated_at = ? WHERE generation_id = ?", ("2020-01-01T00:00:00+00:00", records[0]["generation_id"]))
    store._execute(project.project_id, "UPDATE proposal_preview_renders SET updated_at = ? WHERE generation_id = ?", ("2021-01-01T00:00:00+00:00", records[1]["generation_id"]))
    orphan = store.project_root(project.project_id) / "derived" / "proposal_previews" / "proposal_preview_orphan.mp4"
    orphan.write_bytes(b"orphan")
    os.utime(orphan, (0, 0))

    removed = store.cleanup_proposal_preview_artifacts(project_id=project.project_id, keep_last=1, orphan_older_than_seconds=0)

    assert removed == 3
    assert store.get_proposal_preview(project_id=project.project_id, generation_id=records[2]["generation_id"])["state"] == "obsolete"
    for record in records[:2]:
        with pytest.raises(KeyError):
            store.get_proposal_preview(project_id=project.project_id, generation_id=record["generation_id"])
        assert not (store.project_root(project.project_id) / "derived" / "proposal_previews" / f"{record['generation_id']}.mp4").exists()
    assert exact.read_bytes() == b"exact"
    assert source.read_bytes() == b"source"
    assert not orphan.exists()


def test_yujin_editing_proposal_preview_status_refuses_a_stale_source_session(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture", raw_text="{}", metadata={},
                output_data={"schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.", "proposal": {
                    "proposal_id": "stale-preview", "base_session_revision": 1,
                    "operations": [{"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 2}],
                }},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "stale proposal preview"}).json()["project_id"]
    timeline = store.save_timeline_run(project_id=project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"width": 1280, "height": 720, "duration_sec": 4}, "tracks": []})
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []})
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "첫 장면을 빠르게"}).json()
    record = LocalPipelineRunner(store).start_proposal_preview(project_id=project_id, session_id=session["session_id"], proposal_id=proposal["proposal_id"])
    assert store.claim_proposal_preview(project_id=project_id, generation_id=record["generation_id"], owner_token="test-worker")
    rendered = tmp_path / "proposal-preview.mp4"
    rendered.write_bytes(b"synthetic-preview")
    store.update_editing_session(project_id=project_id, session_id=session["session_id"], session_payload=session, expected_revision=1)
    assert not store.finish_proposal_preview(project_id=project_id, generation_id=record["generation_id"], fingerprint=record["fingerprint"], artifact_path=rendered, owner_token="test-worker", source_fence_result=True)
    assert not (store.project_root(project_id) / "derived" / "proposal_previews" / f"{record['generation_id']}.mp4").exists()

    stale = client.get(f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}")
    stale_content = client.get(f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}/content")

    assert stale.status_code == 409
    assert stale.json() == {"code": "editing_proposal_needs_refresh", "action": "새 편집안을 받아 보세요."}
    assert stale_content.status_code == 409
    assert stale_content.json() == stale.json()


def test_yujin_editing_proposal_preview_refuses_an_asset_changed_during_render(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(provider_name="local", model_name="fixture", raw_text="{}", metadata={}, output_data={
                "schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.",
                "proposal": {"proposal_id": "asset-stale", "base_session_revision": 1, "operations": [{"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 2}]},
            })

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "asset stale proposal preview"}).json()["project_id"]
    source = tmp_path / "source.mp4"; source.write_bytes(b"before-render")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    timeline = store.save_timeline_run(project_id=project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"width": 1280, "height": 720, "duration_sec": 4}, "tracks": [{"track_type": "broll", "clips": [{"clip_id": "b1", "asset_id": asset.asset_id, "asset_uri": asset.storage_uri, "start_sec": 0, "end_sec": 4}]}]})
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []})
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "첫 장면을 빠르게"}).json()

    class MutatingRenderer:
        def render_exact_preview_to_mp4(self, **kwargs):
            kwargs["output_path"].write_bytes(b"synthetic-mp4")
            store.resolve_storage_uri(project_id=project_id, storage_uri=asset.storage_uri).write_bytes(b"changed-during-render")

    pipeline = LocalPipelineRunner(store, final_renderer=MutatingRenderer())
    record = pipeline.start_proposal_preview(project_id=project_id, session_id=session["session_id"], proposal_id=proposal["proposal_id"])
    pipeline.run_proposal_preview(project_id=project_id, generation_id=record["generation_id"])

    assert store.get_proposal_preview(project_id=project_id, generation_id=record["generation_id"])["state"] == "obsolete"
    assert not (store.project_root(project_id) / "derived" / "proposal_previews" / f"{record['generation_id']}.mp4").exists()
    assert client.get(f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}").status_code == 409
    assert client.get(f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}/content").status_code == 409


def test_yujin_editing_proposal_preview_content_serves_synthetic_mp4_only_while_current(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(provider_name="local", model_name="fixture", raw_text="{}", metadata={}, output_data={
                "schema_version": "videobox.yujin-editing-response.v1", "reply_text": "편집안을 준비했어요.",
                "proposal": {"proposal_id": "success-preview", "base_session_revision": 1, "operations": [{"intent": "set_scene_speed", "segment_id": "scene-1", "rate": 2}]},
            })

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app); store = app.state.store
    project_id = client.post("/api/projects", json={"name": "success proposal preview"}).json()["project_id"]
    timeline = store.save_timeline_run(project_id=project_id, output_mode="review", source_session_revision=1, timeline_payload={"output": {"width": 1280, "height": 720, "duration_sec": 4}, "tracks": []})
    session = store.save_editing_session(project_id=project_id, timeline_id=timeline["timeline_id"], session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []})
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "첫 장면을 빠르게"}).json()

    class SyntheticRenderer:
        def render_exact_preview_to_mp4(self, **kwargs): kwargs["output_path"].write_bytes(b"synthetic-mp4")

    pipeline = LocalPipelineRunner(store, final_renderer=SyntheticRenderer())
    record = pipeline.start_proposal_preview(project_id=project_id, session_id=session["session_id"], proposal_id=proposal["proposal_id"])
    pipeline.run_proposal_preview(project_id=project_id, generation_id=record["generation_id"])

    content = client.get(f"/api/projects/{project_id}/proposal-previews/{record['generation_id']}/content")
    assert store.get_proposal_preview(project_id=project_id, generation_id=record["generation_id"])["state"] == "succeeded"
    assert content.status_code == 200 and content.headers["content-type"] == "video/mp4" and content.content == b"synthetic-mp4"


def test_yujin_editing_proposal_apply_uses_the_common_undo_and_redo_history(tmp_path: Path) -> None:
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture",
                output_data={
                    "schema_version": "videobox.yujin-editing-response.v1",
                    "reply_text": "편집안을 준비했어요.",
                    "proposal": {"proposal_id": "apply-history", "base_session_revision": 1, "operations": [
                        {"intent": "set_scene_speed", "segment_id": "scene-2", "rate": 2},
                        {"intent": "set_caption_text", "segment_id": "scene-2", "text": "다듬은 자막"},
                    ]},
                }, raw_text="{}", metadata={},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "editing apply history"}).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [
            {"segment_id": "scene-1", "caption_text": "첫 장면", "start_sec": 0, "end_sec": 4, "cut_action": "keep", "review_required": False},
            {"segment_id": "scene-2", "caption_text": "둘째 장면", "start_sec": 4, "end_sec": 12, "cut_action": "keep", "review_required": False},
        ], "history": []},
    )
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "둘째 장면을 빠르게 하고 자막을 고쳐줘"}).json()

    applied = client.post(
        f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/apply",
        json={"expected_revision": session["session_revision"]},
    )

    assert applied.status_code == 200, applied.text
    assert applied.json()["undo_count"] == 1
    assert applied.json()["segments"][1]["caption_text"] == "다듬은 자막"
    undone = client.post(f"{root}/undo", json={"expected_revision": applied.json()["session_revision"]})
    assert undone.status_code == 200, undone.text
    assert undone.json()["redo_count"] == 1
    redone = client.post(f"{root}/redo", json={"expected_revision": undone.json()["session_revision"]})
    assert redone.status_code == 200, redone.text
    later_manual_edit = client.patch(
        f"{root}/segments/scene-2/caption",
        json={"caption_text": "수동 자막", "expected_revision": redone.json()["session_revision"]},
    )
    assert later_manual_edit.status_code == 200, later_manual_edit.text
    assert later_manual_edit.json()["redo_count"] == 0


def test_yujin_editing_proposal_refuses_an_unapproved_media_asset(tmp_path: Path) -> None:
    class EditingRuntime:
        asset_id = "pending-bgm"

        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture",
                output_data={
                    "schema_version": "videobox.yujin-editing-response.v1",
                    "reply_text": "음악을 골랐어요.",
                    "proposal": {
                        "proposal_id": "unapproved-media",
                        "base_session_revision": 1,
                        "operations": [{
                            "intent": "apply_media", "segment_id": "scene-1",
                                "media_type": "bgm", "asset_id": self.asset_id,
                        }],
                    },
                },
                raw_text="{}", metadata={},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "unapproved editing asset"}).json()["project_id"]
    source = tmp_path / "pending.mp3"
    source.write_bytes(b"pending-media")
    pending_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BGM,
        source_path=source,
        metadata={"review_status": "pending"},
    )
    EditingRuntime.asset_id = pending_asset.asset_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/yujin-editing-proposals",
        json={"instruction": "이 장면에 음악을 넣어줘"},
    )

    assert response.status_code == 201, response.text
    assert response.json() == {"status": "rejected", "reply_text": "이 장면에 음악을 넣어줘", "proposal": None}


def test_yujin_editing_clarification_shows_what_yujin_actually_asked(tmp_path: Path) -> None:
    """Task 4 (2026-08-26 계획서)로 잡힌 결함 -- 모호한 요청에 유진이 실제로
    되물은 말(`reply_text`)이 있는데도, 이 문이 사용자가 방금 쓴 문장을
    그대로 돌려주고 있었다. 유진이 무엇을 더 물었는지 화면에서 한 번도
    보이지 않았다."""
    class EditingRuntime:
        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture",
                output_data={
                    "schema_version": "videobox.yujin-editing-response.v1",
                    "reply_text": "어느 장면을 더 짧게 할지 콕 집어 말씀해 주시겠어요?",
                    "proposal": None,
                },
                raw_text="{}", metadata={},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "ambiguous editing request"}).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/yujin-editing-proposals",
        json={"instruction": "이 장면을 더 짧게 해줘"},
    )

    assert response.status_code == 201, response.text
    assert response.json() == {
        "status": "clarification",
        "reply_text": "어느 장면을 더 짧게 할지 콕 집어 말씀해 주시겠어요?",
        "proposal": None,
    }


def test_yujin_editing_proposal_refuses_an_approved_asset_of_the_wrong_media_type(tmp_path: Path) -> None:
    class EditingRuntime:
        asset_id = "approved-but-wrong-kind"

        def generate_structured(self, **_kwargs):
            return StructuredLLMResponse(
                provider_name="local", model_name="fixture",
                output_data={
                    "schema_version": "videobox.yujin-editing-response.v1",
                    "reply_text": "음악을 골랐어요.",
                    "proposal": {"proposal_id": "wrong-media-kind", "base_session_revision": 1, "operations": [{
                        "intent": "apply_media", "segment_id": "scene-1", "media_type": "bgm", "asset_id": self.asset_id,
                    }]},
                }, raw_text="{}", metadata={},
            )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: EditingRuntime())
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "wrong editing asset type"}).json()["project_id"]
    source = tmp_path / "approved-broll.mp4"
    source.write_bytes(b"approved-broll")
    approved_broll = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={"review_status": "approved"},
    )
    EditingRuntime.asset_id = approved_broll.asset_id
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [{"segment_id": "scene-1", "start_sec": 0, "end_sec": 4}], "history": []},
    )

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/yujin-editing-proposals",
        json={"instruction": "이 장면에 음악을 넣어줘"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["proposal"] is None


def test_generalized_yujin_direct_apply_and_batch_remain_forbidden(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={"name": "generalized yujin"},
    ).json()["project_id"]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{"segment_id": "seg", "caption_text": "기존 자막"}],
            "history": [],
        },
    )
    candidate = DirectorCandidate(
        candidate_id="caption-command",
        visible_reference_code="P00-CAPTION-01",
        media_type="caption",
        asset_id="caption-command",
        library_asset_id=None,
        reason_chips=("자막",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={"text": "추천 자막"},
        expected_content_sha256=None,
        media_revision="caption-r1",
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "yujin_actionable_operation": True,
            "command_kind": "set_caption_text",
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = DirectorProposal(
        proposal_id="generalized-yujin",
        revision_code="P00",
        revision=0,
        base_session_revision=session["session_revision"],
        asset_index_revision=app.state.store.get_asset_index_revision(project_id),
        source_session_id=session["session_id"],
        target_segment_ids=("seg",),
        source_script_segment_ids=("seg",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=(candidate,),
    )
    app.state.store.save_director_proposal(project_id, proposal)
    before = deepcopy(
        app.state.store.get_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
        )
    )
    base = f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"

    responses = (
        client.post(
            f"{base}/apply",
            json={"candidate_ids": [candidate.candidate_id], "expected_revision": 1},
        ),
        client.post(
            f"{base}/batch-apply",
            json={"candidate_ids": [candidate.candidate_id], "expected_revision": 1},
        ),
    )

    assert [(item.status_code, item.json()) for item in responses] == [
        (422, {"detail": "yujin_direct_apply_forbidden"}),
        (422, {"detail": "yujin_direct_apply_forbidden"}),
    ]
    assert app.state.store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


def _save_generalized_yujin_proposal(
    *,
    store: LocalProjectStore,
    project_id: str,
    session_id: str,
    session_revision: int,
    proposal_id: str,
    candidates: tuple[DirectorCandidate, ...],
) -> DirectorProposal:
    proposal = DirectorProposal(
        proposal_id=proposal_id,
        revision_code="P00",
        revision=0,
        base_session_revision=session_revision,
        asset_index_revision=store.get_asset_index_revision(project_id),
        source_session_id=session_id,
        target_segment_ids=("seg",),
        source_script_segment_ids=("seg",),
        status="ready",
        diff={"proposal_mode": "yujin_actionable_v1"},
        expires_at=None,
        candidates=candidates,
    )
    store.save_director_proposal(project_id, proposal)
    return proposal


def _yujin_image_overlay_fixture(
    tmp_path: Path,
    *,
    candidate_text: str = "승인된 장면 이미지",
) -> tuple[TestClient, LocalProjectStore, str, dict, DirectorProposal, DirectorCandidate, Path]:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": "attested yujin image overlay"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "장면",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "cut_action": "keep",
                "review_required": False,
            }],
            "history": [],
        },
    )
    source = tmp_path / "attested-overlay.png"
    source.write_bytes(b"approved-image-bytes")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.IMAGE,
        source_path=source,
        metadata={"review_status": "approved"},
    )
    digest = sha256(source.read_bytes()).hexdigest()
    candidate = DirectorCandidate(
        candidate_id="attested-image-overlay",
        visible_reference_code="P00-OVERLAY-01",
        media_type="overlay",
        asset_id=asset.asset_id,
        library_asset_id=None,
        reason_chips=("이미지 오버레이",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "overlay_kind": "image",
            "asset_id": asset.asset_id,
            "text": candidate_text,
        },
        expected_content_sha256=digest,
        media_revision=asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "overlay",
            "yujin_actionable_operation": True,
            "command_kind": "apply_overlay",
            "source_media_kind": "image",
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = _save_generalized_yujin_proposal(
        store=store,
        project_id=project_id,
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        proposal_id="attested-image-proposal",
        candidates=(candidate,),
    )
    registered = store.get_asset(project_id=project_id, asset_id=asset.asset_id)
    registered_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=str(registered["storage_uri"]),
    )
    return client, store, project_id, session, proposal, candidate, registered_path


def test_yujin_image_overlay_attestation_applies_the_exact_persisted_candidate(
    tmp_path: Path,
) -> None:
    client, store, project_id, session, proposal, candidate, _ = (
        _yujin_image_overlay_fixture(tmp_path)
    )
    base = f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"
    assert client.post(f"{base}/preflight").status_code == 200

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json={
            "asset_id": candidate.asset_id,
            "text": candidate.controls["text"],
            "expected_revision": session["session_revision"],
            "proposal_id": proposal.proposal_id,
            "candidate_id": candidate.candidate_id,
        },
    )

    assert response.status_code == 200
    overlay = response.json()["segments"][0]["visual_overlays"][0]
    assert overlay["asset_id"] == candidate.asset_id
    assert overlay["text"] == candidate.controls["text"]
    assert overlay["expected_content_sha256"] == candidate.expected_content_sha256
    assert overlay["media_revision"] == candidate.media_revision
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    )["session_revision"] == session["session_revision"] + 1


def test_yujin_image_overlay_attestation_canonicalizes_candidate_text_whitespace(
    tmp_path: Path,
) -> None:
    client, _, project_id, session, proposal, candidate, _ = (
        _yujin_image_overlay_fixture(
            tmp_path,
            candidate_text="  승인된 장면 이미지  ",
        )
    )

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json={
            "asset_id": candidate.asset_id,
            "text": candidate.controls["text"],
            "expected_revision": session["session_revision"],
            "proposal_id": proposal.proposal_id,
            "candidate_id": candidate.candidate_id,
        },
    )

    assert response.status_code == 200
    overlay = response.json()["segments"][0]["visual_overlays"][0]
    assert overlay["text"] == "승인된 장면 이미지"


@pytest.mark.parametrize(
    "tamper",
    ["file", "type", "revision", "candidate", "asset", "control", "asset-index"],
)
def test_yujin_image_overlay_attestation_rejects_post_preflight_tampering_without_mutation(
    tmp_path: Path,
    tamper: str,
) -> None:
    client, store, project_id, session, proposal, candidate, registered_path = (
        _yujin_image_overlay_fixture(tmp_path)
    )
    base = f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"
    assert client.post(f"{base}/preflight").status_code == 200
    payload = {
        "asset_id": candidate.asset_id,
        "text": candidate.controls["text"],
        "expected_revision": session["session_revision"],
        "proposal_id": proposal.proposal_id,
        "candidate_id": candidate.candidate_id,
    }
    if tamper == "file":
        registered_path.write_bytes(b"changed-after-preflight")
    elif tamper == "type":
        store._execute(
            project_id,
            "UPDATE assets SET asset_type = ? WHERE project_id = ? AND asset_id = ?",
            (AssetType.BROLL_VIDEO.value, project_id, candidate.asset_id),
        )
    elif tamper == "revision":
        store._execute(
            project_id,
            "UPDATE assets SET created_at = ? WHERE project_id = ? AND asset_id = ?",
            ("2099-01-01T00:00:00+00:00", project_id, candidate.asset_id),
        )
    elif tamper == "candidate":
        payload["candidate_id"] = "forged-candidate"
    elif tamper == "asset":
        payload["asset_id"] = "forged-asset"
    elif tamper == "control":
        payload["text"] = "브라우저가 바꾼 설명"
    else:
        store.bump_asset_index_revision(project_id)
    before = deepcopy(
        store.get_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
        )
    )

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json=payload,
    )

    assert response.status_code == 400
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


@pytest.mark.parametrize("tamper", ["proposal", "asset", "file"])
def test_yujin_image_overlay_terminal_transaction_rechecks_after_initial_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    client, store, project_id, session, proposal, candidate, registered_path = (
        _yujin_image_overlay_fixture(tmp_path)
    )
    original_write = store._write_editing_session

    def race_after_initial_validation(**kwargs):
        if tamper == "proposal":
            store._execute(
                project_id,
                "UPDATE director_proposals SET status = ? WHERE project_id = ? AND proposal_id = ?",
                ("expired", project_id, proposal.proposal_id),
            )
        elif tamper == "asset":
            store._execute(
                project_id,
                "UPDATE assets SET asset_type = ?, created_at = ? "
                "WHERE project_id = ? AND asset_id = ?",
                (
                    AssetType.BROLL_VIDEO.value,
                    "2099-01-01T00:00:00+00:00",
                    project_id,
                    candidate.asset_id,
                ),
            )
        else:
            registered_path.write_bytes(b"terminal-race-bytes")
        return original_write(**kwargs)

    monkeypatch.setattr(store, "_write_editing_session", race_after_initial_validation)
    before = deepcopy(
        store.get_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
        )
    )

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json={
            "asset_id": candidate.asset_id,
            "text": candidate.controls["text"],
            "expected_revision": session["session_revision"],
            "proposal_id": proposal.proposal_id,
            "candidate_id": candidate.candidate_id,
        },
    )

    assert response.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


def test_yujin_image_overlay_terminal_transaction_rejects_stale_session_identity_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, project_id, session, proposal, candidate, registered_path = (
        _yujin_image_overlay_fixture(tmp_path)
    )
    original_write = store._write_editing_session

    def race_to_a_new_terminal_identity(**kwargs):
        replacement = b"new-terminal-image-identity"
        replacement_sha = sha256(replacement).hexdigest()
        replacement_revision = "2099-01-01T00:00:00+00:00"
        registered_path.write_bytes(replacement)
        store._execute(
            project_id,
            "UPDATE assets SET created_at = ? "
            "WHERE project_id = ? AND asset_id = ?",
            (replacement_revision, project_id, candidate.asset_id),
        )
        row = store._fetchone(
            project_id,
            "SELECT proposal_json FROM director_proposals "
            "WHERE project_id = ? AND proposal_id = ?",
            (project_id, proposal.proposal_id),
        )
        assert row is not None
        proposal_payload = json.loads(str(row["proposal_json"]))
        proposal_payload["candidates"][0]["expected_content_sha256"] = replacement_sha
        proposal_payload["candidates"][0]["media_revision"] = replacement_revision
        store._execute(
            project_id,
            "UPDATE director_proposals SET proposal_json = ? "
            "WHERE project_id = ? AND proposal_id = ?",
            (
                json.dumps(proposal_payload, ensure_ascii=True, sort_keys=True),
                project_id,
                proposal.proposal_id,
            ),
        )
        return original_write(**kwargs)

    monkeypatch.setattr(
        store,
        "_write_editing_session",
        race_to_a_new_terminal_identity,
    )
    before = deepcopy(
        store.get_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
        )
    )

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json={
            "asset_id": candidate.asset_id,
            "text": candidate.controls["text"],
            "expected_revision": session["session_revision"],
            "proposal_id": proposal.proposal_id,
            "candidate_id": candidate.candidate_id,
        },
    )

    assert response.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


@pytest.mark.parametrize(
    "identity",
    [
        {"proposal_id": "attested-image-proposal"},
        {"candidate_id": "attested-image-overlay"},
    ],
)
def test_image_overlay_attestation_identity_is_a_strict_pair(
    tmp_path: Path,
    identity: dict[str, str],
) -> None:
    client, store, project_id, session, _, candidate, _ = (
        _yujin_image_overlay_fixture(tmp_path)
    )
    before = deepcopy(
        store.get_editing_session(
            project_id=project_id,
            session_id=session["session_id"],
        )
    )

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/segments/seg/image-overlay",
        json={
            "asset_id": candidate.asset_id,
            "text": candidate.controls["text"],
            "expected_revision": session["session_revision"],
            **identity,
        },
    )

    assert response.status_code == 422
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


@pytest.mark.parametrize(
    ("kind", "command_kind", "media_type", "controls", "route_suffix"),
    [
        (
            "caption_text",
            "set_caption_text",
            "caption",
            {"text": "승인된 자막"},
            "caption",
        ),
        (
            "caption_style",
            "set_caption_style",
            "caption",
            {
                "scope": "current_caption",
                "style": {
                    "font_family": "Pretendard",
                    "font_size_px": 42,
                    "text_color": "#FFFFFFFF",
                    "outline_color": "#000000FF",
                    "outline_width_px": 2,
                    "background_color": "#00000000",
                    "position_x_percent": 50,
                    "position_y_percent": 88,
                    "horizontal_align": "center",
                    "safe_area_enabled": True,
                    "shadow_blur_px": 0,
                },
            },
            "caption-style",
        ),
        (
            "explanation",
            "apply_overlay",
            "overlay",
            {
                "overlay_kind": "explanation-card",
                "title": "핵심",
                "body": "승인된 설명",
                "text": "승인된 카드",
            },
            "explanation-card",
        ),
        (
            "table",
            "apply_overlay",
            "overlay",
            {
                "overlay_kind": "table",
                "columns": ["항목", "값"],
                "rows": [["속도", "빠름"]],
                "text": "승인된 표",
            },
            "table-overlay",
        ),
    ],
)
def test_non_image_yujin_terminal_attestation_rejects_substituted_controls(
    tmp_path: Path,
    kind: str,
    command_kind: str,
    media_type: str,
    controls: dict[str, object],
    route_suffix: str,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": f"attested {kind}"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "기존 자막",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "cut_action": "keep",
                "review_required": False,
            }],
            "history": [],
        },
    )
    candidate = DirectorCandidate(
        candidate_id=f"attested-{kind}",
        visible_reference_code=f"P00-{kind.upper()}-01",
        media_type=media_type,
        asset_id=f"attested-{kind}",
        library_asset_id=None,
        reason_chips=(kind,),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls=controls,
        expected_content_sha256=None,
        media_revision="control-r1",
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": media_type,
            "yujin_actionable_operation": True,
            "command_kind": command_kind,
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = _save_generalized_yujin_proposal(
        store=store,
        project_id=project_id,
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        proposal_id=f"attested-{kind}-proposal",
        candidates=(candidate,),
    )
    base = f"/api/projects/{project_id}"
    assert client.post(
        f"{base}/director/proposals/{proposal.proposal_id}/preflight",
    ).status_code == 200
    identity = {
        "proposal_id": proposal.proposal_id,
        "candidate_id": candidate.candidate_id,
    }
    if kind == "caption_text":
        exact = {
            "caption_text": controls["text"],
            "expected_revision": 1,
            **identity,
        }
        forged = {**exact, "caption_text": "바꿔치기 자막"}
        route = (
            f"{base}/editing-sessions/{session['session_id']}"
            "/segments/seg/caption"
        )
    elif kind == "caption_style":
        exact = {
            "scope": controls["scope"],
            "segment_ids": ["seg"],
            "style": controls["style"],
            "expected_revision": 1,
            **identity,
        }
        forged = {
            **exact,
            "style": {**controls["style"], "font_size_px": 64},
        }
        route = (
            f"{base}/editing-sessions/{session['session_id']}/caption-style"
        )
    elif kind == "explanation":
        exact = {
            "title": controls["title"],
            "body": controls["body"],
            "text": controls["text"],
            "expected_revision": 1,
            **identity,
        }
        forged = {**exact, "text": "바꿔치기 카드"}
        route = (
            f"{base}/editing-sessions/{session['session_id']}"
            f"/segments/seg/{route_suffix}"
        )
    else:
        exact = {
            "columns": controls["columns"],
            "rows": controls["rows"],
            "text": controls["text"],
            "expected_revision": 1,
            **identity,
        }
        forged = {**exact, "text": "바꿔치기 표"}
        route = (
            f"{base}/editing-sessions/{session['session_id']}"
            f"/segments/seg/{route_suffix}"
        )
    before = deepcopy(store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ))

    rejected = client.patch(route, json=forged)

    assert rejected.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
    accepted = client.patch(route, json=exact)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["session_revision"] == 2


@pytest.mark.parametrize(
    ("route_suffix", "payload"),
    [
        (
            "segments/seg/caption",
            {
                "caption_text": "manual caption",
                "expected_revision": 1,
                "proposal_id": "proposal-only",
            },
        ),
        (
            "caption-style",
            {
                "scope": "current_caption",
                "segment_ids": ["seg"],
                "style": {
                    "font_family": "Arial",
                    "font_size_px": 54,
                    "text_color": "#FFFFFFFF",
                    "outline_color": "#000000FF",
                    "outline_width_px": 3,
                    "background_color": "#00000000",
                    "position_x_percent": 50,
                    "position_y_percent": 88,
                    "horizontal_align": "center",
                    "safe_area_enabled": True,
                    "shadow_blur_px": 0,
                },
                "expected_revision": 1,
                "candidate_id": "candidate-only",
            },
        ),
        (
            "segments/seg/explanation-card",
            {
                "title": "title",
                "body": "body",
                "text": "card",
                "expected_revision": 1,
                "proposal_id": "proposal-only",
            },
        ),
        (
            "segments/seg/table-overlay",
            {
                "columns": ["column"],
                "rows": [["value"]],
                "text": "table",
                "expected_revision": 1,
                "candidate_id": "candidate-only",
            },
        ),
        (
            "segments/seg/tts-replacement",
            {
                "recommendation_id": "tts_candidate_manual",
                "asset_id": "asset-manual",
                "expected_revision": 1,
                "proposal_id": "proposal-only",
            },
        ),
    ],
)
def test_non_image_yujin_attestation_identity_must_be_a_complete_pair(
    tmp_path: Path,
    route_suffix: str,
    payload: dict[str, object],
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": "one-sided attestation"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "unchanged",
                "start_sec": 0.0,
                "end_sec": 1.0,
            }],
            "history": [],
        },
    )
    before = deepcopy(store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ))

    response = client.patch(
        (
            f"/api/projects/{project_id}/editing-sessions/"
            f"{session['session_id']}/{route_suffix}"
        ),
        json=payload,
    )

    assert response.status_code == 422
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before


def test_approved_tts_yujin_terminal_attestation_rejects_another_valid_candidate(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": "attested TTS"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{
                "segment_id": "seg",
                "caption_text": "장면",
                "start_sec": 0.0,
                "end_sec": 1.0,
                "cut_action": "keep",
                "review_required": False,
            }],
            "history": [],
        },
    )
    acceptance = SimpleNamespace(
        technical_status="accepted",
        operator_review_status="approved",
        target_duration_sec=1.0,
        actual_duration_sec=1.0,
        failure_code=None,
    )
    candidates = []
    assets = []
    for index in (1, 2):
        source = tmp_path / f"voice-{index}.wav"
        source.write_bytes(f"approved-voice-{index}".encode())
        asset = store.register_asset(
            project_id=project_id,
            asset_type=AssetType.GENERATED_TTS_AUDIO,
            source_path=source,
        )
        assets.append(asset)
        candidates.append(store.save_tts_candidate(
            project_id=project_id,
            segment_id="seg",
            asset_id=asset.asset_id,
            source_text=f"voice {index}",
            acceptance=acceptance,
        ))
    proposal_candidate = DirectorCandidate(
        candidate_id="attested-voice-operation",
        visible_reference_code="P00-VOICE-01",
        media_type="voice",
        asset_id=assets[0].asset_id,
        library_asset_id=None,
        reason_chips=("voice",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "candidate_id": candidates[0]["candidate_id"],
            "asset_id": assets[0].asset_id,
        },
        expected_content_sha256=sha256((tmp_path / "voice-1.wav").read_bytes()).hexdigest(),
        media_revision=assets[0].created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "voice",
            "yujin_actionable_operation": True,
                "command_kind": "apply_tts_candidate",
                "candidate_id": candidates[0]["candidate_id"],
                "source_media_kind": "generated_tts_audio",
                "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = _save_generalized_yujin_proposal(
        store=store,
        project_id=project_id,
        session_id=session["session_id"],
        session_revision=1,
        proposal_id="attested-voice-proposal",
        candidates=(proposal_candidate,),
    )
    base = f"/api/projects/{project_id}"
    assert client.post(
        f"{base}/director/proposals/{proposal.proposal_id}/preflight",
    ).status_code == 200
    route = (
        f"{base}/editing-sessions/{session['session_id']}"
        "/segments/seg/tts-replacement"
    )
    before = deepcopy(store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ))

    rejected = client.patch(route, json={
        "recommendation_id": candidates[1]["candidate_id"],
        "asset_id": assets[1].asset_id,
        "expected_revision": 1,
        "proposal_id": proposal.proposal_id,
        "candidate_id": proposal_candidate.candidate_id,
    })

    assert rejected.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
    exact_payload = {
        "recommendation_id": candidates[0]["candidate_id"],
        "asset_id": assets[0].asset_id,
        "expected_revision": 1,
        "proposal_id": proposal.proposal_id,
        "candidate_id": proposal_candidate.candidate_id,
    }
    stored_asset = store.get_asset(
        project_id=project_id,
        asset_id=assets[0].asset_id,
    )
    stored_path = store.resolve_storage_uri(
        project_id=project_id,
        storage_uri=stored_asset["storage_uri"],
    )
    original_bytes = stored_path.read_bytes()
    stored_path.write_bytes(b"tampered-after-preflight")

    stale = client.patch(route, json=exact_payload)

    assert stale.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
    stored_path.write_bytes(original_bytes)
    store._execute(
        project_id,
        "UPDATE assets SET asset_type = ? "
        "WHERE project_id = ? AND asset_id = ?",
        (
            AssetType.NARRATION_AUDIO.value,
            project_id,
            assets[0].asset_id,
        ),
    )

    wrong_kind = client.patch(route, json=exact_payload)

    assert wrong_kind.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
    store._execute(
        project_id,
        "UPDATE assets SET asset_type = ?, created_at = ? "
        "WHERE project_id = ? AND asset_id = ?",
        (
            AssetType.GENERATED_TTS_AUDIO.value,
            "2026-01-01T00:00:00+00:00",
            project_id,
            assets[0].asset_id,
        ),
    )

    wrong_revision = client.patch(route, json=exact_payload)

    assert wrong_revision.status_code != 200
    assert store.get_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
    ) == before
    store._execute(
        project_id,
        "UPDATE assets SET created_at = ? "
        "WHERE project_id = ? AND asset_id = ?",
        (
            proposal_candidate.media_revision,
            project_id,
            assets[0].asset_id,
        ),
    )
    accepted = client.patch(route, json=exact_payload)
    assert accepted.status_code == 200
    assert accepted.json()["session_revision"] == 2


def _complete_image_analysis(
    *,
    store: LocalProjectStore,
    project_id: str,
    asset_id: str,
    digest: str,
) -> None:
    analysis = store.create_media_analysis(
        project_id=project_id,
        asset_id=asset_id,
        idempotency_key=f"{digest}:generalized-yujin",
        cache_key=f"generalized-{asset_id}",
    )
    claim = store.claim_media_analysis(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
    )
    assert claim is not None
    assert store.complete_media_analysis(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"frames": [{"summary": "generalized candidate"}]},
    )


def test_generalized_yujin_preview_and_materialize_reject_forged_b3_asset_kind(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": "generalized forged b3"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{"segment_id": "seg", "caption_text": "장면"}],
            "history": [],
        },
    )
    source = tmp_path / "forged-broll.png"
    source.write_bytes(b"actual-image-bytes")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.IMAGE,
        source_path=source,
        metadata={"review_status": "approved"},
    )
    digest = sha256(source.read_bytes()).hexdigest()
    _complete_image_analysis(
        store=store,
        project_id=project_id,
        asset_id=asset.asset_id,
        digest=digest,
    )
    candidate = DirectorCandidate(
        candidate_id="generalized-forged-broll",
        visible_reference_code="P00-B-01",
        media_type="broll",
        asset_id=asset.asset_id,
        library_asset_id=None,
        reason_chips=("위조 B-roll",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={"fit": "cover"},
        expected_content_sha256=digest,
        media_revision=asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "broll",
            "yujin_actionable_media": True,
            "source_media_kind": "broll_video",
            "target_segment_id": "seg",
        },
    )
    proposal = _save_generalized_yujin_proposal(
        store=store,
        project_id=project_id,
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        proposal_id="generalized-forged-b3",
        candidates=(candidate,),
    )
    before_assets = store.list_assets(project_id=project_id)
    base = (
        f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"
        f"/candidates/{candidate.candidate_id}"
    )

    responses = (
        client.get(f"{base}/preview"),
        client.post(f"{base}/materialize"),
    )

    assert [(item.status_code, item.json()) for item in responses] == [
        (422, {"detail": "candidate_unavailable"}),
        (422, {"detail": "candidate_unavailable"}),
    ]
    assert store.list_assets(project_id=project_id) == before_assets


def test_generalized_mixed_yujin_materializes_only_valid_b3_media(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects",
        json={"name": "generalized mixed candidates"},
    ).json()["project_id"]
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{"segment_id": "seg", "caption_text": "장면"}],
            "history": [],
        },
    )
    bgm_source = tmp_path / "mixed-bgm.mp3"
    bgm_source.write_bytes(b"valid-bgm-bytes")
    bgm_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BGM,
        source_path=bgm_source,
        metadata={
            "canonical_metadata_indexed": True,
            "mood": "calm",
            "energy": "low",
            "genre": "ambient",
            "recommended_use": "bed",
        },
    )
    image_source = tmp_path / "mixed-overlay.png"
    image_source.write_bytes(b"overlay-image-bytes")
    image_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.IMAGE,
        source_path=image_source,
        metadata={"review_status": "approved"},
    )
    image_digest = sha256(image_source.read_bytes()).hexdigest()
    _complete_image_analysis(
        store=store,
        project_id=project_id,
        asset_id=image_asset.asset_id,
        digest=image_digest,
    )
    bgm = DirectorCandidate(
        candidate_id="generalized-valid-bgm",
        visible_reference_code="P00-BGM-01",
        media_type="bgm",
        asset_id=bgm_asset.asset_id,
        library_asset_id=None,
        reason_chips=("배경 음악",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={"gain_db": -10.0, "ducking_db": -6.0},
        expected_content_sha256=sha256(bgm_source.read_bytes()).hexdigest(),
        media_revision=bgm_asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "bgm",
            "yujin_actionable_media": True,
            "source_media_kind": "bgm",
            "target_segment_id": "seg",
        },
    )
    overlay = DirectorCandidate(
        candidate_id="generalized-image-overlay",
        visible_reference_code="P00-OVERLAY-01",
        media_type="overlay",
        asset_id=image_asset.asset_id,
        library_asset_id=None,
        reason_chips=("이미지 오버레이",),
        scores={},
        availability="actionable",
        review_status="approved",
        preview_uri=None,
        controls={
            "overlay_kind": "image",
            "asset_id": image_asset.asset_id,
            "text": "장면 이미지",
        },
        expected_content_sha256=image_digest,
        media_revision=image_asset.created_at.isoformat(),
        canonical_metadata={
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "overlay",
            "yujin_actionable_operation": True,
            "command_kind": "apply_overlay",
            "source_media_kind": "image",
            "target_segment_id": "seg",
            "requires_materialization": False,
        },
    )
    proposal = _save_generalized_yujin_proposal(
        store=store,
        project_id=project_id,
        session_id=session["session_id"],
        session_revision=session["session_revision"],
        proposal_id="generalized-mixed",
        candidates=(bgm, overlay),
    )
    base = f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"
    before_assets = store.list_assets(project_id=project_id)

    blocked = (
        client.get(f"{base}/candidates/{overlay.candidate_id}/preview"),
        client.post(f"{base}/candidates/{overlay.candidate_id}/materialize"),
    )
    materialized = client.post(
        f"{base}/candidates/{bgm.candidate_id}/materialize"
    )

    assert [(item.status_code, item.json()) for item in blocked] == [
        (422, {"detail": "candidate_unavailable"}),
        (422, {"detail": "candidate_unavailable"}),
    ]
    assert materialized.status_code == 201
    assert materialized.json()["content_sha256"] == bgm.expected_content_sha256
    after_assets = store.list_assets(project_id=project_id)
    assert len(after_assets) == len(before_assets) + 1
    assert after_assets[-1]["asset_type"] == "bgm"


def test_director_reload_get_is_behavioral_read_only_and_never_calls_a_provider(tmp_path: Path) -> None:
    class ForbiddenRuntime:
        calls = 0
        def generate_structured(self, **kwargs):
            type(self).calls += 1
            raise AssertionError("reload must not call a provider")
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: ForbiddenRuntime())
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "reload"}).json()["project_id"]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{
                "segment_id": "segment-1",
                "start_sec": 0,
                "end_sec": 1,
                "broll_override": {"asset_id": "asset-1"},
            }],
            "history": [],
        },
    )
    before = deepcopy(app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]))

    response = client.get(f"/api/projects/{project_id}/director/sessions/{session['session_id']}/reload")

    assert response.status_code == 200
    assert response.json()["conversation"] is None and response.json()["proposal"] is None
    assert response.json()["references"] == [{
        "reference_code": "B-01",
        "immutable_id": {"segment_id": "segment-1", "track_type": "broll"},
        "source": "timeline",
    }]
    assert app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"]) == before
    assert ForbiddenRuntime.calls == 0


def test_director_normal_message_uses_local_only_structured_runtime_contract(tmp_path: Path) -> None:
    """Free-form chat now routes through YujinLocalConversationService (Task 13/14
    wiring): task_type is YUJIN_CONVERSATION with the persona-wrapped prompt and a
    {"reply": ...} response schema, not the generic OPERATOR_COPY contract."""
    class StrictLocalRuntime:
        external_calls = 0
        calls: list[dict] = []

        def generate_structured(self, *, project_id, task_type, prompt, response_schema, now=None):
            assert project_id == self.project_id
            assert task_type.value == "yujin_conversation"
            assert prompt.endswith("창작자: 로컬 응답을 생성해줘")
            assert response_schema == {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"]}
            assert now is None
            type(self).calls.append({"project_id": project_id, "task_type": task_type, "prompt": prompt})
            return StructuredLLMResponse(provider_name="strict-local", model_name="fixture", output_data={"reply": "로컬 응답입니다."}, raw_text='{"reply":"로컬 응답입니다."}', metadata={"provider_trace": {"routing_mode": "local_only"}})

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


def test_director_route_never_invokes_local_failure_or_external_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Director composition is local-store only and never invokes HTTP."""
    class LocalFailureRuntime:
        routing_mode = "local_only"

        def __init__(self) -> None:
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            raise AssertionError("Director proposal must not request runtime generation")

    runtime = LocalFailureRuntime()
    external_calls = {"http": 0}

    def forbidden_http(*args, **kwargs):
        external_calls["http"] += 1
        raise AssertionError("External HTTP is forbidden for Director")

    monkeypatch.setattr("videobox_api.main.urlopen", forbidden_http)
    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=lambda _: runtime)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "no-runtime"}).json()["project_id"]
    session = app.state.store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [{"segment_id": "seg", "caption_text": "local"}], "history": []})

    response = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]})

    assert response.status_code == 409
    assert response.json()["code"] == "director_analysis_blocked"
    assert runtime.calls == 0
    assert external_calls == {"http": 0}


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


def test_candidate_only_proposal_rejects_every_execution_surface_before_mutation(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "candidate-only"}).json()["project_id"]
    source = tmp_path / "candidate.mp4"
    source.write_bytes(b"candidate-only-source")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={"semantic_score": 0.9, "review_status": "approved"},
    )
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(
        project_id=project_id,
        asset_id=asset.asset_id,
        idempotency_key=f"{digest}:candidate-only",
        cache_key="candidate-only",
    )
    claim = store.claim_media_analysis(
        project_id=project_id, analysis_id=analysis["analysis_id"]
    )
    assert claim is not None
    assert store.complete_media_analysis(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"frames": [{"summary": "candidate"}]},
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [{"segment_id": "seg", "caption_text": "candidate"}],
            "history": [],
        },
    )
    proposal = client.post(
        f"/api/projects/{project_id}/director/proposals",
        json={"session_id": session["session_id"]},
    ).json()
    candidate_id = proposal["candidates"][0]["candidate_id"]
    connection = store._connection(project_id)
    connection.execute(
        "UPDATE director_proposals SET status = 'candidate_only' "
        "WHERE project_id = ? AND proposal_id = ?",
        (project_id, proposal["proposal_id"]),
    )
    connection.commit()
    before_session = store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    )
    before_assets = store.list_assets(project_id=project_id)
    base = f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}"
    responses = (
        client.post(f"{base}/preflight"),
        client.get(f"{base}/candidates/{candidate_id}/preview"),
        client.post(f"{base}/candidates/{candidate_id}/materialize"),
        client.post(
            f"{base}/apply",
            json={"candidate_ids": [candidate_id], "expected_revision": 1},
        ),
        client.post(
            f"{base}/batch-apply",
            json={"candidate_ids": [candidate_id], "expected_revision": 1},
        ),
    )

    assert [(response.status_code, response.json()) for response in responses] == [
        (409, {"detail": "proposal_not_ready"})
    ] * 5
    assert store.get_editing_session(
        project_id=project_id, session_id=session["session_id"]
    ) == before_session
    assert store.list_assets(project_id=project_id) == before_assets


def test_ready_yujin_proposal_rejects_deferred_candidate_when_ui_is_bypassed(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post(
        "/api/projects", json={"name": "deferred-yujin"}
    ).json()["project_id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"deferred-yujin-source")
    asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.BROLL_VIDEO,
        source_path=source,
        metadata={"semantic_score": 0.9, "review_status": "approved"},
    )
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(
        project_id=project_id,
        asset_id=asset.asset_id,
        idempotency_key=f"{digest}:deferred",
        cache_key="deferred",
    )
    claim = store.claim_media_analysis(
        project_id=project_id, analysis_id=analysis["analysis_id"]
    )
    assert claim is not None
    assert store.complete_media_analysis(
        project_id=project_id,
        analysis_id=analysis["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"frames": [{"summary": "candidate"}]},
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={
            "segments": [
                {
                    "segment_id": "seg",
                    "caption_text": "candidate",
                    "start_sec": 0,
                    "end_sec": 1,
                }
            ],
            "history": [],
        },
    )
    legacy = client.post(
        f"/api/projects/{project_id}/director/proposals",
        json={"session_id": session["session_id"]},
    ).json()
    stored = store.get_director_proposal(project_id, legacy["proposal_id"])
    actionable = replace(
        stored.candidates[0],
        availability="actionable",
        review_status="approved",
        controls={"fit": "fit"},
        expected_content_sha256=digest,
        canonical_metadata={
            **dict(stored.candidates[0].canonical_metadata),
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "broll",
            "yujin_actionable_media": True,
            "source_media_kind": "broll_video",
            "target_segment_id": "seg",
        },
    )
    deferred = replace(
        stored.candidates[0],
        candidate_id="yujin-deferred-image",
        asset_id="missing-deferred-image",
        availability="candidate_only",
        expected_content_sha256=None,
        media_revision="deferred-r1",
        canonical_metadata={
            **dict(stored.candidates[0].canonical_metadata),
            "schema_version": "videobox.yujin-response.v1",
            "proposal_kind": "broll",
            "yujin_actionable_media": False,
            "source_media_kind": "image",
            "target_segment_id": "seg",
        },
    )
    proposal = replace(
        stored,
        proposal_id="yujin-deferred-bypass",
        status="ready",
        diff={
            **dict(stored.diff),
            "proposal_mode": "yujin_actionable_media_v1",
        },
        candidates=(actionable, deferred),
    )
    store.save_director_proposal(project_id, proposal)
    base = (
        f"/api/projects/{project_id}/director/proposals/{proposal.proposal_id}"
    )
    before = deepcopy(
        store.get_editing_session(
            project_id=project_id, session_id=session["session_id"]
        )
    )
    before_assets = store.list_assets(project_id=project_id)
    preflight = client.post(f"{base}/preflight")
    forbidden_direct_mutations = (
        client.post(
            f"{base}/apply",
            json={
                "candidate_ids": [actionable.candidate_id],
                "expected_revision": session["session_revision"],
            },
        ),
        client.post(
            f"{base}/batch-apply",
            json={
                "candidate_ids": [actionable.candidate_id],
                "expected_revision": session["session_revision"],
            },
        ),
    )

    responses = (
        client.get(f"{base}/candidates/{deferred.candidate_id}/preview"),
        client.post(f"{base}/candidates/{deferred.candidate_id}/materialize"),
        client.post(
            f"{base}/apply",
            json={
                "candidate_ids": [deferred.candidate_id],
                "expected_revision": session["session_revision"],
            },
        ),
        client.post(
            f"{base}/batch-apply",
            json={
                "candidate_ids": [deferred.candidate_id],
                "expected_revision": session["session_revision"],
            },
        ),
    )

    assert preflight.status_code == 200
    assert preflight.json()["status"] == "ready"
    assert [
        (response.status_code, response.json())
        for response in forbidden_direct_mutations
    ] == [
        (422, {"detail": "yujin_direct_apply_forbidden"})
    ] * 2
    assert (
        store.get_editing_session(
            project_id=project_id, session_id=session["session_id"]
        )
        == before
    )
    assert store.list_assets(project_id=project_id) == before_assets
    actionable_preview = client.get(
        f"{base}/candidates/{actionable.candidate_id}/preview"
    )
    assert actionable_preview.status_code == 200
    assert actionable_preview.content == b"deferred-yujin-source"
    assert [(response.status_code, response.json()) for response in responses] == [
        (422, {"detail": "candidate_unavailable"}),
        (422, {"detail": "candidate_unavailable"}),
        (422, {"detail": "yujin_direct_apply_forbidden"}),
        (422, {"detail": "yujin_direct_apply_forbidden"}),
    ]
    claimed_raw_actual_broll = replace(
        actionable,
        candidate_id="yujin-claimed-raw-actual-broll",
        canonical_metadata={
            **dict(actionable.canonical_metadata),
            "source_media_kind": "raw_video",
        },
    )
    claimed_raw_proposal = replace(
        proposal,
        proposal_id="yujin-claimed-raw-actual-broll",
        candidates=(claimed_raw_actual_broll,),
    )
    store.save_director_proposal(project_id, claimed_raw_proposal)
    claimed_raw_base = (
        f"/api/projects/{project_id}/director/proposals/"
        f"{claimed_raw_proposal.proposal_id}/candidates/"
        f"{claimed_raw_actual_broll.candidate_id}"
    )
    assert [
        client.get(f"{claimed_raw_base}/preview").status_code,
        client.post(f"{claimed_raw_base}/materialize").status_code,
    ] == [422, 422]
    materialized = client.post(
        f"{base}/candidates/{actionable.candidate_id}/materialize"
    )
    assert materialized.status_code == 201
    assert materialized.json()["asset_id"]
    persisted = store.get_director_proposal(project_id, proposal.proposal_id)
    assert persisted.candidates[1].candidate_id == deferred.candidate_id
    assert persisted.candidates[1].availability == "candidate_only"

    raw_source = tmp_path / "valid-raw-video.mp4"
    raw_source.write_bytes(b"valid-raw-video")
    raw_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.RAW_VIDEO,
        source_path=raw_source,
        metadata={"semantic_score": 0.9, "review_status": "approved"},
    )
    raw_digest = sha256(raw_source.read_bytes()).hexdigest()
    raw_analysis = store.create_media_analysis(
        project_id=project_id,
        asset_id=raw_asset.asset_id,
        idempotency_key=f"{raw_digest}:raw",
        cache_key="raw",
    )
    raw_claim = store.claim_media_analysis(
        project_id=project_id,
        analysis_id=raw_analysis["analysis_id"],
    )
    assert raw_claim is not None
    assert store.complete_media_analysis(
        project_id=project_id,
        analysis_id=raw_analysis["analysis_id"],
        expected_attempt=raw_claim["attempt"],
        result={"frames": [{"summary": "raw"}]},
    )
    raw_stored = store.get_asset(
        project_id=project_id,
        asset_id=raw_asset.asset_id,
    )
    claimed_broll_actual_raw = replace(
        actionable,
        candidate_id="yujin-claimed-broll-actual-raw",
        asset_id=raw_asset.asset_id,
        expected_content_sha256=raw_digest,
        media_revision=str(raw_stored["created_at"]),
    )
    claimed_broll_proposal = replace(
        proposal,
        proposal_id="yujin-claimed-broll-actual-raw",
        asset_index_revision=store.get_asset_index_revision(project_id),
        candidates=(claimed_broll_actual_raw,),
    )
    store.save_director_proposal(project_id, claimed_broll_proposal)
    claimed_broll_base = (
        f"/api/projects/{project_id}/director/proposals/"
        f"{claimed_broll_proposal.proposal_id}/candidates/"
        f"{claimed_broll_actual_raw.candidate_id}"
    )
    assert [
        client.get(f"{claimed_broll_base}/preview").status_code,
        client.post(f"{claimed_broll_base}/materialize").status_code,
    ] == [422, 422]
    valid_raw = replace(
        claimed_broll_actual_raw,
        candidate_id="yujin-valid-raw",
        canonical_metadata={
            **dict(claimed_broll_actual_raw.canonical_metadata),
            "source_media_kind": "raw_video",
        },
    )
    valid_raw_proposal = replace(
        claimed_broll_proposal,
        proposal_id="yujin-valid-raw",
        candidates=(valid_raw,),
    )
    store.save_director_proposal(project_id, valid_raw_proposal)
    valid_raw_base = (
        f"/api/projects/{project_id}/director/proposals/"
        f"{valid_raw_proposal.proposal_id}/candidates/{valid_raw.candidate_id}"
    )
    valid_raw_responses = (
        client.get(f"{valid_raw_base}/preview"),
        client.post(f"{valid_raw_base}/materialize"),
    )
    assert [response.status_code for response in valid_raw_responses] == [200, 201]
    wrong_source = replace(
        actionable,
        candidate_id="yujin-wrong-source",
        availability="actionable",
        review_status="approved",
        canonical_metadata={
            **dict(actionable.canonical_metadata),
            "yujin_actionable_media": True,
            "source_media_kind": "bgm",
        },
    )
    wrong_source_proposal = replace(
        proposal,
        proposal_id="yujin-wrong-source-bypass",
        candidates=(wrong_source,),
        asset_index_revision=store.get_asset_index_revision(project_id),
    )
    store.save_director_proposal(project_id, wrong_source_proposal)
    wrong_source_response = client.post(
        f"/api/projects/{project_id}/director/proposals/"
        f"{wrong_source_proposal.proposal_id}/candidates/"
        f"{wrong_source.candidate_id}/materialize"
    )
    assert wrong_source_response.status_code == 422
    assert wrong_source_response.json() == {"detail": "candidate_unavailable"}

    forged_source = tmp_path / "forged-image.png"
    forged_source.write_bytes(b"forged-image-as-broll")
    forged_asset = store.register_asset(
        project_id=project_id,
        asset_type=AssetType.IMAGE,
        source_path=forged_source,
        metadata={"semantic_score": 0.9, "review_status": "approved"},
    )
    forged_digest = sha256(forged_source.read_bytes()).hexdigest()
    forged_analysis = store.create_media_analysis(
        project_id=project_id,
        asset_id=forged_asset.asset_id,
        idempotency_key=f"{forged_digest}:forged",
        cache_key="forged",
    )
    forged_claim = store.claim_media_analysis(
        project_id=project_id,
        analysis_id=forged_analysis["analysis_id"],
    )
    assert forged_claim is not None
    assert store.complete_media_analysis(
        project_id=project_id,
        analysis_id=forged_analysis["analysis_id"],
        expected_attempt=forged_claim["attempt"],
        result={"frames": [{"summary": "forged"}]},
    )
    forged = replace(
        actionable,
        candidate_id="yujin-forged-image",
        asset_id=forged_asset.asset_id,
        expected_content_sha256=forged_digest,
        media_revision=forged_asset.created_at.isoformat(),
    )
    forged_proposal = replace(
        proposal,
        proposal_id="yujin-forged-image-bypass",
        candidates=(forged,),
        asset_index_revision=store.get_asset_index_revision(project_id),
    )
    store.save_director_proposal(project_id, forged_proposal)
    forged_base = (
        f"/api/projects/{project_id}/director/proposals/"
        f"{forged_proposal.proposal_id}/candidates/{forged.candidate_id}"
    )
    forged_responses = (
        client.get(f"{forged_base}/preview"),
        client.post(f"{forged_base}/materialize"),
    )
    assert [response.status_code for response in forged_responses] == [422, 422]
    assert (
        store.get_editing_session(
            project_id=project_id, session_id=session["session_id"]
        )
        == before
    )


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


def test_one_undo_takes_back_every_scene_a_batch_apply_filled(tmp_path: Path) -> None:
    """화면이 여러 후보를 한 번에 고르게 되면, 되돌리기도 한 번이어야 한다.

    빈 구간 열두 개를 채운 뒤 실행 취소를 열두 번 눌러야 한다면 그건 고친 게 아니다.
    `batch-apply`는 한 번의 CAS 쓰기라 기록도 하나이며, 그 성질을 여기서 못박는다.
    """
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "batch undo"}).json()["project_id"]
    source = tmp_path / "undo.mp4"; source.write_bytes(b"batch-undo-broll")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(source.read_bytes()).hexdigest()
    analysis = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="undo")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=analysis["analysis_id"], expected_attempt=claim["attempt"], result={"frames": [{"summary": "undo"}]})
    session = store.save_editing_session(project_id=project_id, timeline_id="timeline", session_payload={"segments": [
        {"segment_id": "seg-1", "caption_text": "first", "start_sec": 0.0, "end_sec": 2.0, "cut_action": "keep", "review_required": False},
        {"segment_id": "seg-2", "caption_text": "second", "start_sec": 2.0, "end_sec": 4.0, "cut_action": "keep", "review_required": False},
    ], "history": []})
    proposal = client.post(f"/api/projects/{project_id}/director/proposals", json={"session_id": session["session_id"]}).json()
    selected = [item["candidate_id"] for item in proposal["candidates"] if item["candidate_id"].split(":")[1] in {"seg-1", "seg-2"}]
    assert len(selected) == 2

    applied = client.post(f"/api/projects/{project_id}/director/proposals/{proposal['proposal_id']}/batch-apply", json={
        "candidate_ids": selected, "expected_revision": session["session_revision"],
    }).json()
    assert {segment["segment_id"] for segment in applied["segments"] if segment.get("broll_override")} == {"seg-1", "seg-2"}
    assert applied["undo_count"] == 1

    undone = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}/undo",
        json={"expected_revision": applied["session_revision"]},
    )

    assert undone.status_code == 200, undone.text
    assert [segment.get("broll_override") for segment in undone.json()["segments"]] == [None, None]
    assert undone.json()["undo_count"] == 0


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


def test_narration_recording_syncs_the_captions_without_hand_typed_timings(tmp_path: Path) -> None:
    """The owner records narration; the captions should follow the voice.

    The aligner and speech recognition both existed, but the only way to move a
    script draft off provisional timings was to hand the server a list of
    start/end numbers -- which no screen ever did, so a recording could not
    tighten a single caption.
    """
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    store = app.state.store
    project_id = client.post("/api/projects", json={"name": "voice sync"}).json()["project_id"]

    script = tmp_path / "script.txt"
    script.write_text("\uccab \ubb38\uc7a5\uc785\ub2c8\ub2e4\n\n\ub458\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4\n", encoding="utf-8")
    script_asset = store.register_asset(
        project_id=project_id, asset_type=AssetType.SCRIPT_DOCUMENT, source_path=script
    )
    narration = tmp_path / "narration.wav"
    narration.write_bytes(b"narration bytes")
    narration_asset = store.register_asset(
        project_id=project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration
    )
    session = client.post(
        f"/api/projects/{project_id}/editing-sessions/from-script",
        json={"script_asset_id": script_asset.asset_id},
    ).json()
    assert session["timing_source"] == "provisional_script", session

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        "/narration-alignment/from-recording",
        json={
            "narration_asset_id": narration_asset.asset_id,
            "expected_revision": session["session_revision"],
        },
    )

    assert response.status_code == 200, response.text
    synced = response.json()
    assert synced["timing_source"] == "narration_alignment", synced
    assert synced["narration_alignment_required"] is False


def test_captions_follow_the_recorded_voice_not_a_flat_five_seconds(tmp_path: Path) -> None:
    """Every script sentence was given exactly five seconds, recording or not.

    The owner picks "준비한 나레이션으로 초안 준비" precisely so the captions
    land where the words land. Ignoring the recording made every draft need
    hand-nudging before it was watchable.
    """
    app = create_app(projects_root=tmp_path / "projects")
    store = app.state.store
    project = store.bootstrap_project("caption timing")
    project_id = project.project_id

    narration = tmp_path / "narration.wav"
    narration.write_bytes(b"spoken words")
    narration_asset = store.register_asset(
        project_id=project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration
    )
    store.save_transcript(
        project_id=project_id,
        source_asset_id=narration_asset.asset_id,
        transcript_text="\uccab \ubb38\uc7a5. \ub458\uc9f8 \ubb38\uc7a5.",
        provider_name="test",
        segments=[
            {"start_sec": 0.0, "end_sec": 2.4, "text": "\uccab \ubb38\uc7a5"},
            {"start_sec": 2.4, "end_sec": 9.1, "text": "\ub458\uc9f8 \ubb38\uc7a5"},
        ],
    )

    timed = store.script_segments_for_narration(
        project_id=project_id,
        narration_asset_id=narration_asset.asset_id,
        sentences=["\uccab \ubb38\uc7a5", "\ub458\uc9f8 \ubb38\uc7a5"],
    )

    assert [(item["start_sec"], item["end_sec"]) for item in timed] == [(0.0, 2.4), (2.4, 9.1)]


def test_without_a_recording_the_even_spacing_still_applies(tmp_path: Path) -> None:
    """A silent draft has nothing to follow, so the provisional grid stands."""
    app = create_app(projects_root=tmp_path / "projects")
    store = app.state.store
    project_id = store.bootstrap_project("no recording").project_id

    timed = store.script_segments_for_narration(
        project_id=project_id, narration_asset_id=None, sentences=["\ud558\ub098", "\ub458"]
    )

    assert [(item["start_sec"], item["end_sec"]) for item in timed] == [(0, 5), (5, 10)]


def test_screen_chat_route_carries_owner_approved_memory_into_the_prompt(tmp_path: Path) -> None:
    """The editor screen posts here, not to the Hermes run route.

    Memory retrieval used to be wired only into `hermes-runs`, which no screen
    calls, so an owner who approved a memory never saw Yujin use it.
    """
    class CapturingRuntime:
        routing_mode = "local_only"
        prompts: list[str] = []

        def generate_structured(self, *, project_id, task_type, prompt, response_schema, now=None):
            del project_id, task_type, response_schema, now
            type(self).prompts.append(prompt)
            return StructuredLLMResponse(
                provider_name="strict-local",
                model_name="fixture",
                output_data={"reply": "확인했어요."},
                raw_text='{"reply":"확인했어요."}',
                metadata={"provider_trace": {"routing_mode": "local_only"}},
            )

    class StubMemoryService:
        async def retrieve_approved_memories(self, *, project_id, conversation_id, query):
            del project_id, conversation_id, query
            return (
                UserApprovedPreference(
                    kind="user_approved_preference",
                    category="caption",
                    text="자막은 두 줄 이내를 선호합니다.",
                ),
            )

    app = create_app(
        projects_root=tmp_path / "projects",
        local_only_runtime_service_factory=lambda _: CapturingRuntime(),
    )
    app.state.yujin_memory_service = StubMemoryService()
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "memory on screen"}).json()["project_id"]
    session = app.state.store.save_editing_session(
        project_id=project_id, timeline_id="timeline", session_payload={"segments": [], "history": []}
    )
    conversation = client.post(
        f"/api/projects/{project_id}/director/conversations",
        json={"session_id": session["session_id"]},
    ).json()

    response = client.post(
        f"/api/projects/{project_id}/director/conversations/{conversation['conversation_id']}/messages",
        json={
            "session_id": session["session_id"],
            "client_message_id": "message-1",
            "text": "내 자막 취향이 어떻게 되지?",
        },
    )

    assert response.status_code == 200, response.text
    assert CapturingRuntime.prompts, "the local runtime was never called"
    assert "자막은 두 줄 이내를 선호합니다." in CapturingRuntime.prompts[0]
