from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest

import videobox_core_engine.project_asset_materializer as materializer_module

from videobox_core_engine.project_asset_materializer import ProjectAssetMaterializer
from videobox_core_engine.director_proposal_service import DirectorProposalService
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore
from videobox_api.routers.director_proposals import _remove_preview_snapshot
from dataclasses import replace
from copy import deepcopy


def test_candidate_materializer_stages_then_creates_one_reusable_project_asset(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(b"clip").hexdigest()
    run = store.create_media_analysis(project_id=project.project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="x")
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"], expected_attempt=claim["attempt"], result={"frame": "ok"})
    session = store.save_editing_session(project_id=project.project_id, timeline_id="t", session_payload={"segments": [{"segment_id": "s", "caption_text": "clip"}], "history": []})
    before = deepcopy(store.get_editing_session(project_id=project.project_id, session_id=session["session_id"]))
    candidate = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"]).candidates[0]
    materializer = ProjectAssetMaterializer(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: materializer.materialize(project_id=project.project_id, candidate=candidate), range(2)))
    project_path = store.resolve_storage_uri(project_id=project.project_id, storage_uri=first["storage_uri"])
    assert first["asset_id"] == second["asset_id"] != asset.asset_id
    assert sha256(project_path.read_bytes()).hexdigest() == digest
    assert not (store.project_root(project.project_id) / ".materializing").exists()
    restricted = replace(candidate, candidate_id="candidate:restricted", license_policy="unknown_user_owned", warning_provenance=("copyright_confirmation_required",))
    restricted_result = materializer.materialize(project_id=project.project_id, candidate=restricted)
    assert restricted_result["asset_id"] != first["asset_id"]
    assert restricted_result["warning_provenance"] == ["copyright_confirmation_required"]


def test_candidate_materializer_uses_short_staging_filename_before_store_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(b"clip").hexdigest()
    run = store.create_media_analysis(project_id=project.project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="x")
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"], expected_attempt=claim["attempt"], result={"frame": "ok"})
    session = store.save_editing_session(project_id=project.project_id, timeline_id="t", session_payload={"segments": [{"segment_id": "s", "caption_text": "clip"}], "history": []})
    candidate = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"]).candidates[0]
    registered_source_names: list[str] = []
    original_register = store.register_asset

    def capture_register(**kwargs):
        registered_source_names.append(kwargs["source_path"].name)
        return original_register(**kwargs)

    monkeypatch.setattr(store, "register_asset", capture_register)

    ProjectAssetMaterializer(store).materialize(project_id=project.project_id, candidate=candidate)

    assert len(registered_source_names) == 1
    assert registered_source_names[0].startswith("stage-")
    assert registered_source_names[0].endswith(".mp4")
    assert len(registered_source_names[0]) <= 20


def test_candidate_materializer_rejects_source_mutation_and_leaves_no_stage_or_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("p")
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(b"clip").hexdigest(); run = store.create_media_analysis(project_id=project.project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="x")
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"], expected_attempt=claim["attempt"], result={"frame": "ok"})
    session = store.save_editing_session(project_id=project.project_id, timeline_id="t", session_payload={"segments": [{"segment_id": "s", "caption_text": "clip"}], "history": []})
    before = deepcopy(store.get_editing_session(project_id=project.project_id, session_id=session["session_id"]))
    candidate = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"]).candidates[0]
    original_copy = materializer_module.shutil.copy2
    def mutate_after_stage(src, dst, *args, **kwargs):
        result = original_copy(src, dst, *args, **kwargs)
        Path(src).write_bytes(b"changed")
        return result
    monkeypatch.setattr(materializer_module.shutil, "copy2", mutate_after_stage)
    with pytest.raises(ValueError, match="staging"):
        ProjectAssetMaterializer(store).materialize(project_id=project.project_id, candidate=candidate)
    assert len(store.list_assets(project_id=project.project_id)) == 1
    assert not (store.project_root(project.project_id) / ".materializing").exists()
    assert store.get_editing_session(project_id=project.project_id, session_id=session["session_id"]) == before


def test_candidate_materializer_compensates_when_delete_unlink_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("p")
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(b"clip").hexdigest(); run = store.create_media_analysis(project_id=project.project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="x")
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"], expected_attempt=claim["attempt"], result={"frame": "ok"})
    session = store.save_editing_session(project_id=project.project_id, timeline_id="t", session_payload={"segments": [{"segment_id": "s", "caption_text": "clip"}], "history": []})
    candidate = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"]).candidates[0]
    original_sha, original_unlink = materializer_module.sha256_file, Path.unlink
    def mismatch_new_project(path: Path) -> str:
        if path.name != "clip.mp4" and path.suffix == ".mp4" and "assets" in str(path): return "0" * 64
        return original_sha(path)
    failed = {"done": False}
    def fail_once(path: Path, *args, **kwargs):
        if path.name != "clip.mp4" and path.suffix == ".mp4" and not failed["done"]:
            failed["done"] = True; raise OSError("injected unlink failure")
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(materializer_module, "sha256_file", mismatch_new_project)
    monkeypatch.setattr(Path, "unlink", fail_once)
    with pytest.raises(ValueError, match="project_sha"):
        ProjectAssetMaterializer(store).materialize(project_id=project.project_id, candidate=candidate)
    assert failed["done"]
    assert len(store.list_assets(project_id=project.project_id)) == 1
    assert not (store.project_root(project.project_id) / ".materializing").exists()
    assert len(list((store.project_root(project.project_id) / "assets").rglob("*.mp4"))) == 1
    with pytest.raises(ValueError, match="media_revision"):
        replace(candidate, media_revision=None)  # type: ignore[arg-type]


def test_preview_snapshot_body_stays_at_candidate_sha_after_source_changes(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path / "projects"); project = store.bootstrap_project("p")
    source = tmp_path / "clip.mp4"; source.write_bytes(b"clip")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source, metadata={"review_status": "approved"})
    digest = sha256(b"clip").hexdigest(); run = store.create_media_analysis(project_id=project.project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:local", cache_key="x")
    claim = store.claim_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project.project_id, analysis_id=run["analysis_id"], expected_attempt=claim["attempt"], result={"frame": "ok"})
    session = store.save_editing_session(project_id=project.project_id, timeline_id="t", session_payload={"segments": [{"segment_id": "s", "caption_text": "clip"}], "history": []})
    candidate = DirectorProposalService(store).create(project_id=project.project_id, session_id=session["session_id"]).candidates[0]
    snapshot = ProjectAssetMaterializer(store).preview_snapshot(project_id=project.project_id, candidate=candidate)
    store.resolve_storage_uri(project_id=project.project_id, storage_uri=store.get_asset(project_id=project.project_id, asset_id=asset.asset_id)["storage_uri"]).write_bytes(b"mutated")
    assert sha256(snapshot.read_bytes()).hexdigest() == candidate.expected_content_sha256
    _remove_preview_snapshot(snapshot)
    assert not snapshot.parent.exists()


def test_store_startup_reconciles_uncommitted_batch_manifest_but_preserves_registered_bytes(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    store = LocalProjectStore(root); project = store.bootstrap_project("reconcile")
    operation_dir = store.project_root(project.project_id) / ".batch-director-operations"
    stage = operation_dir / "op-stale" / "stage.mp4"; destination = store.project_root(project.project_id) / "assets" / "imported" / "orphan.mp4"
    stage.parent.mkdir(parents=True); stage.write_bytes(b"staged"); destination.write_bytes(b"orphan")
    manifest = operation_dir / "op-stale.json"
    manifest.write_text(__import__("json").dumps({"operation_id": "op-stale", "status": "staging", "entries": [{"staged_path": str(stage), "destination_path": str(destination), "sha256": sha256(b"orphan").hexdigest()}]}), encoding="utf-8")

    LocalProjectStore(root)

    assert not stage.exists() and not destination.exists() and not manifest.exists()

    source = tmp_path / "verified.mp4"; source.write_bytes(b"verified")
    registered = store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    verified_destination = store.resolve_storage_uri(project_id=project.project_id, storage_uri=registered.storage_uri)
    operation_dir.mkdir()
    committed = operation_dir / "op-committed.json"
    committed.write_text(__import__("json").dumps({"operation_id": "op-committed", "status": "committed", "entries": [{"staged_path": str(operation_dir / "gone.mp4"), "destination_path": str(verified_destination), "sha256": sha256(b"verified").hexdigest()}]}), encoding="utf-8")

    LocalProjectStore(root)

    assert verified_destination.exists() and verified_destination.read_bytes() == b"verified"
    assert not committed.exists()


def test_store_startup_retains_unsafe_batch_manifest_without_touching_its_paths(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    store = LocalProjectStore(root); project = store.bootstrap_project("unsafe-reconcile")
    operations = store.project_root(project.project_id) / ".batch-director-operations"
    stage = operations / "op-unsafe" / "stage.mp4"; stage.parent.mkdir(parents=True); stage.write_bytes(b"stage")
    outside = tmp_path / "must-not-delete.mp4"; outside.write_bytes(b"operator-file")
    manifest = operations / "op-unsafe.json"
    manifest.write_text(__import__("json").dumps({"operation_id": "op-unsafe", "status": "staging", "entries": [{"staged_path": str(stage), "destination_path": str(outside), "sha256": sha256(b"operator-file").hexdigest()}]}), encoding="utf-8")
    stale_tmp = operations / "op-unsafe.tmp"; stale_tmp.write_text("partial", encoding="utf-8")

    LocalProjectStore(root)

    assert outside.read_bytes() == b"operator-file"
    assert stage.exists()
    assert manifest.exists()
    assert not stale_tmp.exists()
